from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from renewables_permitting.project_grouping import (
    PROJECT_GROUPING_COLUMNS,
    group_projects,
)


@dataclass(frozen=True)
class MentionSpec:
    mention_id: str
    names: tuple[str, ...]
    generation_type: str = "eolica"
    province_code: str | None = "21"
    autonomous_community_code: str | None = "01"
    municipality_code: str | None = None


def _grouping_inputs(
    *specs: MentionSpec,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    asset_rows: list[dict[str, object]] = []
    name_rows: list[dict[str, object]] = []
    location_rows: list[dict[str, object]] = []
    for index, spec in enumerate(specs, start=1):
        event_id = f"event_{spec.mention_id}"
        boe_id = f"BOE-A-2026-{index}"
        publication_date = pd.Timestamp(2026, 1, index)
        asset_rows.append(
            {
                "event_id": event_id,
                "identificador_boe": boe_id,
                "fecha_publicacion": publication_date,
                "generation_asset_mention_id": spec.mention_id,
                "local_generation_asset_ref": "generation_asset_1",
                "generation_type": spec.generation_type,
                "evidence": spec.names[0],
            }
        )
        for name_index, name in enumerate(spec.names, start=1):
            name_rows.append(
                {
                    "event_id": event_id,
                    "identificador_boe": boe_id,
                    "fecha_publicacion": publication_date,
                    "generation_asset_mention_id": spec.mention_id,
                    "name_index": name_index,
                    "name_raw": name,
                }
            )
        if (
            spec.province_code is not None
            or spec.autonomous_community_code is not None
        ):
            location_rows.append(
                {
                    "event_id": event_id,
                    "location_mention_id": f"location_{spec.mention_id}",
                    "ine_municipality_code": spec.municipality_code,
                    "municipality_resolution_status": (
                        "resolved"
                        if spec.municipality_code is not None
                        else "not_provided"
                    ),
                    "ine_province_code": spec.province_code,
                    "province_resolution_status": (
                        "resolved"
                        if spec.province_code is not None
                        else "not_provided"
                    ),
                    "ine_autonomous_community_code": (
                        spec.autonomous_community_code
                    ),
                    "autonomous_community_resolution_status": (
                        "resolved"
                        if spec.autonomous_community_code is not None
                        else "not_provided"
                    ),
                }
            )

    asset_columns = (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_mention_id",
        "local_generation_asset_ref",
        "generation_type",
        "evidence",
    )
    name_columns = (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_mention_id",
        "name_index",
        "name_raw",
    )
    location_columns = (
        "event_id",
        "location_mention_id",
        "ine_municipality_code",
        "municipality_resolution_status",
        "ine_province_code",
        "province_resolution_status",
        "ine_autonomous_community_code",
        "autonomous_community_resolution_status",
    )
    assets = pd.DataFrame(asset_rows, columns=asset_columns)
    names = pd.DataFrame(name_rows, columns=name_columns)
    locations = pd.DataFrame(location_rows, columns=location_columns)
    assets["fecha_publicacion"] = pd.to_datetime(assets["fecha_publicacion"])
    names["fecha_publicacion"] = pd.to_datetime(names["fecha_publicacion"])
    for frame in (assets, names, locations):
        for column in frame.columns:
            if column not in {"fecha_publicacion", "name_index"}:
                frame[column] = frame[column].astype("string")
    if "name_index" in names:
        names["name_index"] = names["name_index"].astype("Int64")
    return assets, names, locations


def _group(*specs: MentionSpec) -> pd.DataFrame:
    return group_projects(*_grouping_inputs(*specs))


def _project_ids(result: pd.DataFrame) -> dict[str, str]:
    return result.set_index("generation_asset_mention_id")["project_id"].to_dict()


def test_exact_identity_groups_mentions() -> None:
    result = _group(
        MentionSpec("mention_a", ("Parque Eólico Alfa",)),
        MentionSpec("mention_b", ("Parque Eólico Alfa",)),
    )

    assert result["project_id"].nunique() == 1
    assert result["project_match_method"].unique().tolist() == [
        "strong_exact_name"
    ]


def test_supported_documentary_prefix_variant_groups_mentions() -> None:
    result = _group(
        MentionSpec("mention_a", ("Parque Eólico Alfa",)),
        MentionSpec("mention_b", ("PE Alfa",)),
    )

    assert result["project_id"].nunique() == 1
    assert result["project_match_method"].unique().tolist() == [
        "documentary_variant"
    ]


@pytest.mark.parametrize(
    ("first_name", "second_name"),
    [
        ("Los Naipes", "Los Naipes II"),
        ("Alfa", "Alfa II"),
        ("Proyecto X", "Proyecto X Norte"),
    ],
)
def test_distinctive_name_suffixes_never_merge(
    first_name: str,
    second_name: str,
) -> None:
    result = _group(
        MentionSpec("mention_a", (first_name,)),
        MentionSpec("mention_b", (second_name,)),
    )

    assert result["project_id"].nunique() == 2


def test_alias_set_preserves_the_most_specific_identity() -> None:
    result = _group(
        MentionSpec("mention_specific", ("Los Naipes", "Los Naipes II")),
        MentionSpec("mention_generic", ("Los Naipes",)),
    )

    assert result["project_id"].nunique() == 2


def test_incompatible_generation_technologies_never_merge() -> None:
    result = _group(
        MentionSpec("mention_wind", ("Parque X",), "eolica"),
        MentionSpec("mention_solar", ("Parque X",), "fotovoltaica"),
    )

    assert result["project_id"].nunique() == 2


def test_contradictory_reliable_provinces_never_merge() -> None:
    result = _group(
        MentionSpec("mention_huelva", ("Parque Alfa",), province_code="21"),
        MentionSpec(
            "mention_zaragoza",
            ("Parque Alfa",),
            province_code="50",
            autonomous_community_code="02",
        ),
    )

    assert result["project_id"].nunique() == 2


def test_missing_municipality_does_not_prevent_province_match() -> None:
    result = _group(
        MentionSpec("mention_a", ("Parque Alfa",), municipality_code=None),
        MentionSpec("mention_b", ("Parque Alfa",), municipality_code=None),
    )

    assert result["project_id"].nunique() == 1


def test_autonomous_community_is_used_only_when_province_is_unavailable() -> None:
    same_community = _group(
        MentionSpec(
            "mention_a",
            ("Parque Alfa",),
            province_code=None,
            autonomous_community_code="01",
        ),
        MentionSpec(
            "mention_b",
            ("Parque Alfa",),
            province_code=None,
            autonomous_community_code="01",
        ),
    )
    different_communities = _group(
        MentionSpec(
            "mention_a",
            ("Parque Alfa",),
            province_code=None,
            autonomous_community_code="01",
        ),
        MentionSpec(
            "mention_b",
            ("Parque Alfa",),
            province_code=None,
            autonomous_community_code="02",
        ),
    )

    assert same_community["project_id"].nunique() == 1
    assert different_communities["project_id"].nunique() == 2


def test_input_order_does_not_change_mapping_or_inputs() -> None:
    assets, names, locations = _grouping_inputs(
        MentionSpec("mention_a", ("Parque Eólico Alfa", "PE Alfa")),
        MentionSpec("mention_b", ("PE Alfa",)),
        MentionSpec("mention_c", ("Alfa II",)),
    )
    original_assets = assets.copy(deep=True)
    original_names = names.copy(deep=True)
    original_locations = locations.copy(deep=True)

    first = group_projects(assets, names, locations)
    second = group_projects(
        assets.sample(frac=1, random_state=1),
        names.sample(frac=1, random_state=2),
        locations.sample(frac=1, random_state=3),
    )

    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(assets, original_assets)
    pd.testing.assert_frame_equal(names, original_names)
    pd.testing.assert_frame_equal(locations, original_locations)


def test_repeated_execution_is_reproducible() -> None:
    inputs = _grouping_inputs(
        MentionSpec("mention_a", ("Parque Eólico Alfa",)),
        MentionSpec("mention_b", ("PE Alfa",)),
    )

    pd.testing.assert_frame_equal(
        group_projects(*inputs),
        group_projects(*inputs),
    )


def test_empty_inputs_return_stable_typed_schema() -> None:
    assets, names, locations = _grouping_inputs()

    result = group_projects(assets, names, locations)

    assert result.empty
    assert tuple(result.columns) == PROJECT_GROUPING_COLUMNS
    assert all(str(result[column].dtype) == "string" for column in result)


def test_project_id_is_stable_when_corpus_grows() -> None:
    initial = _group(
        MentionSpec("mention_a", ("Parque Eólico Alfa",)),
        MentionSpec("mention_b", ("PE Alfa",)),
    )
    grown = _group(
        MentionSpec("mention_a", ("Parque Eólico Alfa",)),
        MentionSpec("mention_b", ("PE Alfa",)),
        MentionSpec("mention_c", ("Planta eólica Alfa",)),
    )

    initial_ids = _project_ids(initial)
    grown_ids = _project_ids(grown)
    assert grown_ids["mention_a"] == initial_ids["mention_a"]
    assert grown_ids["mention_b"] == initial_ids["mention_b"]
    assert grown["project_id"].nunique() == 1


def test_added_municipality_does_not_change_province_anchored_project_id() -> None:
    without_municipality = _group(
        MentionSpec("mention_a", ("Parque Alfa",), municipality_code=None),
    )
    with_municipality = _group(
        MentionSpec("mention_a", ("Parque Alfa",), municipality_code="21001"),
    )

    assert _project_ids(without_municipality) == _project_ids(with_municipality)


def test_anti_transitivity_never_creates_contradictory_cluster() -> None:
    result = _group(
        MentionSpec("mention_a", ("Parque Alfa",), province_code="21"),
        MentionSpec(
            "mention_b",
            ("Parque Alfa",),
            province_code=None,
            autonomous_community_code=None,
        ),
        MentionSpec(
            "mention_c",
            ("Parque Alfa",),
            province_code="50",
            autonomous_community_code="02",
        ),
    )

    assert result["project_id"].nunique() != 1


def test_unsafe_location_resolution_is_rejected_instead_of_merged() -> None:
    assets, names, locations = _grouping_inputs(
        MentionSpec("mention_a", ("Parque Alfa",)),
    )
    locations.loc[0, "province_resolution_status"] = "conflict"

    with pytest.raises(ValueError, match="conflict.*requires_inspection"):
        group_projects(assets, names, locations)
