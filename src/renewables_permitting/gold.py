from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from renewables_permitting.utils import (
    is_null_like,
    normalize_text_or_none,
    validate_required_columns,
)


PROJECT_EVENTS_COLUMNS = (
    "project_id",
    "event_id",
    "administrative_action_id",
    "boe_id",
    "publication_date",
    "event_index",
    "administrative_action_index",
    "action_type",
    "decision",
    "is_modification",
    "evidence",
)

PROJECTS_COLUMNS = (
    "project_id",
    "project_name",
    "technology",
    "province_codes",
    "provinces",
    "municipality_codes",
    "municipalities",
    "first_publication_date",
    "last_publication_date",
    "n_publications",
    "n_administrative_actions",
)

_PROJECT_EVENT_DTYPES: Mapping[str, str] = {
    "project_id": "string",
    "event_id": "string",
    "administrative_action_id": "string",
    "boe_id": "string",
    "publication_date": "datetime64[ns]",
    "event_index": "Int64",
    "administrative_action_index": "Int64",
    "action_type": "string",
    "decision": "string",
    "is_modification": "boolean",
    "evidence": "string",
}

_PROJECT_DTYPES: Mapping[str, str] = {
    "project_id": "string",
    "project_name": "string",
    "technology": "string",
    "province_codes": "string",
    "provinces": "string",
    "municipality_codes": "string",
    "municipalities": "string",
    "first_publication_date": "datetime64[ns]",
    "last_publication_date": "datetime64[ns]",
    "n_publications": "Int64",
    "n_administrative_actions": "Int64",
}

_EVENT_COLUMNS = {
    "event_id",
    "identificador_boe",
    "fecha_publicacion",
    "event_index",
}
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
_ACTION_COLUMNS = {
    "event_id",
    "identificador_boe",
    "fecha_publicacion",
    "administrative_action_id",
    "action_index",
    "action_type",
    "decision",
    "is_modification",
    "evidence",
}
_TARGET_COLUMNS = {
    "event_id",
    "administrative_action_id",
    "target_index",
    "target_entity_id",
    "target_kind",
}
_COMPONENT_LINK_COLUMNS = {
    "event_id",
    "associated_component_id",
    "link_index",
    "generation_asset_mention_id",
}
_GROUPING_COLUMNS = {"generation_asset_mention_id", "project_id"}
_LOCATION_COLUMNS = {
    "event_id",
    "location_mention_id",
    "ine_municipality_code",
    "municipality",
    "municipality_resolution_status",
    "ine_province_code",
    "province",
    "province_resolution_status",
}
_PROJECT_EVENT_REQUIRED_COLUMNS = set(PROJECT_EVENTS_COLUMNS)
_TARGET_KINDS = {"event", "generation_asset", "associated_component"}
_MULTIVALUE_SEPARATOR = " | "


def _typed_frame(
    records: list[dict[str, Any]] | pd.DataFrame,
    columns: tuple[str, ...],
    dtypes: Mapping[str, str],
) -> pd.DataFrame:
    frame = pd.DataFrame(records, columns=columns)
    for column, dtype in dtypes.items():
        if dtype == "datetime64[ns]":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def _validate_frame(
    frame: pd.DataFrame,
    name: str,
    required_columns: set[str],
    *,
    primary_key: tuple[str, ...] | None = None,
) -> None:
    if frame.columns.duplicated().any():
        duplicates = frame.columns[
            frame.columns.duplicated(keep=False)
        ].tolist()
        raise ValueError(f"{name} contiene columnas duplicadas: {duplicates}")
    validate_required_columns(frame, required_columns)
    if primary_key is None:
        return
    key = list(primary_key)
    if frame[key].isna().any().any():
        raise ValueError(f"La clave de {name} no puede contener nulos.")
    if frame.duplicated(key).any():
        raise ValueError(f"{name} contiene claves duplicadas.")


def _validate_required_text(
    frame: pd.DataFrame,
    table_name: str,
    columns: tuple[str, ...],
) -> None:
    for column in columns:
        values = frame[column]
        if values.isna().any() or values.astype("string").str.strip().eq("").any():
            raise ValueError(
                f"{table_name}.{column} no puede contener nulos o vacíos."
            )


def _asset_projects(
    generation_asset_mentions: pd.DataFrame,
    project_grouping: pd.DataFrame,
) -> pd.DataFrame:
    _validate_frame(
        generation_asset_mentions,
        "generation_asset_mentions",
        _ASSET_COLUMNS,
        primary_key=("generation_asset_mention_id",),
    )
    _validate_frame(
        project_grouping,
        "project_grouping",
        _GROUPING_COLUMNS,
        primary_key=("generation_asset_mention_id",),
    )
    _validate_required_text(
        generation_asset_mentions,
        "generation_asset_mentions",
        ("event_id", "generation_asset_mention_id", "generation_type"),
    )
    _validate_required_text(
        project_grouping,
        "project_grouping",
        ("generation_asset_mention_id", "project_id"),
    )

    asset_ids = set(
        generation_asset_mentions["generation_asset_mention_id"].astype(str)
    )
    grouped_ids = set(project_grouping["generation_asset_mention_id"].astype(str))
    if asset_ids != grouped_ids:
        missing = sorted(asset_ids - grouped_ids)
        additional = sorted(grouped_ids - asset_ids)
        raise ValueError(
            "project_grouping debe asignar exactamente todas las menciones de "
            f"generación; faltan={missing[:5]}, adicionales={additional[:5]}."
        )

    return generation_asset_mentions.loc[
        :, ["event_id", "generation_asset_mention_id", "generation_type"]
    ].merge(
        project_grouping.loc[
            :, ["generation_asset_mention_id", "project_id"]
        ],
        on="generation_asset_mention_id",
        how="inner",
        validate="one_to_one",
    )


def _validate_project_event_sources(
    publication_events: pd.DataFrame,
    administrative_actions: pd.DataFrame,
    administrative_action_targets: pd.DataFrame,
    associated_component_generation_links: pd.DataFrame,
    asset_projects: pd.DataFrame,
) -> None:
    _validate_frame(
        publication_events,
        "publication_events",
        _EVENT_COLUMNS,
        primary_key=("event_id",),
    )
    _validate_frame(
        administrative_actions,
        "administrative_actions",
        _ACTION_COLUMNS,
        primary_key=("administrative_action_id",),
    )
    _validate_frame(
        administrative_action_targets,
        "administrative_action_targets",
        _TARGET_COLUMNS,
        primary_key=("administrative_action_id", "target_index"),
    )
    _validate_frame(
        associated_component_generation_links,
        "associated_component_generation_links",
        _COMPONENT_LINK_COLUMNS,
        primary_key=("associated_component_id", "link_index"),
    )
    _validate_required_text(
        publication_events,
        "publication_events",
        ("event_id", "identificador_boe"),
    )
    _validate_required_text(
        administrative_actions,
        "administrative_actions",
        (
            "event_id",
            "identificador_boe",
            "administrative_action_id",
            "action_type",
            "decision",
            "evidence",
        ),
    )
    _validate_required_text(
        administrative_action_targets,
        "administrative_action_targets",
        (
            "event_id",
            "administrative_action_id",
            "target_entity_id",
            "target_kind",
        ),
    )
    _validate_required_text(
        associated_component_generation_links,
        "associated_component_generation_links",
        (
            "event_id",
            "associated_component_id",
            "generation_asset_mention_id",
        ),
    )

    for frame, table_name, index_column in (
        (publication_events, "publication_events", "event_index"),
        (administrative_actions, "administrative_actions", "action_index"),
        (
            administrative_action_targets,
            "administrative_action_targets",
            "target_index",
        ),
        (
            associated_component_generation_links,
            "associated_component_generation_links",
            "link_index",
        ),
    ):
        if frame[index_column].isna().any() or (frame[index_column] < 1).any():
            raise ValueError(
                f"{table_name}.{index_column} debe contener índices positivos."
            )

    if publication_events["fecha_publicacion"].isna().any():
        raise ValueError("publication_events.fecha_publicacion no puede ser nula.")
    if administrative_actions["fecha_publicacion"].isna().any():
        raise ValueError("administrative_actions.fecha_publicacion no puede ser nula.")

    event_ids = set(publication_events["event_id"].astype(str))
    for frame, table_name in (
        (asset_projects, "generation_asset_mentions"),
        (administrative_actions, "administrative_actions"),
    ):
        orphans = set(frame["event_id"].astype(str)) - event_ids
        if orphans:
            raise ValueError(
                f"{table_name} contiene event_id huérfanos: {sorted(orphans)[:5]}."
            )

    action_events = administrative_actions.set_index(
        "administrative_action_id"
    )["event_id"].astype(str)
    target_action_events = administrative_action_targets[
        "administrative_action_id"
    ].astype(str).map(action_events)
    if target_action_events.isna().any():
        raise ValueError("administrative_action_targets contiene acciones huérfanas.")
    if not target_action_events.eq(
        administrative_action_targets["event_id"].astype(str)
    ).all():
        raise ValueError(
            "administrative_action_targets contiene targets fuera del evento de su acción."
        )

    target_kinds = set(
        administrative_action_targets["target_kind"].dropna().astype(str)
    )
    invalid_target_kinds = target_kinds - _TARGET_KINDS
    if invalid_target_kinds:
        raise ValueError(
            f"target_kind contiene valores no válidos: {sorted(invalid_target_kinds)}."
        )

    event_metadata = publication_events.set_index("event_id")[
        ["identificador_boe", "fecha_publicacion"]
    ]
    expected_boe = administrative_actions["event_id"].astype(str).map(
        event_metadata["identificador_boe"].astype(str)
    )
    expected_date = administrative_actions["event_id"].astype(str).map(
        event_metadata["fecha_publicacion"]
    )
    if not expected_boe.eq(
        administrative_actions["identificador_boe"].astype(str)
    ).all() or not expected_date.eq(administrative_actions["fecha_publicacion"]).all():
        raise ValueError(
            "administrative_actions contradice la trazabilidad de publication_events."
        )

    asset_events = asset_projects.set_index("generation_asset_mention_id")[
        "event_id"
    ].astype(str)
    link_asset_events = associated_component_generation_links[
        "generation_asset_mention_id"
    ].astype(str).map(asset_events)
    if link_asset_events.isna().any():
        raise ValueError(
            "associated_component_generation_links contiene plantas huérfanas."
        )
    if not link_asset_events.eq(
        associated_component_generation_links["event_id"].astype(str)
    ).all():
        raise ValueError(
            "associated_component_generation_links enlaza plantas de otro evento."
        )


def _action_project_attributions(
    administrative_action_targets: pd.DataFrame,
    associated_component_generation_links: pd.DataFrame,
    asset_projects: pd.DataFrame,
) -> pd.DataFrame:
    event_projects = asset_projects.loc[:, ["event_id", "project_id"]].drop_duplicates()
    target_columns = [
        "event_id",
        "administrative_action_id",
        "target_entity_id",
        "target_kind",
    ]
    targets = administrative_action_targets.loc[:, target_columns]

    event_targets = targets.loc[
        (targets["target_kind"] == "event")
        & (targets["target_entity_id"].astype(str) == targets["event_id"].astype(str))
    ]
    event_attributions = event_targets.merge(
        event_projects,
        on="event_id",
        how="inner",
        validate="many_to_many",
    )

    asset_targets = targets.loc[targets["target_kind"] == "generation_asset"]
    asset_attributions = asset_targets.merge(
        asset_projects.loc[
            :, ["event_id", "generation_asset_mention_id", "project_id"]
        ],
        left_on=["event_id", "target_entity_id"],
        right_on=["event_id", "generation_asset_mention_id"],
        how="inner",
        validate="many_to_one",
    )

    component_targets = targets.loc[
        targets["target_kind"] == "associated_component"
    ]
    component_attributions = component_targets.merge(
        associated_component_generation_links.loc[
            :,
            [
                "event_id",
                "associated_component_id",
                "generation_asset_mention_id",
            ],
        ],
        left_on=["event_id", "target_entity_id"],
        right_on=["event_id", "associated_component_id"],
        how="inner",
        validate="many_to_many",
    ).merge(
        asset_projects.loc[:, ["generation_asset_mention_id", "project_id"]],
        on="generation_asset_mention_id",
        how="inner",
        validate="many_to_one",
    )

    attribution_frames = [
        frame.loc[:, ["administrative_action_id", "project_id"]]
        for frame in (event_attributions, asset_attributions, component_attributions)
        if not frame.empty
    ]
    if not attribution_frames:
        return pd.DataFrame({
            "administrative_action_id": pd.Series(dtype="string"),
            "project_id": pd.Series(dtype="string"),
        })
    return (
        pd.concat(attribution_frames, ignore_index=True)
        .drop_duplicates(["administrative_action_id", "project_id"])
        .reset_index(drop=True)
    )


def build_project_events(
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    administrative_actions: pd.DataFrame,
    administrative_action_targets: pd.DataFrame,
    associated_component_generation_links: pd.DataFrame,
    project_grouping: pd.DataFrame,
) -> pd.DataFrame:
    """Build canonical published administrative milestones per project.

    Event targets expand to every grouped generation project in the event.
    Generation targets resolve only to their own project. Component targets
    resolve only through explicit component-to-generation links. The function
    performs no I/O and never mutates the supplied DataFrames.
    """

    asset_projects = _asset_projects(
        generation_asset_mentions,
        project_grouping,
    )
    _validate_project_event_sources(
        publication_events,
        administrative_actions,
        administrative_action_targets,
        associated_component_generation_links,
        asset_projects,
    )
    attributions = _action_project_attributions(
        administrative_action_targets,
        associated_component_generation_links,
        asset_projects,
    )
    if attributions.empty:
        return _typed_frame([], PROJECT_EVENTS_COLUMNS, _PROJECT_EVENT_DTYPES)

    facts = attributions.merge(
        administrative_actions.loc[
            :,
            [
                "event_id",
                "administrative_action_id",
                "action_index",
                "action_type",
                "decision",
                "is_modification",
                "evidence",
            ],
        ],
        on="administrative_action_id",
        how="inner",
        validate="many_to_one",
    ).merge(
        publication_events.loc[
            :,
            [
                "event_id",
                "identificador_boe",
                "fecha_publicacion",
                "event_index",
            ],
        ],
        on="event_id",
        how="inner",
        validate="many_to_one",
    )
    facts = facts.rename(
        columns={
            "identificador_boe": "boe_id",
            "fecha_publicacion": "publication_date",
            "action_index": "administrative_action_index",
        }
    )
    facts = facts.loc[:, PROJECT_EVENTS_COLUMNS]
    if facts.duplicated(["project_id", "administrative_action_id"]).any():
        raise ValueError(
            "project_events contiene duplicados (project_id, administrative_action_id)."
        )
    facts = facts.sort_values(
        [
            "project_id",
            "publication_date",
            "event_index",
            "administrative_action_index",
            "administrative_action_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    return _typed_frame(facts, PROJECT_EVENTS_COLUMNS, _PROJECT_EVENT_DTYPES)


def _display_name(values: pd.Series) -> str:
    candidates: dict[str, str] = {}
    for value in values:
        if is_null_like(value):
            continue
        cleaned = " ".join(str(value).split())
        normalized = normalize_text_or_none(cleaned)
        if normalized is not None:
            candidates.setdefault(cleaned, normalized)
    if not candidates:
        raise ValueError("No se puede construir project_name sin nombres documentales.")
    return min(
        candidates,
        key=lambda candidate: (
            -len(candidates[candidate].split()),
            -len(candidates[candidate]),
            candidates[candidate],
            candidate,
        ),
    )


def _joined_values(values: pd.Series) -> str | pd.NA:
    unique = {
        str(value).strip()
        for value in values
        if not is_null_like(value) and str(value).strip()
    }
    if not unique:
        return pd.NA
    return _MULTIVALUE_SEPARATOR.join(
        sorted(unique, key=lambda value: (normalize_text_or_none(value) or "", value))
    )


def _validate_project_sources(
    publication_events: pd.DataFrame,
    generation_asset_names: pd.DataFrame,
    resolved_locations: pd.DataFrame,
    asset_projects: pd.DataFrame,
    project_events: pd.DataFrame,
) -> None:
    _validate_frame(
        publication_events,
        "publication_events",
        _EVENT_COLUMNS,
        primary_key=("event_id",),
    )
    _validate_frame(
        generation_asset_names,
        "generation_asset_names",
        _NAME_COLUMNS,
        primary_key=("generation_asset_mention_id", "name_index"),
    )
    _validate_frame(
        resolved_locations,
        "resolved_locations",
        _LOCATION_COLUMNS,
        primary_key=("location_mention_id",),
    )
    _validate_frame(
        project_events,
        "project_events",
        _PROJECT_EVENT_REQUIRED_COLUMNS,
        primary_key=("project_id", "administrative_action_id"),
    )
    _validate_required_text(
        generation_asset_names,
        "generation_asset_names",
        ("event_id", "generation_asset_mention_id", "name_raw"),
    )
    _validate_required_text(
        resolved_locations,
        "resolved_locations",
        ("event_id", "location_mention_id"),
    )

    asset_ids = set(asset_projects["generation_asset_mention_id"].astype(str))
    name_ids = set(generation_asset_names["generation_asset_mention_id"].astype(str))
    if asset_ids != name_ids:
        raise ValueError(
            "generation_asset_names debe cubrir exactamente las menciones agrupadas."
        )
    asset_events = asset_projects.set_index("generation_asset_mention_id")[
        "event_id"
    ].astype(str)
    expected_name_events = generation_asset_names[
        "generation_asset_mention_id"
    ].astype(str).map(asset_events)
    if not expected_name_events.eq(generation_asset_names["event_id"].astype(str)).all():
        raise ValueError("generation_asset_names contiene nombres fuera de su evento.")

    event_ids = set(publication_events["event_id"].astype(str))
    orphan_asset_events = set(asset_projects["event_id"].astype(str)) - event_ids
    if orphan_asset_events:
        raise ValueError("generation_asset_mentions contiene eventos huérfanos.")
    orphan_location_events = set(resolved_locations["event_id"].astype(str)) - event_ids
    if orphan_location_events:
        raise ValueError("resolved_locations contiene eventos huérfanos.")

    project_ids = set(asset_projects["project_id"].astype(str))
    event_project_ids = set(project_events["project_id"].astype(str))
    if event_project_ids - project_ids:
        raise ValueError("project_events contiene project_id ajenos al grouping.")


def build_projects(
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    generation_asset_names: pd.DataFrame,
    resolved_locations: pd.DataFrame,
    project_grouping: pd.DataFrame,
    project_events: pd.DataFrame,
) -> pd.DataFrame:
    """Build one deterministic catalogue row per canonical project identity.

    Names and resolved territory are presentation attributes only. Publication
    counts come from distinct BOEs linked through generation mentions; action
    counts come from canonical ``project_events`` facts.
    """

    asset_projects = _asset_projects(
        generation_asset_mentions,
        project_grouping,
    )
    _validate_project_sources(
        publication_events,
        generation_asset_names,
        resolved_locations,
        asset_projects,
        project_events,
    )
    if asset_projects.empty:
        return _typed_frame([], PROJECTS_COLUMNS, _PROJECT_DTYPES)

    technologies = asset_projects.groupby("project_id", sort=True)[
        "generation_type"
    ].agg(lambda values: sorted(set(values.astype(str))))
    incompatible = technologies.loc[technologies.map(len) != 1]
    if not incompatible.empty:
        details = {
            str(project_id): values
            for project_id, values in incompatible.head(5).items()
        }
        raise ValueError(
            f"Existen project_id con tecnologías incompatibles: {details}."
        )
    technology_by_project = technologies.map(lambda values: values[0])

    names = generation_asset_names.loc[
        :, ["generation_asset_mention_id", "name_raw"]
    ].merge(
        asset_projects.loc[:, ["generation_asset_mention_id", "project_id"]],
        on="generation_asset_mention_id",
        how="inner",
        validate="many_to_one",
    )
    names_by_project = names.groupby("project_id", sort=True)["name_raw"].agg(
        _display_name
    )

    event_projects = asset_projects.loc[:, ["event_id", "project_id"]].drop_duplicates()
    publications = event_projects.merge(
        publication_events.loc[
            :,
            ["event_id", "identificador_boe", "fecha_publicacion"],
        ],
        on="event_id",
        how="inner",
        validate="many_to_one",
    )
    publication_summary = publications.groupby("project_id", sort=True).agg(
        first_publication_date=("fecha_publicacion", "min"),
        last_publication_date=("fecha_publicacion", "max"),
        n_publications=("identificador_boe", "nunique"),
    )
    action_counts = project_events.groupby("project_id", sort=True).size()

    locations = event_projects.merge(
        resolved_locations.loc[
            :,
            [
                "event_id",
                "ine_municipality_code",
                "municipality",
                "municipality_resolution_status",
                "ine_province_code",
                "province",
                "province_resolution_status",
            ],
        ],
        on="event_id",
        how="left",
        validate="many_to_many",
    )
    municipality_locations = locations.loc[
        locations["municipality_resolution_status"] == "resolved"
    ]
    province_locations = locations.loc[
        locations["province_resolution_status"] == "resolved"
    ]

    project_ids = sorted(set(asset_projects["project_id"].astype(str)))
    records: list[dict[str, Any]] = []
    for project_id in project_ids:
        municipalities = municipality_locations.loc[
            municipality_locations["project_id"].astype(str) == project_id
        ]
        provinces = province_locations.loc[
            province_locations["project_id"].astype(str) == project_id
        ]
        summary = publication_summary.loc[project_id]
        records.append({
            "project_id": project_id,
            "project_name": names_by_project.loc[project_id],
            "technology": technology_by_project.loc[project_id],
            "province_codes": _joined_values(provinces["ine_province_code"]),
            "provinces": _joined_values(provinces["province"]),
            "municipality_codes": _joined_values(
                municipalities["ine_municipality_code"]
            ),
            "municipalities": _joined_values(municipalities["municipality"]),
            "first_publication_date": summary["first_publication_date"],
            "last_publication_date": summary["last_publication_date"],
            "n_publications": summary["n_publications"],
            "n_administrative_actions": int(action_counts.get(project_id, 0)),
        })

    return _typed_frame(records, PROJECTS_COLUMNS, _PROJECT_DTYPES).sort_values(
        "project_id", kind="stable"
    ).reset_index(drop=True)


def build_gold_tables(
    *,
    publication_events: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
    generation_asset_names: pd.DataFrame,
    administrative_actions: pd.DataFrame,
    administrative_action_targets: pd.DataFrame,
    associated_component_generation_links: pd.DataFrame,
    project_grouping: pd.DataFrame,
    resolved_locations: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Regenerate the two logical Gold tables from explicit validated inputs."""

    project_events = build_project_events(
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        administrative_actions=administrative_actions,
        administrative_action_targets=administrative_action_targets,
        associated_component_generation_links=(
            associated_component_generation_links
        ),
        project_grouping=project_grouping,
    )
    projects = build_projects(
        publication_events=publication_events,
        generation_asset_mentions=generation_asset_mentions,
        generation_asset_names=generation_asset_names,
        resolved_locations=resolved_locations,
        project_grouping=project_grouping,
        project_events=project_events,
    )
    return {"projects": projects, "project_events": project_events}
