"""Public offline evaluator: verified freezes, provenance, immutable reports."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from evaluation.final_holdout_v2.artifacts import (
    identity, inventory, new_artifact, require_new_output, utc_now, write_json,
)
from evaluation.final_holdout_v2.contract import CONTRACT_VERSION, FROZEN_PRODUCTION_COMMIT, load_truth, sha256_file
from evaluation.final_holdout_v2.evaluator_freeze import evaluator_declaration, validate_evaluator
from evaluation.final_holdout_v2.predictions import (
    EvaluationError, load_prediction_snapshot, validate_execution_record, validate_primary_predictions,
)
from evaluation.final_holdout_v2.scoring import FRAME_COLUMNS, evaluate_frames


REPORT_VERSION = "final_holdout_evaluation_report_v2_b_1"
REPORT_TABLES = {*FRAME_COLUMNS, "entity_matches", "unmatched_truth", "unmatched_predictions"}


@dataclass(frozen=True)
class EvaluationResult:
    output_dir: Path
    evaluation_output_id: str
    metrics: dict


def _frame_identity(frame: pd.DataFrame) -> str:
    rows = [{key: None if pd.isna(value) else value for key, value in row.items()}
            for row in frame.to_dict(orient="records")]
    return identity({"columns": list(frame.columns), "dtypes": [str(t) for t in frame.dtypes],
                     "rows": sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))})


def _report_payload(summary: dict, semantic_tables: dict) -> dict:
    return {"report_version": REPORT_VERSION,
            "summary": {k: v for k, v in summary.items() if k != "created_at_utc"},
            "semantic_table_sha256": semantic_tables}


def validate_evaluation(path: Path, *, expected_manifest_sha256: str | None = None) -> dict:
    """Verify report bytes and recompute content identity without any prediction reads."""
    path = Path(path)
    files = inventory(path)
    expected_files = {f"{name}.parquet" for name in REPORT_TABLES} | {
        "manifest.json", "evaluation_summary.json", "execution_record.json", "evaluator_manifest.json", "truth_manifest.json"}
    if set(files) != expected_files:
        raise EvaluationError("Evaluation report inventory mismatch.")
    if expected_manifest_sha256 is not None and files["manifest.json"] != expected_manifest_sha256:
        raise EvaluationError("Evaluation report manifest differs from expectation.")
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((path / "evaluation_summary.json").read_text(encoding="utf-8"))
        if manifest["report_version"] != REPORT_VERSION:
            raise EvaluationError("Incompatible evaluation report version.")
        if manifest["artifact_sha256"] != {k: v for k, v in files.items() if k != "manifest.json"}:
            raise EvaluationError("Evaluation report file integrity mismatch.")
        if manifest["manifest_identity_sha256"] != identity({k: v for k, v in manifest.items() if k != "manifest_identity_sha256"}):
            raise EvaluationError("Evaluation report manifest integrity mismatch.")
        semantic = {name: _frame_identity(pd.read_parquet(path / f"{name}.parquet")) for name in sorted(REPORT_TABLES)}
        payload = _report_payload(summary, semantic)
        if manifest["evaluation_output_id"] != identity(payload) or manifest["semantic_table_sha256"] != semantic:
            raise EvaluationError("Evaluation report semantic identity mismatch.")
        provenance = summary["provenance"]
        for filename, key in (("truth_manifest.json", "truth_manifest_sha256"),
                              ("evaluator_manifest.json", "evaluator_manifest_sha256"),
                              ("execution_record.json", "execution_record_sha256")):
            if files[filename] != provenance[key]:
                raise EvaluationError("Evaluation report copied provenance mismatch.")
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise EvaluationError(f"Invalid evaluation report: {error}") from error
    return manifest


def evaluate(*, truth_dir: Path, predictions_dir: Path, execution_record_path: Path,
             evaluator_dir: Path, output_dir: Path,
             expected_truth_artifact_id: str | None = None,
             expected_truth_manifest_sha256: str | None = None,
             expected_evaluator_identity: str | None = None,
             expected_evaluator_manifest_sha256: str | None = None) -> EvaluationResult:
    truth_dir, predictions_dir, evaluator_dir, output_dir = map(Path, (truth_dir, predictions_dir, evaluator_dir, output_dir))
    execution_record_path = Path(execution_record_path)
    protected = (truth_dir, predictions_dir, evaluator_dir)
    require_new_output(output_dir, protected)
    before = {str(path): inventory(path) for path in protected}
    if execution_record_path.is_symlink() or not execution_record_path.is_file():
        raise EvaluationError("Execution record must be a regular file.")
    record_sha = sha256_file(execution_record_path)
    frozen = validate_evaluator(evaluator_dir, expected_evaluator_identity=expected_evaluator_identity,
                                expected_manifest_sha256=expected_evaluator_manifest_sha256)
    binding = frozen["truth_binding"]
    truth = load_truth(truth_dir, require_frozen=True, expected_manifest_sha256=binding["truth_manifest_sha256"])
    if truth.truth_artifact_id != binding["truth_artifact_id"] or (
        expected_truth_artifact_id is not None and truth.truth_artifact_id != expected_truth_artifact_id
    ):
        raise EvaluationError("Unexpected truth artifact identity.")
    if expected_truth_manifest_sha256 is not None and binding["truth_manifest_sha256"] != expected_truth_manifest_sha256:
        raise EvaluationError("Unexpected truth manifest SHA-256.")
    for field in ("holdout_artifact_identity", "source_snapshot_identity"):
        if getattr(truth, field) != binding[field]:
            raise EvaluationError(f"Frozen evaluator truth {field} mismatch.")
    snapshot = load_prediction_snapshot(predictions_dir)
    validate_primary_predictions(snapshot, truth)
    record = validate_execution_record(execution_record_path, snapshot_identity=snapshot.snapshot_identity, truth=truth)
    if pd.Timestamp(frozen["created_at_utc"]) > pd.Timestamp(record["started_at_utc"]):
        raise EvaluationError("Evaluator must have been frozen before primary extraction started.")
    if any(type(v) is not int for v in record["model_usage"].values()):
        raise EvaluationError("Execution model usage must contain integers, not booleans.")
    # A terminal transport error may precede PydanticAI's usage increment.
    successful_model_attempts = int((
        snapshot.attempts["attempt_origin"].eq("model")
        & snapshot.attempts["extraction_status"].eq("ok")
    ).sum())
    if record["model_usage"]["requests"] < successful_model_attempts:
        raise EvaluationError("Fewer recorded model requests than successful model-origin attempts.")
    metrics, frames = evaluate_frames(truth, snapshot)
    provenance = {
        **binding, "truth_contract_version": CONTRACT_VERSION,
        "frozen_production_git_commit": FROZEN_PRODUCTION_COMMIT,
        "evaluator_version": frozen["declaration"]["evaluator_version"],
        "evaluator_identity": frozen["declaration"]["evaluator_identity"],
        "evaluator_manifest_sha256": before[str(evaluator_dir)]["manifest.json"],
        "prediction_snapshot_identity": snapshot.snapshot_identity,
        "prediction_manifest_sha256": before[str(predictions_dir)]["manifest.json"],
        "prediction_artifact_sha256": dict(snapshot.artifact_hashes),
        "execution_record_sha256": record_sha, "execution_run_id": record["run_id"],
        "primary_predictions": True, "manual_corrections_applied": False, "downstream_scored": False,
    }
    summary = {"report_version": REPORT_VERSION, "created_at_utc": utc_now(), "provenance": provenance,
               "scoring_configuration": frozen["declaration"]["scoring_configuration"], "metrics": metrics}
    with new_artifact(output_dir, protected=protected) as stage:
        write_json(stage / "evaluation_summary.json", summary)
        for source, name in ((execution_record_path, "execution_record.json"),
                             (evaluator_dir / "manifest.json", "evaluator_manifest.json"),
                             (truth_dir / "manifest.json", "truth_manifest.json")):
            (stage / name).write_bytes(source.read_bytes())
        semantic = {}
        for name, frame in sorted(frames.items()):
            path = stage / f"{name}.parquet"
            frame.to_parquet(path, index=False)
            reloaded = pd.read_parquet(path)
            assert_frame_equal(frame, reloaded)
            semantic[name] = _frame_identity(reloaded)
        output_id = identity(_report_payload(summary, semantic))
        manifest = {"report_version": REPORT_VERSION, "evaluation_output_id": output_id,
                    "semantic_table_sha256": semantic, "artifact_sha256": inventory(stage)}
        manifest["manifest_identity_sha256"] = identity(manifest)
        write_json(stage / "manifest.json", manifest)
        validate_evaluation(stage)
        if any(inventory(path) != before[str(path)] for path in protected) or sha256_file(execution_record_path) != record_sha:
            raise EvaluationError("Evaluation input changed during scoring/publication.")
        if evaluator_declaration() != frozen["declaration"]:
            raise EvaluationError("Evaluator code/rules changed during evaluation.")
    return EvaluationResult(output_dir=output_dir, evaluation_output_id=output_id, metrics=metrics)
