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
    _scored,
    load_truth,
    parse_json_list,
)
from evaluation.final_holdout_v2.terminology import (
    canonical_path,
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
_PRIMARY_QA_TABLES_BEFORE_ACTION_EVIDENCE = (
    "documents",
    "events",
    "generation_assets",
    "administrative_actions",
)
_RESERVED_LOCAL_KEY_VALUES = frozenset({"pending"})
_PRIMARY_MUTATION_TABLES = frozenset({
    "events",
    "generation_assets",
    "administrative_actions",
    "locations",
})


@dataclass(frozen=True)
class ActionDeletionImpact:
    """Direct rows removed with one administrative action."""

    action_key: str
    evidence_count: int
    target_count: int


@dataclass(frozen=True)
class AnnotationValidationFeedback:
    """Human-facing context for one authoritative contract failure."""

    message: str
    section: str
    canonical_path: str | None


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


def action_evidence_rows(
    truth: TruthArtifact,
    boe_id: str,
    *,
    action_key: str | None = None,
) -> pd.DataFrame:
    """Return only administrative-action evidence for the primary V2 UI."""

    evidence = _selected_rows(truth, "evidence_passages", boe_id)
    selected = evidence.loc[
        evidence["owner_type"].astype(str).eq("administrative_action")
    ]
    if action_key is not None:
        selected = selected.loc[
            selected["owner_key"].astype(str).eq(str(action_key))
        ]
    return selected.copy()


def secondary_evidence_rows(
    truth: TruthArtifact,
    boe_id: str,
) -> pd.DataFrame:
    """Return non-action evidence retained only as optional V2 diagnostics."""

    evidence = _selected_rows(truth, "evidence_passages", boe_id)
    return evidence.loc[
        ~evidence["owner_type"].astype(str).eq("administrative_action")
    ].copy()


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
    heading: str,
) -> None:
    lines.extend((f"### {heading}", ""))
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
    for table in _PRIMARY_QA_TABLES_BEFORE_ACTION_EVIDENCE:
        _append_field_rows(
            lines,
            truth=truth,
            boe_id=boe_id,
            table=table,
            fields=_PRIMARY_FIELDS[table],
        )

    _append_evidence_rows(
        lines,
        selected=action_evidence_rows(truth, boe_id),
        heading="Evidencias de actuaciones administrativas",
    )
    _append_field_rows(
        lines,
        truth=truth,
        boe_id=boe_id,
        table="locations",
        fields=_PRIMARY_FIELDS["locations"],
    )

    lines.extend((
        "## Datos secundarios / diagnósticos — no bloqueantes",
        "",
        "Estos datos no forman parte de los requisitos de completitud V2.",
        "",
    ))
    for table in _SECONDARY_TABLES:
        _append_secondary_table(lines, truth, boe_id, table)
    _append_evidence_rows(
        lines,
        selected=secondary_evidence_rows(truth, boe_id),
        heading="Otras evidencias — secundarias / diagnósticas",
    )

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


def _semantic_frame(frame: pd.DataFrame, table: str) -> pd.DataFrame:
    spec = TABLE_SPECS[table]
    if frame.empty:
        return frame.loc[:, list(spec.columns)].reset_index(drop=True)
    return (
        frame.loc[:, list(spec.columns)]
        .sort_values(list(spec.key_columns), kind="stable")
        .reset_index(drop=True)
        .astype("string")
    )


def _semantic_table_changed(
    current: pd.DataFrame,
    candidate: pd.DataFrame,
    table: str,
) -> bool:
    return not _semantic_frame(current, table).equals(
        _semantic_frame(candidate, table)
    )


def _downgrade_complete_document(
    current: TruthArtifact,
    replacements: Mapping[str, pd.DataFrame],
    boe_id: str,
) -> dict[str, pd.DataFrame]:
    prepared = dict(replacements)
    if not any(
        _semantic_table_changed(current.tables[table], candidate, table)
        for table, candidate in prepared.items()
    ):
        return prepared
    documents = prepared.get("documents", current.tables["documents"]).copy()
    mask = documents["identificador_boe"].astype(str).eq(boe_id)
    if int(mask.sum()) != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")
    if str(documents.loc[mask, "annotation_status"].iloc[0]) == "complete":
        documents.loc[mask, "annotation_status"] = "draft"
        prepared["documents"] = documents
    return prepared


def _commit_table_frames(
    truth_dir: Path,
    replacements: Mapping[str, pd.DataFrame],
    *,
    after_staging: Callable[[Path], None] | None = None,
    primary_change_boe_id: str | None = None,
) -> TruthArtifact:
    truth_dir = Path(truth_dir)
    if not replacements:
        raise ValueError("At least one V2 truth table replacement is required.")
    current = load_truth(truth_dir)
    if current.manifest is not None or (truth_dir / TRUTH_MANIFEST).exists():
        raise TruthContractError("Frozen truth cannot be edited.")
    if primary_change_boe_id is not None:
        replacements = _downgrade_complete_document(
            current,
            replacements,
            primary_change_boe_id,
        )
    for table, replacement in replacements.items():
        if table not in TABLE_SPECS:
            raise ValueError(f"Unknown V2 truth table: {table}")
        if tuple(replacement.columns) != TABLE_SPECS[table].columns:
            raise TruthContractError(f"Replacement columns do not match V2 {table}.")
    truth_dir = truth_dir.absolute()
    staging = Path(tempfile.mkdtemp(
        prefix=f".{truth_dir.name}.annotation-staging-",
        dir=truth_dir.parent,
    ))
    try:
        shutil.copytree(truth_dir, staging, dirs_exist_ok=True)
        for table, replacement in replacements.items():
            _write_table(replacement, table, staging / f"{table}.csv")
        load_truth(staging)
        if after_staging is not None:
            after_staging(staging)

        if len(replacements) == 1:
            table = next(iter(replacements))
            os.replace(
                staging / f"{table}.csv",
                truth_dir / f"{table}.csv",
            )
        else:
            backup_dir = staging.with_name(f"{staging.name}.original")
            os.replace(truth_dir, backup_dir)
            try:
                os.replace(staging, truth_dir)
            except BaseException:
                os.replace(backup_dir, truth_dir)
                raise
            else:
                shutil.rmtree(backup_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return load_truth(truth_dir)


def _commit_table_frame(
    truth_dir: Path,
    table: str,
    replacement: pd.DataFrame,
    *,
    after_staging: Callable[[Path], None] | None = None,
    primary_change_boe_id: str | None = None,
) -> TruthArtifact:
    return _commit_table_frames(
        truth_dir,
        {table: replacement},
        after_staging=after_staging,
        primary_change_boe_id=primary_change_boe_id,
    )


def _row_frame(table: str, row: Mapping[str, str]) -> pd.DataFrame:
    spec = TABLE_SPECS[table]
    if set(row) != set(spec.columns):
        missing = sorted(set(spec.columns) - set(row))
        extra = sorted(set(row) - set(spec.columns))
        raise TruthContractError(
            f"V2 {table} row fields do not match contract; "
            f"missing={missing}, extra={extra}."
        )
    for column in spec.columns:
        if not column.endswith("_key"):
            continue
        value = str(row[column]).strip()
        if (
            value.casefold() in _RESERVED_LOCAL_KEY_VALUES
            or (value.startswith("<") and value.endswith(">"))
        ):
            raise TruthContractError(
                f"Reserved annotation placeholder cannot be persisted as "
                f"{table}.{column}: {value!r}."
            )
    return pd.DataFrame(
        [{column: str(row[column]) for column in spec.columns}],
        columns=spec.columns,
        dtype="string",
    )


def _replacement_with_row(
    truth: TruthArtifact,
    table: str,
    boe_id: str,
    new_row: pd.DataFrame,
    *,
    original_key: Mapping[str, str] | None,
) -> pd.DataFrame:
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
    return pd.concat([frame, new_row], ignore_index=True)


def _is_primary_row(table: str, row: Mapping[str, object]) -> bool:
    return table in _PRIMARY_MUTATION_TABLES or (
        table == "evidence_passages"
        and str(row["owner_type"]) == "administrative_action"
    )


def _canonical_row_reference(table: str, row: Mapping[str, object]) -> str:
    if table == "action_targets":
        return (
            f"{qa_path(table, row, 'target_type')}="
            f"{row['target_type']}:{row['target_truth_key']}"
        )
    if table == "evidence_passages":
        return qa_path(table, row, "passage_text")
    field = next(
        column
        for column in TABLE_SPECS[table].columns
        if column not in {"identificador_boe", *TABLE_SPECS[table].key_columns}
    )
    return qa_path(table, row, field).rsplit(".", 1)[0]


def deletion_dependencies(
    truth: TruthArtifact,
    table: str,
    boe_id: str,
    key: Mapping[str, str],
) -> tuple[str, ...]:
    """List canonical references that make an event/asset deletion unsafe."""

    references: list[str] = []
    if table == "events":
        event_key = str(key.get("event_key", ""))
        for child_table in (
            "generation_assets",
            "associated_components",
            "technical_mentions",
            "administrative_actions",
            "action_targets",
            "participants",
            "locations",
        ):
            children = truth.tables[child_table]
            selected = children.loc[
                children["identificador_boe"].astype(str).eq(boe_id)
                & children["event_key"].astype(str).eq(event_key)
            ]
            references.extend(
                _canonical_row_reference(child_table, row)
                for _, row in selected.iterrows()
            )
    elif table == "generation_assets":
        asset_key = str(key.get("asset_key", ""))
        actions = truth.tables["administrative_actions"]
        for _, row in actions.loc[
            actions["identificador_boe"].astype(str).eq(boe_id)
        ].iterrows():
            affected = parse_json_list(
                str(row["expected_affected_generation_asset_keys_json"]),
                label="expected_affected_generation_asset_keys_json",
                allow_empty=True,
            )
            if asset_key in affected:
                references.append(
                    qa_path(
                        "administrative_actions",
                        row,
                        "expected_affected_generation_asset_keys_json",
                    )
                )
        components = truth.tables["associated_components"]
        for _, row in components.loc[
            components["identificador_boe"].astype(str).eq(boe_id)
        ].iterrows():
            related = parse_json_list(
                str(row["related_asset_keys_json"]),
                label="related_asset_keys_json",
                allow_empty=True,
            )
            if asset_key in related:
                references.append(
                    qa_path("associated_components", row, "related_asset_keys_json")
                )
        for child_table, owner_type in (
            ("technical_mentions", "generation_asset"),
            ("evidence_passages", "generation_asset"),
        ):
            children = truth.tables[child_table]
            selected = children.loc[
                children["identificador_boe"].astype(str).eq(boe_id)
                & children["owner_type"].astype(str).eq(owner_type)
                & children["owner_key"].astype(str).eq(asset_key)
            ]
            references.extend(
                _canonical_row_reference(child_table, row)
                for _, row in selected.iterrows()
            )
        targets = truth.tables["action_targets"]
        selected_targets = targets.loc[
            targets["identificador_boe"].astype(str).eq(boe_id)
            & targets["target_type"].astype(str).eq("generation_asset")
            & targets["target_truth_key"].astype(str).eq(asset_key)
        ]
        references.extend(
            _canonical_row_reference("action_targets", row)
            for _, row in selected_targets.iterrows()
        )
    return tuple(sorted(set(references)))


def action_deletion_impact(
    truth: TruthArtifact,
    boe_id: str,
    action_key: str,
) -> ActionDeletionImpact:
    actions = truth.tables["administrative_actions"]
    action_count = int(
        (
            actions["identificador_boe"].astype(str).eq(boe_id)
            & actions["action_key"].astype(str).eq(action_key)
        ).sum()
    )
    if action_count != 1:
        raise TruthContractError(
            f"La actuación {action_key} no existe de forma única en {boe_id}."
        )
    evidence = action_evidence_rows(truth, boe_id, action_key=action_key)
    targets = truth.tables["action_targets"]
    target_count = int(
        (
            targets["identificador_boe"].astype(str).eq(boe_id)
            & targets["action_key"].astype(str).eq(action_key)
        ).sum()
    )
    return ActionDeletionImpact(
        action_key=action_key,
        evidence_count=len(evidence),
        target_count=target_count,
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

    replacement = _replacement_with_row(
        truth,
        table,
        boe_id,
        new_row,
        original_key=original_key,
    )

    primary_change_boe_id = (
        boe_id
        if _is_primary_row(table, new_row.iloc[0].to_dict())
        else None
    )
    return _commit_table_frame(
        Path(truth_dir),
        table,
        replacement,
        primary_change_boe_id=primary_change_boe_id,
    )


def action_has_scored_evidence(
    truth: TruthArtifact,
    boe_id: str,
    action_key: str,
) -> bool:
    """Return whether an action already has contract-scored literal evidence."""

    return not _scored(
        action_evidence_rows(truth, boe_id, action_key=action_key)
    ).empty


def upsert_action_with_initial_evidence(
    truth_dir: Path,
    boe_id: str,
    action_row: Mapping[str, str],
    *,
    evidence_passage: str | None,
    original_key: Mapping[str, str] | None = None,
    source_text: str,
) -> TruthArtifact:
    """Stage and persist an action and any required first evidence together."""

    evidence_rows: list[Mapping[str, str]] = []
    if original_key is not None:
        truth = load_truth(Path(truth_dir))
        evidence_rows.extend(
            row.to_dict()
            for _, row in action_evidence_rows(
                truth,
                boe_id,
                action_key=str(original_key["action_key"]),
            ).iterrows()
        )
    if evidence_passage is not None and str(evidence_passage).strip():
        evidence_rows.append({"passage_text": str(evidence_passage)})
    return upsert_action_with_evidence_set(
        truth_dir,
        boe_id,
        action_row,
        evidence_rows=evidence_rows,
        original_key=original_key,
        source_text=source_text,
    )


def upsert_action_with_evidence_set(
    truth_dir: Path,
    boe_id: str,
    action_row: Mapping[str, str],
    *,
    evidence_rows: Sequence[Mapping[str, str]],
    original_key: Mapping[str, str] | None = None,
    source_text: str,
) -> TruthArtifact:
    """Persist one action and its complete action-evidence set atomically."""

    truth_dir = Path(truth_dir)
    truth = load_truth(truth_dir)
    if truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id).sum() != 1:
        raise TruthContractError(f"Unknown V2 truth document: {boe_id}")

    action_values = dict(action_row)
    if original_key is None:
        action_values["action_key"] = next_key_for_table(
            truth,
            "administrative_actions",
            boe_id,
        )
    elif str(action_values.get("action_key")) != str(
        original_key.get("action_key")
    ):
        raise TruthContractError(
            "La clave persistida de una actuación no puede cambiar al editarla."
        )
    new_action = _row_frame("administrative_actions", action_values)
    if str(new_action.iloc[0]["identificador_boe"]) != boe_id:
        raise TruthContractError("An edit cannot move a row to another BOE.")
    action_key = str(new_action.iloc[0]["action_key"])
    actions = _replacement_with_row(
        truth,
        "administrative_actions",
        boe_id,
        new_action,
        original_key=original_key,
    )

    prepared_evidence: list[pd.DataFrame] = []
    seen_passages: set[str] = set()
    for candidate in evidence_rows:
        raw_passage = str(candidate.get("passage_text", ""))
        if not raw_passage.strip():
            continue
        passage = validate_evidence_literal(raw_passage, source_text)
        if passage in seen_passages:
            raise TruthContractError(
                "No se puede guardar dos veces el mismo pasaje de evidencia."
            )
        seen_passages.add(passage)
        prepared_evidence.append(
            _row_frame(
                "evidence_passages",
                {
                    "identificador_boe": boe_id,
                    "owner_type": "administrative_action",
                    "owner_key": action_key,
                    "passage_text": passage,
                    "applicability": str(
                        candidate.get(
                            "applicability",
                            new_action.iloc[0]["applicability"],
                        )
                    ),
                    "adjudication": str(
                        candidate.get(
                            "adjudication",
                            new_action.iloc[0]["adjudication"],
                        )
                    ),
                    "annotation_notes": str(
                        candidate.get("annotation_notes", NA)
                    ),
                },
            )
        )

    candidate_evidence = (
        pd.concat(prepared_evidence, ignore_index=True)
        if prepared_evidence
        else pd.DataFrame(
            columns=TABLE_SPECS["evidence_passages"].columns,
            dtype="string",
        )
    )
    if not _scored(new_action).empty and _scored(candidate_evidence).empty:
        raise TruthContractError(
            "Cada actuación primaria puntuada necesita al menos un pasaje literal "
            "continuo del BOE; proporciona la evidencia en la misma operación."
        )

    current_evidence = truth.tables["evidence_passages"]
    selected_evidence = (
        current_evidence["identificador_boe"].astype(str).eq(boe_id)
        & current_evidence["owner_type"].astype(str).eq(
            "administrative_action"
        )
        & current_evidence["owner_key"].astype(str).eq(action_key)
    )
    replacements: dict[str, pd.DataFrame] = {
        "administrative_actions": actions,
        "evidence_passages": pd.concat(
            [current_evidence.loc[~selected_evidence].copy(), candidate_evidence],
            ignore_index=True,
        ),
    }

    return _commit_table_frames(
        truth_dir,
        replacements,
        primary_change_boe_id=boe_id,
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
    if table == "administrative_actions":
        action_key = key.get("action_key")
        if action_key is None:
            raise TruthContractError("Missing row key column: action_key")
        return delete_administrative_action(
            truth_dir,
            boe_id,
            str(action_key),
        )
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
    dependencies = deletion_dependencies(truth, table, boe_id, key)
    if dependencies:
        entity = table_entity(table)
        key_field = table_key_field(table)
        local_key = None if key_field is None else str(key[key_field])
        target = canonical_path(entity, local_key=local_key)
        raise TruthContractError(
            f"No se puede eliminar {target}; primero elimina o reasigna estas "
            f"referencias: {', '.join(dependencies)}."
        )
    replacement = frame.loc[~mask].copy()
    selected = frame.loc[mask].iloc[0]
    if (
        table == "evidence_passages"
        and str(selected["owner_type"]) == "administrative_action"
        and not _scored(pd.DataFrame([selected])).empty
    ):
        action_key = str(selected["owner_key"])
        actions = truth.tables["administrative_actions"]
        action = actions.loc[
            actions["identificador_boe"].astype(str).eq(boe_id)
            & actions["action_key"].astype(str).eq(action_key)
        ]
        remaining = replacement.loc[
            replacement["identificador_boe"].astype(str).eq(boe_id)
            & replacement["owner_type"].astype(str).eq("administrative_action")
            & replacement["owner_key"].astype(str).eq(action_key)
        ]
        if not _scored(action).empty and _scored(remaining).empty:
            raise TruthContractError(
                "No se puede eliminar la última evidencia literal puntuada de "
                "una actuación primaria puntuada."
            )
    primary_change_boe_id = (
        boe_id if _is_primary_row(table, selected.to_dict()) else None
    )
    return _commit_table_frame(
        Path(truth_dir),
        table,
        replacement,
        primary_change_boe_id=primary_change_boe_id,
    )


def delete_administrative_action(
    truth_dir: Path,
    boe_id: str,
    action_key: str,
) -> TruthArtifact:
    """Delete one action and only its direct evidence/target children atomically."""

    truth_dir = Path(truth_dir)
    truth = load_truth(truth_dir)
    action_deletion_impact(truth, boe_id, action_key)

    actions = truth.tables["administrative_actions"]
    action_mask = (
        actions["identificador_boe"].astype(str).eq(boe_id)
        & actions["action_key"].astype(str).eq(action_key)
    )
    evidence = truth.tables["evidence_passages"]
    evidence_mask = (
        evidence["identificador_boe"].astype(str).eq(boe_id)
        & evidence["owner_type"].astype(str).eq("administrative_action")
        & evidence["owner_key"].astype(str).eq(action_key)
    )
    targets = truth.tables["action_targets"]
    target_mask = (
        targets["identificador_boe"].astype(str).eq(boe_id)
        & targets["action_key"].astype(str).eq(action_key)
    )
    return _commit_table_frames(
        truth_dir,
        {
            "administrative_actions": actions.loc[~action_mask].copy(),
            "evidence_passages": evidence.loc[~evidence_mask].copy(),
            "action_targets": targets.loc[~target_mask].copy(),
        },
        primary_change_boe_id=boe_id,
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
    updates = {
        "scope_applicability": scope_applicability,
        "scope_adjudication": scope_adjudication,
        "expected_document_scope": expected_document_scope,
        "annotation_notes": annotation_notes.strip() or NA,
    }
    changed = any(
        str(documents.loc[mask, column].iloc[0]) != value
        for column, value in updates.items()
    )
    for column, value in updates.items():
        documents.loc[mask, column] = value
    if changed:
        documents.loc[mask, "reviewed_on"] = (
            datetime.now(timezone.utc).date().isoformat()
        )
    return _commit_table_frame(
        Path(truth_dir),
        "documents",
        documents,
        primary_change_boe_id=boe_id,
    )


def _first_incomplete_event(
    truth: TruthArtifact,
    boe_id: str,
    child_table: str,
) -> str | None:
    events = _scored(_selected_rows(truth, "events", boe_id))
    children = _scored(_selected_rows(truth, child_table, boe_id))
    for event_key in events["event_key"].astype(str):
        if children.loc[
            children["event_key"].astype(str).eq(event_key)
        ].empty:
            return event_key
    return None


def _first_incomplete_action(
    truth: TruthArtifact,
    boe_id: str,
    *,
    field: str | None = None,
) -> str | None:
    actions = _scored(_selected_rows(truth, "administrative_actions", boe_id))
    if field is not None:
        if field == "expected_affected_generation_asset_keys_json":
            actions = actions.loc[
                actions[field].astype(str).map(
                    lambda value: not parse_json_list(
                        value,
                        label=field,
                        allow_empty=True,
                    )
                )
            ]
        else:
            actions = actions.loc[actions[field].astype(str).eq(NA)]
    else:
        evidence = _scored(action_evidence_rows(truth, boe_id))
        supported = set(evidence["owner_key"].astype(str))
        actions = actions.loc[
            ~actions["action_key"].astype(str).isin(supported)
        ]
    if actions.empty:
        return None
    return str(actions.iloc[0]["action_key"])


def validation_error_feedback(
    error: BaseException,
    truth: TruthArtifact,
    boe_id: str,
) -> AnnotationValidationFeedback:
    """Translate common validator failures without replacing the validator."""

    raw = str(error)
    if raw.startswith((
        "No se puede ",
        "Selecciona ",
        "Cada actuación ",
        "La actuación ",
        "Completa y valida ",
        "Confirma ",
    )):
        return AnnotationValidationFeedback(
            message=raw,
            section="Sección actual",
            canonical_path=None,
        )
    if raw in {
        "Evidence passage cannot be empty or __NA__.",
        "Evidence must be one continuous source passage.",
        "Evidence is not a continuous literal passage from this BOE source.",
    }:
        return AnnotationValidationFeedback(
            message=(
                "La evidencia debe ser un único pasaje continuo y literal copiado "
                "de la fuente local. No se guardó ningún cambio."
            ),
            section=(
                "4. Actuaciones administrativas o 7. Opcional / diagnóstico"
            ),
            canonical_path=None,
        )
    if "contains duplicate truth keys" in raw:
        return AnnotationValidationFeedback(
            message=(
                "La fila ya existe con la misma clave canónica. Selecciona Editar "
                "para modificarla o introduce una evidencia distinta."
            ),
            section="Sección actual",
            canonical_path=None,
        )
    if raw == "An administrative action references an unknown affected asset.":
        return AnnotationValidationFeedback(
            message=(
                "La actuación referencia un activo que ya no existe. Selecciona "
                "los activos afectados en 4. Actuaciones administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=None,
        )
    if raw == "An action and its affected assets must belong to the same event.":
        return AnnotationValidationFeedback(
            message=(
                "La actuación y todos sus activos afectados deben pertenecer al "
                "mismo evento. Revisa el evento y el multiselect de activos en "
                "4. Actuaciones administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=None,
        )
    if raw == "Scored administrative-action evidence requires a scored action.":
        return AnnotationValidationFeedback(
            message=(
                "Antes de dejar una actuación fuera de puntuación, revisa sus "
                "evidencias puntuadas en 4. Actuaciones administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=None,
        )
    if raw == "Every scored V2 event needs a scored generation asset.":
        event_key = _first_incomplete_event(
            truth, boe_id, "generation_assets"
        ) or "evento seleccionado"
        path = (
            canonical_path("event", local_key=event_key)
            if event_key.startswith("event_")
            else None
        )
        return AnnotationValidationFeedback(
            message=(
                f"El evento {event_key} necesita al menos un activo de generación "
                "puntuable. Revísalo en 3. Activos de generación."
            ),
            section="3. Activos de generación",
            canonical_path=path,
        )
    if raw == "Every scored V2 event needs a scored administrative action.":
        event_key = _first_incomplete_event(
            truth, boe_id, "administrative_actions"
        ) or "evento seleccionado"
        path = (
            canonical_path("event", local_key=event_key)
            if event_key.startswith("event_")
            else None
        )
        return AnnotationValidationFeedback(
            message=(
                f"El evento {event_key} necesita al menos una actuación "
                "administrativa puntuable. Revísalo en 4. Actuaciones administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=path,
        )
    if raw == "Every scored V2 action needs scored action-specific evidence.":
        action_key = _first_incomplete_action(truth, boe_id) or "actuación seleccionada"
        path = (
            canonical_path(
                "evidence_passage",
                owner_entity="administrative_action",
                local_key=action_key,
            )
            if action_key.startswith("action_")
            else None
        )
        return AnnotationValidationFeedback(
            message=(
                f"La actuación {action_key} necesita al menos una evidencia literal "
                "de actuación antes de completar el documento. Revísala en "
                "4. Actuaciones administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=path,
        )
    action_fields = {
        "expected_action_type": "el tipo de actuación",
        "expected_decision": "la decisión",
        "expected_is_modification": "si es modificación",
    }
    for field, label in action_fields.items():
        if raw == f"Every scored V2 action needs {field}.":
            action_key = _first_incomplete_action(
                truth, boe_id, field=field
            ) or "actuación seleccionada"
            path = (
                canonical_path(
                    "administrative_action",
                    local_key=action_key,
                    field=field,
                )
                if action_key.startswith("action_")
                else None
            )
            return AnnotationValidationFeedback(
                message=(
                    f"La actuación {action_key} necesita indicar {label}. "
                    "Revísala en 4. Actuaciones administrativas."
                ),
                section="4. Actuaciones administrativas",
                canonical_path=path,
            )
    if raw == (
        "Every scored V2 action needs explicit affected-generation-asset attribution."
    ):
        field = "expected_affected_generation_asset_keys_json"
        action_key = _first_incomplete_action(
            truth, boe_id, field=field
        ) or "actuación seleccionada"
        path = (
            canonical_path(
                "administrative_action",
                local_key=action_key,
                field=field,
            )
            if action_key.startswith("action_")
            else None
        )
        return AnnotationValidationFeedback(
            message=(
                f"La actuación {action_key} necesita seleccionar explícitamente sus "
                "activos de generación afectados. Revísala en 4. Actuaciones "
                "administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=path,
        )
    if raw == (
        "Every scored V2 action needs current, historical or explicit ambiguity."
    ):
        actions = _scored(_selected_rows(truth, "administrative_actions", boe_id))
        invalid = actions.loc[actions["temporal_status"].astype(str).eq("not_applicable")]
        action_key = (
            str(invalid.iloc[0]["action_key"])
            if not invalid.empty
            else "actuación seleccionada"
        )
        path = (
            canonical_path(
                "administrative_action",
                local_key=action_key,
                field="temporal_status",
            )
            if action_key.startswith("action_")
            else None
        )
        return AnnotationValidationFeedback(
            message=(
                f"La actuación {action_key} necesita una temporalidad current, "
                "historical_antecedent o ambigua explícita. Revísala en "
                "4. Actuaciones administrativas."
            ),
            section="4. Actuaciones administrativas",
            canonical_path=path,
        )
    if raw == "A project-specific V2 document needs at least one scored event.":
        return AnnotationValidationFeedback(
            message=(
                "El documento está marcado como específico de proyecto, pero necesita "
                "al menos un evento puntuable. Revísalo en 2. Eventos / proyectos "
                "publicados."
            ),
            section="2. Eventos / proyectos publicados",
            canonical_path="document.expected_document_scope",
        )
    if raw == "A complete V2 document requires scored scope.":
        return AnnotationValidationFeedback(
            message=(
                "Completa la evaluación del alcance en 1. Documento: aplicabilidad "
                "`applicable`, adjudicación `scored_truth` y un alcance explícito."
            ),
            section="1. Documento",
            canonical_path="document.expected_document_scope",
        )
    if raw == "A complete non-relevant document cannot contain primary scored entities.":
        return AnnotationValidationFeedback(
            message=(
                "El documento se ha marcado como no relevante, pero todavía contiene "
                "entidades primarias puntuables. Revísalas antes de completar."
            ),
            section="1–6. Verdad primaria",
            canonical_path="document.expected_document_scope",
        )
    return AnnotationValidationFeedback(
        message=(
            "No se pudo validar el cambio. Revisa la entidad y sus relaciones en la "
            "sección actual."
        ),
        section="Sección actual",
        canonical_path=None,
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
