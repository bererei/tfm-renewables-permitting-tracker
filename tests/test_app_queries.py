from __future__ import annotations

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
    build_boe_url,
    build_project_catalog,
    filter_projects,
    get_filter_options,
    get_project_detail,
    get_project_location_sources,
    get_project_locations,
    get_project_timeline,
    label_action_type,
    label_decision,
    label_location_level,
    label_technology,
)


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
        {
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
        },
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
        "action_bad_1",
        "action_bad_2",
    ]


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


def test_build_boe_url_validates_identifier() -> None:
    assert build_boe_url("BOE-A-2024-100") == (
        "https://www.boe.es/txt.php?id=BOE-A-2024-100"
    )
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
        "declaracion_impacto_ambiental",
        "declaracion_utilidad_publica",
        "evaluacion_impacto_ambiental",
        "informe_determinacion_afeccion_ambiental",
        "informe_impacto_ambiental",
        "levantamiento_actas_previas_ocupacion",
        "otro",
        "terminacion_procedimiento",
    } <= ACTION_TYPE_LABELS.keys()
    assert {
        "archivado",
        "autorizado",
        "convocado",
        "declarado",
        "desestimado",
        "desfavorable",
        "desistido",
        "formulado",
        "requiere_evaluacion_ambiental_ordinaria",
        "sin_efectos_adversos_significativos",
        "sometido_informacion_publica",
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
    filter_projects(dataset, provinces=("Huelva",))
    get_project_timeline(dataset, "project_volateo")
    get_project_locations(dataset, "project_volateo")
    get_project_location_sources(dataset, "project_volateo")

    for name, original in originals.items():
        pd.testing.assert_frame_equal(getattr(dataset, name), original)


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
