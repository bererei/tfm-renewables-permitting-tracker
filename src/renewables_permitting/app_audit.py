"""Pure, read-only audit queries over a validated GoldDataset."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from renewables_permitting.app_data import (
    GOLD_TABLE_SPECS,
    GoldDataset,
    GoldTableSpec,
)
from renewables_permitting.app_queries import (
    build_boe_url,
    build_project_catalog,
)
from renewables_permitting.utils import normalize_text


class AuditDataError(ValueError):
    """Validated Gold data cannot be represented by an audit query."""


@dataclass(frozen=True)
class TableQualitySummary:
    """Immutable basic quality observations for one already validated table."""

    row_count: int
    column_count: int
    duplicate_primary_key_rows: int
    null_counts: tuple[tuple[str, int], ...]
    observed_domains: tuple[tuple[str, tuple[str, ...]], ...]
    date_ranges: tuple[
        tuple[str, pd.Timestamp | None, pd.Timestamp | None], ...
    ]
    warnings: tuple[str, ...]


TERRITORIAL_TRACE_COLUMNS = (
    "project_id",
    "project_name",
    "project_location_id",
    "location_level",
    "municipality",
    "ine_municipality_code",
    "province",
    "ine_province_code",
    "autonomous_community",
    "ine_autonomous_community_code",
    "location_mention_id",
    "event_id",
    "boe_id",
    "publication_date",
    "boe_url",
)


def _selected(values: Iterable[object] | None) -> tuple[str, ...]:
    """Normalize an optional audit selection without changing its OR semantics."""

    return tuple(str(value) for value in (values or ()))


def _normalized_contains(values: pd.Series, text: str) -> pd.Series:
    """Return a null-safe normalized substring mask."""

    needle = normalize_text(text)
    if not needle:
        return pd.Series(True, index=values.index, dtype="boolean")
    normalized = values.fillna("").astype("string").map(normalize_text)
    return normalized.str.contains(needle, regex=False).fillna(False)


def _filter_selection(
    frame: pd.DataFrame,
    column: str,
    values: Iterable[object] | None,
) -> pd.DataFrame:
    """Apply OR within one selected column and return the remaining rows."""

    selected = _selected(values)
    if not selected:
        return frame
    return frame[frame[column].astype("string").isin(selected)]


def _filter_dates(
    frame: pd.DataFrame,
    column: str,
    *,
    start_date: date | datetime | pd.Timestamp | None,
    end_date: date | datetime | pd.Timestamp | None,
) -> pd.DataFrame:
    """Apply an inclusive audit date interval to one date column."""

    if start_date is not None:
        frame = frame[frame[column].ge(pd.Timestamp(start_date))]
    if end_date is not None:
        frame = frame[frame[column].le(pd.Timestamp(end_date))]
    return frame


def _ordered_copy(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Return a stable, deterministic copy without mutating Gold inputs."""

    return frame.sort_values(
        list(columns),
        kind="stable",
        na_position="last",
    ).reset_index(drop=True).copy()


def _spec(table_name: str) -> GoldTableSpec:
    """Return declared metadata or fail explicitly for an unknown table."""

    try:
        return GOLD_TABLE_SPECS[table_name]
    except KeyError as error:
        raise AuditDataError(
            f"La tabla Gold {table_name!r} no está disponible para auditoría."
        ) from error


def get_audit_table(dataset: GoldDataset, table_name: str) -> pd.DataFrame:
    """Return a checked copy of one canonical table from the loaded dataset."""

    spec = _spec(table_name)
    frame = getattr(dataset, table_name, None)
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != spec.columns:
        raise AuditDataError(
            f"La tabla Gold {table_name!r} no contiene sus columnas contractuales."
        )
    return frame.copy()


def build_schema_summary(
    dataset: GoldDataset,
    table_name: str,
) -> pd.DataFrame:
    """Describe observed schema, nulls, cardinality and contractual column roles."""

    spec = _spec(table_name)
    frame = get_audit_table(dataset, table_name)
    records: list[dict[str, object]] = []
    for column in spec.columns:
        roles: list[str] = []
        if column in spec.primary_key:
            roles.append("PK")
        if any(column in relationship.columns for relationship in spec.relationships):
            roles.append("FK")
        records.append({
            "column": column,
            "dtype": str(frame[column].dtype),
            "observed_nullable": bool(frame[column].isna().any()),
            "null_count": int(frame[column].isna().sum()),
            "distinct_count": int(frame[column].nunique(dropna=True)),
            "contract_role": ", ".join(roles) or "attribute",
        })
    return pd.DataFrame.from_records(records)


def _observed_values(values: pd.Series) -> tuple[str, ...]:
    """Return non-null observed values once in deterministic display order."""

    unique = {str(value) for value in values.dropna().tolist()}
    return tuple(sorted(unique, key=lambda value: (normalize_text(value), value)))


def observed_filter_values(
    dataset: GoldDataset,
    table_name: str,
    column: str,
) -> tuple[str, ...]:
    """Return deterministic observed values for one declared filter column."""

    spec = _spec(table_name)
    if column not in spec.columns:
        raise AuditDataError(
            f"La columna {column!r} no pertenece a la tabla {table_name!r}."
        )
    return _observed_values(get_audit_table(dataset, table_name)[column])


def summarize_table_quality(
    dataset: GoldDataset,
    table_name: str,
) -> TableQualitySummary:
    """Summarize quality without repeating the loader's contractual validation."""

    spec = _spec(table_name)
    frame = get_audit_table(dataset, table_name)
    duplicate_rows = int(
        frame.duplicated(list(spec.primary_key), keep=False).sum()
    )
    warnings = (
        (f"Se observan {duplicate_rows} filas con PK duplicada.",)
        if duplicate_rows
        else ()
    )
    date_columns = tuple(
        column
        for column in spec.columns
        if spec.dtypes[column] == "datetime64[ns]"
    )
    return TableQualitySummary(
        row_count=len(frame),
        column_count=len(frame.columns),
        duplicate_primary_key_rows=duplicate_rows,
        null_counts=tuple(
            (column, int(frame[column].isna().sum()))
            for column in spec.columns
        ),
        observed_domains=tuple(
            (column, _observed_values(frame[column]))
            for column in spec.domain_columns
        ),
        date_ranges=tuple(
            (
                column,
                None if frame[column].dropna().empty else frame[column].min(),
                None if frame[column].dropna().empty else frame[column].max(),
            )
            for column in date_columns
        ),
        warnings=warnings,
    )


def filter_audit_projects(
    dataset: GoldDataset,
    *,
    text: str = "",
    technologies: Iterable[str] | None = None,
    first_publication_from: date | datetime | pd.Timestamp | None = None,
    last_publication_to: date | datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Filter canonical project rows for audit, preserving one row per project."""

    rows = get_audit_table(dataset, "projects")
    if normalize_text(text):
        mask = _normalized_contains(rows["project_id"], text) | _normalized_contains(
            rows["project_name"], text
        )
        rows = rows[mask]
    rows = _filter_selection(rows, "technology", technologies)
    if first_publication_from is not None:
        rows = rows[
            rows["first_publication_date"].ge(
                pd.Timestamp(first_publication_from)
            )
        ]
    if last_publication_to is not None:
        rows = rows[
            rows["last_publication_date"].le(pd.Timestamp(last_publication_to))
        ]
    return _ordered_copy(rows, ("project_id",))


def filter_audit_project_events(
    dataset: GoldDataset,
    *,
    project_ids: Iterable[str] | None = None,
    boe_ids: Iterable[str] | None = None,
    action_types: Iterable[str] | None = None,
    decisions: Iterable[str] | None = None,
    is_modification: bool | None = None,
    start_date: date | datetime | pd.Timestamp | None = None,
    end_date: date | datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Filter canonical project-event rows with OR within and AND across fields."""

    rows = get_audit_table(dataset, "project_events")
    for column, values in (
        ("project_id", project_ids),
        ("boe_id", boe_ids),
        ("action_type", action_types),
        ("decision", decisions),
    ):
        rows = _filter_selection(rows, column, values)
    if is_modification is not None:
        rows = rows[rows["is_modification"].eq(is_modification).fillna(False)]
    rows = _filter_dates(
        rows,
        "publication_date",
        start_date=start_date,
        end_date=end_date,
    )
    return _ordered_copy(
        rows,
        (
            "publication_date",
            "project_id",
            "event_index",
            "administrative_action_index",
            "administrative_action_id",
        ),
    )


def filter_audit_project_locations(
    dataset: GoldDataset,
    *,
    project_ids: Iterable[str] | None = None,
    location_levels: Iterable[str] | None = None,
    autonomous_communities: Iterable[str] | None = None,
    provinces: Iterable[str] | None = None,
    municipalities: Iterable[str] | None = None,
    ine_codes: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Filter canonical project-location rows without fabricating hierarchy."""

    rows = get_audit_table(dataset, "project_locations")
    for column, values in (
        ("project_id", project_ids),
        ("location_level", location_levels),
        ("autonomous_community", autonomous_communities),
        ("province", provinces),
        ("municipality", municipalities),
    ):
        rows = _filter_selection(rows, column, values)
    selected_codes = _selected(ine_codes)
    if selected_codes:
        code_columns = (
            "ine_municipality_code",
            "ine_province_code",
            "ine_autonomous_community_code",
        )
        rows = rows[
            rows.loc[:, list(code_columns)]
            .astype("string")
            .isin(selected_codes)
            .any(axis=1)
        ]
    return _ordered_copy(
        rows,
        ("project_id", "location_level", "project_location_id"),
    )


def filter_audit_project_location_sources(
    dataset: GoldDataset,
    *,
    location_ids: Iterable[str] | None = None,
    location_mention_ids: Iterable[str] | None = None,
    event_ids: Iterable[str] | None = None,
    boe_ids: Iterable[str] | None = None,
    start_date: date | datetime | pd.Timestamp | None = None,
    end_date: date | datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Filter canonical territorial-source rows while preserving source grain."""

    rows = get_audit_table(dataset, "project_location_sources")
    for column, values in (
        ("project_location_id", location_ids),
        ("location_mention_id", location_mention_ids),
        ("event_id", event_ids),
        ("boe_id", boe_ids),
    ):
        rows = _filter_selection(rows, column, values)
    rows = _filter_dates(
        rows,
        "publication_date",
        start_date=start_date,
        end_date=end_date,
    )
    return _ordered_copy(
        rows,
        (
            "publication_date",
            "boe_id",
            "event_id",
            "project_location_id",
            "location_mention_id",
        ),
    )


def build_project_summary(dataset: GoldDataset) -> pd.DataFrame:
    """Return the existing one-row-per-project derived catalogue for audit."""

    return build_project_catalog(dataset).copy()


def build_territorial_trace(dataset: GoldDataset) -> pd.DataFrame:
    """Build one audit row per territorial source without joining actions."""

    locations = get_audit_table(dataset, "project_locations")
    sources = get_audit_table(dataset, "project_location_sources")
    projects = get_audit_table(dataset, "projects").loc[
        :, ["project_id", "project_name"]
    ]
    # La fuente ya contiene event_id, BOE y fecha. No se une project_events
    # porque cada evento puede tener varias actuaciones y multiplicaría las
    # filas de trazabilidad sin aportar información territorial nueva.
    try:
        trace = sources.merge(
            locations,
            on="project_location_id",
            how="inner",
            validate="many_to_one",
        ).merge(
            projects,
            on="project_id",
            how="inner",
            validate="many_to_one",
        )
    except (KeyError, pd.errors.MergeError) as error:
        raise AuditDataError(
            "No se pudo construir la trazabilidad territorial validada."
        ) from error
    trace["boe_url"] = trace["boe_id"].astype(str).map(build_boe_url)
    return _ordered_copy(
        trace.loc[:, TERRITORIAL_TRACE_COLUMNS],
        (
            "project_id",
            "project_location_id",
            "publication_date",
            "location_mention_id",
        ),
    )


def filter_territorial_trace(
    dataset: GoldDataset,
    *,
    project_ids: Iterable[str] | None = None,
    location_levels: Iterable[str] | None = None,
    boe_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Filter the territorial derived view without changing its source grain."""

    rows = build_territorial_trace(dataset)
    for column, values in (
        ("project_id", project_ids),
        ("location_level", location_levels),
        ("boe_id", boe_ids),
    ):
        rows = _filter_selection(rows, column, values)
    return _ordered_copy(
        rows,
        (
            "project_id",
            "project_location_id",
            "publication_date",
            "location_mention_id",
        ),
    )
