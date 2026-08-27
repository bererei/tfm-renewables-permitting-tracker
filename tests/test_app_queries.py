from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.app_data import GoldDataset
from renewables_permitting.app_queries import (
    ACTION_TYPE_LABELS,
    DECISION_LABELS,
    LOCATION_LEVEL_LABELS,
    TECHNOLOGY_LABELS,
    ProjectNotFoundError,
    build_administrative_situation_counts,
    build_boe_url,
    build_catalog_interaction_context,
    build_dashboard_selection,
    build_chart_year_filter,
    build_latest_project_actions,
    build_matching_action_summary,
    build_project_publication_summary,
    build_publication_counts,
    build_project_catalog,
    build_yearly_project_counts,
    build_territory_project_counts,
    extract_chart_selected_values,
    extract_chart_selected_year,
    filter_projects,
    format_project_display_name,
    get_filter_options,
    get_project_detail,
    get_project_location_sources,
    get_project_locations,
    get_project_timeline,
    group_project_timeline_by_publication,
    label_action_type,
    label_decision,
    label_location_level,
    label_technology,
    summarize_dashboard_selection,
)


PROJECT_EVENT_DTYPES = {
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


def _frame(
    rows: list[dict[str, object]],
    dtypes: dict[str, str],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(dtypes))
    for column, dtype in dtypes.items():
        if dtype == "datetime64[ns]":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def _project(
    project_id: str,
    name: str,
    technology: str,
    first: str,
    last: str,
    publications: int,
    actions: int,
) -> dict[str, object]:
    return {
        "project_id": project_id,
        "project_name": name,
        "technology": technology,
        "province_codes": pd.NA,
        "provinces": pd.NA,
        "municipality_codes": pd.NA,
        "municipalities": pd.NA,
        "first_publication_date": first,
        "last_publication_date": last,
        "n_publications": publications,
        "n_administrative_actions": actions,
    }


def _event(
    project_id: str,
    event_id: str,
    action_id: str,
    boe_id: str,
    date: str,
    action_type: str,
    decision: str,
    *,
    event_index: int = 1,
    action_index: int = 1,
) -> dict[str, object]:
    return {
        "project_id": project_id,
        "event_id": event_id,
        "administrative_action_id": action_id,
        "boe_id": boe_id,
        "publication_date": date,
        "event_index": event_index,
        "administrative_action_index": action_index,
        "action_type": action_type,
        "decision": decision,
        "is_modification": False,
        "evidence": f"Evidencia de {action_id}.",
    }


def _location(
    location_id: str,
    project_id: str,
    level: str,
    *,
    municipality: str | None = None,
    municipality_code: str | None = None,
    province: str | None = None,
    province_code: str | None = None,
    community: str,
    community_code: str,
    date: str,
) -> dict[str, object]:
    return {
        "project_location_id": location_id,
        "project_id": project_id,
        "location_level": level,
        "municipality": municipality,
        "municipality_norm": municipality.casefold() if municipality else None,
        "ine_municipality_code": municipality_code,
        "province": province,
        "province_norm": province.casefold() if province else None,
        "ine_province_code": province_code,
        "autonomous_community": community,
        "autonomous_community_norm": community.casefold(),
        "ine_autonomous_community_code": community_code,
        "source_location_mention_count": 1,
        "source_publication_count": 1,
        "first_publication_date": date,
        "last_publication_date": date,
    }


def synthetic_dataset() -> GoldDataset:
    """Build a diverse in-memory dataset for pure query tests."""

    project_rows = [
        _project(
            "project_badulaque",
            "Parque Eólico Badulaque",
            "eolica",
            "2023-01-10",
            "2024-01-10",
            2,
            2,
        ),
        _project(
            "project_volateo",
            "Volateo Solar",
            "fotovoltaica",
            "2023-02-10",
            "2025-02-10",
            2,
            2,
        ),
        _project(
            "project_puebla",
            "La Puebla 1",
            "fotovoltaica",
            "2024-03-10",
            "2024-03-10",
            1,
            1,
        ),
        _project(
            "project_andevalo",
            "FV Andévalo",
            "fotovoltaica",
            "2024-04-10",
            "2024-04-10",
            1,
            1,
        ),
        _project(
            "project_angostillos",
            "PE Angostillos",
            "eolica",
            "2024-05-10",
            "2024-05-10",
            1,
            1,
        ),
        _project(
            "project_insular",
            "Central Insular",
            "otra_generacion",
            "2024-06-10",
            "2024-06-10",
            1,
            1,
        ),
    ]
    projects = _frame(
        project_rows,
        {
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
        },
    )
    project_events = _frame(
        [
            _event(
                "project_badulaque",
                "event_bad_1",
                "action_bad_1",
                "BOE-A-2023-10",
                "2023-01-10",
                "declaracion_impacto_ambiental",
                "desfavorable",
            ),
            _event(
                "project_badulaque",
                "event_bad_2",
                "action_bad_2",
                "BOE-A-2024-10",
                "2024-01-10",
                "autorizacion_administrativa_previa",
                "autorizado",
            ),
            _event(
                "project_volateo",
                "event_vol_1",
                "action_vol_1",
                "BOE-A-2023-20",
                "2023-02-10",
                "declaracion_impacto_ambiental",
                "desfavorable",
            ),
            _event(
                "project_volateo",
                "event_vol_2",
                "action_vol_2",
                "BOE-A-2025-20",
                "2025-02-10",
                "autorizacion_administrativa_previa",
                "autorizado",
            ),
            _event(
                "project_puebla",
                "event_puebla",
                "action_puebla",
                "BOE-A-2024-30",
                "2024-03-10",
                "informe_determinacion_afeccion_ambiental",
                "sin_efectos_adversos_significativos",
            ),
            _event(
                "project_andevalo",
                "event_andevalo",
                "action_andevalo",
                "BOE-A-2024-40",
                "2024-04-10",
                "declaracion_utilidad_publica",
                "declarado",
            ),
            _event(
                "project_angostillos",
                "event_angostillos",
                "action_angostillos",
                "BOE-A-2024-50",
                "2024-05-10",
                "autorizacion_administrativa_construccion",
                "autorizado",
            ),
            _event(
                "project_insular",
                "event_insular",
                "action_insular",
                "BOE-B-2024-60",
                "2024-06-10",
                "otro",
                "formulado",
            ),
        ],
        PROJECT_EVENT_DTYPES,
    )
    location_rows: list[dict[str, object]] = []
    for index, municipality in enumerate(
        ["Cariño", "Cedeira", "Cerdido", "Mañón", "Moeche", "Muras", "Ortigueira"],
        start=1,
    ):
        location_rows.append(_location(
            f"location_bad_{index}",
            "project_badulaque",
            "municipality",
            municipality=municipality,
            municipality_code=f"15{index:03d}",
            province="A Coruña",
            province_code="15",
            community="Galicia",
            community_code="12",
            date="2023-01-10",
        ))
    location_rows.extend([
        _location(
            "location_vol_1",
            "project_volateo",
            "municipality",
            municipality="Antequera",
            municipality_code="29015",
            province="Málaga",
            province_code="29",
            community="Andalucía",
            community_code="01",
            date="2023-02-10",
        ),
        _location(
            "location_vol_2",
            "project_volateo",
            "municipality",
            municipality="Campillos",
            municipality_code="29032",
            province="Málaga",
            province_code="29",
            community="Andalucía",
            community_code="01",
            date="2025-02-10",
        ),
        _location(
            "location_puebla",
            "project_puebla",
            "municipality",
            municipality="Puebla de Guzmán",
            municipality_code="21058",
            province="Huelva",
            province_code="21",
            community="Andalucía",
            community_code="01",
            date="2024-03-10",
        ),
        _location(
            "location_andevalo",
            "project_andevalo",
            "municipality",
            municipality="Alosno",
            municipality_code="21006",
            province="Huelva",
            province_code="21",
            community="Andalucía",
            community_code="01",
            date="2024-04-10",
        ),
        _location(
            "location_angostillos",
            "project_angostillos",
            "province",
            province="Zaragoza",
            province_code="50",
            community="Aragón",
            community_code="02",
            date="2024-05-10",
        ),
        _location(
            "location_insular",
            "project_insular",
            "autonomous_community",
            community="Canarias",
            community_code="05",
            date="2024-06-10",
        ),
    ])
    project_locations = _frame(
        location_rows,
        {
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
        },
    )
    boe_by_project = {
        row.project_id: (row.event_id, row.boe_id, row.publication_date)
        for row in project_events.itertuples()
    }
    project_location_sources = _frame(
        [
            {
                "project_location_id": row.project_location_id,
                "location_mention_id": f"mention_{row.project_location_id}",
                "event_id": boe_by_project[row.project_id][0],
                "boe_id": boe_by_project[row.project_id][1],
                "publication_date": boe_by_project[row.project_id][2],
            }
            for row in project_locations.itertuples()
        ],
        {
            "project_location_id": "string",
            "location_mention_id": "string",
            "event_id": "string",
            "boe_id": "string",
            "publication_date": "datetime64[ns]",
        },
    )
    return GoldDataset(
        projects=projects,
        project_events=project_events,
        project_locations=project_locations,
        project_location_sources=project_location_sources,
        manifest={},
        gold_dir=Path("."),
        downstream_id="synthetic",
    )


def _ids(frame: pd.DataFrame) -> set[str]:
    return set(frame["project_id"].astype(str))


def _with_project_events(
    dataset: GoldDataset,
    event_rows: list[dict[str, object]],
) -> GoldDataset:
    return GoldDataset(
        projects=dataset.projects,
        project_events=_frame(event_rows, PROJECT_EVENT_DTYPES),
        project_locations=dataset.project_locations,
        project_location_sources=dataset.project_location_sources,
        manifest=dataset.manifest,
        gold_dir=dataset.gold_dir,
        downstream_id=dataset.downstream_id,
    )


def _coscojar_dataset() -> GoldDataset:
    source = synthetic_dataset()
    source_project_id = "project_andevalo"
    project_id = "project_c9b8afc7704b5e1ab5ab8a76bde9aeda"
    projects = source.projects[
        source.projects["project_id"].eq(source_project_id)
    ].copy()
    projects.loc[:, "project_id"] = project_id
    projects.loc[:, "project_name"] = "FV El Coscojar II"
    projects.loc[:, "first_publication_date"] = pd.Timestamp("2026-06-18")
    projects.loc[:, "last_publication_date"] = pd.Timestamp("2026-06-18")
    projects.loc[:, "n_publications"] = 1
    projects.loc[:, "n_administrative_actions"] = 3
    events = _frame(
        [
            _event(
                project_id,
                "event_coscojar",
                f"action_coscojar_{index}",
                "BOE-B-2026-19389",
                "2026-06-18",
                action_type,
                "sometido_informacion_publica",
                action_index=index,
            )
            for index, action_type in enumerate(
                (
                    "evaluacion_impacto_ambiental",
                    "autorizacion_administrativa_previa",
                    "autorizacion_administrativa_construccion",
                ),
                start=1,
            )
        ],
        PROJECT_EVENT_DTYPES,
    )
    locations = source.project_locations[
        source.project_locations["project_id"].eq(source_project_id)
    ].copy()
    locations.loc[:, "project_id"] = project_id
    sources = source.project_location_sources[
        source.project_location_sources["project_location_id"].isin(
            locations["project_location_id"]
        )
    ].copy()
    sources.loc[:, "event_id"] = "event_coscojar"
    sources.loc[:, "boe_id"] = "BOE-B-2026-19389"
    sources.loc[:, "publication_date"] = pd.Timestamp("2026-06-18")
    return GoldDataset(
        projects=projects.reset_index(drop=True),
        project_events=events,
        project_locations=locations.reset_index(drop=True),
        project_location_sources=sources.reset_index(drop=True),
        manifest={},
        gold_dir=Path("."),
        downstream_id="synthetic-coscojar",
    )


def test_catalog_has_one_row_per_project_and_deterministic_territory() -> None:
    dataset = synthetic_dataset()

    catalog = build_project_catalog(dataset)

    assert len(catalog) == len(dataset.projects)
    assert catalog["project_id"].is_unique
    badulaque = catalog.loc[
        catalog["project_id"] == "project_badulaque"
    ].iloc[0]
    assert badulaque["territorial_summary"] == (
        "Cariño, Cedeira, Cerdido y 4 más"
    )
    assert badulaque["autonomous_communities"] == "Galicia"
    assert badulaque["provinces"] == "A Coruña"
    assert badulaque["municipalities"] == (
        "Cariño, Cedeira, Cerdido y 4 más"
    )


def test_catalog_interaction_context_keeps_structured_unabridged_values() -> None:
    dataset = synthetic_dataset()
    original_locations = dataset.project_locations.copy(deep=True)

    context = build_catalog_interaction_context(
        dataset,
        ("project_badulaque",),
    )

    assert context == [{
        "project_id": "project_badulaque",
        "technology": "eolica",
        "autonomous_communities": ("Galicia",),
        "provinces": ("A Coruña",),
        "province_communities": ("Galicia",),
        "municipalities": (
            "Cariño",
            "Cedeira",
            "Cerdido",
            "Mañón",
            "Moeche",
            "Muras",
            "Ortigueira",
        ),
        "municipality_provinces": ("A Coruña",),
        "municipality_communities": ("Galicia",),
    }]
    pd.testing.assert_frame_equal(dataset.project_locations, original_locations)


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("  parque   eólico Mudarra ", "Parque eólico Mudarra"),
        ("PARQUE EÓLICO MUDARRA", "Parque eólico Mudarra"),
        ("HSF ANUBIS", "HSF Anubis"),
        ("SET ATENEA 30/220 KV", "SET Atenea 30/220 kV"),
        ("BESS MUDARRA II 50 MW", "BESS Mudarra II 50 MW"),
    ],
)
def test_project_display_name_is_deterministic_and_preserves_acronyms(
    raw_name: str,
    expected: str,
) -> None:
    assert format_project_display_name(raw_name) == expected


def test_text_search_is_accent_and_case_insensitive() -> None:
    result = filter_projects(synthetic_dataset(), text="fv andevalo")
    assert _ids(result) == {"project_andevalo"}


@pytest.mark.parametrize(
    ("technologies", "expected"),
    [
        (("otra_generacion",), {"project_insular"}),
        (
            ("eolica", "otra_generacion"),
            {"project_badulaque", "project_angostillos", "project_insular"},
        ),
    ],
)
def test_technology_filter_uses_or_within_category(
    technologies: tuple[str, ...],
    expected: set[str],
) -> None:
    assert _ids(filter_projects(
        synthetic_dataset(), technologies=technologies
    )) == expected


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"autonomous_communities": ("Galicia",)}, {"project_badulaque"}),
        (
            {"provinces": ("Huelva",)},
            {"project_puebla", "project_andevalo"},
        ),
        ({"municipalities": ("Campillos",)}, {"project_volateo"}),
        ({"provinces": ("Zaragoza",)}, {"project_angostillos"}),
        (
            {"autonomous_communities": ("Canarias",)},
            {"project_insular"},
        ),
    ],
    ids=["community", "province", "municipality", "province-only", "community-only"],
)
def test_territorial_filters_include_contractual_levels(
    kwargs: dict[str, tuple[str, ...]],
    expected: set[str],
) -> None:
    assert _ids(filter_projects(synthetic_dataset(), **kwargs)) == expected


def test_combined_territorial_filters_use_and_without_duplicates() -> None:
    result = filter_projects(
        synthetic_dataset(),
        autonomous_communities=("Andalucía",),
        provinces=("Málaga",),
        municipalities=("Antequera", "Campillos"),
    )

    assert _ids(result) == {"project_volateo"}
    assert result["project_id"].is_unique


def test_filter_options_follow_territorial_hierarchy() -> None:
    options = get_filter_options(
        synthetic_dataset(),
        autonomous_communities=("Andalucía",),
        provinces=("Huelva",),
    )

    assert "Zaragoza" not in options["provinces"]
    assert options["municipalities"] == ("Alosno", "Puebla de Guzmán")


def test_date_range_is_inclusive() -> None:
    result = filter_projects(
        synthetic_dataset(),
        start_date=pd.Timestamp("2024-03-10"),
        end_date=pd.Timestamp("2024-04-10"),
    )
    assert _ids(result) == {"project_puebla", "project_andevalo"}


def test_date_action_and_decision_apply_to_same_event_rows() -> None:
    dataset = synthetic_dataset()

    passing = filter_projects(
        dataset,
        start_date=pd.Timestamp("2023-01-01"),
        end_date=pd.Timestamp("2023-12-31"),
        action_types=("declaracion_impacto_ambiental",),
        decisions=("desfavorable",),
    )
    impossible_cross_row = filter_projects(
        dataset,
        start_date=pd.Timestamp("2023-01-01"),
        end_date=pd.Timestamp("2023-12-31"),
        action_types=("autorizacion_administrativa_previa",),
        decisions=("desfavorable",),
    )

    assert _ids(passing) == {"project_badulaque", "project_volateo"}
    assert impossible_cross_row.empty


def test_latest_actions_use_the_complete_contractual_tiebreak_order() -> None:
    events = _frame(
        [
            _event(
                "project_badulaque",
                "event_old_date",
                "action_z_old_date",
                "BOE-A-2024-1",
                "2024-01-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                event_index=99,
                action_index=99,
            ),
            _event(
                "project_badulaque",
                "event_low_event",
                "action_z_low_event",
                "BOE-A-2025-1",
                "2025-01-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                event_index=1,
                action_index=99,
            ),
            _event(
                "project_badulaque",
                "event_low_action",
                "action_z_low_action",
                "BOE-A-2025-2",
                "2025-01-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                event_index=2,
                action_index=1,
            ),
            _event(
                "project_badulaque",
                "event_final",
                "action_a_final",
                "BOE-A-2025-3",
                "2025-01-01",
                "autorizacion_administrativa_previa",
                "autorizado",
                event_index=2,
                action_index=2,
            ),
            _event(
                "project_badulaque",
                "event_final",
                "action_z_final",
                "BOE-A-2025-3",
                "2025-01-01",
                "autorizacion_administrativa_previa",
                "autorizado",
                event_index=2,
                action_index=2,
            ),
            _event(
                "project_badulaque",
                "event_dia",
                "action_dia",
                "BOE-A-2023-1",
                "2023-01-01",
                "declaracion_impacto_ambiental",
                "desfavorable",
            ),
        ],
        PROJECT_EVENT_DTYPES,
    ).sample(frac=1, random_state=7).reset_index(drop=True)
    original = events.copy(deep=True)

    latest = build_latest_project_actions(events)

    assert latest[["project_id", "action_type"]].duplicated().sum() == 0
    assert latest["administrative_action_id"].tolist() == [
        "action_z_final",
        "action_dia",
    ]
    pd.testing.assert_frame_equal(events, original)


def test_latest_actions_reject_missing_contractual_columns() -> None:
    events = synthetic_dataset().project_events.drop(columns=["event_index"])

    with pytest.raises(ValueError, match="event_index"):
        build_latest_project_actions(events)


def test_historical_and_latest_modes_diverge_after_a_later_decision() -> None:
    dataset = _with_project_events(
        synthetic_dataset(),
        [
            _event(
                "project_badulaque",
                "event_a_2025",
                "action_a_2025",
                "BOE-A-2025-1",
                "2025-01-10",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
            ),
            _event(
                "project_badulaque",
                "event_a_2026",
                "action_a_2026",
                "BOE-A-2026-1",
                "2026-01-10",
                "autorizacion_administrativa_previa",
                "autorizado",
            ),
        ],
    )

    historical = filter_projects(
        dataset,
        temporal_interpretation="historical",
        decisions=("sometido_informacion_publica",),
    )
    latest_submitted = filter_projects(
        dataset,
        temporal_interpretation="latest",
        decisions=("sometido_informacion_publica",),
    )
    latest_authorized = filter_projects(
        dataset,
        temporal_interpretation="latest",
        decisions=("autorizado",),
    )

    assert _ids(historical) == {"project_badulaque"}
    assert latest_submitted.empty
    assert _ids(latest_authorized) == {"project_badulaque"}


def test_action_type_matching_supports_any_all_and_same_row_filters() -> None:
    dataset = _with_project_events(
        synthetic_dataset(),
        [
            _event(
                "project_badulaque",
                "event_a",
                "action_a_aap",
                "BOE-A-2025-1",
                "2025-06-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                action_index=1,
            ),
            _event(
                "project_badulaque",
                "event_a",
                "action_a_aac",
                "BOE-A-2025-1",
                "2025-06-01",
                "autorizacion_administrativa_construccion",
                "sometido_informacion_publica",
                action_index=2,
            ),
            _event(
                "project_volateo",
                "event_b",
                "action_b_aap",
                "BOE-A-2026-1",
                "2026-06-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                action_index=1,
            ),
            _event(
                "project_volateo",
                "event_b",
                "action_b_aac",
                "BOE-A-2026-1",
                "2026-06-01",
                "autorizacion_administrativa_construccion",
                "autorizado",
                action_index=2,
            ),
        ],
    )
    action_types = (
        "autorizacion_administrativa_previa",
        "autorizacion_administrativa_construccion",
    )

    any_match = filter_projects(
        dataset,
        decisions=("sometido_informacion_publica",),
        action_types=action_types,
        action_match="any",
    )
    all_match = filter_projects(
        dataset,
        decisions=("sometido_informacion_publica",),
        action_types=action_types,
        action_match="all",
    )
    one_action = filter_projects(
        dataset,
        decisions=("sometido_informacion_publica",),
        action_types=("autorizacion_administrativa_construccion",),
        action_match="all",
    )
    no_action = filter_projects(
        dataset,
        decisions=("sometido_informacion_publica",),
    )
    several_decisions = filter_projects(
        dataset,
        decisions=("sometido_informacion_publica", "autorizado"),
        action_types=action_types,
        action_match="all",
    )

    assert _ids(any_match) == {"project_badulaque", "project_volateo"}
    assert _ids(all_match) == {"project_badulaque"}
    assert _ids(one_action) == {"project_badulaque"}
    assert _ids(no_action) == {"project_badulaque", "project_volateo"}
    assert _ids(several_decisions) == {
        "project_badulaque",
        "project_volateo",
    }
    assert all_match["matching_action_types"].iloc[0] == action_types
    assert all_match["project_id"].is_unique


def test_administrative_filters_intersect_date_technology_and_territory() -> None:
    dataset = _with_project_events(
        synthetic_dataset(),
        [
            _event(
                "project_badulaque",
                "event_a",
                "action_a",
                "BOE-A-2025-1",
                "2025-06-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
            ),
            _event(
                "project_volateo",
                "event_b",
                "action_b",
                "BOE-A-2026-1",
                "2026-06-01",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
            ),
        ],
    )

    result = filter_projects(
        dataset,
        technologies=("eolica",),
        autonomous_communities=("Galicia",),
        start_date=pd.Timestamp("2025-01-01"),
        end_date=pd.Timestamp("2025-12-31"),
        decisions=("sometido_informacion_publica",),
    )

    assert _ids(result) == {"project_badulaque"}
    assert result["project_id"].is_unique


def test_coscojar_matches_three_distinct_actions_in_both_modes() -> None:
    dataset = _coscojar_dataset()
    action_types = (
        "evaluacion_impacto_ambiental",
        "autorizacion_administrativa_previa",
        "autorizacion_administrativa_construccion",
    )

    for interpretation in ("latest", "historical"):
        result = filter_projects(
            dataset,
            temporal_interpretation=interpretation,
            decisions=("sometido_informacion_publica",),
            action_types=action_types,
            action_match="all",
        )
        assert _ids(result) == {
            "project_c9b8afc7704b5e1ab5ab8a76bde9aeda"
        }
        assert result["matching_action_types"].iloc[0] == action_types
    assert dataset.project_events["administrative_action_id"].nunique() == 3
    assert dataset.project_events["boe_id"].eq("BOE-B-2026-19389").all()
    assert dataset.project_events["publication_date"].nunique() == 1


def test_matching_summary_and_filters_do_not_mutate_gold_inputs() -> None:
    dataset = _coscojar_dataset()
    originals = {
        name: getattr(dataset, name).copy(deep=True)
        for name in (
            "projects",
            "project_events",
            "project_locations",
            "project_location_sources",
        )
    }

    build_latest_project_actions(dataset.project_events)
    build_matching_action_summary(
        dataset.project_events,
        temporal_interpretation="latest",
        decisions=("sometido_informacion_publica",),
    )
    filter_projects(
        dataset,
        temporal_interpretation="latest",
        decisions=("sometido_informacion_publica",),
    )

    for name, original in originals.items():
        pd.testing.assert_frame_equal(getattr(dataset, name), original)


def test_final_filter_is_intersection_of_catalog_territory_and_events() -> None:
    result = filter_projects(
        synthetic_dataset(),
        text="solar",
        technologies=("fotovoltaica",),
        autonomous_communities=("Andalucía",),
        action_types=("autorizacion_administrativa_previa",),
    )
    assert _ids(result) == {"project_volateo"}


def test_timeline_is_stably_ordered() -> None:
    dataset = synthetic_dataset()
    shuffled = dataset.project_events.sample(frac=1, random_state=4).reset_index(
        drop=True
    )
    changed = GoldDataset(
        projects=dataset.projects,
        project_events=shuffled,
        project_locations=dataset.project_locations,
        project_location_sources=dataset.project_location_sources,
        manifest=dataset.manifest,
        gold_dir=dataset.gold_dir,
        downstream_id=dataset.downstream_id,
    )

    timeline = get_project_timeline(changed, "project_badulaque")

    assert timeline["administrative_action_id"].tolist() == [
        "action_bad_2",
        "action_bad_1",
    ]


def test_timeline_groups_actions_once_per_boe_newest_first() -> None:
    rows = _frame(
        [
            _event(
                "project_badulaque",
                "event_new",
                "action_new",
                "BOE-A-2025-20",
                "2025-02-10",
                "declaracion_utilidad_publica",
                "declarado",
            ),
            _event(
                "project_badulaque",
                "event_old",
                "action_old_2",
                "BOE-A-2024-10",
                "2024-01-10",
                "autorizacion_administrativa_construccion",
                "autorizado",
                action_index=2,
            ),
            _event(
                "project_badulaque",
                "event_old",
                "action_old_1",
                "BOE-A-2024-10",
                "2024-01-10",
                "autorizacion_administrativa_previa",
                "autorizado",
                action_index=1,
            ),
        ],
        PROJECT_EVENT_DTYPES,
    )

    groups = group_project_timeline_by_publication(rows)

    assert [group.boe_id for group in groups] == [
        "BOE-A-2025-20",
        "BOE-A-2024-10",
    ]
    assert [action.administrative_action_id for action in groups[1].actions] == [
        "action_old_1",
        "action_old_2",
    ]


def test_don_rodrigo_timeline_is_newest_first_with_stable_action_order() -> None:
    rows = _frame(
        [
            _event(
                "project_don_rodrigo",
                "BOE-B-2026-12663_event_1",
                "BOE-B-2026-12663_event_1_action_1",
                "BOE-B-2026-12663",
                "2026-04-23",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                action_index=1,
            ),
            _event(
                "project_don_rodrigo",
                "BOE-A-2026-17939_event_1",
                "BOE-A-2026-17939_event_1_action_2",
                "BOE-A-2026-17939",
                "2026-08-19",
                "autorizacion_administrativa_construccion",
                "autorizado",
                action_index=2,
            ),
            _event(
                "project_don_rodrigo",
                "BOE-A-2026-17939_event_1",
                "BOE-A-2026-17939_event_1_action_1",
                "BOE-A-2026-17939",
                "2026-08-19",
                "autorizacion_administrativa_previa",
                "autorizado",
                action_index=1,
            ),
        ],
        PROJECT_EVENT_DTYPES,
    )

    groups = group_project_timeline_by_publication(rows)

    assert [group.boe_id for group in groups] == [
        "BOE-A-2026-17939",
        "BOE-B-2026-12663",
    ]
    assert [
        action.administrative_action_id for action in groups[0].actions
    ] == [
        "BOE-A-2026-17939_event_1_action_1",
        "BOE-A-2026-17939_event_1_action_2",
    ]


def test_project_publication_summary_counts_distinct_actions_without_duplicates(
) -> None:
    dataset = synthetic_dataset()
    timeline = get_project_timeline(dataset, "project_badulaque")
    sources = get_project_location_sources(dataset, "project_badulaque")

    summary = build_project_publication_summary(timeline, sources)

    assert summary["boe_id"].is_unique
    assert summary["administrative_actions"].tolist() == [1, 1]


def test_project_detail_is_complete_and_independent_of_prior_filters() -> None:
    dataset = synthetic_dataset()
    filtered = filter_projects(dataset, text="badulaque")
    assert len(filtered) == 1

    detail = get_project_detail(dataset, "project_volateo")
    locations = get_project_locations(dataset, "project_volateo")
    sources = get_project_location_sources(dataset, "project_volateo")

    assert detail["project_name"] == "Volateo Solar"
    assert len(locations) == 2
    assert len(sources) == 2


def test_unknown_project_raises_specific_error() -> None:
    with pytest.raises(ProjectNotFoundError):
        get_project_detail(synthetic_dataset(), "project_missing")


@pytest.mark.parametrize(
    ("boe_id", "expected_url"),
    [
        (
            "BOE-A-2023-10306",
            "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2023-10306",
        ),
        (
            "BOE-B-2026-19389",
            "https://www.boe.es/diario_boe/txt.php?id=BOE-B-2026-19389",
        ),
    ],
)
def test_build_boe_url_validates_identifier(
    boe_id: str,
    expected_url: str,
) -> None:
    assert build_boe_url(boe_id) == expected_url


def test_build_boe_url_rejects_invalid_identifier() -> None:
    with pytest.raises(ValueError):
        build_boe_url("../../etc/passwd")


def test_observed_domains_have_explicit_labels() -> None:
    assert {
        "eolica",
        "fotovoltaica",
        "hidroelectrica",
        "otra_generacion",
        "termosolar",
    } <= TECHNOLOGY_LABELS.keys()
    assert {
        "autorizacion_administrativa_construccion",
        "autorizacion_administrativa_previa",
        "concesion_aguas",
        "correccion_errores",
        "declaracion_impacto_ambiental",
        "declaracion_utilidad_publica",
        "evaluacion_impacto_ambiental",
        "informe_determinacion_afeccion_ambiental",
        "informe_impacto_ambiental",
        "informacion_publica",
        "levantamiento_actas_previas_ocupacion",
        "modificacion_autorizacion",
        "otro",
        "solicitud_tramitacion",
        "solicitud_tramitacion_ambiental",
        "subsanacion_documentacion",
        "terminacion_procedimiento",
    } <= ACTION_TYPE_LABELS.keys()
    assert {
        "archivado",
        "autorizado",
        "convocado",
        "declarado",
        "denegado",
        "desestimado",
        "desfavorable",
        "desistido",
        "formulado",
        "favorable",
        "modificado",
        "rectificado",
        "requiere_evaluacion_ambiental_ordinaria",
        "sin_efectos_adversos_significativos",
        "solicitado",
        "sometido_informacion_publica",
        "subsanado",
    } <= DECISION_LABELS.keys()
    assert set(LOCATION_LEVEL_LABELS) == {
        "municipality",
        "province",
        "autonomous_community",
    }


def test_unknown_domain_value_is_humanized(caplog) -> None:
    assert label_action_type("future_action") == "Future action"
    assert "future_action" in caplog.text


def test_known_label_functions_keep_canonical_values_outside_display() -> None:
    assert label_technology("eolica") == "Eólica"
    assert label_action_type("autorizacion_administrativa_previa") == (
        "Autorización administrativa previa"
    )
    assert label_decision("desestimado") == "Desestimado"
    assert label_location_level("municipality") == "Municipio"


def test_queries_do_not_mutate_inputs() -> None:
    dataset = synthetic_dataset()
    originals = {
        name: getattr(dataset, name).copy(deep=True)
        for name in (
            "projects",
            "project_events",
            "project_locations",
            "project_location_sources",
        )
    }

    build_project_catalog(dataset)
    build_catalog_interaction_context(dataset, dataset.projects["project_id"])
    filter_projects(dataset, provinces=("Huelva",))
    get_project_timeline(dataset, "project_volateo")
    get_project_locations(dataset, "project_volateo")
    get_project_location_sources(dataset, "project_volateo")

    for name, original in originals.items():
        pd.testing.assert_frame_equal(getattr(dataset, name), original)


def test_dashboard_metrics_count_distinct_projects_and_boe() -> None:
    dataset = synthetic_dataset()
    duplicated_boe = dataset.project_events.iloc[[0]].copy()
    duplicated_boe["project_id"] = "project_volateo"
    duplicated_boe["event_id"] = "event_vol_shared"
    duplicated_boe["administrative_action_id"] = "action_vol_shared"
    shared = _with_project_events(
        dataset,
        pd.concat([dataset.project_events, duplicated_boe], ignore_index=True),
    )

    metrics = summarize_dashboard_selection(build_dashboard_selection(shared))

    assert metrics.projects == 6
    assert metrics.relevant_boe_publications == dataset.project_events[
        "boe_id"
    ].nunique()


def test_publication_counts_deduplicate_project_events_from_same_boe() -> None:
    dataset = synthetic_dataset()
    repeated = pd.concat(
        [dataset.project_events, dataset.project_events.iloc[[0]]],
        ignore_index=True,
    )

    counts = build_publication_counts(repeated)

    assert counts["boe_publications"].sum() == dataset.project_events[
        "boe_id"
    ].nunique()
    assert list(counts.columns) == ["publication_year", "boe_publications"]


def test_yearly_project_counts_count_distinct_projects_with_publication() -> None:
    dataset = synthetic_dataset()
    repeated = pd.concat(
        [dataset.project_events, dataset.project_events.iloc[[0]]],
        ignore_index=True,
    )

    counts = build_yearly_project_counts(repeated)

    assert list(counts.columns) == ["publication_year", "projects"]
    assert counts.set_index("publication_year")["projects"].to_dict() == {
        2023: 2,
        2024: 5,
        2025: 1,
    }


def test_chart_year_selection_builds_exact_calendar_filter_and_can_clear() -> None:
    selected = build_chart_year_filter(2022, available_years=range(2022, 2027))
    cleared = build_chart_year_filter(None, available_years=range(2022, 2027))

    assert selected.publication_years == (2022,)
    assert selected.start_date == date(2022, 1, 1)
    assert selected.end_date == date(2022, 12, 31)
    assert cleared.publication_years == ()
    assert cleared.start_date is None
    assert cleared.end_date is None


def test_chart_year_filter_composes_with_existing_catalogue_filters() -> None:
    temporal = build_chart_year_filter(2024, available_years=range(2022, 2027))

    selection = build_dashboard_selection(
        synthetic_dataset(),
        technologies=("fotovoltaica",),
        autonomous_communities=("Andalucía",),
        publication_years=temporal.publication_years,
        start_date=temporal.start_date,
        end_date=temporal.end_date,
        temporal_interpretation="historical",
    )

    assert set(selection.projects["project_id"]) == {
        "project_puebla",
        "project_andevalo",
    }
    assert set(selection.supporting_events["publication_date"].dt.year) == {2024}


def test_chart_selection_parser_handles_streamlit_point_selection() -> None:
    state = {
        "selection": {
            "project_year_selection": [{"publication_year": 2024}],
        }
    }

    assert extract_chart_selected_year(
        state,
        selection_name="project_year_selection",
        available_years=range(2022, 2027),
    ) == 2024
    assert extract_chart_selected_year(
        {"selection": {"project_year_selection": []}},
        selection_name="project_year_selection",
        available_years=range(2022, 2027),
    ) is None


def test_chart_selection_parser_reads_named_cross_filter_fields() -> None:
    state = {
        "selection": {
            "administrative_selection": [{
                "action_type": "declaracion_impacto_ambiental",
                "decision": "favorable",
            }],
        }
    }

    assert extract_chart_selected_values(
        state,
        selection_name="administrative_selection",
        fields=("action_type", "decision"),
    ) == {
        "action_type": "declaracion_impacto_ambiental",
        "decision": "favorable",
    }
    assert extract_chart_selected_values(
        {"selection": {"administrative_selection": []}},
        selection_name="administrative_selection",
        fields=("action_type", "decision"),
    ) is None


def test_administrative_counts_use_distinct_projects_per_action_and_decision() -> None:
    dataset = synthetic_dataset()
    duplicated = pd.concat(
        [dataset.project_events, dataset.project_events.iloc[[0]]],
        ignore_index=True,
    )

    counts = build_administrative_situation_counts(
        duplicated,
        temporal_interpretation="historical",
    )

    row = counts[
        (counts["action_type"] == "declaracion_impacto_ambiental")
        & (counts["decision"] == "desfavorable")
    ].iloc[0]
    assert int(row["project_count"]) == 2


def test_territory_counts_deduplicate_project_and_code() -> None:
    dataset = synthetic_dataset()
    duplicate = dataset.project_locations.iloc[[0]].copy()
    duplicate["project_location_id"] = "location_duplicate_source"
    locations = pd.concat(
        [dataset.project_locations, duplicate],
        ignore_index=True,
    )

    counts = build_territory_project_counts(
        locations,
        project_ids=dataset.projects["project_id"],
        level="municipality",
    )

    badulaque = counts[counts["code"] == "15001"].iloc[0]
    assert int(badulaque["project_count"]) == 1


def test_publication_year_composes_with_technology_and_territory() -> None:
    dataset = synthetic_dataset()

    selection = build_dashboard_selection(
        dataset,
        technologies=["fotovoltaica"],
        autonomous_communities=["Andalucía"],
        publication_years=[2024],
    )

    assert set(selection.projects["project_id"]) == {
        "project_puebla",
        "project_andevalo",
    }
    assert set(selection.supporting_events["publication_date"].dt.year) == {2024}


def test_project_without_resolved_territory_remains_in_dashboard_but_not_map() -> None:
    source = synthetic_dataset()
    locations = source.project_locations[
        source.project_locations["project_id"] != "project_insular"
    ].reset_index(drop=True)
    dataset = GoldDataset(
        projects=source.projects,
        project_events=source.project_events,
        project_locations=locations,
        project_location_sources=source.project_location_sources,
        manifest=source.manifest,
        gold_dir=source.gold_dir,
        downstream_id=source.downstream_id,
    )

    selection = build_dashboard_selection(dataset)
    map_counts = build_territory_project_counts(
        locations,
        project_ids=selection.projects["project_id"],
        level="autonomous_community",
    )

    assert "project_insular" in set(selection.projects["project_id"])
    assert summarize_dashboard_selection(selection).projects == 6
    assert int(map_counts["project_count"].sum()) == 5


def test_27607_shared_action_appears_once_in_each_project_chronology() -> None:
    source = synthetic_dataset()
    projects = source.projects.copy()
    identities = (
        ("project_badulaque", "HSF ANUBIS"),
        ("project_volateo", "HSF AFRODITA"),
        ("project_puebla", "HSF DEMETER"),
    )
    for project_id, name in identities:
        projects.loc[projects["project_id"].eq(project_id), "project_name"] = name
    rows = [
        _event(
            project_id,
            "event_27607",
            "action_27607_shared_dup",
            "BOE-B-2023-27607",
            "2023-11-18",
            "declaracion_utilidad_publica",
            "declarado",
        )
        for project_id, _ in identities
    ]
    dataset = GoldDataset(
        projects=projects,
        project_events=_frame(rows, PROJECT_EVENT_DTYPES),
        project_locations=source.project_locations,
        project_location_sources=source.project_location_sources,
        manifest=source.manifest,
        gold_dir=source.gold_dir,
        downstream_id=source.downstream_id,
    )

    for project_id, _ in identities:
        timeline = get_project_timeline(dataset, project_id)
        assert len(timeline) == 1
        assert timeline.iloc[0]["administrative_action_id"] == (
            "action_27607_shared_dup"
        )
    counts = build_administrative_situation_counts(dataset.project_events)
    assert int(counts.iloc[0]["project_count"]) == 3


@pytest.mark.parametrize(
    ("project_id", "name"),
    [
        ("project_badulaque", "Parque Eólico Badulaque"),
        ("project_volateo", "Volateo Solar"),
        ("project_puebla", "La Puebla 1"),
        ("project_andevalo", "FV Andévalo"),
        ("project_angostillos", "PE Angostillos"),
    ],
)
def test_regression_projects_are_retrievable(
    project_id: str,
    name: str,
) -> None:
    detail = get_project_detail(synthetic_dataset(), project_id)
    assert detail["project_name"] == name
