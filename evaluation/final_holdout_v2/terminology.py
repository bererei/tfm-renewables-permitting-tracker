from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from evaluation.final_holdout_v2.contract import (
    CONTRACT_DECLARATION_PATH,
    TruthContractError,
)


@lru_cache(maxsize=1)
def terminology_registry() -> Mapping[str, Any]:
    declaration = json.loads(
        Path(CONTRACT_DECLARATION_PATH).read_text(encoding="utf-8")
    )
    registry = declaration.get("terminology")
    if not isinstance(registry, dict):
        raise TruthContractError("V2 contract has no terminology registry.")
    return registry


def entity_label(entity: str) -> str:
    try:
        return str(terminology_registry()["entities"][entity])
    except KeyError as error:
        raise TruthContractError(f"Unknown canonical entity: {entity}") from error


def canonical_path(
    entity: str,
    *,
    local_key: str | None = None,
    field: str | None = None,
    owner_entity: str | None = None,
) -> str:
    if entity == "document":
        if local_key is not None or field is None:
            raise TruthContractError("Document paths require one field and no key.")
        return f"document.{field}"
    if entity == "evidence_passage":
        if owner_entity is None or local_key is None or field is not None:
            raise TruthContractError(
                "Evidence paths require owner entity/key and no field."
            )
        return f"evidence_passage/{owner_entity}/{local_key}"
    if local_key is None:
        raise TruthContractError(f"{entity} paths require a local key.")
    base = f"{entity}/{local_key}"
    return base if field is None else f"{base}.{field}"


def field_label(entity: str, field: str) -> str:
    try:
        return str(terminology_registry()["fields"][entity][field])
    except KeyError as error:
        raise TruthContractError(
            f"Unknown canonical field: {entity}.{field}"
        ) from error


def table_entity(table: str) -> str:
    try:
        return str(terminology_registry()["tables"][table]["entity"])
    except KeyError as error:
        raise TruthContractError(f"Unknown truth table: {table}") from error


def table_key_field(table: str) -> str | None:
    try:
        value = terminology_registry()["tables"][table]["key_field"]
    except KeyError as error:
        raise TruthContractError(f"Unknown truth table: {table}") from error
    return None if value is None else str(value)


def row_local_key(table: str, row: Mapping[str, object]) -> str | None:
    key_field = table_key_field(table)
    return None if key_field is None else str(row[str(key_field)])


def qa_path(table: str, row: Mapping[str, object], field: str) -> str:
    entity = table_entity(table)
    if entity == "document":
        return canonical_path(entity, field=field)
    if entity == "evidence_passage":
        return canonical_path(
            entity,
            local_key=str(row["owner_key"]),
            owner_entity=str(row["owner_type"]),
        )
    if entity == "action_target":
        return canonical_path(
            entity,
            local_key=str(row["action_key"]),
            field="target" if field in {"target_type", "target_truth_key"} else field,
        )
    return canonical_path(
        entity,
        local_key=row_local_key(table, row),
        field=field,
    )


def widget_label(entity: str, field: str, *, local_key: str | None = None) -> str:
    path = canonical_path(entity, local_key=local_key, field=field)
    return f"{field_label(entity, field)} · {path}"
