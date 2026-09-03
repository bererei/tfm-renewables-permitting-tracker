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

from evaluation.final_holdout_v2.annotation import (
    SOURCE_DIR_ENV,
    TRUTH_DIR_ENV,
    action_evidence_rows,
    build_ai_qa_review_package,
    load_annotation_workspace,
    secondary_evidence_rows,
    serialize_affected_assets,
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
        "evidence_passage/administrative_action/" in caption.value
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
