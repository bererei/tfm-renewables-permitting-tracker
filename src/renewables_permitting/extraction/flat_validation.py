from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from renewables_permitting.extraction.flat_contract import FLAT_TABLE_SPECS
from renewables_permitting.extraction.models import (
    AdministrativeActionType,
    AdministrativeDecision,
    AdministrativeLocationLevel,
    AssociatedComponentType,
    GenerationRelationType,
    GenerationType,
    ParticipantRole,
    TechnicalAttributeType,
)


_SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class FlatTableValidationIssue:
    """Representa una incidencia estructural o relacional limitada."""

    table: str
    rule: str
    columns: tuple[str, ...]
    sample: tuple[str, ...] = ()

    def render(self) -> str:
        """Devuelve una descripción compacta de la incidencia."""

        columns = ", ".join(self.columns) if self.columns else "-"
        sample = "; ".join(self.sample) if self.sample else "-"
        return (
            f"tabla={self.table}; regla={self.rule}; "
            f"columnas={columns}; muestra={sample}"
        )


class FlatTableValidationError(ValueError):
    """Agrupa las incidencias detectadas en las tablas normalizadas."""

    def __init__(self, issues: list[FlatTableValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "\n".join(f"- {issue.render()}" for issue in self.issues)
        super().__init__(
            f"Se detectaron {len(self.issues)} incidencias en las tablas "
            f"normalizadas:\n{details}"
        )


def _sample_rows(
    dataframe: pd.DataFrame,
    mask: pd.Series | list[bool],
    columns: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    selected_columns = [
        column for column in dict.fromkeys(columns) if column in dataframe.columns
    ]
    boolean_mask = pd.Series(mask).fillna(False).to_numpy(dtype=bool)
    records = dataframe.loc[boolean_mask, selected_columns].head(
        _SAMPLE_LIMIT
    ).to_dict(orient="records")
    return tuple(repr(record) for record in records)


def _append_mask_issue(
    issues: list[FlatTableValidationIssue],
    *,
    table: str,
    rule: str,
    columns: tuple[str, ...],
    dataframe: pd.DataFrame,
    mask: pd.Series | list[bool],
    sample_columns: tuple[str, ...] | None = None,
) -> None:
    boolean_mask = pd.Series(mask).fillna(False).to_numpy(dtype=bool)
    if not boolean_mask.any():
        return
    issues.append(FlatTableValidationIssue(
        table=table,
        rule=rule,
        columns=columns,
        sample=_sample_rows(
            dataframe,
            boolean_mask,
            sample_columns or columns,
        ),
    ))


def _basic_contract_issues(
    tables: Mapping[str, pd.DataFrame],
) -> list[FlatTableValidationIssue]:
    issues: list[FlatTableValidationIssue] = []
    expected_names = tuple(FLAT_TABLE_SPECS)
    actual_names = tuple(tables)

    for table_name in expected_names:
        if table_name not in tables:
            issues.append(FlatTableValidationIssue(
                table=table_name,
                rule="missing_table",
                columns=(),
            ))
    for table_name in actual_names:
        if table_name not in FLAT_TABLE_SPECS:
            issues.append(FlatTableValidationIssue(
                table=str(table_name),
                rule="unexpected_table",
                columns=(),
            ))

    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        if table_name not in tables:
            continue
        dataframe = tables[table_name]
        if not isinstance(dataframe, pd.DataFrame):
            issues.append(FlatTableValidationIssue(
                table=table_name,
                rule="not_a_dataframe",
                columns=(),
                sample=(type(dataframe).__name__,),
            ))
            continue
        if not dataframe.columns.is_unique:
            duplicated = dataframe.columns[
                dataframe.columns.duplicated()
            ].tolist()
            issues.append(FlatTableValidationIssue(
                table=table_name,
                rule="duplicate_columns",
                columns=tuple(str(column) for column in duplicated),
            ))
            continue

        expected_columns = table_spec.column_names
        actual_columns = tuple(dataframe.columns)
        if actual_columns != expected_columns:
            issues.append(FlatTableValidationIssue(
                table=table_name,
                rule="column_contract",
                columns=tuple(str(column) for column in actual_columns),
                sample=(
                    f"esperadas={expected_columns!r}",
                    f"recibidas={actual_columns!r}",
                ),
            ))
            continue

        for column in table_spec.columns:
            actual_dtype = str(dataframe.dtypes[column.name])
            if actual_dtype != column.pandas_dtype:
                issues.append(FlatTableValidationIssue(
                    table=table_name,
                    rule="column_dtype",
                    columns=(column.name,),
                    sample=(
                        f"esperado={column.pandas_dtype!r}",
                        f"recibido={actual_dtype!r}",
                    ),
                ))
    return issues


def _validate_nullability(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        dataframe = tables[table_name]
        for column in table_spec.columns:
            series = dataframe[column.name]
            if not column.nullable:
                _append_mask_issue(
                    issues,
                    table=table_name,
                    rule="non_nullable",
                    columns=(column.name,),
                    dataframe=dataframe,
                    mask=series.isna(),
                    sample_columns=(
                        "event_id",
                        *table_spec.primary_key,
                        column.name,
                    ),
                )
            if column.pandas_dtype == "string" and not column.nullable:
                blank = series.notna() & series.str.strip().eq("")
                _append_mask_issue(
                    issues,
                    table=table_name,
                    rule="required_string_blank",
                    columns=(column.name,),
                    dataframe=dataframe,
                    mask=blank,
                    sample_columns=(
                        "event_id",
                        *table_spec.primary_key,
                        column.name,
                    ),
                )


def _validate_primary_keys(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        dataframe = tables[table_name]
        primary_key = table_spec.primary_key
        null_mask = dataframe.loc[:, list(primary_key)].isna().any(axis=1)
        _append_mask_issue(
            issues,
            table=table_name,
            rule="primary_key_null",
            columns=primary_key,
            dataframe=dataframe,
            mask=null_mask,
            sample_columns=primary_key,
        )
        duplicated = dataframe.duplicated(
            subset=list(primary_key),
            keep=False,
        ) & ~null_mask
        _append_mask_issue(
            issues,
            table=table_name,
            rule="primary_key_duplicate",
            columns=primary_key,
            dataframe=dataframe,
            mask=duplicated,
            sample_columns=primary_key,
        )


def _validate_event_context(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    events = tables["publication_events"]
    event_context = (
        events.drop_duplicates("event_id", keep="first")
        .set_index("event_id")
    )
    valid_event_ids = set(event_context.index.dropna())

    for table_name, dataframe in tables.items():
        if table_name == "publication_events" or dataframe.empty:
            continue
        orphan = ~dataframe["event_id"].isin(valid_event_ids)
        _append_mask_issue(
            issues,
            table=table_name,
            rule="event_foreign_key",
            columns=("event_id",),
            dataframe=dataframe,
            mask=orphan,
            sample_columns=(
                "event_id",
                "identificador_boe",
                "fecha_publicacion",
            ),
        )

        comparable = ~orphan & dataframe["event_id"].notna()
        expected_boe = dataframe["event_id"].map(
            event_context["identificador_boe"]
        )
        boe_mismatch = comparable & dataframe["identificador_boe"].ne(
            expected_boe
        ).fillna(True)
        _append_mask_issue(
            issues,
            table=table_name,
            rule="event_boe_context",
            columns=("event_id", "identificador_boe"),
            dataframe=dataframe,
            mask=boe_mismatch,
            sample_columns=("event_id", "identificador_boe"),
        )

        expected_date = dataframe["event_id"].map(
            event_context["fecha_publicacion"]
        )
        date_mismatch = comparable & dataframe["fecha_publicacion"].ne(
            expected_date
        ).fillna(True)
        _append_mask_issue(
            issues,
            table=table_name,
            rule="event_date_context",
            columns=("event_id", "fecha_publicacion"),
            dataframe=dataframe,
            mask=date_mismatch,
            sample_columns=("event_id", "fecha_publicacion"),
        )


def _key_is_null(key: tuple[Any, ...]) -> bool:
    return any(pd.isna(value) for value in key)


def _validate_declared_foreign_keys(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        source = tables[table_name].reset_index(drop=True)
        for foreign_key in table_spec.foreign_keys:
            if (
                foreign_key.target_table == "publication_events"
                and foreign_key.source_columns == ("event_id",)
            ):
                continue

            target = tables[foreign_key.target_table].reset_index(drop=True)
            target_events: dict[tuple[Any, ...], set[Any]] = {}
            target_columns = [
                *foreign_key.target_columns,
                "event_id",
            ]
            for values in target.loc[:, target_columns].itertuples(
                index=False,
                name=None,
            ):
                key = tuple(values[:-1])
                if _key_is_null(key):
                    continue
                target_events.setdefault(key, set()).add(values[-1])

            orphan_flags: list[bool] = []
            event_flags: list[bool] = []
            source_columns = [*foreign_key.source_columns, "event_id"]
            for values in source.loc[:, source_columns].itertuples(
                index=False,
                name=None,
            ):
                key = tuple(values[:-1])
                source_event_id = values[-1]
                if _key_is_null(key):
                    orphan_flags.append(False)
                    event_flags.append(False)
                    continue
                parent_events = target_events.get(key)
                orphan_flags.append(parent_events is None)
                event_flags.append(
                    parent_events is not None
                    and source_event_id not in parent_events
                )

            _append_mask_issue(
                issues,
                table=table_name,
                rule=f"foreign_key:{foreign_key.target_table}",
                columns=foreign_key.source_columns,
                dataframe=source,
                mask=orphan_flags,
                sample_columns=(
                    "event_id",
                    *foreign_key.source_columns,
                ),
            )
            _append_mask_issue(
                issues,
                table=table_name,
                rule=f"foreign_key_event:{foreign_key.target_table}",
                columns=("event_id", *foreign_key.source_columns),
                dataframe=source,
                mask=event_flags,
                sample_columns=(
                    "event_id",
                    *foreign_key.source_columns,
                ),
            )


def _validate_consecutive_index(
    issues: list[FlatTableValidationIssue],
    tables: Mapping[str, pd.DataFrame],
    *,
    table_name: str,
    group_columns: tuple[str, ...],
    index_column: str,
) -> None:
    dataframe = tables[table_name].reset_index(drop=True)
    invalid = pd.Series(False, index=dataframe.index)
    for _, group in dataframe.groupby(
        list(group_columns),
        sort=False,
        dropna=False,
    ):
        values = group[index_column].dropna().astype(int).tolist()
        expected = set(range(1, len(group) + 1))
        if len(values) != len(group) or set(values) != expected:
            invalid.loc[group.index] = True
    _append_mask_issue(
        issues,
        table=table_name,
        rule="consecutive_index",
        columns=(*group_columns, index_column),
        dataframe=dataframe,
        mask=invalid,
        sample_columns=(*group_columns, index_column),
    )


def _validate_id_formula(
    issues: list[FlatTableValidationIssue],
    tables: Mapping[str, pd.DataFrame],
    *,
    table_name: str,
    id_column: str,
    columns: tuple[str, ...],
    expected_id: Any,
) -> None:
    dataframe = tables[table_name].reset_index(drop=True)
    invalid: list[bool] = []
    for row in dataframe.itertuples(index=False):
        expected = expected_id(row)
        invalid.append(getattr(row, id_column) != expected)
    _append_mask_issue(
        issues,
        table=table_name,
        rule="identifier_formula",
        columns=(id_column, *columns),
        dataframe=dataframe,
        mask=invalid,
        sample_columns=(id_column, *columns),
    )


def _validate_local_entities(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
    *,
    table_name: str,
    local_column: str,
    id_column: str,
    local_prefix: str,
) -> None:
    dataframe = tables[table_name].reset_index(drop=True)
    sequence_invalid = pd.Series(False, index=dataframe.index)
    formula_invalid = pd.Series(False, index=dataframe.index)
    for _, group in dataframe.groupby(
        "event_id",
        sort=False,
        dropna=False,
    ):
        expected_refs = {
            f"{local_prefix}_{index}"
            for index in range(1, len(group) + 1)
        }
        actual_refs = group[local_column].dropna().astype(str).tolist()
        if len(actual_refs) != len(group) or set(actual_refs) != expected_refs:
            sequence_invalid.loc[group.index] = True
        expected_ids = group["event_id"] + "_" + group[local_column]
        mismatch = group[id_column].ne(expected_ids).fillna(True)
        formula_invalid.loc[group.index] = mismatch.to_numpy()

    _append_mask_issue(
        issues,
        table=table_name,
        rule="local_reference_sequence",
        columns=("event_id", local_column),
        dataframe=dataframe,
        mask=sequence_invalid,
        sample_columns=("event_id", local_column, id_column),
    )
    _append_mask_issue(
        issues,
        table=table_name,
        rule="local_global_identifier",
        columns=("event_id", local_column, id_column),
        dataframe=dataframe,
        mask=formula_invalid,
        sample_columns=("event_id", local_column, id_column),
    )


def _validate_numbered_ids(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
    *,
    table_name: str,
    id_column: str,
    suffix: str,
) -> None:
    dataframe = tables[table_name].reset_index(drop=True)
    invalid = pd.Series(False, index=dataframe.index)
    for event_id, group in dataframe.groupby(
        "event_id",
        sort=False,
        dropna=False,
    ):
        expected_ids = {
            f"{event_id}_{suffix}_{index}"
            for index in range(1, len(group) + 1)
        }
        actual_ids = group[id_column].dropna().astype(str).tolist()
        if len(actual_ids) != len(group) or set(actual_ids) != expected_ids:
            invalid.loc[group.index] = True
    _append_mask_issue(
        issues,
        table=table_name,
        rule="positional_identifier",
        columns=("event_id", id_column),
        dataframe=dataframe,
        mask=invalid,
        sample_columns=("event_id", id_column),
    )


def _validate_positions_and_identifiers(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    _validate_consecutive_index(
        issues,
        tables,
        table_name="publication_events",
        group_columns=("identificador_boe",),
        index_column="event_index",
    )
    _validate_id_formula(
        issues,
        tables,
        table_name="publication_events",
        id_column="event_id",
        columns=("identificador_boe", "event_index"),
        expected_id=lambda row: (
            f"{row.identificador_boe}_event_{row.event_index}"
        ),
    )

    _validate_local_entities(
        tables,
        issues,
        table_name="generation_asset_mentions",
        local_column="local_generation_asset_ref",
        id_column="generation_asset_mention_id",
        local_prefix="generation_asset",
    )
    _validate_local_entities(
        tables,
        issues,
        table_name="associated_components",
        local_column="local_component_ref",
        id_column="associated_component_id",
        local_prefix="component",
    )

    index_specs = (
        ("generation_asset_names", ("generation_asset_mention_id",), "name_index"),
        ("associated_component_names", ("associated_component_id",), "name_index"),
        (
            "associated_component_generation_links",
            ("associated_component_id",),
            "link_index",
        ),
        ("administrative_actions", ("event_id",), "action_index"),
        (
            "administrative_action_targets",
            ("administrative_action_id",),
            "target_index",
        ),
        ("case_file_references", ("event_id",), "reference_index"),
    )
    for table_name, group_columns, index_column in index_specs:
        _validate_consecutive_index(
            issues,
            tables,
            table_name=table_name,
            group_columns=group_columns,
            index_column=index_column,
        )

    _validate_id_formula(
        issues,
        tables,
        table_name="administrative_actions",
        id_column="administrative_action_id",
        columns=("event_id", "action_index"),
        expected_id=lambda row: (
            f"{row.event_id}_action_{row.action_index}"
        ),
    )
    _validate_id_formula(
        issues,
        tables,
        table_name="case_file_references",
        id_column="case_file_reference_id",
        columns=("event_id", "reference_index"),
        expected_id=lambda row: (
            f"{row.event_id}_case_file_{row.reference_index}"
        ),
    )

    for table_name, id_column, suffix in (
        ("participant_mentions", "participant_mention_id", "participant"),
        ("location_mentions", "location_mention_id", "location"),
        (
            "generation_asset_relations",
            "generation_asset_relation_id",
            "relation",
        ),
    ):
        _validate_numbered_ids(
            tables,
            issues,
            table_name=table_name,
            id_column=id_column,
            suffix=suffix,
        )


def _validate_event_counts(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    events = tables["publication_events"].reset_index(drop=True)
    count_specs = (
        (
            "n_generation_assets",
            "generation_asset_mentions",
            True,
        ),
        (
            "n_associated_components",
            "associated_components",
            False,
        ),
        (
            "n_administrative_actions",
            "administrative_actions",
            True,
        ),
    )
    for count_column, child_table, required in count_specs:
        counts = tables[child_table].groupby("event_id", dropna=False).size()
        actual = events["event_id"].map(counts).fillna(0).astype("Int64")
        mismatch = events[count_column].ne(actual).fillna(True)
        _append_mask_issue(
            issues,
            table="publication_events",
            rule=f"count_matches:{child_table}",
            columns=("event_id", count_column),
            dataframe=events,
            mask=mismatch,
            sample_columns=("event_id", count_column),
        )
        if required:
            _append_mask_issue(
                issues,
                table="publication_events",
                rule=f"minimum_cardinality:{child_table}",
                columns=("event_id",),
                dataframe=events,
                mask=actual.lt(1),
                sample_columns=("event_id", count_column),
            )

    asset_names = tables["generation_asset_names"].groupby(
        "generation_asset_mention_id",
        dropna=False,
    ).size()
    assets = tables["generation_asset_mentions"]
    without_names = assets["generation_asset_mention_id"].map(
        asset_names
    ).fillna(0).lt(1)
    _append_mask_issue(
        issues,
        table="generation_asset_mentions",
        rule="minimum_cardinality:generation_asset_names",
        columns=("generation_asset_mention_id",),
        dataframe=assets,
        mask=without_names,
        sample_columns=("event_id", "generation_asset_mention_id"),
    )


def _entity_lookup(
    dataframe: pd.DataFrame,
    *,
    id_column: str,
    local_column: str,
) -> dict[Any, tuple[Any, Any]]:
    lookup: dict[Any, tuple[Any, Any]] = {}
    for entity_id, event_id, local_ref in dataframe.loc[
        :, [id_column, "event_id", local_column]
    ].itertuples(index=False, name=None):
        if pd.notna(entity_id) and entity_id not in lookup:
            lookup[entity_id] = (event_id, local_ref)
    return lookup


def _validate_link_local_references(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    assets = _entity_lookup(
        tables["generation_asset_mentions"],
        id_column="generation_asset_mention_id",
        local_column="local_generation_asset_ref",
    )
    links = tables["associated_component_generation_links"].reset_index(
        drop=True
    )
    mismatch: list[bool] = []
    for row in links.itertuples(index=False):
        parent = assets.get(row.generation_asset_mention_id)
        mismatch.append(
            parent is not None
            and row.local_generation_asset_ref != parent[1]
        )
    _append_mask_issue(
        issues,
        table="associated_component_generation_links",
        rule="local_global_reference",
        columns=(
            "local_generation_asset_ref",
            "generation_asset_mention_id",
        ),
        dataframe=links,
        mask=mismatch,
        sample_columns=(
            "event_id",
            "local_generation_asset_ref",
            "generation_asset_mention_id",
        ),
    )


def _polymorphic_relations_by_value(
    table_name: str,
) -> dict[str, Any]:
    return {
        relation.discriminator_value: relation
        for relation in FLAT_TABLE_SPECS[table_name].polymorphic_relations
    }


def _validate_action_targets(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    table_name = "administrative_action_targets"
    targets = tables[table_name].reset_index(drop=True)
    relations = _polymorphic_relations_by_value(table_name)
    valid_kinds = set(relations)
    unknown = ~targets["target_kind"].isin(valid_kinds)
    _append_mask_issue(
        issues,
        table=table_name,
        rule="polymorphic_discriminator",
        columns=("target_kind",),
        dataframe=targets,
        mask=unknown,
        sample_columns=(
            "event_id",
            "administrative_action_id",
            "target_kind",
        ),
    )

    local_columns = {
        "generation_asset_mentions": "local_generation_asset_ref",
        "associated_components": "local_component_ref",
    }
    for kind, relation in relations.items():
        kind_mask = targets["target_kind"].eq(kind).fillna(False)
        target_table = tables[relation.target_table]
        parent_rows = target_table.drop_duplicates(
            relation.target_column,
            keep="first",
        ).set_index(relation.target_column)
        ids = targets[relation.source_column]
        exists = ids.isin(parent_rows.index)
        _append_mask_issue(
            issues,
            table=table_name,
            rule=f"polymorphic_target:{relation.target_table}",
            columns=("target_kind", relation.source_column),
            dataframe=targets,
            mask=kind_mask & ~exists,
            sample_columns=(
                "event_id",
                "target_kind",
                "target_ref",
                relation.source_column,
            ),
        )

        comparable = kind_mask & exists
        expected_event = (
            ids
            if relation.target_table == "publication_events"
            else ids.map(parent_rows["event_id"])
        )
        _append_mask_issue(
            issues,
            table=table_name,
            rule="polymorphic_target_event",
            columns=("event_id", relation.source_column),
            dataframe=targets,
            mask=comparable & targets["event_id"].ne(
                expected_event
            ).fillna(True),
            sample_columns=(
                "event_id",
                "target_kind",
                "target_ref",
                relation.source_column,
            ),
        )

        if relation.target_table == "publication_events":
            expected_ref = pd.Series("event", index=targets.index)
        else:
            local_column = local_columns[relation.target_table]
            expected_ref = ids.map(parent_rows[local_column])
        _append_mask_issue(
            issues,
            table=table_name,
            rule="polymorphic_target_reference",
            columns=(
                "target_kind",
                "target_ref",
                relation.source_column,
            ),
            dataframe=targets,
            mask=comparable & targets["target_ref"].ne(
                expected_ref
            ).fillna(True),
            sample_columns=(
                "event_id",
                "target_kind",
                "target_ref",
                relation.source_column,
            ),
        )


def _validate_technical_owners(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    table_name = "technical_mentions"
    technical = tables[table_name].reset_index(drop=True)
    relations = _polymorphic_relations_by_value(table_name)
    owner_columns = tuple(
        relation.source_column for relation in relations.values()
    )
    owner_count = technical.loc[:, list(owner_columns)].notna().sum(axis=1)
    _append_mask_issue(
        issues,
        table=table_name,
        rule="polymorphic_owner_exactly_one",
        columns=owner_columns,
        dataframe=technical,
        mask=owner_count.ne(1),
        sample_columns=(
            "event_id",
            "technical_mention_id",
            "owner_kind",
            *owner_columns,
        ),
    )

    valid_kinds = set(relations)
    _append_mask_issue(
        issues,
        table=table_name,
        rule="polymorphic_discriminator",
        columns=("owner_kind",),
        dataframe=technical,
        mask=~technical["owner_kind"].isin(valid_kinds),
        sample_columns=(
            "event_id",
            "technical_mention_id",
            "owner_kind",
        ),
    )

    local_columns = {
        "generation_asset_mentions": "local_generation_asset_ref",
        "associated_components": "local_component_ref",
    }
    for kind, relation in relations.items():
        other_columns = tuple(
            column for column in owner_columns
            if column != relation.source_column
        )
        kind_mask = technical["owner_kind"].eq(kind).fillna(False)
        shape_valid = (
            technical[relation.source_column].notna()
            & technical.loc[:, list(other_columns)].isna().all(axis=1)
        )
        _append_mask_issue(
            issues,
            table=table_name,
            rule="polymorphic_owner_kind",
            columns=("owner_kind", *owner_columns),
            dataframe=technical,
            mask=kind_mask & ~shape_valid,
            sample_columns=(
                "event_id",
                "technical_mention_id",
                "owner_kind",
                *owner_columns,
            ),
        )

        target = tables[relation.target_table]
        parent_rows = target.drop_duplicates(
            relation.target_column,
            keep="first",
        ).set_index(relation.target_column)
        ids = technical[relation.source_column]
        exists = ids.isin(parent_rows.index)
        comparable = kind_mask & shape_valid
        _append_mask_issue(
            issues,
            table=table_name,
            rule=f"polymorphic_owner:{relation.target_table}",
            columns=("owner_kind", relation.source_column),
            dataframe=technical,
            mask=comparable & ~exists,
            sample_columns=(
                "event_id",
                "technical_mention_id",
                "owner_kind",
                relation.source_column,
            ),
        )

        comparable &= exists
        expected_event = ids.map(parent_rows["event_id"])
        _append_mask_issue(
            issues,
            table=table_name,
            rule="polymorphic_owner_event",
            columns=("event_id", relation.source_column),
            dataframe=technical,
            mask=comparable & technical["event_id"].ne(
                expected_event
            ).fillna(True),
            sample_columns=(
                "event_id",
                "technical_mention_id",
                "owner_kind",
                relation.source_column,
            ),
        )

        local_column = local_columns[relation.target_table]
        expected_ref = ids.map(parent_rows[local_column])
        _append_mask_issue(
            issues,
            table=table_name,
            rule="polymorphic_owner_reference",
            columns=(
                "owner_kind",
                "owner_ref",
                relation.source_column,
            ),
            dataframe=technical,
            mask=comparable & technical["owner_ref"].ne(
                expected_ref
            ).fillna(True),
            sample_columns=(
                "event_id",
                "technical_mention_id",
                "owner_kind",
                "owner_ref",
                relation.source_column,
            ),
        )

    valid_owner = owner_count.eq(1)
    owner_ids = technical[owner_columns[0]].combine_first(
        technical[owner_columns[1]]
    )
    invalid_ids = pd.Series(False, index=technical.index)
    grouped = technical.assign(_owner_id=owner_ids).loc[valid_owner].groupby(
        "_owner_id",
        sort=False,
        dropna=False,
    )
    for owner_id, group in grouped:
        expected_ids = {
            f"{owner_id}_technical_{index}"
            for index in range(1, len(group) + 1)
        }
        actual_ids = (
            group["technical_mention_id"].dropna().astype(str).tolist()
        )
        if len(actual_ids) != len(group) or set(actual_ids) != expected_ids:
            invalid_ids.loc[group.index] = True
    _append_mask_issue(
        issues,
        table=table_name,
        rule="positional_identifier",
        columns=("technical_mention_id", *owner_columns),
        dataframe=technical,
        mask=invalid_ids,
        sample_columns=(
            "event_id",
            "technical_mention_id",
            "owner_kind",
            *owner_columns,
        ),
    )


def _validate_generation_relations(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    relations = tables["generation_asset_relations"].reset_index(drop=True)
    assets = _entity_lookup(
        tables["generation_asset_mentions"],
        id_column="generation_asset_mention_id",
        local_column="local_generation_asset_ref",
    )
    for side in ("source", "target"):
        id_column = f"{side}_generation_asset_mention_id"
        ref_column = f"{side}_generation_asset_ref"
        mismatch: list[bool] = []
        for row in relations.itertuples(index=False):
            entity = assets.get(getattr(row, id_column))
            mismatch.append(
                entity is not None
                and getattr(row, ref_column) != entity[1]
            )
        _append_mask_issue(
            issues,
            table="generation_asset_relations",
            rule="local_global_reference",
            columns=(ref_column, id_column),
            dataframe=relations,
            mask=mismatch,
            sample_columns=("event_id", ref_column, id_column),
        )

    self_relation = relations[
        "source_generation_asset_mention_id"
    ].eq(relations["target_generation_asset_mention_id"]) | relations[
        "source_generation_asset_ref"
    ].eq(relations["target_generation_asset_ref"])
    _append_mask_issue(
        issues,
        table="generation_asset_relations",
        rule="self_relation",
        columns=(
            "source_generation_asset_mention_id",
            "target_generation_asset_mention_id",
        ),
        dataframe=relations,
        mask=self_relation,
        sample_columns=(
            "event_id",
            "source_generation_asset_ref",
            "source_generation_asset_mention_id",
            "target_generation_asset_ref",
            "target_generation_asset_mention_id",
        ),
    )


_ENUM_DOMAINS: dict[tuple[str, str], type[Enum]] = {
    ("generation_asset_mentions", "generation_type"): GenerationType,
    ("associated_components", "component_type"): AssociatedComponentType,
    ("administrative_actions", "action_type"): AdministrativeActionType,
    ("administrative_actions", "decision"): AdministrativeDecision,
    ("participant_mentions", "participant_role"): ParticipantRole,
    ("location_mentions", "location_level"): AdministrativeLocationLevel,
    ("generation_asset_relations", "relation_type"): GenerationRelationType,
    ("technical_mentions", "attribute_type"): TechnicalAttributeType,
}


def _validate_domains(
    tables: Mapping[str, pd.DataFrame],
    issues: list[FlatTableValidationIssue],
) -> None:
    for (table_name, column_name), enum_type in _ENUM_DOMAINS.items():
        dataframe = tables[table_name]
        allowed = {item.value for item in enum_type}
        invalid = dataframe[column_name].notna() & ~dataframe[
            column_name
        ].isin(allowed)
        _append_mask_issue(
            issues,
            table=table_name,
            rule=f"controlled_domain:{enum_type.__name__}",
            columns=(column_name,),
            dataframe=dataframe,
            mask=invalid,
            sample_columns=("event_id", column_name),
        )

def validate_flat_tables(
    tables: Mapping[str, pd.DataFrame],
) -> None:
    """Valida forma, claves y relaciones de las 13 tablas sin modificarlas."""

    if not isinstance(tables, Mapping):
        raise FlatTableValidationError([
            FlatTableValidationIssue(
                table="<tables>",
                rule="not_a_mapping",
                columns=(),
                sample=(type(tables).__name__,),
            )
        ])

    structural_issues = _basic_contract_issues(tables)
    if structural_issues:
        raise FlatTableValidationError(structural_issues)

    issues: list[FlatTableValidationIssue] = []
    _validate_nullability(tables, issues)
    _validate_primary_keys(tables, issues)
    _validate_event_context(tables, issues)
    _validate_declared_foreign_keys(tables, issues)
    _validate_positions_and_identifiers(tables, issues)
    _validate_event_counts(tables, issues)
    _validate_link_local_references(tables, issues)
    _validate_action_targets(tables, issues)
    _validate_technical_owners(tables, issues)
    _validate_generation_relations(tables, issues)
    _validate_domains(tables, issues)

    if issues:
        raise FlatTableValidationError(issues)
