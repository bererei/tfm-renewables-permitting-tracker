from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import evaluation.final_holdout_v2.annotation as annotation_module
from evaluation.final_holdout_v2.annotation import (
    SOURCE_DIR_ENV,
    TRUTH_DIR_ENV,
    action_deletion_impact,
    action_has_scored_evidence,
    action_evidence_rows,
    build_ai_qa_review_package,
    delete_administrative_action,
    delete_truth_row,
    deletion_dependencies,
    load_annotation_workspace,
    mark_document_complete,
    next_key_for_table,
    secondary_evidence_rows,
    serialize_affected_assets,
    update_document_scope,
    upsert_action_with_initial_evidence,
    upsert_action_with_evidence_set,
    upsert_truth_row,
    validate_document,
    validation_error_feedback,
)
from evaluation.final_holdout_v2.contract import (
    CONTRACT_VERSION,
    NA,
    TABLE_SPECS,
    TruthContractError,
    load_truth,
)
from evaluation.final_holdout_v2.terminology import qa_path, widget_label
from renewables_permitting.extraction.documents import build_source_document


BOE_ID = "BOE-A-2099-301"
ACTION_EVIDENCE = "Se otorga autorización administrativa previa a Planta V2."
SECOND_ACTION_EVIDENCE = "Se publica la decisión administrativa para Planta V2."
SECONDARY_EVIDENCE = "Promotora V2, SL figura como promotora."
REPOSITORY_ROOT = Path(__file__).parents[2]
ANNOTATION_APP = REPOSITORY_ROOT / "evaluation/final_holdout_v2/annotation_app.py"


def _common() -> dict[str, str]:
    return {
        "identificador_boe": BOE_ID,
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }


@pytest.fixture
def v2_annotation_workspace(tmp_path: Path) -> tuple[Path, Path]:
    source = pd.DataFrame([{
        "identificador": BOE_ID,
        "fecha_publicacion": pd.Timestamp(2099, 2, 1),
        "titulo": "Resolución sintética V2",
        "texto_limpio": (
            "La planta fotovoltaica Planta V2 se sitúa en Villa V2. "
            f"{ACTION_EVIDENCE} {SECOND_ACTION_EVIDENCE} "
            f"{SECONDARY_EVIDENCE} Tiene 25 MW de potencia instalada."
        ),
    }])
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source.to_parquet(source_dir / "documents.parquet", index=False)
    source_hash = build_source_document(source.iloc[0]).source_document_sha256

    rows: dict[str, list[dict[str, object]]] = {
        table: [] for table in TABLE_SPECS
    }
    rows["documents"] = [{
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_version": "synthetic_v2",
        "identificador_boe": BOE_ID,
        "source_document_sha256": source_hash,
        "annotation_status": "draft",
        "scope_applicability": "applicable",
        "scope_adjudication": "scored_truth",
        "expected_document_scope": "generation_project_specific",
        "reviewer_id": "synthetic_reviewer",
        "reviewed_on": "2099-02-01",
        "annotation_notes": NA,
    }]
    rows["events"] = [{
        **_common(),
        "event_key": "event_1",
        "event_label": "Planta V2",
    }]
    rows["generation_assets"] = [{
        **_common(),
        "event_key": "event_1",
        "asset_key": "asset_1",
        "names_json": '["Planta V2"]',
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
        "expected_affected_generation_asset_keys_json": '["asset_1"]',
    }]
    rows["locations"] = [{
        **_common(),
        "event_key": "event_1",
        "location_key": "location_1",
        "location_name_raw": "Villa V2",
        "expected_location_level": "municipio",
    }]
    rows["evidence_passages"] = [
        {
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": ACTION_EVIDENCE,
        },
        {
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": SECOND_ACTION_EVIDENCE,
        },
        {
            **_common(),
            "owner_type": "participant",
            "owner_key": "participant_1",
            "passage_text": SECONDARY_EVIDENCE,
        },
    ]
    rows["participants"] = [{
        **_common(),
        "event_key": "event_1",
        "participant_key": "participant_1",
        "participant_name_raw": "Promotora V2, SL",
        "expected_participant_role": "promotor",
    }]
    truth_dir = tmp_path / "truth"
    truth_dir.mkdir()
    for table, spec in TABLE_SPECS.items():
        pd.DataFrame(rows[table], columns=spec.columns, dtype="string").to_csv(
            truth_dir / f"{table}.csv",
            index=False,
            lineterminator="\n",
        )
    (truth_dir / "truth_metadata.json").write_text(
        json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "holdout_artifact_identity": "e" * 64,
            "source_snapshot_identity": "f" * 64,
            "initialization_mode": "synthetic_blind_annotation",
            "predictions_exposed_during_annotation": False,
        }),
        encoding="utf-8",
    )
    load_truth(truth_dir)
    return truth_dir, source_dir


@pytest.fixture
def v2_multirow_annotation_workspace(
    v2_annotation_workspace: tuple[Path, Path],
) -> tuple[Path, Path]:
    truth_dir, source_dir = v2_annotation_workspace
    truth = load_truth(truth_dir)
    tables = {
        table: frame.copy()
        for table, frame in truth.tables.items()
    }

    def append_rows(table: str, rows: list[dict[str, object]]) -> None:
        tables[table] = pd.concat(
            [tables[table], pd.DataFrame(rows)],
            ignore_index=True,
        )

    append_rows(
        "events",
        [{
            **_common(),
            "event_key": "event_2",
            "event_label": "Proyecto V2 alternativo",
            "annotation_notes": "Notas persistidas del evento 2",
        }],
    )
    append_rows(
        "generation_assets",
        [{
            **_common(),
            "event_key": "event_2",
            "asset_key": "asset_2",
            "names_json": '["Parque Eólico V2"]',
            "expected_generation_type": "eolica",
        }],
    )

    actions = tables["administrative_actions"]
    actions.loc[:, "expected_action_type"] = "declaracion_utilidad_publica"
    actions.loc[:, "expected_decision"] = "declarado"
    tables["administrative_actions"] = pd.concat(
        [
            actions,
            pd.DataFrame(
                [
                    {
                        **_action_row("action_2"),
                        "event_key": "event_2",
                        "expected_action_type": "autorizacion_administrativa_previa",
                        "expected_decision": "autorizado",
                        "temporal_status": "historical_antecedent",
                        "expected_affected_generation_asset_keys_json": '["asset_2"]',
                        "annotation_notes": "Notas persistidas de action_2",
                    },
                    {
                        **_action_row("action_3"),
                        "expected_action_type": "autorizacion_administrativa_previa",
                        "expected_decision": "autorizado",
                        "expected_is_modification": "true",
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    append_rows(
        "locations",
        [{
            **_common(),
            "event_key": "event_2",
            "location_key": "location_2",
            "location_name_raw": "Provincia V2",
            "expected_location_level": "provincia",
        }],
    )
    append_rows(
        "associated_components",
        [
            {
                **_common(),
                "event_key": "event_1",
                "component_key": "component_1",
                "names_json": '["Línea V2"]',
                "description_raw": "Línea subterránea V2",
                "expected_component_type": "linea_electrica",
                "related_asset_keys_json": '["asset_1"]',
            },
            {
                **_common(),
                "event_key": "event_2",
                "component_key": "component_2",
                "names_json": '["SET V2"]',
                "description_raw": "Subestación V2",
                "expected_component_type": "subestacion_electrica",
                "related_asset_keys_json": '["asset_2"]',
            },
        ],
    )
    append_rows(
        "technical_mentions",
        [
            {
                **_common(),
                "event_key": "event_1",
                "owner_type": "generation_asset",
                "owner_key": "asset_1",
                "technical_key": "technical_1",
                "expected_attribute_type": "potencia_instalada",
                "expected_value_raw": "25 MW",
            },
            {
                **_common(),
                "event_key": "event_2",
                "owner_type": "generation_asset",
                "owner_key": "asset_2",
                "technical_key": "technical_2",
                "expected_attribute_type": "potencia_pico",
                "expected_value_raw": "30 MWp",
            },
        ],
    )
    append_rows(
        "action_targets",
        [
            {
                **_common(),
                "event_key": "event_1",
                "action_key": "action_1",
                "target_type": "generation_asset",
                "target_truth_key": "asset_1",
            },
            {
                **_common(),
                "event_key": "event_2",
                "action_key": "action_2",
                "target_type": "generation_asset",
                "target_truth_key": "asset_2",
            },
        ],
    )
    append_rows(
        "participants",
        [{
            **_common(),
            "event_key": "event_2",
            "participant_key": "participant_2",
            "participant_name_raw": "Operadora V2, SL",
            "expected_participant_role": "operador",
        }],
    )
    append_rows(
        "evidence_passages",
        [
            {
                **_common(),
                "owner_type": "administrative_action",
                "owner_key": "action_2",
                "passage_text": ACTION_EVIDENCE,
            },
            {
                **_common(),
                "owner_type": "participant",
                "owner_key": "participant_1",
                "passage_text": "Tiene 25 MW de potencia instalada.",
            },
        ],
    )
    for table, spec in TABLE_SPECS.items():
        tables[table].loc[:, list(spec.columns)].to_csv(
            truth_dir / f"{table}.csv",
            index=False,
            lineterminator="\n",
        )
    load_truth(truth_dir)
    return truth_dir, source_dir


def _mark_complete(truth_dir: Path) -> None:
    documents = pd.read_csv(
        truth_dir / "documents.csv", dtype="string", keep_default_na=False
    )
    documents.loc[:, "annotation_status"] = "complete"
    documents.to_csv(truth_dir / "documents.csv", index=False, lineterminator="\n")
    load_truth(truth_dir, require_complete=True)


def _workspace_bytes(truth_dir: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(truth_dir.iterdir())}


def _source_text(truth_dir: Path, source_dir: Path) -> str:
    workspace = load_annotation_workspace(truth_dir, source_dir)
    source = workspace.source_documents.iloc[0]
    return f"{source['titulo']}\n{source['texto_limpio']}"


def _action_row(
    action_key: str,
    *,
    applicability: str = "applicable",
    adjudication: str = "scored_truth",
    affected_assets: str = '["asset_1"]',
) -> dict[str, str]:
    return {
        **_common(),
        "event_key": "event_1",
        "action_key": action_key,
        "expected_action_type": "autorizacion_administrativa_previa",
        "expected_decision": "autorizado",
        "expected_is_modification": "false",
        "temporal_status": "current",
        "expected_affected_generation_asset_keys_json": affected_assets,
        "applicability": applicability,
        "adjudication": adjudication,
    }


def _fill_new_action_form(app: AppTest) -> None:
    selections = {
        "Evento · administrative_action/<nueva_clave>.event_key": "event_1",
        "Tipo de actuación · administrative_action/<nueva_clave>.expected_action_type": (
            "autorizacion_administrativa_previa"
        ),
        "Decisión · administrative_action/<nueva_clave>.expected_decision": (
            "autorizado"
        ),
        "Es modificación · administrative_action/<nueva_clave>.expected_is_modification": (
            "false"
        ),
        "Temporalidad · administrative_action/<nueva_clave>.temporal_status": (
            "current"
        ),
        "Aplicabilidad · administrative_action/<nueva_clave>.applicability": (
            "applicable"
        ),
        "Adjudicación · administrative_action/<nueva_clave>.adjudication": (
            "scored_truth"
        ),
    }
    for label, value in selections.items():
        next(
            widget for widget in app.selectbox if widget.label == label
        ).set_value(value)
    next(
        widget
        for widget in app.multiselect
        if widget.label
        == "Activos afectados · administrative_action/<nueva_clave>."
        "expected_affected_generation_asset_keys_json"
    ).set_value(["asset_1"])


def _action_evidence_inputs(app: AppTest, action_key: str) -> list[object]:
    path = f"evidence_passage/administrative_action/{action_key}"
    return [
        widget
        for widget in app.text_area
        if widget.label.startswith("Evidencia literal de la actuación")
        and path in widget.label
    ]


def _keep_only_action_evidence(truth_dir: Path, passage_text: str) -> None:
    evidence = pd.read_csv(
        truth_dir / "evidence_passages.csv",
        dtype="string",
        keep_default_na=False,
    )
    keep = ~evidence["owner_type"].astype(str).eq(
        "administrative_action"
    ) | evidence["passage_text"].astype(str).eq(passage_text)
    evidence.loc[keep].to_csv(
        truth_dir / "evidence_passages.csv",
        index=False,
        lineterminator="\n",
    )
    load_truth(truth_dir)


def _reset_to_unscoped_empty_truth(truth_dir: Path) -> None:
    for table, spec in TABLE_SPECS.items():
        frame = pd.read_csv(
            truth_dir / f"{table}.csv",
            dtype="string",
            keep_default_na=False,
        )
        if table == "documents":
            frame.loc[:, "annotation_status"] = "draft"
            frame.loc[:, "scope_applicability"] = "unknown"
            frame.loc[:, "scope_adjudication"] = (
                "ambiguous_not_safely_determinable"
            )
            frame.loc[:, "expected_document_scope"] = NA
            frame.loc[:, "annotation_notes"] = NA
        else:
            frame = pd.DataFrame(columns=spec.columns, dtype="string")
        frame.to_csv(
            truth_dir / f"{table}.csv",
            index=False,
            lineterminator="\n",
        )
    load_truth(truth_dir)


def test_affected_assets_are_serialized_from_a_selector_not_manual_json() -> None:
    assert serialize_affected_assets(["asset_2", "asset_1", "asset_2"]) == (
        '["asset_2","asset_1"]'
    )
    assert serialize_affected_assets([]) == "[]"


def test_ui_and_qa_export_import_the_same_terminology_registry() -> None:
    for module_path in (
        Path("evaluation/final_holdout_v2/annotation.py"),
        Path("evaluation/final_holdout_v2/annotation_app.py"),
    ):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "evaluation.final_holdout_v2.terminology" in imports

    assert widget_label(
        "administrative_action",
        "expected_decision",
        local_key="action_1",
    ) == "Decisión · administrative_action/action_1.expected_decision"
    assert qa_path(
        "administrative_actions",
        {"action_key": "action_1"},
        "expected_decision",
    ) == "administrative_action/action_1.expected_decision"


def test_v2_review_package_is_primary_first_secondary_labelled_and_deterministic(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    workspace = load_annotation_workspace(truth_dir, source_dir)
    source = workspace.source_documents.iloc[0]
    before = {path.name: path.read_bytes() for path in sorted(truth_dir.iterdir())}

    first = build_ai_qa_review_package(
        workspace.truth,
        BOE_ID,
        title=str(source["titulo"]),
        publication_date="2099-02-01",
        source_text=str(source["texto_limpio"]),
    )
    second = build_ai_qa_review_package(
        workspace.truth,
        BOE_ID,
        title=str(source["titulo"]),
        publication_date="2099-02-01",
        source_text=str(source["texto_limpio"]),
    )
    text = first.decode("utf-8")

    assert first == second
    assert before == {
        path.name: path.read_bytes() for path in sorted(truth_dir.iterdir())
    }
    primary_start = text.index("## Verdad primaria V2")
    secondary_start = text.index(
        "## Datos secundarios / diagnósticos — no bloqueantes"
    )
    primary_headings = (
        "### Documento",
        "### Evento / proyecto publicado",
        "### Activo de generación",
        "### Actuación administrativa",
        "### Evidencias de actuaciones administrativas",
        "### Localización",
    )
    positions = [text.index(heading, primary_start) for heading in primary_headings]
    assert positions == sorted(positions)
    assert positions[-1] < secondary_start
    assert text.count("### Evidencias de actuaciones administrativas") == 1
    assert text.count(
        f"{ACTION_EVIDENCE} [applicability=applicable; adjudication=scored_truth]"
    ) == 1
    assert text.count(
        f"{SECOND_ACTION_EVIDENCE} "
        "[applicability=applicable; adjudication=scored_truth]"
    ) == 1
    for path in (
        "document.expected_document_scope",
        "generation_asset/asset_1.names_json",
        "administrative_action/action_1.expected_decision",
        "administrative_action/action_1.expected_affected_generation_asset_keys_json",
        "location/location_1.expected_location_level",
        "evidence_passage/administrative_action/action_1",
        "participant/participant_1.expected_participant_role",
    ):
        assert f"`{path}`" in text
    assert "SECUNDARIO_NO_BLOQUEANTE" in text
    assert "### Otras evidencias — secundarias / diagnósticas" in text
    assert "SIN DISCREPANCIAS PRIMARIAS V2 DETECTADAS." in text
    for forbidden in (
        "attempts.parquet",
        "current_extractions",
        "review_queue",
        "model_output",
    ):
        assert forbidden not in text


def test_v2_review_export_refuses_draft(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    workspace = load_annotation_workspace(truth_dir, source_dir)

    with pytest.raises(ValueError, match="Completa y valida"):
        build_ai_qa_review_package(
            workspace.truth,
            BOE_ID,
            title="Resolución sintética V2",
            publication_date="2099-02-01",
            source_text="Texto sintético",
        )


def test_action_and_secondary_evidence_are_disjoint_and_preserved(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    workspace = load_annotation_workspace(truth_dir, source_dir)
    before = (truth_dir / "evidence_passages.csv").read_bytes()

    primary = action_evidence_rows(
        workspace.truth,
        BOE_ID,
        action_key="action_1",
    )
    secondary = secondary_evidence_rows(workspace.truth, BOE_ID)

    assert len(primary) == 2
    assert primary["owner_type"].astype(str).unique().tolist() == [
        "administrative_action"
    ]
    assert set(primary["passage_text"].astype(str)) == {
        ACTION_EVIDENCE,
        SECOND_ACTION_EVIDENCE,
    }
    assert len(secondary) == 1
    assert secondary.iloc[0]["owner_type"] == "participant"
    assert secondary.iloc[0]["passage_text"] == SECONDARY_EVIDENCE
    assert (truth_dir / "evidence_passages.csv").read_bytes() == before


def test_action_evidence_requires_an_existing_action_in_the_ui(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    actions = pd.read_csv(
        truth_dir / "administrative_actions.csv",
        dtype="string",
        keep_default_na=False,
    )
    actions.iloc[0:0].to_csv(
        truth_dir / "administrative_actions.csv",
        index=False,
        lineterminator="\n",
    )
    evidence = pd.read_csv(
        truth_dir / "evidence_passages.csv",
        dtype="string",
        keep_default_na=False,
    )
    evidence = evidence.loc[
        ~evidence["owner_type"].astype(str).eq("administrative_action")
    ]
    evidence.to_csv(
        truth_dir / "evidence_passages.csv",
        index=False,
        lineterminator="\n",
    )
    load_truth(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))

    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()

    assert not app.exception
    assert any(
        control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
        and control.options == ["Añadir"]
        for control in app.segmented_control
    )
    assert not any(
        element.value.startswith("**Evidencias de `")
        for element in app.markdown
    )
    assert any(
        area.label.startswith("Evidencia literal de la actuación")
        and "evidence_passage/administrative_action/<nueva_clave>"
        in area.label
        for area in app.text_area
    )
    assert sum(
        button.label == "Guardar actuación y evidencias"
        for button in app.button
    ) == 1


def test_primary_dependency_messages_are_explicit(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    for table, spec in TABLE_SPECS.items():
        if table == "documents":
            continue
        pd.DataFrame(columns=spec.columns, dtype="string").to_csv(
            truth_dir / f"{table}.csv",
            index=False,
            lineterminator="\n",
        )
    load_truth(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))

    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    messages = [message.value for message in app.info]

    assert not app.exception
    assert any("Añade primero un evento" in message for message in messages)
    assert any("Añade primero un activo" in message for message in messages)
    assert not any(
        control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
        for control in app.segmented_control
    )


def test_action_evidence_still_requires_one_literal_continuous_passage(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    workspace = load_annotation_workspace(truth_dir, source_dir)
    source = workspace.source_documents.iloc[0]
    source_text = f"{source['titulo']}\n{source['texto_limpio']}"
    before = {path.name: path.read_bytes() for path in truth_dir.iterdir()}
    base_row = {
        **_common(),
        "owner_type": "administrative_action",
        "owner_key": "action_1",
    }

    with pytest.raises(TruthContractError, match="literal"):
        upsert_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {**base_row, "passage_text": "Resumen no literal de la actuación."},
            source_text=source_text,
        )
    with pytest.raises(TruthContractError, match="continuous"):
        upsert_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {
                **base_row,
                "passage_text": f"{ACTION_EVIDENCE} [...] {SECOND_ACTION_EVIDENCE}",
            },
            source_text=source_text,
        )
    assert before == {path.name: path.read_bytes() for path in truth_dir.iterdir()}


def test_new_scored_action_and_first_evidence_are_saved_together(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    truth = load_truth(truth_dir)
    action_key = next_key_for_table(
        truth,
        "administrative_actions",
        BOE_ID,
    )

    saved = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row(action_key),
        evidence_passage=ACTION_EVIDENCE,
        source_text=_source_text(truth_dir, source_dir),
    )

    assert action_key == "action_2"
    assert saved.tables["administrative_actions"]["action_key"].astype(str).eq(
        action_key
    ).sum() == 1
    created_evidence = action_evidence_rows(saved, BOE_ID, action_key=action_key)
    assert len(created_evidence) == 1
    assert created_evidence.iloc[0]["owner_key"] == action_key
    assert created_evidence.iloc[0]["passage_text"] == ACTION_EVIDENCE
    assert action_has_scored_evidence(saved, BOE_ID, action_key)
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"
    validate_document(truth_dir, BOE_ID, source_text=_source_text(truth_dir, source_dir))


def test_existing_action_1_action_2_add_generates_action_3_for_both_rows(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )

    saved = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage=SECOND_ACTION_EVIDENCE,
        source_text=source_text,
    )

    assert saved.tables["administrative_actions"]["action_key"].astype(str).tolist() == [
        "action_1",
        "action_2",
        "action_3",
    ]
    evidence = action_evidence_rows(saved, BOE_ID, action_key="action_3")
    assert len(evidence) == 1
    assert evidence.iloc[0]["owner_key"] == "action_3"
    assert evidence.iloc[0]["passage_text"] == SECOND_ACTION_EVIDENCE


@pytest.mark.parametrize("placeholder", ["pending", "<NEW_ACTION_KEY>"])
def test_annotation_write_boundary_rejects_reserved_action_key_placeholders(
    v2_annotation_workspace: tuple[Path, Path],
    placeholder: str,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="placeholder"):
        upsert_truth_row(
            truth_dir,
            "administrative_actions",
            BOE_ID,
            _action_row(placeholder),
            source_text=_source_text(truth_dir, source_dir),
        )

    assert _workspace_bytes(truth_dir) == before


def test_annotation_write_boundary_rejects_pending_evidence_owner_key(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="placeholder"):
        upsert_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {
                **_common(),
                "owner_type": "administrative_action",
                "owner_key": "pending",
                "passage_text": ACTION_EVIDENCE,
            },
            source_text=_source_text(truth_dir, source_dir),
        )

    assert _workspace_bytes(truth_dir) == before


def test_sparse_action_keys_use_existing_max_plus_one_policy(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    source_text = _source_text(truth_dir, source_dir)
    upsert_truth_row(
        truth_dir,
        "administrative_actions",
        BOE_ID,
        _action_row(
            "action_3",
            applicability="not_applicable",
            adjudication="excluded_from_scoring",
        ),
        source_text=source_text,
    )

    saved = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )

    assert saved.tables["administrative_actions"]["action_key"].astype(str).tolist() == [
        "action_1",
        "action_3",
        "action_4",
    ]
    assert action_evidence_rows(saved, BOE_ID, action_key="action_4").shape[0] == 1


def test_editing_existing_action_does_not_allocate_a_new_key(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    truth = load_truth(truth_dir)
    action = truth.tables["administrative_actions"].iloc[0].to_dict()

    def refuse_allocation(*args: object, **kwargs: object) -> str:
        raise AssertionError("Editing must not allocate an action key.")

    monkeypatch.setattr(annotation_module, "next_key_for_table", refuse_allocation)
    saved = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action,
        evidence_passage=None,
        original_key={"action_key": "action_1"},
        source_text=_source_text(truth_dir, source_dir),
    )

    assert saved.tables["administrative_actions"]["action_key"].astype(str).tolist() == [
        "action_1"
    ]


def test_multiple_sequential_additions_allocate_action_3_action_4_action_5(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )
    for passage in (ACTION_EVIDENCE, SECOND_ACTION_EVIDENCE, ACTION_EVIDENCE):
        saved = upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("pending"),
            evidence_passage=passage,
            source_text=source_text,
        )

    keys = saved.tables["administrative_actions"]["action_key"].astype(str).tolist()
    assert keys == ["action_1", "action_2", "action_3", "action_4", "action_5"]
    assert len(keys) == len(set(keys))
    for action_key in ("action_3", "action_4", "action_5"):
        evidence = action_evidence_rows(saved, BOE_ID, action_key=action_key)
        assert len(evidence) == 1
        assert evidence.iloc[0]["owner_key"] == action_key


def test_action_edit_preserves_key_and_evidence_and_downgrades_complete(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    before = load_truth(truth_dir)
    action = before.tables["administrative_actions"].iloc[0].to_dict()
    action["expected_decision"] = "denegado"
    evidence_before = action_evidence_rows(before, BOE_ID, action_key="action_1")

    saved = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action,
        evidence_passage=None,
        original_key={"action_key": "action_1"},
        source_text=_source_text(truth_dir, source_dir),
    )

    edited = saved.tables["administrative_actions"].iloc[0]
    assert edited["action_key"] == "action_1"
    assert edited["expected_decision"] == "denegado"
    assert action_evidence_rows(
        saved, BOE_ID, action_key="action_1"
    ).equals(evidence_before)
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_action_and_complete_evidence_set_are_replaced_in_one_transaction(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    source_text = _source_text(truth_dir, source_dir)
    other_boe = "BOE-A-2099-999"
    for table in TABLE_SPECS:
        frame = pd.read_csv(
            truth_dir / f"{table}.csv",
            dtype="string",
            keep_default_na=False,
        )
        other_rows = frame.loc[
            frame["identificador_boe"].astype(str).eq(BOE_ID)
        ].copy()
        other_rows.loc[:, "identificador_boe"] = other_boe
        if table == "documents":
            other_rows.loc[:, "annotation_status"] = "draft"
        pd.concat([frame, other_rows], ignore_index=True).to_csv(
            truth_dir / f"{table}.csv",
            index=False,
            lineterminator="\n",
        )
    before = load_truth(truth_dir)
    other_before = {
        table: frame.loc[
            frame["identificador_boe"].astype(str).eq(other_boe)
        ].reset_index(drop=True)
        for table, frame in before.tables.items()
    }
    action = before.tables["administrative_actions"].loc[
        before.tables["administrative_actions"]["identificador_boe"]
        .astype(str)
        .eq(BOE_ID)
    ].iloc[0].to_dict()
    action["expected_decision"] = "denegado"
    evidence_metadata = action_evidence_rows(
        before, BOE_ID, action_key="action_1"
    ).iloc[0].to_dict()

    saved = upsert_action_with_evidence_set(
        truth_dir,
        BOE_ID,
        action,
        evidence_rows=[
            {
                **evidence_metadata,
                "passage_text": SECOND_ACTION_EVIDENCE,
            }
        ],
        original_key={"action_key": "action_1"},
        source_text=source_text,
    )

    selected_action = saved.tables["administrative_actions"].loc[
        saved.tables["administrative_actions"]["identificador_boe"]
        .astype(str)
        .eq(BOE_ID)
    ].iloc[0]
    assert selected_action["action_key"] == "action_1"
    assert selected_action["expected_decision"] == "denegado"
    selected_evidence = action_evidence_rows(
        saved, BOE_ID, action_key="action_1"
    )
    assert selected_evidence["passage_text"].astype(str).tolist() == [
        SECOND_ACTION_EVIDENCE
    ]
    assert selected_evidence.iloc[0]["applicability"] == (
        evidence_metadata["applicability"]
    )
    assert selected_evidence.iloc[0]["adjudication"] == (
        evidence_metadata["adjudication"]
    )
    for table, frame in saved.tables.items():
        other_after = frame.loc[
            frame["identificador_boe"].astype(str).eq(other_boe)
        ].reset_index(drop=True)
        assert other_after.equals(other_before[table])


def test_invalid_action_evidence_set_preserves_every_workspace_byte(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    truth = load_truth(truth_dir)
    action = truth.tables["administrative_actions"].iloc[0].to_dict()
    action["expected_decision"] = "denegado"
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="continuous literal"):
        upsert_action_with_evidence_set(
            truth_dir,
            BOE_ID,
            action,
            evidence_rows=[{"passage_text": "Paráfrasis inexistente"}],
            original_key={"action_key": "action_1"},
            source_text=_source_text(truth_dir, source_dir),
        )

    assert _workspace_bytes(truth_dir) == before


def test_action_delete_removes_only_direct_evidence_and_targets_atomically(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    upsert_truth_row(
        truth_dir,
        "action_targets",
        BOE_ID,
        {
            **_common(),
            "event_key": "event_1",
            "action_key": "action_1",
            "target_type": "generation_asset",
            "target_truth_key": "asset_1",
        },
        source_text=_source_text(truth_dir, source_dir),
    )
    before = _workspace_bytes(truth_dir)
    truth = load_truth(truth_dir, require_complete=True)
    impact = action_deletion_impact(truth, BOE_ID, "action_1")

    saved = delete_administrative_action(truth_dir, BOE_ID, "action_1")

    assert impact.evidence_count == 2
    assert impact.target_count == 1
    assert saved.tables["administrative_actions"].empty
    assert action_evidence_rows(saved, BOE_ID, action_key="action_1").empty
    assert saved.tables["action_targets"].empty
    assert saved.tables["events"].shape[0] == 1
    assert saved.tables["generation_assets"].shape[0] == 1
    assert saved.tables["locations"].shape[0] == 1
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"
    after = _workspace_bytes(truth_dir)
    assert {
        name for name in before if before[name] != after[name]
    } == {
        "documents.csv",
        "administrative_actions.csv",
        "action_targets.csv",
        "evidence_passages.csv",
    }


def test_event_delete_lists_children_and_preserves_workspace(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    truth = load_truth(truth_dir)
    key = {"event_key": "event_1"}
    dependencies = deletion_dependencies(truth, "events", BOE_ID, key)
    before = _workspace_bytes(truth_dir)

    assert "generation_asset/asset_1" in dependencies
    assert "administrative_action/action_1" in dependencies
    assert "location/location_1" in dependencies
    with pytest.raises(TruthContractError, match="primero elimina o reasigna") as error:
        delete_truth_row(
            truth_dir,
            "events",
            BOE_ID,
            key,
            source_text=_source_text(truth_dir, source_dir),
        )

    assert "generation_asset/asset_1" in str(error.value)
    assert "administrative_action/action_1" in str(error.value)
    assert _workspace_bytes(truth_dir) == before


def test_asset_delete_lists_primary_and_secondary_references(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    source_text = _source_text(truth_dir, source_dir)
    upsert_truth_row(
        truth_dir,
        "associated_components",
        BOE_ID,
        {
            **_common(),
            "event_key": "event_1",
            "component_key": "component_1",
            "names_json": "[]",
            "description_raw": "Componente sintético",
            "expected_component_type": "sistema_evacuacion",
            "related_asset_keys_json": '["asset_1"]',
        },
        source_text=source_text,
    )
    upsert_truth_row(
        truth_dir,
        "technical_mentions",
        BOE_ID,
        {
            **_common(),
            "event_key": "event_1",
            "owner_type": "generation_asset",
            "owner_key": "asset_1",
            "technical_key": "technical_1",
            "expected_attribute_type": "potencia_instalada",
            "expected_value_raw": "25 MW",
        },
        source_text=source_text,
    )
    upsert_truth_row(
        truth_dir,
        "action_targets",
        BOE_ID,
        {
            **_common(),
            "event_key": "event_1",
            "action_key": "action_1",
            "target_type": "generation_asset",
            "target_truth_key": "asset_1",
        },
        source_text=source_text,
    )
    upsert_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            **_common(),
            "owner_type": "generation_asset",
            "owner_key": "asset_1",
            "passage_text": "La planta fotovoltaica Planta V2 se sitúa en Villa V2.",
        },
        source_text=source_text,
    )
    truth = load_truth(truth_dir)
    dependencies = deletion_dependencies(
        truth,
        "generation_assets",
        BOE_ID,
        {"asset_key": "asset_1"},
    )
    before = _workspace_bytes(truth_dir)

    assert (
        "administrative_action/action_1."
        "expected_affected_generation_asset_keys_json"
    ) in dependencies
    assert "associated_component/component_1.related_asset_keys_json" in dependencies
    assert "technical_mention/technical_1" in dependencies
    assert "evidence_passage/generation_asset/asset_1" in dependencies
    assert "action_target/action_1.target=generation_asset:asset_1" in dependencies
    with pytest.raises(TruthContractError, match="generation_asset/asset_1"):
        delete_truth_row(
            truth_dir,
            "generation_assets",
            BOE_ID,
            {"asset_key": "asset_1"},
            source_text=source_text,
        )
    assert _workspace_bytes(truth_dir) == before


def test_action_evidence_edit_revalidates_literal_and_downgrades_complete(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    saved = upsert_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": SECONDARY_EVIDENCE,
        },
        original_key={
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": ACTION_EVIDENCE,
        },
        source_text=source_text,
    )

    passages = action_evidence_rows(saved, BOE_ID, action_key="action_1")
    assert set(passages["passage_text"].astype(str)) == {
        SECOND_ACTION_EVIDENCE,
        SECONDARY_EVIDENCE,
    }
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_duplicate_action_evidence_fails_without_writing(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    before = _workspace_bytes(truth_dir)
    with pytest.raises(TruthContractError, match="duplicate truth keys"):
        upsert_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {
                **_common(),
                "owner_type": "administrative_action",
                "owner_key": "action_1",
                "passage_text": ACTION_EVIDENCE,
            },
            source_text=_source_text(truth_dir, source_dir),
        )
    assert _workspace_bytes(truth_dir) == before


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Evidence is not a continuous literal passage from this BOE source.",
            "pasaje continuo y literal",
        ),
        (
            "evidence_passages contains duplicate truth keys.",
            "Selecciona Editar",
        ),
        (
            "An action and its affected assets must belong to the same event.",
            "mismo evento",
        ),
        (
            "No se puede eliminar event/event_1; primero reasigna sus referencias.",
            "event/event_1",
        ),
    ],
)
def test_operator_validation_feedback_translates_without_revalidating(
    v2_annotation_workspace: tuple[Path, Path],
    raw: str,
    expected: str,
) -> None:
    truth_dir, _ = v2_annotation_workspace
    feedback = validation_error_feedback(
        TruthContractError(raw),
        load_truth(truth_dir),
        BOE_ID,
    )
    assert expected in feedback.message


@pytest.mark.parametrize(
    ("table", "field", "value"),
    [
        ("events", "event_label", "Planta V2 editada"),
        ("generation_assets", "names_json", '["Planta V2","Alias V2"]'),
        ("administrative_actions", "expected_decision", "denegado"),
        ("locations", "location_name_raw", "Villa V2 editada"),
    ],
)
def test_each_primary_entity_edit_downgrades_complete_to_draft(
    v2_annotation_workspace: tuple[Path, Path],
    table: str,
    field: str,
    value: str,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    truth = load_truth(truth_dir)
    row = truth.tables[table].iloc[0].to_dict()
    row[field] = value
    if table == "administrative_actions":
        saved = upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            row,
            evidence_passage=None,
            original_key={"action_key": "action_1"},
            source_text=_source_text(truth_dir, source_dir),
        )
    else:
        saved = upsert_truth_row(
            truth_dir,
            table,
            BOE_ID,
            row,
            original_key={
                column: str(row[column])
                for column in TABLE_SPECS[table].key_columns
                if column != "identificador_boe"
            },
            source_text=_source_text(truth_dir, source_dir),
        )
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_scope_change_downgrades_complete_but_noop_primary_edit_does_not(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    truth = load_truth(truth_dir)
    action = truth.tables["administrative_actions"].iloc[0].to_dict()
    unchanged = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action,
        evidence_passage=None,
        original_key={"action_key": "action_1"},
        source_text=source_text,
    )
    assert unchanged.tables["documents"].iloc[0]["annotation_status"] == "complete"

    changed = update_document_scope(
        truth_dir,
        BOE_ID,
        scope_applicability="applicable",
        scope_adjudication="scored_truth",
        expected_document_scope="generation_project_specific",
        annotation_notes="Alcance revisado",
        source_text=source_text,
    )
    assert changed.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_secondary_edit_does_not_downgrade_complete(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    truth = load_truth(truth_dir)
    participant = truth.tables["participants"].iloc[0].to_dict()
    participant["participant_name_raw"] = "Promotora V2 editada, SL"
    saved = upsert_truth_row(
        truth_dir,
        "participants",
        BOE_ID,
        participant,
        original_key={"participant_key": "participant_1"},
        source_text=_source_text(truth_dir, source_dir),
    )
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "complete"


def test_new_scored_action_without_evidence_is_rejected_before_write(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="misma operación"):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("action_2"),
            evidence_passage="",
            source_text=_source_text(truth_dir, source_dir),
        )

    assert _workspace_bytes(truth_dir) == before


@pytest.mark.parametrize(
    ("passage", "message"),
    [
        ("Resumen no literal de la actuación.", "literal"),
        (f"{ACTION_EVIDENCE} [...] {SECOND_ACTION_EVIDENCE}", "continuous"),
    ],
)
def test_invalid_first_evidence_rejects_action_and_evidence_together(
    v2_annotation_workspace: tuple[Path, Path],
    passage: str,
    message: str,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match=message):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("action_2"),
            evidence_passage=passage,
            source_text=_source_text(truth_dir, source_dir),
        )

    assert _workspace_bytes(truth_dir) == before


def test_staged_action_validation_failure_preserves_original_workspace_bytes(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="unknown affected asset"):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("action_2", affected_assets='["asset_999"]'),
            evidence_passage=ACTION_EVIDENCE,
            source_text=_source_text(truth_dir, source_dir),
        )

    assert _workspace_bytes(truth_dir) == before


def test_action_evidence_publish_failure_restores_original_workspace_bytes(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    before = _workspace_bytes(truth_dir)
    real_replace = annotation_module.os.replace
    failed = False

    def fail_candidate_publication(source: object, destination: object) -> None:
        nonlocal failed
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            not failed
            and ".annotation-staging-" in source_path.name
            and destination_path == truth_dir.absolute()
        ):
            failed = True
            raise OSError("synthetic publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(annotation_module.os, "replace", fail_candidate_publication)

    with pytest.raises(OSError, match="synthetic publication failure"):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("action_2"),
            evidence_passage=ACTION_EVIDENCE,
            source_text=_source_text(truth_dir, source_dir),
        )

    assert failed
    assert _workspace_bytes(truth_dir) == before
    load_truth(truth_dir, require_complete=True)


def test_existing_action_accepts_multiple_distinct_evidence_passages(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("action_2"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )

    saved = upsert_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": "action_2",
            "passage_text": SECOND_ACTION_EVIDENCE,
        },
        source_text=source_text,
    )

    evidence = action_evidence_rows(saved, BOE_ID, action_key="action_2")
    assert set(evidence["passage_text"].astype(str)) == {
        ACTION_EVIDENCE,
        SECOND_ACTION_EVIDENCE,
    }


def test_deleting_last_scored_action_evidence_fails_closed(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("action_2"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )
    before = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="última evidencia"):
        delete_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {
                "owner_type": "administrative_action",
                "owner_key": "action_2",
                "passage_text": ACTION_EVIDENCE,
            },
            source_text=source_text,
        )

    assert _workspace_bytes(truth_dir) == before


def test_deleting_one_of_multiple_scored_action_evidences_still_succeeds(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)

    saved = delete_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": ACTION_EVIDENCE,
        },
        source_text=_source_text(truth_dir, source_dir),
    )

    evidence = action_evidence_rows(saved, BOE_ID, action_key="action_1")
    assert evidence["passage_text"].astype(str).tolist() == [SECOND_ACTION_EVIDENCE]
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"
    validate_document(truth_dir, BOE_ID, source_text=_source_text(truth_dir, source_dir))


def test_non_scored_action_stays_optional_and_scored_transition_is_atomic(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    non_scored = _action_row(
        "action_2",
        applicability="not_applicable",
        adjudication="excluded_from_scoring",
    )
    saved = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        non_scored,
        evidence_passage="",
        source_text=source_text,
    )
    assert action_evidence_rows(saved, BOE_ID, action_key="action_2").empty
    before_transition = _workspace_bytes(truth_dir)

    with pytest.raises(TruthContractError, match="misma operación"):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("action_2"),
            evidence_passage="",
            original_key={"action_key": "action_2"},
            source_text=source_text,
        )
    assert _workspace_bytes(truth_dir) == before_transition

    transitioned = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("action_2"),
        evidence_passage=ACTION_EVIDENCE,
        original_key={"action_key": "action_2"},
        source_text=source_text,
    )
    assert action_has_scored_evidence(transitioned, BOE_ID, "action_2")
    assert transitioned.tables["documents"].iloc[0]["annotation_status"] == "draft"
    validate_document(truth_dir, BOE_ID, source_text=source_text)


def test_end_to_end_relevant_operator_lifecycle(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _reset_to_unscoped_empty_truth(truth_dir)
    source_text = _source_text(truth_dir, source_dir)

    update_document_scope(
        truth_dir,
        BOE_ID,
        scope_applicability="applicable",
        scope_adjudication="scored_truth",
        expected_document_scope="generation_project_specific",
        annotation_notes="",
        source_text=source_text,
    )
    event = {
        **_common(),
        "event_key": "event_1",
        "event_label": "Proyecto V2",
    }
    upsert_truth_row(truth_dir, "events", BOE_ID, event, source_text=source_text)
    event["event_label"] = "Proyecto V2 publicado"
    upsert_truth_row(
        truth_dir,
        "events",
        BOE_ID,
        event,
        original_key={"event_key": "event_1"},
        source_text=source_text,
    )
    asset = {
        **_common(),
        "event_key": "event_1",
        "asset_key": "asset_1",
        "names_json": '["Planta V2"]',
        "expected_generation_type": "fotovoltaica",
    }
    upsert_truth_row(
        truth_dir, "generation_assets", BOE_ID, asset, source_text=source_text
    )
    asset["names_json"] = '["Planta V2","Planta V2 publicada"]'
    asset["expected_generation_type"] = "eolica"
    upsert_truth_row(
        truth_dir,
        "generation_assets",
        BOE_ID,
        asset,
        original_key={"asset_key": "asset_1"},
        source_text=source_text,
    )
    created = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )
    action = created.tables["administrative_actions"].iloc[0].to_dict()
    action["expected_decision"] = "favorable"
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action,
        evidence_passage=None,
        original_key={"action_key": "action_1"},
        source_text=source_text,
    )
    upsert_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            **_common(),
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": SECOND_ACTION_EVIDENCE,
        },
        source_text=source_text,
    )
    delete_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": SECOND_ACTION_EVIDENCE,
        },
        source_text=source_text,
    )
    for location_key, name, level in (
        ("location_1", "Villa V2", "municipio"),
        ("location_2", "Provincia V2", "provincia"),
    ):
        upsert_truth_row(
            truth_dir,
            "locations",
            BOE_ID,
            {
                **_common(),
                "event_key": "event_1",
                "location_key": location_key,
                "location_name_raw": name,
                "expected_location_level": level,
            },
            source_text=source_text,
        )
    validate_document(truth_dir, BOE_ID, source_text=source_text)
    completed = mark_document_complete(
        truth_dir, BOE_ID, source_text=source_text
    )
    assert completed.tables["documents"].iloc[0]["annotation_status"] == "complete"

    action = completed.tables["administrative_actions"].iloc[0].to_dict()
    action["expected_decision"] = "denegado"
    edited = upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action,
        evidence_passage=None,
        original_key={"action_key": "action_1"},
        source_text=source_text,
    )
    assert edited.tables["documents"].iloc[0]["annotation_status"] == "draft"
    validate_document(truth_dir, BOE_ID, source_text=source_text)
    completed = mark_document_complete(
        truth_dir, BOE_ID, source_text=source_text
    )
    source = load_annotation_workspace(truth_dir, source_dir).source_documents.iloc[0]
    package = build_ai_qa_review_package(
        completed,
        BOE_ID,
        title=str(source["titulo"]),
        publication_date="2099-02-01",
        source_text=str(source["texto_limpio"]),
    )
    assert b"administrative_action/action_1.expected_decision" in package
    assert b"denegado" in package
    assert package.count(SECOND_ACTION_EVIDENCE.encode()) == 1

    upsert_truth_row(
        truth_dir,
        "action_targets",
        BOE_ID,
        {
            **_common(),
            "event_key": "event_1",
            "action_key": "action_1",
            "target_type": "generation_asset",
            "target_truth_key": "asset_1",
        },
        source_text=source_text,
    )
    deleted = delete_administrative_action(truth_dir, BOE_ID, "action_1")
    assert deleted.tables["documents"].iloc[0]["annotation_status"] == "draft"
    assert deleted.tables["administrative_actions"].empty
    assert action_evidence_rows(deleted, BOE_ID).empty
    assert deleted.tables["action_targets"].empty


def test_end_to_end_non_relevant_operator_lifecycle(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _reset_to_unscoped_empty_truth(truth_dir)
    source_text = _source_text(truth_dir, source_dir)
    updated = update_document_scope(
        truth_dir,
        BOE_ID,
        scope_applicability="applicable",
        scope_adjudication="scored_truth",
        expected_document_scope="not_relevant_for_generation_projects",
        annotation_notes="No relevante según revisión humana",
        source_text=source_text,
    )
    assert updated.tables["events"].empty
    validate_document(truth_dir, BOE_ID, source_text=source_text)
    completed = mark_document_complete(
        truth_dir, BOE_ID, source_text=source_text
    )
    source = load_annotation_workspace(truth_dir, source_dir).source_documents.iloc[0]
    package = build_ai_qa_review_package(
        completed,
        BOE_ID,
        title=str(source["titulo"]),
        publication_date="2099-02-01",
        source_text=str(source["texto_limpio"]),
    )
    assert b"not_relevant_for_generation_projects" in package
    assert b"No rows for this BOE" not in package
    assert completed.tables["documents"].iloc[0]["annotation_status"] == "complete"


def test_end_to_end_multi_action_keys_edits_and_delete_are_stable(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    source_text = _source_text(truth_dir, source_dir)
    action_2 = _action_row("pending")
    action_2["temporal_status"] = "historical_antecedent"
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action_2,
        evidence_passage=ACTION_EVIDENCE,
        source_text=source_text,
    )
    action_3 = _action_row("pending")
    action_3["temporal_status"] = "historical_antecedent"
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        action_3,
        evidence_passage=SECOND_ACTION_EVIDENCE,
        source_text=source_text,
    )
    truth = load_truth(truth_dir)
    edit = truth.tables["administrative_actions"].loc[
        truth.tables["administrative_actions"]["action_key"].astype(str).eq("action_2")
    ].iloc[0].to_dict()
    edit["expected_decision"] = "denegado"
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        edit,
        evidence_passage=None,
        original_key={"action_key": "action_2"},
        source_text=source_text,
    )
    saved = delete_administrative_action(truth_dir, BOE_ID, "action_3")

    assert saved.tables["administrative_actions"]["action_key"].astype(str).tolist() == [
        "action_1",
        "action_2",
    ]
    assert action_evidence_rows(saved, BOE_ID, action_key="action_3").empty
    assert action_evidence_rows(saved, BOE_ID, action_key="action_2").shape[0] == 1
    assert next_key_for_table(saved, "administrative_actions", BOE_ID) == "action_3"


def test_qa_export_reflects_current_edits_and_omits_deleted_action(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    source_text = _source_text(truth_dir, source_dir)
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage="Tiene 25 MW de potencia instalada.",
        source_text=source_text,
    )
    truth = load_truth(truth_dir)
    event = truth.tables["events"].iloc[0].to_dict()
    event["event_label"] = "Etiqueta editada para QA"
    upsert_truth_row(
        truth_dir,
        "events",
        BOE_ID,
        event,
        original_key={"event_key": "event_1"},
        source_text=source_text,
    )
    delete_administrative_action(truth_dir, BOE_ID, "action_2")
    validate_document(truth_dir, BOE_ID, source_text=source_text)
    completed = mark_document_complete(
        truth_dir, BOE_ID, source_text=source_text
    )
    source = load_annotation_workspace(truth_dir, source_dir).source_documents.iloc[0]

    package = build_ai_qa_review_package(
        completed,
        BOE_ID,
        title=str(source["titulo"]),
        publication_date="2099-02-01",
        source_text=str(source["texto_limpio"]),
    )

    assert b"Etiqueta editada para QA" in package
    assert b"administrative_action/action_2" not in package
    assert package.count(b"Tiene 25 MW de potencia instalada.") == 1
    assert b"## Datos secundarios / diagn\xc3\xb3sticos" in package


def test_end_to_end_dependency_failures_preserve_bytes(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    source_text = _source_text(truth_dir, source_dir)
    for table, key, message in (
        ("events", {"event_key": "event_1"}, "reasigna"),
        ("generation_assets", {"asset_key": "asset_1"}, "reasigna"),
    ):
        before = _workspace_bytes(truth_dir)
        with pytest.raises(TruthContractError, match=message):
            delete_truth_row(
                truth_dir,
                table,
                BOE_ID,
                key,
                source_text=source_text,
            )
        assert _workspace_bytes(truth_dir) == before

    before = _workspace_bytes(truth_dir)
    with pytest.raises(TruthContractError, match="literal"):
        upsert_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {
                **_common(),
                "owner_type": "administrative_action",
                "owner_key": "action_1",
                "passage_text": "Texto inventado",
            },
            source_text=source_text,
        )
    assert _workspace_bytes(truth_dir) == before

    delete_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ID,
        {
            "owner_type": "administrative_action",
            "owner_key": "action_1",
            "passage_text": SECOND_ACTION_EVIDENCE,
        },
        source_text=source_text,
    )
    before = _workspace_bytes(truth_dir)
    with pytest.raises(TruthContractError, match="última evidencia"):
        delete_truth_row(
            truth_dir,
            "evidence_passages",
            BOE_ID,
            {
                "owner_type": "administrative_action",
                "owner_key": "action_1",
                "passage_text": ACTION_EVIDENCE,
            },
            source_text=source_text,
        )
    assert _workspace_bytes(truth_dir) == before

    with pytest.raises(TruthContractError, match="unknown affected asset"):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("pending", affected_assets='["asset_999"]'),
            evidence_passage=ACTION_EVIDENCE,
            source_text=source_text,
        )
    assert _workspace_bytes(truth_dir) == before


def test_new_action_form_integrates_evidence_and_one_persistence_button(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    action_mode = next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )

    action_mode.set_value("Añadir").run()

    assert not app.exception
    assert any(
        area.label.startswith("Evidencia literal de la actuación")
        and "evidence_passage/administrative_action/<nueva_clave>"
        in area.label
        and area.value == ""
        for area in app.text_area
    )
    assert any(
        "La clave real de la actuación se genera una sola vez"
        in caption.value
        for caption in app.caption
    )
    assert not any("Propietario" in widget.label for widget in app.selectbox)
    assert sum(
        button.label == "Guardar actuación y evidencias"
        for button in app.button
    ) == 1


def test_new_scored_action_is_saved_with_evidence_through_streamlit_form(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    upsert_action_with_initial_evidence(
        truth_dir,
        BOE_ID,
        _action_row("pending"),
        evidence_passage=ACTION_EVIDENCE,
        source_text=_source_text(truth_dir, source_dir),
    )
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    action_mode = next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )
    action_mode.set_value("Añadir").run()

    selections = {
        "Evento · administrative_action/<nueva_clave>.event_key": "event_1",
        "Tipo de actuación · administrative_action/<nueva_clave>.expected_action_type": (
            "autorizacion_administrativa_previa"
        ),
        "Decisión · administrative_action/<nueva_clave>.expected_decision": "autorizado",
        "Es modificación · administrative_action/<nueva_clave>.expected_is_modification": (
            "false"
        ),
        "Temporalidad · administrative_action/<nueva_clave>.temporal_status": "current",
        "Aplicabilidad · administrative_action/<nueva_clave>.applicability": "applicable",
        "Adjudicación · administrative_action/<nueva_clave>.adjudication": "scored_truth",
    }
    for label, value in selections.items():
        next(widget for widget in app.selectbox if widget.label == label).set_value(value)
    next(
        widget
        for widget in app.multiselect
        if widget.label
        == "Activos afectados · administrative_action/<nueva_clave>."
        "expected_affected_generation_asset_keys_json"
    ).set_value(["asset_1"])
    next(
        area
        for area in app.text_area
        if area.label.startswith("Evidencia literal de la actuación")
    ).set_value(ACTION_EVIDENCE)

    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert not app.error
    saved = load_truth(truth_dir)
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"
    assert saved.tables["administrative_actions"]["action_key"].astype(str).eq(
        "action_3"
    ).sum() == 1
    evidence = action_evidence_rows(saved, BOE_ID, action_key="action_3")
    assert len(evidence) == 1
    assert evidence.iloc[0]["passage_text"] == ACTION_EVIDENCE


def test_new_action_adds_second_draft_passage_without_losing_pending_fields(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    ).set_value("Añadir").run()
    _fill_new_action_form(app)
    _action_evidence_inputs(app, "<nueva_clave>")[0].set_value(
        ACTION_EVIDENCE
    )

    next(
        button for button in app.button if button.label == "Agregar otro pasaje"
    ).click().run()

    assert not app.exception
    assert next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/<nueva_clave>.expected_decision"
    ).value == "autorizado"
    passages = _action_evidence_inputs(app, "<nueva_clave>")
    assert [widget.value for widget in passages] == [ACTION_EVIDENCE, ""]
    passages[1].set_value(SECOND_ACTION_EVIDENCE)
    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert not app.error
    saved = load_truth(truth_dir)
    assert saved.tables["administrative_actions"]["action_key"].astype(
        str
    ).tolist() == ["action_1", "action_2"]
    assert action_evidence_rows(
        saved, BOE_ID, action_key="action_2"
    )["passage_text"].astype(str).tolist() == [
        ACTION_EVIDENCE,
        SECOND_ACTION_EVIDENCE,
    ]


def test_scored_action_without_evidence_is_rejected_without_writing(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    ).set_value("Añadir").run()
    _fill_new_action_form(app)

    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert any("necesita al menos un pasaje literal" in error.value for error in app.error)
    assert _workspace_bytes(truth_dir) == before


def test_existing_action_edit_is_exposed_and_persists_through_streamlit(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    action_mode = next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )

    assert action_mode.options == ["Editar", "Añadir", "Eliminar"]
    assert action_mode.value == "Editar"
    row_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_edit_administrative_actions_{BOE_ID}_False_all"
    )
    assert row_selector.options == ["Actuación administrativa · action_1"]
    decision = next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    )
    decision.set_value("denegado")
    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert any(
        "vuelve a borrador" in message.value for message in app.success
    )
    saved = load_truth(truth_dir)
    action = saved.tables["administrative_actions"].iloc[0]
    assert action["action_key"] == "action_1"
    assert action["expected_decision"] == "denegado"
    assert action_evidence_rows(saved, BOE_ID, action_key="action_1").shape[0] == 2
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_edit_action_and_its_only_evidence_are_saved_together(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _keep_only_action_evidence(truth_dir, ACTION_EVIDENCE)
    _mark_complete(truth_dir)
    before = load_truth(truth_dir)
    evidence_before = action_evidence_rows(
        before, BOE_ID, action_key="action_1"
    ).iloc[0]
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    ).set_value("denegado")
    evidence_input = _action_evidence_inputs(app, "action_1")
    assert [widget.value for widget in evidence_input] == [ACTION_EVIDENCE]
    evidence_input[0].set_value(SECOND_ACTION_EVIDENCE)

    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert not app.error
    saved = load_truth(truth_dir)
    action = saved.tables["administrative_actions"].iloc[0]
    assert action["action_key"] == "action_1"
    assert action["expected_decision"] == "denegado"
    evidence = action_evidence_rows(saved, BOE_ID, action_key="action_1")
    assert evidence["passage_text"].astype(str).tolist() == [
        SECOND_ACTION_EVIDENCE
    ]
    assert evidence.iloc[0]["applicability"] == evidence_before["applicability"]
    assert evidence.iloc[0]["adjudication"] == evidence_before["adjudication"]
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_invalid_integrated_evidence_keeps_action_and_passages_unwritten(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    ).set_value("denegado")
    inputs = _action_evidence_inputs(app, "action_1")
    inputs[0].set_value("Paráfrasis inexistente")

    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert any("No se guardó ningún cambio" in error.value for error in app.error)
    assert next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    ).value == "denegado"
    assert _action_evidence_inputs(app, "action_1")[0].value == (
        "Paráfrasis inexistente"
    )
    assert _workspace_bytes(truth_dir) == before


def test_removing_only_required_evidence_is_draft_only_and_save_fails_closed(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _keep_only_action_evidence(truth_dir, ACTION_EVIDENCE)
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    ).set_value("denegado")

    next(
        button for button in app.button if button.label == "Retirar pasaje 1"
    ).click().run()

    assert not app.exception
    assert _action_evidence_inputs(app, "action_1") == []
    assert next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    ).value == "denegado"
    assert _workspace_bytes(truth_dir) == before
    next(
        button
        for button in app.button
        if button.label == "Guardar actuación y evidencias"
    ).click().run()

    assert not app.exception
    assert any("necesita al menos un pasaje literal" in error.value for error in app.error)
    assert _workspace_bytes(truth_dir) == before


def test_action_edit_selection_always_rehydrates_the_selected_persisted_row(
    v2_multirow_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_multirow_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    row_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_edit_administrative_actions_{BOE_ID}_False_all"
    )

    expected = (
        (
            "action_1",
            "declaracion_utilidad_publica",
            "declarado",
            "false",
        ),
        (
            "action_2",
            "autorizacion_administrativa_previa",
            "autorizado",
            "false",
        ),
        (
            "action_3",
            "autorizacion_administrativa_previa",
            "autorizado",
            "true",
        ),
        (
            "action_1",
            "declaracion_utilidad_publica",
            "declarado",
            "false",
        ),
    )
    for position, (action_key, action_type, decision, modification) in enumerate(
        expected
    ):
        row_selector = next(
            widget
            for widget in app.selectbox
            if widget.key
            == f"v2_edit_administrative_actions_{BOE_ID}_False_all"
        )
        row_selector.set_value(
            f"Actuación administrativa · {action_key}"
        ).run()
        values = {
            widget.label: widget.value
            for widget in app.selectbox
            if f"administrative_action/{action_key}." in widget.label
        }
        assert values[
            f"Tipo de actuación · administrative_action/{action_key}."
            "expected_action_type"
        ] == action_type
        assert values[
            f"Decisión · administrative_action/{action_key}.expected_decision"
        ] == decision
        assert values[
            f"Es modificación · administrative_action/{action_key}."
            "expected_is_modification"
        ] == modification

        if action_key == "action_2":
            assert values[
                "Evento · administrative_action/action_2.event_key"
            ] == "event_2"
            assert values[
                "Temporalidad · administrative_action/action_2.temporal_status"
            ] == "historical_antecedent"
            assert values[
                "Aplicabilidad · administrative_action/action_2.applicability"
            ] == "applicable"
            assert values[
                "Adjudicación · administrative_action/action_2.adjudication"
            ] == "scored_truth"
            assert next(
                widget
                for widget in app.multiselect
                if "administrative_action/action_2."
                "expected_affected_generation_asset_keys_json" in widget.label
            ).value == ["asset_2"]
            assert next(
                widget
                for widget in app.text_area
                if widget.label
                == "Notas de anotación · administrative_action/action_2."
                "annotation_notes"
            ).value == "Notas persistidas de action_2"
            assert not any(
                widget.label.startswith("Evidencia literal de la actuación")
                and widget.value == ""
                for widget in app.text_area
            )
        elif action_key == "action_3":
            assert any(
                widget.label.startswith("Evidencia literal de la actuación")
                and "evidence_passage/administrative_action/action_3"
                in widget.label
                for widget in app.text_area
            )

        if position == 0:
            next(
                widget
                for widget in app.selectbox
                if widget.label
                == "Decisión · administrative_action/action_1.expected_decision"
            ).set_value("favorable")
        elif position == 1:
            decision_widget = next(
                widget
                for widget in app.selectbox
                if widget.label
                == "Decisión · administrative_action/action_2.expected_decision"
            )
            decision_widget.set_value("denegado")
            next(
                widget
                for widget in app.segmented_control
                if widget.key == "v2_status_filter"
            ).set_value("Draft").run()
            assert next(
                widget
                for widget in app.selectbox
                if widget.label
                == "Decisión · administrative_action/action_2.expected_decision"
            ).value == "denegado"

    assert _workspace_bytes(truth_dir) == before


def test_primary_crud_editors_rehydrate_each_selected_row_without_writes(
    v2_multirow_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_multirow_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()

    cases = (
        (
            "events",
            "Evento / proyecto publicado · event_2",
            "text_area",
            "Notas de anotación · event/event_2.annotation_notes",
            "Notas persistidas del evento 2",
        ),
        (
            "generation_assets",
            "Activo de generación · asset_2",
            "selectbox",
            "Tipo de generación · generation_asset/asset_2.expected_generation_type",
            "eolica",
        ),
        (
            "locations",
            "Localización · location_2",
            "selectbox",
            "Nivel administrativo · location/location_2.expected_location_level",
            "provincia",
        ),
    )
    for table, selected, widget_type, field_label, expected_value in cases:
        next(
            widget
            for widget in app.selectbox
            if widget.key == f"v2_edit_{table}_{BOE_ID}_False_all"
        ).set_value(selected).run()
        assert next(
            widget
            for widget in getattr(app, widget_type)
            if widget.label == field_label
        ).value == expected_value

    assert _workspace_bytes(truth_dir) == before


def test_action_and_secondary_evidence_editors_rehydrate_compound_key_rows(
    v2_multirow_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_multirow_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()

    expected_passages = {
        "action_1": [ACTION_EVIDENCE, SECOND_ACTION_EVIDENCE],
        "action_2": [ACTION_EVIDENCE],
        "action_3": [""],
    }
    for action_key in ("action_1", "action_2", "action_3", "action_1"):
        action_selector = next(
            widget
            for widget in app.selectbox
            if widget.key
            == f"v2_edit_administrative_actions_{BOE_ID}_False_all"
        )
        action_selector.set_value(
            f"Actuación administrativa · {action_key}"
        ).run()

        action_headings = [
            element.value
            for element in app.markdown
            if element.value.startswith("**Actuación administrativa · `")
        ]
        evidence_headings = [
            element.value
            for element in app.markdown
            if element.value == "**Evidencias literales de esta actuación**"
        ]
        assert action_headings == [
            f"**Actuación administrativa · `{action_key}`**"
        ]
        assert evidence_headings == ["**Evidencias literales de esta actuación**"]
        assert any(
            f"evidence_passage/administrative_action/{action_key}"
            in caption.value
            for caption in app.caption
        )
        passages = [
            widget.value
            for widget in app.text_area
            if widget.label.startswith("Evidencia literal de la actuación")
            and f"evidence_passage/administrative_action/{action_key}"
            in widget.label
        ]
        assert passages == expected_passages[action_key]
        assert sum(
            button.label == "Guardar actuación y evidencias"
            for button in app.button
        ) == 1
        assert not any(
            widget.key
            and str(widget.key).startswith(
                f"v2_mode_evidence_passages_{BOE_ID}_"
            )
            for widget in app.segmented_control
        )

    next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_secondary_table_{BOE_ID}"
    ).set_value("evidence_passages").run()
    secondary_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_edit_evidence_passages_{BOE_ID}_False_all"
    )
    secondary_selector.set_value(
        next(
            option
            for option in secondary_selector.options
            if "Tiene 25 MW de potencia instalada." in option
        )
    ).run()
    assert next(
        widget
        for widget in app.text_area
        if widget.label
        == "Pasaje continuo literal · evidence_passage/participant/participant_1"
    ).value == "Tiene 25 MW de potencia instalada."

    assert _workspace_bytes(truth_dir) == before


def test_visual_numbers_do_not_replace_sparse_location_keys_or_qa_paths(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    locations = pd.read_csv(
        truth_dir / "locations.csv",
        dtype="string",
        keep_default_na=False,
    )
    additions = pd.DataFrame(
        [
            {
                **_common(),
                "event_key": "event_1",
                "location_key": location_key,
                "location_name_raw": location_name,
                "expected_location_level": "municipio",
            }
            for location_key, location_name in (
                ("location_2", "Villa Dos"),
                ("location_3", "Villa Tres"),
                ("location_5", "Villa Cinco"),
                ("location_6", "Villa Seis"),
            )
        ],
        columns=TABLE_SPECS["locations"].columns,
        dtype="string",
    )
    pd.concat([locations, additions], ignore_index=True).to_csv(
        truth_dir / "locations.csv",
        index=False,
        lineterminator="\n",
    )
    _mark_complete(truth_dir)
    complete = load_truth(truth_dir, require_complete=True)
    source = load_annotation_workspace(truth_dir, source_dir).source_documents.iloc[0]
    package = build_ai_qa_review_package(
        complete,
        BOE_ID,
        title=str(source["titulo"]),
        publication_date="2099-02-01",
        source_text=str(source["texto_limpio"]),
    )
    assert b"location/location_5.location_name_raw" in package
    assert b"location/location_4" not in package

    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()

    location_table = next(
        frame.value
        for frame in app.dataframe
        if "location_key" in frame.value.columns
    )
    assert location_table.columns[0] == "Nº"
    assert location_table["Nº"].tolist() == [1, 2, 3, 4, 5]
    assert location_table["location_key"].astype(str).tolist() == [
        "location_1",
        "location_2",
        "location_3",
        "location_5",
        "location_6",
    ]

    location_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_edit_locations_{BOE_ID}_False_all"
    )
    location_selector.set_value("Localización · location_5").run()
    next(
        widget
        for widget in app.text_input
        if widget.label
        == "Localización literal · location/location_5.location_name_raw"
    ).set_value("Villa V2")
    next(
        button
        for button in app.button
        if button.label == "Guardar fila" and "locations" in str(button.key)
    ).click().run()

    saved = load_truth(truth_dir)
    location_names = dict(
        zip(
            saved.tables["locations"]["location_key"].astype(str),
            saved.tables["locations"]["location_name_raw"].astype(str),
            strict=True,
        )
    )
    assert location_names == {
        "location_1": "Villa V2",
        "location_2": "Villa Dos",
        "location_3": "Villa Tres",
        "location_5": "Villa V2",
        "location_6": "Villa Seis",
    }

    location_mode = next(
        widget
        for widget in app.segmented_control
        if widget.key == f"v2_mode_locations_{BOE_ID}_all"
    )
    location_mode.set_value("Eliminar").run()
    delete_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_delete_locations_{BOE_ID}_all"
    )
    delete_selector.set_value("Localización · location_3").run()
    next(
        widget
        for widget in app.checkbox
        if "location/location_3" in widget.label
    ).set_value(True)
    next(
        button
        for button in app.button
        if button.label == "Eliminar fila" and "locations" in str(button.key)
    ).click().run()

    assert not app.exception
    delete_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_delete_locations_{BOE_ID}_all"
    )
    assert "Localización · location_3" not in delete_selector.options
    assert delete_selector.value in delete_selector.options
    assert next(
        widget
        for widget in app.checkbox
        if "location/" in widget.label
    ).value is False
    location_table = next(
        frame.value
        for frame in app.dataframe
        if "location_key" in frame.value.columns
    )
    assert location_table["Nº"].tolist() == [1, 2, 3, 4]
    assert location_table["location_key"].astype(str).tolist() == [
        "location_1",
        "location_2",
        "location_5",
        "location_6",
    ]
    final_truth = load_truth(truth_dir)
    assert final_truth.tables["events"]["event_key"].astype(str).tolist() == [
        "event_1"
    ]
    assert final_truth.tables["generation_assets"]["asset_key"].astype(
        str
    ).tolist() == ["asset_1"]


def test_secondary_crud_editors_rehydrate_each_selected_row_without_writes(
    v2_multirow_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_multirow_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    dimension = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_secondary_table_{BOE_ID}"
    )

    cases = (
        (
            "associated_components",
            "Componente asociado · component_2",
            "Tipo de componente · associated_component/component_2."
            "expected_component_type",
            "subestacion_electrica",
        ),
        (
            "technical_mentions",
            "Mención técnica · technical_2",
            "Tipo de potencia/atributo · technical_mention/technical_2."
            "expected_attribute_type",
            "potencia_pico",
        ),
        (
            "participants",
            "Participante · participant_2",
            "Rol · participant/participant_2.expected_participant_role",
            "operador",
        ),
    )
    for table, selected, field_label, expected_value in cases:
        dimension = next(
            widget
            for widget in app.selectbox
            if widget.key == f"v2_secondary_table_{BOE_ID}"
        )
        dimension.set_value(table).run()
        next(
            widget
            for widget in app.selectbox
            if widget.key == f"v2_edit_{table}_{BOE_ID}_False_all"
        ).set_value(selected).run()
        assert next(
            widget for widget in app.selectbox if widget.label == field_label
        ).value == expected_value

    dimension = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_secondary_table_{BOE_ID}"
    )
    dimension.set_value("action_targets").run()
    target_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_edit_action_targets_{BOE_ID}_False_all"
    )
    target_selector.set_value(
        next(option for option in target_selector.options if "action_2" in option)
    ).run()
    assert next(
        widget
        for widget in app.selectbox
        if widget.label == "Actuación · action_target/<action_key>.target"
    ).value == "action_2"

    assert _workspace_bytes(truth_dir) == before


def test_crud_operation_and_delete_confirmation_state_are_isolated_by_row(
    v2_multirow_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_multirow_annotation_workspace
    before = _workspace_bytes(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    action_mode = next(
        widget
        for widget in app.segmented_control
        if widget.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )

    action_mode.set_value("Añadir").run()
    next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/<nueva_clave>.expected_decision"
    ).set_value("denegado")
    action_mode = next(
        widget
        for widget in app.segmented_control
        if widget.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )
    action_mode.set_value("Editar").run()
    assert next(
        widget
        for widget in app.selectbox
        if widget.label
        == "Decisión · administrative_action/action_1.expected_decision"
    ).value == "declarado"

    action_mode = next(
        widget
        for widget in app.segmented_control
        if widget.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )
    action_mode.set_value("Eliminar").run()
    next(
        widget
        for widget in app.checkbox
        if "administrative_action/action_1" in widget.label
    ).set_value(True)
    delete_selector = next(
        widget
        for widget in app.selectbox
        if widget.key == f"v2_delete_administrative_actions_{BOE_ID}_all"
    )
    delete_selector.set_value("Actuación administrativa · action_2").run()
    assert next(
        widget
        for widget in app.checkbox
        if "administrative_action/action_2" in widget.label
    ).value is False

    assert _workspace_bytes(truth_dir) == before


def test_action_delete_confirmation_and_atomic_cleanup_are_visible_in_apptest(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    action_mode = next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_administrative_actions_{BOE_ID}_all"
    )
    action_mode.set_value("Eliminar").run()

    assert any(
        "administrative_action/action_1" in warning.value
        and "2 pasaje(s)" in warning.value
        and "0 target(s)" in warning.value
        for warning in app.warning
    )
    confirmation = next(
        widget
        for widget in app.checkbox
        if "administrative_action/action_1" in widget.label
    )
    confirmation.set_value(True)
    delete_button = next(
        button for button in app.button if button.label == "Eliminar fila"
    )
    assert delete_button.disabled is False
    delete_button.click().run()

    assert not app.exception
    assert any(
        "vuelve a borrador" in message.value for message in app.success
    )
    saved = load_truth(truth_dir)
    assert saved.tables["administrative_actions"].empty
    assert action_evidence_rows(saved, BOE_ID).empty
    assert saved.tables["documents"].iloc[0]["annotation_status"] == "draft"


def test_event_delete_is_visibly_blocked_by_canonical_child_references(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    event_mode = next(
        control
        for control in app.segmented_control
        if control.key == f"v2_mode_events_{BOE_ID}_all"
    )
    event_mode.set_value("Eliminar").run()

    assert any(
        "event/event_1" in warning.value
        and "referencias" in warning.value
        for warning in app.warning
    )
    assert any(
        markdown.value == "- `administrative_action/action_1`"
        for markdown in app.markdown
    )
    delete_button = next(
        button for button in app.button if button.label == "Eliminar fila"
    )
    assert delete_button.disabled is True


def test_validation_failure_is_translated_and_keeps_raw_detail_in_apptest(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    evidence = pd.read_csv(
        truth_dir / "evidence_passages.csv",
        dtype="string",
        keep_default_na=False,
    )
    evidence = evidence.loc[
        ~evidence["owner_type"].astype(str).eq("administrative_action")
    ]
    evidence.to_csv(
        truth_dir / "evidence_passages.csv",
        index=False,
        lineterminator="\n",
    )
    load_truth(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()
    next(
        button for button in app.button if button.label == "Validar documento V2"
    ).click().run()

    assert not app.exception
    assert any(
        "La actuación action_1 necesita al menos una evidencia literal"
        in message.value
        for message in app.error
    )
    assert any(
        "Every scored V2 action needs scored action-specific evidence."
        in code.value
        for code in app.code
    )
    assert any(
        "evidence_passage/administrative_action/action_1" in caption.value
        for caption in app.caption
    )
    assert any(
        caption.value.startswith("Sección: 4. Actuaciones administrativas")
        for caption in app.caption
    )


def test_complete_document_enables_current_qa_export(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    _mark_complete(truth_dir)
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()

    download = app.main.get("download_button")[0].proto
    assert download.label == "Descargar paquete para revisión IA"
    assert download.disabled is False


def test_v2_streamlit_surface_is_blind_and_shows_primary_optional_and_paths(
    v2_annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))

    def refuse_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("V2 annotation rendering must remain offline.")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    app = AppTest.from_file(ANNOTATION_APP, default_timeout=30).run()

    assert not app.exception
    assert app.title[0].value == "Anotación humana ciega V2"
    subheaders = [
        element.value
        for element in app.subheader
        if element.value[:1].isdigit()
    ]
    assert subheaders == [
        "1. Documento",
        "2. Eventos / proyectos publicados",
        "3. Activos de generación",
        "4. Actuaciones administrativas + evidencias",
        "5. Localizaciones",
        "6. Validación y estado de anotación",
    ]
    assert any(
        expander.label == "7. Opcional / diagnóstico" for expander in app.expander
    )
    assert not any(
        element.value == "5. Evidencias de actuaciones administrativas"
        for element in app.subheader
    )
    assert any(
        caption.value
        == "Cada actuación primaria se completa aquí junto con sus evidencias "
        "literales obligatorias."
        for caption in app.caption
    )
    assert any(
        element.value == "**Actuación administrativa · `action_1`**"
        for element in app.markdown
    )
    assert any(
        element.value == "**Evidencias literales de esta actuación**"
        for element in app.markdown
    )
    for field in ("applicability", "adjudication", "annotation_notes"):
        assert any(
            f"administrative_action/action_1.{field}" in widget.label
            for widget in [*app.selectbox, *app.text_area]
        )
    assert any(
        "`applicable` significa que la pregunta de relevancia puede evaluarse"
        in message.value
        for message in app.info
    )
    affected = [
        widget
        for widget in app.multiselect
        if "expected_affected_generation_asset_keys_json" in widget.label
    ]
    assert len(affected) == 1
    assert affected[0].options == ["event_1 · asset_1 · [\"Planta V2\"]"]
    assert not any(
        "expected_affected_generation_asset_keys_json" in widget.label
        for widget in [*app.text_input, *app.text_area]
    )
    assert any(
        "evidence_passage/administrative_action/action_1" in caption.value
        for caption in app.caption
    )
    numbered_tables = [
        frame.value for frame in app.dataframe if not frame.value.empty
    ]
    assert numbered_tables
    for frame in numbered_tables:
        assert frame.columns[0] == "Nº"
        assert frame["Nº"].tolist() == list(range(1, len(frame) + 1))
    assert any(
        caption.value
        == "Nº indica la posición en esta tabla. La clave identifica la entidad "
        "y se conserva aunque se eliminen otras filas."
        for caption in app.caption
    )
    download = app.main.get("download_button")[0].proto
    assert download.label == "Descargar paquete para revisión IA"
    assert download.disabled is True


def test_v2_canonical_script_launch_bootstraps_namespace(
    v2_annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = v2_annotation_workspace
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update({
        TRUTH_DIR_ENV: str(truth_dir),
        SOURCE_DIR_ENV: str(source_dir),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_OFFLINE": "1",
    })

    completed = subprocess.run(
        [sys.executable, str(ANNOTATION_APP)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr


def test_v2_annotation_modules_have_no_prediction_or_pipeline_input() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("evaluation/final_holdout_v2/annotation.py"),
            Path("evaluation/final_holdout_v2/annotation_app.py"),
        )
    )
    signature = inspect.signature(load_annotation_workspace)

    assert tuple(signature.parameters) == ("truth_dir", "source_dir")
    for forbidden in (
        "attempts.parquet",
        "current_extractions.parquet",
        "review_queue.parquet",
        "renewables_permitting.pipeline",
        "pydantic_ai",
        "requests.",
    ):
        assert forbidden not in source
