import json
from datetime import date
from hashlib import sha256
from inspect import signature
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

import renewables_permitting.extraction.flat_materialization as materialization
from renewables_permitting.extraction.flat_contract import (
    FLAT_CONTRACT_VERSION,
    FLAT_TABLE_SPECS,
    FlatTableSpec,
)
from renewables_permitting.extraction.flat_materialization import (
    FlatMaterializationError,
    FlatMaterializationResult,
    materialize_current_extractions,
    materialize_flat_tables,
)
from renewables_permitting.extraction.flat_validation import (
    FlatTableValidationError,
    validate_flat_tables,
)
from renewables_permitting.extraction.flatten import (
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


def _relevant_extraction() -> BOEProjectExtraction:
    evidence = "Se autoriza Aurora Solar, Brisa Eólica y su evacuación."
    event = PublicationEvent(
        generation_assets=[
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Aurora Solar"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[TechnicalMention(
                    attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                    value_raw="50 MW",
                    evidence=evidence,
                )],
                evidence=evidence,
            ),
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_2",
                names_raw=["Brisa Eólica"],
                generation_type=GenerationType.WIND,
                technical_mentions=[],
                evidence=evidence,
            ),
        ],
        associated_components=[AssociatedComponent(
            local_component_ref="component_1",
            component_type=AssociatedComponentType.EVACUATION_SYSTEM,
            names_raw=["SET Aurora"],
            description_raw=None,
            related_generation_asset_refs=["generation_asset_1"],
            technical_mentions=[TechnicalMention(
                attribute_type=TechnicalAttributeType.VOLTAGE,
                value_raw="220 kV",
                evidence=evidence,
            )],
            evidence=evidence,
        )],
        administrative_actions=[
            AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                is_modification=False,
                targets=["event"],
                evidence=evidence,
            ),
            AdministrativeAction(
                action_type=AdministrativeActionType.PUBLIC_INFORMATION,
                decision=(
                    AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
                ),
                is_modification=False,
                targets=["generation_asset_1", "component_1"],
                evidence=evidence,
            ),
        ],
        participants=[ParticipantMention(
            participant_name_raw="Renovables Aurora, SA",
            participant_role=ParticipantRole.HOLDER,
            evidence=evidence,
        )],
        administrative_locations=[AdministrativeLocationMention(
            location_name_raw="Villa Solar",
            location_level=AdministrativeLocationLevel.MUNICIPALITY,
            province_hint_raw="Provincia Solar",
            autonomous_community_hint_raw=None,
            evidence=evidence,
        )],
        generation_relations=[GenerationAssetRelation(
            source_generation_asset_ref="generation_asset_1",
            target_generation_asset_ref="generation_asset_2",
            relation_type=GenerationRelationType.HYBRIDIZED_WITH,
            evidence=evidence,
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


def _non_relevant_extraction() -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS,
        classification_reason="Publicación no relevante.",
        publication_events=[],
        extraction_notes=None,
        boe_id="BOE-B-2026-20002",
        publication_date=date(2026, 1, 3),
    )


def _current_extractions() -> pd.DataFrame:
    relevant = _relevant_extraction()
    non_relevant = _non_relevant_extraction()
    return pd.DataFrame([
        {
            "attempt_id": "attempt-auto-1",
            "identificador_boe": relevant.boe_id,
            "source_document_sha256": "a" * 64,
            "extraction_config_id": "config-v1",
            "selection_source": "auto_validated",
            "extraction_json": relevant.model_dump_json(),
            "titulo": "Título que no debe entrar en el manifiesto",
            "reviewer": "persona-no-publicable",
            "absolute_path": "/home/example/private.parquet",
            "model_response": "respuesta completa no publicable",
        },
        {
            "attempt_id": "attempt-manual-2",
            "identificador_boe": non_relevant.boe_id,
            "source_document_sha256": "b" * 64,
            "extraction_config_id": "config-v1",
            "selection_source": "manually_validated",
            "extraction_json": non_relevant.model_dump_json(),
            "titulo": "Otro título no publicable",
            "reviewer": "otra-persona",
            "absolute_path": "/tmp/private.json",
            "model_response": "otra respuesta completa",
        },
    ])


def _direct_manifest_context(
    *,
    input_row_count: int = 2,
    input_with_events_count: int = 1,
    input_without_events_count: int = 1,
    lineage: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "input_row_count": input_row_count,
        "input_with_events_count": input_with_events_count,
        "input_without_events_count": input_without_events_count,
    }
    if lineage is not None:
        context["lineage"] = lineage
    return context


def _read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_materialized_tables(
    output_dir: Path,
) -> dict[str, pd.DataFrame]:
    return {
        table_name: pd.read_parquet(output_dir / table_spec.filename)
        for table_name, table_spec in FLAT_TABLE_SPECS.items()
    }


def _assert_no_staging(output_dir: Path) -> None:
    if output_dir.parent.exists():
        assert list(output_dir.parent.glob(
            f".{output_dir.name}.staging-*"
        )) == []


def _unrelated_sentinel(tmp_path: Path) -> Path:
    unrelated = tmp_path / ".other.staging-keep"
    unrelated.mkdir()
    sentinel = unrelated / "sentinel"
    sentinel.write_text("preservar", encoding="utf-8")
    return sentinel


def _assert_failure_cleanup(output_dir: Path, sentinel: Path) -> None:
    assert not output_dir.exists()
    assert sentinel.read_text(encoding="utf-8") == "preservar"
    _assert_no_staging(output_dir)


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_materialize_current_extractions_writes_complete_verified_version(
    tmp_path: Path,
) -> None:
    current = _current_extractions()
    snapshot = current.copy(deep=True)
    output_dir = tmp_path / "silver-v1"

    result = materialize_current_extractions(
        current,
        output_dir=output_dir,
    )

    assert isinstance(result, FlatMaterializationResult)
    assert result.output_dir == output_dir
    assert result.manifest_path == output_dir / "manifest.json"
    assert list(result.table_paths) == list(FLAT_TABLE_SPECS)
    assert set(path.name for path in output_dir.iterdir()) == {
        *(spec.filename for spec in FLAT_TABLE_SPECS.values()),
        "manifest.json",
    }
    assert all(path.is_file() for path in output_dir.iterdir())
    assert len(result.materialization_id) == 64
    assert dict(result.row_counts) == {
        name: len(table)
        for name, table in flatten_current_extractions(current).items()
    }
    validate_flat_tables(_read_materialized_tables(output_dir))
    pd.testing.assert_frame_equal(current, snapshot)
    _assert_no_staging(output_dir)


def test_parquet_names_schemas_counts_hashes_and_indices_follow_contract(
    tmp_path: Path,
) -> None:
    current = _current_extractions()
    result = materialize_current_extractions(
        current,
        output_dir=tmp_path / "schema-version",
    )
    manifest = _read_manifest(result.manifest_path)
    manifest_tables = {
        entry["table_name"]: entry
        for entry in manifest["tables"]
    }

    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        path = result.table_paths[table_name]
        assert path.name == table_spec.filename
        assert pq.read_schema(path).equals(
            table_spec.arrow_schema,
            check_metadata=False,
        )
        stored = pd.read_parquet(path)
        assert tuple(stored.columns) == table_spec.column_names
        assert isinstance(stored.index, pd.RangeIndex)
        assert "__index_level_0__" not in pq.read_table(path).column_names
        entry = manifest_tables[table_name]
        assert entry["filename"] == table_spec.filename
        assert entry["row_count"] == len(stored)
        assert entry["columns"] == list(table_spec.column_names)
        assert entry["primary_key"] == list(table_spec.primary_key)
        assert entry["sha256"] == _file_sha256(path)


def test_all_empty_typed_tables_materialize_with_physical_schemas(
    tmp_path: Path,
) -> None:
    tables = flatten_current_extractions(pd.DataFrame())

    result = materialize_flat_tables(
        tables,
        output_dir=tmp_path / "empty-version",
        manifest_context=_direct_manifest_context(
            input_row_count=0,
            input_with_events_count=0,
            input_without_events_count=0,
            lineage=[],
        ),
    )

    assert all(count == 0 for count in result.row_counts.values())
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        stored = pd.read_parquet(result.table_paths[table_name])
        assert stored.empty
        assert tuple(stored.columns) == table_spec.column_names
        assert pq.read_schema(result.table_paths[table_name]).equals(
            table_spec.arrow_schema,
            check_metadata=False,
        )
    manifest = _read_manifest(result.manifest_path)
    assert manifest["input_row_count"] == 0
    assert manifest["materialized_event_count"] == 0


def test_manifest_counts_lineage_and_relative_paths_are_safe(
    tmp_path: Path,
) -> None:
    result = materialize_current_extractions(
        _current_extractions(),
        output_dir=tmp_path / "manifest-version",
    )

    manifest = _read_manifest(result.manifest_path)
    assert manifest["flat_contract_version"] == FLAT_CONTRACT_VERSION
    assert manifest["input_row_count"] == 2
    assert manifest["input_with_events_count"] == 1
    assert manifest["input_without_events_count"] == 1
    assert manifest["materialized_event_count"] == 1
    assert manifest["table_count"] == 13
    assert manifest["materialization_id"] == result.materialization_id
    assert manifest["lineage"]["columns"] == [
        "identificador_boe",
        "attempt_id",
        "source_document_sha256",
        "extraction_config_id",
        "selection_source",
    ]
    assert len(manifest["lineage"]["records"]) == 2
    assert all(
        not Path(entry["filename"]).is_absolute()
        for entry in manifest["tables"]
    )
    manifest_text = result.manifest_path.read_text(encoding="utf-8")
    for forbidden in (
        str(tmp_path),
        "Título que no debe entrar",
        "persona-no-publicable",
        "respuesta completa",
        "extraction_json",
        "absolute_path",
    ):
        assert forbidden not in manifest_text


@pytest.mark.parametrize("invalid_kind", ["missing_table", "missing_column"])
def test_invalid_structure_never_creates_output_or_staging(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    tables = flatten_current_extractions(_current_extractions())
    if invalid_kind == "missing_table":
        tables.pop("technical_mentions")
    else:
        tables["publication_events"] = tables[
            "publication_events"
        ].drop(columns=["event_summary"])
    output_dir = tmp_path / "invalid-structure"

    with pytest.raises(FlatTableValidationError):
        materialize_flat_tables(tables, output_dir=output_dir)

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


@pytest.mark.parametrize("invalid_kind", ["duplicate_pk", "orphan_fk"])
def test_invalid_relations_never_create_output_or_staging(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    tables = flatten_current_extractions(_current_extractions())
    if invalid_kind == "duplicate_pk":
        tables["publication_events"] = pd.concat([
            tables["publication_events"],
            tables["publication_events"].iloc[[0]],
        ], ignore_index=True)
    else:
        tables["generation_asset_names"].loc[
            0, "generation_asset_mention_id"
        ] = "missing-generation-asset"
    output_dir = tmp_path / "invalid-relations"

    with pytest.raises(FlatTableValidationError):
        materialize_flat_tables(tables, output_dir=output_dir)

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


@pytest.mark.parametrize(
    "destination_kind",
    ["file", "empty_directory", "nonempty_directory"],
)
def test_existing_output_is_rejected_without_modification(
    tmp_path: Path,
    destination_kind: str,
) -> None:
    output_dir = tmp_path / "existing"
    if destination_kind == "file":
        output_dir.write_text("preservar", encoding="utf-8")
    else:
        output_dir.mkdir()
        if destination_kind == "nonempty_directory":
            (output_dir / "sentinel.txt").write_text(
                "preservar",
                encoding="utf-8",
            )

    with pytest.raises(FileExistsError, match="ya existe"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    if destination_kind == "file":
        assert output_dir.read_text(encoding="utf-8") == "preservar"
    elif destination_kind == "empty_directory":
        assert output_dir.is_dir()
        assert list(output_dir.iterdir()) == []
    else:
        sentinel = output_dir / "sentinel.txt"
        assert list(output_dir.iterdir()) == [sentinel]
        assert sentinel.read_text(encoding="utf-8") == "preservar"
    _assert_no_staging(output_dir)


def test_materialization_creates_missing_parent_directories(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "new" / "nested" / "version"

    result = materialize_flat_tables(
        flatten_current_extractions(_current_extractions()),
        output_dir=output_dir,
        manifest_context=_direct_manifest_context(),
    )

    assert result.output_dir == output_dir
    assert output_dir.is_dir()
    assert result.manifest_path.is_file()


@pytest.mark.parametrize("failure_call", [1, 3])
def test_parquet_write_failure_cleans_only_own_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    output_dir = tmp_path / "write-failure"
    sentinel = _unrelated_sentinel(tmp_path)
    real_write = materialization.pq.write_table
    calls = 0

    def failing_write(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("fallo inyectado de escritura")
        real_write(*args, **kwargs)

    monkeypatch.setattr(materialization.pq, "write_table", failing_write)

    with pytest.raises(OSError, match="fallo inyectado"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    _assert_failure_cleanup(output_dir, sentinel)


def test_reload_failure_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "reload-failure"
    sentinel = _unrelated_sentinel(tmp_path)

    def failing_read(*args: object, **kwargs: object) -> object:
        raise OSError("fallo inyectado de relectura")

    monkeypatch.setattr(materialization.pq, "read_table", failing_read)

    with pytest.raises(OSError, match="fallo inyectado"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    _assert_failure_cleanup(output_dir, sentinel)


def test_post_write_validation_failure_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "validation-failure"
    sentinel = _unrelated_sentinel(tmp_path)
    real_validate = validate_flat_tables
    calls = 0

    def failing_second_validation(
        tables: dict[str, pd.DataFrame],
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fallo inyectado de validación posterior")
        real_validate(tables)

    monkeypatch.setattr(
        materialization,
        "validate_flat_tables",
        failing_second_validation,
    )

    with pytest.raises(RuntimeError, match="validación posterior"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    assert calls == 2
    _assert_failure_cleanup(output_dir, sentinel)


def test_manifest_write_failure_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "manifest-write-failure"
    sentinel = _unrelated_sentinel(tmp_path)
    real_write_text = Path.write_text

    def failing_manifest_write(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> int:
        if path.name == "manifest.json":
            raise OSError("fallo inyectado de escritura del manifiesto")
        return real_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_manifest_write)

    with pytest.raises(OSError, match="escritura del manifiesto"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    _assert_failure_cleanup(output_dir, sentinel)


def test_manifest_read_failure_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "manifest-read-failure"
    sentinel = _unrelated_sentinel(tmp_path)
    real_read_text = Path.read_text

    def failing_manifest_read(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> str:
        if path.name == "manifest.json":
            raise OSError("fallo inyectado de relectura del manifiesto")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_manifest_read)

    with pytest.raises(OSError, match="relectura del manifiesto"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    _assert_failure_cleanup(output_dir, sentinel)


def test_final_rename_failure_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "rename-failure"
    sentinel = _unrelated_sentinel(tmp_path)
    real_rename = Path.rename

    def failing_final_rename(path: Path, target: Path) -> Path:
        if path.name.startswith(f".{output_dir.name}.staging-"):
            raise OSError("fallo inyectado de rename final")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", failing_final_rename)

    with pytest.raises(OSError, match="rename final"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    _assert_failure_cleanup(output_dir, sentinel)


def test_semantic_change_after_write_is_detected_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "semantic-change"
    sentinel = _unrelated_sentinel(tmp_path)
    real_read = materialization._read_contract_parquet

    def altered_read(
        path: Path,
        table_spec: FlatTableSpec,
    ) -> pd.DataFrame:
        dataframe = real_read(path, table_spec)
        if table_spec.name == "publication_events":
            dataframe = dataframe.copy(deep=True)
            dataframe.loc[0, "event_summary"] = "Resumen alterado tras escribir."
        return dataframe

    monkeypatch.setattr(
        materialization,
        "_read_contract_parquet",
        altered_read,
    )

    with pytest.raises(FlatMaterializationError, match="semánticamente"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=_direct_manifest_context(),
        )

    _assert_failure_cleanup(output_dir, sentinel)


def test_same_input_has_same_id_and_semantically_equal_tables_across_paths(
    tmp_path: Path,
) -> None:
    current = _current_extractions()

    first = materialize_current_extractions(
        current,
        output_dir=tmp_path / "first",
    )
    second = materialize_current_extractions(
        current.iloc[::-1],
        output_dir=tmp_path / "different" / "second",
    )

    assert first.materialization_id == second.materialization_id
    first_tables = _read_materialized_tables(first.output_dir)
    second_tables = _read_materialized_tables(second.output_dir)
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        primary_key = list(table_spec.primary_key)
        pd.testing.assert_frame_equal(
            first_tables[table_name].sort_values(primary_key).reset_index(
                drop=True
            ),
            second_tables[table_name].sort_values(primary_key).reset_index(
                drop=True
            ),
        )


def test_different_extraction_or_selection_changes_materialization_id(
    tmp_path: Path,
) -> None:
    current = _current_extractions()
    baseline = materialize_current_extractions(
        current,
        output_dir=tmp_path / "baseline",
    )

    changed_selection = current.copy(deep=True)
    changed_selection.loc[0, "selection_source"] = "manually_validated"
    selection_result = materialize_current_extractions(
        changed_selection,
        output_dir=tmp_path / "changed-selection",
    )

    changed_extraction = current.copy(deep=True)
    payload = json.loads(changed_extraction.loc[0, "extraction_json"])
    payload["publication_events"][0]["event_summary"] = "Resumen distinto."
    changed_extraction.loc[0, "extraction_json"] = json.dumps(payload)
    extraction_result = materialize_current_extractions(
        changed_extraction,
        output_dir=tmp_path / "changed-extraction",
    )

    assert selection_result.materialization_id != baseline.materialization_id
    assert extraction_result.materialization_id != baseline.materialization_id


def test_shuffled_rows_and_custom_pandas_indices_preserve_semantic_identity(
    tmp_path: Path,
) -> None:
    tables = flatten_current_extractions(_current_extractions())
    shuffled: dict[str, pd.DataFrame] = {}
    for position, (table_name, dataframe) in enumerate(tables.items()):
        candidate = dataframe.sample(frac=1, random_state=position)
        candidate.index = pd.Index(
            range(1000, 1000 + len(candidate)),
            name="non_contract_index",
        )
        shuffled[table_name] = candidate

    first = materialize_flat_tables(
        tables,
        output_dir=tmp_path / "ordered",
        manifest_context=_direct_manifest_context(),
    )
    second = materialize_flat_tables(
        shuffled,
        output_dir=tmp_path / "shuffled",
        manifest_context=_direct_manifest_context(),
    )

    assert first.materialization_id == second.materialization_id
    for table_name in FLAT_TABLE_SPECS:
        ordered_stored = pd.read_parquet(first.table_paths[table_name])
        shuffled_stored = pd.read_parquet(second.table_paths[table_name])
        pd.testing.assert_frame_equal(ordered_stored, shuffled_stored)
        assert isinstance(shuffled_stored.index, pd.RangeIndex)
    validate_flat_tables(_read_materialized_tables(second.output_dir))


def test_direct_context_counts_contribute_to_materialization_id(
    tmp_path: Path,
) -> None:
    tables = flatten_current_extractions(pd.DataFrame())

    one_input = materialize_flat_tables(
        tables,
        output_dir=tmp_path / "one-input",
        manifest_context={
            "input_row_count": 1,
            "input_with_events_count": 0,
            "input_without_events_count": 1,
        },
    )
    two_inputs = materialize_flat_tables(
        tables,
        output_dir=tmp_path / "two-inputs",
        manifest_context={
            "input_row_count": 2,
            "input_with_events_count": 0,
            "input_without_events_count": 2,
        },
    )

    assert one_input.materialization_id != two_inputs.materialization_id


@pytest.mark.parametrize(
    "manifest_context",
    [
        None,
        {},
        {
            "input_with_events_count": 0,
            "input_without_events_count": 0,
        },
        {
            "input_row_count": 0,
            "input_without_events_count": 0,
        },
        {
            "input_row_count": 0,
            "input_with_events_count": 0,
        },
    ],
)
def test_direct_api_requires_all_document_counts(
    tmp_path: Path,
    manifest_context: dict[str, object] | None,
) -> None:
    output_dir = tmp_path / "missing-counts"

    with pytest.raises(FlatMaterializationError, match="conteo|conteos"):
        materialize_flat_tables(
            flatten_current_extractions(pd.DataFrame()),
            output_dir=output_dir,
            manifest_context=manifest_context,
        )

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


@pytest.mark.parametrize(
    "manifest_context",
    [
        _direct_manifest_context(
            input_row_count=2,
            input_with_events_count=1,
            input_without_events_count=0,
        ),
        _direct_manifest_context(
            input_row_count=-1,
            input_with_events_count=0,
            input_without_events_count=0,
        ),
    ],
)
def test_direct_api_rejects_inconsistent_document_counts(
    tmp_path: Path,
    manifest_context: dict[str, object],
) -> None:
    output_dir = tmp_path / "invalid-counts"

    with pytest.raises(FlatMaterializationError):
        materialize_flat_tables(
            flatten_current_extractions(pd.DataFrame()),
            output_dir=output_dir,
            manifest_context=manifest_context,
        )

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


@pytest.mark.parametrize(
    "manifest_context",
    [
        _direct_manifest_context(
            input_row_count=2,
            input_with_events_count=1,
            input_without_events_count=1,
            lineage=[{"attempt_id": "only-one"}],
        ),
        _direct_manifest_context(
            input_row_count=0,
            input_with_events_count=0,
            input_without_events_count=0,
            lineage=[{"attempt_id": "unexpected"}],
        ),
    ],
)
def test_direct_api_rejects_lineage_cardinality_mismatch(
    tmp_path: Path,
    manifest_context: dict[str, object],
) -> None:
    output_dir = tmp_path / "invalid-lineage"

    with pytest.raises(FlatMaterializationError, match="cardinalidad"):
        materialize_flat_tables(
            flatten_current_extractions(_current_extractions()),
            output_dir=output_dir,
            manifest_context=manifest_context,
        )

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


def test_direct_api_accepts_exact_counts_and_one_lineage_record_per_input(
    tmp_path: Path,
) -> None:
    context = _direct_manifest_context(
        lineage=[
            {"attempt_id": "attempt-2"},
            {"attempt_id": "attempt-1"},
        ],
    )

    result = materialize_flat_tables(
        flatten_current_extractions(_current_extractions()),
        output_dir=tmp_path / "exact-context",
        manifest_context=context,
    )

    manifest = _read_manifest(result.manifest_path)
    assert manifest["input_row_count"] == 2
    assert manifest["input_with_events_count"] == 1
    assert manifest["input_without_events_count"] == 1
    assert manifest["materialized_event_count"] == 1
    assert manifest["lineage"]["records"] == [
        {"attempt_id": "attempt-1"},
        {"attempt_id": "attempt-2"},
    ]


def test_lineage_only_uses_columns_that_are_actually_available(
    tmp_path: Path,
) -> None:
    current = pd.DataFrame([{
        "extraction_json": _non_relevant_extraction().model_dump_json(),
        "attempt_id": "only-available-lineage",
    }])

    result = materialize_current_extractions(
        current,
        output_dir=tmp_path / "limited-lineage",
    )

    lineage = _read_manifest(result.manifest_path)["lineage"]
    assert lineage["columns"] == ["attempt_id"]
    assert lineage["records"] == [{
        "attempt_id": "only-available-lineage",
    }]


def test_invalid_extraction_json_is_rejected_before_staging(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "invalid-json"
    current = pd.DataFrame({"extraction_json": ["{not-valid-json"]})

    with pytest.raises(ValueError):
        materialize_current_extractions(current, output_dir=output_dir)

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


def test_multiple_events_have_document_and_event_counts(
    tmp_path: Path,
) -> None:
    payload = _relevant_extraction().model_dump(mode="json")
    second_event = dict(payload["publication_events"][0])
    second_event["event_summary"] = "Segundo evento de la publicación."
    payload["publication_events"].append(second_event)
    extraction = BOEProjectExtraction.model_validate(payload)
    current = pd.DataFrame({
        "extraction_json": [extraction.model_dump_json()],
    })

    result = materialize_current_extractions(
        current,
        output_dir=tmp_path / "multiple-events",
    )

    manifest = _read_manifest(result.manifest_path)
    assert manifest["input_row_count"] == 1
    assert manifest["input_with_events_count"] == 1
    assert manifest["input_without_events_count"] == 0
    assert manifest["materialized_event_count"] == 2


def test_uncertain_classification_without_events_is_counted(
    tmp_path: Path,
) -> None:
    extraction = BOEProjectExtraction(
        classification_status=ClassificationStatus.UNCERTAIN,
        document_scope=None,
        classification_reason="Clasificación pendiente de revisión.",
        publication_events=[],
        extraction_notes=None,
        boe_id="BOE-A-2026-30003",
        publication_date=date(2026, 1, 4),
    )
    current = pd.DataFrame({
        "extraction_json": [extraction.model_dump_json()],
    })

    result = materialize_current_extractions(
        current,
        output_dir=tmp_path / "uncertain",
    )

    manifest = _read_manifest(result.manifest_path)
    assert manifest["input_row_count"] == 1
    assert manifest["input_with_events_count"] == 0
    assert manifest["input_without_events_count"] == 1
    assert manifest["materialized_event_count"] == 0


@pytest.mark.parametrize("with_events", [True, False])
def test_duplicate_canonical_boe_is_rejected_even_without_events(
    tmp_path: Path,
    with_events: bool,
) -> None:
    extraction = (
        _relevant_extraction()
        if with_events
        else _non_relevant_extraction()
    )
    current = pd.DataFrame({
        "extraction_json": [
            extraction.model_dump_json(),
            extraction.model_dump_json(),
        ],
    })
    output_dir = tmp_path / "duplicate-boe"

    with pytest.raises(FlatMaterializationError, match="duplicados"):
        materialize_current_extractions(current, output_dir=output_dir)

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


@pytest.mark.parametrize(
    "row_boe_id",
    ["BOE-A-2026-99999", pd.NA],
)
def test_row_boe_must_match_canonical_json_boe(
    tmp_path: Path,
    row_boe_id: object,
) -> None:
    extraction = _relevant_extraction()
    current = pd.DataFrame([{
        "identificador_boe": row_boe_id,
        "extraction_json": extraction.model_dump_json(),
    }])
    output_dir = tmp_path / "inconsistent-boe"

    with pytest.raises(FlatMaterializationError, match="BOE canónico"):
        materialize_current_extractions(current, output_dir=output_dir)

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


def test_missing_optional_row_boe_uses_canonical_json_boe(
    tmp_path: Path,
) -> None:
    extraction = _relevant_extraction()
    current = pd.DataFrame([{
        "attempt_id": "without-row-boe",
        "extraction_json": extraction.model_dump_json(),
    }])

    result = materialize_current_extractions(
        current,
        output_dir=tmp_path / "canonical-boe",
    )

    events = pd.read_parquet(result.table_paths["publication_events"])
    assert events["identificador_boe"].tolist() == [extraction.boe_id]
    lineage = _read_manifest(result.manifest_path)["lineage"]
    assert lineage["columns"] == ["attempt_id"]


def test_physical_parquet_hashes_do_not_contribute_to_materialization_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def simulated_file_hash(path: Path) -> str:
        is_first = any("first-binary" in part for part in path.parts)
        return "a" * 64 if is_first else "b" * 64

    monkeypatch.setattr(materialization, "_sha256_file", simulated_file_hash)
    current = _current_extractions()

    first = materialize_current_extractions(
        current,
        output_dir=tmp_path / "first-binary",
    )
    second = materialize_current_extractions(
        current,
        output_dir=tmp_path / "second-binary",
    )

    assert first.materialization_id == second.materialization_id
    first_hashes = {
        entry["sha256"]
        for entry in _read_manifest(first.manifest_path)["tables"]
    }
    second_hashes = {
        entry["sha256"]
        for entry in _read_manifest(second.manifest_path)["tables"]
    }
    assert first_hashes == {"a" * 64}
    assert second_hashes == {"b" * 64}


@pytest.mark.parametrize(
    "current_extractions",
    [
        "not-a-dataframe",
        pd.DataFrame({"other": ["value"]}),
    ],
)
def test_current_api_rejects_missing_minimum_input_before_writing(
    tmp_path: Path,
    current_extractions: object,
) -> None:
    output_dir = tmp_path / "invalid-current"

    with pytest.raises((TypeError, ValueError)):
        materialize_current_extractions(
            current_extractions,  # type: ignore[arg-type]
            output_dir=output_dir,
        )

    assert not output_dir.exists()
    _assert_no_staging(output_dir)


def test_public_materialization_signatures_are_stable() -> None:
    assert tuple(signature(materialize_current_extractions).parameters) == (
        "current_extractions",
        "output_dir",
    )
    assert tuple(signature(materialize_flat_tables).parameters) == (
        "tables",
        "output_dir",
        "manifest_context",
    )
