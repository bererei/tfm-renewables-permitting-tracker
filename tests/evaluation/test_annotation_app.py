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

from evaluation.final_holdout_v1.annotation import (
    AnnotationWorkspace,
    SOURCE_DIR_ENV,
    TRUTH_DIR_ENV,
    build_ai_qa_review_package,
    build_official_boe_url,
    derive_entity_reference,
    entity_choices,
    load_annotation_workspace,
    mark_document_complete,
    next_local_key,
    serialize_aliases,
    serialize_key_selection,
    update_document_scope,
    upsert_truth_row,
    validate_evidence_literal,
)
from evaluation.final_holdout_v1.contract import (
    CONTRACT_VERSION,
    FROZEN_SOURCE_SNAPSHOT_ID,
    NA,
    TABLE_SPECS,
    TruthContractError,
    load_truth,
)
from renewables_permitting.extraction.documents import build_source_document


BOE_ONE = "BOE-A-2099-101"
BOE_TWO = "BOE-A-2099-102"
ACTION_EVIDENCE = "Se otorga autorización administrativa previa a Planta Aurora."
TECHNICAL_EVIDENCE = "25 MW de potencia instalada"
REPOSITORY_ROOT = Path(__file__).parents[2]
ANNOTATION_APP = REPOSITORY_ROOT / "evaluation/final_holdout_v1/annotation_app.py"


def _source_row(boe_id: str, day: int, title: str, text: str) -> dict[str, object]:
    return {
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp(2099, 1, day),
        "titulo": title,
        "texto_limpio": text,
    }


def _write_table(
    truth_dir: Path,
    table: str,
    rows: list[dict[str, object]],
) -> None:
    pd.DataFrame(rows, columns=TABLE_SPECS[table].columns, dtype="string").to_csv(
        truth_dir / f"{table}.csv",
        index=False,
        lineterminator="\n",
    )


def _document_row(
    boe_id: str,
    source_hash: str,
    *,
    expected_scope: str,
) -> dict[str, str]:
    return {
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_version": "synthetic_annotation_v1",
        "identificador_boe": boe_id,
        "source_document_sha256": source_hash,
        "annotation_status": "draft",
        "scope_applicability": "applicable",
        "scope_adjudication": "scored_truth",
        "expected_document_scope": expected_scope,
        "reviewer_id": "synthetic_human",
        "reviewed_on": "2099-01-01",
        "annotation_notes": NA,
    }


@pytest.fixture
def annotation_workspace(tmp_path: Path) -> tuple[Path, Path]:
    source_rows = [
        _source_row(
            BOE_ONE,
            1,
            "Anuncio de Planta Aurora",
            (
                "La planta fotovoltaica Planta Aurora se ubica en Villa Solar. "
                f"Dispone de {TECHNICAL_EVIDENCE}. {ACTION_EVIDENCE}"
            ),
        ),
        _source_row(
            BOE_TWO,
            2,
            "Anuncio sintético sin proyecto",
            "Este anuncio no identifica ningún proyecto de generación.",
        ),
    ]
    source = pd.DataFrame(source_rows)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source.to_parquet(source_dir / "documents.parquet", index=False)
    source_hashes = {
        str(row["identificador"]): build_source_document(row).source_document_sha256
        for _, row in source.iterrows()
    }

    truth_dir = tmp_path / "truth"
    truth_dir.mkdir()
    rows: dict[str, list[dict[str, object]]] = {
        table: [] for table in TABLE_SPECS
    }
    rows["documents"] = [
        _document_row(
            BOE_ONE,
            source_hashes[BOE_ONE],
            expected_scope="generation_project_specific",
        ),
        _document_row(
            BOE_TWO,
            source_hashes[BOE_TWO],
            expected_scope="not_relevant_for_generation_projects",
        ),
    ]
    rows["events"] = [{
        "identificador_boe": BOE_ONE,
        "event_key": "event_1",
        "event_label": "Planta Aurora",
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }]
    rows["generation_assets"] = [{
        "identificador_boe": BOE_ONE,
        "event_key": "event_1",
        "asset_key": "asset_1",
        "names_json": '["Planta Aurora"]',
        "expected_generation_type": "fotovoltaica",
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }]
    rows["administrative_actions"] = [{
        "identificador_boe": BOE_ONE,
        "event_key": "event_1",
        "action_key": "action_1",
        "expected_action_type": "autorizacion_administrativa_previa",
        "expected_decision": "autorizado",
        "expected_is_modification": "false",
        "temporal_status": "current",
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }]
    rows["action_targets"] = [{
        "identificador_boe": BOE_ONE,
        "event_key": "event_1",
        "action_key": "action_1",
        "target_type": "generation_asset",
        "target_truth_key": "asset_1",
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }]
    rows["evidence_passages"] = [{
        "identificador_boe": BOE_ONE,
        "owner_type": "administrative_action",
        "owner_key": "action_1",
        "passage_text": ACTION_EVIDENCE,
        "applicability": "applicable",
        "adjudication": "scored_truth",
        "annotation_notes": NA,
    }]
    for table, table_rows in rows.items():
        _write_table(truth_dir, table, table_rows)
    (truth_dir / "truth_metadata.json").write_text(
        json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "holdout_artifact_identity": "a" * 64,
            "source_snapshot_identity": FROZEN_SOURCE_SNAPSHOT_ID,
            "initialization_mode": "blind_annotation",
            "predictions_exposed_during_annotation": False,
        }),
        encoding="utf-8",
    )
    load_truth(truth_dir)
    return truth_dir, source_dir


def _rows_for_boe(truth_dir: Path, boe_id: str) -> dict[str, list[dict[str, str]]]:
    truth = load_truth(truth_dir)
    result: dict[str, list[dict[str, str]]] = {}
    for table, frame in truth.tables.items():
        selected = frame.loc[frame["identificador_boe"].astype(str).eq(boe_id)]
        result[table] = [
            {column: str(row[column]) for column in frame.columns}
            for _, row in selected.iterrows()
        ]
    return result


def _complete_review_package_truth(
    truth_dir: Path,
    source_dir: Path,
) -> tuple[AnnotationWorkspace, pd.Series]:
    upsert_truth_row(
        truth_dir,
        "associated_components",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "event_key": "event_1",
            "component_key": "component_1",
            "names_json": '["Subestación Aurora"]',
            "description_raw": "Subestación sintética de evacuación",
            "expected_component_type": "subestacion_electrica",
            "related_asset_keys_json": '["asset_1"]',
            "applicability": "applicable",
            "adjudication": "scored_truth",
            "annotation_notes": NA,
        },
    )
    upsert_truth_row(
        truth_dir,
        "technical_mentions",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "event_key": "event_1",
            "owner_type": "generation_asset",
            "owner_key": "asset_1",
            "technical_key": "technical_1",
            "expected_attribute_type": "potencia_instalada",
            "expected_value_raw": "25 MW",
            "applicability": "applicable",
            "adjudication": "scored_truth",
            "annotation_notes": NA,
        },
    )
    upsert_truth_row(
        truth_dir,
        "participants",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "event_key": "event_1",
            "participant_key": "participant_1",
            "participant_name_raw": "Promotora Aurora, S.L.",
            "expected_participant_role": "promotor",
            "applicability": "applicable",
            "adjudication": "scored_truth",
            "annotation_notes": NA,
        },
    )
    upsert_truth_row(
        truth_dir,
        "locations",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "event_key": "event_1",
            "location_key": "location_1",
            "location_name_raw": "Villa Solar",
            "expected_location_level": "municipio",
            "applicability": "unknown",
            "adjudication": "ambiguous_not_safely_determinable",
            "annotation_notes": "Nivel territorial pendiente de adjudicación",
        },
    )
    upsert_truth_row(
        truth_dir,
        "evidence_passages",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "owner_type": "technical_mention",
            "owner_key": "technical_1",
            "passage_text": TECHNICAL_EVIDENCE,
            "applicability": "applicable",
            "adjudication": "scored_truth",
            "annotation_notes": NA,
        },
    )
    workspace = load_annotation_workspace(truth_dir, source_dir)
    source_row = workspace.source_documents.loc[
        workspace.source_documents["identificador"].astype(str).eq(BOE_ONE)
    ].iloc[0]
    mark_document_complete(
        truth_dir,
        BOE_ONE,
        source_text=f"{source_row['titulo']}\n{source_row['texto_limpio']}",
    )
    completed = load_annotation_workspace(truth_dir, source_dir)
    completed_source = completed.source_documents.loc[
        completed.source_documents["identificador"].astype(str).eq(BOE_ONE)
    ].iloc[0]
    return completed, completed_source


def _build_review_package(
    workspace: AnnotationWorkspace,
    source_row: pd.Series,
) -> bytes:
    return build_ai_qa_review_package(
        workspace.truth,
        BOE_ONE,
        title=str(source_row["titulo"]),
        publication_date=pd.Timestamp(source_row["fecha_publicacion"])
        .date()
        .isoformat(),
        source_text=str(source_row["texto_limpio"]),
    )


def test_workspace_loader_has_only_blind_truth_and_source_inputs(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = annotation_workspace

    workspace = load_annotation_workspace(truth_dir, source_dir)

    assert set(workspace.source_documents["identificador"].astype(str)) == {
        BOE_ONE,
        BOE_TWO,
    }
    assert tuple(inspect.signature(load_annotation_workspace).parameters) == (
        "truth_dir",
        "source_dir",
    )
    for module_path in (
        Path("evaluation/final_holdout_v1/annotation.py"),
        Path("evaluation/final_holdout_v1/annotation_app.py"),
    ):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
        assert "evaluation.final_holdout_v1.evaluator" not in imported_modules
        source = module_path.read_text(encoding="utf-8")
        for forbidden_path in (
            "attempts.parquet",
            "current_extractions.parquet",
            "review_queue.parquet",
            "extraction.json",
        ):
            assert forbidden_path not in source


def test_next_key_generation_uses_next_deterministic_integer() -> None:
    frame = pd.DataFrame({
        "identificador_boe": [BOE_ONE, BOE_ONE, BOE_TWO],
        "asset_key": ["asset_1", "asset_3", "asset_9"],
    })

    assert next_local_key(
        frame,
        boe_id=BOE_ONE,
        key_column="asset_key",
        prefix="asset",
    ) == "asset_4"


def test_aliases_and_related_assets_are_serialized_without_json_bookkeeping() -> None:
    assert serialize_aliases("Planta Aurora\nAurora FV\nPlanta Aurora\n") == (
        '["Planta Aurora","Aurora FV"]'
    )
    assert serialize_key_selection(["asset_2", "asset_1", "asset_2"]) == (
        '["asset_2","asset_1"]'
    )
    with pytest.raises(TruthContractError, match="alias"):
        serialize_aliases("\n  \n")


@pytest.mark.parametrize(
    ("boe_id", "expected"),
    [
        (
            "BOE-A-2099-101",
            "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-101",
        ),
        (
            "BOE-B-2098-7",
            "https://www.boe.es/diario_boe/txt.php?id=BOE-B-2098-7",
        ),
    ],
)
def test_official_boe_url_uses_only_the_valid_identifier(
    boe_id: str,
    expected: str,
) -> None:
    assert build_official_boe_url(boe_id) == expected


@pytest.mark.parametrize(
    "boe_id",
    [
        "BOE-A-2099-101?prediction=1",
        "boe-a-2099-101",
        "BOE-X-2099-101",
        "BOE-A-99-1",
    ],
)
def test_official_boe_url_rejects_malformed_identifiers(boe_id: str) -> None:
    with pytest.raises(TruthContractError, match="Invalid BOE identifier"):
        build_official_boe_url(boe_id)


def test_related_asset_selection_is_saved_as_valid_contract_json(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, _ = annotation_workspace

    upsert_truth_row(
        truth_dir,
        "associated_components",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "event_key": "event_1",
            "component_key": "component_1",
            "names_json": "[]",
            "description_raw": "Línea de evacuación sintética",
            "expected_component_type": "linea_electrica",
            "related_asset_keys_json": serialize_key_selection(["asset_1"]),
            "applicability": "applicable",
            "adjudication": "scored_truth",
            "annotation_notes": NA,
        },
    )

    components = load_truth(truth_dir).tables["associated_components"]
    assert components.iloc[0]["related_asset_keys_json"] == '["asset_1"]'


def test_action_target_selection_derives_type_and_truth_key(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, _ = annotation_workspace
    truth = load_truth(truth_dir)
    choices = entity_choices(truth, BOE_ONE, purpose="action_target")

    assert derive_entity_reference("generation_asset:asset_1", choices) == (
        "generation_asset",
        "asset_1",
    )
    with pytest.raises(TruthContractError, match="existing truth entity"):
        derive_entity_reference("generation_asset:asset_99", choices)


def test_evidence_requires_one_literal_continuous_source_passage() -> None:
    source = f"Título\n{ACTION_EVIDENCE} Después continúa el anuncio."

    assert validate_evidence_literal(ACTION_EVIDENCE, source) == ACTION_EVIDENCE
    assert validate_evidence_literal(
        "SE OTORGA AUTORIZACIÓN ADMINISTRATIVA PREVIA A PLANTA AURORA.",
        source,
    )
    with pytest.raises(TruthContractError, match="literal"):
        validate_evidence_literal("Se autoriza de forma resumida.", source)
    with pytest.raises(TruthContractError, match="continuous"):
        validate_evidence_literal("Se otorga [...] Planta Aurora.", source)


def test_safe_write_changes_only_selected_boe(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, _ = annotation_workspace
    other_before = _rows_for_boe(truth_dir, BOE_TWO)

    upsert_truth_row(
        truth_dir,
        "participants",
        BOE_ONE,
        {
            "identificador_boe": BOE_ONE,
            "event_key": "event_1",
            "participant_key": "participant_1",
            "participant_name_raw": "Solar Sintética, S.L.",
            "expected_participant_role": "promotor",
            "applicability": "applicable",
            "adjudication": "scored_truth",
            "annotation_notes": NA,
        },
    )

    assert _rows_for_boe(truth_dir, BOE_TWO) == other_before
    participants = load_truth(truth_dir).tables["participants"]
    assert participants["participant_key"].astype(str).tolist() == ["participant_1"]


def test_validation_failure_preserves_original_table_bytes(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, _ = annotation_workspace
    path = truth_dir / "participants.csv"
    original = path.read_bytes()

    with pytest.raises(TruthContractError, match="unknown event"):
        upsert_truth_row(
            truth_dir,
            "participants",
            BOE_ONE,
            {
                "identificador_boe": BOE_ONE,
                "event_key": "event_99",
                "participant_key": "participant_1",
                "participant_name_raw": "Entidad inválida",
                "expected_participant_role": "promotor",
                "applicability": "applicable",
                "adjudication": "scored_truth",
                "annotation_notes": NA,
            },
        )

    assert path.read_bytes() == original


def test_mark_complete_uses_frozen_document_completeness_and_fails_closed(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, _ = annotation_workspace

    mark_document_complete(
        truth_dir,
        BOE_ONE,
        source_text=f"Anuncio\n{ACTION_EVIDENCE}",
    )
    documents = load_truth(truth_dir).tables["documents"]
    assert documents.loc[
        documents["identificador_boe"].astype(str).eq(BOE_ONE),
        "annotation_status",
    ].iloc[0] == "complete"

    update_document_scope(
        truth_dir,
        BOE_TWO,
        scope_applicability="applicable",
        scope_adjudication="scored_truth",
        expected_document_scope="generation_project_specific",
        annotation_notes="synthetic incomplete project",
    )
    documents_path = truth_dir / "documents.csv"
    before_failure = documents_path.read_bytes()
    with pytest.raises(TruthContractError, match="at least one scored event"):
        mark_document_complete(
            truth_dir,
            BOE_TWO,
            source_text="Anuncio sin proyecto.",
        )
    assert documents_path.read_bytes() == before_failure


def test_completed_document_builds_full_blind_ai_qa_review_package(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = annotation_workspace
    workspace, source_row = _complete_review_package_truth(truth_dir, source_dir)

    package = _build_review_package(workspace, source_row)
    text = package.decode("utf-8")

    assert text.startswith("# Blind Human Annotation Review Package\n")
    assert f"- **BOE ID:** {BOE_ONE}" in text
    assert "- **Title:** Anuncio de Planta Aurora" in text
    assert "- **Publication date:** 2099-01-01" in text
    assert str(source_row["texto_limpio"]) in text
    for table in TABLE_SPECS:
        assert f"### {table}" in text
    for expected_value in (
        '["Planta Aurora"]',
        "Subestación sintética de evacuación",
        "25 MW",
        "autorizacion_administrativa_previa",
        "generation_asset",
        "Promotora Aurora, S.L.",
        "Villa Solar",
        ACTION_EVIDENCE,
        TECHNICAL_EVIDENCE,
        NA,
        "ambiguous_not_safely_determinable",
        "scored_truth",
    ):
        assert expected_value in text
    for instruction in (
        "El BOE suministrado es la única fuente de verdad.",
        "No sustituyas la anotación por una extracción propia.",
        "OMISIÓN",
        "INCLUSIÓN_INDEBIDA",
        "VALOR_INCORRECTO",
        "EVIDENCIA_INSUFICIENTE",
        "TEMPORALIDAD_DUDOSA",
        "RELACIÓN_TARGET_DUDOSA",
        "AMBIGÜEDAD",
        "SIN DISCREPANCIAS MATERIALES DETECTADAS.",
        "| Nº | Tipo | Entidad/campo | Anotación actual | Posible problema |",
    ):
        assert instruction in text
    for forbidden in (
        BOE_TWO,
        "source_document_sha256",
        "attempt_id",
        "current_extractions",
        "review_queue",
        "model_output",
        "Gemini",
        "P0",
    ):
        assert forbidden not in text


def test_draft_document_cannot_build_review_package(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = annotation_workspace
    workspace = load_annotation_workspace(truth_dir, source_dir)
    source_row = workspace.source_documents.loc[
        workspace.source_documents["identificador"].astype(str).eq(BOE_ONE)
    ].iloc[0]

    with pytest.raises(TruthContractError, match="Completa y valida"):
        _build_review_package(workspace, source_row)


def test_review_package_is_deterministic_and_does_not_modify_truth(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = annotation_workspace
    workspace, source_row = _complete_review_package_truth(truth_dir, source_dir)
    before = {
        path.name: path.read_bytes()
        for path in sorted(truth_dir.iterdir())
        if path.is_file()
    }

    first = _build_review_package(workspace, source_row)
    second = _build_review_package(workspace, source_row)

    after = {
        path.name: path.read_bytes()
        for path in sorted(truth_dir.iterdir())
        if path.is_file()
    }
    assert first == second
    assert before == after


def test_review_package_is_isolated_to_selected_boe(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = annotation_workspace
    initial = load_annotation_workspace(truth_dir, source_dir)
    source_row = initial.source_documents.loc[
        initial.source_documents["identificador"].astype(str).eq(BOE_TWO)
    ].iloc[0]
    mark_document_complete(
        truth_dir,
        BOE_TWO,
        source_text=f"{source_row['titulo']}\n{source_row['texto_limpio']}",
    )
    workspace = load_annotation_workspace(truth_dir, source_dir)

    package = build_ai_qa_review_package(
        workspace.truth,
        BOE_TWO,
        title=str(source_row["titulo"]),
        publication_date="2099-01-02",
        source_text=str(source_row["texto_limpio"]),
    ).decode("utf-8")

    assert BOE_TWO in package
    assert "Este anuncio no identifica ningún proyecto" in package
    assert BOE_ONE not in package
    assert "Planta Aurora" not in package
    assert ACTION_EVIDENCE not in package


def test_streamlit_annotation_app_smoke_uses_synthetic_workspace(
    annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = annotation_workspace
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))

    def refuse_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Annotation rendering must not access the network.")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)

    app = AppTest.from_file(
        ANNOTATION_APP,
        default_timeout=20,
    ).run()

    assert not app.exception
    assert app.title[0].value == "Anotación humana ciega"
    assert len(app.get("progress")) == 1
    assert any("BOE-A-2099-101" in caption.value for caption in app.caption)
    link = app.main.get("link_button")[0].proto
    assert link.label == "Abrir documento en BOE"
    assert link.url == (
        "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-101"
    )
    download = app.main.get("download_button")[0].proto
    assert download.label == "Descargar paquete para revisión IA"
    assert download.disabled is True
    assert any(
        caption.value == "Completa y valida primero la anotación humana."
        for caption in app.caption
    )


def test_streamlit_completed_document_exposes_in_memory_review_download(
    annotation_workspace: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_dir, source_dir = annotation_workspace
    workspace = load_annotation_workspace(truth_dir, source_dir)
    source_row = workspace.source_documents.loc[
        workspace.source_documents["identificador"].astype(str).eq(BOE_ONE)
    ].iloc[0]
    mark_document_complete(
        truth_dir,
        BOE_ONE,
        source_text=f"{source_row['titulo']}\n{source_row['texto_limpio']}",
    )
    before = {
        path.name: path.read_bytes()
        for path in sorted(truth_dir.iterdir())
        if path.is_file()
    }
    monkeypatch.setenv(TRUTH_DIR_ENV, str(truth_dir))
    monkeypatch.setenv(SOURCE_DIR_ENV, str(source_dir))

    def refuse_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Annotation rendering must not access the network.")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)

    app = AppTest.from_file(ANNOTATION_APP, default_timeout=20).run()

    assert not app.exception
    download = app.main.get("download_button")[0].proto
    assert download.label == "Descargar paquete para revisión IA"
    assert download.url.endswith(".md")
    assert download.disabled is False
    assert download.ignore_rerun is True
    after = {
        path.name: path.read_bytes()
        for path in sorted(truth_dir.iterdir())
        if path.is_file()
    }
    assert before == after


def test_canonical_script_launch_bootstraps_evaluation_namespace(
    annotation_workspace: tuple[Path, Path],
) -> None:
    truth_dir, source_dir = annotation_workspace
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
    assert "No module named 'evaluation'" not in completed.stderr
