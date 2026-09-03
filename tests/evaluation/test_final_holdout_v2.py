from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from evaluation.final_holdout_v1 import contract as v1
from evaluation.final_holdout_v2.contract import (
    CONTRACT_VERSION,
    MIGRATION_VERSION,
    NA,
    TABLE_SPECS,
    TruthContractError,
    load_truth,
    migrate_v1_truth,
)
from evaluation.final_holdout_v2.terminology import (
    canonical_path,
    field_label,
    qa_path,
    terminology_registry,
)


PROJECT_BOE = "BOE-A-2099-201"
NON_RELEVANT_BOE = "BOE-A-2099-202"


def _write_tables(
    path: Path,
    specs: dict[str, v1.TableSpec],
    rows: dict[str, list[dict[str, object]]],
) -> Path:
    path.mkdir()
    for table, spec in specs.items():
        pd.DataFrame(
            rows.get(table, []),
            columns=spec.columns,
            dtype="string",
        ).to_csv(path / f"{table}.csv", index=False, lineterminator="\n")
    return path


def _document(
    boe_id: str,
    *,
    contract_version: str,
    scope: str,
    status: str,
) -> dict[str, str]:
    return {
        "truth_contract_version": contract_version,
        "holdout_version": "synthetic_holdout",
        "identificador_boe": boe_id,
        "source_document_sha256": (
            "a" * 64 if boe_id == PROJECT_BOE else "b" * 64
        ),
        "annotation_status": status,
        "scope_applicability": "applicable",
        "scope_adjudication": "scored_truth",
        "expected_document_scope": scope,
        "reviewer_id": "synthetic_reviewer",
        "reviewed_on": "2099-01-01",
        "annotation_notes": NA,
    }


def _common(boe_id: str = PROJECT_BOE) -> dict[str, str]:
    return {
        "identificador_boe": boe_id,
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }


def _v2_rows(
    *,
    affected_assets: str = '["asset_1"]',
    include_action_evidence: bool = True,
    include_secondary: bool = False,
) -> dict[str, list[dict[str, object]]]:
    rows = {table: [] for table in TABLE_SPECS}
    rows["documents"] = [
        _document(
            PROJECT_BOE,
            contract_version=CONTRACT_VERSION,
            scope="generation_project_specific",
            status="complete",
        ),
        _document(
            NON_RELEVANT_BOE,
            contract_version=CONTRACT_VERSION,
            scope="not_relevant_for_generation_projects",
            status="complete",
        ),
    ]
    rows["events"] = [{
        **_common(),
        "event_key": "event_1",
        "event_label": "Proyecto Sintético",
    }]
    rows["generation_assets"] = [{
        **_common(),
        "event_key": "event_1",
        "asset_key": "asset_1",
        "names_json": '["Planta Sintética"]',
        "expected_generation_type": "fotovoltaica",
    }]
    rows["administrative_actions"] = [{
        **_common(),
        "event_key": "event_1",
        "action_key": "action_1",
        "expected_action_type": "autorizacion_administrativa_previa",
        "expected_decision": "autorizado",
        "expected_is_modification": "false",
        "temporal_status": "current",
        "expected_affected_generation_asset_keys_json": affected_assets,
    }]
    rows["locations"] = [{
        **_common(),
        "event_key": "event_1",
        "location_key": "location_1",
        "location_name_raw": "Villa Sintética",
        "expected_location_level": "municipio",
    }]
    if include_action_evidence:
        rows["evidence_passages"].append({
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": "Se otorga autorización a la Planta Sintética.",
        })
    if include_secondary:
        rows["associated_components"] = [{
            **_common(),
            "event_key": "event_1",
            "component_key": "component_1",
            "names_json": "[]",
            "description_raw": "Línea sintética",
            "expected_component_type": "linea_electrica",
            "related_asset_keys_json": '["asset_1"]',
        }]
        rows["technical_mentions"] = [{
            **_common(),
            "event_key": "event_1",
            "owner_type": "generation_asset",
            "owner_key": "asset_1",
            "technical_key": "technical_1",
            "expected_attribute_type": "potencia_instalada",
            "expected_value_raw": "25 MW",
        }]
        rows["action_targets"] = [{
            **_common(),
            "event_key": "event_1",
            "action_key": "action_1",
            "target_type": "generation_asset",
            "target_truth_key": "asset_1",
        }]
        rows["participants"] = [{
            **_common(),
            "event_key": "event_1",
            "participant_key": "participant_1",
            "participant_name_raw": "Promotora Sintética, SL",
            "expected_participant_role": "promotor",
        }]
        rows["evidence_passages"].append({
            **_common(),
            "owner_type": "technical_mention",
            "owner_key": "technical_1",
            "passage_text": "25 MW de potencia instalada.",
        })
    return rows


def _write_v2_truth(path: Path, **kwargs: object) -> Path:
    _write_tables(path, TABLE_SPECS, _v2_rows(**kwargs))
    (path / "truth_metadata.json").write_text(
        json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "holdout_artifact_identity": "c" * 64,
            "source_snapshot_identity": "d" * 64,
            "initialization_mode": "synthetic_blind_annotation",
            "predictions_exposed_during_annotation": False,
        }),
        encoding="utf-8",
    )
    return path


def test_v2_primary_completion_needs_no_secondary_rows(tmp_path: Path) -> None:
    truth = load_truth(_write_v2_truth(tmp_path / "truth"), require_complete=True)

    assert truth.tables["associated_components"].empty
    assert truth.tables["technical_mentions"].empty
    assert truth.tables["action_targets"].empty
    assert truth.tables["participants"].empty


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"include_action_evidence": False}, "action-specific evidence"),
        ({"affected_assets": "[]"}, "affected-generation-asset attribution"),
    ],
)
def test_v2_primary_completion_fails_closed(
    tmp_path: Path,
    kwargs: dict[str, object],
    message: str,
) -> None:
    path = _write_v2_truth(tmp_path / "truth", **kwargs)

    with pytest.raises(TruthContractError, match=message):
        load_truth(path)


def test_valid_secondary_rows_do_not_change_completion(tmp_path: Path) -> None:
    truth = load_truth(
        _write_v2_truth(tmp_path / "truth", include_secondary=True),
        require_complete=True,
    )

    assert len(truth.tables["associated_components"]) == 1
    assert len(truth.tables["technical_mentions"]) == 1
    assert len(truth.tables["participants"]) == 1


def test_canonical_terminology_paths_are_deterministic() -> None:
    row = {
        "action_key": "action_1",
        "owner_type": "administrative_action",
        "owner_key": "action_1",
    }

    assert terminology_registry() is terminology_registry()
    assert field_label("administrative_action", "expected_decision") == "Decisión"
    assert canonical_path("document", field="expected_document_scope") == (
        "document.expected_document_scope"
    )
    assert canonical_path(
        "generation_asset", local_key="asset_1", field="names_json"
    ) == "generation_asset/asset_1.names_json"
    assert qa_path("administrative_actions", row, "expected_decision") == (
        "administrative_action/action_1.expected_decision"
    )
    assert qa_path("evidence_passages", row, "passage_text") == (
        "evidence_passage/administrative_action/action_1"
    )


def _v1_rows() -> dict[str, list[dict[str, object]]]:
    rows = {table: [] for table in v1.TABLE_SPECS}
    rows["documents"] = [
        _document(
            PROJECT_BOE,
            contract_version=v1.CONTRACT_VERSION,
            scope="generation_project_specific",
            status="complete",
        ),
        _document(
            NON_RELEVANT_BOE,
            contract_version=v1.CONTRACT_VERSION,
            scope="not_relevant_for_generation_projects",
            status="complete",
        ),
    ]
    rows["events"] = [{
        **_common(),
        "event_key": "event_1",
        "event_label": "Proyecto Sintético",
    }]
    rows["generation_assets"] = [
        {
            **_common(),
            "event_key": "event_1",
            "asset_key": "asset_1",
            "names_json": '["Planta Uno"]',
            "expected_generation_type": "fotovoltaica",
        },
        {
            **_common(),
            "event_key": "event_1",
            "asset_key": "asset_2",
            "names_json": '["Planta Dos"]',
            "expected_generation_type": "eolica",
        },
    ]
    rows["associated_components"] = [{
        **_common(),
        "event_key": "event_1",
        "component_key": "component_1",
        "names_json": "[]",
        "description_raw": "Infraestructura compartida",
        "expected_component_type": "sistema_evacuacion",
        "related_asset_keys_json": '["asset_2"]',
    }]
    action_specs = (
        ("action_1", "event"),
        ("action_2", "generation_asset"),
        ("action_3", "associated_component"),
        ("action_4", "unsafe"),
    )
    rows["administrative_actions"] = [
        {
            **_common(),
            "event_key": "event_1",
            "action_key": action_key,
            "expected_action_type": "autorizacion_administrativa_previa",
            "expected_decision": "autorizado",
            "expected_is_modification": "false",
            "temporal_status": "current",
        }
        for action_key, _ in action_specs
    ]
    targets = {
        "event": ("event", "event_1", "applicable", "scored_truth"),
        "generation_asset": (
            "generation_asset",
            "asset_1",
            "applicable",
            "scored_truth",
        ),
        "associated_component": (
            "associated_component",
            "component_1",
            "applicable",
            "scored_truth",
        ),
        "unsafe": (
            "event",
            "event_1",
            "unknown",
            "ambiguous_not_safely_determinable",
        ),
    }
    rows["action_targets"] = []
    for action_key, kind in action_specs:
        target_type, target_key, applicability, adjudication = targets[kind]
        target_row = {
            **_common(),
            "event_key": "event_1",
            "action_key": action_key,
            "target_type": target_type,
            "target_truth_key": target_key,
        }
        target_row["applicability"] = applicability
        target_row["adjudication"] = adjudication
        rows["action_targets"].append(target_row)
        rows["evidence_passages"].append({
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": action_key,
            "passage_text": f"Pasaje sintético para {action_key}.",
        })
    rows["participants"] = [{
        **_common(),
        "event_key": "event_1",
        "participant_key": "participant_1",
        "participant_name_raw": "Promotora Sintética, SL",
        "expected_participant_role": "promotor",
    }]
    return rows


def _write_v1_truth(path: Path) -> Path:
    _write_tables(path, v1.TABLE_SPECS, _v1_rows())
    (path / "truth_metadata.json").write_text(
        json.dumps({
            "truth_contract_version": v1.CONTRACT_VERSION,
            "holdout_artifact_identity": "c" * 64,
            "source_snapshot_identity": "d" * 64,
            "initialization_mode": "synthetic_blind_annotation",
            "predictions_exposed_during_annotation": False,
            "seal_break_acknowledged": True,
        }),
        encoding="utf-8",
    )
    v1.load_truth(path, require_complete=True)
    return path


def test_migration_is_non_destructive_and_preserves_rows_and_provenance(
    tmp_path: Path,
) -> None:
    source = _write_v1_truth(tmp_path / "v1")
    before = {path.name: path.read_bytes() for path in sorted(source.iterdir())}
    source_truth = v1.load_truth(source)

    output = migrate_v1_truth(source, tmp_path / "v2")
    migrated = load_truth(output)
    after = {path.name: path.read_bytes() for path in sorted(source.iterdir())}

    assert before == after
    for table in TABLE_SPECS:
        if table in {"documents", "administrative_actions"}:
            continue
        assert_frame_equal(
            migrated.tables[table].reset_index(drop=True),
            source_truth.tables[table].reset_index(drop=True),
        )
    assert migrated.tables["documents"][
        ["identificador_boe", "source_document_sha256", "holdout_version"]
    ].to_dict("records") == source_truth.tables["documents"][
        ["identificador_boe", "source_document_sha256", "holdout_version"]
    ].to_dict("records")
    assert_frame_equal(
        migrated.tables["administrative_actions"].drop(
            columns=["expected_affected_generation_asset_keys_json"]
        ).reset_index(drop=True),
        source_truth.tables["administrative_actions"].reset_index(drop=True),
    )
    metadata = migrated.metadata["migration"]
    assert metadata["migration_version"] == MIGRATION_VERSION
    assert metadata["source_truth_artifact_id"] == source_truth.truth_artifact_id
    assert metadata["predictions_used"] is False


def test_migration_derives_only_safe_human_v1_attributions(tmp_path: Path) -> None:
    output = migrate_v1_truth(
        _write_v1_truth(tmp_path / "v1"),
        tmp_path / "v2",
    )
    truth = load_truth(output)
    actions = truth.tables["administrative_actions"].set_index("action_key")

    assert json.loads(actions.loc["action_1", "expected_affected_generation_asset_keys_json"]) == [
        "asset_1",
        "asset_2",
    ]
    assert json.loads(actions.loc["action_2", "expected_affected_generation_asset_keys_json"]) == [
        "asset_1"
    ]
    assert json.loads(actions.loc["action_3", "expected_affected_generation_asset_keys_json"]) == [
        "asset_2"
    ]
    assert json.loads(actions.loc["action_4", "expected_affected_generation_asset_keys_json"]) == []
    assert truth.metadata["migration"]["unresolved_affected_asset_actions"] == [
        f"{PROJECT_BOE}|action_4"
    ]


def test_migration_status_is_generic_and_non_overwriting(tmp_path: Path) -> None:
    source = _write_v1_truth(tmp_path / "v1")
    output = migrate_v1_truth(source, tmp_path / "v2")
    documents = load_truth(output).tables["documents"].set_index(
        "identificador_boe"
    )

    assert documents.loc[PROJECT_BOE, "annotation_status"] == "draft"
    assert documents.loc[NON_RELEVANT_BOE, "annotation_status"] == "complete"
    with pytest.raises(FileExistsError, match="already exists"):
        migrate_v1_truth(source, output)


def test_migration_refuses_output_inside_v1_workspace(tmp_path: Path) -> None:
    source = _write_v1_truth(tmp_path / "v1")

    with pytest.raises(TruthContractError, match="immutable V1 workspace"):
        migrate_v1_truth(source, source / "v2")
    assert not (source / "v2").exists()
