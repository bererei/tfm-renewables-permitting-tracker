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
    action_has_scored_evidence,
    action_evidence_rows,
    build_ai_qa_review_package,
    delete_truth_row,
    load_annotation_workspace,
    next_key_for_table,
    secondary_evidence_rows,
    serialize_affected_assets,
    upsert_action_with_initial_evidence,
    upsert_truth_row,
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
        "Añade primero una actuación para poder registrar su evidencia"
        in message.value
        for message in app.info
    )
    assert not any(
        element.value.startswith("**Evidencias de `")
        for element in app.markdown
    )
    assert any(
        caption.value == "`evidence_passage/administrative_action/action_1`"
        for caption in app.caption
    )


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
    assert any("Añade primero una actuación" in message for message in messages)


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
    load_truth(truth_dir, require_complete=True)


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

    with pytest.raises(TruthContractError, match="affected-generation-asset"):
        upsert_action_with_initial_evidence(
            truth_dir,
            BOE_ID,
            _action_row("action_2", affected_assets="[]"),
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
    load_truth(truth_dir, require_complete=True)


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
    load_truth(truth_dir, require_complete=True)


def test_new_action_form_shows_required_first_evidence_and_canonical_path(
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
        element.value == "**Evidencia literal obligatoria**"
        for element in app.markdown
    )
    assert any(
        area.label.startswith("Primera evidencia literal de la actuación")
        and "evidence_passage/administrative_action/action_2" in area.label
        for area in app.text_area
    )
    assert any(
        "La actuación y su primera evidencia se guardan conjuntamente"
        in caption.value
        for caption in app.caption
    )
    assert any(
        caption.value == "`evidence_passage/administrative_action/action_2`"
        for caption in app.caption
    )
    assert any(button.label == "Guardar actuación" for button in app.button)


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
        "Evento · administrative_action/action_3.event_key": "event_1",
        "Tipo de actuación · administrative_action/action_3.expected_action_type": (
            "autorizacion_administrativa_previa"
        ),
        "Decisión · administrative_action/action_3.expected_decision": "autorizado",
        "Es modificación · administrative_action/action_3.expected_is_modification": (
            "false"
        ),
        "Temporalidad · administrative_action/action_3.temporal_status": "current",
        "Aplicabilidad · administrative_action/action_3.applicability": "applicable",
        "Adjudicación · administrative_action/action_3.adjudication": "scored_truth",
    }
    for label, value in selections.items():
        next(widget for widget in app.selectbox if widget.label == label).set_value(value)
    next(
        widget
        for widget in app.multiselect
        if widget.label
        == "Activos afectados · administrative_action/action_3."
        "expected_affected_generation_asset_keys_json"
    ).set_value(["asset_1"])
    next(
        area
        for area in app.text_area
        if area.label.startswith("Primera evidencia literal de la actuación")
    ).set_value(ACTION_EVIDENCE)

    next(
        button for button in app.button if button.label == "Guardar actuación"
    ).click().run()

    assert not app.exception
    assert not app.error
    saved = load_truth(truth_dir, require_complete=True)
    assert saved.tables["administrative_actions"]["action_key"].astype(str).eq(
        "action_3"
    ).sum() == 1
    evidence = action_evidence_rows(saved, BOE_ID, action_key="action_3")
    assert len(evidence) == 1
    assert evidence.iloc[0]["passage_text"] == ACTION_EVIDENCE


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
        "4. Actuaciones administrativas",
        "5. Evidencias de actuaciones administrativas",
        "6. Localizaciones",
        "7. Validación y estado de anotación",
    ]
    assert any(
        expander.label == "8. Opcional / diagnóstico" for expander in app.expander
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
