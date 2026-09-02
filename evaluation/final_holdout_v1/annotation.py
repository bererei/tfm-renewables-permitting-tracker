from __future__ import annotations

import csv
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlencode

import pandas as pd

from evaluation.final_holdout_v1.contract import (
    NA,
    TABLE_SPECS,
    TRUTH_MANIFEST,
    TRUTH_METADATA,
    TruthArtifact,
    TruthContractError,
    _BOE_RE,
    _derive_source_document_identities,
    _documents_path,
    load_truth,
)
from evaluation.final_holdout_v1.matching import normalize_evidence


DEFAULT_TRUTH_DIR = Path("runs/final_holdout_p2_v1_truth_working")
DEFAULT_SOURCE_DIR = Path(
    "runs/final-corpus-preflight-20220101-20260820-v2/source"
)
TRUTH_DIR_ENV = "FINAL_HOLDOUT_ANNOTATION_TRUTH_DIR"
SOURCE_DIR_ENV = "FINAL_HOLDOUT_ANNOTATION_SOURCE_DIR"
OFFICIAL_BOE_TEXT_URL = "https://www.boe.es/diario_boe/txt.php"

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


@dataclass(frozen=True)
class AnnotationWorkspace:
    truth_dir: Path
    source_path: Path
    truth: TruthArtifact
    source_documents: pd.DataFrame


@dataclass(frozen=True)
class EntityChoice:
    owner_type: str
    owner_key: str
    event_key: str | None
    label: str

    @property
    def value(self) -> str:
        return f"{self.owner_type}:{self.owner_key}"


def configured_paths() -> tuple[Path, Path]:
    """Return the two evaluation-only inputs configured for the local UI."""

    truth_dir = Path(os.environ.get(TRUTH_DIR_ENV, str(DEFAULT_TRUTH_DIR)))
    source_dir = Path(os.environ.get(SOURCE_DIR_ENV, str(DEFAULT_SOURCE_DIR)))
    return truth_dir, source_dir


def build_official_boe_url(boe_id: str) -> str:
    """Build the official text URL from one contract-valid BOE identifier."""

    if not isinstance(boe_id, str) or _BOE_RE.fullmatch(boe_id) is None:
        raise TruthContractError("Invalid BOE identifier for official URL.")
    return f"{OFFICIAL_BOE_TEXT_URL}?{urlencode({'id': boe_id})}"


def load_annotation_workspace(
    truth_dir: Path,
    source_dir: Path,
) -> AnnotationWorkspace:
    """Load validated truth and only its matching canonical source documents."""

    truth_dir = Path(truth_dir)
    source_path = _documents_path(Path(source_dir))
    truth = load_truth(truth_dir)
    documents = truth.tables["documents"]
    boe_ids = documents["identificador_boe"].astype(str).tolist()
    if not boe_ids:
        raise TruthContractError("The annotation workspace contains no documents.")

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
            "Truth/source document membership or canonical identity mismatch."
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


def serialize_aliases(value: str) -> str:
    """Serialize one human-entered alias per line without semantic changes."""

    aliases: list[str] = []
    for line in str(value).splitlines():
        alias = line.strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    if not aliases:
        raise TruthContractError("At least one generation-asset alias is required.")
    return json.dumps(aliases, ensure_ascii=False, separators=(",", ":"))


def serialize_key_selection(values: Sequence[str]) -> str:
    """Serialize UI multiselect values as a deterministic unique JSON list."""

    selected: list[str] = []
    for value in values:
        key = str(value).strip()
        if key and key not in selected:
            selected.append(key)
    return json.dumps(selected, ensure_ascii=False, separators=(",", ":"))


def aliases_for_edit(value: str) -> str:
    parsed = json.loads(str(value))
    return "\n".join(str(item) for item in parsed)


def next_local_key(
    frame: pd.DataFrame,
    *,
    boe_id: str,
    key_column: str,
    prefix: str,
) -> str:
    """Generate prefix_N using one plus the greatest existing local integer."""

    pattern = re.compile(rf"{re.escape(prefix)}_([1-9][0-9]*)")
    used = [
        int(match.group(1))
        for value in frame.loc[
            frame["identificador_boe"].astype(str).eq(boe_id), key_column
        ].astype(str)
        if (match := pattern.fullmatch(value))
    ]
    return f"{prefix}_{max(used, default=0) + 1}"


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


def entity_choices(
    truth: TruthArtifact,
    boe_id: str,
    *,
    purpose: str,
    event_key: str | None = None,
) -> tuple[EntityChoice, ...]:
    """Return existing human truth entities eligible for an owner/target field."""

    if purpose not in {"technical_owner", "action_target", "evidence_owner"}:
        raise ValueError(f"Unknown entity-choice purpose: {purpose}")
    table_specs = {
        "event": ("events", "event_key", "event_label"),
        "generation_asset": ("generation_assets", "asset_key", "names_json"),
        "associated_component": (
            "associated_components",
            "component_key",
            "names_json",
        ),
        "technical_mention": (
            "technical_mentions",
            "technical_key",
            "expected_value_raw",
        ),
        "administrative_action": (
            "administrative_actions",
            "action_key",
            "expected_action_type",
        ),
        "participant": ("participants", "participant_key", "participant_name_raw"),
        "location": ("locations", "location_key", "location_name_raw"),
    }
    allowed_types = {
        "technical_owner": ("generation_asset", "associated_component"),
        "action_target": ("event", "generation_asset", "associated_component"),
        "evidence_owner": (
            "generation_asset",
            "associated_component",
            "technical_mention",
            "administrative_action",
            "participant",
            "location",
        ),
    }[purpose]
    choices: list[EntityChoice] = []
    for owner_type in allowed_types:
        table, key_column, label_column = table_specs[owner_type]
        rows = truth.tables[table]
        rows = rows.loc[rows["identificador_boe"].astype(str).eq(boe_id)]
        if event_key is not None and "event_key" in rows.columns:
            rows = rows.loc[rows["event_key"].astype(str).eq(event_key)]
        for _, row in rows.iterrows():
            key = str(row[key_column])
            label = str(row[label_column])
            choices.append(EntityChoice(
                owner_type=owner_type,
                owner_key=key,
                event_key=(
                    key if owner_type == "event" else str(row["event_key"])
                ),
                label=f"{owner_type} · {key} · {label}",
            ))
    return tuple(sorted(choices, key=lambda choice: (choice.owner_type, choice.owner_key)))


def derive_entity_reference(
    value: str,
    choices: Sequence[EntityChoice],
) -> tuple[str, str]:
    matches = [choice for choice in choices if choice.value == value]
    if len(matches) != 1:
        raise TruthContractError("Select one existing truth entity.")
    choice = matches[0]
    return choice.owner_type, choice.owner_key


def validate_evidence_literal(passage: str, source_text: str) -> str:
    """Validate a pasted continuous passage with frozen evidence normalization."""

    value = str(passage).strip()
    if not value or value == NA:
        raise TruthContractError("Evidence passage cannot be empty or __NA__.")
    if "[...]" in value:
        raise TruthContractError("Evidence must be one continuous source passage.")
    normalized_passage = normalize_evidence(value)
    normalized_source = normalize_evidence(source_text)
    if normalized_passage not in normalized_source:
        raise TruthContractError(
            "Evidence is not a continuous literal passage from this BOE source."
        )
    return value


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


def _validate_document_evidence(
    truth: TruthArtifact,
    boe_id: str,
    source_text: str,
) -> None:
    evidence = truth.tables["evidence_passages"]
    evidence = evidence.loc[evidence["identificador_boe"].astype(str).eq(boe_id)]
    for passage in evidence["passage_text"].astype(str):
        validate_evidence_literal(passage, source_text)


def validate_document(
    truth_dir: Path,
    boe_id: str,
    *,
    source_text: str | None = None,
) -> TruthArtifact:
    """Apply frozen completeness checks to one document without changing truth."""

    truth_dir = Path(truth_dir)
    truth = load_truth(truth_dir)
    documents = truth.tables["documents"]
    if documents["identificador_boe"].astype(str).eq(boe_id).sum() != 1:
        raise TruthContractError(f"Unknown truth document: {boe_id}")

    with tempfile.TemporaryDirectory(prefix="blind-annotation-document-") as temp:
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
            _validate_document_evidence(isolated_truth, boe_id, source_text)
        return isolated_truth


def _commit_table_frame(
    truth_dir: Path,
    table: str,
    replacement: pd.DataFrame,
    *,
    after_staging: Callable[[Path], None] | None = None,
) -> TruthArtifact:
    """Validate a full staged workspace before atomically replacing one CSV."""

    truth_dir = Path(truth_dir)
    if table not in TABLE_SPECS:
        raise ValueError(f"Unknown truth table: {table}")
    current = load_truth(truth_dir)
    if current.manifest is not None or (truth_dir / TRUTH_MANIFEST).exists():
        raise TruthContractError("Frozen truth cannot be edited.")
    if tuple(replacement.columns) != TABLE_SPECS[table].columns:
        raise TruthContractError(f"Replacement columns do not match {table}.")

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
            f"{table} row fields do not match contract; missing={missing}, extra={extra}."
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
    """Add or explicitly edit one row for one BOE through staged validation."""

    if table not in EDITABLE_TABLES:
        raise ValueError(f"Table is not entity-editable: {table}")
    truth = load_truth(Path(truth_dir))
    if truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id).sum() != 1:
        raise TruthContractError(f"Unknown truth document: {boe_id}")
    new_row = _row_frame(table, row)
    if str(new_row.iloc[0]["identificador_boe"]) != boe_id:
        raise TruthContractError("An edit cannot move a row to another BOE.")

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
            raise TruthContractError("The row selected for editing no longer exists uniquely.")
        frame = frame.loc[~mask].copy()
    replacement = pd.concat([frame, new_row], ignore_index=True)

    document_status = str(
        truth.tables["documents"].loc[
            truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id),
            "annotation_status",
        ].iloc[0]
    )
    callback = None
    if document_status == "complete":
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
    """Delete one explicitly selected row; foreign keys fail closed."""

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
        raise TruthContractError("The row selected for deletion no longer exists uniquely.")
    replacement = frame.loc[~mask].copy()

    document_status = str(
        truth.tables["documents"].loc[
            truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id),
            "annotation_status",
        ].iloc[0]
    )
    callback = None
    if document_status == "complete":
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
        raise TruthContractError(f"Unknown truth document: {boe_id}")
    documents.loc[mask, "scope_applicability"] = scope_applicability
    documents.loc[mask, "scope_adjudication"] = scope_adjudication
    documents.loc[mask, "expected_document_scope"] = expected_document_scope
    documents.loc[mask, "annotation_notes"] = annotation_notes.strip() or NA
    documents.loc[mask, "reviewed_on"] = datetime.now(timezone.utc).date().isoformat()

    status = str(documents.loc[mask, "annotation_status"].iloc[0])
    callback = None
    if status == "complete":
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
        raise TruthContractError(f"Unknown truth document: {boe_id}")
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
