from __future__ import annotations

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from renewables_permitting.app_audit import (
    AuditDataError,
    build_project_summary,
    build_schema_summary,
    build_territorial_trace,
    filter_audit_project_events,
    filter_audit_project_location_sources,
    filter_audit_project_locations,
    filter_audit_projects,
    get_audit_table,
    summarize_table_quality,
)
from renewables_permitting.app_data import (
    GOLD_TABLE_SPECS,
    GoldDataset,
)
from test_app_queries import synthetic_dataset


EXPECTED_TABLES = (
    "projects",
    "project_events",
    "project_locations",
    "project_location_sources",
)


def _dataset_with_tables(
    dataset: GoldDataset,
    **changes: pd.DataFrame,
) -> GoldDataset:
    values = {
        name: changes.get(name, getattr(dataset, name))
        for name in EXPECTED_TABLES
    }
    return GoldDataset(
        **values,
        manifest=dataset.manifest,
        gold_dir=dataset.gold_dir,
        downstream_id=dataset.downstream_id,
    )


def test_gold_table_specs_are_complete_immutable_and_descriptive() -> None:
    assert tuple(GOLD_TABLE_SPECS) == EXPECTED_TABLES
    assert GOLD_TABLE_SPECS["projects"].primary_key == ("project_id",)
    assert GOLD_TABLE_SPECS["project_events"].primary_key == (
        "project_id",
        "administrative_action_id",
    )
    assert GOLD_TABLE_SPECS["project_locations"].granularity == (
        "una fila por asociación canónica project_id × territorio"
    )
    assert GOLD_TABLE_SPECS["project_location_sources"].primary_key == (
        "project_location_id",
        "location_mention_id",
    )
    assert GOLD_TABLE_SPECS["project_location_sources"].relationships
    with pytest.raises(TypeError):
        GOLD_TABLE_SPECS["other"] = GOLD_TABLE_SPECS["projects"]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        GOLD_TABLE_SPECS["projects"].name = "other"  # type: ignore[misc]


def test_schema_summary_reports_dtype_nulls_distinct_values_and_roles() -> None:
    dataset = synthetic_dataset()

    summary = build_schema_summary(dataset, "project_locations")

    assert summary["column"].tolist() == list(
        GOLD_TABLE_SPECS["project_locations"].columns
    )
    project_id = summary.loc[summary["column"] == "project_id"].iloc[0]
    assert project_id["dtype"] == "string"
    assert project_id["contract_role"] == "FK"
    municipality = summary.loc[summary["column"] == "municipality"].iloc[0]
    assert bool(municipality["observed_nullable"])
    assert municipality["null_count"] == 2
    assert municipality["distinct_count"] > 0


def test_quality_summary_reports_pk_domains_dates_and_nulls() -> None:
    summary = summarize_table_quality(synthetic_dataset(), "project_events")

    assert summary.row_count == 8
    assert summary.column_count == 11
    assert summary.duplicate_primary_key_rows == 0
    assert dict(summary.null_counts)["project_id"] == 0
    domains = dict(summary.observed_domains)
    assert "autorizado" in domains["decision"]
    dates = {
        column: (minimum, maximum)
        for column, minimum, maximum in summary.date_ranges
    }
    assert dates["publication_date"] == (
        pd.Timestamp("2023-01-10"),
        pd.Timestamp("2025-02-10"),
    )


def test_filter_audit_projects_uses_normalized_text_or_and_inclusive_dates() -> None:
    result = filter_audit_projects(
        synthetic_dataset(),
        text="fv andevalo",
        technologies=("fotovoltaica", "eolica"),
        first_publication_from=pd.Timestamp("2024-04-10"),
        last_publication_to=pd.Timestamp("2024-04-10"),
    )

    assert result["project_id"].tolist() == ["project_andevalo"]


def test_filter_audit_events_supports_or_and_same_row_constraints() -> None:
    dataset = synthetic_dataset()

    or_result = filter_audit_project_events(
        dataset,
        project_ids=("project_badulaque", "project_volateo"),
        decisions=("desfavorable",),
    )
    impossible = filter_audit_project_events(
        dataset,
        action_types=("autorizacion_administrativa_previa",),
        decisions=("desfavorable",),
    )

    assert set(or_result["project_id"].astype(str)) == {
        "project_badulaque",
        "project_volateo",
    }
    assert len(or_result) == 2
    assert impossible.empty


def test_filter_audit_events_uses_inclusive_dates_and_modification() -> None:
    dataset = synthetic_dataset()
    events = dataset.project_events.copy()
    events.loc[events["project_id"] == "project_puebla", "is_modification"] = True
    changed = _dataset_with_tables(dataset, project_events=events)

    result = filter_audit_project_events(
        changed,
        is_modification=True,
        start_date=pd.Timestamp("2024-03-10"),
        end_date=pd.Timestamp("2024-03-10"),
    )

    assert result["project_id"].tolist() == ["project_puebla"]


def test_filter_audit_locations_preserves_contractual_levels() -> None:
    dataset = synthetic_dataset()

    province_only = filter_audit_project_locations(
        dataset,
        location_levels=("province",),
        provinces=("Zaragoza",),
        ine_codes=("50",),
    )
    community_only = filter_audit_project_locations(
        dataset,
        location_levels=("autonomous_community",),
        autonomous_communities=("Canarias",),
    )

    assert province_only["project_id"].tolist() == ["project_angostillos"]
    assert province_only["municipality"].isna().all()
    assert community_only["project_id"].tolist() == ["project_insular"]
    assert community_only["province"].isna().all()


def test_filter_audit_location_sources_combines_categories_with_and() -> None:
    dataset = synthetic_dataset()
    source = dataset.project_location_sources.iloc[0]

    result = filter_audit_project_location_sources(
        dataset,
        location_ids=(str(source["project_location_id"]), "missing"),
        event_ids=(str(source["event_id"]),),
        boe_ids=(str(source["boe_id"]),),
        start_date=pd.Timestamp(source["publication_date"]),
        end_date=pd.Timestamp(source["publication_date"]),
    )

    assert len(result) == 1
    assert result.iloc[0]["location_mention_id"] == source["location_mention_id"]


def test_audit_queries_do_not_mutate_inputs_and_order_deterministically() -> None:
    dataset = synthetic_dataset()
    originals = {
        name: getattr(dataset, name).copy(deep=True)
        for name in EXPECTED_TABLES
    }
    shuffled = _dataset_with_tables(
        dataset,
        **{
            name: frame.sample(frac=1, random_state=13).reset_index(drop=True)
            for name, frame in originals.items()
        },
    )

    for function in (
        filter_audit_projects,
        filter_audit_project_events,
        filter_audit_project_locations,
        filter_audit_project_location_sources,
    ):
        expected = function(dataset)
        actual = function(shuffled)
        pd.testing.assert_frame_equal(actual, expected)

    build_schema_summary(dataset, "projects")
    summarize_table_quality(dataset, "projects")
    build_project_summary(dataset)
    build_territorial_trace(dataset)
    for name, original in originals.items():
        pd.testing.assert_frame_equal(getattr(dataset, name), original)


def test_project_summary_is_derived_and_has_one_row_per_project() -> None:
    summary = build_project_summary(synthetic_dataset())

    assert summary["project_id"].is_unique
    assert len(summary) == len(synthetic_dataset().projects)
    assert "territorial_summary" in summary


def test_territorial_trace_has_source_granularity_and_valid_boe_urls() -> None:
    dataset = synthetic_dataset()

    trace = build_territorial_trace(dataset)

    assert len(trace) == len(dataset.project_location_sources)
    assert not trace.duplicated(
        ["project_location_id", "location_mention_id"]
    ).any()
    assert trace["project_id"].notna().all()
    assert trace["project_name"].notna().all()
    assert trace["boe_url"].str.startswith(
        "https://www.boe.es/diario_boe/txt.php?id="
    ).all()


def test_territorial_trace_does_not_multiply_rows_by_project_actions() -> None:
    dataset = synthetic_dataset()
    events = pd.concat(
        [dataset.project_events, dataset.project_events.iloc[[0]]],
        ignore_index=True,
    )
    events.loc[len(events) - 1, "administrative_action_id"] = "another_action"
    changed = _dataset_with_tables(dataset, project_events=events)

    trace = build_territorial_trace(changed)

    assert len(trace) == len(dataset.project_location_sources)


def test_empty_filters_keep_schema_and_unknown_table_is_explicit() -> None:
    result = filter_audit_projects(synthetic_dataset(), text="does-not-exist")

    assert result.empty
    assert tuple(result.columns) == GOLD_TABLE_SPECS["projects"].columns
    with pytest.raises(AuditDataError, match="tabla"):
        get_audit_table(synthetic_dataset(), "unknown")
