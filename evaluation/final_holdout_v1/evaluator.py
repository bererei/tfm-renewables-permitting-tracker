from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from evaluation.final_holdout_v1.contract import (
    CONTRACT_DECLARATION_PATH,
    CONTRACT_VERSION,
    FROZEN_CONTRACT_SHA256,
    FROZEN_EXTRACTION_CONFIG_ID,
    FROZEN_INSTRUCTIONS_SHA256,
    FROZEN_MODEL_NAME,
    FROZEN_MODEL_PROVIDER,
    FROZEN_PRODUCTION_COMMIT,
    FROZEN_SOURCE_SNAPSHOT_ID,
    FROZEN_UV_LOCK_SHA256,
    NA,
    POWER_ATTRIBUTE_TYPES,
    TruthArtifact,
    TruthContractError,
    canonical_json_bytes,
    load_truth,
    parse_json_list,
    sha256_file,
)
from evaluation.final_holdout_v1.matching import (
    MatchResult,
    deterministic_match,
    evidence_candidate,
    evidence_is_correct,
    metric_from_counts,
    name_candidate_pairs,
    normalize_evidence,
    normalize_name,
    parse_power_mw,
)


PRIMARY_ENTITY_TYPES = (
    "event",
    "generation_asset",
    "administrative_action",
    "participant",
    "location",
)
SECONDARY_ENTITY_TYPES = ("associated_component", "technical_mention")
REQUIRED_SNAPSHOT_ARTIFACTS = {
    "documents",
    "attempts",
    "manual_reviews",
    "current_extractions",
    "review_queue",
    "historical_antecedent_corrections",
    "historical_antecedent_reviews",
}
EXECUTION_RECORD_VERSION = "final_holdout_execution_record_v1"
HISTORICAL_ANTECEDENT_POLICY_VERSION = "1"
HISTORICAL_ANTECEDENT_REASON_CODE = "possible_historical_antecedent"
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_P0_ACTION_RE = re.compile(r"_event_([1-9]\d*)_action_([1-9]\d*)$")


class EvaluationError(ValueError):
    """Evaluation inputs are invalid or incompatible."""


@dataclass(frozen=True)
class PredictionSnapshot:
    path: Path
    manifest: Mapping[str, Any]
    snapshot_identity: str
    documents: pd.DataFrame
    attempts: pd.DataFrame
    manual_reviews: pd.DataFrame
    current_extractions: pd.DataFrame
    review_queue: pd.DataFrame
    historical_corrections: pd.DataFrame
    historical_reviews: pd.DataFrame
    artifact_hashes: Mapping[str, str]


@dataclass(frozen=True)
class EvaluationResult:
    output_dir: Path
    evaluation_output_id: str
    metrics: Mapping[str, Any]


def _load_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"Cannot read {label}: {path}.") from error
    if not isinstance(value, dict):
        raise EvaluationError(f"{label} must contain a JSON object.")
    return value


def _artifact_path(
    snapshot_dir: Path,
    manifest: Mapping[str, Any],
    artifact_name: str,
) -> tuple[Path, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise EvaluationError("Prediction manifest has no artifacts object.")
    entry = artifacts.get(artifact_name)
    if not isinstance(entry, dict):
        raise EvaluationError(f"Prediction manifest misses {artifact_name}.")
    filename = entry.get("filename")
    expected_sha = entry.get("sha256")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not isinstance(expected_sha, str)
        or not _SHA_RE.fullmatch(expected_sha)
    ):
        raise EvaluationError(f"Invalid artifact declaration: {artifact_name}.")
    path = snapshot_dir / filename
    if not path.is_file() or sha256_file(path) != expected_sha:
        raise EvaluationError(f"Prediction artifact hash mismatch: {artifact_name}.")
    return path, expected_sha


def _read_parquet(path: Path, *, label: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as error:
        raise EvaluationError(f"Cannot read {label} Parquet.") from error


def _read_optional_csv(
    snapshot_dir: Path,
    manifest: Mapping[str, Any],
    artifact_name: str,
) -> tuple[pd.DataFrame, str | None]:
    artifacts = manifest.get("artifacts", {})
    if artifact_name not in artifacts:
        return pd.DataFrame(), None
    path, digest = _artifact_path(snapshot_dir, manifest, artifact_name)
    try:
        return pd.read_csv(path, dtype="string", keep_default_na=False), digest
    except (OSError, pd.errors.ParserError) as error:
        raise EvaluationError(f"Cannot read {artifact_name} CSV.") from error


def _snapshot_identity(manifest: Mapping[str, Any]) -> str:
    persisted = manifest.get("snapshot_identity_sha256")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise EvaluationError("Prediction manifest has no artifact identity.")
    artifact_hashes: dict[str, str] = {}
    for name, entry in sorted(artifacts.items()):
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            raise EvaluationError("Prediction artifact identity is incomplete.")
        artifact_hashes[str(name)] = str(entry["sha256"])
    computed = sha256(canonical_json_bytes({
        "stage": manifest.get("stage"),
        "stage_version": manifest.get("stage_version"),
        "extraction_config_id": manifest.get("extraction_config_id"),
        "document_identity_sha256": manifest.get("document_identity_sha256"),
        "artifact_sha256": artifact_hashes,
    })).hexdigest()
    if persisted is not None:
        if not isinstance(persisted, str) or not _SHA_RE.fullmatch(persisted):
            raise EvaluationError("Prediction snapshot identity is malformed.")
        if persisted != computed:
            raise EvaluationError("Persisted prediction snapshot identity mismatch.")
    return computed


def load_prediction_snapshot(snapshot_dir: Path) -> PredictionSnapshot:
    snapshot_dir = Path(snapshot_dir).absolute()
    manifest = _load_json(snapshot_dir / "manifest.json", label="prediction manifest")
    expected_metadata = {
        "stage": "extraction",
        "stage_version": "1",
        "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
        "model_provider": FROZEN_MODEL_PROVIDER,
        "model_name": FROZEN_MODEL_NAME,
        "instructions_sha256": FROZEN_INSTRUCTIONS_SHA256,
        "contract_schema_sha256": FROZEN_CONTRACT_SHA256,
        "document_validation_version": "25",
    }
    for key, expected in expected_metadata.items():
        if manifest.get(key) != expected:
            raise EvaluationError(
                f"Prediction manifest {key} is incompatible: "
                f"expected={expected!r}; found={manifest.get(key)!r}."
            )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not REQUIRED_SNAPSHOT_ARTIFACTS.issubset(
        artifacts
    ):
        raise EvaluationError("Prediction snapshot misses required artifacts.")

    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for artifact_name in REQUIRED_SNAPSHOT_ARTIFACTS:
        paths[artifact_name], hashes[artifact_name] = _artifact_path(
            snapshot_dir, manifest, artifact_name
        )
    corrections, corrections_hash = _read_optional_csv(
        snapshot_dir, manifest, "historical_antecedent_corrections"
    )
    reviews, reviews_hash = _read_optional_csv(
        snapshot_dir, manifest, "historical_antecedent_reviews"
    )
    if corrections_hash:
        hashes["historical_antecedent_corrections"] = corrections_hash
    if reviews_hash:
        hashes["historical_antecedent_reviews"] = reviews_hash
    safeguard = manifest.get(HISTORICAL_ANTECEDENT_REASON_CODE)
    if not isinstance(safeguard, dict):
        raise EvaluationError("Prediction manifest misses the P0 safeguard declaration.")
    expected_safeguard = {
        "policy_version": HISTORICAL_ANTECEDENT_POLICY_VERSION,
        "reason_code": HISTORICAL_ANTECEDENT_REASON_CODE,
        "corrections_file_sha256": hashes["historical_antecedent_corrections"],
        "reviews_file_sha256": hashes["historical_antecedent_reviews"],
    }
    for key, expected in expected_safeguard.items():
        if safeguard.get(key) != expected:
            raise EvaluationError(
                f"Prediction P0 safeguard {key} is incompatible."
            )
    return PredictionSnapshot(
        path=snapshot_dir,
        manifest=manifest,
        snapshot_identity=_snapshot_identity(manifest),
        documents=_read_parquet(paths["documents"], label="documents"),
        attempts=_read_parquet(paths["attempts"], label="attempts"),
        manual_reviews=_read_parquet(paths["manual_reviews"], label="manual reviews"),
        current_extractions=_read_parquet(
            paths["current_extractions"], label="current extractions"
        ),
        review_queue=_read_parquet(paths["review_queue"], label="review queue"),
        historical_corrections=corrections,
        historical_reviews=reviews,
        artifact_hashes=hashes,
    )


def validate_execution_record(
    path: Path,
    *,
    snapshot_identity: str | None = None,
    truth: TruthArtifact | None = None,
) -> Mapping[str, Any]:
    record = _load_json(Path(path), label="execution record")
    required = {
        "record_version",
        "run_id",
        "started_at_utc",
        "ended_at_utc",
        "exact_command",
        "exit_code",
        "frozen_production_git_commit",
        "extraction_config_id",
        "model_provider",
        "model_name",
        "source_snapshot_identity",
        "holdout_artifact_identity",
        "extraction_output_identity",
        "stdout_log_path",
        "stderr_log_path",
        "python_version",
        "uv_lock_sha256",
        "model_usage",
        "incident_retry_notes",
        "manual_intervention_before_primary_freeze",
        "primary_predictions_frozen_at_utc",
    }
    if set(record) != required:
        raise EvaluationError(
            f"Execution record fields mismatch: missing={sorted(required - set(record))}; "
            f"extra={sorted(set(record) - required)}."
        )
    expected = {
        "record_version": EXECUTION_RECORD_VERSION,
        "frozen_production_git_commit": FROZEN_PRODUCTION_COMMIT,
        "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
        "model_provider": FROZEN_MODEL_PROVIDER,
        "model_name": FROZEN_MODEL_NAME,
        "source_snapshot_identity": FROZEN_SOURCE_SNAPSHOT_ID,
        "uv_lock_sha256": FROZEN_UV_LOCK_SHA256,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise EvaluationError(f"Execution record {key} is incompatible.")
    if record["manual_intervention_before_primary_freeze"] is not False:
        raise EvaluationError("Primary execution record declares human intervention.")
    if (
        not isinstance(record["exact_command"], list)
        or not record["exact_command"]
        or any(
            not isinstance(value, str) or not value
            for value in record["exact_command"]
        )
    ):
        raise EvaluationError("exact_command must be a non-empty argv JSON array.")
    if not isinstance(record["exit_code"], int) or isinstance(record["exit_code"], bool):
        raise EvaluationError("exit_code must be an integer.")
    for key in (
        "holdout_artifact_identity",
        "extraction_output_identity",
    ):
        if not isinstance(record[key], str) or not _SHA_RE.fullmatch(record[key]):
            raise EvaluationError(f"Execution record {key} must be SHA-256.")
    for key in (
        "run_id",
        "stdout_log_path",
        "stderr_log_path",
        "python_version",
        "incident_retry_notes",
    ):
        if not isinstance(record[key], str) or not record[key].strip():
            raise EvaluationError(f"Execution record {key} must be non-empty text.")
    timestamps: dict[str, pd.Timestamp] = {}
    for key in ("started_at_utc", "ended_at_utc", "primary_predictions_frozen_at_utc"):
        value = str(record[key])
        try:
            parsed = pd.Timestamp(value)
        except ValueError as error:
            raise EvaluationError(f"Execution record {key} is not a timestamp.") from error
        if parsed.tzinfo is None:
            raise EvaluationError(f"Execution record {key} must include a timezone.")
        if parsed.utcoffset() != timedelta(0):
            raise EvaluationError(f"Execution record {key} must be UTC.")
        timestamps[key] = parsed
    if not (
        timestamps["started_at_utc"]
        <= timestamps["ended_at_utc"]
        <= timestamps["primary_predictions_frozen_at_utc"]
    ):
        raise EvaluationError("Execution record timestamps are out of order.")
    usage = record["model_usage"]
    if not isinstance(usage, dict) or set(usage) != {
        "requests",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }:
        raise EvaluationError("Execution record model_usage contract mismatch.")
    if any(not isinstance(value, int) or value < 0 for value in usage.values()):
        raise EvaluationError("Execution record model usage must be non-negative integers.")
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise EvaluationError("Execution record total_tokens is inconsistent.")
    if snapshot_identity is not None and record["extraction_output_identity"] != snapshot_identity:
        raise EvaluationError("Execution record does not identify the prediction snapshot.")
    if truth is not None:
        if record["holdout_artifact_identity"] != truth.holdout_artifact_identity:
            raise EvaluationError("Execution and truth use different holdout artifacts.")
        if record["source_snapshot_identity"] != truth.source_snapshot_identity:
            raise EvaluationError("Execution and truth use different source snapshots.")
    return record


def _truth_ids(truth: TruthArtifact) -> set[str]:
    return set(truth.tables["documents"]["identificador_boe"].astype(str))


def _validate_primary_predictions(
    snapshot: PredictionSnapshot,
    truth: TruthArtifact,
) -> None:
    truth_documents = truth.tables["documents"]
    truth_ids = _truth_ids(truth)
    required_document_columns = {
        "identificador",
        "source_document_sha256",
        "texto_limpio",
        "titulo",
    }
    if not required_document_columns.issubset(snapshot.documents.columns):
        raise EvaluationError("Prediction documents miss required source columns.")
    document_ids = set(snapshot.documents["identificador"].astype(str))
    if document_ids != truth_ids or snapshot.documents["identificador"].duplicated().any():
        raise EvaluationError("Prediction document universe differs from frozen truth.")
    truth_hashes = dict(zip(
        truth_documents["identificador_boe"].astype(str),
        truth_documents["source_document_sha256"].astype(str),
        strict=True,
    ))
    for _, row in snapshot.documents.iterrows():
        boe_id = str(row["identificador"])
        if str(row["source_document_sha256"]) != truth_hashes[boe_id]:
            raise EvaluationError(f"Prediction source hash drift for {boe_id}.")

    required_attempt_columns = {
        "attempt_id",
        "identificador_boe",
        "source_document_sha256",
        "attempt_origin",
        "source_attempt_id",
        "extraction_config_id",
        "model_provider",
        "model_name",
        "extraction_status",
        "extraction_json",
    }
    if not required_attempt_columns.issubset(snapshot.attempts.columns):
        raise EvaluationError("Prediction attempts miss primary-lineage columns.")
    attempts = snapshot.attempts.loc[
        snapshot.attempts["identificador_boe"].astype(str).isin(truth_ids)
    ]
    if (
        set(snapshot.attempts["identificador_boe"].astype(str)) != truth_ids
        or len(snapshot.attempts) != len(truth_ids)
        or len(attempts) != len(truth_ids)
        or attempts["identificador_boe"].astype(str).duplicated().any()
        or set(attempts["identificador_boe"].astype(str)) != truth_ids
    ):
        raise EvaluationError("Primary predictions require exactly one attempt per document.")
    allowed_origins = {"model", "deterministic"}
    if not attempts["attempt_origin"].astype(str).isin(allowed_origins).all():
        raise EvaluationError(
            "Primary holdout attempts must be fresh model or deterministic attempts."
        )
    attempt_hashes = dict(zip(
        attempts["identificador_boe"].astype(str),
        attempts["source_document_sha256"].astype(str),
        strict=True,
    ))
    if attempt_hashes != truth_hashes:
        raise EvaluationError("Primary attempt source hashes differ from blind truth.")
    inherited = attempts["source_attempt_id"].notna() & attempts[
        "source_attempt_id"
    ].astype(str).str.strip().ne("")
    if inherited.any():
        raise EvaluationError("Primary holdout attempts cannot inherit prior attempts.")
    for column, expected in (
        ("extraction_config_id", FROZEN_EXTRACTION_CONFIG_ID),
        ("model_provider", FROZEN_MODEL_PROVIDER),
        ("model_name", FROZEN_MODEL_NAME),
    ):
        if not attempts[column].astype(str).eq(expected).all():
            raise EvaluationError(f"Primary attempt lineage mismatch: {column}.")

    required_current_columns = {
        "attempt_id",
        "identificador_boe",
        "source_document_sha256",
        "extraction_status",
        "extraction_json",
    }
    if not required_current_columns.issubset(snapshot.current_extractions.columns):
        raise EvaluationError("Current extractions miss primary-selection columns.")
    current = snapshot.current_extractions
    if (
        current["identificador_boe"].astype(str).duplicated().any()
        or not current["identificador_boe"].astype(str).isin(truth_ids).all()
        or not current["extraction_status"].astype(str).eq("ok").all()
    ):
        raise EvaluationError("Current extractions are not a unique valid holdout selection.")
    successful = attempts.loc[attempts["extraction_status"].astype(str).eq("ok")]
    if set(current["attempt_id"].astype(str)) != set(successful["attempt_id"].astype(str)):
        raise EvaluationError("Current extractions differ from the primary successful attempts.")
    attempt_payloads = {
        str(row["attempt_id"]): str(row["extraction_json"])
        for _, row in successful.iterrows()
    }
    if any(
        str(row["extraction_json"]) != attempt_payloads[str(row["attempt_id"])]
        for _, row in current.iterrows()
    ):
        raise EvaluationError("Current extraction payload drift detected.")
    attempt_rows = {
        str(row["attempt_id"]): row for _, row in successful.iterrows()
    }
    if any(
        str(row["identificador_boe"])
        != str(attempt_rows[str(row["attempt_id"])]["identificador_boe"])
        or str(row.get("source_document_sha256"))
        != str(attempt_rows[str(row["attempt_id"])]["source_document_sha256"])
        for _, row in current.iterrows()
    ):
        raise EvaluationError("Current extraction lineage differs from its attempt.")

    if not snapshot.manual_reviews.empty:
        manual_ids = set(snapshot.manual_reviews["identificador_boe"].astype(str))
        if manual_ids & truth_ids:
            raise EvaluationError("Primary predictions contain holdout manual reviews.")
    for label, frame in (
        ("historical corrections", snapshot.historical_corrections),
        ("historical CURRENT reviews", snapshot.historical_reviews),
    ):
        if frame.empty:
            continue
        if "boe_id" not in frame.columns:
            raise EvaluationError(f"Snapshot {label} miss boe_id.")
        if set(frame["boe_id"].astype(str)) & truth_ids:
            raise EvaluationError(f"Primary predictions contain holdout-specific {label}.")
    if not snapshot.review_queue.empty:
        if "identificador_boe" not in snapshot.review_queue.columns:
            raise EvaluationError("Review queue misses document identity.")
        if not snapshot.review_queue["identificador_boe"].astype(str).isin(
            truth_ids
        ).all():
            raise EvaluationError("Review queue contains documents outside the holdout.")


def _global(boe_id: str, local_key: str) -> str:
    return f"{boe_id}|{local_key}"


def _truth_row_maps(truth: TruthArtifact) -> dict[str, dict[str, pd.Series]]:
    key_by_table = {
        "events": "event_key",
        "generation_assets": "asset_key",
        "associated_components": "component_key",
        "technical_mentions": "technical_key",
        "administrative_actions": "action_key",
        "participants": "participant_key",
        "locations": "location_key",
    }
    return {
        table: {
            _global(str(row["identificador_boe"]), str(row[key_column])): row
            for _, row in truth.tables[table].iterrows()
        }
        for table, key_column in key_by_table.items()
    }


def _truth_passages(
    truth: TruthArtifact,
    *,
    scored_only: bool,
) -> dict[tuple[str, str], list[str]]:
    passages: dict[tuple[str, str], list[str]] = defaultdict(list)
    for _, row in truth.tables["evidence_passages"].iterrows():
        if scored_only and not (
            row["applicability"] == "applicable"
            and row["adjudication"] == "scored_truth"
        ):
            continue
        passages[(
            _global(str(row["identificador_boe"]), str(row["owner_key"])),
            str(row["owner_type"]),
        )].append(str(row["passage_text"]))
    return passages


def _validate_truth_evidence_against_source(
    truth: TruthArtifact,
    snapshot: PredictionSnapshot,
) -> None:
    source_by_id = {
        str(row["identificador"]): f"{row['titulo']}\n{row['texto_limpio']}"
        for _, row in snapshot.documents.iterrows()
    }
    for _, row in truth.tables["evidence_passages"].iterrows():
        if row["adjudication"] != "scored_truth":
            continue
        source = normalize_evidence(source_by_id[str(row["identificador_boe"])])
        passage = normalize_evidence(str(row["passage_text"]))
        if passage not in source:
            raise EvaluationError(
                "A scored truth evidence passage is not a literal source passage."
            )


def _flatten_predictions(snapshot: PredictionSnapshot) -> dict[str, dict[str, dict[str, Any]]]:
    flattened: dict[str, dict[str, dict[str, Any]]] = {
        entity_type: {}
        for entity_type in (
            "events",
            "generation_assets",
            "associated_components",
            "technical_mentions",
            "administrative_actions",
            "participants",
            "locations",
        )
    }
    attempts = snapshot.attempts.sort_values("identificador_boe", kind="stable")
    for _, attempt in attempts.iterrows():
        boe_id = str(attempt["identificador_boe"])
        if str(attempt["extraction_status"]) != "ok":
            continue
        raw = attempt["extraction_json"]
        if raw is None or pd.isna(raw):
            raise EvaluationError("A successful attempt has no extraction JSON.")
        try:
            extraction = json.loads(str(raw))
        except json.JSONDecodeError as error:
            raise EvaluationError("A successful attempt has invalid extraction JSON.") from error
        events = extraction.get("publication_events")
        if not isinstance(events, list):
            raise EvaluationError("Prediction extraction has no event list.")
        for event_index, event in enumerate(events, start=1):
            event_local = f"pred_event_{event_index}"
            event_global = _global(boe_id, event_local)
            flattened["events"][event_global] = {
                "boe_id": boe_id,
                "local_key": event_local,
                "event_global": event_global,
                "value": event,
            }
            for asset in event.get("generation_assets", []):
                local_ref = str(asset["local_generation_asset_ref"])
                key = _global(boe_id, f"{event_local}:{local_ref}")
                flattened["generation_assets"][key] = {
                    "boe_id": boe_id,
                    "local_key": key.split("|", 1)[1],
                    "event_global": event_global,
                    "names": list(asset.get("names_raw", [])),
                    "generation_type": asset.get("generation_type"),
                    "evidence": asset.get("evidence", ""),
                    "local_ref": local_ref,
                    "value": asset,
                }
                for technical_index, mention in enumerate(
                    asset.get("technical_mentions", []), start=1
                ):
                    technical_key = _global(
                        boe_id, f"{event_local}:{local_ref}:technical_{technical_index}"
                    )
                    flattened["technical_mentions"][technical_key] = {
                        "boe_id": boe_id,
                        "local_key": technical_key.split("|", 1)[1],
                        "event_global": event_global,
                        "owner_predicted_key": key,
                        "owner_type": "generation_asset",
                        "attribute_type": mention.get("attribute_type"),
                        "value_raw": mention.get("value_raw"),
                        "evidence": mention.get("evidence", ""),
                    }
            for component in event.get("associated_components", []):
                local_ref = str(component["local_component_ref"])
                key = _global(boe_id, f"{event_local}:{local_ref}")
                flattened["associated_components"][key] = {
                    "boe_id": boe_id,
                    "local_key": key.split("|", 1)[1],
                    "event_global": event_global,
                    "names": list(component.get("names_raw", [])),
                    "description_raw": component.get("description_raw"),
                    "component_type": component.get("component_type"),
                    "related_generation_asset_refs": list(
                        component.get("related_generation_asset_refs", [])
                    ),
                    "evidence": component.get("evidence", ""),
                    "local_ref": local_ref,
                    "value": component,
                }
                for technical_index, mention in enumerate(
                    component.get("technical_mentions", []), start=1
                ):
                    technical_key = _global(
                        boe_id, f"{event_local}:{local_ref}:technical_{technical_index}"
                    )
                    flattened["technical_mentions"][technical_key] = {
                        "boe_id": boe_id,
                        "local_key": technical_key.split("|", 1)[1],
                        "event_global": event_global,
                        "owner_predicted_key": key,
                        "owner_type": "associated_component",
                        "attribute_type": mention.get("attribute_type"),
                        "value_raw": mention.get("value_raw"),
                        "evidence": mention.get("evidence", ""),
                    }
            for action_index, action in enumerate(
                event.get("administrative_actions", []), start=1
            ):
                local_key = f"{event_local}:action_{action_index}"
                key = _global(boe_id, local_key)
                flattened["administrative_actions"][key] = {
                    "boe_id": boe_id,
                    "local_key": local_key,
                    "event_global": event_global,
                    "action_type": action.get("action_type"),
                    "decision": action.get("decision"),
                    "is_modification": action.get("is_modification", False),
                    "targets": list(action.get("targets", [])),
                    "evidence": action.get("evidence", ""),
                    "event_index": event_index,
                    "action_index": action_index,
                }
            for participant_index, participant in enumerate(
                event.get("participants", []), start=1
            ):
                local_key = f"{event_local}:participant_{participant_index}"
                key = _global(boe_id, local_key)
                flattened["participants"][key] = {
                    "boe_id": boe_id,
                    "local_key": local_key,
                    "event_global": event_global,
                    "names": [participant.get("participant_name_raw", "")],
                    "participant_role": participant.get("participant_role"),
                    "evidence": participant.get("evidence", ""),
                }
            for location_index, location in enumerate(
                event.get("administrative_locations", []), start=1
            ):
                local_key = f"{event_local}:location_{location_index}"
                key = _global(boe_id, local_key)
                flattened["locations"][key] = {
                    "boe_id": boe_id,
                    "local_key": local_key,
                    "event_global": event_global,
                    "names": [location.get("location_name_raw", "")],
                    "location_level": location.get("location_level"),
                    "province_hint_raw": location.get("province_hint_raw"),
                    "autonomous_community_hint_raw": location.get(
                        "autonomous_community_hint_raw"
                    ),
                    "evidence": location.get("evidence", ""),
                }
    return flattened


def _scored(row: pd.Series) -> bool:
    return row["applicability"] == "applicable" and row["adjudication"] == "scored_truth"


def _match_record_rows(
    *,
    boe_id: str,
    entity_type: str,
    result: MatchResult,
    truth_rows: Mapping[str, pd.Series],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    unmatched_truth: list[dict[str, Any]] = []
    unmatched_predicted: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for truth_key, predicted_key in result.matches:
        scored = _scored(truth_rows[truth_key])
        matches.append({
            "identificador_boe": boe_id,
            "entity_type": entity_type,
            "truth_key": truth_key,
            "predicted_key": predicted_key,
            "match_status": "matched" if scored else "excluded_truth_match",
            "scored": scored,
        })
    for truth_key in result.unmatched_truth:
        unmatched_truth.append({
            "identificador_boe": boe_id,
            "entity_type": entity_type,
            "truth_key": truth_key,
            "reason": "no_candidate",
        })
    for truth_key in result.ambiguous_truth:
        unmatched_truth.append({
            "identificador_boe": boe_id,
            "entity_type": entity_type,
            "truth_key": truth_key,
            "reason": "ambiguous_matching",
        })
    for predicted_key in result.unmatched_predicted:
        unmatched_predicted.append({
            "identificador_boe": boe_id,
            "entity_type": entity_type,
            "predicted_key": predicted_key,
            "reason": "no_candidate",
        })
    for predicted_key in result.ambiguous_predicted:
        unmatched_predicted.append({
            "identificador_boe": boe_id,
            "entity_type": entity_type,
            "predicted_key": predicted_key,
            "reason": "ambiguous_matching",
        })
    for truth_key in result.excluded_truth:
        if truth_key not in {truth for truth, _ in result.matches}:
            unmatched_truth.append({
                "identificador_boe": boe_id,
                "entity_type": entity_type,
                "truth_key": truth_key,
                "reason": "excluded_from_scoring",
            })
    for predicted_key in result.excluded_predicted:
        unmatched_predicted.append({
            "identificador_boe": boe_id,
            "entity_type": entity_type,
            "predicted_key": predicted_key,
            "reason": "excluded_from_scoring",
        })
    if result.ambiguous_truth or result.ambiguous_predicted:
        issues.append({
            "identificador_boe": boe_id,
            "issue_type": "ambiguous_many_to_many_match",
            "entity_type": entity_type,
            "truth_keys_json": json.dumps(list(result.ambiguous_truth), sort_keys=True),
            "predicted_keys_json": json.dumps(
                list(result.ambiguous_predicted), sort_keys=True
            ),
        })
    return matches, unmatched_truth, unmatched_predicted, issues


def _candidate_by_event_and_names(
    truth_rows: Mapping[str, pd.Series],
    predicted_rows: Mapping[str, Mapping[str, Any]],
    event_pred_to_truth: Mapping[str, str],
    *,
    truth_name_column: str,
    prediction_name_field: str = "names",
) -> set[tuple[str, str]]:
    truth_names: dict[str, Sequence[str]] = {}
    for key, row in truth_rows.items():
        value = str(row[truth_name_column])
        truth_names[key] = (
            parse_json_list(value, label=truth_name_column)
            if truth_name_column.endswith("_json")
            else [value]
        )
    predicted_names = {
        key: list(row[prediction_name_field]) for key, row in predicted_rows.items()
    }
    name_pairs = name_candidate_pairs(truth_names, predicted_names)
    return {
        (truth_key, predicted_key)
        for truth_key, predicted_key in name_pairs
        if event_pred_to_truth.get(str(predicted_rows[predicted_key]["event_global"]))
        == _global(
            str(truth_rows[truth_key]["identificador_boe"]),
            str(truth_rows[truth_key]["event_key"]),
        )
    }


def _p0_warning_keys(snapshot: PredictionSnapshot) -> tuple[set[str], int]:
    warnings: set[str] = set()
    unresolved = 0
    if snapshot.review_queue.empty:
        return warnings, unresolved
    required = {"identificador_boe", "reason_code", "validation_issues_json"}
    if not required.issubset(snapshot.review_queue.columns):
        raise EvaluationError("Review queue misses P0 diagnostic columns.")
    queue = snapshot.review_queue.loc[
        snapshot.review_queue["reason_code"].astype(str).eq(
            "possible_historical_antecedent"
        )
    ]
    for _, row in queue.iterrows():
        raw = row["validation_issues_json"]
        try:
            findings = json.loads(str(raw))
        except json.JSONDecodeError as error:
            raise EvaluationError("P0 review finding JSON is invalid.") from error
        if not isinstance(findings, list):
            raise EvaluationError("P0 review findings must be a JSON array.")
        for finding in findings:
            action_id = finding.get("administrative_action_id") if isinstance(finding, dict) else None
            match = _P0_ACTION_RE.search(str(action_id))
            if not match:
                unresolved += 1
                continue
            local = f"pred_event_{int(match.group(1))}:action_{int(match.group(2))}"
            warnings.add(_global(str(row["identificador_boe"]), local))
    return warnings, unresolved


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _semantic_frame_hash(frame: pd.DataFrame, sort_columns: Sequence[str]) -> str:
    if frame.empty:
        rows: list[dict[str, Any]] = []
    else:
        ordered = frame.sort_values(list(sort_columns), kind="stable")
        rows = [
            {
                column: None if pd.isna(value) else value
                for column, value in row.items()
            }
            for row in ordered.to_dict(orient="records")
        ]
    return sha256(canonical_json_bytes(rows)).hexdigest()


def _field_result(
    *,
    boe_id: str,
    entity_type: str,
    truth_key: str,
    predicted_key: str,
    field_name: str,
    expected: Any,
    predicted: Any,
    applicable: bool = True,
) -> dict[str, Any]:
    predicted_present = predicted is not None and not (
        isinstance(predicted, str) and not predicted.strip()
    )
    if predicted_present:
        try:
            missing = pd.isna(predicted)
        except (TypeError, ValueError):
            missing = False
        if isinstance(missing, bool) and missing:
            predicted_present = False
    serializable_prediction = predicted if predicted_present else None
    correct = bool(applicable and expected == serializable_prediction)
    return {
        "identificador_boe": boe_id,
        "entity_type": entity_type,
        "truth_key": truth_key,
        "predicted_key": predicted_key,
        "field_name": field_name,
        "expected_value_json": json.dumps(expected, ensure_ascii=False, sort_keys=True),
        "predicted_value_json": json.dumps(
            serializable_prediction, ensure_ascii=False, sort_keys=True
        ),
        "applicable": applicable,
        "predicted_present": predicted_present if applicable else pd.NA,
        "correct": correct if applicable else pd.NA,
    }


def _evaluate_frames(
    truth: TruthArtifact,
    snapshot: PredictionSnapshot,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    truth_maps = _truth_row_maps(truth)
    passages = _truth_passages(truth, scored_only=True)
    candidate_passages = _truth_passages(truth, scored_only=False)
    predicted = _flatten_predictions(snapshot)
    truth_documents = truth.tables["documents"]
    truth_ids = sorted(_truth_ids(truth))
    scored_document_ids = set(
        truth_documents.loc[
            truth_documents["scope_adjudication"].eq("scored_truth"),
            "identificador_boe",
        ].astype(str)
    )
    attempts_by_id = {
        str(row["identificador_boe"]): row for _, row in snapshot.attempts.iterrows()
    }
    queue_by_id: dict[str, list[str]] = defaultdict(list)
    if not snapshot.review_queue.empty:
        for _, row in snapshot.review_queue.iterrows():
            queue_by_id[str(row["identificador_boe"])].append(str(row["reason_code"]))
    p0_warnings, unresolved_p0_warning_ids = _p0_warning_keys(snapshot)

    match_rows: list[dict[str, Any]] = []
    unmatched_expected_rows: list[dict[str, Any]] = []
    unmatched_predicted_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    p0_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []
    match_maps: dict[str, dict[str, str]] = {
        entity_type: {}
        for entity_type in (
            "event",
            "generation_asset",
            "associated_component",
            "technical_mention",
            "administrative_action",
            "participant",
            "location",
        )
    }

    table_entity = {
        "events": "event",
        "generation_assets": "generation_asset",
        "associated_components": "associated_component",
        "technical_mentions": "technical_mention",
        "administrative_actions": "administrative_action",
        "participants": "participant",
        "locations": "location",
    }
    detection_counts = {
        entity_type: {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "excluded_truth": 0,
            "excluded_predicted": 0,
            "matching_ambiguities": 0,
        }
        for entity_type in (*PRIMARY_ENTITY_TYPES, *SECONDARY_ENTITY_TYPES)
    }
    per_doc_errors: dict[str, bool] = {boe_id: False for boe_id in truth_ids}
    per_doc_uncertain: dict[str, bool] = {boe_id: False for boe_id in truth_ids}

    document_scope_scored = 0
    document_scope_correct = 0
    for _, truth_document in truth_documents.iterrows():
        boe_id = str(truth_document["identificador_boe"])
        attempt = attempts_by_id[boe_id]
        predicted_scope = (
            None
            if str(attempt["extraction_status"]) != "ok"
            or pd.isna(attempt.get("document_scope"))
            else str(attempt["document_scope"])
        )
        scope_scored = truth_document["scope_adjudication"] == "scored_truth"
        scope_correct = bool(
            scope_scored
            and predicted_scope == str(truth_document["expected_document_scope"])
        )
        if scope_scored:
            document_scope_scored += 1
            document_scope_correct += int(scope_correct)
            per_doc_errors[boe_id] |= not scope_correct
        else:
            per_doc_uncertain[boe_id] = True
        document_rows.append({
            "identificador_boe": boe_id,
            "source_document_sha256": str(truth_document["source_document_sha256"]),
            "extraction_status": str(attempt["extraction_status"]),
            "expected_document_scope": str(truth_document["expected_document_scope"]),
            "predicted_document_scope": predicted_scope,
            "document_scope_scored": scope_scored,
            "document_scope_correct": scope_correct if scope_scored else pd.NA,
            "review_reason_codes_json": json.dumps(sorted(queue_by_id.get(boe_id, []))),
        })

    def record_result(
        boe_id: str,
        table: str,
        result: MatchResult,
    ) -> None:
        entity_type = table_entity[table]
        matches, unmatched_truth, unmatched_predicted, issues = _match_record_rows(
            boe_id=boe_id,
            entity_type=entity_type,
            result=result,
            truth_rows=truth_maps[table],
        )
        match_rows.extend(matches)
        unmatched_expected_rows.extend(unmatched_truth)
        unmatched_predicted_rows.extend(unmatched_predicted)
        issue_rows.extend(issues)
        for truth_key, predicted_key in result.matches:
            if _scored(truth_maps[table][truth_key]):
                detection_counts[entity_type]["tp"] += 1
                match_maps[entity_type][predicted_key] = truth_key
        detection_counts[entity_type]["fn"] += len(result.unmatched_truth) + len(
            result.ambiguous_truth
        )
        detection_counts[entity_type]["fp"] += len(result.unmatched_predicted) + len(
            result.ambiguous_predicted
        )
        detection_counts[entity_type]["excluded_truth"] += len(result.excluded_truth)
        detection_counts[entity_type]["excluded_predicted"] += len(
            result.excluded_predicted
        )
        detection_counts[entity_type]["matching_ambiguities"] += len(
            result.ambiguous_truth
        )
        if entity_type in PRIMARY_ENTITY_TYPES:
            per_doc_errors[boe_id] |= bool(
                result.unmatched_truth
                or result.unmatched_predicted
                or result.ambiguous_truth
                or result.ambiguous_predicted
            )
        if entity_type in PRIMARY_ENTITY_TYPES:
            per_doc_uncertain[boe_id] |= bool(
                result.excluded_truth or result.excluded_predicted
            )

    def resolve_result(
        *,
        boe_id: str,
        truth_rows: Mapping[str, pd.Series],
        pred_rows: Mapping[str, Mapping[str, Any]],
        pairs: Iterable[tuple[str, str]],
        excluded: set[str],
    ) -> MatchResult:
        if boe_id not in scored_document_ids:
            return MatchResult(
                matches=(),
                unmatched_truth=(),
                unmatched_predicted=(),
                ambiguous_truth=(),
                ambiguous_predicted=(),
                excluded_truth=tuple(sorted(truth_rows)),
                excluded_predicted=tuple(sorted(pred_rows)),
            )
        return deterministic_match(
            truth_keys=truth_rows,
            predicted_keys=pred_rows,
            candidate_pairs=pairs,
            excluded_truth_keys=excluded,
        )

    # Assets are matched first across each document using exact normalized aliases.
    for boe_id in truth_ids:
        truth_rows = {
            key: row
            for key, row in truth_maps["generation_assets"].items()
            if key.startswith(f"{boe_id}|")
        }
        pred_rows = {
            key: row
            for key, row in predicted["generation_assets"].items()
            if row["boe_id"] == boe_id
        }
        pairs = name_candidate_pairs(
            {
                key: parse_json_list(str(row["names_json"]), label="names_json")
                for key, row in truth_rows.items()
            },
            {key: row["names"] for key, row in pred_rows.items()},
        )
        excluded = {key for key, row in truth_rows.items() if not _scored(row)}
        result = resolve_result(
            boe_id=boe_id,
            truth_rows=truth_rows,
            pred_rows=pred_rows,
            pairs=pairs,
            excluded=excluded,
        )
        record_result(boe_id, "generation_assets", result)

    # Events require equality of non-empty matched generation-asset sets.
    for boe_id in truth_ids:
        truth_rows = {
            key: row for key, row in truth_maps["events"].items() if key.startswith(f"{boe_id}|")
        }
        pred_rows = {
            key: row for key, row in predicted["events"].items() if row["boe_id"] == boe_id
        }
        truth_assets_by_event: dict[str, set[str]] = defaultdict(set)
        for asset_key, asset_row in truth_maps["generation_assets"].items():
            if asset_key.startswith(f"{boe_id}|"):
                truth_assets_by_event[_global(boe_id, str(asset_row["event_key"]))].add(asset_key)
        predicted_assets_by_event: dict[str, set[str]] = defaultdict(set)
        for predicted_key, asset in predicted["generation_assets"].items():
            if asset["boe_id"] == boe_id and predicted_key in match_maps["generation_asset"]:
                predicted_assets_by_event[str(asset["event_global"])].add(
                    match_maps["generation_asset"][predicted_key]
                )
        pairs = {
            (truth_key, predicted_key)
            for truth_key in truth_rows
            for predicted_key in pred_rows
            if truth_assets_by_event[truth_key]
            and truth_assets_by_event[truth_key] == predicted_assets_by_event[predicted_key]
        }
        excluded = {key for key, row in truth_rows.items() if not _scored(row)}
        result = resolve_result(
            boe_id=boe_id,
            truth_rows=truth_rows,
            pred_rows=pred_rows,
            pairs=pairs,
            excluded=excluded,
        )
        record_result(boe_id, "events", result)

    event_pred_to_truth = match_maps["event"]

    # Components, participants and raw locations use aliases within matched events.
    for table, prediction_table, truth_name_column in (
        ("associated_components", "associated_components", "names_json"),
        ("participants", "participants", "participant_name_raw"),
        ("locations", "locations", "location_name_raw"),
    ):
        for boe_id in truth_ids:
            truth_rows = {
                key: row for key, row in truth_maps[table].items() if key.startswith(f"{boe_id}|")
            }
            pred_rows = {
                key: row
                for key, row in predicted[prediction_table].items()
                if row["boe_id"] == boe_id
            }
            pairs = _candidate_by_event_and_names(
                truth_rows,
                pred_rows,
                event_pred_to_truth,
                truth_name_column=truth_name_column,
            )
            if table == "associated_components":
                # Unnamed components may match by exact normalized description.
                pairs.update({
                    (truth_key, predicted_key)
                    for truth_key, truth_row in truth_rows.items()
                    for predicted_key, pred_row in pred_rows.items()
                    if event_pred_to_truth.get(str(pred_row["event_global"]))
                    == _global(boe_id, str(truth_row["event_key"]))
                    and str(truth_row["description_raw"]) != NA
                    and pred_row.get("description_raw") is not None
                    and normalize_name(str(truth_row["description_raw"]))
                    == normalize_name(str(pred_row["description_raw"]))
                })
            excluded = {key for key, row in truth_rows.items() if not _scored(row)}
            result = resolve_result(
                boe_id=boe_id,
                truth_rows=truth_rows,
                pred_rows=pred_rows,
                pairs=pairs,
                excluded=excluded,
            )
            record_result(boe_id, table, result)

    # Actions and technical mentions are source-anchored by entity-specific evidence.
    for table, prediction_table, owner_type in (
        ("administrative_actions", "administrative_actions", "administrative_action"),
        ("technical_mentions", "technical_mentions", "technical_mention"),
    ):
        for boe_id in truth_ids:
            truth_rows = {
                key: row for key, row in truth_maps[table].items() if key.startswith(f"{boe_id}|")
            }
            pred_rows = {
                key: row
                for key, row in predicted[prediction_table].items()
                if row["boe_id"] == boe_id
            }
            pairs: set[tuple[str, str]] = set()
            for truth_key, truth_row in truth_rows.items():
                truth_event = _global(boe_id, str(truth_row["event_key"]))
                accepted = (
                    passages if _scored(truth_row) else candidate_passages
                ).get((truth_key, owner_type), [])
                for predicted_key, pred_row in pred_rows.items():
                    if event_pred_to_truth.get(str(pred_row["event_global"])) != truth_event:
                        continue
                    if table == "technical_mentions":
                        owner_pred = str(pred_row["owner_predicted_key"])
                        owner_mapping = match_maps[
                            "generation_asset"
                            if pred_row["owner_type"] == "generation_asset"
                            else "associated_component"
                        ].get(owner_pred)
                        expected_owner = _global(boe_id, str(truth_row["owner_key"]))
                        if owner_mapping != expected_owner:
                            continue
                    if evidence_candidate(str(pred_row["evidence"]), accepted):
                        pairs.add((truth_key, predicted_key))
            excluded = {key for key, row in truth_rows.items() if not _scored(row)}
            result = resolve_result(
                boe_id=boe_id,
                truth_rows=truth_rows,
                pred_rows=pred_rows,
                pairs=pairs,
                excluded=excluded,
            )
            record_result(boe_id, table, result)

    # Field metrics for scored 1:1 matches.
    match_field_specs = {
        "generation_asset": (
            "generation_assets",
            "expected_generation_type",
            "generation_type",
        ),
        "associated_component": (
            "associated_components",
            "expected_component_type",
            "component_type",
        ),
        "participant": (
            "participants",
            "expected_participant_role",
            "participant_role",
        ),
        "location": (
            "locations",
            "expected_location_level",
            "location_level",
        ),
    }
    for entity_type, (table, expected_column, predicted_field) in match_field_specs.items():
        for predicted_key, truth_key in match_maps[entity_type].items():
            truth_row = truth_maps[table][truth_key]
            expected = str(truth_row[expected_column])
            predicted_value = predicted[table][predicted_key].get(predicted_field)
            applicable = expected != NA
            field_rows.append(_field_result(
                boe_id=str(truth_row["identificador_boe"]),
                entity_type=entity_type,
                truth_key=truth_key,
                predicted_key=predicted_key,
                field_name=expected_column.removeprefix("expected_"),
                expected=expected,
                predicted=predicted_value,
                applicable=applicable,
            ))
            if (
                entity_type in PRIMARY_ENTITY_TYPES
                and applicable
                and expected != predicted_value
            ):
                per_doc_errors[str(truth_row["identificador_boe"])] = True

    # Action fields, mapped targets and semantic evidence correctness.
    truth_targets: dict[str, set[tuple[str, str]]] = defaultdict(set)
    uncertain_target_actions: set[str] = set()
    for _, row in truth.tables["action_targets"].iterrows():
        action_key = _global(
            str(row["identificador_boe"]), str(row["action_key"])
        )
        if _scored(row):
            truth_targets[action_key].add(
                (str(row["target_type"]), _global(str(row["identificador_boe"]), str(row["target_truth_key"])))
            )
        else:
            uncertain_target_actions.add(action_key)
    for predicted_key, truth_key in match_maps["administrative_action"].items():
        truth_row = truth_maps["administrative_actions"][truth_key]
        pred_row = predicted["administrative_actions"][predicted_key]
        boe_id = str(truth_row["identificador_boe"])
        for field_name, expected_column, predicted_field in (
            ("action_type", "expected_action_type", "action_type"),
            ("decision", "expected_decision", "decision"),
            ("is_modification", "expected_is_modification", "is_modification"),
        ):
            expected: Any = str(truth_row[expected_column])
            predicted_value: Any = pred_row[predicted_field]
            if field_name == "is_modification" and expected != NA:
                expected = expected == "true"
            applicable = expected != NA
            field_rows.append(_field_result(
                boe_id=boe_id,
                entity_type="administrative_action",
                truth_key=truth_key,
                predicted_key=predicted_key,
                field_name=field_name,
                expected=expected,
                predicted=predicted_value,
                applicable=applicable,
            ))
            if applicable and expected != predicted_value:
                per_doc_errors[boe_id] = True

        predicted_targets: set[tuple[str, str]] = set()
        event_global = str(pred_row["event_global"])
        for target in pred_row["targets"]:
            if target == "event":
                mapped = match_maps["event"].get(event_global)
                predicted_targets.add(("event", mapped or "__UNMATCHED__"))
                continue
            prefix = "generation_asset" if str(target).startswith("generation_asset_") else "associated_component"
            predicted_owner = _global(
                boe_id,
                f"{pred_row['local_key'].split(':', 1)[0]}:{target}",
            )
            mapped = match_maps[prefix].get(predicted_owner)
            predicted_targets.add((prefix, mapped or "__UNMATCHED__"))
        expected_targets = truth_targets.get(truth_key, set())
        targets_applicable = truth_key not in uncertain_target_actions
        target_row = _field_result(
            boe_id=boe_id,
            entity_type="administrative_action",
            truth_key=truth_key,
            predicted_key=predicted_key,
            field_name="targets",
            expected=sorted(expected_targets),
            predicted=sorted(predicted_targets),
            applicable=targets_applicable,
        )
        field_rows.append(target_row)
        if targets_applicable:
            per_doc_errors[boe_id] |= not bool(target_row["correct"])
        else:
            per_doc_uncertain[boe_id] = True

        evidence_correct = evidence_is_correct(
            str(pred_row["evidence"]), passages.get((truth_key, "administrative_action"), [])
        )
        evidence_row = _field_result(
            boe_id=boe_id,
            entity_type="administrative_action",
            truth_key=truth_key,
            predicted_key=predicted_key,
            field_name="semantic_evidence",
            expected=True,
            predicted=evidence_correct,
        )
        field_rows.append(evidence_row)
        per_doc_errors[boe_id] |= not evidence_correct

        temporal = str(truth_row["temporal_status"])
        warned = predicted_key in p0_warnings
        if temporal == "historical_antecedent":
            outcome = "tp" if warned else "fn"
        elif temporal == "current":
            outcome = "fp" if warned else "tn"
        else:
            outcome = "excluded_ambiguous_temporal_truth"
        p0_rows.append({
            "identificador_boe": boe_id,
            "truth_action_key": truth_key,
            "predicted_action_key": predicted_key,
            "temporal_truth": temporal,
            "p0_warning": warned,
            "p0_outcome": outcome,
        })

    # Technical fields and exact power normalization derived from annotated raw truth.
    for predicted_key, truth_key in match_maps["technical_mention"].items():
        truth_row = truth_maps["technical_mentions"][truth_key]
        pred_row = predicted["technical_mentions"][predicted_key]
        boe_id = str(truth_row["identificador_boe"])
        for field_name, expected, predicted_value in (
            (
                "attribute_type",
                str(truth_row["expected_attribute_type"]),
                pred_row["attribute_type"],
            ),
            (
                "value_raw",
                normalize_name(str(truth_row["expected_value_raw"])),
                normalize_name(str(pred_row["value_raw"])),
            ),
        ):
            applicable = expected != NA and str(truth_row[
                "expected_attribute_type" if field_name == "attribute_type" else "expected_value_raw"
            ]) != NA
            field_rows.append(_field_result(
                boe_id=boe_id,
                entity_type="technical_mention",
                truth_key=truth_key,
                predicted_key=predicted_key,
                field_name=field_name,
                expected=expected,
                predicted=predicted_value,
                applicable=applicable,
            ))
        expected_mw = (
            parse_power_mw(str(truth_row["expected_value_raw"]))
            if str(truth_row["expected_attribute_type"]) in POWER_ATTRIBUTE_TYPES
            else None
        )
        if expected_mw is not None:
            predicted_mw = parse_power_mw(str(pred_row["value_raw"]))
            expected_decimal = format(expected_mw.normalize(), "f")
            predicted_decimal = (
                None
                if predicted_mw is None
                else format(predicted_mw.normalize(), "f")
            )
            field_rows.append(_field_result(
                boe_id=boe_id,
                entity_type="technical_mention",
                truth_key=truth_key,
                predicted_key=predicted_key,
                field_name="value_mw_exact",
                expected=expected_decimal,
                predicted=predicted_decimal,
            ))

    # Missing historical truth actions remain extraction FN, never P0 FN.
    matched_truth_actions = set(match_maps["administrative_action"].values())
    for truth_key, truth_row in truth_maps["administrative_actions"].items():
        if (
            _scored(truth_row)
            and truth_key not in matched_truth_actions
            and truth_row["temporal_status"] == "historical_antecedent"
        ):
            p0_rows.append({
                "identificador_boe": str(truth_row["identificador_boe"]),
                "truth_action_key": truth_key,
                "predicted_action_key": pd.NA,
                "temporal_truth": "historical_antecedent",
                "p0_warning": pd.NA,
                "p0_outcome": "missing_extraction_not_p0_fn",
            })
    matched_pred_actions = set(match_maps["administrative_action"])
    for predicted_key in sorted(p0_warnings - matched_pred_actions):
        boe_id = predicted_key.split("|", 1)[0]
        p0_rows.append({
            "identificador_boe": boe_id,
            "truth_action_key": pd.NA,
            "predicted_action_key": predicted_key,
            "temporal_truth": pd.NA,
            "p0_warning": True,
            "p0_outcome": "unadjudicated_warning",
        })

    field_frame = pd.DataFrame(field_rows)
    match_frame = pd.DataFrame(match_rows)
    unmatched_expected_frame = pd.DataFrame(unmatched_expected_rows)
    unmatched_predicted_frame = pd.DataFrame(unmatched_predicted_rows)
    p0_frame = pd.DataFrame(p0_rows)
    issues_frame = pd.DataFrame(issue_rows)

    # Strict document exact match is secondary and unavailable under ambiguity.
    for document_row in document_rows:
        boe_id = document_row["identificador_boe"]
        has_primary_ambiguity = per_doc_uncertain[boe_id]
        if has_primary_ambiguity or not document_row["document_scope_scored"]:
            document_row["document_extraction_exact_match_scored"] = False
            document_row["document_extraction_exact_match"] = pd.NA
        else:
            document_row["document_extraction_exact_match_scored"] = True
            document_row["document_extraction_exact_match"] = not per_doc_errors[boe_id]

    document_frame = pd.DataFrame(document_rows)
    review_rows: list[dict[str, Any]] = []
    for row in document_rows:
        boe_id = row["identificador_boe"]
        reasons = sorted(queue_by_id.get(boe_id, []))
        routed = bool(reasons)
        exact_scored = bool(row["document_extraction_exact_match_scored"])
        exact = bool(row["document_extraction_exact_match"]) if exact_scored else None
        if not exact_scored:
            outcome = "ambiguous_or_excluded_truth_routed" if routed else "ambiguous_or_excluded_truth_not_routed"
        elif exact and routed:
            outcome = "correct_extraction_unnecessarily_routed"
        elif exact:
            outcome = "correct_extraction_not_routed"
        elif routed:
            outcome = "true_extraction_error_routed"
        else:
            outcome = "true_extraction_error_not_routed"
        review_rows.append({
            "identificador_boe": boe_id,
            "routed_to_blocking_review": routed,
            "reason_codes_json": json.dumps(reasons),
            "truth_status": "scored" if exact_scored else "ambiguous_or_excluded",
            "strict_extraction_correct": exact if exact_scored else pd.NA,
            "routing_outcome": outcome,
        })
    review_frame = pd.DataFrame(review_rows)

    entity_metrics: dict[str, Any] = {}
    for entity_type, counts in detection_counts.items():
        entity_metrics[entity_type] = {
            **metric_from_counts(counts["tp"], counts["fp"], counts["fn"]),
            "aggregation": "micro",
            "unit": entity_type,
            "excluded_truth": counts["excluded_truth"],
            "excluded_predicted": counts["excluded_predicted"],
            "matching_ambiguities": counts["matching_ambiguities"],
        }
    field_metrics: dict[str, Any] = {}
    if not field_frame.empty:
        applicable_fields = field_frame.loc[field_frame["applicable"].eq(True)]
        for (entity_type, field_name), group in applicable_fields.groupby(
            ["entity_type", "field_name"], sort=True
        ):
            numerator = int(group["correct"].eq(True).sum())
            denominator = len(group)
            present = int(group["predicted_present"].eq(True).sum())
            field_metrics[f"{entity_type}.{field_name}"] = {
                "correct": numerator,
                "scored": denominator,
                "accuracy": _safe_ratio(numerator, denominator),
                "predicted_present": present,
                "coverage": _safe_ratio(present, denominator),
                "aggregation": "micro_over_matched_entities",
            }

    p0_counter = Counter(p0_frame["p0_outcome"].astype(str)) if not p0_frame.empty else Counter()
    p0_metric = {
        "tp": p0_counter["tp"],
        "fp": p0_counter["fp"],
        "fn": p0_counter["fn"],
        "tn": p0_counter["tn"],
        "precision": _safe_ratio(p0_counter["tp"], p0_counter["tp"] + p0_counter["fp"]),
        "recall": _safe_ratio(p0_counter["tp"], p0_counter["tp"] + p0_counter["fn"]),
        "f1": metric_from_counts(
            p0_counter["tp"], p0_counter["fp"], p0_counter["fn"]
        )["f1"],
        "ambiguous_temporal_truth": p0_counter[
            "excluded_ambiguous_temporal_truth"
        ],
        "missing_extraction_not_p0_fn": p0_counter[
            "missing_extraction_not_p0_fn"
        ],
        "unadjudicated_warnings": p0_counter["unadjudicated_warning"]
        + unresolved_p0_warning_ids,
        "warning_rate_per_predicted_action": _safe_ratio(
            len(p0_warnings), len(predicted["administrative_actions"])
        ),
        "aggregation": "micro_action_level",
    }

    reason_counter = Counter(
        reason
        for reasons in queue_by_id.values()
        for reason in reasons
    )
    routing_counter = Counter(review_frame["routing_outcome"].astype(str))
    review_metrics = {
        "reviewed_documents": int(review_frame["routed_to_blocking_review"].sum()),
        "document_count": len(review_frame),
        "review_rate": _safe_ratio(
            int(review_frame["routed_to_blocking_review"].sum()), len(review_frame)
        ),
        "reason_code_distribution": dict(sorted(reason_counter.items())),
        "true_errors_routed": routing_counter["true_extraction_error_routed"],
        "true_errors_not_routed": routing_counter["true_extraction_error_not_routed"],
        "true_error_routing_rate": _safe_ratio(
            routing_counter["true_extraction_error_routed"],
            routing_counter["true_extraction_error_routed"]
            + routing_counter["true_extraction_error_not_routed"],
        ),
        "correct_extractions_unnecessarily_routed": routing_counter[
            "correct_extraction_unnecessarily_routed"
        ],
        "scored_correct_extractions": routing_counter[
            "correct_extraction_unnecessarily_routed"
        ]
        + routing_counter["correct_extraction_not_routed"],
        "unnecessary_review_rate": _safe_ratio(
            routing_counter["correct_extraction_unnecessarily_routed"],
            routing_counter["correct_extraction_unnecessarily_routed"]
            + routing_counter["correct_extraction_not_routed"],
        ),
        "ambiguous_or_excluded_routed": routing_counter[
            "ambiguous_or_excluded_truth_routed"
        ],
    }

    exact_scored = document_frame.loc[
        document_frame["document_extraction_exact_match_scored"].eq(True)
    ]
    exact_correct = int(exact_scored["document_extraction_exact_match"].eq(True).sum())
    metrics = {
        "truth_contract_version": CONTRACT_VERSION,
        "evaluation_contract_declaration_sha256": sha256_file(
            CONTRACT_DECLARATION_PATH
        ),
        "primary_scope": "frozen_extraction_output_only",
        "aggregation_policy": "micro; no macro average and no global accuracy",
        "document_scope": {
            "correct": document_scope_correct,
            "scored": document_scope_scored,
            "accuracy": _safe_ratio(document_scope_correct, document_scope_scored),
            "aggregation": "micro_document_level",
        },
        "entity_detection": entity_metrics,
        "matched_entity_fields": field_metrics,
        "document_extraction_exact_match_secondary": {
            "correct": exact_correct,
            "scored": len(exact_scored),
            "accuracy": _safe_ratio(exact_correct, len(exact_scored)),
            "excluded_documents": len(document_frame) - len(exact_scored),
        },
        "p0_historical_antecedent": p0_metric,
        "review_routing": review_metrics,
        "downstream_not_scored": [
            "INE resolution",
            "project grouping",
            "Silver",
            "Gold",
            "Streamlit",
        ],
    }
    frames = {
        "document_results": document_frame,
        "entity_matches": match_frame,
        "unmatched_expected": unmatched_expected_frame,
        "unmatched_predicted": unmatched_predicted_frame,
        "field_results": field_frame,
        "p0_results": p0_frame,
        "review_routing_results": review_frame,
        "validation_issues": issues_frame,
    }
    return metrics, frames


def _summary(metrics: Mapping[str, Any]) -> str:
    scope = metrics["document_scope"]
    exact = metrics["document_extraction_exact_match_secondary"]
    p0 = metrics["p0_historical_antecedent"]
    review = metrics["review_routing"]
    lines = [
        "# Final holdout evaluation V1",
        "",
        "Primary scope: frozen extraction output before holdout-specific human decisions.",
        "No global accuracy is reported. Downstream layers are not scored.",
        "",
        "## Document metrics",
        "",
        f"- Document-scope accuracy: {scope['correct']}/{scope['scored']} "
        f"({scope['accuracy']!r})",
        f"- Strict document extraction exact match (secondary): "
        f"{exact['correct']}/{exact['scored']} ({exact['accuracy']!r})",
        "",
        "## Entity detection (micro)",
        "",
    ]
    for entity_type, value in metrics["entity_detection"].items():
        lines.append(
            f"- {entity_type}: TP={value['tp']}, FP={value['fp']}, "
            f"FN={value['fn']}, P={value['precision']!r}, "
            f"R={value['recall']!r}, F1={value['f1']!r}"
        )
    lines.extend([
        "",
        "## Historical-antecedent safeguard",
        "",
        f"- TP={p0['tp']}, FP={p0['fp']}, FN={p0['fn']}, TN={p0['tn']}",
        f"- Precision={p0['precision']!r}, recall={p0['recall']!r}, "
        f"F1={p0['f1']!r}",
        "",
        "## Review routing",
        "",
        f"- Review rate: {review['reviewed_documents']}/{review['document_count']} "
        f"({review['review_rate']!r})",
        f"- True-error routing rate: {review['true_error_routing_rate']!r}",
        f"- Unnecessary review rate: {review['unnecessary_review_rate']!r}",
        "",
        "## Interpretation boundary",
        "",
        "These results do not independently evaluate INE resolution, project grouping, "
        "Silver, Gold or Streamlit.",
        "",
    ])
    return "\n".join(lines)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    frame.to_parquet(path, index=False)


def evaluate(
    *,
    truth_dir: Path,
    predictions_dir: Path,
    execution_record_path: Path,
    output_dir: Path,
) -> EvaluationResult:
    truth = load_truth(truth_dir, require_complete=True, require_frozen=True)
    snapshot = load_prediction_snapshot(predictions_dir)
    _validate_primary_predictions(snapshot, truth)
    _validate_truth_evidence_against_source(truth, snapshot)
    execution_record = validate_execution_record(
        execution_record_path,
        snapshot_identity=snapshot.snapshot_identity,
        truth=truth,
    )
    model_attempt_count = int(
        snapshot.attempts["attempt_origin"].astype(str).eq("model").sum()
    )
    if execution_record["model_usage"]["requests"] < model_attempt_count:
        raise EvaluationError(
            "Execution record model requests are fewer than model-origin attempts."
        )
    before_hashes = {
        path.name: sha256_file(path)
        for path in snapshot.path.iterdir()
        if path.is_file()
    }
    metrics, frames = _evaluate_frames(truth, snapshot)

    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    published = False
    try:
        metrics_path = staging / "metrics.json"
        metrics_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "summary.md").write_text(_summary(metrics), encoding="utf-8")
        semantic_hashes: dict[str, str] = {}
        for name, frame in frames.items():
            path = staging / f"{name}.parquet"
            _write_frame(frame, path)
            sort_columns = list(frame.columns[: min(4, len(frame.columns))])
            semantic_hashes[name] = _semantic_frame_hash(frame, sort_columns)
        semantic_hashes["metrics"] = sha256(canonical_json_bytes(metrics)).hexdigest()
        semantic_hashes["summary"] = sha256(
            (staging / "summary.md").read_bytes()
        ).hexdigest()
        evaluation_id = sha256(canonical_json_bytes({
            "evaluation_contract_version": CONTRACT_VERSION,
            "evaluation_contract_declaration_sha256": sha256_file(
                CONTRACT_DECLARATION_PATH
            ),
            "truth_artifact_id": truth.truth_artifact_id,
            "prediction_snapshot_identity": snapshot.snapshot_identity,
            "frozen_production_git_commit": FROZEN_PRODUCTION_COMMIT,
            "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
            "semantic_artifact_sha256": semantic_hashes,
        })).hexdigest()
        artifacts = {
            path.name: {"sha256": sha256_file(path)}
            for path in sorted(staging.iterdir())
            if path.is_file()
        }
        manifest = {
            "stage": "final_holdout_evaluation",
            "evaluation_contract_version": CONTRACT_VERSION,
            "evaluation_contract_declaration_sha256": sha256_file(
                CONTRACT_DECLARATION_PATH
            ),
            "evaluation_output_id": evaluation_id,
            "truth_artifact_id": truth.truth_artifact_id,
            "truth_file_hashes": truth.manifest["truth_file_hashes"],
            "prediction_snapshot_identity": snapshot.snapshot_identity,
            "prediction_artifact_hashes": dict(snapshot.artifact_hashes),
            "execution_record_sha256": sha256_file(Path(execution_record_path)),
            "execution_run_id": execution_record["run_id"],
            "frozen_production_git_commit": FROZEN_PRODUCTION_COMMIT,
            "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
            "model_provider": FROZEN_MODEL_PROVIDER,
            "model_name": FROZEN_MODEL_NAME,
            "semantic_artifact_sha256": semantic_hashes,
            "artifacts": artifacts,
            "primary_predictions": True,
            "manual_corrections_applied": False,
            "downstream_scored": False,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        after_hashes = {
            path.name: sha256_file(path)
            for path in snapshot.path.iterdir()
            if path.is_file()
        }
        if after_hashes != before_hashes:
            raise EvaluationError("Prediction snapshot changed during evaluation.")
        staging.rename(output_dir)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)
    return EvaluationResult(
        output_dir=output_dir,
        evaluation_output_id=evaluation_id,
        metrics=metrics,
    )
