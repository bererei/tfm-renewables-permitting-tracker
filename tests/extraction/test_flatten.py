import ast
import json
from datetime import date
from pathlib import Path

import pandas as pd

from renewables_permitting.extraction.flatten import (
    FLAT_TABLE_COLUMNS,
    flatten_current_extractions,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    AdministrativeLocationLevel,
    AdministrativeLocationMention,
    AssociatedComponent,
    AssociatedComponentType,
    BOEProjectExtraction,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationAssetRelation,
    GenerationRelationType,
    GenerationType,
    ParticipantMention,
    ParticipantRole,
    PublicationEvent,
    TechnicalAttributeType,
    TechnicalMention,
)


EXPECTED_FLAT_TABLE_COLUMNS = {
    "publication_events": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "event_index",
        "event_summary",
        "n_generation_assets",
        "n_associated_components",
        "n_administrative_actions",
    ],
    "generation_asset_mentions": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_mention_id",
        "local_generation_asset_ref",
        "generation_type",
        "evidence",
    ],
    "generation_asset_names": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_mention_id",
        "name_index",
        "name_raw",
    ],
    "associated_components": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "associated_component_id",
        "local_component_ref",
        "component_type",
        "description_raw",
        "evidence",
    ],
    "associated_component_names": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "associated_component_id",
        "name_index",
        "name_raw",
    ],
    "associated_component_generation_links": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "associated_component_id",
        "link_index",
        "local_generation_asset_ref",
        "generation_asset_mention_id",
    ],
    "administrative_actions": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "administrative_action_id",
        "action_index",
        "action_type",
        "decision",
        "is_modification",
        "evidence",
    ],
    "administrative_action_targets": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "administrative_action_id",
        "target_index",
        "target_ref",
        "target_entity_id",
        "target_kind",
    ],
    "participant_mentions": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "participant_mention_id",
        "participant_name_raw",
        "participant_role",
        "evidence",
    ],
    "location_mentions": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "location_mention_id",
        "location_name_raw",
        "location_level",
        "province_hint_raw",
        "autonomous_community_hint_raw",
        "evidence",
    ],
    "generation_asset_relations": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_relation_id",
        "source_generation_asset_ref",
        "source_generation_asset_mention_id",
        "target_generation_asset_ref",
        "target_generation_asset_mention_id",
        "relation_type",
        "evidence",
    ],
    "technical_mentions": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "technical_mention_id",
        "owner_kind",
        "owner_ref",
        "generation_asset_mention_id",
        "associated_component_id",
        "attribute_type",
        "value_raw",
        "evidence",
    ],
    "case_file_references": [
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "case_file_reference_id",
        "reference_index",
        "case_file_reference_raw",
    ],
}

EXPECTED_COLUMN_COUNTS = {
    "publication_events": 8,
    "generation_asset_mentions": 7,
    "generation_asset_names": 6,
    "associated_components": 8,
    "associated_component_names": 6,
    "associated_component_generation_links": 7,
    "administrative_actions": 9,
    "administrative_action_targets": 8,
    "participant_mentions": 7,
    "location_mentions": 9,
    "generation_asset_relations": 10,
    "technical_mentions": 11,
    "case_file_references": 6,
}

EXPECTED_ROW_COUNTS = {
    "publication_events": 2,
    "generation_asset_mentions": 3,
    "generation_asset_names": 4,
    "associated_components": 2,
    "associated_component_names": 2,
    "associated_component_generation_links": 3,
    "administrative_actions": 3,
    "administrative_action_targets": 4,
    "participant_mentions": 1,
    "location_mentions": 1,
    "generation_asset_relations": 1,
    "technical_mentions": 4,
    "case_file_references": 3,
}


def _relevant_extraction() -> BOEProjectExtraction:
    first_event = PublicationEvent(
        generation_assets=[
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Solar Alfa", "PSFV Alfa"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                        value_raw="50 MW",
                        evidence="potencia instalada de 50 MW",
                    )
                ],
                evidence="planta solar fotovoltaica Solar Alfa",
            ),
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_2",
                names_raw=["Parque Eólico Beta"],
                generation_type=GenerationType.WIND,
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.UNIT_COUNT,
                        value_raw="5 aerogeneradores",
                        evidence="compuesto por 5 aerogeneradores",
                    )
                ],
                evidence="parque eólico Parque Eólico Beta",
            ),
        ],
        associated_components=[
            AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.ENERGY_STORAGE,
                names_raw=["BESS Alfa", "Sistema Alfa"],
                description_raw=None,
                related_generation_asset_refs=[
                    "generation_asset_1",
                    "generation_asset_2",
                ],
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.STORAGE_CAPACITY,
                        value_raw="100 MWh",
                        evidence="capacidad de almacenamiento de 100 MWh",
                    )
                ],
                evidence="sistema de almacenamiento BESS Alfa",
            ),
            AssociatedComponent(
                local_component_ref="component_2",
                component_type=AssociatedComponentType.POWER_LINE,
                names_raw=[],
                description_raw="línea eléctrica de evacuación a 220 kV",
                related_generation_asset_refs=["generation_asset_1"],
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.VOLTAGE,
                        value_raw="220 kV",
                        evidence="línea eléctrica de evacuación a 220 kV",
                    )
                ],
                evidence="línea eléctrica de evacuación a 220 kV",
            ),
        ],
        administrative_actions=[
            AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                is_modification=False,
                targets=["event"],
                evidence="se otorga autorización administrativa previa",
            ),
            AdministrativeAction(
                action_type=AdministrativeActionType.PUBLIC_INFORMATION,
                decision=(
                    AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
                ),
                is_modification=False,
                targets=["generation_asset_1", "component_1"],
                evidence="se somete a información pública",
            ),
        ],
        participants=[
            ParticipantMention(
                participant_name_raw="Renovables Ejemplo, S.L.",
                participant_role=ParticipantRole.PROMOTER,
                evidence="promovido por Renovables Ejemplo, S.L.",
            )
        ],
        administrative_locations=[
            AdministrativeLocationMention(
                location_name_raw="Villanueva",
                location_level=AdministrativeLocationLevel.MUNICIPALITY,
                province_hint_raw="Toledo",
                autonomous_community_hint_raw=None,
                evidence="término municipal de Villanueva, Toledo",
            )
        ],
        generation_relations=[
            GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_2",
                relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                evidence="Solar Alfa se hibrida con Parque Eólico Beta",
            )
        ],
        case_file_references=["PFot-100", "PEol-200"],
        event_summary="Autorización e información pública del proyecto híbrido.",
    )
    second_event = PublicationEvent(
        generation_assets=[
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Central Gamma"],
                generation_type=GenerationType.HYDROPOWER,
                technical_mentions=[],
                evidence="central hidroeléctrica Central Gamma",
            )
        ],
        associated_components=[],
        administrative_actions=[
            AdministrativeAction(
                action_type=AdministrativeActionType.WATER_CONCESSION,
                decision=AdministrativeDecision.REQUESTED,
                is_modification=False,
                targets=["generation_asset_1"],
                evidence="solicitud de concesión de aguas",
            )
        ],
        participants=[],
        administrative_locations=[],
        generation_relations=[],
        case_file_references=["H-300"],
        event_summary="Solicitud de concesión para Central Gamma.",
    )
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de proyectos.",
        publication_events=[first_event, second_event],
        extraction_notes=None,
        boe_id="BOE-A-2024-9608",
        publication_date=date(2024, 5, 13),
    )


def _non_relevant_extraction() -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS,
        classification_reason="Publicación no relevante.",
        publication_events=[],
        extraction_notes=None,
        boe_id="BOE-B-2025-1",
        publication_date=date(2025, 1, 2),
    )


def _current_extractions() -> tuple[
    pd.DataFrame,
    BOEProjectExtraction,
    BOEProjectExtraction,
]:
    relevant = _relevant_extraction()
    non_relevant = _non_relevant_extraction()
    dataframe = pd.DataFrame(
        [
            {
                "extraction_json": relevant.model_dump_json(),
                "sentinel": "relevant",
            },
            {
                "extraction_json": non_relevant.model_dump_json(),
                "sentinel": "non_relevant",
            },
        ]
    )
    return dataframe, relevant, non_relevant


def _node_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def test_flatten_nodes_match_notebook_ast() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb").read_text()
    )
    notebook_tree = ast.parse("".join(notebook["cells"][17]["source"]))
    module_tree = ast.parse(
        (
            project_root
            / "src"
            / "renewables_permitting"
            / "extraction"
            / "flatten.py"
        ).read_text()
    )
    expected_symbols = {"FLAT_TABLE_COLUMNS", "flatten_current_extractions"}
    notebook_nodes = [
        node
        for node in notebook_tree.body
        if _node_name(node) in expected_symbols
    ]
    module_nodes = [
        node
        for node in module_tree.body
        if _node_name(node) is not None
    ]

    assert [_node_name(node) for node in module_nodes] == [
        _node_name(node) for node in notebook_nodes
    ]
    assert {_node_name(node) for node in module_nodes} == expected_symbols

    notebook_by_name = {_node_name(node): node for node in notebook_nodes}
    module_by_name = {_node_name(node): node for node in module_nodes}
    for name in expected_symbols:
        assert ast.dump(
            module_by_name[name],
            include_attributes=False,
        ) == ast.dump(
            notebook_by_name[name],
            include_attributes=False,
        )


def test_flat_table_names_columns_and_column_counts_are_exact() -> None:
    dataframe, _, _ = _current_extractions()
    tables = flatten_current_extractions(dataframe)

    assert FLAT_TABLE_COLUMNS == EXPECTED_FLAT_TABLE_COLUMNS
    assert list(tables) == list(EXPECTED_FLAT_TABLE_COLUMNS)
    assert {
        name: len(columns)
        for name, columns in FLAT_TABLE_COLUMNS.items()
    } == EXPECTED_COLUMN_COUNTS
    for name, expected_columns in EXPECTED_FLAT_TABLE_COLUMNS.items():
        assert tables[name].columns.tolist() == expected_columns


def test_flat_table_row_counts_are_exact() -> None:
    dataframe, _, _ = _current_extractions()
    tables = flatten_current_extractions(dataframe)

    assert {name: len(table) for name, table in tables.items()} == (
        EXPECTED_ROW_COUNTS
    )


def test_flattened_identifiers_indices_values_and_nulls_are_exact() -> None:
    dataframe, _, _ = _current_extractions()
    tables = flatten_current_extractions(dataframe)
    event_1 = "BOE-A-2024-9608_event_1"
    event_2 = "BOE-A-2024-9608_event_2"
    publication_date = pd.Timestamp(date(2024, 5, 13))

    assert tables["publication_events"]["event_id"].tolist() == [
        event_1,
        event_2,
    ]
    assert tables["publication_events"]["event_index"].tolist() == [1, 2]
    assert tables["publication_events"]["identificador_boe"].tolist() == [
        "BOE-A-2024-9608",
        "BOE-A-2024-9608",
    ]
    assert tables["publication_events"]["fecha_publicacion"].tolist() == [
        publication_date,
        publication_date,
    ]
    assert tables["publication_events"][
        [
            "n_generation_assets",
            "n_associated_components",
            "n_administrative_actions",
        ]
    ].values.tolist() == [[2, 2, 2], [1, 0, 1]]

    asset_mentions = tables["generation_asset_mentions"]
    assert asset_mentions["generation_asset_mention_id"].tolist() == [
        f"{event_1}_generation_asset_1",
        f"{event_1}_generation_asset_2",
        f"{event_2}_generation_asset_1",
    ]
    assert asset_mentions["local_generation_asset_ref"].tolist() == [
        "generation_asset_1",
        "generation_asset_2",
        "generation_asset_1",
    ]
    assert asset_mentions["generation_type"].tolist() == [
        GenerationType.PHOTOVOLTAIC.value,
        GenerationType.WIND.value,
        GenerationType.HYDROPOWER.value,
    ]
    assert asset_mentions["evidence"].tolist()[0] == (
        "planta solar fotovoltaica Solar Alfa"
    )

    names = tables["generation_asset_names"]
    assert names["name_index"].tolist() == [1, 2, 1, 1]
    assert names["name_raw"].tolist() == [
        "Solar Alfa",
        "PSFV Alfa",
        "Parque Eólico Beta",
        "Central Gamma",
    ]
    assert names["generation_asset_mention_id"].tolist()[:2] == [
        f"{event_1}_generation_asset_1",
        f"{event_1}_generation_asset_1",
    ]

    components = tables["associated_components"]
    assert components["associated_component_id"].tolist() == [
        f"{event_1}_component_1",
        f"{event_1}_component_2",
    ]
    assert components["component_type"].tolist() == [
        AssociatedComponentType.ENERGY_STORAGE.value,
        AssociatedComponentType.POWER_LINE.value,
    ]
    assert components.iloc[0]["description_raw"] is None
    assert components.iloc[1]["description_raw"] == (
        "línea eléctrica de evacuación a 220 kV"
    )

    component_names = tables["associated_component_names"]
    assert component_names["name_index"].tolist() == [1, 2]
    assert component_names["name_raw"].tolist() == [
        "BESS Alfa",
        "Sistema Alfa",
    ]

    links = tables["associated_component_generation_links"]
    assert links["link_index"].tolist() == [1, 2, 1]
    assert links["local_generation_asset_ref"].tolist() == [
        "generation_asset_1",
        "generation_asset_2",
        "generation_asset_1",
    ]
    assert links["generation_asset_mention_id"].tolist() == [
        f"{event_1}_generation_asset_1",
        f"{event_1}_generation_asset_2",
        f"{event_1}_generation_asset_1",
    ]

    actions = tables["administrative_actions"]
    assert actions["administrative_action_id"].tolist() == [
        f"{event_1}_action_1",
        f"{event_1}_action_2",
        f"{event_2}_action_1",
    ]
    assert actions["action_index"].tolist() == [1, 2, 1]
    assert actions["action_type"].tolist() == [
        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION.value,
        AdministrativeActionType.PUBLIC_INFORMATION.value,
        AdministrativeActionType.WATER_CONCESSION.value,
    ]
    assert actions["decision"].tolist() == [
        AdministrativeDecision.AUTHORIZED.value,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION.value,
        AdministrativeDecision.REQUESTED.value,
    ]
    assert actions["is_modification"].tolist() == [False, False, False]

    targets = tables["administrative_action_targets"]
    assert targets["target_index"].tolist() == [1, 1, 2, 1]
    assert targets["target_ref"].tolist() == [
        "event",
        "generation_asset_1",
        "component_1",
        "generation_asset_1",
    ]
    assert targets["target_entity_id"].tolist() == [
        event_1,
        f"{event_1}_generation_asset_1",
        f"{event_1}_component_1",
        f"{event_2}_generation_asset_1",
    ]
    assert targets["target_kind"].tolist() == [
        "event",
        "generation_asset",
        "associated_component",
        "generation_asset",
    ]

    participants = tables["participant_mentions"]
    assert participants.iloc[0]["participant_mention_id"] == (
        f"{event_1}_participant_1"
    )
    assert participants.iloc[0]["participant_role"] == ParticipantRole.PROMOTER.value

    locations = tables["location_mentions"]
    assert locations.iloc[0]["location_mention_id"] == (
        f"{event_1}_location_1"
    )
    assert locations.iloc[0]["location_level"] == (
        AdministrativeLocationLevel.MUNICIPALITY.value
    )
    assert locations.iloc[0]["province_hint_raw"] == "Toledo"
    assert locations.iloc[0]["autonomous_community_hint_raw"] is None

    relations = tables["generation_asset_relations"]
    assert relations.iloc[0]["generation_asset_relation_id"] == (
        f"{event_1}_relation_1"
    )
    assert relations.iloc[0]["source_generation_asset_mention_id"] == (
        f"{event_1}_generation_asset_1"
    )
    assert relations.iloc[0]["target_generation_asset_mention_id"] == (
        f"{event_1}_generation_asset_2"
    )
    assert relations.iloc[0]["relation_type"] == (
        GenerationRelationType.HYBRIDIZED_WITH.value
    )

    technical = tables["technical_mentions"]
    assert technical["technical_mention_id"].tolist() == [
        f"{event_1}_generation_asset_1_technical_1",
        f"{event_1}_generation_asset_2_technical_1",
        f"{event_1}_component_1_technical_1",
        f"{event_1}_component_2_technical_1",
    ]
    assert technical["owner_kind"].tolist() == [
        "generation_asset",
        "generation_asset",
        "associated_component",
        "associated_component",
    ]
    assert technical["attribute_type"].tolist() == [
        TechnicalAttributeType.INSTALLED_POWER.value,
        TechnicalAttributeType.UNIT_COUNT.value,
        TechnicalAttributeType.STORAGE_CAPACITY.value,
        TechnicalAttributeType.VOLTAGE.value,
    ]
    assert technical.iloc[0]["associated_component_id"] is None
    assert technical.iloc[2]["generation_asset_mention_id"] is None

    references = tables["case_file_references"]
    assert references["case_file_reference_id"].tolist() == [
        f"{event_1}_case_file_1",
        f"{event_1}_case_file_2",
        f"{event_2}_case_file_1",
    ]
    assert references["reference_index"].tolist() == [1, 2, 1]
    assert references["case_file_reference_raw"].tolist() == [
        "PFot-100",
        "PEol-200",
        "H-300",
    ]


def test_flattened_row_order_is_deterministic() -> None:
    dataframe, _, _ = _current_extractions()

    first = flatten_current_extractions(dataframe)
    second = flatten_current_extractions(dataframe)

    for name in EXPECTED_FLAT_TABLE_COLUMNS:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_non_relevant_extraction_produces_empty_tables_with_schema() -> None:
    extraction = _non_relevant_extraction()
    dataframe = pd.DataFrame(
        [{"extraction_json": extraction.model_dump_json()}]
    )

    tables = flatten_current_extractions(dataframe)

    assert list(tables) == list(EXPECTED_FLAT_TABLE_COLUMNS)
    for name, table in tables.items():
        assert table.empty
        assert table.columns.tolist() == EXPECTED_FLAT_TABLE_COLUMNS[name]


def test_empty_input_produces_empty_tables_with_schema() -> None:
    tables = flatten_current_extractions(pd.DataFrame())

    assert list(tables) == list(EXPECTED_FLAT_TABLE_COLUMNS)
    for name, table in tables.items():
        assert table.empty
        assert table.columns.tolist() == EXPECTED_FLAT_TABLE_COLUMNS[name]


def test_flatten_does_not_modify_dataframe_or_extraction_objects() -> None:
    dataframe, relevant, non_relevant = _current_extractions()
    dataframe_before = dataframe.copy(deep=True)
    relevant_json_before = relevant.model_dump_json()
    non_relevant_json_before = non_relevant.model_dump_json()

    flatten_current_extractions(dataframe)

    pd.testing.assert_frame_equal(dataframe, dataframe_before)
    assert relevant.model_dump_json() == relevant_json_before
    assert non_relevant.model_dump_json() == non_relevant_json_before
