from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import pandas as pd
import pyarrow as pa


FLAT_CONTRACT_VERSION = "1"


@dataclass(frozen=True)
class FlatColumnSpec:
    """Declara el nombre, tipo y nulabilidad de una columna Silver."""

    name: str
    pandas_dtype: str
    arrow_type: pa.DataType
    nullable: bool = False


@dataclass(frozen=True)
class FlatForeignKeySpec:
    """Describe una clave foránea lógica sin imponer su validación."""

    source_columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]


@dataclass(frozen=True)
class FlatPolymorphicRelationSpec:
    """Describe una rama de una relación lógica polimórfica."""

    discriminator_column: str
    discriminator_value: str
    source_column: str
    target_table: str
    target_column: str


@dataclass(frozen=True)
class FlatTableSpec:
    """Contiene el contrato declarativo de una tabla normalizada."""

    name: str
    filename: str
    columns: tuple[FlatColumnSpec, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[FlatForeignKeySpec, ...] = ()
    polymorphic_relations: tuple[FlatPolymorphicRelationSpec, ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        """Devuelve los nombres de columna en el orden contractual."""

        return tuple(column.name for column in self.columns)

    @property
    def arrow_schema(self) -> pa.Schema:
        """Devuelve el esquema PyArrow declarado para la tabla."""

        return pa.schema([
            pa.field(
                column.name,
                column.arrow_type,
                nullable=column.nullable,
            )
            for column in self.columns
        ])


def _string(name: str, *, nullable: bool = False) -> FlatColumnSpec:
    return FlatColumnSpec(name, "string", pa.string(), nullable)


def _integer(name: str) -> FlatColumnSpec:
    return FlatColumnSpec(name, "Int64", pa.int64())


def _boolean(name: str) -> FlatColumnSpec:
    return FlatColumnSpec(name, "boolean", pa.bool_())


def _timestamp(name: str) -> FlatColumnSpec:
    return FlatColumnSpec(name, "datetime64[ns]", pa.timestamp("ns"))


_TRACEABILITY_COLUMNS = (
    _string("event_id"),
    _string("identificador_boe"),
    _timestamp("fecha_publicacion"),
)


def _columns(*columns: FlatColumnSpec) -> tuple[FlatColumnSpec, ...]:
    return (*_TRACEABILITY_COLUMNS, *columns)


def _foreign_key(
    source_column: str,
    target_table: str,
    target_column: str,
) -> FlatForeignKeySpec:
    return FlatForeignKeySpec(
        source_columns=(source_column,),
        target_table=target_table,
        target_columns=(target_column,),
    )


_EVENT_FOREIGN_KEY = _foreign_key(
    "event_id",
    "publication_events",
    "event_id",
)


_TABLE_SPECS = (
    FlatTableSpec(
        name="publication_events",
        filename="publication_events.parquet",
        columns=_columns(
            _integer("event_index"),
            _string("event_summary"),
            _integer("n_generation_assets"),
            _integer("n_associated_components"),
            _integer("n_administrative_actions"),
        ),
        primary_key=("event_id",),
    ),
    FlatTableSpec(
        name="generation_asset_mentions",
        filename="generation_asset_mentions.parquet",
        columns=_columns(
            _string("generation_asset_mention_id"),
            _string("local_generation_asset_ref"),
            _string("generation_type"),
            _string("evidence"),
        ),
        primary_key=("generation_asset_mention_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
    ),
    FlatTableSpec(
        name="generation_asset_names",
        filename="generation_asset_names.parquet",
        columns=_columns(
            _string("generation_asset_mention_id"),
            _integer("name_index"),
            _string("name_raw"),
        ),
        primary_key=("generation_asset_mention_id", "name_index"),
        foreign_keys=(
            _EVENT_FOREIGN_KEY,
            _foreign_key(
                "generation_asset_mention_id",
                "generation_asset_mentions",
                "generation_asset_mention_id",
            ),
        ),
    ),
    FlatTableSpec(
        name="associated_components",
        filename="associated_components.parquet",
        columns=_columns(
            _string("associated_component_id"),
            _string("local_component_ref"),
            _string("component_type"),
            _string("description_raw", nullable=True),
            _string("evidence"),
        ),
        primary_key=("associated_component_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
    ),
    FlatTableSpec(
        name="associated_component_names",
        filename="associated_component_names.parquet",
        columns=_columns(
            _string("associated_component_id"),
            _integer("name_index"),
            _string("name_raw"),
        ),
        primary_key=("associated_component_id", "name_index"),
        foreign_keys=(
            _EVENT_FOREIGN_KEY,
            _foreign_key(
                "associated_component_id",
                "associated_components",
                "associated_component_id",
            ),
        ),
    ),
    FlatTableSpec(
        name="associated_component_generation_links",
        filename="associated_component_generation_links.parquet",
        columns=_columns(
            _string("associated_component_id"),
            _integer("link_index"),
            _string("local_generation_asset_ref"),
            _string("generation_asset_mention_id"),
        ),
        primary_key=("associated_component_id", "link_index"),
        foreign_keys=(
            _EVENT_FOREIGN_KEY,
            _foreign_key(
                "associated_component_id",
                "associated_components",
                "associated_component_id",
            ),
            _foreign_key(
                "generation_asset_mention_id",
                "generation_asset_mentions",
                "generation_asset_mention_id",
            ),
        ),
    ),
    FlatTableSpec(
        name="administrative_actions",
        filename="administrative_actions.parquet",
        columns=_columns(
            _string("administrative_action_id"),
            _integer("action_index"),
            _string("action_type"),
            _string("decision"),
            _boolean("is_modification"),
            _string("evidence"),
        ),
        primary_key=("administrative_action_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
    ),
    FlatTableSpec(
        name="administrative_action_targets",
        filename="administrative_action_targets.parquet",
        columns=_columns(
            _string("administrative_action_id"),
            _integer("target_index"),
            _string("target_ref"),
            _string("target_entity_id"),
            _string("target_kind"),
        ),
        primary_key=("administrative_action_id", "target_index"),
        foreign_keys=(
            _EVENT_FOREIGN_KEY,
            _foreign_key(
                "administrative_action_id",
                "administrative_actions",
                "administrative_action_id",
            ),
        ),
        polymorphic_relations=(
            FlatPolymorphicRelationSpec(
                discriminator_column="target_kind",
                discriminator_value="event",
                source_column="target_entity_id",
                target_table="publication_events",
                target_column="event_id",
            ),
            FlatPolymorphicRelationSpec(
                discriminator_column="target_kind",
                discriminator_value="generation_asset",
                source_column="target_entity_id",
                target_table="generation_asset_mentions",
                target_column="generation_asset_mention_id",
            ),
            FlatPolymorphicRelationSpec(
                discriminator_column="target_kind",
                discriminator_value="associated_component",
                source_column="target_entity_id",
                target_table="associated_components",
                target_column="associated_component_id",
            ),
        ),
    ),
    FlatTableSpec(
        name="participant_mentions",
        filename="participant_mentions.parquet",
        columns=_columns(
            _string("participant_mention_id"),
            _string("participant_name_raw"),
            _string("participant_role"),
            _string("evidence"),
        ),
        primary_key=("participant_mention_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
    ),
    FlatTableSpec(
        name="location_mentions",
        filename="location_mentions.parquet",
        columns=_columns(
            _string("location_mention_id"),
            _string("location_name_raw"),
            _string("location_level"),
            _string("province_hint_raw", nullable=True),
            _string("autonomous_community_hint_raw", nullable=True),
            _string("evidence"),
        ),
        primary_key=("location_mention_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
    ),
    FlatTableSpec(
        name="generation_asset_relations",
        filename="generation_asset_relations.parquet",
        columns=_columns(
            _string("generation_asset_relation_id"),
            _string("source_generation_asset_ref"),
            _string("source_generation_asset_mention_id"),
            _string("target_generation_asset_ref"),
            _string("target_generation_asset_mention_id"),
            _string("relation_type"),
            _string("evidence"),
        ),
        primary_key=("generation_asset_relation_id",),
        foreign_keys=(
            _EVENT_FOREIGN_KEY,
            _foreign_key(
                "source_generation_asset_mention_id",
                "generation_asset_mentions",
                "generation_asset_mention_id",
            ),
            _foreign_key(
                "target_generation_asset_mention_id",
                "generation_asset_mentions",
                "generation_asset_mention_id",
            ),
        ),
    ),
    FlatTableSpec(
        name="technical_mentions",
        filename="technical_mentions.parquet",
        columns=_columns(
            _string("technical_mention_id"),
            _string("owner_kind"),
            _string("owner_ref"),
            _string("generation_asset_mention_id", nullable=True),
            _string("associated_component_id", nullable=True),
            _string("attribute_type"),
            _string("value_raw"),
            _string("evidence"),
        ),
        primary_key=("technical_mention_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
        polymorphic_relations=(
            FlatPolymorphicRelationSpec(
                discriminator_column="owner_kind",
                discriminator_value="generation_asset",
                source_column="generation_asset_mention_id",
                target_table="generation_asset_mentions",
                target_column="generation_asset_mention_id",
            ),
            FlatPolymorphicRelationSpec(
                discriminator_column="owner_kind",
                discriminator_value="associated_component",
                source_column="associated_component_id",
                target_table="associated_components",
                target_column="associated_component_id",
            ),
        ),
    ),
    FlatTableSpec(
        name="case_file_references",
        filename="case_file_references.parquet",
        columns=_columns(
            _string("case_file_reference_id"),
            _integer("reference_index"),
            _string("case_file_reference_raw"),
        ),
        primary_key=("case_file_reference_id",),
        foreign_keys=(_EVENT_FOREIGN_KEY,),
    ),
)


FLAT_TABLE_SPECS: Mapping[str, FlatTableSpec] = MappingProxyType({
    table.name: table
    for table in _TABLE_SPECS
})


FLAT_TABLE_COLUMNS: dict[str, list[str]] = {
    table_name: list(table_spec.column_names)
    for table_name, table_spec in FLAT_TABLE_SPECS.items()
}


def apply_flat_table_types(
    tables: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Copia las 13 tablas y aplica su orden y tipos contractuales."""

    expected_table_names = tuple(FLAT_TABLE_SPECS)
    actual_table_names = tuple(tables)
    missing_tables = [
        name for name in expected_table_names if name not in tables
    ]
    unexpected_tables = [
        name for name in actual_table_names if name not in FLAT_TABLE_SPECS
    ]
    if missing_tables or unexpected_tables:
        raise ValueError(
            "Conjunto de tablas incompatible con el contrato: "
            f"faltan={missing_tables}; inesperadas={unexpected_tables}."
        )

    typed_tables: dict[str, pd.DataFrame] = {}
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        dataframe = tables[table_name]
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError(
                f"{table_name!r} debe ser un pandas.DataFrame."
            )
        if not dataframe.columns.is_unique:
            duplicated = dataframe.columns[
                dataframe.columns.duplicated()
            ].tolist()
            raise ValueError(
                f"{table_name!r} contiene columnas duplicadas: {duplicated}."
            )

        expected_columns = table_spec.column_names
        actual_columns = tuple(dataframe.columns)
        missing_columns = [
            name for name in expected_columns if name not in actual_columns
        ]
        unexpected_columns = [
            name for name in actual_columns if name not in expected_columns
        ]
        if missing_columns or unexpected_columns:
            raise ValueError(
                f"Columnas incompatibles en {table_name!r}: "
                f"faltan={missing_columns}; inesperadas={unexpected_columns}."
            )

        typed = dataframe.loc[:, list(expected_columns)].copy(deep=True)
        for column in table_spec.columns:
            try:
                typed[column.name] = typed[column.name].astype(
                    column.pandas_dtype
                )
            except (TypeError, ValueError, OverflowError) as error:
                raise TypeError(
                    f"No se puede convertir {table_name!r}.{column.name} "
                    f"a {column.pandas_dtype}."
                ) from error
        typed_tables[table_name] = typed

    return typed_tables
