"""Additive Gold territories with exact publication-location provenance."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid5

import pandas as pd


PROJECT_LOCATIONS_COLUMNS = (
    "project_location_id",
    "project_id",
    "location_level",
    "municipality",
    "municipality_norm",
    "ine_municipality_code",
    "province",
    "province_norm",
    "ine_province_code",
    "autonomous_community",
    "autonomous_community_norm",
    "ine_autonomous_community_code",
    "source_location_mention_count",
    "source_publication_count",
    "first_publication_date",
    "last_publication_date",
)

PROJECT_LOCATION_SOURCES_COLUMNS = (
    "project_location_id",
    "location_mention_id",
    "event_id",
    "boe_id",
    "publication_date",
)

# Fixed UUID5 namespace derived for the v1 project-location identity contract.
# Changing it would change every persisted ``project_location_id``.
PROJECT_LOCATION_NAMESPACE = UUID("d9afa47c-7ede-53d4-9e78-8abfe0704bf3")
PROJECT_LOCATION_ID_VERSION = "v1"
PROJECT_LOCATIONS_CONTRACT_VERSION = "1"

_PROJECT_LOCATION_DTYPES: Mapping[str, str] = {
    "project_location_id": "string",
    "project_id": "string",
    "location_level": "string",
    "municipality": "string",
    "municipality_norm": "string",
    "ine_municipality_code": "string",
    "province": "string",
    "province_norm": "string",
    "ine_province_code": "string",
    "autonomous_community": "string",
    "autonomous_community_norm": "string",
    "ine_autonomous_community_code": "string",
    "source_location_mention_count": "Int64",
    "source_publication_count": "Int64",
    "first_publication_date": "datetime64[ns]",
    "last_publication_date": "datetime64[ns]",
}

_PROJECT_LOCATION_SOURCE_DTYPES: Mapping[str, str] = {
    "project_location_id": "string",
    "location_mention_id": "string",
    "event_id": "string",
    "boe_id": "string",
    "publication_date": "datetime64[ns]",
}

_PUBLICATION_EVENT_COLUMNS = {
    "event_id",
    "identificador_boe",
    "fecha_publicacion",
}
_GENERATION_ASSET_COLUMNS = {
    "event_id",
    "generation_asset_mention_id",
}
_PROJECT_GROUPING_COLUMNS = {"generation_asset_mention_id", "project_id"}
_PROJECT_COLUMNS = {"project_id"}
_RESOLVED_LOCATION_COLUMNS = {
    "event_id",
    "identificador_boe",
    "fecha_publicacion",
    "location_mention_id",
    "municipality",
    "municipality_norm",
    "ine_municipality_code",
    "municipality_resolution_status",
    "province",
    "province_norm",
    "ine_province_code",
    "province_resolution_status",
    "autonomous_community",
    "autonomous_community_norm",
    "ine_autonomous_community_code",
    "autonomous_community_resolution_status",
}

_LOCATION_LEVELS = {
    "municipality",
    "province",
    "autonomous_community",
}
_RESOLUTION_STATUSES = {
    "resolved",
    "ambiguous",
    "not_found",
    "not_provided",
    "conflict",
}
_LEVEL_CODE_COLUMNS = {
    "municipality": "ine_municipality_code",
    "province": "ine_province_code",
    "autonomous_community": "ine_autonomous_community_code",
}
def _typed_frame(
    records: list[dict[str, Any]] | pd.DataFrame,
    columns: tuple[str, ...],
    dtypes: Mapping[str, str],
) -> pd.DataFrame:
    """Build a DataFrame with an exact ordered nullable contract."""

    frame = pd.DataFrame(records, columns=columns)
    for column, dtype in dtypes.items():
        if dtype == "datetime64[ns]":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def _validate_input_frame(
    frame: pd.DataFrame,
    name: str,
    required_columns: set[str],
    primary_key: tuple[str, ...],
) -> None:
    """Validate columns and logical primary keys at the input boundary."""

    if frame.columns.duplicated().any():
        duplicates = frame.columns[
            frame.columns.duplicated(keep=False)
        ].tolist()
        raise ValueError(f"{name} contiene columnas duplicadas: {duplicates}.")
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise ValueError(f"{name} no contiene las columnas requeridas: {missing}.")
    key = list(primary_key)
    if frame[key].isna().any().any():
        raise ValueError(f"La PK de {name} no puede contener nulos.")
    if frame.duplicated(key).any():
        raise ValueError(f"{name} contiene {primary_key} duplicada.")


def _validate_required_text(
    frame: pd.DataFrame,
    name: str,
    columns: tuple[str, ...],
) -> None:
    """Reject null or blank values in required text columns."""

    for column in columns:
        values = frame[column].astype("string")
        if values.isna().any() or values.str.strip().eq("").fillna(False).any():
            raise ValueError(f"{name}.{column} no puede ser nulo o vacío.")


def _required_text(value: Any, field_name: str) -> str:
    """Return one non-empty canonical text value or fail closed."""

    if pd.isna(value):
        raise ValueError(f"{field_name} no puede ser nulo.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} no puede estar vacío.")
    return text


def _required_code(value: Any, field_name: str, width: int) -> str:
    """Return an exact canonical INE code with the required width."""

    code = _required_text(value, field_name)
    if re.fullmatch(rf"\d{{{width}}}", code) is None:
        raise ValueError(
            f"El código {field_name} debe contener exactamente {width} dígitos."
        )
    return code


def _project_location_id(
    project_id: str,
    location_level: str,
    canonical_code: str,
) -> str:
    """Derive the stable UUID5 identity of a Gold project territory."""

    payload = (
        f"{PROJECT_LOCATION_ID_VERSION}|project:{project_id}|"
        f"level:{location_level}|territory:{canonical_code}"
    )
    return f"project_location_{uuid5(PROJECT_LOCATION_NAMESPACE, payload).hex}"


def _resolved_level(row: pd.Series) -> str | None:
    """Select the most specific independently resolved territorial level."""

    if str(row["municipality_resolution_status"]) == "resolved":
        return "municipality"
    if str(row["province_resolution_status"]) == "resolved":
        return "province"
    if str(row["autonomous_community_resolution_status"]) == "resolved":
        return "autonomous_community"
    return None


def _location_values(row: pd.Series, location_level: str) -> dict[str, Any]:
    """Build level-aware canonical names and codes from one resolved mention."""

    autonomous_community = _required_text(
        row["autonomous_community"], "autonomous_community"
    )
    autonomous_community_norm = _required_text(
        row["autonomous_community_norm"], "autonomous_community_norm"
    )
    autonomous_community_code = _required_code(
        row["ine_autonomous_community_code"],
        "ine_autonomous_community_code",
        2,
    )
    values: dict[str, Any] = {
        "municipality": pd.NA,
        "municipality_norm": pd.NA,
        "ine_municipality_code": pd.NA,
        "province": pd.NA,
        "province_norm": pd.NA,
        "ine_province_code": pd.NA,
        "autonomous_community": autonomous_community,
        "autonomous_community_norm": autonomous_community_norm,
        "ine_autonomous_community_code": autonomous_community_code,
    }
    if location_level in {"municipality", "province"}:
        values.update({
            "province": _required_text(row["province"], "province"),
            "province_norm": _required_text(
                row["province_norm"], "province_norm"
            ),
            "ine_province_code": _required_code(
                row["ine_province_code"], "ine_province_code", 2
            ),
        })
    if location_level == "municipality":
        values.update({
            "municipality": _required_text(
                row["municipality"], "municipality"
            ),
            "municipality_norm": _required_text(
                row["municipality_norm"], "municipality_norm"
            ),
            "ine_municipality_code": _required_code(
                row["ine_municipality_code"], "ine_municipality_code", 5
            ),
        })
        if not str(values["ine_municipality_code"]).startswith(
            str(values["ine_province_code"])
        ):
            raise ValueError(
                "El código municipal contradice el código provincial."
            )
    return values


def _validate_inputs(
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    project_grouping: pd.DataFrame,
    projects: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> pd.DataFrame:
    """Validate lineage inputs and return the distinct event-to-project map."""

    _validate_input_frame(
        publication_events,
        "publication_events",
        _PUBLICATION_EVENT_COLUMNS,
        ("event_id",),
    )
    _validate_input_frame(
        generation_asset_mentions,
        "generation_asset_mentions",
        _GENERATION_ASSET_COLUMNS,
        ("generation_asset_mention_id",),
    )
    _validate_input_frame(
        project_grouping,
        "project_grouping",
        _PROJECT_GROUPING_COLUMNS,
        ("generation_asset_mention_id",),
    )
    _validate_input_frame(projects, "projects", _PROJECT_COLUMNS, ("project_id",))
    _validate_input_frame(
        resolved_locations,
        "resolved_locations",
        _RESOLVED_LOCATION_COLUMNS,
        ("location_mention_id",),
    )
    _validate_required_text(
        publication_events,
        "publication_events",
        ("event_id", "identificador_boe"),
    )
    _validate_required_text(
        generation_asset_mentions,
        "generation_asset_mentions",
        ("event_id", "generation_asset_mention_id"),
    )
    _validate_required_text(
        project_grouping,
        "project_grouping",
        ("generation_asset_mention_id", "project_id"),
    )
    _validate_required_text(projects, "projects", ("project_id",))
    _validate_required_text(
        resolved_locations,
        "resolved_locations",
        ("event_id", "identificador_boe", "location_mention_id"),
    )
    if str(publication_events["fecha_publicacion"].dtype) != "datetime64[ns]":
        raise ValueError(
            "publication_events.fecha_publicacion debe ser datetime64[ns]."
        )
    if str(resolved_locations["fecha_publicacion"].dtype) != "datetime64[ns]":
        raise ValueError(
            "resolved_locations.fecha_publicacion debe ser datetime64[ns]."
        )
    if publication_events["fecha_publicacion"].isna().any():
        raise ValueError("publication_events contiene fechas nulas.")
    if resolved_locations["fecha_publicacion"].isna().any():
        raise ValueError("resolved_locations contiene fechas nulas.")

    for column in (
        "municipality_resolution_status",
        "province_resolution_status",
        "autonomous_community_resolution_status",
    ):
        statuses = set(resolved_locations[column].dropna().astype(str))
        if resolved_locations[column].isna().any() or statuses - _RESOLUTION_STATUSES:
            raise ValueError(
                f"resolved_locations.{column} contiene estados no válidos."
            )

    asset_ids = set(
        generation_asset_mentions["generation_asset_mention_id"].astype(str)
    )
    grouped_ids = set(project_grouping["generation_asset_mention_id"].astype(str))
    if asset_ids != grouped_ids:
        raise ValueError(
            "project_grouping debe cubrir exactamente generation_asset_mentions."
        )
    grouped_project_ids = set(project_grouping["project_id"].astype(str))
    project_ids = set(projects["project_id"].astype(str))
    if grouped_project_ids != project_ids:
        raise ValueError("projects y project_grouping no tienen la misma membresía.")

    event_ids = set(publication_events["event_id"].astype(str))
    for frame, name in (
        (generation_asset_mentions, "generation_asset_mentions"),
        (resolved_locations, "resolved_locations"),
    ):
        orphans = set(frame["event_id"].astype(str)) - event_ids
        if orphans:
            raise ValueError(f"{name} contiene event_id huérfanos.")

    event_metadata = publication_events.set_index("event_id")[
        ["identificador_boe", "fecha_publicacion"]
    ]
    expected_boe = resolved_locations["event_id"].astype(str).map(
        event_metadata["identificador_boe"].astype(str)
    )
    expected_date = resolved_locations["event_id"].astype(str).map(
        event_metadata["fecha_publicacion"]
    )
    if not expected_boe.eq(
        resolved_locations["identificador_boe"].astype(str)
    ).all() or not expected_date.eq(resolved_locations["fecha_publicacion"]).all():
        raise ValueError(
            "resolved_locations contradice el BOE o fecha de publication_events."
        )

    event_projects = generation_asset_mentions.loc[
        :, ["event_id", "generation_asset_mention_id"]
    ].merge(
        project_grouping.loc[
            :, ["generation_asset_mention_id", "project_id"]
        ],
        on="generation_asset_mention_id",
        how="inner",
        validate="one_to_one",
    )
    return (
        event_projects.loc[:, ["event_id", "project_id"]]
        .drop_duplicates()
        .sort_values(["event_id", "project_id"], kind="stable")
        .reset_index(drop=True)
    )


def _semantic_values(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> set[tuple[Any, ...]]:
    """Return null-safe semantic tuples for consistency checks."""

    values: set[tuple[Any, ...]] = set()
    for row in frame.loc[:, columns].itertuples(index=False, name=None):
        values.add(tuple(None if pd.isna(value) else value for value in row))
    return values


def _derive_tables(
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    project_grouping: pd.DataFrame,
    projects: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Derive both Gold location tables from validated canonical sources."""

    event_projects = _validate_inputs(
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        project_grouping=project_grouping,
        projects=projects,
        resolved_locations=resolved_locations,
    )
    projects_by_event = {
        str(event_id): tuple(sorted(set(rows["project_id"].astype(str))))
        for event_id, rows in event_projects.groupby("event_id", sort=True)
    }
    expanded_records: list[dict[str, Any]] = []
    for _, source in resolved_locations.iterrows():
        location_level = _resolved_level(source)
        if location_level is None:
            continue
        values = _location_values(source, location_level)
        canonical_code = str(values[_LEVEL_CODE_COLUMNS[location_level]])
        event_id = str(source["event_id"])
        project_ids = projects_by_event.get(event_id, ())
        if not project_ids:
            raise ValueError(
                "Una localización resuelta no puede quedar sin proyecto de evento."
            )
        for project_id in project_ids:
            expanded_records.append({
                "project_location_id": _project_location_id(
                    project_id,
                    location_level,
                    canonical_code,
                ),
                "project_id": project_id,
                "location_level": location_level,
                **values,
                "location_mention_id": str(source["location_mention_id"]),
                "event_id": event_id,
                "boe_id": str(source["identificador_boe"]),
                "publication_date": source["fecha_publicacion"],
            })

    if not expanded_records:
        return {
            "project_locations": _typed_frame(
                [], PROJECT_LOCATIONS_COLUMNS, _PROJECT_LOCATION_DTYPES
            ),
            "project_location_sources": _typed_frame(
                [],
                PROJECT_LOCATION_SOURCES_COLUMNS,
                _PROJECT_LOCATION_SOURCE_DTYPES,
            ),
        }

    expanded = pd.DataFrame(expanded_records)
    source_columns = list(PROJECT_LOCATION_SOURCES_COLUMNS)
    source_frame = expanded.loc[:, source_columns]
    if source_frame.duplicated(
        ["project_location_id", "location_mention_id"]
    ).any():
        raise ValueError(
            "La expansión produce fuentes project/location duplicadas."
        )

    semantic_columns = PROJECT_LOCATIONS_COLUMNS[:12]
    location_records: list[dict[str, Any]] = []
    for project_location_id, rows in expanded.groupby(
        "project_location_id", sort=True
    ):
        if len(_semantic_values(rows, semantic_columns)) != 1:
            raise ValueError(
                "Un código territorial resuelto presenta atributos canónicos "
                "contradictorios."
            )
        first = rows.iloc[0]
        location_records.append({
            **{column: first[column] for column in semantic_columns},
            "source_location_mention_count": rows[
                "location_mention_id"
            ].nunique(),
            "source_publication_count": rows["boe_id"].nunique(),
            "first_publication_date": rows["publication_date"].min(),
            "last_publication_date": rows["publication_date"].max(),
        })

    project_locations = _typed_frame(
        location_records,
        PROJECT_LOCATIONS_COLUMNS,
        _PROJECT_LOCATION_DTYPES,
    ).sort_values("project_location_id", kind="stable").reset_index(drop=True)
    project_location_sources = _typed_frame(
        source_frame,
        PROJECT_LOCATION_SOURCES_COLUMNS,
        _PROJECT_LOCATION_SOURCE_DTYPES,
    ).sort_values(
        ["project_location_id", "location_mention_id"], kind="stable"
    ).reset_index(drop=True)
    return {
        "project_locations": project_locations,
        "project_location_sources": project_location_sources,
    }


def _validate_exact_contract(
    frame: pd.DataFrame,
    name: str,
    columns: tuple[str, ...],
    dtypes: Mapping[str, str],
) -> None:
    """Validate exact columns, dtypes and absence of blank strings."""

    if frame.columns.duplicated().any():
        raise ValueError(f"{name} contiene columnas duplicadas.")
    if tuple(frame.columns) != columns:
        raise ValueError(f"{name} no conserva las columnas exactas.")
    actual_dtypes = {column: str(frame[column].dtype) for column in columns}
    if actual_dtypes != dict(dtypes):
        raise ValueError(f"{name} no conserva los dtypes exactos.")
    for column, dtype in dtypes.items():
        if dtype != "string":
            continue
        values = frame[column].astype("string")
        if values.notna().any() and values.dropna().str.strip().eq("").any():
            raise ValueError(f"{name}.{column} contiene cadenas vacías.")


def _validate_project_location_rows(
    project_locations: pd.DataFrame,
    projects: pd.DataFrame,
) -> None:
    """Validate main-table keys, domains, levels, hierarchy and ordering."""

    _validate_exact_contract(
        project_locations,
        "project_locations",
        PROJECT_LOCATIONS_COLUMNS,
        _PROJECT_LOCATION_DTYPES,
    )
    if project_locations["project_location_id"].isna().any() or project_locations[
        "project_location_id"
    ].duplicated().any():
        raise ValueError("project_locations contiene una PK nula o duplicada.")
    _validate_required_text(
        project_locations,
        "project_locations",
        ("project_location_id", "project_id", "location_level"),
    )
    levels = set(project_locations["location_level"].dropna().astype(str))
    if levels - _LOCATION_LEVELS:
        raise ValueError("project_locations contiene location_level no válido.")
    project_ids = set(projects["project_id"].astype(str))
    if set(project_locations["project_id"].astype(str)) - project_ids:
        raise ValueError("project_locations contiene project_id huérfanos.")

    semantic_keys: set[tuple[str, str, str]] = set()
    for _, row in project_locations.iterrows():
        project_id = str(row["project_id"])
        level = str(row["location_level"])
        values = _location_values(row, level)
        code = str(values[_LEVEL_CODE_COLUMNS[level]])
        if level == "province" and any(
            not pd.isna(row[column])
            for column in (
                "municipality",
                "municipality_norm",
                "ine_municipality_code",
            )
        ):
            raise ValueError(
                "Una fila province debe tener los campos municipality nulos."
            )
        if level == "autonomous_community" and any(
            not pd.isna(row[column])
            for column in (
                "municipality",
                "municipality_norm",
                "ine_municipality_code",
                "province",
                "province_norm",
                "ine_province_code",
            )
        ):
            raise ValueError(
                "Una fila autonomous_community debe tener municipio y provincia nulos."
            )
        expected_id = _project_location_id(project_id, level, code)
        if row["project_location_id"] != expected_id:
            raise ValueError("project_location_id no es recalculable.")
        semantic_key = (project_id, level, code)
        if semantic_key in semantic_keys:
            raise ValueError(
                "project_locations contiene una clave semántica duplicada."
            )
        semantic_keys.add(semantic_key)

    if (
        project_locations["source_location_mention_count"].isna().any()
        or project_locations["source_publication_count"].isna().any()
        or (project_locations["source_location_mention_count"] < 1).any()
        or (project_locations["source_publication_count"] < 1).any()
        or (
            project_locations["source_publication_count"]
            > project_locations["source_location_mention_count"]
        ).any()
    ):
        raise ValueError("project_locations contiene conteos no válidos.")
    if (
        project_locations["first_publication_date"].isna().any()
        or project_locations["last_publication_date"].isna().any()
        or (
            project_locations["first_publication_date"]
            > project_locations["last_publication_date"]
        ).any()
    ):
        raise ValueError("project_locations contiene fechas agregadas no válidas.")
    expected_order = project_locations.sort_values(
        "project_location_id", kind="stable"
    ).reset_index(drop=True)
    if not project_locations.reset_index(drop=True).equals(expected_order):
        raise ValueError("project_locations no conserva el orden determinista.")


def _validate_project_location_source_rows(
    project_location_sources: pd.DataFrame,
    project_locations: pd.DataFrame,
    publication_events: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> None:
    """Validate bridge keys, foreign keys, source metadata and ordering."""

    _validate_exact_contract(
        project_location_sources,
        "project_location_sources",
        PROJECT_LOCATION_SOURCES_COLUMNS,
        _PROJECT_LOCATION_SOURCE_DTYPES,
    )
    key = ["project_location_id", "location_mention_id"]
    if project_location_sources[key].isna().any().any() or (
        project_location_sources.duplicated(key).any()
    ):
        raise ValueError("project_location_sources contiene una PK nula o duplicada.")
    _validate_required_text(
        project_location_sources,
        "project_location_sources",
        ("project_location_id", "location_mention_id", "event_id", "boe_id"),
    )
    if project_location_sources["publication_date"].isna().any():
        raise ValueError("project_location_sources contiene fechas nulas.")
    if set(project_location_sources["project_location_id"].astype(str)) - set(
        project_locations["project_location_id"].astype(str)
    ):
        raise ValueError(
            "project_location_sources contiene project_location_id huérfanos."
        )
    if set(project_location_sources["location_mention_id"].astype(str)) - set(
        resolved_locations["location_mention_id"].astype(str)
    ):
        raise ValueError(
            "project_location_sources contiene location_mention_id huérfanos."
        )
    if set(project_location_sources["event_id"].astype(str)) - set(
        publication_events["event_id"].astype(str)
    ):
        raise ValueError("project_location_sources contiene event_id huérfanos.")
    if set(project_locations["project_location_id"].astype(str)) - set(
        project_location_sources["project_location_id"].astype(str)
    ):
        raise ValueError("Cada project_location debe conservar al menos una fuente.")

    event_metadata = publication_events.set_index("event_id")[
        ["identificador_boe", "fecha_publicacion"]
    ]
    expected_boe = project_location_sources["event_id"].astype(str).map(
        event_metadata["identificador_boe"].astype(str)
    )
    expected_date = project_location_sources["event_id"].astype(str).map(
        event_metadata["fecha_publicacion"]
    )
    if not expected_boe.eq(project_location_sources["boe_id"].astype(str)).all():
        raise ValueError("Las fuentes contienen un BOE incoherente con event_id.")
    if not expected_date.eq(project_location_sources["publication_date"]).all():
        raise ValueError("Las fuentes contienen una fecha incoherente con event_id.")

    location_events = resolved_locations.set_index("location_mention_id")[
        "event_id"
    ].astype(str)
    expected_event = project_location_sources["location_mention_id"].astype(str).map(
        location_events
    )
    if not expected_event.eq(project_location_sources["event_id"].astype(str)).all():
        raise ValueError("Las fuentes contradicen el evento de la location mention.")
    expected_order = project_location_sources.sort_values(
        key, kind="stable"
    ).reset_index(drop=True)
    if not project_location_sources.reset_index(drop=True).equals(expected_order):
        raise ValueError("project_location_sources no conserva el orden determinista.")


def build_project_locations(
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    project_grouping: pd.DataFrame,
    projects: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build the two additive Gold project-location tables without I/O.

    Resolved mentions are attributed through their publication event to every
    distinct canonical project represented by generation assets in that event.
    Only the most specific resolved territorial level is published. Inputs are
    validated and never mutated.
    """

    result = _derive_tables(
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        project_grouping=project_grouping,
        projects=projects,
        resolved_locations=resolved_locations,
    )
    validate_project_locations(
        result["project_locations"],
        result["project_location_sources"],
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        project_grouping=project_grouping,
        projects=projects,
        resolved_locations=resolved_locations,
    )
    return result


def validate_project_locations(
    project_locations: pd.DataFrame,
    project_location_sources: pd.DataFrame,
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    project_grouping: pd.DataFrame,
    projects: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> None:
    """Validate contracts, lineage and exact reconstruction from sources.

    The validator performs no correction and does not mutate any supplied
    DataFrame. The aggregate must equal a fresh deterministic reconstruction
    from the canonical resolved mentions and frozen project membership.
    """

    _validate_inputs(
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        project_grouping=project_grouping,
        projects=projects,
        resolved_locations=resolved_locations,
    )
    _validate_project_location_rows(project_locations, projects)
    _validate_project_location_source_rows(
        project_location_sources,
        project_locations,
        publication_events,
        resolved_locations,
    )
    expected = _derive_tables(
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        project_grouping=project_grouping,
        projects=projects,
        resolved_locations=resolved_locations,
    )
    try:
        pd.testing.assert_frame_equal(
            project_locations,
            expected["project_locations"],
            check_dtype=True,
            check_exact=True,
        )
        pd.testing.assert_frame_equal(
            project_location_sources,
            expected["project_location_sources"],
            check_dtype=True,
            check_exact=True,
        )
    except AssertionError as error:
        raise ValueError(
            "project_locations no se reconstruye exactamente desde sus fuentes."
        ) from error


def _json_scalar(value: Any) -> Any:
    """Convert pandas scalars into canonical JSON-compatible values."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def project_locations_semantic_hash(
    project_locations: pd.DataFrame,
    project_location_sources: pd.DataFrame,
) -> str:
    """Hash both location contracts independently of physical row order."""

    _validate_exact_contract(
        project_locations,
        "project_locations",
        PROJECT_LOCATIONS_COLUMNS,
        _PROJECT_LOCATION_DTYPES,
    )
    _validate_exact_contract(
        project_location_sources,
        "project_location_sources",
        PROJECT_LOCATION_SOURCES_COLUMNS,
        _PROJECT_LOCATION_SOURCE_DTYPES,
    )
    payload: dict[str, Any] = {}
    for name, frame, key in (
        (
            "project_locations",
            project_locations,
            ("project_location_id",),
        ),
        (
            "project_location_sources",
            project_location_sources,
            ("project_location_id", "location_mention_id"),
        ),
    ):
        ordered = frame.sort_values(list(key), kind="stable").reset_index(drop=True)
        payload[name] = {
            "columns": list(ordered.columns),
            "rows": [
                [_json_scalar(value) for value in row]
                for row in ordered.itertuples(index=False, name=None)
            ],
        }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()
