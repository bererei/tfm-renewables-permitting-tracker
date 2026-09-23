from __future__ import annotations

import json
import inspect
from pathlib import Path

import pandas as pd
import pytest

from evaluation.final_holdout_v1.contract import (
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
    TABLE_SPECS,
    TEMPLATES_DIR,
    CONTRACT_DECLARATION_PATH,
    TruthContractError,
    freeze_truth,
    initialize_truth,
    load_truth,
    sha256_file,
)
from evaluation.final_holdout_v1.evaluator import (
    EXECUTION_RECORD_VERSION,
    EvaluationError,
    evaluate,
    load_prediction_snapshot,
    validate_execution_record,
)
from evaluation.final_holdout_v1.matching import (
    deterministic_match,
    evidence_is_correct,
    metric_from_counts,
    name_candidate_pairs,
    normalize_name,
    parse_power_mw,
)
from renewables_permitting.extraction.documents import build_source_document


SYNTHETIC_HOLDOUT_ID = "a" * 64
SYNTHETIC_DOCUMENTS = [
    ("BOE-A-2099-1", "1" * 64),
    ("BOE-A-2099-2", "2" * 64),
    ("BOE-B-2099-3", "3" * 64),
    ("BOE-B-2099-4", "4" * 64),
]


def _document_common(boe_id: str, source_hash: str) -> dict[str, str]:
    return {
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_version": "synthetic_v1",
        "identificador_boe": boe_id,
        "source_document_sha256": source_hash,
        "reviewer_id": "synthetic_reviewer",
        "reviewed_on": "2099-01-01",
        "annotation_notes": NA,
    }


def _entity_common(boe_id: str) -> dict[str, str]:
    return {
        "identificador_boe": boe_id,
        "annotation_notes": NA,
    }


def _write_truth_table(path: Path, table: str, rows: list[dict[str, object]]) -> None:
    columns = TABLE_SPECS[table].columns
    frame = pd.DataFrame(rows, columns=columns)
    frame.to_csv(path / f"{table}.csv", index=False, lineterminator="\n")


def _empty_truth_dir(path: Path) -> Path:
    path.mkdir()
    for table, spec in TABLE_SPECS.items():
        pd.DataFrame(columns=spec.columns).to_csv(
            path / f"{table}.csv", index=False, lineterminator="\n"
        )
    return path


def _truth_rows() -> dict[str, list[dict[str, object]]]:
    rows = {table: [] for table in TABLE_SPECS}
    for boe_id, source_hash in SYNTHETIC_DOCUMENTS:
        document_common = _document_common(boe_id, source_hash)
        entity_common = _entity_common(boe_id)
        if boe_id.endswith("-4"):
            rows["documents"].append({
                **document_common,
                "annotation_status": "complete",
                "scope_applicability": "unknown",
                "scope_adjudication": "ambiguous_not_safely_determinable",
                "expected_document_scope": NA,
            })
            continue
        rows["documents"].append({
            **document_common,
            "annotation_status": "complete",
            "scope_applicability": "applicable",
            "scope_adjudication": "scored_truth",
            "expected_document_scope": "generation_project_specific",
        })
        rows["events"].append({
            **entity_common,
            "event_key": "event_1",
            "event_label": f"Synthetic project {boe_id}",
            "applicability": "applicable",
            "adjudication": "scored_truth",
        })
        rows["generation_assets"].append({
            **entity_common,
            "event_key": "event_1",
            "asset_key": "asset_1",
            "names_json": json.dumps([f"Planta {boe_id}"]),
            "expected_generation_type": "fotovoltaica",
            "applicability": "applicable",
            "adjudication": "scored_truth",
        })
        rows["evidence_passages"].append({
            **entity_common,
            "owner_type": "generation_asset",
            "owner_key": "asset_1",
            "passage_text": f"La planta {boe_id} es fotovoltaica.",
            "applicability": "applicable",
            "adjudication": "scored_truth",
        })
        if boe_id.endswith("-1"):
            rows["technical_mentions"].append({
                **entity_common,
                "event_key": "event_1",
                "owner_type": "generation_asset",
                "owner_key": "asset_1",
                "technical_key": "technical_1",
                "expected_attribute_type": "potencia_instalada",
                "expected_value_raw": "Potencia instalada de 1,5 GW.",
                "applicability": "applicable",
                "adjudication": "scored_truth",
            })
            rows["evidence_passages"].append({
                **entity_common,
                "owner_type": "technical_mention",
                "owner_key": "technical_1",
                "passage_text": "Potencia instalada de 1,5 GW.",
                "applicability": "applicable",
                "adjudication": "scored_truth",
            })

        action_specs = (
            [
                ("action_1", "historical_antecedent", "Actuación histórica alfa.", "applicable", "scored_truth"),
                ("action_2", "current", "Actuación vigente beta.", "applicable", "scored_truth"),
                ("action_3", "historical_antecedent", "Actuación histórica gamma.", "applicable", "scored_truth"),
                ("action_4", "current", "Actuación vigente delta.", "applicable", "scored_truth"),
                ("action_5", "historical_antecedent", "Actuación histórica omitida.", "applicable", "scored_truth"),
                (
                    "action_6",
                    "ambiguous_not_safely_determinable",
                    "Actuación temporalmente ambigua.",
                    "applicable",
                    "scored_truth",
                ),
            ]
            if boe_id.endswith("-1")
            else [(
                "action_1",
                "current",
                f"Actuación vigente {boe_id}.",
                "applicable",
                "scored_truth",
            )]
        )
        for action_key, temporal, passage, applicability, adjudication in action_specs:
            rows["administrative_actions"].append({
                **entity_common,
                "event_key": "event_1",
                "action_key": action_key,
                "expected_action_type": "autorizacion_administrativa_previa",
                "expected_decision": "autorizado",
                "expected_is_modification": "false",
                "temporal_status": temporal,
                "applicability": applicability,
                "adjudication": adjudication,
            })
            rows["action_targets"].append({
                **entity_common,
                "event_key": "event_1",
                "action_key": action_key,
                "target_type": "event",
                "target_truth_key": "event_1",
                "applicability": applicability,
                "adjudication": adjudication,
            })
            rows["evidence_passages"].append({
                **entity_common,
                "owner_type": "administrative_action",
                "owner_key": action_key,
                "passage_text": passage,
                "applicability": applicability,
                "adjudication": adjudication,
            })
    return rows


def _build_truth(path: Path, *, reverse_rows: bool = False) -> Path:
    path.mkdir()
    rows = _truth_rows()
    for table in TABLE_SPECS:
        table_rows = list(reversed(rows[table])) if reverse_rows else rows[table]
        _write_truth_table(path, table, table_rows)
    (path / "truth_metadata.json").write_text(json.dumps({
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_artifact_identity": SYNTHETIC_HOLDOUT_ID,
        "source_snapshot_identity": FROZEN_SOURCE_SNAPSHOT_ID,
        "initialization_mode": "blind_annotation",
        "predictions_exposed_during_annotation": False,
    }), encoding="utf-8")
    return path


def _extraction_json(boe_id: str) -> dict[str, object]:
    passages = (
        [
            "Actuación histórica alfa.",
            "Actuación vigente beta.",
            "Actuación histórica gamma.",
            "Actuación vigente delta.",
            "Actuación temporalmente ambigua.",
        ]
        if boe_id.endswith("-1")
        else [f"Actuación vigente {boe_id}."]
    )
    actions = [
        {
            "action_type": "autorizacion_administrativa_previa",
            "decision": "autorizado",
            "is_modification": False,
            "targets": ["event"],
            "evidence": passage,
        }
        for passage in passages
    ]
    technical_mentions = (
        [{
            "attribute_type": "potencia_instalada",
            "value_raw": "Potencia instalada de 1,5 GW.",
            "evidence": "Potencia instalada de 1,5 GW.",
        }]
        if boe_id.endswith("-1")
        else []
    )
    return {
        "boe_id": boe_id,
        "publication_date": "2099-01-01",
        "classification_status": "classified",
        "document_scope": "generation_project_specific",
        "classification_reason": "Synthetic classified document",
        "publication_events": [{
            "generation_assets": [{
                "local_generation_asset_ref": "generation_asset_1",
                "names_raw": [f"Planta {boe_id}"],
                "generation_type": "fotovoltaica",
                "technical_mentions": technical_mentions,
                "evidence": f"La planta {boe_id} es fotovoltaica.",
            }],
            "associated_components": [],
            "administrative_actions": actions,
            "participants": [],
            "administrative_locations": [],
            "generation_relations": [],
            "case_file_references": [],
            "event_summary": "Synthetic event",
        }],
        "extraction_notes": None,
    }


def _artifact(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    frame.to_parquet(path, index=False)
    return {
        "filename": path.name,
        "row_count": len(frame),
        "sha256": sha256_file(path),
    }


def _refresh_snapshot_artifact(path: Path, artifact_name: str, row_count: int) -> None:
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][artifact_name]
    artifact_path = path / artifact["filename"]
    artifact["row_count"] = row_count
    artifact["sha256"] = sha256_file(artifact_path)
    safeguard_key = (
        "corrections_file_sha256"
        if artifact_name == "historical_antecedent_corrections"
        else "reviews_file_sha256"
        if artifact_name == "historical_antecedent_reviews"
        else None
    )
    if safeguard_key is not None:
        manifest["possible_historical_antecedent"][safeguard_key] = artifact[
            "sha256"
        ]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _mutate_parquet_artifact(
    snapshot_dir: Path,
    artifact_name: str,
    mutate: object,
) -> None:
    manifest = json.loads(
        (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    artifact_path = snapshot_dir / manifest["artifacts"][artifact_name]["filename"]
    frame = pd.read_parquet(artifact_path)
    mutate(frame)
    frame.to_parquet(artifact_path, index=False)
    _refresh_snapshot_artifact(snapshot_dir, artifact_name, len(frame))


def _rewrite_prediction_payload(
    snapshot_dir: Path,
    boe_id: str,
    mutate: object,
) -> None:
    for artifact_name in ("attempts", "current_extractions"):
        manifest = json.loads(
            (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
        )
        artifact_path = snapshot_dir / manifest["artifacts"][artifact_name]["filename"]
        frame = pd.read_parquet(artifact_path)
        row_index = frame.index[frame["identificador_boe"].astype(str).eq(boe_id)][0]
        payload = json.loads(str(frame.at[row_index, "extraction_json"]))
        mutate(payload)
        frame.at[row_index, "extraction_json"] = json.dumps(
            payload, ensure_ascii=False
        )
        frame.to_parquet(artifact_path, index=False)
        _refresh_snapshot_artifact(snapshot_dir, artifact_name, len(frame))


def _build_snapshot(path: Path) -> Path:
    path.mkdir()
    documents = []
    attempts = []
    current = []
    for index, (boe_id, source_hash) in enumerate(SYNTHETIC_DOCUMENTS, start=1):
        extraction = _extraction_json(boe_id)
        evidence = [f"La planta {boe_id} es fotovoltaica."]
        if boe_id.endswith("-1"):
            evidence.append("Potencia instalada de 1,5 GW.")
            evidence.extend([
                "Actuación histórica alfa.",
                "Actuación vigente beta.",
                "Actuación histórica gamma.",
                "Actuación vigente delta.",
                "Actuación histórica omitida.",
                "Actuación temporalmente ambigua.",
            ])
        else:
            evidence.append(f"Actuación vigente {boe_id}.")
        documents.append({
            "identificador": boe_id,
            "source_document_sha256": source_hash,
            "titulo": "Synthetic BOE",
            "texto_limpio": " ".join(evidence),
        })
        attempt = {
            "attempt_id": f"synthetic_attempt_{index}",
            "identificador_boe": boe_id,
            "source_document_sha256": source_hash,
            "attempt_origin": "model",
            "source_attempt_id": pd.NA,
            "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
            "model_provider": FROZEN_MODEL_PROVIDER,
            "model_name": FROZEN_MODEL_NAME,
            "extraction_status": "ok",
            "document_scope": extraction["document_scope"],
            "extraction_json": json.dumps(extraction, ensure_ascii=False),
        }
        attempts.append(attempt)
        current.append(attempt)

    review_queue = pd.DataFrame([
        {
            "identificador_boe": SYNTHETIC_DOCUMENTS[0][0],
            "reason_code": "possible_historical_antecedent",
            "validation_issues_json": json.dumps([
                {"administrative_action_id": f"{SYNTHETIC_DOCUMENTS[0][0]}_event_1_action_1"},
                {"administrative_action_id": f"{SYNTHETIC_DOCUMENTS[0][0]}_event_1_action_2"},
            ]),
        },
        {
            "identificador_boe": SYNTHETIC_DOCUMENTS[2][0],
            "reason_code": "possible_historical_antecedent",
            "validation_issues_json": json.dumps([
                {"administrative_action_id": f"{SYNTHETIC_DOCUMENTS[2][0]}_event_1_action_1"}
            ]),
        },
        {
            "identificador_boe": SYNTHETIC_DOCUMENTS[3][0],
            "reason_code": "classification_uncertain",
            "validation_issues_json": pd.NA,
        },
    ])
    manual_reviews = pd.DataFrame(columns=["identificador_boe"])
    artifacts = {
        "documents": _artifact(path / "documents.parquet", pd.DataFrame(documents)),
        "attempts": _artifact(path / "attempts.parquet", pd.DataFrame(attempts)),
        "manual_reviews": _artifact(path / "manual_reviews.parquet", manual_reviews),
        "current_extractions": _artifact(
            path / "current_extractions.parquet", pd.DataFrame(current)
        ),
        "review_queue": _artifact(path / "review_queue.parquet", review_queue),
    }
    pd.DataFrame(columns=["boe_id"]).to_csv(
        path / "historical_antecedent_corrections.csv", index=False
    )
    artifacts["historical_antecedent_corrections"] = {
        "filename": "historical_antecedent_corrections.csv",
        "row_count": 0,
        "sha256": sha256_file(path / "historical_antecedent_corrections.csv"),
    }
    pd.DataFrame(columns=["boe_id"]).to_csv(
        path / "historical_antecedent_reviews.csv", index=False
    )
    artifacts["historical_antecedent_reviews"] = {
        "filename": "historical_antecedent_reviews.csv",
        "row_count": 0,
        "sha256": sha256_file(path / "historical_antecedent_reviews.csv"),
    }
    manifest = {
        "stage": "extraction",
        "stage_version": "1",
        "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
        "model_provider": FROZEN_MODEL_PROVIDER,
        "model_name": FROZEN_MODEL_NAME,
        "instructions_sha256": FROZEN_INSTRUCTIONS_SHA256,
        "contract_schema_sha256": FROZEN_CONTRACT_SHA256,
        "document_validation_version": "25",
        "document_identity_sha256": "b" * 64,
        "possible_historical_antecedent": {
            "policy_version": "1",
            "reason_code": "possible_historical_antecedent",
            "corrections_logical_path": "synthetic/corrections.csv",
            "corrections_file_sha256": artifacts[
                "historical_antecedent_corrections"
            ]["sha256"],
            "corrections_identity": "d" * 64,
            "reviews_logical_path": "synthetic/reviews.csv",
            "reviews_file_sha256": artifacts[
                "historical_antecedent_reviews"
            ]["sha256"],
            "reviews_identity": "e" * 64,
        },
        "artifacts": artifacts,
    }
    (path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _execution_record(path: Path, snapshot_identity: str) -> Path:
    record = {
        "record_version": EXECUTION_RECORD_VERSION,
        "run_id": "synthetic-primary-v1",
        "started_at_utc": "2099-01-01T00:00:00Z",
        "ended_at_utc": "2099-01-01T00:01:00Z",
        "exact_command": ["synthetic", "extract"],
        "exit_code": 4,
        "frozen_production_git_commit": FROZEN_PRODUCTION_COMMIT,
        "extraction_config_id": FROZEN_EXTRACTION_CONFIG_ID,
        "model_provider": FROZEN_MODEL_PROVIDER,
        "model_name": FROZEN_MODEL_NAME,
        "source_snapshot_identity": FROZEN_SOURCE_SNAPSHOT_ID,
        "holdout_artifact_identity": SYNTHETIC_HOLDOUT_ID,
        "extraction_output_identity": snapshot_identity,
        "stdout_log_path": "logs/stdout.log",
        "stderr_log_path": "logs/stderr.log",
        "python_version": "3.10.synthetic",
        "uv_lock_sha256": FROZEN_UV_LOCK_SHA256,
        "model_usage": {
            "requests": 4,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        },
        "incident_retry_notes": NA,
        "manual_intervention_before_primary_freeze": False,
        "primary_predictions_frozen_at_utc": "2099-01-01T00:02:00Z",
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _canonical_source_row(
    *,
    boe_id: str = "BOE-A-2099-10",
    text: str = "Texto canónico sintético de la publicación.",
) -> dict[str, object]:
    return {
        "identificador": boe_id,
        "fecha_publicacion": "2099-01-10",
        "titulo": "Resolución sintética",
        "texto_limpio": text,
        "xml_status": "ok",
        "doc_file_stem": "20990110-BOE-A-2099-10",
        "url_html": "https://example.invalid/boe.html",
        "url_xml": "https://example.invalid/boe.xml",
        "seccion_nombre": "III",
        "departamento_nombre": "Departamento sintético",
        "epigrafe_nombre": "Energía",
        "summary_sha256": "1" * 64,
        "candidate_policy_version": "synthetic_v1",
        "candidate_policy_id": "synthetic",
        "xml_sha256": "2" * 64,
        "texto_len": len(text),
        "parse_error": pd.NA,
        "source": "synthetic_fixture",
    }


def _write_init_inputs(
    path: Path,
    *,
    source_row: dict[str, object],
) -> tuple[Path, Path, str]:
    source_dir = path / "source"
    source_dir.mkdir(parents=True)
    source_frame = pd.DataFrame([source_row])
    source_frame.to_parquet(source_dir / "documents.parquet", index=False)
    expected_hash = build_source_document(source_frame.iloc[0]).source_document_sha256
    holdout_path = path / "synthetic_holdout.csv"
    pd.DataFrame([{
        "identificador_boe": source_row["identificador"],
        "source_document_sha256": expected_hash,
    }]).to_csv(holdout_path, index=False)
    return holdout_path, source_dir, expected_hash


def test_versioned_empty_templates_are_valid() -> None:
    truth = load_truth(TEMPLATES_DIR)
    assert truth.manifest is None
    assert all(frame.empty for frame in truth.tables.values())
    schema = json.loads(
        Path(
            "evaluation/final_holdout_v1/execution_record.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["$id"] == EXECUTION_RECORD_VERSION
    assert schema["additionalProperties"] is False
    assert "expected_value_mw" not in TABLE_SPECS["technical_mentions"].columns


def test_truth_rejects_malformed_schema_duplicate_keys_and_bad_applicability(
    tmp_path: Path,
) -> None:
    malformed = _empty_truth_dir(tmp_path / "malformed")
    documents = pd.read_csv(malformed / "documents.csv")
    documents.drop(columns=["annotation_notes"]).to_csv(
        malformed / "documents.csv", index=False
    )
    with pytest.raises(TruthContractError, match="columns"):
        load_truth(malformed)

    duplicate = _build_truth(tmp_path / "duplicate")
    documents = pd.read_csv(duplicate / "documents.csv", dtype=str)
    pd.concat([documents, documents.iloc[[0]]]).to_csv(
        duplicate / "documents.csv", index=False
    )
    with pytest.raises(TruthContractError, match="duplicate"):
        load_truth(duplicate)

    bad_applicability = _build_truth(tmp_path / "bad_applicability")
    documents = pd.read_csv(bad_applicability / "documents.csv", dtype=str)
    documents.loc[0, "scope_applicability"] = "unknown"
    documents.loc[0, "scope_adjudication"] = "scored_truth"
    documents.to_csv(bad_applicability / "documents.csv", index=False)
    with pytest.raises(TruthContractError, match="scored_truth"):
        load_truth(bad_applicability)

    bad_adjudication = _build_truth(tmp_path / "bad_adjudication")
    events = pd.read_csv(bad_adjudication / "events.csv", dtype=str)
    events.loc[0, "adjudication"] = "invented"
    events.to_csv(bad_adjudication / "events.csv", index=False)
    with pytest.raises(TruthContractError, match="closed domain"):
        load_truth(bad_adjudication)

    blank = _build_truth(tmp_path / "blank")
    events = pd.read_csv(blank / "events.csv", dtype=str)
    events.loc[0, "event_label"] = ""
    events.to_csv(blank / "events.csv", index=False)
    with pytest.raises(TruthContractError, match="blank cells"):
        load_truth(blank)

    wrong_evidence_owner = _build_truth(tmp_path / "wrong_evidence_owner")
    evidence = pd.read_csv(
        wrong_evidence_owner / "evidence_passages.csv", dtype=str
    )
    evidence.loc[0, "owner_key"] = "missing_owner"
    evidence.to_csv(
        wrong_evidence_owner / "evidence_passages.csv", index=False
    )
    with pytest.raises(TruthContractError, match="unknown owner"):
        load_truth(wrong_evidence_owner)


def test_matching_is_order_independent_and_reports_all_outcomes() -> None:
    arguments = {
        "truth_keys": ["truth_b", "truth_a", "truth_c"],
        "predicted_keys": ["pred_extra", "pred_b", "pred_a"],
        "candidate_pairs": [
            ("truth_a", "pred_a"),
            ("truth_b", "pred_a"),
            ("truth_b", "pred_b"),
        ],
    }
    first = deterministic_match(**arguments)
    second = deterministic_match(**{
        key: list(reversed(value)) for key, value in arguments.items()
    })
    assert first == second
    assert first.matches == (("truth_a", "pred_a"), ("truth_b", "pred_b"))
    assert first.unmatched_truth == ("truth_c",)
    assert first.unmatched_predicted == ("pred_extra",)

    ambiguous = deterministic_match(
        truth_keys=["t1", "t2"],
        predicted_keys=["p1", "p2"],
        candidate_pairs=[("t1", "p1"), ("t1", "p2"), ("t2", "p1"), ("t2", "p2")],
    )
    assert ambiguous.matches == ()
    assert ambiguous.ambiguous_truth == ("t1", "t2")
    assert ambiguous.ambiguous_predicted == ("p1", "p2")

    excluded = deterministic_match(
        truth_keys=["t1"],
        predicted_keys=["p1"],
        candidate_pairs=[("t1", "p1")],
        excluded_truth_keys=["t1"],
    )
    assert excluded.matches == (("t1", "p1"),)
    assert excluded.excluded_truth == ("t1",)


def test_frozen_name_evidence_and_power_normalization() -> None:
    assert normalize_name("  Parque Eólico—Norte ") == "parque eolico norte"
    pairs = name_candidate_pairs(
        {"truth": ["Parque Eólico Norte"]},
        {"prediction": ["PARQUE EOLICO-NORTE"]},
    )
    assert pairs == {("truth", "prediction")}
    assert evidence_is_correct(
        "se otorga autorización [...] queda aprobada",
        ["Por la presente se otorga autorización al proyecto.", "También queda aprobada la obra."],
    )
    assert not evidence_is_correct(
        "texto que solo existe en otra parte",
        ["Pasaje específico de esta actuación."],
    )
    assert str(parse_power_mw("Potencia de 1,5 GW")) == "1500.0"
    assert str(parse_power_mw("Potencia de 1.500 MW")) == "1500"
    assert parse_power_mw("Potencias de 1 MW y 2 MW") is None
    assert parse_power_mw("Potencia entre 50 y 60 MW") is None
    assert parse_power_mw("Potencia de 50–60 MW") is None
    assert parse_power_mw("Potencia combinada de 50 + 60 MW") is None
    assert parse_power_mw("Potencia de 100 MWac") is None
    assert parse_power_mw("Potencia de 100 MWp") is None
    assert parse_power_mw("Potencia de 100 sin unidad") is None


def test_metric_zero_denominators_are_explicit() -> None:
    empty = metric_from_counts(0, 0, 0)
    assert empty == {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "precision": None,
        "recall": None,
        "f1": None,
    }
    zero = metric_from_counts(0, 1, 1)
    assert zero["precision"] == 0.0
    assert zero["recall"] == 0.0
    assert zero["f1"] == 0.0


def test_truth_identity_is_row_order_independent_and_content_sensitive(
    tmp_path: Path,
) -> None:
    first = load_truth(_build_truth(tmp_path / "truth_a"))
    reordered = load_truth(_build_truth(tmp_path / "truth_b", reverse_rows=True))
    assert first.truth_artifact_id == reordered.truth_artifact_id

    changed_path = _build_truth(tmp_path / "truth_changed")
    actions = pd.read_csv(changed_path / "administrative_actions.csv", dtype=str)
    actions.loc[0, "annotation_notes"] = "changed"
    actions.to_csv(changed_path / "administrative_actions.csv", index=False)
    changed = load_truth(changed_path)
    assert changed.truth_artifact_id != first.truth_artifact_id


def test_freeze_truth_writes_verified_manifest_and_never_overwrites(
    tmp_path: Path,
) -> None:
    draft = _build_truth(tmp_path / "truth")
    frozen = freeze_truth(draft, tmp_path / "frozen")
    assert frozen.manifest is not None
    assert frozen.manifest["truth_artifact_id"] == frozen.truth_artifact_id
    assert frozen.manifest["truth_contract_declaration_sha256"] == sha256_file(
        CONTRACT_DECLARATION_PATH
    )
    with pytest.raises(FileExistsError):
        freeze_truth(draft, tmp_path / "frozen")


def test_init_truth_refuses_before_touching_missing_inputs(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="--break-seal"):
        initialize_truth(
            holdout_path=tmp_path / "must_not_be_opened.csv",
            documents_path=tmp_path / "must_not_be_opened.parquet",
            output_dir=tmp_path / "output",
            holdout_version="synthetic",
            reviewer_id="reviewer",
            break_seal=False,
        )
    assert not (tmp_path / "output").exists()


def test_init_truth_derives_canonical_source_identity_without_mutating_source(
    tmp_path: Path,
) -> None:
    source_row = _canonical_source_row()
    holdout_path, source_dir, expected_hash = _write_init_inputs(
        tmp_path,
        source_row=source_row,
    )
    source_path = source_dir / "documents.parquet"
    source_hash_before = sha256_file(source_path)

    output = initialize_truth(
        holdout_path=holdout_path,
        documents_path=source_dir,
        output_dir=tmp_path / "truth_working",
        holdout_version="synthetic_holdout_v1",
        reviewer_id="synthetic_reviewer",
        break_seal=True,
    )

    assert output == (tmp_path / "truth_working").absolute()
    truth = load_truth(output)
    assert truth.tables["documents"].loc[0, "source_document_sha256"] == expected_hash
    assert all(
        frame.empty
        for table, frame in truth.tables.items()
        if table != "documents"
    )
    assert set(path.name for path in output.iterdir()) == {
        *(f"{table}.csv" for table in TABLE_SPECS),
        "truth_metadata.json",
    }
    metadata = json.loads((output / "truth_metadata.json").read_text(encoding="utf-8"))
    assert metadata["predictions_exposed_during_annotation"] is False
    assert metadata["seal_break_acknowledged"] is True
    assert sha256_file(source_path) == source_hash_before


def test_init_truth_identity_changes_with_canonical_source_content(
    tmp_path: Path,
) -> None:
    hashes: list[str] = []
    for label, text in (
        ("first", "Texto canónico sintético inicial."),
        ("changed", "Texto canónico sintético modificado."),
    ):
        case_dir = tmp_path / label
        holdout_path, source_dir, expected_hash = _write_init_inputs(
            case_dir,
            source_row=_canonical_source_row(text=text),
        )
        initialize_truth(
            holdout_path=holdout_path,
            documents_path=source_dir,
            output_dir=case_dir / "truth_working",
            holdout_version="synthetic_holdout_v1",
            reviewer_id="synthetic_reviewer",
            break_seal=True,
        )
        initialized_hash = pd.read_csv(
            case_dir / "truth_working" / "documents.csv",
            dtype=str,
        ).loc[0, "source_document_sha256"]
        assert initialized_hash == expected_hash
        hashes.append(initialized_hash)

    assert hashes[0] != hashes[1]


@pytest.mark.parametrize(
    "missing_column",
    ["identificador", "fecha_publicacion", "titulo", "texto_limpio"],
)
def test_init_truth_rejects_missing_canonical_source_identity_fields(
    tmp_path: Path,
    missing_column: str,
) -> None:
    source_row = _canonical_source_row()
    expected_hash = build_source_document(pd.Series(source_row)).source_document_sha256
    source_row.pop(missing_column)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    pd.DataFrame([source_row]).to_parquet(
        source_dir / "documents.parquet",
        index=False,
    )
    holdout_path = tmp_path / "synthetic_holdout.csv"
    pd.DataFrame([{
        "identificador_boe": "BOE-A-2099-10",
        "source_document_sha256": expected_hash,
    }]).to_csv(holdout_path, index=False)

    with pytest.raises(TruthContractError, match="canonical identity columns"):
        initialize_truth(
            holdout_path=holdout_path,
            documents_path=source_dir,
            output_dir=tmp_path / "truth_working",
            holdout_version="synthetic_holdout_v1",
            reviewer_id="synthetic_reviewer",
            break_seal=True,
        )
    assert not (tmp_path / "truth_working").exists()


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("identificador", "not-a-boe-id"),
        ("fecha_publicacion", "not-a-date"),
        ("titulo", "   "),
        ("texto_limpio", ""),
    ],
)
def test_init_truth_rejects_malformed_canonical_source_identity_fields(
    tmp_path: Path,
    field: str,
    invalid_value: str,
) -> None:
    source_row = _canonical_source_row()
    expected_hash = build_source_document(pd.Series(source_row)).source_document_sha256
    source_row[field] = invalid_value
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    pd.DataFrame([source_row]).to_parquet(
        source_dir / "documents.parquet",
        index=False,
    )
    holdout_path = tmp_path / "synthetic_holdout.csv"
    pd.DataFrame([{
        "identificador_boe": "BOE-A-2099-10",
        "source_document_sha256": expected_hash,
    }]).to_csv(holdout_path, index=False)

    with pytest.raises(TruthContractError, match="invalid canonical identity fields"):
        initialize_truth(
            holdout_path=holdout_path,
            documents_path=source_dir,
            output_dir=tmp_path / "truth_working",
            holdout_version="synthetic_holdout_v1",
            reviewer_id="synthetic_reviewer",
            break_seal=True,
        )
    assert not (tmp_path / "truth_working").exists()


def test_break_seal_path_is_explicit_and_has_no_prediction_input() -> None:
    source = inspect.getsource(initialize_truth)
    assert source.index("if not break_seal") < source.index("_read_csv(holdout_path)")
    assert "predictions" not in inspect.signature(initialize_truth).parameters
    assert "current_extractions" not in source
    assert "review_queue" not in source


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("inherited_attempt", "inherit"),
        ("manual_review", "manual reviews"),
        ("current_review", "CURRENT"),
        ("antecedent_correction", "corrections"),
        ("document_hash", "source hash"),
        ("attempt_hash", "source hashes"),
        ("config", "extraction_config_id"),
        ("snapshot_identity", "snapshot identity mismatch"),
    ],
)
def test_primary_prediction_safeguards_fail_closed(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    truth = freeze_truth(
        _build_truth(tmp_path / f"truth_working_{case}"),
        tmp_path / f"truth_frozen_{case}",
    )
    snapshot_dir = _build_snapshot(tmp_path / f"predictions_{case}")
    holdout_boe = SYNTHETIC_DOCUMENTS[0][0]

    if case == "inherited_attempt":
        def mutate(frame: pd.DataFrame) -> None:
            frame.loc[0, "source_attempt_id"] = "prior_attempt"

        _mutate_parquet_artifact(snapshot_dir, "attempts", mutate)
    elif case == "manual_review":
        def mutate(frame: pd.DataFrame) -> None:
            frame.loc[0, "identificador_boe"] = holdout_boe

        _mutate_parquet_artifact(snapshot_dir, "manual_reviews", mutate)
    elif case in {"current_review", "antecedent_correction"}:
        artifact_name = (
            "historical_antecedent_reviews"
            if case == "current_review"
            else "historical_antecedent_corrections"
        )
        manifest = json.loads(
            (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
        )
        artifact_path = snapshot_dir / manifest["artifacts"][artifact_name]["filename"]
        pd.DataFrame([{"boe_id": holdout_boe}]).to_csv(artifact_path, index=False)
        _refresh_snapshot_artifact(snapshot_dir, artifact_name, 1)
    elif case == "document_hash":
        def mutate(frame: pd.DataFrame) -> None:
            frame.loc[0, "source_document_sha256"] = "f" * 64

        _mutate_parquet_artifact(snapshot_dir, "documents", mutate)
    elif case == "attempt_hash":
        def mutate(frame: pd.DataFrame) -> None:
            frame.loc[0, "source_document_sha256"] = "f" * 64

        _mutate_parquet_artifact(snapshot_dir, "attempts", mutate)
    elif case in {"config", "snapshot_identity"}:
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if case == "config":
            manifest["extraction_config_id"] = "wrong-config"
        else:
            manifest["snapshot_identity_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        raise AssertionError(case)

    if case in {"config", "snapshot_identity"}:
        snapshot_identity = "0" * 64
    else:
        snapshot_identity = load_prediction_snapshot(snapshot_dir).snapshot_identity
    record = _execution_record(
        tmp_path / f"execution_{case}.json", snapshot_identity
    )
    with pytest.raises(EvaluationError, match=message):
        evaluate(
            truth_dir=tmp_path / f"truth_frozen_{case}",
            predictions_dir=snapshot_dir,
            execution_record_path=record,
            output_dir=tmp_path / f"evaluation_{case}",
        )
    assert truth.truth_artifact_id


def test_execution_record_rejects_malformed_commit_and_time_order(
    tmp_path: Path,
) -> None:
    record_path = _execution_record(tmp_path / "record.json", "1" * 64)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record.pop("run_id")
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(EvaluationError, match="fields mismatch"):
        validate_execution_record(record_path)

    record_path = _execution_record(tmp_path / "commit.json", "1" * 64)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["frozen_production_git_commit"] = "0" * 40
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(EvaluationError, match="git_commit"):
        validate_execution_record(record_path)

    record_path = _execution_record(tmp_path / "time.json", "1" * 64)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["ended_at_utc"] = "2098-01-01T00:01:00Z"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(EvaluationError, match="out of order"):
        validate_execution_record(record_path)


def test_synthetic_end_to_end_metrics_p0_routing_and_immutability(
    tmp_path: Path,
) -> None:
    truth_working = _build_truth(tmp_path / "truth_working")
    frozen_truth = freeze_truth(truth_working, tmp_path / "truth_frozen")
    snapshot_dir = _build_snapshot(tmp_path / "predictions")
    snapshot = load_prediction_snapshot(snapshot_dir)
    record = _execution_record(tmp_path / "execution_record.json", snapshot.snapshot_identity)
    assert validate_execution_record(record)["run_id"] == "synthetic-primary-v1"
    before = {
        path.name: sha256_file(path)
        for path in snapshot_dir.iterdir()
        if path.is_file()
    }

    result = evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation",
    )
    after = {
        path.name: sha256_file(path)
        for path in snapshot_dir.iterdir()
        if path.is_file()
    }
    assert before == after
    assert result.output_dir == tmp_path / "evaluation"
    assert result.metrics["document_scope"] == {
        "correct": 3,
        "scored": 3,
        "accuracy": 1.0,
        "aggregation": "micro_document_level",
    }
    actions = result.metrics["entity_detection"]["administrative_action"]
    assert (actions["tp"], actions["fp"], actions["fn"]) == (7, 0, 1)
    assert actions["precision"] == 1.0
    assert actions["recall"] == 7 / 8
    assert actions["f1"] == 14 / 15
    assert actions["excluded_predicted"] == 1
    assets = result.metrics["entity_detection"]["generation_asset"]
    assert assets["excluded_predicted"] == 1
    generation_type = result.metrics["matched_entity_fields"][
        "generation_asset.generation_type"
    ]
    assert generation_type["accuracy"] == 1.0
    assert generation_type["coverage"] == 1.0
    semantic_evidence = result.metrics["matched_entity_fields"][
        "administrative_action.semantic_evidence"
    ]
    assert semantic_evidence["accuracy"] == 1.0
    assert semantic_evidence["coverage"] == 1.0
    p0 = result.metrics["p0_historical_antecedent"]
    assert (p0["tp"], p0["fp"], p0["fn"], p0["tn"]) == (1, 2, 1, 2)
    assert p0["ambiguous_temporal_truth"] == 1
    assert p0["missing_extraction_not_p0_fn"] == 1
    routing = result.metrics["review_routing"]
    assert routing["true_errors_routed"] == 1
    assert routing["correct_extractions_unnecessarily_routed"] == 1
    assert routing["ambiguous_or_excluded_routed"] == 1
    assert routing["reason_code_distribution"] == {
        "classification_uncertain": 1,
        "possible_historical_antecedent": 2,
    }
    technical_mw = result.metrics["matched_entity_fields"][
        "technical_mention.value_mw_exact"
    ]
    assert technical_mw == {
        "correct": 1,
        "scored": 1,
        "accuracy": 1.0,
        "predicted_present": 1,
        "coverage": 1.0,
        "aggregation": "micro_over_matched_entities",
    }
    manifest = json.loads(
        (tmp_path / "evaluation" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["truth_artifact_id"] == frozen_truth.truth_artifact_id
    assert manifest["primary_predictions"] is True
    assert manifest["frozen_production_git_commit"] == FROZEN_PRODUCTION_COMMIT
    assert manifest["evaluation_contract_declaration_sha256"] == sha256_file(
        CONTRACT_DECLARATION_PATH
    )
    unmatched = pd.read_parquet(
        tmp_path / "evaluation" / "unmatched_predicted.parquet"
    )
    excluded_document_predictions = unmatched.loc[
        unmatched["identificador_boe"].eq("BOE-B-2099-4")
    ]
    assert set(excluded_document_predictions["reason"]) == {
        "excluded_from_scoring"
    }
    assert len(result.evaluation_output_id) == 64
    assert set(result.evaluation_output_id) <= set("0123456789abcdef")
    with pytest.raises(FileExistsError):
        evaluate(
            truth_dir=tmp_path / "truth_frozen",
            predictions_dir=snapshot_dir,
            execution_record_path=record,
            output_dir=tmp_path / "evaluation",
        )


def test_target_and_semantic_evidence_errors_are_scored_on_matched_actions(
    tmp_path: Path,
) -> None:
    freeze_truth(
        _build_truth(tmp_path / "truth_working"), tmp_path / "truth_frozen"
    )
    snapshot_dir = _build_snapshot(tmp_path / "predictions")

    def mutate(payload: dict[str, object]) -> None:
        actions = payload["publication_events"][0]["administrative_actions"]
        actions[0]["action_type"] = "autorizacion_administrativa_construccion"
        actions[0]["targets"] = ["generation_asset_1"]
        actions[1]["evidence"] = (
            "Actuación vigente beta. [...] Actuación histórica alfa."
        )
        actions.append({
            "action_type": "autorizacion_administrativa_previa",
            "decision": "autorizado",
            "is_modification": False,
            "targets": ["event"],
            "evidence": "Actuación extra literal.",
        })

    _rewrite_prediction_payload(snapshot_dir, SYNTHETIC_DOCUMENTS[0][0], mutate)

    def add_extra_source(frame: pd.DataFrame) -> None:
        mask = frame["identificador"].astype(str).eq(SYNTHETIC_DOCUMENTS[0][0])
        frame.loc[mask, "texto_limpio"] = (
            frame.loc[mask, "texto_limpio"].astype(str)
            + " Actuación extra literal."
        )

    _mutate_parquet_artifact(snapshot_dir, "documents", add_extra_source)
    snapshot = load_prediction_snapshot(snapshot_dir)
    record = _execution_record(tmp_path / "record.json", snapshot.snapshot_identity)
    result = evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation",
    )
    target_metric = result.metrics["matched_entity_fields"][
        "administrative_action.targets"
    ]
    action_type_metric = result.metrics["matched_entity_fields"][
        "administrative_action.action_type"
    ]
    evidence_metric = result.metrics["matched_entity_fields"][
        "administrative_action.semantic_evidence"
    ]
    assert target_metric["correct"] == target_metric["scored"] - 1
    assert action_type_metric["correct"] == action_type_metric["scored"] - 1
    assert evidence_metric["correct"] == evidence_metric["scored"] - 1
    assert result.metrics["entity_detection"]["administrative_action"]["fp"] == 1


def test_explicit_target_ambiguity_is_excluded_from_field_and_document_scores(
    tmp_path: Path,
) -> None:
    truth_working = _build_truth(tmp_path / "truth_working")
    targets_path = truth_working / "action_targets.csv"
    targets = pd.read_csv(targets_path, dtype=str)
    mask = (
        targets["identificador_boe"].eq(SYNTHETIC_DOCUMENTS[1][0])
        & targets["action_key"].eq("action_1")
    )
    targets.loc[mask, "applicability"] = "unknown"
    targets.loc[mask, "adjudication"] = "ambiguous_not_safely_determinable"
    targets.to_csv(targets_path, index=False)
    freeze_truth(truth_working, tmp_path / "truth_frozen")
    snapshot_dir = _build_snapshot(tmp_path / "predictions")
    snapshot = load_prediction_snapshot(snapshot_dir)
    record = _execution_record(tmp_path / "record.json", snapshot.snapshot_identity)
    evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation",
    )
    fields = pd.read_parquet(tmp_path / "evaluation" / "field_results.parquet")
    target = fields.loc[
        fields["truth_key"].eq(f"{SYNTHETIC_DOCUMENTS[1][0]}|action_1")
        & fields["field_name"].eq("targets")
    ].iloc[0]
    assert not bool(target["applicable"])
    documents = pd.read_parquet(
        tmp_path / "evaluation" / "document_results.parquet"
    )
    document = documents.loc[
        documents["identificador_boe"].eq(SYNTHETIC_DOCUMENTS[1][0])
    ].iloc[0]
    assert not bool(document["document_extraction_exact_match_scored"])


def test_system_created_matching_ambiguity_fails_strict_document_match(
    tmp_path: Path,
) -> None:
    truth_working = _build_truth(tmp_path / "truth_working")
    assets_path = truth_working / "generation_assets.csv"
    assets = pd.read_csv(assets_path, dtype=str)
    source = assets.loc[
        assets["identificador_boe"].eq(SYNTHETIC_DOCUMENTS[1][0])
    ].iloc[0].copy()
    source["asset_key"] = "asset_2"
    assets = pd.concat([assets, source.to_frame().T], ignore_index=True)
    assets.to_csv(assets_path, index=False)
    freeze_truth(truth_working, tmp_path / "truth_frozen")
    snapshot_dir = _build_snapshot(tmp_path / "predictions")

    def mutate(payload: dict[str, object]) -> None:
        assets = payload["publication_events"][0]["generation_assets"]
        duplicate = dict(assets[0])
        duplicate["local_generation_asset_ref"] = "generation_asset_2"
        assets.append(duplicate)

    _rewrite_prediction_payload(snapshot_dir, SYNTHETIC_DOCUMENTS[1][0], mutate)
    snapshot = load_prediction_snapshot(snapshot_dir)
    record = _execution_record(tmp_path / "record.json", snapshot.snapshot_identity)
    result = evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation",
    )
    assert result.metrics["entity_detection"]["generation_asset"][
        "matching_ambiguities"
    ] == 2
    documents = pd.read_parquet(
        tmp_path / "evaluation" / "document_results.parquet"
    )
    document = documents.loc[
        documents["identificador_boe"].eq(SYNTHETIC_DOCUMENTS[1][0])
    ].iloc[0]
    assert bool(document["document_extraction_exact_match_scored"])
    assert not bool(document["document_extraction_exact_match"])


def test_evaluation_is_semantically_deterministic_across_output_directories(
    tmp_path: Path,
) -> None:
    freeze_truth(
        _build_truth(tmp_path / "truth_working"), tmp_path / "truth_frozen"
    )
    snapshot_dir = _build_snapshot(tmp_path / "predictions")
    snapshot = load_prediction_snapshot(snapshot_dir)
    record = _execution_record(tmp_path / "record.json", snapshot.snapshot_identity)
    first = evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation_a",
    )
    second = evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation_b",
    )
    first_manifest = json.loads(
        (first.output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    second_manifest = json.loads(
        (second.output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert first.metrics == second.metrics
    assert first.evaluation_output_id == second.evaluation_output_id
    assert (
        first_manifest["semantic_artifact_sha256"]
        == second_manifest["semantic_artifact_sha256"]
    )
    assert first_manifest["artifacts"] == second_manifest["artifacts"]


def test_unrelated_historical_registries_do_not_taint_primary_predictions(
    tmp_path: Path,
) -> None:
    freeze_truth(
        _build_truth(tmp_path / "truth_working"), tmp_path / "truth_frozen"
    )
    snapshot_dir = _build_snapshot(tmp_path / "predictions")
    manifest = json.loads(
        (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    for artifact_name in (
        "historical_antecedent_corrections",
        "historical_antecedent_reviews",
    ):
        artifact_path = snapshot_dir / manifest["artifacts"][artifact_name]["filename"]
        pd.DataFrame([{"boe_id": "BOE-A-2000-1"}]).to_csv(
            artifact_path, index=False
        )
        _refresh_snapshot_artifact(snapshot_dir, artifact_name, 1)

    def mark_fresh_deterministic(frame: pd.DataFrame) -> None:
        mask = frame["identificador_boe"].astype(str).eq(SYNTHETIC_DOCUMENTS[1][0])
        frame.loc[mask, "attempt_origin"] = "deterministic"

    _mutate_parquet_artifact(snapshot_dir, "attempts", mark_fresh_deterministic)
    _mutate_parquet_artifact(
        snapshot_dir, "current_extractions", mark_fresh_deterministic
    )
    snapshot = load_prediction_snapshot(snapshot_dir)
    record = _execution_record(tmp_path / "record.json", snapshot.snapshot_identity)
    result = evaluate(
        truth_dir=tmp_path / "truth_frozen",
        predictions_dir=snapshot_dir,
        execution_record_path=record,
        output_dir=tmp_path / "evaluation",
    )
    assert result.metrics["document_scope"]["accuracy"] == 1.0


def test_evaluation_namespace_has_no_model_network_or_pipeline_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((Path("evaluation") / "final_holdout_v1").glob("*.py"))
    )
    assert "pydantic_ai" not in source
    assert "requests." not in source
    assert "renewables_permitting.pipeline" not in source
    assert "build_boe_extraction_agent" not in source
