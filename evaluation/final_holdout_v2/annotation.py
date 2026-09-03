from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

from evaluation.final_holdout_v1.annotation import (
    EntityChoice,
    aliases_for_edit,
    build_official_boe_url,
    derive_entity_reference,
    entity_choices,
    next_local_key,
    serialize_aliases,
    serialize_key_selection,
    validate_evidence_literal,
)
from evaluation.final_holdout_v1.contract import (
    _derive_source_document_identities,
    _documents_path,
)
from evaluation.final_holdout_v2.contract import (
    NA,
    TABLE_SPECS,
    TRUTH_MANIFEST,
    TRUTH_METADATA,
    TruthArtifact,
    TruthContractError,
    load_truth,
)
from evaluation.final_holdout_v2.terminology import (
    entity_label,
    field_label,
    qa_path,
    table_entity,
    table_key_field,
)


DEFAULT_TRUTH_DIR = Path("runs/final_holdout_p2_v1_truth_v2_working")
DEFAULT_SOURCE_DIR = Path(
    "runs/final-corpus-preflight-20220101-20260820-v2/source"
)
TRUTH_DIR_ENV = "FINAL_HOLDOUT_V2_ANNOTATION_TRUTH_DIR"
SOURCE_DIR_ENV = "FINAL_HOLDOUT_V2_ANNOTATION_SOURCE_DIR"
SOURCE_COLUMNS = (
    "identificador",
    "fecha_publicacion",
    "titulo",
    "texto_limpio",
)
EDITABLE_TABLES = tuple(table for table in TABLE_SPECS if table != "documents")
KEY_PREFIXES = {
    "events": ("event_key", "event"),
    "generation_assets": ("asset_key", "asset"),
    "associated_components": ("component_key", "component"),
    "technical_mentions": ("technical_key", "technical"),
    "administrative_actions": ("action_key", "action"),
    "participants": ("participant_key", "participant"),
    "locations": ("location_key", "location"),
}

_PRIMARY_FIELDS = {
    "documents": (
        "annotation_status",
        "scope_applicability",
        "scope_adjudication",
        "expected_document_scope",
        "reviewer_id",
        "reviewed_on",
        "annotation_notes",
    ),
    "events": (
        "event_label",
        "applicability",
        "adjudication",
        "annotation_notes",
    ),
    "generation_assets": (
        "event_key",
        "names_json",
        "expected_generation_type",
        "applicability",
        "adjudication",
        "annotation_notes",
    ),
    "administrative_actions": (
        "event_key",
        "expected_action_type",
        "expected_decision",
        "expected_is_modification",
        "temporal_status",
        "expected_affected_generation_asset_keys_json",
        "applicability",
        "adjudication",
        "annotation_notes",
    ),
    "locations": (
        "event_key",
        "location_name_raw",
        "expected_location_level",
        "applicability",
        "adjudication",
        "annotation_notes",
    ),
}
_SECONDARY_TABLES = (
    "associated_components",
    "technical_mentions",
    "action_targets",
    "participants",
)


@dataclass(frozen=True)
class AnnotationWorkspace:
    truth_dir: Path
    source_path: Path
    truth: TruthArtifact
    source_documents: pd.DataFrame


def configured_paths() -> tuple[Path, Path]:
    return (
        Path(os.environ.get(TRUTH_DIR_ENV, str(DEFAULT_TRUTH_DIR))),
        Path(os.environ.get(SOURCE_DIR_ENV, str(DEFAULT_SOURCE_DIR))),
    )


def serialize_affected_assets(values: Sequence[str]) -> str:
    """Serialize a human multiselect without exposing JSON entry in the UI."""

    return serialize_key_selection(values)


def next_key_for_table(truth: TruthArtifact, table: str, boe_id: str) -> str:
    if table not in KEY_PREFIXES:
        raise ValueError(f"Table has no generated local key: {table}")
    key_column, prefix = KEY_PREFIXES[table]
    return next_local_key(
        truth.tables[table],
        boe_id=boe_id,
        key_column=key_column,
        prefix=prefix,
    )


def _markdown_cell(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\r", "<br>")
        .replace("\n", "<br>")
    )


def _fenced_text(value: str) -> str:
    longest = 0
    run = 0
    for character in value:
        run = run + 1 if character == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def _selected_rows(
    truth: TruthArtifact, table: str, boe_id: str
) -> pd.DataFrame:
    frame = truth.tables[table]
    selected = frame.loc[frame["identificador_boe"].astype(str).eq(boe_id)]
    if selected.empty:
        return selected
    return selected.sort_values(list(TABLE_SPECS[table].key_columns), kind="stable")


def _append_field_rows(
    lines: list[str],
    *,
    truth: TruthArtifact,
    boe_id: str,
    table: str,
    fields: Sequence[str],
) -> None:
    selected = _selected_rows(truth, table, boe_id)
    entity = table_entity(table)
    lines.extend((f"### {entity_label(entity)}", ""))
    if selected.empty:
        lines.extend(("_Sin filas para este BOE._", ""))
        return
    lines.extend(("| Etiqueta | Entidad/campo | Anotación actual |", "| --- | --- | --- |"))
    for _, row in selected.iterrows():
        for field in fields:
            lines.append(
                f"| {_markdown_cell(field_label(entity, field))} "
                f"| `{qa_path(table, row, field)}` "
                f"| {_markdown_cell(row[field])} |"
            )
    lines.append("")


def _append_evidence_rows(
    lines: list[str],
    *,
    selected: pd.DataFrame,
) -> None:
    lines.extend(("### Evidencia", ""))
    if selected.empty:
        lines.extend(("_Sin filas para este BOE._", ""))
        return
    lines.extend(("| Entidad/campo | Anotación actual |", "| --- | --- |"))
    for _, row in selected.iterrows():
        value = (
            f"{row['passage_text']} "
            f"[applicability={row['applicability']}; "
            f"adjudication={row['adjudication']}]"
        )
        lines.append(
            f"| `{qa_path('evidence_passages', row, 'passage_text')}` "
            f"| {_markdown_cell(value)} |"
        )
    lines.append("")


def _append_secondary_table(
    lines: list[str], truth: TruthArtifact, boe_id: str, table: str
) -> None:
    selected = _selected_rows(truth, table, boe_id)
    entity = table_entity(table)
    lines.extend((f"### {entity_label(entity)}", ""))
    if selected.empty:
        lines.extend(("_Sin filas para este BOE._", ""))
        return
    lines.extend(("| Entidad/campo | Anotación actual |", "| --- | --- |"))
    for _, row in selected.iterrows():
        if table == "action_targets":
            path = qa_path(table, row, "target_type")
            value = f"{row['target_type']}:{row['target_truth_key']}"
            lines.append(f"| `{path}` | {_markdown_cell(value)} |")
            continue
        key_field = table_key_field(table)
        for field in TABLE_SPECS[table].columns:
            if field in {"identificador_boe", key_field}:
                continue
            lines.append(
                f"| `{qa_path(table, row, field)}` | {_markdown_cell(row[field])} |"
            )
    lines.append("")


def build_ai_qa_review_package(
    truth: TruthArtifact,
    boe_id: str,
    *,
    title: str,
    publication_date: str | None,
    source_text: str,
) -> bytes:
    documents = _selected_rows(truth, "documents", boe_id)
    if len(documents) != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")
    if str(documents.iloc[0]["annotation_status"]) != "complete":
        raise TruthContractError("Completa y valida primero la anotación humana V2.")
    if not isinstance(title, str) or not isinstance(source_text, str):
        raise TruthContractError("V2 review export requires local source text.")

    lines = [
        "# Paquete de revisión de anotación humana ciega V2",
        "",
        "## Documento fuente",
        "",
        f"- **BOE ID:** {_markdown_cell(boe_id)}",
        f"- **Título:** {_markdown_cell(title)}",
        f"- **Fecha de publicación:** {_markdown_cell(publication_date or 'No disponible')}",
        "- **Contrato:** `final_holdout_evaluation_contract_v2`",
        "- **Contenido:** texto fuente local y verdad humana; sin salidas del sistema evaluado.",
        "",
        "## Texto oficial local",
        "",
        _fenced_text(source_text),
        "",
        "## Verdad primaria V2",
        "",
    ]
    for table, fields in _PRIMARY_FIELDS.items():
        _append_field_rows(
            lines,
            truth=truth,
            boe_id=boe_id,
            table=table,
            fields=fields,
        )

    evidence = _selected_rows(truth, "evidence_passages", boe_id)
    primary_evidence = evidence.loc[
        evidence["owner_type"].astype(str).eq("administrative_action")
    ]
    _append_evidence_rows(lines, selected=primary_evidence)

    lines.extend((
        "## Datos secundarios / diagnósticos — no bloqueantes",
        "",
        "Estos datos no forman parte de los requisitos de completitud V2.",
        "",
    ))
    for table in _SECONDARY_TABLES:
        _append_secondary_table(lines, truth, boe_id, table)
    secondary_evidence = evidence.loc[
        ~evidence["owner_type"].astype(str).eq("administrative_action")
    ]
    _append_evidence_rows(lines, selected=secondary_evidence)

    lines.extend((
        "## Instrucciones fijas para la revisión IA independiente",
        "",
        "- El texto BOE suministrado es la única fuente documental.",
        "- Evalúa exclusivamente los requisitos PRIMARIOS V2: alcance, eventos, "
        "activos de generación, actuaciones, temporalidad, activos afectados, "
        "localizaciones y evidencia de actuaciones.",
        "- No conviertas datos secundarios ausentes en hallazgos bloqueantes.",
        "- Una observación sobre datos secundarios existentes debe empezar por "
        "`SECUNDARIO_NO_BLOQUEANTE`.",
        "- Cada hallazgo debe aportar un pasaje continuo literal.",
        "- `Entidad/campo` debe usar exactamente una ruta canónica mostrada en el paquete.",
        "- Si no hay discrepancias primarias materiales, responde exactamente:",
        "",
        "  `SIN DISCREPANCIAS PRIMARIAS V2 DETECTADAS.`",
        "",
        "| Nº | Tipo | Entidad/campo | Anotación actual | Posible problema | Pasaje literal | Recomendación | Confianza |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        "",
    ))
    return "\n".join(lines).encode("utf-8")


def load_annotation_workspace(
    truth_dir: Path,
    source_dir: Path,
) -> AnnotationWorkspace:
    truth_dir = Path(truth_dir)
    source_path = _documents_path(Path(source_dir))
    truth = load_truth(truth_dir)
    documents = truth.tables["documents"]
    boe_ids = documents["identificador_boe"].astype(str).tolist()
    if not boe_ids:
        raise TruthContractError("The V2 annotation workspace contains no documents.")
    source = pd.read_parquet(
        source_path,
        columns=list(SOURCE_COLUMNS),
        filters=[("identificador", "in", boe_ids)],
    )
    identities = _derive_source_document_identities(source)
    expected = {
        str(row["identificador_boe"]): str(row["source_document_sha256"])
        for _, row in documents.iterrows()
    }
    observed = {
        str(row["identificador"]): str(row["source_document_sha256"])
        for _, row in identities.iterrows()
    }
    if observed != expected:
        raise TruthContractError(
            "V2 truth/source document membership or canonical identity mismatch."
        )
    source = source.copy()
    source["identificador"] = source["identificador"].astype("string")
    source = source.sort_values("identificador", kind="stable").reset_index(drop=True)
    return AnnotationWorkspace(
        truth_dir=truth_dir,
        source_path=source_path,
        truth=truth,
        source_documents=source,
    )


def _write_table(frame: pd.DataFrame, table: str, path: Path) -> None:
    spec = TABLE_SPECS[table]
    ordered = (
        frame.sort_values(list(spec.key_columns), kind="stable")
        if not frame.empty
        else frame
    )
    ordered.to_csv(
        path,
        index=False,
        columns=list(spec.columns),
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )


def _validate_primary_action_evidence(
    truth: TruthArtifact, boe_id: str, source_text: str
) -> None:
    evidence = truth.tables["evidence_passages"]
    evidence = evidence.loc[
        evidence["identificador_boe"].astype(str).eq(boe_id)
        & evidence["owner_type"].astype(str).eq("administrative_action")
        & evidence["applicability"].astype(str).eq("applicable")
        & evidence["adjudication"].astype(str).eq("scored_truth")
    ]
    for passage in evidence["passage_text"].astype(str):
        validate_evidence_literal(passage, source_text)


def validate_document(
    truth_dir: Path,
    boe_id: str,
    *,
    source_text: str | None = None,
) -> TruthArtifact:
    truth_dir = Path(truth_dir)
    truth = load_truth(truth_dir)
    documents = truth.tables["documents"]
    if documents["identificador_boe"].astype(str).eq(boe_id).sum() != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")
    with tempfile.TemporaryDirectory(prefix="blind-v2-annotation-document-") as temp:
        isolated_dir = Path(temp)
        for table in TABLE_SPECS:
            frame = truth.tables[table]
            isolated = frame.loc[
                frame["identificador_boe"].astype(str).eq(boe_id)
            ].copy()
            if table == "documents":
                isolated.loc[:, "annotation_status"] = "complete"
            _write_table(isolated, table, isolated_dir / f"{table}.csv")
        metadata_path = truth_dir / TRUTH_METADATA
        if metadata_path.is_file():
            shutil.copy2(metadata_path, isolated_dir / TRUTH_METADATA)
        isolated_truth = load_truth(isolated_dir, require_complete=True)
        if source_text is not None:
            _validate_primary_action_evidence(isolated_truth, boe_id, source_text)
        return isolated_truth


def _commit_table_frame(
    truth_dir: Path,
    table: str,
    replacement: pd.DataFrame,
    *,
    after_staging: Callable[[Path], None] | None = None,
) -> TruthArtifact:
    truth_dir = Path(truth_dir)
    if table not in TABLE_SPECS:
        raise ValueError(f"Unknown V2 truth table: {table}")
    current = load_truth(truth_dir)
    if current.manifest is not None or (truth_dir / TRUTH_MANIFEST).exists():
        raise TruthContractError("Frozen truth cannot be edited.")
    if tuple(replacement.columns) != TABLE_SPECS[table].columns:
        raise TruthContractError(f"Replacement columns do not match V2 {table}.")
    truth_dir = truth_dir.absolute()
    staging = Path(tempfile.mkdtemp(
        prefix=f".{truth_dir.name}.annotation-staging-",
        dir=truth_dir.parent,
    ))
    try:
        shutil.copytree(truth_dir, staging, dirs_exist_ok=True)
        staged_table = staging / f"{table}.csv"
        _write_table(replacement, table, staged_table)
        load_truth(staging)
        if after_staging is not None:
            after_staging(staging)
        os.replace(staged_table, truth_dir / staged_table.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return load_truth(truth_dir)


def _row_frame(table: str, row: Mapping[str, str]) -> pd.DataFrame:
    spec = TABLE_SPECS[table]
    if set(row) != set(spec.columns):
        missing = sorted(set(spec.columns) - set(row))
        extra = sorted(set(row) - set(spec.columns))
        raise TruthContractError(
            f"V2 {table} row fields do not match contract; "
            f"missing={missing}, extra={extra}."
        )
    return pd.DataFrame(
        [{column: str(row[column]) for column in spec.columns}],
        columns=spec.columns,
        dtype="string",
    )


def upsert_truth_row(
    truth_dir: Path,
    table: str,
    boe_id: str,
    row: Mapping[str, str],
    *,
    original_key: Mapping[str, str] | None = None,
    source_text: str | None = None,
) -> TruthArtifact:
    if table not in EDITABLE_TABLES:
        raise ValueError(f"Table is not entity-editable: {table}")
    truth = load_truth(Path(truth_dir))
    if truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id).sum() != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")
    new_row = _row_frame(table, row)
    if str(new_row.iloc[0]["identificador_boe"]) != boe_id:
        raise TruthContractError("An edit cannot move a row to another BOE.")
    if table == "evidence_passages" and source_text is not None:
        validate_evidence_literal(str(new_row.iloc[0]["passage_text"]), source_text)

    frame = truth.tables[table].copy()
    if original_key is not None:
        mask = frame["identificador_boe"].astype(str).eq(boe_id)
        for column in TABLE_SPECS[table].key_columns:
            if column == "identificador_boe":
                continue
            if column not in original_key:
                raise TruthContractError(f"Missing original key column: {column}")
            mask &= frame[column].astype(str).eq(str(original_key[column]))
        if int(mask.sum()) != 1:
            raise TruthContractError("The V2 row selected for editing is not unique.")
        frame = frame.loc[~mask].copy()
    replacement = pd.concat([frame, new_row], ignore_index=True)

    status = str(
        truth.tables["documents"].loc[
            truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id),
            "annotation_status",
        ].iloc[0]
    )
    callback = None
    if status == "complete":
        callback = lambda staging: validate_document(
            staging, boe_id, source_text=source_text
        )
    return _commit_table_frame(
        Path(truth_dir), table, replacement, after_staging=callback
    )


def delete_truth_row(
    truth_dir: Path,
    table: str,
    boe_id: str,
    key: Mapping[str, str],
    *,
    source_text: str | None = None,
) -> TruthArtifact:
    if table not in EDITABLE_TABLES:
        raise ValueError(f"Table is not entity-editable: {table}")
    truth = load_truth(Path(truth_dir))
    frame = truth.tables[table].copy()
    mask = frame["identificador_boe"].astype(str).eq(boe_id)
    for column in TABLE_SPECS[table].key_columns:
        if column == "identificador_boe":
            continue
        if column not in key:
            raise TruthContractError(f"Missing row key column: {column}")
        mask &= frame[column].astype(str).eq(str(key[column]))
    if int(mask.sum()) != 1:
        raise TruthContractError("The V2 row selected for deletion is not unique.")
    replacement = frame.loc[~mask].copy()
    status = str(
        truth.tables["documents"].loc[
            truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id),
            "annotation_status",
        ].iloc[0]
    )
    callback = None
    if status == "complete":
        callback = lambda staging: validate_document(
            staging, boe_id, source_text=source_text
        )
    return _commit_table_frame(
        Path(truth_dir), table, replacement, after_staging=callback
    )


def update_document_scope(
    truth_dir: Path,
    boe_id: str,
    *,
    scope_applicability: str,
    scope_adjudication: str,
    expected_document_scope: str,
    annotation_notes: str,
    source_text: str | None = None,
) -> TruthArtifact:
    truth = load_truth(Path(truth_dir))
    documents = truth.tables["documents"].copy()
    mask = documents["identificador_boe"].astype(str).eq(boe_id)
    if int(mask.sum()) != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")
    documents.loc[mask, "scope_applicability"] = scope_applicability
    documents.loc[mask, "scope_adjudication"] = scope_adjudication
    documents.loc[mask, "expected_document_scope"] = expected_document_scope
    documents.loc[mask, "annotation_notes"] = annotation_notes.strip() or NA
    documents.loc[mask, "reviewed_on"] = datetime.now(timezone.utc).date().isoformat()
    callback = None
    if str(documents.loc[mask, "annotation_status"].iloc[0]) == "complete":
        callback = lambda staging: validate_document(
            staging, boe_id, source_text=source_text
        )
    return _commit_table_frame(
        Path(truth_dir), "documents", documents, after_staging=callback
    )


def mark_document_complete(
    truth_dir: Path,
    boe_id: str,
    *,
    source_text: str,
) -> TruthArtifact:
    truth = load_truth(Path(truth_dir))
    documents = truth.tables["documents"].copy()
    mask = documents["identificador_boe"].astype(str).eq(boe_id)
    if int(mask.sum()) != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")
    documents.loc[mask, "annotation_status"] = "complete"
    documents.loc[mask, "reviewed_on"] = datetime.now(timezone.utc).date().isoformat()
    return _commit_table_frame(
        Path(truth_dir),
        "documents",
        documents,
        after_staging=lambda staging: validate_document(
            staging, boe_id, source_text=source_text
        ),
    )
