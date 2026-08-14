from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pytest

from renewables_permitting.project_locations import (
    PROJECT_LOCATION_SOURCES_COLUMNS,
    PROJECT_LOCATIONS_COLUMNS,
    build_project_locations,
    project_locations_semantic_hash,
    validate_project_locations,
)


def _frame(
    rows: list[dict[str, object]],
    columns: tuple[str, ...],
    dtypes: Mapping[str, str],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    for column, dtype in dtypes.items():
        if dtype == "datetime64[ns]":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def _location(
    *,
    event_id: str,
    boe_id: str,
    publication_date: str,
    location_id: str,
    municipality: str | None = None,
    municipality_code: str | None = None,
    municipality_status: str = "not_provided",
    province: str | None = None,
    province_code: str | None = None,
    province_status: str = "not_provided",
    autonomous_community: str | None = None,
    autonomous_community_code: str | None = None,
    autonomous_community_status: str = "not_provided",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "identificador_boe": boe_id,
        "fecha_publicacion": publication_date,
        "location_mention_id": location_id,
        "municipality": municipality,
        "municipality_norm": municipality.casefold() if municipality else None,
        "ine_municipality_code": municipality_code,
        "municipality_resolution_status": municipality_status,
        "province": province,
        "province_norm": province.casefold() if province else None,
        "ine_province_code": province_code,
        "province_resolution_status": province_status,
        "autonomous_community": autonomous_community,
        "autonomous_community_norm": (
            autonomous_community.casefold() if autonomous_community else None
        ),
        "ine_autonomous_community_code": autonomous_community_code,
        "autonomous_community_resolution_status": autonomous_community_status,
    }


def _inputs() -> dict[str, pd.DataFrame]:
    events = [
        ("event_municipality", "BOE-A-2024-1", "2024-01-10"),
        ("event_municipality_later", "BOE-A-2025-2", "2025-02-20"),
        ("event_province", "BOE-A-2024-3", "2024-03-15"),
        ("event_autonomous", "BOE-A-2024-4", "2024-04-16"),
        ("event_unresolved", "BOE-A-2024-5", "2024-05-17"),
        ("event_multi", "BOE-A-2024-6", "2024-06-18"),
    ]
    publication_events = _frame(
        [
            {
                "event_id": event_id,
                "identificador_boe": boe_id,
                "fecha_publicacion": publication_date,
            }
            for event_id, boe_id, publication_date in events
        ],
        ("event_id", "identificador_boe", "fecha_publicacion"),
        {
            "event_id": "string",
            "identificador_boe": "string",
            "fecha_publicacion": "datetime64[ns]",
        },
    )
    asset_rows = [
        ("event_municipality", "asset_a_1", "project_a"),
        ("event_municipality_later", "asset_a_2", "project_a"),
        ("event_province", "asset_b", "project_b"),
        ("event_autonomous", "asset_c", "project_c"),
        ("event_unresolved", "asset_d", "project_d"),
        ("event_multi", "asset_e", "project_e"),
        ("event_multi", "asset_f", "project_f"),
    ]
    generation_asset_mentions = _frame(
        [
            {
                "event_id": event_id,
                "generation_asset_mention_id": asset_id,
            }
            for event_id, asset_id, _ in asset_rows
        ],
        ("event_id", "generation_asset_mention_id"),
        {"event_id": "string", "generation_asset_mention_id": "string"},
    )
    project_grouping = _frame(
        [
            {
                "generation_asset_mention_id": asset_id,
                "project_id": project_id,
            }
            for _, asset_id, project_id in asset_rows
        ],
        ("generation_asset_mention_id", "project_id"),
        {"generation_asset_mention_id": "string", "project_id": "string"},
    )
    project_ids = sorted({project_id for _, _, project_id in asset_rows})
    projects = _frame(
        [{"project_id": project_id} for project_id in project_ids],
        ("project_id",),
        {"project_id": "string"},
    )
    locations = [
        _location(
            event_id="event_municipality",
            boe_id="BOE-A-2024-1",
            publication_date="2024-01-10",
            location_id="location_municipality_1",
            municipality="Antequera",
            municipality_code="29015",
            municipality_status="resolved",
            province="Málaga",
            province_code="29",
            province_status="resolved",
            autonomous_community="Andalucía",
            autonomous_community_code="01",
            autonomous_community_status="resolved",
        ),
        _location(
            event_id="event_municipality",
            boe_id="BOE-A-2024-1",
            publication_date="2024-01-10",
            location_id="location_municipality_2",
            municipality="Antequera",
            municipality_code="29015",
            municipality_status="resolved",
            province="Málaga",
            province_code="29",
            province_status="resolved",
            autonomous_community="Andalucía",
            autonomous_community_code="01",
            autonomous_community_status="resolved",
        ),
        _location(
            event_id="event_municipality_later",
            boe_id="BOE-A-2025-2",
            publication_date="2025-02-20",
            location_id="location_municipality_3",
            municipality="Antequera",
            municipality_code="29015",
            municipality_status="resolved",
            province="Málaga",
            province_code="29",
            province_status="resolved",
            autonomous_community="Andalucía",
            autonomous_community_code="01",
            autonomous_community_status="resolved",
        ),
        _location(
            event_id="event_province",
            boe_id="BOE-A-2024-3",
            publication_date="2024-03-15",
            location_id="location_province",
            municipality_status="not_found",
            province="Huelva",
            province_code="21",
            province_status="resolved",
            autonomous_community="Andalucía",
            autonomous_community_code="01",
            autonomous_community_status="resolved",
        ),
        _location(
            event_id="event_autonomous",
            boe_id="BOE-A-2024-4",
            publication_date="2024-04-16",
            location_id="location_autonomous",
            municipality_status="not_found",
            province_status="not_found",
            autonomous_community="Galicia",
            autonomous_community_code="12",
            autonomous_community_status="resolved",
        ),
        _location(
            event_id="event_unresolved",
            boe_id="BOE-A-2024-5",
            publication_date="2024-05-17",
            location_id="location_unresolved",
            municipality_status="not_found",
            province_status="not_found",
            autonomous_community_status="not_found",
        ),
        _location(
            event_id="event_multi",
            boe_id="BOE-A-2024-6",
            publication_date="2024-06-18",
            location_id="location_multi",
            municipality="Alosno",
            municipality_code="21006",
            municipality_status="resolved",
            province="Huelva",
            province_code="21",
            province_status="resolved",
            autonomous_community="Andalucía",
            autonomous_community_code="01",
            autonomous_community_status="resolved",
        ),
    ]
    resolved_locations = _frame(
        locations,
        tuple(locations[0]),
        {
            "event_id": "string",
            "identificador_boe": "string",
            "fecha_publicacion": "datetime64[ns]",
            "location_mention_id": "string",
            "municipality": "string",
            "municipality_norm": "string",
            "ine_municipality_code": "string",
            "municipality_resolution_status": "string",
            "province": "string",
            "province_norm": "string",
            "ine_province_code": "string",
            "province_resolution_status": "string",
            "autonomous_community": "string",
            "autonomous_community_norm": "string",
            "ine_autonomous_community_code": "string",
            "autonomous_community_resolution_status": "string",
        },
    )
    return {
        "publication_events": publication_events,
        "generation_asset_mentions": generation_asset_mentions,
        "project_grouping": project_grouping,
        "projects": projects,
        "resolved_locations": resolved_locations,
    }


def test_empty_project_location_tables_are_typed() -> None:
    inputs = {
        name: frame.iloc[0:0].copy()
        for name, frame in _inputs().items()
    }

    result = build_project_locations(**inputs)

    assert set(result) == {"project_locations", "project_location_sources"}
    assert tuple(result["project_locations"].columns) == PROJECT_LOCATIONS_COLUMNS
    assert tuple(result["project_location_sources"].columns) == (
        PROJECT_LOCATION_SOURCES_COLUMNS
    )
    assert result["project_locations"].empty
    assert result["project_location_sources"].empty
    assert all(
        str(dtype) != "object"
        for frame in result.values()
        for dtype in frame.dtypes
    )


def test_all_three_location_levels_follow_the_exact_contract() -> None:
    result = build_project_locations(**_inputs())["project_locations"]
    by_project = result.set_index("project_id")

    assert set(result["location_level"]) == {
        "municipality",
        "province",
        "autonomous_community",
    }
    assert "location_role" not in result.columns
    assert by_project.loc["project_a", "ine_municipality_code"] == "29015"
    assert by_project.loc["project_a", "ine_province_code"] == "29"
    assert by_project.loc["project_a", "ine_autonomous_community_code"] == "01"
    assert pd.isna(by_project.loc["project_b", "municipality"])
    assert by_project.loc["project_b", "province"] == "Huelva"
    assert pd.isna(by_project.loc["project_c", "province"])
    assert by_project.loc["project_c", "autonomous_community"] == "Galicia"


@pytest.mark.parametrize(
    ("project_id", "column", "value", "message"),
    [
        ("project_a", "province", pd.NA, "province"),
        ("project_b", "municipality", "Inventado", "province"),
        ("project_c", "province", "Inventada", "autonomous_community"),
        ("project_a", "ine_municipality_code", "29A15", "código"),
        ("project_b", "ine_province_code", pd.NA, "ine_province_code"),
    ],
)
def test_invalid_level_nullability_or_codes_fail_closed(
    project_id: str,
    column: str,
    value: object,
    message: str,
) -> None:
    inputs = _inputs()
    result = build_project_locations(**inputs)
    locations = result["project_locations"].copy(deep=True)
    locations.loc[locations["project_id"] == project_id, column] = value

    with pytest.raises(ValueError, match=message):
        validate_project_locations(
            locations,
            result["project_location_sources"],
            **inputs,
        )


def test_ids_are_stable_under_reordering_and_change_with_semantics() -> None:
    inputs = _inputs()
    first = build_project_locations(**inputs)
    shuffled_inputs = {
        name: frame.sample(frac=1, random_state=index).reset_index(drop=True)
        for index, (name, frame) in enumerate(inputs.items(), start=1)
    }
    shuffled = build_project_locations(**shuffled_inputs)

    pd.testing.assert_frame_equal(
        first["project_locations"], shuffled["project_locations"]
    )
    pd.testing.assert_frame_equal(
        first["project_location_sources"],
        shuffled["project_location_sources"],
    )
    locations = first["project_locations"].set_index("project_id")
    assert locations.loc["project_e", "project_location_id"] != locations.loc[
        "project_f", "project_location_id"
    ]
    assert len(set(locations["project_location_id"])) == len(locations)

    changed_code_inputs = _inputs()
    changed_code_inputs["resolved_locations"].loc[
        changed_code_inputs["resolved_locations"]["location_mention_id"]
        == "location_province",
        "ine_province_code",
    ] = "22"
    changed_code = build_project_locations(**changed_code_inputs)[
        "project_locations"
    ].set_index("project_id")
    assert changed_code.loc["project_b", "project_location_id"] != locations.loc[
        "project_b", "project_location_id"
    ]

    changed_level_inputs = _inputs()
    changed_level_inputs["resolved_locations"].loc[
        changed_level_inputs["resolved_locations"]["location_mention_id"]
        == "location_province",
        "province_resolution_status",
    ] = "not_found"
    changed_level = build_project_locations(**changed_level_inputs)[
        "project_locations"
    ].set_index("project_id")
    assert changed_level.loc[
        "project_b", "project_location_id"
    ] != locations.loc["project_b", "project_location_id"]


def test_aggregation_sources_unresolved_and_multiproject_expansion() -> None:
    result = build_project_locations(**_inputs())
    locations = result["project_locations"].set_index("project_id")
    sources = result["project_location_sources"]

    assert len(locations) == 5
    assert len(sources) == 7
    assert locations.loc["project_a", "source_location_mention_count"] == 3
    assert locations.loc["project_a", "source_publication_count"] == 2
    assert locations.loc["project_a", "first_publication_date"] == pd.Timestamp(
        "2024-01-10"
    )
    assert locations.loc["project_a", "last_publication_date"] == pd.Timestamp(
        "2025-02-20"
    )
    assert "project_d" not in locations.index
    multi_sources = sources.loc[sources["location_mention_id"] == "location_multi"]
    assert len(multi_sources) == 2
    assert multi_sources["project_location_id"].nunique() == 2
    assert "location_unresolved" not in set(sources["location_mention_id"])


def test_duplicate_source_mentions_fail_closed() -> None:
    inputs = _inputs()
    inputs["resolved_locations"] = pd.concat(
        [inputs["resolved_locations"], inputs["resolved_locations"].iloc[[0]]],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="location_mention_id.*duplicad"):
        build_project_locations(**inputs)


def test_bridge_and_aggregate_tampering_are_rejected() -> None:
    inputs = _inputs()
    result = build_project_locations(**inputs)
    broken_sources = result["project_location_sources"].copy(deep=True)
    broken_sources.loc[0, "boe_id"] = "BOE-A-2099-999"

    with pytest.raises(ValueError, match="fuentes|BOE|reconstru"):
        validate_project_locations(
            result["project_locations"],
            broken_sources,
            **inputs,
        )

    broken_locations = result["project_locations"].copy(deep=True)
    broken_locations.loc[0, "source_location_mention_count"] += 1
    with pytest.raises(ValueError, match="reconstru|conteo"):
        validate_project_locations(
            broken_locations,
            result["project_location_sources"],
            **inputs,
        )


def test_project_location_semantic_hash_is_order_independent() -> None:
    result = build_project_locations(**_inputs())
    first = project_locations_semantic_hash(
        result["project_locations"], result["project_location_sources"]
    )
    reordered = project_locations_semantic_hash(
        result["project_locations"].iloc[::-1].reset_index(drop=True),
        result["project_location_sources"].iloc[::-1].reset_index(drop=True),
    )

    assert first == reordered
    assert len(first) == 64
