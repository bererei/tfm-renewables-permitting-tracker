from datetime import date

import pandas as pd
import pytest

from renewables_permitting.extraction.flat_contract import (
    FLAT_TABLE_COLUMNS,
    apply_flat_table_types,
)
from renewables_permitting.extraction.flat_validation import (
    FlatTableValidationError,
    validate_flat_tables,
)
from renewables_permitting.extraction.flatten import flatten_current_extractions
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    BOEProjectExtraction,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationType,
    PublicationEvent,
)


BOE_ID = "BOE-A-2026-10001"
PUBLICATION_DATE = pd.Timestamp("2026-01-02")
EVENT_1 = f"{BOE_ID}_event_1"
EVENT_2 = f"{BOE_ID}_event_2"
ASSET_1 = f"{EVENT_1}_generation_asset_1"
ASSET_2 = f"{EVENT_1}_generation_asset_2"
ASSET_3 = f"{EVENT_2}_generation_asset_1"
COMPONENT_1 = f"{EVENT_1}_component_1"
COMPONENT_2 = f"{EVENT_2}_component_1"
ACTION_1 = f"{EVENT_1}_action_1"
ACTION_2 = f"{EVENT_1}_action_2"
ACTION_3 = f"{EVENT_2}_action_1"


def _base(event_id: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "identificador_boe": BOE_ID,
        "fecha_publicacion": PUBLICATION_DATE,
    }


def _valid_tables() -> dict[str, pd.DataFrame]:
    records: dict[str, list[dict[str, object]]] = {
        "publication_events": [
            {
                **_base(EVENT_1),
                "event_index": 1,
                "event_summary": "Primer evento",
                "n_generation_assets": 2,
                "n_associated_components": 1,
                "n_administrative_actions": 2,
            },
            {
                **_base(EVENT_2),
                "event_index": 2,
                "event_summary": "Segundo evento",
                "n_generation_assets": 1,
                "n_associated_components": 1,
                "n_administrative_actions": 1,
            },
        ],
        "generation_asset_mentions": [
            {
                **_base(EVENT_1),
                "generation_asset_mention_id": ASSET_1,
                "local_generation_asset_ref": "generation_asset_1",
                "generation_type": "fotovoltaica",
                "evidence": "Planta Solar Uno",
            },
            {
                **_base(EVENT_1),
                "generation_asset_mention_id": ASSET_2,
                "local_generation_asset_ref": "generation_asset_2",
                "generation_type": "eolica",
                "evidence": "Parque Eólico Dos",
            },
            {
                **_base(EVENT_2),
                "generation_asset_mention_id": ASSET_3,
                "local_generation_asset_ref": "generation_asset_1",
                "generation_type": "hidroelectrica",
                "evidence": "Central Hidráulica Tres",
            },
        ],
        "generation_asset_names": [
            {
                **_base(EVENT_1),
                "generation_asset_mention_id": ASSET_1,
                "name_index": 1,
                "name_raw": "Solar Uno",
            },
            {
                **_base(EVENT_1),
                "generation_asset_mention_id": ASSET_1,
                "name_index": 2,
                "name_raw": "PSFV Uno",
            },
            {
                **_base(EVENT_1),
                "generation_asset_mention_id": ASSET_2,
                "name_index": 1,
                "name_raw": "Eólica Dos",
            },
            {
                **_base(EVENT_2),
                "generation_asset_mention_id": ASSET_3,
                "name_index": 1,
                "name_raw": "Hidráulica Tres",
            },
        ],
        "associated_components": [
            {
                **_base(EVENT_1),
                "associated_component_id": COMPONENT_1,
                "local_component_ref": "component_1",
                "component_type": "almacenamiento",
                "description_raw": None,
                "evidence": "Sistema de almacenamiento",
            },
            {
                **_base(EVENT_2),
                "associated_component_id": COMPONENT_2,
                "local_component_ref": "component_1",
                "component_type": "linea_electrica",
                "description_raw": "Línea de evacuación",
                "evidence": "Línea eléctrica de evacuación",
            },
        ],
        "associated_component_names": [
            {
                **_base(EVENT_1),
                "associated_component_id": COMPONENT_1,
                "name_index": 1,
                "name_raw": "BESS Uno",
            },
        ],
        "associated_component_generation_links": [
            {
                **_base(EVENT_1),
                "associated_component_id": COMPONENT_1,
                "link_index": 1,
                "local_generation_asset_ref": "generation_asset_1",
                "generation_asset_mention_id": ASSET_1,
            },
            {
                **_base(EVENT_1),
                "associated_component_id": COMPONENT_1,
                "link_index": 2,
                "local_generation_asset_ref": "generation_asset_2",
                "generation_asset_mention_id": ASSET_2,
            },
            {
                **_base(EVENT_2),
                "associated_component_id": COMPONENT_2,
                "link_index": 1,
                "local_generation_asset_ref": "generation_asset_1",
                "generation_asset_mention_id": ASSET_3,
            },
        ],
        "administrative_actions": [
            {
                **_base(EVENT_1),
                "administrative_action_id": ACTION_1,
                "action_index": 1,
                "action_type": "autorizacion_administrativa_previa",
                "decision": "autorizado",
                "is_modification": False,
                "evidence": "Se autoriza",
            },
            {
                **_base(EVENT_1),
                "administrative_action_id": ACTION_2,
                "action_index": 2,
                "action_type": "informacion_publica",
                "decision": "sometido_informacion_publica",
                "is_modification": False,
                "evidence": "Se somete a información pública",
            },
            {
                **_base(EVENT_2),
                "administrative_action_id": ACTION_3,
                "action_index": 1,
                "action_type": "concesion_aguas",
                "decision": "solicitado",
                "is_modification": False,
                "evidence": "Se solicita concesión",
            },
        ],
        "administrative_action_targets": [
            {
                **_base(EVENT_1),
                "administrative_action_id": ACTION_1,
                "target_index": 1,
                "target_ref": "event",
                "target_entity_id": EVENT_1,
                "target_kind": "event",
            },
            {
                **_base(EVENT_1),
                "administrative_action_id": ACTION_2,
                "target_index": 1,
                "target_ref": "generation_asset_1",
                "target_entity_id": ASSET_1,
                "target_kind": "generation_asset",
            },
            {
                **_base(EVENT_1),
                "administrative_action_id": ACTION_2,
                "target_index": 2,
                "target_ref": "component_1",
                "target_entity_id": COMPONENT_1,
                "target_kind": "associated_component",
            },
            {
                **_base(EVENT_2),
                "administrative_action_id": ACTION_3,
                "target_index": 1,
                "target_ref": "generation_asset_1",
                "target_entity_id": ASSET_3,
                "target_kind": "generation_asset",
            },
        ],
        "participant_mentions": [
            {
                **_base(EVENT_1),
                "participant_mention_id": f"{EVENT_1}_participant_1",
                "participant_name_raw": "Promotor Uno, SL",
                "participant_role": "promotor",
                "evidence": "Promovido por Promotor Uno, SL",
            },
            {
                **_base(EVENT_2),
                "participant_mention_id": f"{EVENT_2}_participant_1",
                "participant_name_raw": "Titular Dos, SL",
                "participant_role": "titular",
                "evidence": "Titular Dos, SL",
            },
        ],
        "location_mentions": [
            {
                **_base(EVENT_1),
                "location_mention_id": f"{EVENT_1}_location_1",
                "location_name_raw": "Villa Uno",
                "location_level": "municipio",
                "province_hint_raw": "Provincia Uno",
                "autonomous_community_hint_raw": None,
                "evidence": "En Villa Uno",
            },
        ],
        "generation_asset_relations": [
            {
                **_base(EVENT_1),
                "generation_asset_relation_id": f"{EVENT_1}_relation_1",
                "source_generation_asset_ref": "generation_asset_1",
                "source_generation_asset_mention_id": ASSET_1,
                "target_generation_asset_ref": "generation_asset_2",
                "target_generation_asset_mention_id": ASSET_2,
                "relation_type": "hibrida_con",
                "evidence": "Solar Uno se hibrida con Eólica Dos",
            },
        ],
        "technical_mentions": [
            {
                **_base(EVENT_1),
                "technical_mention_id": f"{ASSET_1}_technical_1",
                "owner_kind": "generation_asset",
                "owner_ref": "generation_asset_1",
                "generation_asset_mention_id": ASSET_1,
                "associated_component_id": None,
                "attribute_type": "potencia_instalada",
                "value_raw": "50 MW",
                "evidence": "Potencia instalada de 50 MW",
            },
            {
                **_base(EVENT_1),
                "technical_mention_id": f"{ASSET_1}_technical_2",
                "owner_kind": "generation_asset",
                "owner_ref": "generation_asset_1",
                "generation_asset_mention_id": ASSET_1,
                "associated_component_id": None,
                "attribute_type": "potencia_pico",
                "value_raw": "55 MWp",
                "evidence": "Potencia pico de 55 MWp",
            },
            {
                **_base(EVENT_1),
                "technical_mention_id": f"{COMPONENT_1}_technical_1",
                "owner_kind": "associated_component",
                "owner_ref": "component_1",
                "generation_asset_mention_id": None,
                "associated_component_id": COMPONENT_1,
                "attribute_type": "capacidad_almacenamiento",
                "value_raw": "100 MWh",
                "evidence": "Capacidad de 100 MWh",
            },
            {
                **_base(EVENT_2),
                "technical_mention_id": f"{COMPONENT_2}_technical_1",
                "owner_kind": "associated_component",
                "owner_ref": "component_1",
                "generation_asset_mention_id": None,
                "associated_component_id": COMPONENT_2,
                "attribute_type": "tension",
                "value_raw": "220 kV",
                "evidence": "Tensión de 220 kV",
            },
        ],
        "case_file_references": [
            {
                **_base(EVENT_1),
                "case_file_reference_id": f"{EVENT_1}_case_file_1",
                "reference_index": 1,
                "case_file_reference_raw": "PFot-1",
            },
            {
                **_base(EVENT_1),
                "case_file_reference_id": f"{EVENT_1}_case_file_2",
                "reference_index": 2,
                "case_file_reference_raw": "PEol-2",
            },
            {
                **_base(EVENT_2),
                "case_file_reference_id": f"{EVENT_2}_case_file_1",
                "reference_index": 1,
                "case_file_reference_raw": "H-3",
            },
        ],
    }
    return apply_flat_table_types({
        table_name: pd.DataFrame(
            records[table_name],
            columns=columns,
        )
        for table_name, columns in FLAT_TABLE_COLUMNS.items()
    })


def _empty_tables() -> dict[str, pd.DataFrame]:
    return apply_flat_table_types({
        table_name: pd.DataFrame(columns=columns)
        for table_name, columns in FLAT_TABLE_COLUMNS.items()
    })


def _copy_tables(
    tables: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    return {
        name: dataframe.copy(deep=True)
        for name, dataframe in tables.items()
    }


def _assert_invalid(
    tables: dict[str, pd.DataFrame],
    *,
    table: str,
    rule: str,
) -> FlatTableValidationError:
    with pytest.raises(FlatTableValidationError) as exc_info:
        validate_flat_tables(tables)
    assert any(
        issue.table == table and rule in issue.rule
        for issue in exc_info.value.issues
    ), str(exc_info.value)
    assert table in str(exc_info.value)
    return exc_info.value


def _minimal_current_extractions() -> pd.DataFrame:
    evidence = "Se autoriza la planta Solar Mínima"
    extraction = BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica",
        publication_events=[PublicationEvent(
            generation_assets=[GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Solar Mínima"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[],
                evidence=evidence,
            )],
            associated_components=[],
            administrative_actions=[AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                targets=[],
                evidence=evidence,
            )],
            participants=[],
            administrative_locations=[],
            generation_relations=[],
            case_file_references=[],
            event_summary="Autorización de Solar Mínima",
        )],
        boe_id="BOE-A-2026-20002",
        publication_date=date(2026, 2, 3),
    )
    return pd.DataFrame([{
        "extraction_json": extraction.model_dump_json(),
    }])


def test_valid_rich_tables_pass_validation() -> None:
    assert validate_flat_tables(_valid_tables()) is None


def test_all_thirteen_empty_typed_tables_are_valid() -> None:
    assert validate_flat_tables(_empty_tables()) is None


def test_rejects_missing_and_unexpected_tables() -> None:
    tables = _empty_tables()
    tables.pop("technical_mentions")
    tables["unexpected_table"] = pd.DataFrame()

    error = _assert_invalid(
        tables,
        table="technical_mentions",
        rule="missing_table",
    )

    assert any(
        issue.table == "unexpected_table"
        and issue.rule == "unexpected_table"
        for issue in error.issues
    )


def test_rejects_non_dataframe_table() -> None:
    tables: dict[str, object] = dict(_empty_tables())
    tables["technical_mentions"] = []

    with pytest.raises(FlatTableValidationError) as exc_info:
        validate_flat_tables(tables)  # type: ignore[arg-type]

    assert any(
        issue.table == "technical_mentions"
        and issue.rule == "not_a_dataframe"
        for issue in exc_info.value.issues
    )


def test_rejects_duplicate_columns() -> None:
    tables = _empty_tables()
    events = tables["publication_events"]
    tables["publication_events"] = pd.concat(
        [events, events.loc[:, ["event_id"]]],
        axis=1,
    )

    _assert_invalid(
        tables,
        table="publication_events",
        rule="duplicate_columns",
    )


def test_rejects_columns_out_of_contractual_order() -> None:
    tables = _empty_tables()
    events = tables["publication_events"]
    tables["publication_events"] = events.loc[
        :, list(reversed(events.columns))
    ]

    _assert_invalid(
        tables,
        table="publication_events",
        rule="column_contract",
    )


def test_rejects_incorrect_column_dtype() -> None:
    tables = _empty_tables()
    tables["publication_events"]["event_index"] = tables[
        "publication_events"
    ]["event_index"].astype("string")

    _assert_invalid(
        tables,
        table="publication_events",
        rule="column_dtype",
    )


def test_legitimate_mix_of_empty_and_populated_tables_is_valid() -> None:
    tables = flatten_current_extractions(_minimal_current_extractions())

    assert tables["publication_events"].shape[0] == 1
    assert tables["associated_components"].empty
    assert tables["technical_mentions"].empty
    assert validate_flat_tables(tables) is None


def test_validation_does_not_modify_dataframes() -> None:
    tables = _valid_tables()
    snapshots = _copy_tables(tables)

    validate_flat_tables(tables)

    for name, dataframe in tables.items():
        pd.testing.assert_frame_equal(dataframe, snapshots[name])


def test_flatten_returns_tables_that_pass_validation() -> None:
    tables = flatten_current_extractions(_minimal_current_extractions())

    assert validate_flat_tables(tables) is None


@pytest.mark.parametrize(
    ("mutation", "table", "rule"),
    [
        (
            lambda tables: tables["publication_events"].__setitem__(
                "event_summary",
                pd.Series([pd.NA, "Segundo evento"], dtype="string"),
            ),
            "publication_events",
            "non_nullable",
        ),
        (
            lambda tables: tables["publication_events"].__setitem__(
                "event_summary",
                pd.Series(["   ", "Segundo evento"], dtype="string"),
            ),
            "publication_events",
            "required_string_blank",
        ),
    ],
)
def test_rejects_invalid_required_values(
    mutation: object,
    table: str,
    rule: str,
) -> None:
    tables = _valid_tables()
    mutation(tables)  # type: ignore[operator]

    _assert_invalid(tables, table=table, rule=rule)


def test_rejects_duplicate_simple_primary_key() -> None:
    tables = _valid_tables()
    tables["publication_events"] = pd.concat([
        tables["publication_events"],
        tables["publication_events"].iloc[[0]],
    ], ignore_index=True)

    _assert_invalid(
        tables,
        table="publication_events",
        rule="primary_key_duplicate",
    )


def test_rejects_duplicate_composite_primary_key() -> None:
    tables = _valid_tables()
    tables["generation_asset_names"] = pd.concat([
        tables["generation_asset_names"],
        tables["generation_asset_names"].iloc[[0]],
    ], ignore_index=True)

    _assert_invalid(
        tables,
        table="generation_asset_names",
        rule="primary_key_duplicate",
    )


def test_rejects_null_primary_key() -> None:
    tables = _valid_tables()
    tables["participant_mentions"].loc[0, "participant_mention_id"] = pd.NA

    _assert_invalid(
        tables,
        table="participant_mentions",
        rule="primary_key_null",
    )


@pytest.mark.parametrize(
    ("table_name", "column_name", "value", "rule"),
    [
        ("participant_mentions", "event_id", "missing_event", "event_foreign_key"),
        (
            "participant_mentions",
            "identificador_boe",
            "BOE-A-2026-999",
            "event_boe_context",
        ),
        (
            "participant_mentions",
            "fecha_publicacion",
            pd.Timestamp("2026-01-03"),
            "event_date_context",
        ),
        (
            "generation_asset_names",
            "generation_asset_mention_id",
            "missing_asset",
            "foreign_key:generation_asset_mentions",
        ),
        (
            "associated_component_names",
            "associated_component_id",
            "missing_component",
            "foreign_key:associated_components",
        ),
        (
            "associated_component_generation_links",
            "generation_asset_mention_id",
            "missing_asset",
            "foreign_key:generation_asset_mentions",
        ),
        (
            "generation_asset_relations",
            "source_generation_asset_mention_id",
            "missing_asset",
            "foreign_key:generation_asset_mentions",
        ),
        (
            "generation_asset_relations",
            "target_generation_asset_mention_id",
            "missing_asset",
            "foreign_key:generation_asset_mentions",
        ),
    ],
)
def test_rejects_event_and_direct_foreign_key_errors(
    table_name: str,
    column_name: str,
    value: object,
    rule: str,
) -> None:
    tables = _valid_tables()
    tables[table_name].loc[0, column_name] = value

    _assert_invalid(tables, table=table_name, rule=rule)


def test_rejects_parent_entity_from_another_event() -> None:
    tables = _valid_tables()
    tables["generation_asset_names"].loc[0, "event_id"] = EVENT_2

    _assert_invalid(
        tables,
        table="generation_asset_names",
        rule="foreign_key_event:generation_asset_mentions",
    )


@pytest.mark.parametrize(
    ("count_column", "rule_table"),
    [
        ("n_generation_assets", "generation_asset_mentions"),
        ("n_associated_components", "associated_components"),
        ("n_administrative_actions", "administrative_actions"),
    ],
)
def test_rejects_incorrect_event_counts(
    count_column: str,
    rule_table: str,
) -> None:
    tables = _valid_tables()
    tables["publication_events"].loc[0, count_column] += 1

    _assert_invalid(
        tables,
        table="publication_events",
        rule=f"count_matches:{rule_table}",
    )


def test_rejects_event_without_generation_assets() -> None:
    tables = flatten_current_extractions(_minimal_current_extractions())
    tables["generation_asset_mentions"] = tables[
        "generation_asset_mentions"
    ].iloc[0:0].copy()
    tables["generation_asset_names"] = tables[
        "generation_asset_names"
    ].iloc[0:0].copy()
    tables["publication_events"].loc[0, "n_generation_assets"] = 0

    _assert_invalid(
        tables,
        table="publication_events",
        rule="minimum_cardinality:generation_asset_mentions",
    )


def test_rejects_event_without_administrative_actions() -> None:
    tables = flatten_current_extractions(_minimal_current_extractions())
    tables["administrative_actions"] = tables[
        "administrative_actions"
    ].iloc[0:0].copy()
    tables["publication_events"].loc[0, "n_administrative_actions"] = 0

    _assert_invalid(
        tables,
        table="publication_events",
        rule="minimum_cardinality:administrative_actions",
    )


def test_rejects_generation_asset_without_names() -> None:
    tables = flatten_current_extractions(_minimal_current_extractions())
    tables["generation_asset_names"] = tables[
        "generation_asset_names"
    ].iloc[0:0].copy()

    _assert_invalid(
        tables,
        table="generation_asset_mentions",
        rule="minimum_cardinality:generation_asset_names",
    )


@pytest.mark.parametrize("replacement", [1, 3])
def test_rejects_duplicate_or_nonconsecutive_index(replacement: int) -> None:
    tables = _valid_tables()
    tables["generation_asset_names"].loc[1, "name_index"] = replacement

    _assert_invalid(
        tables,
        table="generation_asset_names",
        rule="consecutive_index",
    )


def test_rejects_index_sequence_that_does_not_start_at_one() -> None:
    tables = _valid_tables()
    tables["generation_asset_names"].loc[
        [0, 1], "name_index"
    ] = [2, 3]

    _assert_invalid(
        tables,
        table="generation_asset_names",
        rule="consecutive_index",
    )


def test_valid_tables_remain_valid_after_independent_row_shuffling() -> None:
    tables = _valid_tables()
    shuffled = {
        table_name: dataframe.sample(frac=1, random_state=0)
        for table_name, dataframe in tables.items()
    }

    assert all(
        not dataframe.index.equals(shuffled[table_name].index)
        for table_name, dataframe in tables.items()
        if len(dataframe) > 1
    )
    assert validate_flat_tables(shuffled) is None


@pytest.mark.parametrize(
    ("table_name", "id_column", "replacement", "rule"),
    [
        (
            "administrative_actions",
            "administrative_action_id",
            f"{EVENT_1}_action_99",
            "identifier_formula",
        ),
        (
            "participant_mentions",
            "participant_mention_id",
            f"{EVENT_1}_participant_99",
            "positional_identifier",
        ),
        (
            "location_mentions",
            "location_mention_id",
            f"{EVENT_1}_location_99",
            "positional_identifier",
        ),
        (
            "generation_asset_relations",
            "generation_asset_relation_id",
            f"{EVENT_1}_relation_99",
            "positional_identifier",
        ),
        (
            "technical_mentions",
            "technical_mention_id",
            f"{ASSET_1}_technical_99",
            "positional_identifier",
        ),
    ],
)
def test_rejects_incoherent_positional_identifiers(
    table_name: str,
    id_column: str,
    replacement: str,
    rule: str,
) -> None:
    tables = _valid_tables()
    tables[table_name].loc[0, id_column] = replacement

    _assert_invalid(tables, table=table_name, rule=rule)


@pytest.mark.parametrize(
    ("row_index", "column_name", "value", "rule"),
    [
        (0, "target_kind", "unknown", "polymorphic_discriminator"),
        (0, "target_entity_id", EVENT_2, "polymorphic_target_event"),
        (1, "target_entity_id", "missing_asset", "polymorphic_target"),
        (2, "target_entity_id", "missing_component", "polymorphic_target"),
        (1, "target_ref", "generation_asset_2", "polymorphic_target_reference"),
    ],
)
def test_rejects_invalid_polymorphic_targets(
    row_index: int,
    column_name: str,
    value: str,
    rule: str,
) -> None:
    tables = _valid_tables()
    tables["administrative_action_targets"].loc[
        row_index,
        column_name,
    ] = value

    _assert_invalid(
        tables,
        table="administrative_action_targets",
        rule=rule,
    )


def test_rejects_technical_mention_with_both_owners() -> None:
    tables = _valid_tables()
    tables["technical_mentions"].loc[0, "associated_component_id"] = (
        COMPONENT_1
    )

    _assert_invalid(
        tables,
        table="technical_mentions",
        rule="polymorphic_owner_exactly_one",
    )


def test_rejects_technical_mention_without_owner() -> None:
    tables = _valid_tables()
    tables["technical_mentions"].loc[0, "generation_asset_mention_id"] = pd.NA

    _assert_invalid(
        tables,
        table="technical_mentions",
        rule="polymorphic_owner_exactly_one",
    )


@pytest.mark.parametrize(
    ("column_name", "value", "rule"),
    [
        ("owner_kind", "associated_component", "polymorphic_owner_kind"),
        (
            "generation_asset_mention_id",
            "missing_asset",
            "polymorphic_owner:generation_asset_mentions",
        ),
        (
            "generation_asset_mention_id",
            ASSET_3,
            "polymorphic_owner_event",
        ),
        ("owner_ref", "generation_asset_2", "polymorphic_owner_reference"),
    ],
)
def test_rejects_invalid_technical_owner(
    column_name: str,
    value: str,
    rule: str,
) -> None:
    tables = _valid_tables()
    tables["technical_mentions"].loc[0, column_name] = value

    _assert_invalid(tables, table="technical_mentions", rule=rule)


@pytest.mark.parametrize(
    ("table_name", "column_name", "value"),
    [
        ("generation_asset_mentions", "generation_type", "unknown"),
        ("associated_components", "component_type", "unknown"),
        ("administrative_actions", "action_type", "unknown"),
        ("administrative_actions", "decision", "unknown"),
        ("participant_mentions", "participant_role", "unknown"),
        ("location_mentions", "location_level", "unknown"),
        ("generation_asset_relations", "relation_type", "unknown"),
        ("technical_mentions", "attribute_type", "unknown"),
    ],
)
def test_rejects_unknown_enum_values(
    table_name: str,
    column_name: str,
    value: str,
) -> None:
    tables = _valid_tables()
    tables[table_name].loc[0, column_name] = value

    _assert_invalid(tables, table=table_name, rule="controlled_domain")


def test_rejects_link_with_incompatible_local_reference() -> None:
    tables = _valid_tables()
    tables["associated_component_generation_links"].loc[
        0,
        "local_generation_asset_ref",
    ] = "generation_asset_2"

    _assert_invalid(
        tables,
        table="associated_component_generation_links",
        rule="local_global_reference",
    )


def test_rejects_relation_with_incompatible_local_reference() -> None:
    tables = _valid_tables()
    tables["generation_asset_relations"].loc[
        0,
        "source_generation_asset_ref",
    ] = "generation_asset_2"

    _assert_invalid(
        tables,
        table="generation_asset_relations",
        rule="local_global_reference",
    )


def test_rejects_self_relation_between_generation_assets() -> None:
    tables = _valid_tables()
    tables["generation_asset_relations"].loc[
        0,
        "target_generation_asset_ref",
    ] = "generation_asset_1"
    tables["generation_asset_relations"].loc[
        0,
        "target_generation_asset_mention_id",
    ] = ASSET_1

    _assert_invalid(
        tables,
        table="generation_asset_relations",
        rule="self_relation",
    )


def test_error_aggregates_rules_and_limits_samples() -> None:
    tables = _valid_tables()
    tables["publication_events"].loc[:, "event_summary"] = "   "
    tables["generation_asset_mentions"].loc[:, "generation_type"] = "unknown"

    error = _assert_invalid(
        tables,
        table="publication_events",
        rule="required_string_blank",
    )

    assert len(error.issues) >= 2
    assert all(len(issue.sample) <= 5 for issue in error.issues)
