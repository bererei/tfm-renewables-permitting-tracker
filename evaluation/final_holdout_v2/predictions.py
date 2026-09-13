"""Read-only V2 adapters for the frozen production snapshot and original P0 queue.

V1 lineage guards are reused explicitly. This does not run canonicalisation,
postprocess extraction, or apply historical/manual corrections.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.final_holdout_v1 import contract as v1_contract
from evaluation.final_holdout_v1 import evaluator as v1
from evaluation.final_holdout_v2.contract import DOCUMENT_SCOPES, TruthArtifact

EvaluationError = v1.EvaluationError
PredictionSnapshot = v1.PredictionSnapshot
validate_execution_record = v1.validate_execution_record


def load_prediction_snapshot(path: Path) -> PredictionSnapshot:
    snapshot = v1.load_prediction_snapshot(path)
    hashes, filenames = {}, set()
    for name in snapshot.manifest["artifacts"]:
        artifact, digest = v1._artifact_path(Path(path), snapshot.manifest, name)
        if artifact.is_symlink() or artifact.name in filenames:
            raise EvaluationError("Prediction artifacts require unique regular files.")
        filenames.add(artifact.name)
        hashes[name] = digest
    for name, frame in (("documents", snapshot.documents), ("attempts", snapshot.attempts),
                        ("manual_reviews", snapshot.manual_reviews), ("current_extractions", snapshot.current_extractions),
                        ("review_queue", snapshot.review_queue), ("historical_antecedent_corrections", snapshot.historical_corrections),
                        ("historical_antecedent_reviews", snapshot.historical_reviews)):
        count = snapshot.manifest["artifacts"][name].get("row_count")
        if type(count) is not int or count != len(frame):
            raise EvaluationError(f"Prediction artifact row count mismatch: {name}.")
    return replace(snapshot, artifact_hashes=hashes)


def validate_primary_predictions(snapshot: PredictionSnapshot, truth: TruthArtifact) -> None:
    from renewables_permitting.pipeline import _documents_identity

    v1._validate_primary_predictions(snapshot, truth)
    for label, frame in (("attempts", snapshot.attempts), ("current", snapshot.current_extractions)):
        ids = frame["attempt_id"]
        if ids.isna().any() or ids.astype(str).str.strip().eq("").any() or ids.duplicated().any():
            raise EvaluationError(f"Duplicate or empty {label} attempt identity.")
    if not snapshot.attempts["extraction_status"].isin(["ok", "error"]).all():
        raise EvaluationError("Unknown extraction status in primary attempts.")
    derived = v1_contract._derive_source_document_identities(snapshot.documents)
    actual = dict(zip(derived["identificador"], derived["source_document_sha256"]))
    expected = dict(zip(truth.tables["documents"]["identificador_boe"],
                        truth.tables["documents"]["source_document_sha256"]))
    if actual != expected:
        raise EvaluationError("Canonical source content differs from frozen truth hashes.")
    if snapshot.manifest.get("document_identity_sha256") != _documents_identity(snapshot.documents):
        raise EvaluationError("Prediction manifest document identity mismatch.")
    if "review_queue_id" in snapshot.review_queue:
        queue_ids = snapshot.review_queue["review_queue_id"]
        if queue_ids.isna().any() or queue_ids.duplicated().any():
            raise EvaluationError("Duplicate or empty review queue identity.")
    if "attempt_id" in snapshot.review_queue:
        by_boe = snapshot.attempts.set_index("identificador_boe")["attempt_id"].to_dict()
        for _, row in snapshot.review_queue.iterrows():
            if pd.isna(row["attempt_id"]) or row["attempt_id"] != by_boe[row["identificador_boe"]]:
                raise EvaluationError("Review queue is not from the primary attempt.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError(f"Duplicate prediction JSON key: {key}.")
        result[key] = value
    return result


def _objects(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise EvaluationError(f"{label} must be a list of objects.")
    return value


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise EvaluationError(f"{label} must be a list of nonempty strings.")
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise EvaluationError("Prediction evidence must be text or missing.")
    return value


def flatten_predictions(snapshot: PredictionSnapshot) -> tuple[dict, dict]:
    """Keep frozen positional event/action/location IDs; never match on attributes.

    Validate identity/shape before building maps (no duplicate-key overwrite).
    Missing scored values remain missing, including is_modification; no defaults
    or full model revalidation that could repair/reject an attribute error.
    """
    predicted: dict[str, dict] = {table: {} for table in (
        "events", "generation_assets", "administrative_actions", "locations",
        "associated_components",
    )}
    scopes = {}
    for _, attempt in snapshot.attempts.sort_values("identificador_boe").iterrows():
        boe = str(attempt["identificador_boe"])
        scopes[boe] = None
        if attempt["extraction_status"] != "ok":
            continue
        try:
            payload = json.loads(str(attempt["extraction_json"]), object_pairs_hook=_unique_object)
        except (ValueError, TypeError) as error:
            raise EvaluationError("Invalid primary extraction JSON.") from error
        if not isinstance(payload, dict) or payload.get("boe_id") != boe:
            raise EvaluationError("Prediction payload has a different BOE identity.")
        scope = payload.get("document_scope")
        if scope is not None and scope not in DOCUMENT_SCOPES:
            raise EvaluationError("Unknown explicit prediction document scope.")
        scopes[boe] = scope
        if "document_scope" in attempt and pd.notna(attempt["document_scope"]):
            if attempt["document_scope"] != scope:
                raise EvaluationError("Cached document scope differs from extraction JSON.")
        events = _objects(payload.get("publication_events"), "publication_events")
        if events and scope != "generation_project_specific":
            raise EvaluationError("Predicted events contradict the explicit document scope.")
        for event_index, event in enumerate(events, 1):
            event_key = f"{boe}|pred_event_{event_index}"
            base = {"boe_id": boe, "event_global": event_key}
            predicted["events"][event_key] = {**base, "value": event}
            for table, field, reference in (
                ("generation_assets", "generation_assets", "local_generation_asset_ref"),
                ("associated_components", "associated_components", "local_component_ref"),
            ):
                for entity in _objects(event.get(field, []), field):
                    ref = entity.get(reference)
                    pattern = r"generation_asset_[1-9]\d*" if table == "generation_assets" else r"component_[1-9]\d*"
                    if not isinstance(ref, str) or not re.fullmatch(pattern, ref):
                        raise EvaluationError("Invalid local prediction reference.")
                    key = f"{event_key}:{ref}"
                    if key in predicted[table]:
                        raise EvaluationError("Duplicate local prediction identity.")
                    row = {**base, "names": _strings(entity.get("names_raw", []), "names_raw"),
                           "local_ref": ref, "generation_type": entity.get("generation_type")}
                    if table == "associated_components":
                        row["related_generation_asset_refs"] = _strings(
                            entity.get("related_generation_asset_refs", []), "component links")
                    predicted[table][key] = row
            for index, action in enumerate(_objects(event.get("administrative_actions", []), "actions"), 1):
                predicted["administrative_actions"][f"{event_key}:action_{index}"] = {
                    **base, "action_type": action.get("action_type"), "decision": action.get("decision"),
                    "is_modification": action.get("is_modification"),
                    "targets": _strings(action.get("targets", []), "targets"),
                    "evidence": _text(action.get("evidence")),
                }
            for index, location in enumerate(_objects(event.get("administrative_locations", []), "locations"), 1):
                predicted["locations"][f"{event_key}:location_{index}"] = {
                    **base, "names": [_text(location.get("location_name_raw"))],
                    "location_level": location.get("location_level"),
                }
    return predicted, scopes


def p0_warnings(snapshot: PredictionSnapshot) -> tuple[set[str], list[dict]]:
    """Deduplicate alarms per extracted action; retain every unresolvable finding."""
    warnings: set[str] = set()
    unresolved = []
    if snapshot.review_queue.empty:
        return warnings, unresolved
    required = {"identificador_boe", "reason_code", "validation_issues_json"}
    if not required.issubset(snapshot.review_queue):
        raise EvaluationError("Review queue misses P0 diagnostic columns.")
    for _, row in snapshot.review_queue.iterrows():
        if row["reason_code"] != "possible_historical_antecedent":
            continue
        boe = str(row["identificador_boe"])
        try:
            findings = json.loads(str(row["validation_issues_json"]))
        except ValueError as error:
            raise EvaluationError("Invalid P0 finding JSON.") from error
        if not isinstance(findings, list):
            raise EvaluationError("P0 findings must be an array.")
        for finding in findings or [None]:
            action_id = finding.get("administrative_action_id") if isinstance(finding, dict) else None
            match = re.fullmatch(re.escape(boe) + r"_event_([1-9]\d*)_action_([1-9]\d*)", str(action_id))
            if match:
                warnings.add(f"{boe}|pred_event_{match[1]}:action_{match[2]}")
            else:
                unresolved.append({"identificador_boe": boe, "truth_action_key": None,
                                   "predicted_action_key": None, "temporal_truth": None,
                                   "p0_warning": True, "p0_outcome": "unadjudicated",
                                   "reason": "unresolvable_warning_identity",
                                   "warning_source_json": json.dumps(finding, sort_keys=True, ensure_ascii=False)})
    return warnings, unresolved
