from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pytest

from renewables_permitting.gold import (
    PROJECT_EVENTS_COLUMNS,
    PROJECTS_COLUMNS,
    build_gold_tables,
    build_project_events,
    build_projects,
)
from renewables_permitting.project_locations import (
    PROJECT_LOCATION_SOURCES_COLUMNS,
    PROJECT_LOCATIONS_COLUMNS,
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


def _gold_inputs() -> dict[str, pd.DataFrame]:
    publication_events = _frame(
        [
            {
                "event_id": "event_a_1",
                "identificador_boe": "BOE-A-2023-1",
                "fecha_publicacion": "2023-01-10",
                "event_index": 1,
            },
            {
                "event_id": "event_multi",
                "identificador_boe": "BOE-A-2024-3",
                "fecha_publicacion": "2024-03-15",
                "event_index": 1,
            },
            {
                "event_id": "event_a_2",
                "identificador_boe": "BOE-A-2025-2",
                "fecha_publicacion": "2025-02-20",
                "event_index": 1,
            },
        ],
        ("event_id", "identificador_boe", "fecha_publicacion", "event_index"),
        {
            "event_id": "string",
            "identificador_boe": "string",
            "fecha_publicacion": "datetime64[ns]",
            "event_index": "Int64",
        },
    )
    generation_asset_mentions = _frame(
        [
            {
                "event_id": "event_a_1",
                "generation_asset_mention_id": "asset_a_1",
                "generation_type": "fotovoltaica",
            },
            {
                "event_id": "event_a_2",
                "generation_asset_mention_id": "asset_a_2",
                "generation_type": "fotovoltaica",
            },
            {
                "event_id": "event_multi",
                "generation_asset_mention_id": "asset_b",
                "generation_type": "eolica",
            },
            {
                "event_id": "event_multi",
                "generation_asset_mention_id": "asset_c",
                "generation_type": "fotovoltaica",
            },
        ],
        ("event_id", "generation_asset_mention_id", "generation_type"),
        {
            "event_id": "string",
            "generation_asset_mention_id": "string",
            "generation_type": "string",
        },
    )
    generation_asset_names = _frame(
        [
            {
                "event_id": "event_a_1",
                "generation_asset_mention_id": "asset_a_1",
                "name_index": 1,
                "name_raw": "PFV Volateo Solar",
            },
            {
                "event_id": "event_a_2",
                "generation_asset_mention_id": "asset_a_2",
                "name_index": 1,
                "name_raw": "Planta Fotovoltaica Volateo Solar",
            },
            {
                "event_id": "event_multi",
                "generation_asset_mention_id": "asset_b",
                "name_index": 1,
                "name_raw": "Parque Eólico Beta",
            },
            {
                "event_id": "event_multi",
                "generation_asset_mention_id": "asset_c",
                "name_index": 1,
                "name_raw": "Planta Fotovoltaica Gamma",
            },
        ],
        (
            "event_id",
            "generation_asset_mention_id",
            "name_index",
            "name_raw",
        ),
        {
            "event_id": "string",
            "generation_asset_mention_id": "string",
            "name_index": "Int64",
            "name_raw": "string",
        },
    )
    administrative_actions = _frame(
        [
            {
                "event_id": "event_a_1",
                "identificador_boe": "BOE-A-2023-1",
                "fecha_publicacion": "2023-01-10",
                "administrative_action_id": "action_a_1",
                "action_index": 1,
                "action_type": "declaracion_impacto_ambiental",
                "decision": "favorable",
                "is_modification": False,
                "evidence": "Evidencia literal A1.",
            },
            {
                "event_id": "event_a_2",
                "identificador_boe": "BOE-A-2025-2",
                "fecha_publicacion": "2025-02-20",
                "administrative_action_id": "action_a_2",
                "action_index": 1,
                "action_type": "autorizacion_administrativa_previa",
                "decision": "autorizado",
                "is_modification": False,
                "evidence": "Evidencia literal A2.",
            },
            {
                "event_id": "event_a_2",
                "identificador_boe": "BOE-A-2025-2",
                "fecha_publicacion": "2025-02-20",
                "administrative_action_id": "action_a_3",
                "action_index": 2,
                "action_type": "autorizacion_administrativa_construccion",
                "decision": "autorizado",
                "is_modification": False,
                "evidence": "Evidencia literal A3.",
            },
            {
                "event_id": "event_multi",
                "identificador_boe": "BOE-A-2024-3",
                "fecha_publicacion": "2024-03-15",
                "administrative_action_id": "action_event",
                "action_index": 1,
                "action_type": "informacion_publica",
                "decision": "sometido_informacion_publica",
                "is_modification": False,
                "evidence": "Evidencia literal de evento.",
            },
            {
                "event_id": "event_multi",
                "identificador_boe": "BOE-A-2024-3",
                "fecha_publicacion": "2024-03-15",
                "administrative_action_id": "action_asset_b",
                "action_index": 2,
                "action_type": "autorizacion_explotacion",
                "decision": "autorizado",
                "is_modification": False,
                "evidence": "Evidencia literal de B.",
            },
            {
                "event_id": "event_multi",
                "identificador_boe": "BOE-A-2024-3",
                "fecha_publicacion": "2024-03-15",
                "administrative_action_id": "action_component_c",
                "action_index": 3,
                "action_type": "autorizacion_administrativa_construccion",
                "decision": "autorizado",
                "is_modification": True,
                "evidence": "Evidencia literal del componente C.",
            },
            {
                "event_id": "event_multi",
                "identificador_boe": "BOE-A-2024-3",
                "fecha_publicacion": "2024-03-15",
                "administrative_action_id": "action_component_unlinked",
                "action_index": 4,
                "action_type": "autorizacion_administrativa_construccion",
                "decision": "autorizado",
                "is_modification": False,
                "evidence": "Evidencia literal del componente sin vínculo.",
            },
        ],
        (
            "event_id",
            "identificador_boe",
            "fecha_publicacion",
            "administrative_action_id",
            "action_index",
            "action_type",
            "decision",
            "is_modification",
            "evidence",
        ),
        {
            "event_id": "string",
            "identificador_boe": "string",
            "fecha_publicacion": "datetime64[ns]",
            "administrative_action_id": "string",
            "action_index": "Int64",
            "action_type": "string",
            "decision": "string",
            "is_modification": "boolean",
            "evidence": "string",
        },
    )
    administrative_action_targets = _frame(
        [
            {
                "event_id": "event_a_1",
                "administrative_action_id": "action_a_1",
                "target_index": 1,
                "target_entity_id": "event_a_1",
                "target_kind": "event",
            },
            {
                "event_id": "event_a_2",
                "administrative_action_id": "action_a_2",
                "target_index": 1,
                "target_entity_id": "asset_a_2",
                "target_kind": "generation_asset",
            },
            {
                "event_id": "event_a_2",
                "administrative_action_id": "action_a_3",
                "target_index": 1,
                "target_entity_id": "asset_a_2",
                "target_kind": "generation_asset",
            },
            {
                "event_id": "event_multi",
                "administrative_action_id": "action_event",
                "target_index": 1,
                "target_entity_id": "event_multi",
                "target_kind": "event",
            },
            {
                "event_id": "event_multi",
                "administrative_action_id": "action_asset_b",
                "target_index": 1,
                "target_entity_id": "asset_b",
                "target_kind": "generation_asset",
            },
            {
                "event_id": "event_multi",
                "administrative_action_id": "action_asset_b",
                "target_index": 2,
                "target_entity_id": "asset_b",
                "target_kind": "generation_asset",
            },
            {
                "event_id": "event_multi",
                "administrative_action_id": "action_component_c",
                "target_index": 1,
                "target_entity_id": "component_c",
                "target_kind": "associated_component",
            },
            {
                "event_id": "event_multi",
                "administrative_action_id": "action_component_unlinked",
                "target_index": 1,
                "target_entity_id": "component_unlinked",
                "target_kind": "associated_component",
            },
        ],
        (
            "event_id",
            "administrative_action_id",
            "target_index",
            "target_entity_id",
            "target_kind",
        ),
        {
            "event_id": "string",
            "administrative_action_id": "string",
            "target_index": "Int64",
            "target_entity_id": "string",
            "target_kind": "string",
        },
    )
    associated_component_generation_links = _frame(
        [
            {
                "event_id": "event_multi",
                "associated_component_id": "component_c",
                "link_index": 1,
                "generation_asset_mention_id": "asset_c",
            }
        ],
        (
            "event_id",
            "associated_component_id",
            "link_index",
            "generation_asset_mention_id",
        ),
        {
            "event_id": "string",
            "associated_component_id": "string",
            "link_index": "Int64",
            "generation_asset_mention_id": "string",
        },
    )
    project_grouping = _frame(
        [
            {
                "generation_asset_mention_id": "asset_a_1",
                "project_id": "project_a",
            },
            {
                "generation_asset_mention_id": "asset_a_2",
                "project_id": "project_a",
            },
            {
                "generation_asset_mention_id": "asset_b",
                "project_id": "project_b",
            },
            {
                "generation_asset_mention_id": "asset_c",
                "project_id": "project_c",
            },
        ],
        ("generation_asset_mention_id", "project_id"),
        {
            "generation_asset_mention_id": "string",
            "project_id": "string",
        },
    )
    resolved_locations = _frame(
        [
            {
                "event_id": "event_a_1",
                "location_mention_id": "location_a_1_1",
                "ine_municipality_code": "29015",
                "municipality": "Antequera",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "29",
                "province": "Málaga",
                "province_resolution_status": "resolved",
            },
            {
                "event_id": "event_a_1",
                "location_mention_id": "location_a_1_2",
                "ine_municipality_code": "29032",
                "municipality": "Campillos",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "29",
                "province": "Málaga",
                "province_resolution_status": "resolved",
            },
            {
                "event_id": "event_a_2",
                "location_mention_id": "location_a_2_1",
                "ine_municipality_code": "29015",
                "municipality": "Antequera",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "29",
                "province": "Málaga",
                "province_resolution_status": "resolved",
            },
            {
                "event_id": "event_a_2",
                "location_mention_id": "location_a_2_2",
                "ine_municipality_code": "29032",
                "municipality": "Campillos",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "29",
                "province": "Málaga",
                "province_resolution_status": "resolved",
            },
            {
                "event_id": "event_a_2",
                "location_mention_id": "location_a_2_3",
                "ine_municipality_code": "29012",
                "municipality": "Álora",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "29",
                "province": "Málaga",
                "province_resolution_status": "resolved",
            },
            {
                "event_id": "event_multi",
                "location_mention_id": "location_multi_1",
                "ine_municipality_code": "21041",
                "municipality": "Huelva",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "21",
                "province": "Huelva",
                "province_resolution_status": "resolved",
            },
            {
                "event_id": "event_multi",
                "location_mention_id": "location_multi_2",
                "ine_municipality_code": "41091",
                "municipality": "Sevilla",
                "municipality_resolution_status": "resolved",
                "ine_province_code": "41",
                "province": "Sevilla",
                "province_resolution_status": "resolved",
            },
        ],
        (
            "event_id",
            "location_mention_id",
            "ine_municipality_code",
            "municipality",
            "municipality_resolution_status",
            "ine_province_code",
            "province",
            "province_resolution_status",
        ),
        {
            "event_id": "string",
            "location_mention_id": "string",
            "ine_municipality_code": "string",
            "municipality": "string",
            "municipality_resolution_status": "string",
            "ine_province_code": "string",
            "province": "string",
            "province_resolution_status": "string",
        },
    )
    event_metadata = publication_events.set_index("event_id")
    resolved_locations["identificador_boe"] = resolved_locations[
        "event_id"
    ].map(event_metadata["identificador_boe"]).astype("string")
    resolved_locations["fecha_publicacion"] = pd.to_datetime(
        resolved_locations["event_id"].map(
            event_metadata["fecha_publicacion"]
        )
    )
    resolved_locations["municipality_norm"] = resolved_locations[
        "municipality"
    ].str.casefold().astype("string")
    resolved_locations["province_norm"] = resolved_locations[
        "province"
    ].str.casefold().astype("string")
    resolved_locations["autonomous_community"] = pd.Series(
        ["Andalucía"] * len(resolved_locations), dtype="string"
    )
    resolved_locations["autonomous_community_norm"] = pd.Series(
        ["andalucía"] * len(resolved_locations), dtype="string"
    )
    resolved_locations["ine_autonomous_community_code"] = pd.Series(
        ["01"] * len(resolved_locations), dtype="string"
    )
    resolved_locations["autonomous_community_resolution_status"] = pd.Series(
        ["resolved"] * len(resolved_locations), dtype="string"
    )
    return {
        "publication_events": publication_events,
        "generation_asset_mentions": generation_asset_mentions,
        "generation_asset_names": generation_asset_names,
        "administrative_actions": administrative_actions,
        "administrative_action_targets": administrative_action_targets,
        "associated_component_generation_links": (
            associated_component_generation_links
        ),
        "project_grouping": project_grouping,
        "resolved_locations": resolved_locations,
    }


def test_project_events_are_the_canonical_chronology_facts() -> None:
    inputs = _gold_inputs()

    result = build_project_events(
        publication_events=inputs["publication_events"],
        generation_asset_mentions=inputs["generation_asset_mentions"],
        administrative_actions=inputs["administrative_actions"],
        administrative_action_targets=inputs["administrative_action_targets"],
        associated_component_generation_links=inputs[
            "associated_component_generation_links"
        ],
        project_grouping=inputs["project_grouping"],
    )
    timeline = result.loc[result["project_id"] == "project_a"].sort_values(
        [
            "publication_date",
            "event_index",
            "administrative_action_index",
        ]
    )

    assert timeline["administrative_action_id"].tolist() == [
        "action_a_1",
        "action_a_2",
        "action_a_3",
    ]
    assert timeline["publication_date"].tolist() == [
        pd.Timestamp("2023-01-10"),
        pd.Timestamp("2025-02-20"),
        pd.Timestamp("2025-02-20"),
    ]
    assert timeline["evidence"].tolist() == [
        "Evidencia literal A1.",
        "Evidencia literal A2.",
        "Evidencia literal A3.",
    ]


def test_action_targets_are_attributed_structurally_and_conservatively() -> None:
    inputs = _gold_inputs()
    result = build_project_events(
        publication_events=inputs["publication_events"],
        generation_asset_mentions=inputs["generation_asset_mentions"],
        administrative_actions=inputs["administrative_actions"],
        administrative_action_targets=inputs["administrative_action_targets"],
        associated_component_generation_links=inputs[
            "associated_component_generation_links"
        ],
        project_grouping=inputs["project_grouping"],
    )
    projects_by_action = (
        result.groupby("administrative_action_id")["project_id"]
        .apply(lambda values: set(values))
        .to_dict()
    )

    assert projects_by_action["action_event"] == {"project_b", "project_c"}
    assert projects_by_action["action_asset_b"] == {"project_b"}
    assert projects_by_action["action_component_c"] == {"project_c"}
    assert "action_component_unlinked" not in projects_by_action


def test_component_linked_to_multiple_roots_expands_to_their_projects() -> None:
    inputs = _gold_inputs()
    links = inputs["associated_component_generation_links"]
    additional_link = links.iloc[[0]].copy(deep=True)
    additional_link.loc[:, "link_index"] = 2
    additional_link.loc[:, "generation_asset_mention_id"] = "asset_b"
    inputs["associated_component_generation_links"] = pd.concat(
        [links, additional_link], ignore_index=True
    )

    result = build_project_events(
        publication_events=inputs["publication_events"],
        generation_asset_mentions=inputs["generation_asset_mentions"],
        administrative_actions=inputs["administrative_actions"],
        administrative_action_targets=inputs["administrative_action_targets"],
        associated_component_generation_links=inputs[
            "associated_component_generation_links"
        ],
        project_grouping=inputs["project_grouping"],
    )

    component_projects = set(
        result.loc[
            result["administrative_action_id"] == "action_component_c",
            "project_id",
        ]
    )
    assert component_projects == {"project_b", "project_c"}


def test_project_action_key_is_unique_after_legitimate_expansion() -> None:
    result = build_gold_tables(**_gold_inputs())["project_events"]

    assert not result.duplicated(
        ["project_id", "administrative_action_id"]
    ).any()
    assert len(result) == 7


def test_additive_location_build_preserves_existing_gold_tables() -> None:
    inputs = _gold_inputs()
    expected_events = build_project_events(
        publication_events=inputs["publication_events"],
        generation_asset_mentions=inputs["generation_asset_mentions"],
        administrative_actions=inputs["administrative_actions"],
        administrative_action_targets=inputs["administrative_action_targets"],
        associated_component_generation_links=inputs[
            "associated_component_generation_links"
        ],
        project_grouping=inputs["project_grouping"],
    )
    expected_projects = build_projects(
        publication_events=inputs["publication_events"],
        generation_asset_mentions=inputs["generation_asset_mentions"],
        generation_asset_names=inputs["generation_asset_names"],
        resolved_locations=inputs["resolved_locations"],
        project_grouping=inputs["project_grouping"],
        project_events=expected_events,
    )

    result = build_gold_tables(**inputs)

    pd.testing.assert_frame_equal(result["projects"], expected_projects)
    pd.testing.assert_frame_equal(result["project_events"], expected_events)


def test_projects_are_a_compact_catalog_with_separate_counts() -> None:
    outputs = build_gold_tables(**_gold_inputs())
    projects = outputs["projects"].set_index("project_id")
    volateo = projects.loc["project_a"]

    assert volateo["project_name"] == "Planta Fotovoltaica Volateo Solar"
    assert volateo["technology"] == "fotovoltaica"
    assert volateo["province_codes"] == "29"
    assert volateo["provinces"] == "Málaga"
    assert volateo["municipality_codes"] == "29012 | 29015 | 29032"
    assert volateo["municipalities"] == "Álora | Antequera | Campillos"
    assert volateo["first_publication_date"] == pd.Timestamp("2023-01-10")
    assert volateo["last_publication_date"] == pd.Timestamp("2025-02-20")
    assert volateo["n_publications"] == 2
    assert volateo["n_administrative_actions"] == 3


def test_projects_preserve_every_resolved_province() -> None:
    outputs = build_gold_tables(**_gold_inputs())
    projects = outputs["projects"].set_index("project_id")

    assert projects.loc["project_b", "province_codes"] == "21 | 41"
    assert projects.loc["project_b", "provinces"] == "Huelva | Sevilla"


def test_incompatible_technologies_inside_project_are_rejected() -> None:
    inputs = _gold_inputs()
    grouping = inputs["project_grouping"].copy(deep=True)
    grouping.loc[
        grouping["generation_asset_mention_id"] == "asset_c", "project_id"
    ] = "project_b"
    project_events = build_project_events(
        publication_events=inputs["publication_events"],
        generation_asset_mentions=inputs["generation_asset_mentions"],
        administrative_actions=inputs["administrative_actions"],
        administrative_action_targets=inputs["administrative_action_targets"],
        associated_component_generation_links=inputs[
            "associated_component_generation_links"
        ],
        project_grouping=grouping,
    )

    with pytest.raises(ValueError, match="tecnologías incompatibles"):
        build_projects(
            publication_events=inputs["publication_events"],
            generation_asset_mentions=inputs["generation_asset_mentions"],
            generation_asset_names=inputs["generation_asset_names"],
            resolved_locations=inputs["resolved_locations"],
            project_grouping=grouping,
            project_events=project_events,
        )


def test_gold_is_reproducible_order_independent_and_does_not_mutate_inputs() -> None:
    inputs = _gold_inputs()
    originals = {name: frame.copy(deep=True) for name, frame in inputs.items()}
    first = build_gold_tables(**inputs)
    second = build_gold_tables(**inputs)
    shuffled = {
        name: frame.sample(frac=1, random_state=index).reset_index(drop=True)
        for index, (name, frame) in enumerate(inputs.items(), start=1)
    }
    permuted = build_gold_tables(**shuffled)

    for table_name in (
        "projects",
        "project_events",
        "project_locations",
        "project_location_sources",
    ):
        pd.testing.assert_frame_equal(first[table_name], second[table_name])
        pd.testing.assert_frame_equal(first[table_name], permuted[table_name])
    for name, original in originals.items():
        pd.testing.assert_frame_equal(inputs[name], original)


def test_typed_empty_gold_outputs_have_all_four_contract_tables() -> None:
    empty_inputs = {
        name: frame.iloc[0:0].copy()
        for name, frame in _gold_inputs().items()
    }

    outputs = build_gold_tables(**empty_inputs)

    assert set(outputs) == {
        "projects",
        "project_events",
        "project_locations",
        "project_location_sources",
    }
    assert tuple(outputs["projects"].columns) == PROJECTS_COLUMNS
    assert tuple(outputs["project_events"].columns) == PROJECT_EVENTS_COLUMNS
    assert tuple(outputs["project_locations"].columns) == PROJECT_LOCATIONS_COLUMNS
    assert tuple(outputs["project_location_sources"].columns) == (
        PROJECT_LOCATION_SOURCES_COLUMNS
    )
    assert outputs["projects"].empty
    assert outputs["project_events"].empty
    assert outputs["project_locations"].empty
    assert outputs["project_location_sources"].empty
    assert all(str(dtype) != "object" for dtype in outputs["projects"].dtypes)
    assert all(
        str(dtype) != "object" for dtype in outputs["project_events"].dtypes
    )


def test_gold_schema_does_not_persist_timeline_or_current_status() -> None:
    outputs = build_gold_tables(**_gold_inputs())
    forbidden = ("timeline", "chronology", "current_status", "legal_status")

    for frame in outputs.values():
        assert not any(
            token in column
            for column in frame.columns
            for token in forbidden
        )
