from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

import pandas as pd

from renewables_permitting.utils import (
    is_null_like,
    normalize_text_or_none,
    validate_required_columns,
)


PROJECT_GROUPING_COLUMNS = (
    "generation_asset_mention_id",
    "project_id",
    "project_match_key",
    "project_match_method",
)

_ASSET_COLUMNS = {
    "event_id",
    "generation_asset_mention_id",
    "generation_type",
}
_NAME_COLUMNS = {
    "event_id",
    "generation_asset_mention_id",
    "name_index",
    "name_raw",
}
_LOCATION_COLUMNS = {
    "event_id",
    "ine_province_code",
    "province_resolution_status",
    "ine_autonomous_community_code",
    "autonomous_community_resolution_status",
}

_SAFE_LOCATION_STATUSES = {"resolved", "not_found", "not_provided"}
_UNSAFE_LOCATION_STATUSES = {"ambiguous", "conflict"}
_PROJECT_NAMESPACE = UUID("89295561-461b-54c3-91bd-22944e68357f")
_MATCH_KEY_VERSION = "v1"

# Solo se eliminan descriptores al comienzo del nombre. Los números, numerales,
# puntos cardinales y cualquier token posterior permanecen como identidad.
_GENERATION_NAME_PREFIX_TOKENS = {
    "central",
    "de",
    "denominada",
    "denominado",
    "eolica",
    "eolico",
    "existente",
    "fotovoltaica",
    "fotovoltaico",
    "fv",
    "generacion",
    "hibrida",
    "hibrido",
    "hidroelectrica",
    "hidroelectrico",
    "instalacion",
    "modulo",
    "parque",
    "pe",
    "pfv",
    "planta",
    "proyecto",
    "psf",
    "psfv",
    "solar",
    "termosolar",
}


@dataclass(frozen=True)
class _NameIdentity:
    key: str
    full_names: frozenset[str]


def _validate_no_duplicate_columns(frame: pd.DataFrame, name: str) -> None:
    if not frame.columns.duplicated().any():
        return
    duplicates = frame.columns[
        frame.columns.duplicated(keep=False)
    ].tolist()
    raise ValueError(f"{name} contiene columnas duplicadas: {duplicates}")


def _validate_inputs(
    generation_asset_mentions: pd.DataFrame,
    generation_asset_names: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> None:
    inputs = (
        (
            generation_asset_mentions,
            "generation_asset_mentions",
            _ASSET_COLUMNS,
        ),
        (generation_asset_names, "generation_asset_names", _NAME_COLUMNS),
        (resolved_locations, "resolved_locations", _LOCATION_COLUMNS),
    )
    for frame, name, columns in inputs:
        _validate_no_duplicate_columns(frame, name)
        validate_required_columns(frame, columns)

    mention_ids = generation_asset_mentions["generation_asset_mention_id"]
    if mention_ids.isna().any() or mention_ids.astype("string").str.strip().eq("").any():
        raise ValueError("generation_asset_mention_id no puede contener nulos o vacíos.")
    if mention_ids.duplicated().any():
        raise ValueError("generation_asset_mention_id debe ser único.")

    if generation_asset_mentions[["event_id", "generation_type"]].isna().any().any():
        raise ValueError("event_id y generation_type no pueden contener nulos.")

    name_key = ["generation_asset_mention_id", "name_index"]
    if generation_asset_names[name_key].isna().any().any():
        raise ValueError("La clave de generation_asset_names no puede contener nulos.")
    if generation_asset_names.duplicated(name_key).any():
        raise ValueError("generation_asset_names contiene claves duplicadas.")
    if generation_asset_names["name_raw"].isna().any() or generation_asset_names[
        "name_raw"
    ].astype("string").str.strip().eq("").any():
        raise ValueError("name_raw no puede contener nulos o vacíos.")

    asset_ids = set(mention_ids.astype(str))
    name_ids = set(
        generation_asset_names["generation_asset_mention_id"].astype(str)
    )
    if name_ids - asset_ids:
        raise ValueError("generation_asset_names contiene menciones huérfanas.")
    if asset_ids - name_ids:
        raise ValueError("Cada mención de generación debe tener al menos un nombre.")

    asset_events = generation_asset_mentions.set_index(
        "generation_asset_mention_id"
    )["event_id"].astype(str)
    name_events = generation_asset_names["generation_asset_mention_id"].astype(
        str
    ).map(asset_events)
    if not name_events.eq(generation_asset_names["event_id"].astype(str)).all():
        raise ValueError("Los nombres deben pertenecer al evento de su mención.")

    for column in (
        "province_resolution_status",
        "autonomous_community_resolution_status",
    ):
        statuses = set(resolved_locations[column].dropna().astype(str))
        invalid = statuses - _SAFE_LOCATION_STATUSES - _UNSAFE_LOCATION_STATUSES
        if invalid:
            raise ValueError(f"{column} contiene estados no válidos: {sorted(invalid)}")
        unsafe = statuses & _UNSAFE_LOCATION_STATUSES
        if unsafe:
            raise ValueError(
                "La resolución territorial contiene estados "
                f"{', '.join(sorted(unsafe))}; requires_inspection antes de agrupar."
            )


def _normalize_generation_name(value: Any) -> str:
    normalized = normalize_text_or_none(value)
    if normalized is None:
        raise ValueError("No se puede agrupar una mención sin nombre normalizable.")
    tokens = normalized.split()
    first_distinctive = 0
    while (
        first_distinctive < len(tokens)
        and tokens[first_distinctive] in _GENERATION_NAME_PREFIX_TOKENS
    ):
        first_distinctive += 1
    distinctive = tokens[first_distinctive:]
    return " ".join(distinctive or tokens)


def _name_identity(names: pd.Series) -> _NameIdentity:
    full_names = frozenset(
        normalized
        for value in names
        if (normalized := normalize_text_or_none(value)) is not None
    )
    grouping_names = sorted({_normalize_generation_name(value) for value in names})
    if len(grouping_names) == 1:
        key = grouping_names[0]
    else:
        key = "aliases:[" + "||".join(grouping_names) + "]"
    return _NameIdentity(key=key, full_names=full_names)


def _resolved_codes(
    rows: pd.DataFrame,
    *,
    code_column: str,
    status_column: str,
) -> tuple[str, ...]:
    resolved = rows.loc[rows[status_column].astype("string") == "resolved"]
    codes = {
        str(code).strip()
        for code in resolved[code_column]
        if not is_null_like(code) and str(code).strip()
    }
    return tuple(sorted(codes))


def _event_geography_anchors(
    resolved_locations: pd.DataFrame,
) -> dict[str, str]:
    anchors: dict[str, str] = {}
    for event_id, rows in resolved_locations.groupby("event_id", sort=True):
        provinces = _resolved_codes(
            rows,
            code_column="ine_province_code",
            status_column="province_resolution_status",
        )
        if provinces:
            anchors[str(event_id)] = "province:" + ",".join(provinces)
            continue
        communities = _resolved_codes(
            rows,
            code_column="ine_autonomous_community_code",
            status_column="autonomous_community_resolution_status",
        )
        if communities:
            anchors[str(event_id)] = (
                "autonomous_community:" + ",".join(communities)
            )
    return anchors


def _project_match_key(
    *,
    name_identity: str,
    generation_type: str,
    geography_anchor: str,
) -> str:
    return (
        f"{_MATCH_KEY_VERSION}|name:{name_identity}"
        f"|technology:{generation_type}|geography:{geography_anchor}"
    )


def _stable_project_id(project_match_key: str) -> str:
    return f"project_{uuid5(_PROJECT_NAMESPACE, project_match_key).hex}"


def _group_match_method(group: pd.DataFrame) -> str:
    if len(group) == 1:
        return "singleton"
    shared_full_names = set(group.iloc[0]["full_names"])
    for names in group.iloc[1:]["full_names"]:
        shared_full_names.intersection_update(names)
    return "strong_exact_name" if shared_full_names else "documentary_variant"


def group_projects(
    generation_asset_mentions: pd.DataFrame,
    generation_asset_names: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> pd.DataFrame:
    """Assign stable canonical project identities to generation mentions.

    Inputs are explicit DataFrames from the normalized Silver extraction and
    the output of ``resolve_locations``. Matching is deliberately conservative:
    canonical documentary name, exact generation technology and one stable
    territorial anchor must coincide. Province is preferred; autonomous
    community is used only when no province is resolved. Municipality never
    participates in the key, so later municipal enrichment cannot change an
    existing project identity. The function performs no I/O and does not
    mutate its inputs.
    """

    _validate_inputs(
        generation_asset_mentions,
        generation_asset_names,
        resolved_locations,
    )
    if generation_asset_mentions.empty:
        return pd.DataFrame({
            column: pd.Series(dtype="string")
            for column in PROJECT_GROUPING_COLUMNS
        })

    identities = {
        str(mention_id): _name_identity(rows["name_raw"])
        for mention_id, rows in generation_asset_names.groupby(
            "generation_asset_mention_id",
            sort=True,
        )
    }
    geography_anchors = _event_geography_anchors(resolved_locations)
    records: list[dict[str, Any]] = []
    for row in generation_asset_mentions.sort_values(
        "generation_asset_mention_id", kind="stable"
    ).itertuples(index=False):
        mention_id = str(row.generation_asset_mention_id)
        identity = identities[mention_id]
        match_key = _project_match_key(
            name_identity=identity.key,
            generation_type=str(row.generation_type),
            geography_anchor=geography_anchors.get(str(row.event_id), "unresolved"),
        )
        records.append({
            "generation_asset_mention_id": mention_id,
            "project_id": _stable_project_id(match_key),
            "project_match_key": match_key,
            "full_names": identity.full_names,
        })

    candidates = pd.DataFrame(records)
    methods = {
        match_key: _group_match_method(group)
        for match_key, group in candidates.groupby("project_match_key", sort=True)
    }
    candidates["project_match_method"] = candidates["project_match_key"].map(
        methods
    )
    result = candidates.loc[:, PROJECT_GROUPING_COLUMNS].sort_values(
        "generation_asset_mention_id", kind="stable"
    ).reset_index(drop=True)
    for column in PROJECT_GROUPING_COLUMNS:
        result[column] = result[column].astype("string")
    return result
