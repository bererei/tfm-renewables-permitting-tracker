from __future__ import annotations

import copy
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from evaluation.final_holdout_v1 import evaluator as v1
from evaluation.final_holdout_v2 import evaluator as module
from evaluation.final_holdout_v2 import evaluator_freeze as freeze_module
from evaluation.final_holdout_v2.artifacts import inventory
from evaluation.final_holdout_v2.cli import main
from evaluation.final_holdout_v2.contract import TruthContractError, load_truth, sha256_file
from evaluation.final_holdout_v2.evaluator import evaluate, validate_evaluation
from evaluation.final_holdout_v2.evaluator_freeze import evaluator_declaration, freeze_evaluator, validate_evaluator
from evaluation.final_holdout_v2.predictions import EvaluationError
from v2b_fixtures import BOE, OTHER, make_case, publish_case
from test_final_holdout_v1 import _refresh_snapshot_artifact, _rewrite_prediction_payload
from test_primary_execution import case as primary_case


@pytest.fixture
def published(tmp_path):
    case = make_case(tmp_path)
    case.add_action("historical_antecedent")
    case.add_action("historical_antecedent", predict=False)
    case.warn(2)
    return publish_case(case, tmp_path)


def refresh_record(inputs):
    snapshot = v1.load_prediction_snapshot(inputs["predictions_dir"])
    path = inputs["execution_record_path"]
    record = json.loads(path.read_text())
    record["extraction_output_identity"] = snapshot.snapshot_identity
    path.write_text(json.dumps(record))


def freeze_args(inputs, output):
    truth = load_truth(inputs["truth_dir"], require_frozen=True)
    return {"truth_dir": inputs["truth_dir"], "output_dir": output,
            "expected_truth_artifact_id": truth.truth_artifact_id,
            "expected_truth_manifest_sha256": sha256_file(inputs["truth_dir"] / "manifest.json")}


def test_frozen_evaluator_and_report_roundtrip_provenance(published, tmp_path):
    before = {name: inventory(published[name]) for name in ("truth_dir", "predictions_dir", "evaluator_dir")}
    result = evaluate(**published)
    manifest = validate_evaluation(result.output_dir, expected_manifest_sha256=sha256_file(result.output_dir / "manifest.json"))
    assert manifest["evaluation_output_id"] == result.evaluation_output_id
    summary = json.loads((result.output_dir / "evaluation_summary.json").read_text())
    provenance = summary["provenance"]
    assert provenance["truth_artifact_id"] == load_truth(published["truth_dir"]).truth_artifact_id
    assert provenance["truth_manifest_sha256"] == before["truth_dir"]["manifest.json"]
    assert provenance["frozen_production_git_commit"] == "282de815bea4e248bdcba2c655e3ee078cb58a49"
    assert provenance["evaluator_identity"] == evaluator_declaration()["evaluator_identity"]
    assert provenance["prediction_snapshot_identity"] == v1.load_prediction_snapshot(published["predictions_dir"]).snapshot_identity
    assert result.metrics["entity_detection"]["administrative_action"]["historical_contamination_fp"] == 1
    assert result.metrics["p0"]["tp"] == 1
    assert result.metrics["p0"]["fn"] == 0
    assert len(manifest["artifact_sha256"]) == 16
    assert str(tmp_path) not in json.dumps(summary)
    for name in before:
        assert inventory(published[name]) == before[name]
    assert not list(tmp_path.glob(".*.staging-*"))


def test_report_identity_reproducible_with_same_inputs(published, tmp_path):
    first = evaluate(**published)
    second = evaluate(**{**published, "output_dir": tmp_path / "report_again"})
    assert first.metrics == second.metrics
    assert first.evaluation_output_id == second.evaluation_output_id
    for path in first.output_dir.glob("*.parquet"):
        assert path.read_bytes() == (second.output_dir / path.name).read_bytes()


def test_freeze_identity_excludes_destination_time_and_truth_rows(published, tmp_path):
    args = freeze_args(published, tmp_path / "another_evaluator")
    first = validate_evaluator(published["evaluator_dir"])
    second = freeze_evaluator(**args)
    assert first["created_at_utc"] != second["created_at_utc"]
    assert first["declaration"] == second["declaration"]
    assert str(tmp_path) not in json.dumps(second)
    assert validate_evaluator(args["output_dir"], expected_evaluator_identity=second["declaration"]["evaluator_identity"])


def test_evaluator_identity_relative_code_configuration_and_contract(tmp_path):
    root = freeze_module.REPO_ROOT
    replica = tmp_path / "replica"
    replica.mkdir()
    for directory in ("evaluation/final_holdout_v1", "evaluation/final_holdout_v2", "src/renewables_permitting"):
        shutil.copytree(root / directory, replica / directory, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("uv.lock", "pyproject.toml", "evaluation/__init__.py"):
        shutil.copyfile(root / name, replica / name)
    original = evaluator_declaration()
    assert evaluator_declaration(repo_root=replica) == original
    for relative in ("evaluation/final_holdout_v2/evaluator.py", "evaluation/final_holdout_v2/scoring.py", "evaluation/final_holdout_v2/scoring_rules.json",
                     "evaluation/final_holdout_v2/contract.json", "evaluation/final_holdout_v1/matching.py",
                     "src/renewables_permitting/gold.py", "uv.lock"):
        file = replica / relative
        before = file.read_bytes()
        file.write_bytes(before + b"\n")
        assert evaluator_declaration(repo_root=replica)["evaluator_identity"] != original["evaluator_identity"]
        file.write_bytes(before)


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
def test_existing_outputs_refused_for_both_publications(published, tmp_path, kind):
    output = tmp_path / "occupied"
    if kind == "directory":
        output.mkdir()
        (output / "keep").write_text("keep")
    elif kind == "file":
        output.write_text("keep")
    else:
        output.symlink_to(tmp_path / "absent")
    for operation in (lambda: evaluate(**{**published, "output_dir": output}),
                      lambda: freeze_evaluator(**freeze_args(published, output))):
        with pytest.raises(FileExistsError):
            operation()
    assert output.is_symlink() if kind == "symlink" else (output / "keep" if output.is_dir() else output).read_text() == "keep"


def test_working_truth_rejected_in_both_paths(published, tmp_path):
    working = tmp_path / "working"
    with pytest.raises(TruthContractError):
        evaluate(**{**published, "truth_dir": working})
    args = freeze_args(published, tmp_path / "another")
    with pytest.raises(TruthContractError):
        freeze_evaluator(**{**args, "truth_dir": working})


@pytest.mark.parametrize("kind", ["csv", "manifest", "removed_manifest", "extra", "symlink"])
def test_corrupt_frozen_truth_rejected(published, kind):
    path = published["truth_dir"]
    if kind == "csv":
        target = path / "documents.csv"
        target.write_bytes(target.read_bytes() + b"\n")
    elif kind == "manifest":
        (path / "manifest.json").write_text("{}")
    elif kind == "removed_manifest":
        (path / "manifest.json").unlink()
    elif kind == "extra":
        (path / "extra").write_text("unexpected")
    else:
        target = path / "documents.csv"
        copy_path = path.parent / "documents-copy.csv"
        shutil.copyfile(target, copy_path)
        target.unlink()
        target.symlink_to(copy_path)
    with pytest.raises((TruthContractError, EvaluationError)):
        evaluate(**published)
    assert not published["output_dir"].exists()


@pytest.mark.parametrize("keyword", ["expected_truth_artifact_id", "expected_truth_manifest_sha256",
    "expected_evaluator_identity", "expected_evaluator_manifest_sha256"])
def test_explicit_wrong_expectations_rejected(published, keyword):
    with pytest.raises((TruthContractError, EvaluationError)):
        evaluate(**published, **{keyword: "0" * 64})
    assert not published["output_dir"].exists()


@pytest.mark.parametrize("kind", ["corrupt", "rules", "extra", "wrong_identity", "changed_code", "manifest_expectation"])
def test_evaluator_freeze_integrity(published, monkeypatch, kind):
    path = published["evaluator_dir"]
    kwargs = {}
    if kind == "corrupt":
        (path / "manifest.json").write_text("{}")
    elif kind == "rules":
        (path / "scoring_rules.json").write_text("{}")
    elif kind == "extra":
        (path / "extra.txt").write_text("extra")
    elif kind == "wrong_identity":
        kwargs["expected_evaluator_identity"] = "0" * 64
    elif kind == "manifest_expectation":
        kwargs["expected_manifest_sha256"] = "0" * 64
    else:
        changed = copy.deepcopy(evaluator_declaration())
        changed["source_file_sha256"]["evaluation/final_holdout_v2/scoring.py"] = "0" * 64
        monkeypatch.setattr(freeze_module, "evaluator_declaration", lambda: changed)
    with pytest.raises(EvaluationError):
        validate_evaluator(path, **kwargs)


@pytest.mark.parametrize("kind", ["wrong_universe", "duplicate_document", "duplicate_attempt", "retry", "inherited", "current_drift",
    "source_content", "manual", "historical_correction", "historical_review", "queue_outside", "queue_attempt", "status"])
def test_primary_prediction_lineage_rejections(published, kind):
    root = published["predictions_dir"]
    table = {"wrong_universe": "documents", "duplicate_document": "documents", "duplicate_attempt": "attempts",
             "retry": "attempts", "inherited": "attempts", "current_drift": "current_extractions", "source_content": "documents",
             "manual": "manual_reviews", "historical_correction": "historical_antecedent_corrections",
             "historical_review": "historical_antecedent_reviews", "queue_outside": "review_queue",
             "queue_attempt": "review_queue", "status": "attempts"}[kind]
    suffix = "csv" if kind.startswith("historical_") else "parquet"
    path = root / f"{table}.{suffix}"
    frame = pd.read_csv(path) if suffix == "csv" else pd.read_parquet(path)
    if kind == "wrong_universe":
        frame.loc[0, "identificador"] = "BOE-A-2099-999"
    elif kind in {"duplicate_document", "retry"}:
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif kind == "duplicate_attempt":
        frame.loc[1, "attempt_id"] = frame.loc[0, "attempt_id"]
    elif kind == "inherited":
        frame.loc[0, "source_attempt_id"] = "old-attempt"
    elif kind == "current_drift":
        frame.loc[0, "extraction_json"] = "{}"
    elif kind == "source_content":
        frame.loc[0, "texto_limpio"] = "different source"
    elif kind == "manual":
        frame = pd.DataFrame([{"identificador_boe": BOE}])
    elif kind.startswith("historical_"):
        frame = pd.DataFrame([{"boe_id": BOE}])
    elif kind == "queue_outside":
        frame.loc[0, "identificador_boe"] = "BOE-A-2099-999"
    elif kind == "queue_attempt":
        frame["attempt_id"] = "not_primary"
    elif kind == "status":
        frame.loc[0, "extraction_status"] = "invented_status"
    frame.to_csv(path, index=False) if suffix == "csv" else frame.to_parquet(path, index=False)
    _refresh_snapshot_artifact(root, table, len(frame))
    with pytest.raises((EvaluationError, TruthContractError)):
        evaluate(**published)
    assert not published["output_dir"].exists()


@pytest.mark.parametrize("kind", ["boe_identity", "duplicate_ref", "scope_drift", "invalid_json", "duplicate_json_key"])
def test_prediction_shape_rejected_without_silent_repair(published, kind):
    def change(payload):
        if kind == "boe_identity":
            payload["boe_id"] = OTHER
        elif kind == "duplicate_ref":
            assets = payload["publication_events"][0]["generation_assets"]
            assets.append(copy.deepcopy(assets[0]))
        elif kind == "scope_drift":
            payload["document_scope"] = "not_relevant_for_generation_projects"
    _rewrite_prediction_payload(published["predictions_dir"], BOE, change)
    if kind in {"invalid_json", "duplicate_json_key"}:
        for table in ("attempts", "current_extractions"):
            path = published["predictions_dir"] / f"{table}.parquet"
            frame = pd.read_parquet(path)
            i = frame.index[frame["identificador_boe"].eq(BOE)][0]
            frame.at[i, "extraction_json"] = "{" if kind == "invalid_json" else '{"boe_id":"first",' + frame.at[i, "extraction_json"][1:]
            frame.to_parquet(path, index=False)
            _refresh_snapshot_artifact(published["predictions_dir"], table, len(frame))
    refresh_record(published)
    with pytest.raises(EvaluationError):
        evaluate(**published)


@pytest.mark.parametrize("kind", ["model", "config", "hash"])
def test_incompatible_prediction_manifest(published, kind):
    path = published["predictions_dir"] / "manifest.json"
    value = json.loads(path.read_text())
    if kind == "model":
        value["model_name"] = "different-model"
    elif kind == "config":
        value["extraction_config_id"] = "different-config"
    else:
        value["artifacts"]["attempts"]["sha256"] = "0" * 64
    path.write_text(json.dumps(value))
    with pytest.raises(EvaluationError):
        evaluate(**published)


@pytest.mark.parametrize("kind", ["early_run", "human", "wrong_truth", "wrong_snapshot", "usage"])
def test_execution_record_integrity_and_pre_execution_freeze(published, kind):
    path = published["execution_record_path"]
    record = json.loads(path.read_text())
    if kind == "early_run":
        for field in ("started_at_utc", "ended_at_utc", "primary_predictions_frozen_at_utc"):
            record[field] = record[field].replace("2099", "2000")
    elif kind == "human":
        record["manual_intervention_before_primary_freeze"] = True
    elif kind == "wrong_truth":
        record["holdout_artifact_identity"] = "0" * 64
    elif kind == "wrong_snapshot":
        record["extraction_output_identity"] = "0" * 64
    else:
        record["model_usage"]["requests"] = 0
    path.write_text(json.dumps(record))
    with pytest.raises(EvaluationError):
        evaluate(**published)


@pytest.mark.parametrize("kind", ["score_failure", "write_failure", "rename_failure", "destination_appears", "input_changes", "code_changes"])
def test_failed_evaluation_never_publishes_partial_output(published, tmp_path, monkeypatch, kind):
    original = module.evaluate_frames
    before = inventory(published["truth_dir"])
    if kind == "write_failure":
        def fail_write(*args, **kwargs):
            raise OSError("injected write failure")
        monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_write)
    elif kind == "rename_failure":
        def fail_rename(*args, **kwargs):
            raise OSError("injected rename failure")
        monkeypatch.setattr(Path, "rename", fail_rename)
    else:
        def wrapped(*args):
            if kind == "score_failure":
                raise EvaluationError("injected scoring failure")
            result = original(*args)
            if kind == "destination_appears":
                published["output_dir"].mkdir()
                (published["output_dir"] / "keep").write_text("concurrent writer")
            elif kind == "input_changes":
                (published["predictions_dir"] / "extra").write_text("changed input")
            elif kind == "code_changes":
                monkeypatch.setattr(module, "evaluator_declaration", lambda: {})
            return result
        monkeypatch.setattr(module, "evaluate_frames", wrapped)
    with pytest.raises((EvaluationError, OSError)):
        evaluate(**published)
    if kind == "destination_appears":
        assert (published["output_dir"] / "keep").read_text() == "concurrent writer"
    else:
        assert not published["output_dir"].exists()
    assert inventory(published["truth_dir"]) == before
    assert not list(tmp_path.glob(".*.staging-*"))


@pytest.mark.parametrize("kind", ["table", "summary", "manifest", "extra", "expected_hash"])
def test_corrupt_report_detected_without_original_inputs(published, kind):
    result = evaluate(**published)
    path = result.output_dir
    if kind == "table":
        (path / "field_results.parquet").write_bytes(b"bad parquet")
    elif kind == "summary":
        (path / "evaluation_summary.json").write_text("{}")
    elif kind == "manifest":
        (path / "manifest.json").write_text("{}")
    elif kind == "extra":
        (path / "extra.txt").write_text("extra")
    for name in ("truth_dir", "predictions_dir", "evaluator_dir"):
        shutil.rmtree(published[name])
    with pytest.raises(EvaluationError):
        validate_evaluation(path, **({"expected_manifest_sha256": "0" * 64} if kind == "expected_hash" else {}))


def test_cli_synthetic_freeze_validate_evaluate_and_verify(published, tmp_path, capsys):
    truth = load_truth(published["truth_dir"], require_frozen=True)
    evaluator_dir = tmp_path / "cli_evaluator"
    assert main(["freeze-evaluator", "--truth", str(published["truth_dir"]), "--output", str(evaluator_dir),
                 "--expected-truth-artifact-id", truth.truth_artifact_id,
                 "--expected-truth-manifest-sha256", sha256_file(published["truth_dir"] / "manifest.json")]) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert main(["validate-evaluator", "--evaluator", str(evaluator_dir), "--expected-evaluator-identity", frozen["evaluator_identity"],
                 "--expected-manifest-sha256", frozen["manifest_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    assert main(["validate-execution-record", "--record", str(published["execution_record_path"])]) == 0
    capsys.readouterr()
    argv = ["evaluate"]
    for key, value in published.items():
        flag = {"truth_dir": "truth", "predictions_dir": "predictions", "evaluator_dir": "evaluator", "execution_record_path": "execution-record", "output_dir": "output"}[key]
        argv.extend([f"--{flag}", str(value)])
    assert main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert main(["validate-evaluation", "--evaluation", str(published["output_dir"])]) == 0
    assert json.loads(capsys.readouterr().out)["evaluation_output_id"] == output["evaluation_output_id"]


@pytest.mark.parametrize("command", ["freeze-evaluator", "validate-evaluator", "evaluate", "validate-evaluation"])
def test_cli_help_does_not_execute(command, capsys):
    with pytest.raises(SystemExit) as result:
        main([command, "--help"])
    assert result.value.code == 0
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("attempts,requests,accepted", [
    ([("model", "ok")], 1, True),
    ([("model", "ok")], 0, False),
    ([("model", "error")], 0, True),
    ([("model", "ok"), ("model", "ok"), ("model", "error")], 2, True),
    ([("model", "ok"), ("model", "ok"), ("model", "error")], 1, False),
    ([("deterministic", "ok"), ("deterministic", "error")], 0, True),
    ([("model", "ok"), ("deterministic", "ok")], 1, True),
    ([("model", "ok")] * 3 + [("model", "error")] * 4, 3, True),
    ([("model", "error")] * 3, 0, True),
    ([("model", "ok"), ("model", "error")], 5, True),
], ids=["success", "unreported_success", "unreported_error", "two_success_one_error",
        "insufficient_for_successes", "non_model", "mixed_origins", "several_errors",
        "only_errors", "reported_retries"])
def test_requests_guard_matrix(published, monkeypatch, attempts, requests, accepted):
    """Isolate the usage gate; full primary validation is covered below."""
    snapshot = module.load_prediction_snapshot(published["predictions_dir"])
    frame = pd.DataFrame(attempts, columns=["attempt_origin", "extraction_status"])
    candidate = replace(snapshot, attempts=frame)
    before_frame = frame.copy(deep=True)
    path = published["execution_record_path"]
    record = json.loads(path.read_text())
    record["model_usage"]["requests"] = requests
    path.write_text(json.dumps(record))
    before_record = path.read_bytes()
    monkeypatch.setattr(module, "load_prediction_snapshot", lambda *args: candidate)
    monkeypatch.setattr(module, "validate_primary_predictions", lambda *args: None)

    class ReachedScoring(Exception):
        pass

    def stop_before_scoring(*args):
        raise ReachedScoring

    monkeypatch.setattr(module, "evaluate_frames", stop_before_scoring)
    if accepted:
        with pytest.raises(ReachedScoring):
            evaluate(**published)
    else:
        with pytest.raises(EvaluationError, match="Fewer recorded model requests than successful model-origin attempts"):
            evaluate(**published)
    assert path.read_bytes() == before_record
    pd.testing.assert_frame_equal(frame, before_frame)
    assert not published["output_dir"].exists()


def test_requests_guard_preserves_pre_fix_scientific_results(published):
    # Captured before changing the guard, from the same invented published fixture.
    baseline = json.loads((Path(__file__).parent / "fixtures/v2b_usage_guard_pre_fix.json").read_text())
    result = evaluate(**published)
    assert result.metrics == baseline["metrics"]
    actual = {name: module._frame_identity(pd.read_parquet(result.output_dir / f"{name}.parquet"))
              for name in sorted(module.REPORT_TABLES)}
    assert actual == baseline["semantic_table_sha256"]
    assert (result.output_dir / "execution_record.json").read_bytes() == published["execution_record_path"].read_bytes()
    assert evaluator_declaration()["evaluator_identity"] != baseline["evaluator_identity"]


def test_requests_guard_accepts_preserved_transport_error(primary_case, monkeypatch, tmp_path):
    """Real PydanticAI graph + frozen runner, local fake model and no network."""
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.output import NativeOutput
    from renewables_permitting import pipeline
    from renewables_permitting.extraction.config import AGENT_RETRIES
    from renewables_permitting.extraction.instructions import AGENT_INSTRUCTIONS
    from renewables_permitting.extraction.models import BOEAIExtraction
    from evaluation.final_holdout_v2.predictions import load_prediction_snapshot, validate_primary_predictions
    from test_primary_execution import FakeAgent, prepare, run, finalize

    case = primary_case
    failed_boe = case.documents.iloc[1].identificador
    fake_invocations = []

    async def fail_before_response(messages, info):
        fake_invocations.append("synthetic_503")
        raise ModelHTTPError(status_code=503, model_name="synthetic-function-model", body="Synthetic transport failure")

    local_agent = Agent(FunctionModel(fail_before_response), output_type=NativeOutput(BOEAIExtraction),
                        instructions=AGENT_INSTRUCTIONS, retries=AGENT_RETRIES)
    successful_fake = FakeAgent(case)

    class SelectiveAgent:
        async def run(self, prompt, **kwargs):
            target = local_agent if prompt.split("BOE_ID: ")[1].splitlines()[0] == failed_boe else successful_fake
            return await target.run(prompt, **kwargs)

    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", SelectiveAgent)
    prepare(case)
    status = run(case)
    assert status["counts"]["TERMINAL_ERROR"] == 1
    provenance = finalize(case)
    snapshot_dir = case.root / "primary/extraction"
    snapshot = load_prediction_snapshot(snapshot_dir)
    validate_primary_predictions(snapshot, case.truth)
    failed = snapshot.attempts.loc[snapshot.attempts.identificador_boe.eq(failed_boe)].iloc[0]
    assert failed.attempt_origin == "model" and failed.extraction_status == "error"
    assert failed.usage_requests == 0 and len(fake_invocations) == 2
    assert len(snapshot.attempts) == 3 and len(snapshot.current_extractions) == 2
    record_path = case.root / "finalization/execution_record.json"
    before_record = record_path.read_bytes()
    record = json.loads(before_record)
    assert record["model_usage"]["requests"] == 2
    assert provenance["document_executions_started"] == 3
    # Controller compatibility diagnostic retains the historical bound; it is not
    # the corrected evaluator's admissibility gate and is deliberately unchanged.
    assert provenance["frozen_evaluator_usage_guard_satisfied"] is False
    before = inventory(case.root)
    result = evaluate(truth_dir=case.args["truth_dir"], evaluator_dir=case.args["evaluator_dir"],
                      predictions_dir=snapshot_dir, execution_record_path=record_path,
                      output_dir=tmp_path / "accepted_report")
    assert inventory(case.root) == before
    assert (result.output_dir / "execution_record.json").read_bytes() == before_record
    validate_evaluation(result.output_dir)


@pytest.mark.parametrize("kind", ["document_digest", "row_count", "extra_artifact", "duplicate_artifact_file"])
def test_all_prediction_artifacts_and_document_digest_are_verified(published, kind):
    path = published["predictions_dir"] / "manifest.json"
    manifest = json.loads(path.read_text())
    if kind == "document_digest":
        manifest["document_identity_sha256"] = "0" * 64
    elif kind == "row_count":
        manifest["artifacts"]["attempts"]["row_count"] = 999
    elif kind == "extra_artifact":
        manifest["artifacts"]["extra"] = {"filename": "absent.json", "sha256": "0" * 64}
    else:
        manifest["artifacts"]["extra"] = manifest["artifacts"]["attempts"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(EvaluationError):
        evaluate(**published)


@pytest.mark.parametrize("name", ["truth_dir", "predictions_dir", "evaluator_dir"])
def test_output_inside_input_is_rejected(published, name):
    with pytest.raises(EvaluationError, match="inside"):
        evaluate(**{**published, "output_dir": published[name] / "nested_report"})


def test_freeze_rejects_wrong_truth_identity(published, tmp_path):
    args = freeze_args(published, tmp_path / "new_evaluator")
    args["expected_truth_artifact_id"] = "0" * 64
    with pytest.raises(EvaluationError):
        freeze_evaluator(**args)
    assert not args["output_dir"].exists()


@pytest.mark.parametrize("kind", ["write", "rename", "source_changes"])
def test_evaluator_freeze_failure_cleans_staging(published, tmp_path, monkeypatch, kind):
    args = freeze_args(published, tmp_path / "another_evaluator")
    if kind == "source_changes":
        original = freeze_module.validate_evaluator
        def changed(*a, **kw):
            result = original(*a, **kw)
            (published["truth_dir"] / "changed_input").write_text("injected")
            return result
        monkeypatch.setattr(freeze_module, "validate_evaluator", changed)
    else:
        def fail(*a, **kw):
            raise OSError("injected failure")
        if kind == "write":
            monkeypatch.setattr(freeze_module, "write_json", fail)
        else:
            monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises((EvaluationError, OSError)):
        freeze_evaluator(**args)
    assert not args["output_dir"].exists()
    assert not list(tmp_path.glob(".*.staging-*"))


def test_valid_report_verification_is_independent_of_original_inputs(published):
    result = evaluate(**published)
    for name in ("truth_dir", "predictions_dir", "evaluator_dir"):
        shutil.rmtree(published[name])
    assert validate_evaluation(result.output_dir)["evaluation_output_id"] == result.evaluation_output_id
