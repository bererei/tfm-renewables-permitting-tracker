from datetime import date
from inspect import signature
from pathlib import Path

import pandas as pd
import pytest

import renewables_permitting.extraction.flatten as flatten_module
from renewables_permitting.extraction.flatten import (
    FLAT_TABLE_COLUMNS,
    flatten_current_extractions,
    save_flattened_extractions,
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
from renewables_permitting.extraction.persistence import (
    save_parquet_atomic as real_save_parquet_atomic,
)


TABLE_PATH_ATTRIBUTES = [
    ("publication_events", "PUBLICATION_EVENTS_PATH"),
    ("generation_asset_mentions", "GENERATION_ASSET_MENTIONS_PATH"),
    ("generation_asset_names", "GENERATION_ASSET_NAMES_PATH"),
    ("associated_components", "ASSOCIATED_COMPONENTS_PATH"),
    ("associated_component_names", "ASSOCIATED_COMPONENT_NAMES_PATH"),
    (
        "associated_component_generation_links",
        "ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH",
    ),
    ("administrative_actions", "ADMINISTRATIVE_ACTIONS_PATH"),
    (
        "administrative_action_targets",
        "ADMINISTRATIVE_ACTION_TARGETS_PATH",
    ),
    ("participant_mentions", "PARTICIPANT_MENTIONS_PATH"),
    ("location_mentions", "LOCATION_MENTIONS_PATH"),
    ("generation_asset_relations", "GENERATION_RELATIONS_PATH"),
    ("technical_mentions", "TECHNICAL_MENTIONS_PATH"),
    ("case_file_references", "CASE_FILE_REFERENCES_PATH"),
]


@pytest.fixture
def flat_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for position, (table_name, attribute_name) in enumerate(
        TABLE_PATH_ATTRIBUTES,
        start=1,
    ):
        path = (
            tmp_path
            / f"group_{position:02d}"
            / f"{table_name}.parquet"
        )
        monkeypatch.setattr(flatten_module, attribute_name, path)
        paths[table_name] = path
    return paths


def _tables(
    *,
    empty_names: set[str] | None = None,
) -> dict[str, pd.DataFrame]:
    empty_names = empty_names or set()
    tables: dict[str, pd.DataFrame] = {}
    for table_position, (table_name, columns) in enumerate(
        FLAT_TABLE_COLUMNS.items(),
        start=1,
    ):
        if table_name in empty_names:
            tables[table_name] = pd.DataFrame(columns=columns)
            continue
        records = [
            {
                column: (
                    f"{table_position:02d}-{row_position:02d}-{column}"
                )
                for column in columns
            }
            for row_position in (2, 1)
        ]
        tables[table_name] = pd.DataFrame(
            records,
            columns=columns,
            index=[20, 10],
        )
    return tables


def _rich_extraction() -> BOEProjectExtraction:
    title = (
        "Autorización de las plantas Aurora Solar y Brisa Eólica, "
        "su evacuación y su hibridación."
    )
    event = PublicationEvent(
        generation_assets=[
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Aurora Solar"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[TechnicalMention(
                    attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                    value_raw="50 MW",
                    evidence=title,
                )],
                evidence=title,
            ),
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_2",
                names_raw=["Brisa Eólica"],
                generation_type=GenerationType.WIND,
                technical_mentions=[],
                evidence=title,
            ),
        ],
        associated_components=[AssociatedComponent(
            local_component_ref="component_1",
            component_type=AssociatedComponentType.EVACUATION_SYSTEM,
            names_raw=["SET Aurora"],
            description_raw="infraestructura de evacuación",
            related_generation_asset_refs=[
                "generation_asset_1",
                "generation_asset_2",
            ],
            technical_mentions=[TechnicalMention(
                attribute_type=TechnicalAttributeType.VOLTAGE,
                value_raw="220 kV",
                evidence=title,
            )],
            evidence=title,
        )],
        administrative_actions=[AdministrativeAction(
            action_type=(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
            ),
            decision=AdministrativeDecision.AUTHORIZED,
            is_modification=False,
            targets=["generation_asset_1", "component_1"],
            evidence=title,
        )],
        participants=[ParticipantMention(
            participant_name_raw="Renovables Aurora, SA",
            participant_role=ParticipantRole.HOLDER,
            evidence=title,
        )],
        administrative_locations=[AdministrativeLocationMention(
            location_name_raw="Villa Solar",
            location_level=AdministrativeLocationLevel.MUNICIPALITY,
            province_hint_raw="Provincia Solar",
            autonomous_community_hint_raw="Comunidad Solar",
            evidence=title,
        )],
        generation_relations=[GenerationAssetRelation(
            source_generation_asset_ref="generation_asset_1",
            target_generation_asset_ref="generation_asset_2",
            relation_type=GenerationRelationType.HYBRIDIZED_WITH,
            evidence=title,
        )],
        case_file_references=["PFot-123"],
        event_summary="Autorización conjunta de Aurora y Brisa.",
    )
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de generación.",
        publication_events=[event],
        extraction_notes=None,
        boe_id="BOE-A-2026-10001",
        publication_date=date(2026, 1, 2),
    )


def test_save_writes_all_tables_once_in_contract_order_and_replaces_files(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = _tables()
    snapshots = {
        name: dataframe.copy(deep=True)
        for name, dataframe in tables.items()
    }
    current_extractions = pd.DataFrame(
        {"extraction_json": ["not-used-by-mocked-flatten"]},
        index=[9],
    )
    input_snapshot = current_extractions.copy(deep=True)
    for path in flat_paths.values():
        real_save_parquet_atomic(
            pd.DataFrame({"obsolete": ["old"]}),
            path,
        )
    calls: list[tuple[str, Path]] = []

    def flatten_spy(dataframe: pd.DataFrame) -> dict[str, pd.DataFrame]:
        assert dataframe is current_extractions
        return tables

    def atomic_spy(dataframe: pd.DataFrame, path: Path) -> None:
        table_name = next(
            name for name, expected_path in flat_paths.items()
            if expected_path == path
        )
        assert dataframe is tables[table_name]
        calls.append((table_name, path))
        real_save_parquet_atomic(dataframe, path)

    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        flatten_spy,
    )
    monkeypatch.setattr(flatten_module, "save_parquet_atomic", atomic_spy)

    returned = save_flattened_extractions(current_extractions)

    assert returned is tables
    assert calls == [
        (table_name, flat_paths[table_name])
        for table_name in FLAT_TABLE_COLUMNS
    ]
    assert list(FLAT_TABLE_COLUMNS) == [
        table_name for table_name, _ in TABLE_PATH_ATTRIBUTES
    ]
    for table_name, expected in tables.items():
        path = flat_paths[table_name]
        assert path.is_file()
        assert path.parent.is_dir()
        persisted = pd.read_parquet(path)
        pd.testing.assert_frame_equal(
            persisted,
            expected.reset_index(drop=True),
        )
        assert persisted.columns.tolist() == FLAT_TABLE_COLUMNS[table_name]
        assert persisted.iloc[0].tolist() == expected.iloc[0].tolist()
        assert persisted.iloc[1].tolist() == expected.iloc[1].tolist()
        pd.testing.assert_frame_equal(expected, snapshots[table_name])
    pd.testing.assert_frame_equal(current_extractions, input_snapshot)
    assert list(next(iter(flat_paths.values())).parents[1].rglob("*.tmp")) == []


def test_save_writes_thirteen_empty_tables(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = _tables(empty_names=set(FLAT_TABLE_COLUMNS))
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    returned = save_flattened_extractions(pd.DataFrame())

    assert returned is tables
    assert len(returned) == 13
    for table_name, path in flat_paths.items():
        persisted = pd.read_parquet(path)
        assert persisted.empty
        assert persisted.columns.tolist() == FLAT_TABLE_COLUMNS[table_name]
    assert list(next(iter(flat_paths.values())).parents[1].rglob("*.tmp")) == []


def test_save_handles_mixed_empty_and_nonempty_tables(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty_names = set(list(FLAT_TABLE_COLUMNS)[::2])
    tables = _tables(empty_names=empty_names)
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    save_flattened_extractions(pd.DataFrame())

    for table_name, path in flat_paths.items():
        persisted = pd.read_parquet(path)
        assert persisted.empty is (table_name in empty_names)
        assert persisted.columns.tolist() == FLAT_TABLE_COLUMNS[table_name]


def test_missing_expected_table_is_not_validated_and_only_present_tables_write(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = _tables()
    missing_name = "technical_mentions"
    del tables[missing_name]
    calls: list[str] = []
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    def atomic_spy(dataframe: pd.DataFrame, path: Path) -> None:
        table_name = next(
            name for name, expected_path in flat_paths.items()
            if expected_path == path
        )
        calls.append(table_name)
        real_save_parquet_atomic(dataframe, path)

    monkeypatch.setattr(flatten_module, "save_parquet_atomic", atomic_spy)

    returned = save_flattened_extractions(pd.DataFrame())

    assert returned is tables
    assert calls == [
        name for name in FLAT_TABLE_COLUMNS if name != missing_name
    ]
    assert not flat_paths[missing_name].exists()


def test_unknown_table_key_raises_key_error_after_previous_writes(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = {
        "publication_events": _tables()["publication_events"],
        "unknown_table": pd.DataFrame({"value": ["unknown"]}),
        "generation_asset_mentions": _tables()[
            "generation_asset_mentions"
        ],
    }
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    with pytest.raises(KeyError) as exc_info:
        save_flattened_extractions(pd.DataFrame())

    assert exc_info.value.args == ("unknown_table",)
    assert flat_paths["publication_events"].is_file()
    assert not flat_paths["generation_asset_mentions"].exists()
    assert list(next(iter(flat_paths.values())).parents[1].rglob("*.tmp")) == []


def test_non_dataframe_is_forwarded_to_atomic_writer_and_original_error_propagates(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = {
        "publication_events": _tables()["publication_events"],
        "generation_asset_mentions": "not-a-dataframe",
    }
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    with pytest.raises(AttributeError) as exc_info:
        save_flattened_extractions(pd.DataFrame())

    assert str(exc_info.value) == (
        "'str' object has no attribute 'to_parquet'"
    )
    assert flat_paths["publication_events"].is_file()
    assert not flat_paths["generation_asset_mentions"].exists()
    assert not flat_paths["generation_asset_mentions"].with_suffix(
        ".parquet.tmp"
    ).exists()


def test_missing_and_additional_columns_are_not_validated(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = _tables()
    malformed = tables["publication_events"].drop(
        columns=["event_summary"]
    ).copy()
    malformed["additional_column"] = ["extra-1", "extra-2"]
    tables["publication_events"] = malformed
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    returned = save_flattened_extractions(pd.DataFrame())
    persisted = pd.read_parquet(flat_paths["publication_events"])

    assert returned["publication_events"].columns.tolist() == (
        malformed.columns.tolist()
    )
    assert persisted.columns.tolist() == malformed.columns.tolist()
    assert "event_summary" not in persisted.columns
    assert persisted["additional_column"].tolist() == [
        "extra-1",
        "extra-2",
    ]


def test_atomic_failure_stops_later_writes_without_global_rollback(
    flat_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = _tables()
    ordered_names = list(tables)
    failing_name = ordered_names[3]
    calls: list[str] = []
    original_error = RuntimeError("atomic write failed")
    monkeypatch.setattr(
        flatten_module,
        "flatten_current_extractions",
        lambda _: tables,
    )

    def failing_writer(dataframe: pd.DataFrame, path: Path) -> None:
        table_name = next(
            name for name, expected_path in flat_paths.items()
            if expected_path == path
        )
        calls.append(table_name)
        if table_name == failing_name:
            raise original_error
        real_save_parquet_atomic(dataframe, path)

    monkeypatch.setattr(
        flatten_module,
        "save_parquet_atomic",
        failing_writer,
    )

    with pytest.raises(RuntimeError) as exc_info:
        save_flattened_extractions(pd.DataFrame())

    assert exc_info.value is original_error
    assert calls == ordered_names[:4]
    for table_name in ordered_names[:3]:
        assert flat_paths[table_name].is_file()
    assert not flat_paths[failing_name].exists()
    assert not flat_paths[failing_name].with_suffix(
        ".parquet.tmp"
    ).exists()
    for table_name in ordered_names[4:]:
        assert not flat_paths[table_name].exists()


def test_direct_flattened_dictionary_is_not_an_accepted_input(
    flat_paths: dict[str, Path],
) -> None:
    tables = _tables()

    with pytest.raises(AttributeError) as exc_info:
        save_flattened_extractions(tables)  # type: ignore[arg-type]

    assert str(exc_info.value) == (
        "'dict' object has no attribute 'itertuples'"
    )
    assert not any(path.exists() for path in flat_paths.values())


def test_integration_flattens_then_writes_and_preserves_relationships(
    flat_paths: dict[str, Path],
) -> None:
    extraction = _rich_extraction()
    current_extractions = pd.DataFrame([{
        "attempt_id": "manual-or-auto",
        "extraction_json": extraction.model_dump_json(),
    }], index=[42])
    input_snapshot = current_extractions.copy(deep=True)
    expected = flatten_current_extractions(current_extractions)

    returned = save_flattened_extractions(current_extractions)

    assert list(returned) == list(FLAT_TABLE_COLUMNS)
    assert len(returned) == 13
    for table_name, expected_frame in expected.items():
        assert returned[table_name].columns.tolist() == (
            FLAT_TABLE_COLUMNS[table_name]
        )
        pd.testing.assert_frame_equal(
            returned[table_name],
            expected_frame,
        )
        persisted = pd.read_parquet(flat_paths[table_name])
        pd.testing.assert_frame_equal(
            persisted,
            expected_frame.reset_index(drop=True),
        )
        if not persisted.empty:
            assert set(persisted["identificador_boe"]) == {
                extraction.boe_id
            }

    event_id = f"{extraction.boe_id}_event_1"
    generation_mentions = returned["generation_asset_mentions"]
    assert generation_mentions["generation_asset_mention_id"].tolist() == [
        f"{event_id}_generation_asset_1",
        f"{event_id}_generation_asset_2",
    ]
    links = returned["associated_component_generation_links"]
    assert links["generation_asset_mention_id"].tolist() == [
        f"{event_id}_generation_asset_1",
        f"{event_id}_generation_asset_2",
    ]
    action_targets = returned["administrative_action_targets"]
    assert action_targets["target_entity_id"].tolist() == [
        f"{event_id}_generation_asset_1",
        f"{event_id}_component_1",
    ]
    relations = returned["generation_asset_relations"]
    assert relations.iloc[0]["source_generation_asset_mention_id"] == (
        f"{event_id}_generation_asset_1"
    )
    assert relations.iloc[0]["target_generation_asset_mention_id"] == (
        f"{event_id}_generation_asset_2"
    )
    pd.testing.assert_frame_equal(current_extractions, input_snapshot)
    assert list(next(iter(flat_paths.values())).parents[1].rglob("*.tmp")) == []


def test_save_flattened_extractions_has_stable_public_signature() -> None:
    assert tuple(signature(save_flattened_extractions).parameters) == (
        "current_extractions",
    )


def test_flat_table_key_and_path_order_is_exact() -> None:
    assert list(FLAT_TABLE_COLUMNS) == [
        "publication_events",
        "generation_asset_mentions",
        "generation_asset_names",
        "associated_components",
        "associated_component_names",
        "associated_component_generation_links",
        "administrative_actions",
        "administrative_action_targets",
        "participant_mentions",
        "location_mentions",
        "generation_asset_relations",
        "technical_mentions",
        "case_file_references",
    ]
    assert len(FLAT_TABLE_COLUMNS) == 13
    assert "generation_relations" not in FLAT_TABLE_COLUMNS
