from inspect import signature

import pandas as pd
import pyarrow as pa
import pytest

import renewables_permitting.extraction.flat_contract as contract_module
import renewables_permitting.extraction.flatten as flatten_module
from renewables_permitting.extraction.flat_contract import (
    FLAT_CONTRACT_VERSION,
    FLAT_TABLE_COLUMNS,
    FLAT_TABLE_SPECS,
    apply_flat_table_types,
)


EXPECTED_TABLE_COLUMNS = {
    "publication_events": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "event_index",
        "event_summary",
        "n_generation_assets",
        "n_associated_components",
        "n_administrative_actions",
    ),
    "generation_asset_mentions": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_mention_id",
        "local_generation_asset_ref",
        "generation_type",
        "evidence",
    ),
    "generation_asset_names": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "generation_asset_mention_id",
        "name_index",
        "name_raw",
    ),
    "associated_components": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "associated_component_id",
        "local_component_ref",
        "component_type",
        "description_raw",
        "evidence",
    ),
    "associated_component_names": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "associated_component_id",
        "name_index",
        "name_raw",
    ),
    "associated_component_generation_links": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "associated_component_id",
        "link_index",
        "local_generation_asset_ref",
        "generation_asset_mention_id",
    ),
    "administrative_actions": (
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
    "administrative_action_targets": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "administrative_action_id",
        "target_index",
        "target_ref",
        "target_entity_id",
        "target_kind",
    ),
    "participant_mentions": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "participant_mention_id",
        "participant_name_raw",
        "participant_role",
        "evidence",
    ),
    "location_mentions": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "location_mention_id",
        "location_name_raw",
        "location_level",
        "province_hint_raw",
        "autonomous_community_hint_raw",
        "evidence",
    ),
    "generation_asset_relations": (
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
    ),
    "technical_mentions": (
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
    ),
    "case_file_references": (
        "event_id",
        "identificador_boe",
        "fecha_publicacion",
        "case_file_reference_id",
        "reference_index",
        "case_file_reference_raw",
    ),
}


EXPECTED_PRIMARY_KEYS = {
    "publication_events": ("event_id",),
    "generation_asset_mentions": ("generation_asset_mention_id",),
    "generation_asset_names": (
        "generation_asset_mention_id",
        "name_index",
    ),
    "associated_components": ("associated_component_id",),
    "associated_component_names": (
        "associated_component_id",
        "name_index",
    ),
    "associated_component_generation_links": (
        "associated_component_id",
        "link_index",
    ),
    "administrative_actions": ("administrative_action_id",),
    "administrative_action_targets": (
        "administrative_action_id",
        "target_index",
    ),
    "participant_mentions": ("participant_mention_id",),
    "location_mentions": ("location_mention_id",),
    "generation_asset_relations": ("generation_asset_relation_id",),
    "technical_mentions": ("technical_mention_id",),
    "case_file_references": ("case_file_reference_id",),
}


EVENT_FK = (
    ("event_id",),
    "publication_events",
    ("event_id",),
)


EXPECTED_FOREIGN_KEYS = {
    "publication_events": (),
    "generation_asset_mentions": (EVENT_FK,),
    "generation_asset_names": (
        EVENT_FK,
        (
            ("generation_asset_mention_id",),
            "generation_asset_mentions",
            ("generation_asset_mention_id",),
        ),
    ),
    "associated_components": (EVENT_FK,),
    "associated_component_names": (
        EVENT_FK,
        (
            ("associated_component_id",),
            "associated_components",
            ("associated_component_id",),
        ),
    ),
    "associated_component_generation_links": (
        EVENT_FK,
        (
            ("associated_component_id",),
            "associated_components",
            ("associated_component_id",),
        ),
        (
            ("generation_asset_mention_id",),
            "generation_asset_mentions",
            ("generation_asset_mention_id",),
        ),
    ),
    "administrative_actions": (EVENT_FK,),
    "administrative_action_targets": (
        EVENT_FK,
        (
            ("administrative_action_id",),
            "administrative_actions",
            ("administrative_action_id",),
        ),
    ),
    "participant_mentions": (EVENT_FK,),
    "location_mentions": (EVENT_FK,),
    "generation_asset_relations": (
        EVENT_FK,
        (
            ("source_generation_asset_mention_id",),
            "generation_asset_mentions",
            ("generation_asset_mention_id",),
        ),
        (
            ("target_generation_asset_mention_id",),
            "generation_asset_mentions",
            ("generation_asset_mention_id",),
        ),
    ),
    "technical_mentions": (EVENT_FK,),
    "case_file_references": (EVENT_FK,),
}


EXPECTED_POLYMORPHIC_RELATIONS = {
    "administrative_action_targets": (
        (
            "target_kind",
            "event",
            "target_entity_id",
            "publication_events",
            "event_id",
        ),
        (
            "target_kind",
            "generation_asset",
            "target_entity_id",
            "generation_asset_mentions",
            "generation_asset_mention_id",
        ),
        (
            "target_kind",
            "associated_component",
            "target_entity_id",
            "associated_components",
            "associated_component_id",
        ),
    ),
    "technical_mentions": (
        (
            "owner_kind",
            "generation_asset",
            "generation_asset_mention_id",
            "generation_asset_mentions",
            "generation_asset_mention_id",
        ),
        (
            "owner_kind",
            "associated_component",
            "associated_component_id",
            "associated_components",
            "associated_component_id",
        ),
    ),
}


INTEGER_COLUMNS = {
    ("publication_events", "event_index"),
    ("publication_events", "n_generation_assets"),
    ("publication_events", "n_associated_components"),
    ("publication_events", "n_administrative_actions"),
    ("generation_asset_names", "name_index"),
    ("associated_component_names", "name_index"),
    ("associated_component_generation_links", "link_index"),
    ("administrative_actions", "action_index"),
    ("administrative_action_targets", "target_index"),
    ("case_file_references", "reference_index"),
}


NULLABLE_COLUMNS = {
    ("associated_components", "description_raw"),
    ("location_mentions", "province_hint_raw"),
    ("location_mentions", "autonomous_community_hint_raw"),
    ("technical_mentions", "generation_asset_mention_id"),
    ("technical_mentions", "associated_component_id"),
}


def _expected_types(table_name: str, column_name: str) -> tuple[str, pa.DataType]:
    if column_name == "fecha_publicacion":
        return "datetime64[ns]", pa.timestamp("ns")
    if (table_name, column_name) in INTEGER_COLUMNS:
        return "Int64", pa.int64()
    if (table_name, column_name) == (
        "administrative_actions",
        "is_modification",
    ):
        return "boolean", pa.bool_()
    return "string", pa.string()


def _untyped_tables(
    *,
    empty_names: set[str] | None = None,
    reverse_columns: bool = False,
) -> dict[str, pd.DataFrame]:
    empty_names = empty_names or set()
    tables: dict[str, pd.DataFrame] = {}
    for table_name, columns in EXPECTED_TABLE_COLUMNS.items():
        if table_name in empty_names:
            dataframe = pd.DataFrame(columns=columns)
        else:
            record: dict[str, object] = {}
            for column_name in columns:
                pandas_dtype, _ = _expected_types(table_name, column_name)
                if (table_name, column_name) in NULLABLE_COLUMNS:
                    value: object = None
                elif pandas_dtype == "Int64":
                    value = 1
                elif pandas_dtype == "boolean":
                    value = True
                elif pandas_dtype == "datetime64[ns]":
                    value = pd.Timestamp("2026-01-02")
                else:
                    value = f"{table_name}-{column_name}"
                record[column_name] = value
            dataframe = pd.DataFrame([record], columns=columns, index=[7])
        if reverse_columns:
            dataframe = dataframe.loc[:, list(reversed(columns))]
        tables[table_name] = dataframe
    return tables


def _assert_contractual_types(tables: dict[str, pd.DataFrame]) -> None:
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        dataframe = tables[table_name]
        assert dataframe.columns.tolist() == list(table_spec.column_names)
        for column in table_spec.columns:
            assert str(dataframe.dtypes[column.name]) == column.pandas_dtype
        arrow_schema = pa.Schema.from_pandas(
            dataframe,
            preserve_index=False,
        )
        assert [field.type for field in arrow_schema] == [
            column.arrow_type for column in table_spec.columns
        ]


def test_contract_version_and_exact_table_order() -> None:
    assert FLAT_CONTRACT_VERSION == "1"
    assert tuple(FLAT_TABLE_SPECS) == tuple(EXPECTED_TABLE_COLUMNS)
    assert len(FLAT_TABLE_SPECS) == 13


def test_contract_declares_exact_columns_order_and_filenames() -> None:
    for table_name, expected_columns in EXPECTED_TABLE_COLUMNS.items():
        table_spec = FLAT_TABLE_SPECS[table_name]
        assert table_spec.name == table_name
        assert table_spec.filename == f"{table_name}.parquet"
        assert table_spec.column_names == expected_columns
        assert table_spec.arrow_schema.names == list(expected_columns)


def test_every_column_declares_pandas_arrow_types_and_nullability() -> None:
    observed_nullable: set[tuple[str, str]] = set()
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        for column in table_spec.columns:
            expected_pandas, expected_arrow = _expected_types(
                table_name,
                column.name,
            )
            assert column.pandas_dtype == expected_pandas
            assert column.arrow_type == expected_arrow
            assert column.nullable is (
                (table_name, column.name) in NULLABLE_COLUMNS
            )
            assert table_spec.arrow_schema.field(column.name).nullable is (
                column.nullable
            )
            if column.nullable:
                observed_nullable.add((table_name, column.name))
    assert observed_nullable == NULLABLE_COLUMNS


def test_contract_declares_primary_and_foreign_keys() -> None:
    assert {
        name: table.primary_key
        for name, table in FLAT_TABLE_SPECS.items()
    } == EXPECTED_PRIMARY_KEYS
    observed_foreign_keys = {
        name: tuple(
            (
                foreign_key.source_columns,
                foreign_key.target_table,
                foreign_key.target_columns,
            )
            for foreign_key in table.foreign_keys
        )
        for name, table in FLAT_TABLE_SPECS.items()
    }
    assert observed_foreign_keys == EXPECTED_FOREIGN_KEYS


def test_contract_declares_only_the_two_polymorphic_relationships() -> None:
    observed = {
        name: tuple(
            (
                relation.discriminator_column,
                relation.discriminator_value,
                relation.source_column,
                relation.target_table,
                relation.target_column,
            )
            for relation in table.polymorphic_relations
        )
        for name, table in FLAT_TABLE_SPECS.items()
        if table.polymorphic_relations
    }
    assert observed == EXPECTED_POLYMORPHIC_RELATIONS


def test_flat_table_columns_is_a_derived_compatibility_view() -> None:
    assert flatten_module.FLAT_TABLE_COLUMNS is FLAT_TABLE_COLUMNS
    assert contract_module.FLAT_TABLE_COLUMNS is FLAT_TABLE_COLUMNS
    assert FLAT_TABLE_COLUMNS == {
        table_name: list(table_spec.column_names)
        for table_name, table_spec in FLAT_TABLE_SPECS.items()
    }


def test_apply_flat_table_types_has_stable_public_signature_and_docstring() -> None:
    assert tuple(signature(apply_flat_table_types).parameters) == ("tables",)
    assert apply_flat_table_types.__doc__


def test_apply_types_to_all_empty_tables() -> None:
    tables = _untyped_tables(empty_names=set(EXPECTED_TABLE_COLUMNS))

    typed = apply_flat_table_types(tables)

    assert all(table.empty for table in typed.values())
    _assert_contractual_types(typed)


def test_apply_types_to_mixed_empty_and_populated_tables_and_reorders_columns() -> None:
    empty_names = set(tuple(EXPECTED_TABLE_COLUMNS)[::2])
    tables = _untyped_tables(
        empty_names=empty_names,
        reverse_columns=True,
    )

    typed = apply_flat_table_types(dict(reversed(tuple(tables.items()))))

    assert tuple(typed) == tuple(EXPECTED_TABLE_COLUMNS)
    assert {
        name for name, dataframe in typed.items() if dataframe.empty
    } == empty_names
    _assert_contractual_types(typed)


def test_apply_rejects_a_missing_table() -> None:
    tables = _untyped_tables()
    del tables["technical_mentions"]

    with pytest.raises(ValueError, match="faltan=\\['technical_mentions'\\]"):
        apply_flat_table_types(tables)


def test_apply_rejects_an_unexpected_table() -> None:
    tables = _untyped_tables()
    tables["unexpected"] = pd.DataFrame()

    with pytest.raises(ValueError, match="inesperadas=\\['unexpected'\\]"):
        apply_flat_table_types(tables)


def test_apply_rejects_a_missing_column() -> None:
    tables = _untyped_tables()
    tables["publication_events"] = tables["publication_events"].drop(
        columns=["event_summary"]
    )

    with pytest.raises(ValueError, match="faltan=\\['event_summary'\\]"):
        apply_flat_table_types(tables)


def test_apply_rejects_an_unexpected_column() -> None:
    tables = _untyped_tables()
    tables["publication_events"]["unexpected"] = "value"

    with pytest.raises(ValueError, match="inesperadas=\\['unexpected'\\]"):
        apply_flat_table_types(tables)


def test_apply_rejects_duplicate_columns_without_modifying_inputs() -> None:
    tables = _untyped_tables()
    snapshots = {
        name: dataframe.copy(deep=True)
        for name, dataframe in tables.items()
    }
    duplicated = pd.concat([
        tables["publication_events"],
        tables["publication_events"][["event_id"]],
    ], axis="columns")
    invalid_tables = {**tables, "publication_events": duplicated}

    with pytest.raises(
        ValueError,
        match="publication_events.*columnas duplicadas",
    ):
        apply_flat_table_types(invalid_tables)

    for name, dataframe in tables.items():
        pd.testing.assert_frame_equal(dataframe, snapshots[name])


def test_apply_rejects_a_non_convertible_value_without_coercing_it() -> None:
    tables = _untyped_tables()
    tables["publication_events"]["event_index"] = pd.Series(
        ["not-an-integer"],
        index=tables["publication_events"].index,
        dtype="object",
    )

    with pytest.raises(
        TypeError,
        match="publication_events.*event_index.*Int64",
    ):
        apply_flat_table_types(tables)
    assert tables["publication_events"].iloc[0]["event_index"] == (
        "not-an-integer"
    )


def test_apply_does_not_modify_input_dataframes() -> None:
    tables = _untyped_tables(reverse_columns=True)
    snapshots = {
        name: dataframe.copy(deep=True)
        for name, dataframe in tables.items()
    }

    typed = apply_flat_table_types(tables)

    for name, original in tables.items():
        assert typed[name] is not original
        pd.testing.assert_frame_equal(original, snapshots[name])


def test_apply_is_deterministic_for_the_same_input() -> None:
    tables = _untyped_tables(
        empty_names={"associated_component_names", "technical_mentions"}
    )

    first = apply_flat_table_types(tables)
    second = apply_flat_table_types(tables)

    for name in EXPECTED_TABLE_COLUMNS:
        pd.testing.assert_frame_equal(first[name], second[name])
