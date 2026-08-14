from __future__ import annotations

import builtins
import inspect
import json
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

import renewables_permitting.downstream as downstream_module
from renewables_permitting.downstream import (
    DownstreamError,
    run_downstream,
)
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.flat_materialization import (
    materialize_current_extractions,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    AdministrativeLocationLevel,
    AdministrativeLocationMention,
    BOEProjectExtraction,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationType,
    PublicationEvent,
)
from renewables_permitting.gold import (
    PROJECT_EVENTS_COLUMNS,
    PROJECTS_COLUMNS,
)
from renewables_permitting.ine_reference import (
    build_municipality_dimension,
    materialize_municipality_dimension,
)
from renewables_permitting.location_resolution import (
    LOCATION_RESOLUTION_COLUMNS,
)
from renewables_permitting.project_grouping import PROJECT_GROUPING_COLUMNS
from renewables_permitting.project_locations import (
    PROJECT_LOCATION_SOURCES_COLUMNS,
    PROJECT_LOCATIONS_COLUMNS,
)


FIXED_CREATED_AT = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)


def _extraction(index: int) -> BOEProjectExtraction:
    boe_id = f"BOE-A-2026-{100 + index}"
    publication_date = date(2026, 1, index)
    evidence = "Se autoriza la planta fotovoltaica Aurora Solar en Alosno."
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de generación.",
        publication_events=[PublicationEvent(
            generation_assets=[GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Aurora Solar"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                evidence=evidence,
            )],
            administrative_actions=[AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                targets=["event"],
                evidence=evidence,
            )],
            administrative_locations=[AdministrativeLocationMention(
                location_name_raw="Alosno",
                location_level=AdministrativeLocationLevel.MUNICIPALITY,
                province_hint_raw="Huelva",
                evidence=evidence,
            )],
            event_summary="Autorización de Aurora Solar.",
        )],
        extraction_notes=None,
        boe_id=boe_id,
        publication_date=publication_date,
    )


def _current_extractions(*, reverse: bool = False) -> pd.DataFrame:
    rows = []
    for index in (1, 2):
        extraction = _extraction(index)
        rows.append({
            "attempt_id": f"attempt-{index}",
            "identificador_boe": extraction.boe_id,
            "source_document_sha256": str(index) * 64,
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
            "instructions_sha256": INSTRUCTIONS_SHA256,
            "model_provider": MODEL_PROVIDER,
            "model_name": AI_MODEL_NAME,
            "document_validation_version": DOCUMENT_VALIDATION_VERSION,
            "selection_source": "auto_validated",
            "extraction_json": extraction.model_dump_json(),
        })
    return pd.DataFrame(rows[::-1] if reverse else rows)


def _materialize_ine_reference(tmp_path: Path):
    codine = pd.DataFrame([{
        "codauto": "1",
        "comunidad_autonoma": "Andalucía",
        "cpro": "21",
        "provincia": "Huelva",
    }]).astype("string")
    dictionary = pd.DataFrame([{
        "codauto": "1",
        "cpro": "21",
        "cmun": "6",
        "dc": "0",
        "nombre": "Alosno",
    }]).astype("string")
    codine_path = tmp_path / "codine.csv"
    dictionary_path = tmp_path / "dictionary.csv"
    codine.to_csv(codine_path, index=False, encoding="utf-8-sig")
    dictionary.to_csv(dictionary_path, index=False, encoding="utf-8-sig")
    dimension = build_municipality_dimension(codine, dictionary)
    return materialize_municipality_dimension(
        dimension,
        output_dir=tmp_path / "ine-reference",
        codine_source_path=codine_path,
        dictionary_source_path=dictionary_path,
        created_at=FIXED_CREATED_AT,
    )


def _materialize_inputs(tmp_path: Path, *, reverse: bool = False):
    silver = materialize_current_extractions(
        _current_extractions(reverse=reverse),
        output_dir=tmp_path / "silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    ine = _materialize_ine_reference(tmp_path)
    return silver, ine


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_valid_downstream_materializes_all_artifacts_with_lineage(tmp_path) -> None:
    silver, ine = _materialize_inputs(tmp_path)

    result = run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=ine.output_dir,
        output_dir=tmp_path / "downstream",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=FIXED_CREATED_AT,
    )

    resolved = pd.read_parquet(result.resolved_locations_path)
    grouping = pd.read_parquet(result.project_grouping_path)
    projects = pd.read_parquet(result.projects_path)
    project_events = pd.read_parquet(result.project_events_path)
    project_locations = pd.read_parquet(result.project_locations_path)
    project_location_sources = pd.read_parquet(
        result.project_location_sources_path
    )
    downstream_manifest = json.loads(
        result.downstream_manifest_path.read_text(encoding="utf-8")
    )
    gold_manifest = json.loads(
        result.gold_manifest_path.read_text(encoding="utf-8")
    )

    assert result.output_dir == tmp_path / "downstream"
    assert len(resolved) == 2
    assert len(grouping) == 2
    assert len(projects) == 1
    assert len(project_events) == 2
    assert len(project_locations) == 1
    assert len(project_location_sources) == 2
    assert tuple(grouping.columns) == PROJECT_GROUPING_COLUMNS
    assert tuple(projects.columns) == PROJECTS_COLUMNS
    assert tuple(project_events.columns) == PROJECT_EVENTS_COLUMNS
    assert tuple(project_locations.columns) == PROJECT_LOCATIONS_COLUMNS
    assert tuple(project_location_sources.columns) == (
        PROJECT_LOCATION_SOURCES_COLUMNS
    )
    assert set(LOCATION_RESOLUTION_COLUMNS).issubset(resolved.columns)
    assert projects["project_id"].is_unique
    assert not project_events.duplicated([
        "project_id", "administrative_action_id"
    ]).any()
    assert downstream_manifest["silver"]["materialization_id"] == (
        silver.materialization_id
    )
    assert downstream_manifest["silver"]["extraction_config_id"] == (
        EXTRACTION_CONFIG_ID
    )
    assert downstream_manifest["ine_reference"]["semantic_reference_id"] == (
        ine.semantic_reference_id
    )
    assert gold_manifest["silver_materialization_id"] == silver.materialization_id
    assert gold_manifest["ine_reference_id"] == ine.semantic_reference_id
    assert gold_manifest["downstream_materialization_id"] == (
        result.materialization_id
    )
    artifact_semantic_sha256 = {
        "resolved_locations": downstream_manifest["artifacts"][
            "resolved_locations"
        ]["semantic_sha256"],
        "project_grouping": downstream_manifest["artifacts"][
            "project_grouping"
        ]["semantic_sha256"],
        **{
            name: metadata["semantic_sha256"]
            for name, metadata in gold_manifest["tables"].items()
        },
    }
    assert downstream_module.compute_downstream_materialization_id(
        silver_materialization_id=silver.materialization_id,
        extraction_config_id=EXTRACTION_CONFIG_ID,
        ine_reference_sha256=ine.semantic_reference_sha256,
        artifact_semantic_sha256=artifact_semantic_sha256,
    ) == result.materialization_id
    assert downstream_manifest["artifacts"]["resolved_locations"][
        "parquet_sha256"
    ] == _file_hash(result.resolved_locations_path)
    assert downstream_manifest["artifacts"]["project_grouping"][
        "parquet_sha256"
    ] == _file_hash(result.project_grouping_path)
    assert downstream_manifest["artifacts"]["project_grouping"]["lineage"][
        "resolved_locations_id"
    ] == downstream_manifest["artifacts"]["resolved_locations"][
        "semantic_sha256"
    ]
    assert gold_manifest["tables"]["projects"]["parquet_sha256"] == (
        _file_hash(result.projects_path)
    )
    assert gold_manifest["tables"]["project_events"]["parquet_sha256"] == (
        _file_hash(result.project_events_path)
    )
    assert gold_manifest["tables"]["project_locations"]["parquet_sha256"] == (
        _file_hash(result.project_locations_path)
    )
    assert gold_manifest["tables"]["project_location_sources"][
        "parquet_sha256"
    ] == _file_hash(result.project_location_sources_path)
    assert gold_manifest["tables"]["project_locations"]["sources"] == [
        "projects",
        "publication_events",
        "generation_asset_mentions",
        "project_grouping",
        "resolved_locations",
    ]
    assert gold_manifest["tables"]["project_locations"][
        "contract_version"
    ] == "1"
    assert gold_manifest["tables"]["project_location_sources"][
        "contract_version"
    ] == "1"
    assert gold_manifest["project_locations_audit"] == {
        "multiproject_source_expansions": 0,
        "resolved_source_location_mentions": 2,
        "source_location_mentions": 2,
        "unresolved_source_location_mentions_omitted": 0,
    }


def test_stale_or_missing_silver_fails_before_publishing(tmp_path) -> None:
    silver, ine = _materialize_inputs(tmp_path)
    stale_output = tmp_path / "stale-output"

    with pytest.raises(DownstreamError, match="Silver.*config"):
        run_downstream(
            silver_snapshot=silver.output_dir,
            municipality_reference=ine.output_dir,
            output_dir=stale_output,
            expected_extraction_config_id="stale-config",
        )
    assert not stale_output.exists()

    missing_manifest = tmp_path / "missing-manifest"
    missing_manifest.mkdir()
    with pytest.raises(DownstreamError, match="Silver.*manifest"):
        run_downstream(
            silver_snapshot=missing_manifest,
            municipality_reference=ine.output_dir,
            output_dir=tmp_path / "missing-output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "missing-output").exists()


def test_corrupt_silver_or_ine_fails_before_publishing(tmp_path) -> None:
    silver, ine = _materialize_inputs(tmp_path)
    silver_table = silver.table_paths["location_mentions"]
    silver_table.write_bytes(silver_table.read_bytes() + b"corrupt")

    with pytest.raises(DownstreamError, match="Silver.*hash"):
        run_downstream(
            silver_snapshot=silver.output_dir,
            municipality_reference=ine.output_dir,
            output_dir=tmp_path / "corrupt-silver-output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "corrupt-silver-output").exists()

    clean_root = tmp_path / "clean"
    clean_root.mkdir()
    clean_silver, clean_ine = _materialize_inputs(clean_root)
    ine_path = clean_ine.dimension_path
    ine_path.write_bytes(ine_path.read_bytes() + b"corrupt")
    with pytest.raises(DownstreamError, match="INE.*hash"):
        run_downstream(
            silver_snapshot=clean_silver.output_dir,
            municipality_reference=clean_ine.output_dir,
            output_dir=tmp_path / "corrupt-ine-output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "corrupt-ine-output").exists()


def test_tampered_silver_materialization_id_fails_before_publishing(
    tmp_path,
) -> None:
    silver, ine = _materialize_inputs(tmp_path)
    manifest = json.loads(silver.manifest_path.read_text(encoding="utf-8"))
    manifest["materialization_id"] = "0" * 64
    silver.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DownstreamError, match="Silver.*materialization_id"):
        run_downstream(
            silver_snapshot=silver.output_dir,
            municipality_reference=ine.output_dir,
            output_dir=tmp_path / "tampered-id-output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "tampered-id-output").exists()


def test_repeatability_and_input_order_do_not_change_identity(tmp_path) -> None:
    silver, ine = _materialize_inputs(tmp_path / "first-input")
    first = run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=ine.output_dir,
        output_dir=tmp_path / "first-output",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=FIXED_CREATED_AT,
    )
    repeated = run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=ine.output_dir,
        output_dir=tmp_path / "repeated-output",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=FIXED_CREATED_AT.replace(hour=13),
    )
    reverse_silver, reverse_ine = _materialize_inputs(
        tmp_path / "reverse-input",
        reverse=True,
    )
    reversed_result = run_downstream(
        silver_snapshot=reverse_silver.output_dir,
        municipality_reference=reverse_ine.output_dir,
        output_dir=tmp_path / "reverse-output",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=FIXED_CREATED_AT,
    )

    assert silver.materialization_id == reverse_silver.materialization_id
    assert ine.semantic_reference_id == reverse_ine.semantic_reference_id
    assert first.materialization_id == repeated.materialization_id
    assert first.materialization_id == reversed_result.materialization_id
    for attribute in (
        "resolved_locations_path",
        "project_grouping_path",
        "projects_path",
        "project_events_path",
        "project_locations_path",
        "project_location_sources_path",
    ):
        pd.testing.assert_frame_equal(
            pd.read_parquet(getattr(first, attribute)),
            pd.read_parquet(getattr(reversed_result, attribute)),
        )


def test_intermediate_failure_cleans_staging_and_never_publishes(
    tmp_path,
    monkeypatch,
) -> None:
    silver, ine = _materialize_inputs(tmp_path)
    output_dir = tmp_path / "failed-output"

    def fail_gold(**kwargs):
        raise RuntimeError("synthetic Gold failure")

    monkeypatch.setattr(downstream_module, "build_gold_tables", fail_gold)
    with pytest.raises(DownstreamError, match="Gold"):
        run_downstream(
            silver_snapshot=silver.output_dir,
            municipality_reference=ine.output_dir,
            output_dir=output_dir,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".failed-output.staging-*"))


def test_materialization_failure_cleans_created_staging(
    tmp_path,
    monkeypatch,
) -> None:
    silver, ine = _materialize_inputs(tmp_path)
    output_dir = tmp_path / "failed-write-output"
    original_writer = downstream_module._write_verified_parquet
    write_count = 0

    def fail_second_write(*args, **kwargs):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise RuntimeError("synthetic Parquet failure")
        return original_writer(*args, **kwargs)

    monkeypatch.setattr(
        downstream_module,
        "_write_verified_parquet",
        fail_second_write,
    )
    with pytest.raises(DownstreamError, match="materialization"):
        run_downstream(
            silver_snapshot=silver.output_dir,
            municipality_reference=ine.output_dir,
            output_dir=output_dir,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".failed-write-output.staging-*"))


def test_project_location_write_failure_never_publishes_partial_gold(
    tmp_path,
    monkeypatch,
) -> None:
    silver, ine = _materialize_inputs(tmp_path)
    output_dir = tmp_path / "failed-location-output"
    original_writer = downstream_module._write_verified_parquet

    def fail_project_locations(frame, path, **kwargs):
        if path.name == "project_locations.parquet":
            raise RuntimeError("synthetic project_locations failure")
        return original_writer(frame, path, **kwargs)

    monkeypatch.setattr(
        downstream_module,
        "_write_verified_parquet",
        fail_project_locations,
    )
    with pytest.raises(DownstreamError, match="materialization"):
        run_downstream(
            silver_snapshot=silver.output_dir,
            municipality_reference=ine.output_dir,
            output_dir=output_dir,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".failed-location-output.staging-*"))


def test_empty_valid_silver_produces_typed_empty_downstream(tmp_path) -> None:
    silver = materialize_current_extractions(
        pd.DataFrame(columns=["extraction_json"]),
        output_dir=tmp_path / "empty-silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    ine = _materialize_ine_reference(tmp_path)

    result = run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=ine.output_dir,
        output_dir=tmp_path / "empty-downstream",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    resolved = pd.read_parquet(result.resolved_locations_path)
    grouping = pd.read_parquet(result.project_grouping_path)
    projects = pd.read_parquet(result.projects_path)
    project_events = pd.read_parquet(result.project_events_path)
    project_locations = pd.read_parquet(result.project_locations_path)
    project_location_sources = pd.read_parquet(
        result.project_location_sources_path
    )
    assert resolved.empty
    assert grouping.empty
    assert projects.empty
    assert project_events.empty
    assert project_locations.empty
    assert project_location_sources.empty
    assert tuple(grouping.columns) == PROJECT_GROUPING_COLUMNS
    assert tuple(projects.columns) == PROJECTS_COLUMNS
    assert tuple(project_events.columns) == PROJECT_EVENTS_COLUMNS
    assert tuple(project_locations.columns) == PROJECT_LOCATIONS_COLUMNS
    assert tuple(project_location_sources.columns) == (
        PROJECT_LOCATION_SOURCES_COLUMNS
    )


def test_downstream_has_no_ai_or_user_interaction(tmp_path, monkeypatch) -> None:
    silver, ine = _materialize_inputs(tmp_path)

    def forbidden_input(*args, **kwargs):
        raise AssertionError("input() must not be called")

    monkeypatch.setattr(builtins, "input", forbidden_input)
    run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=ine.output_dir,
        output_dir=tmp_path / "non-interactive-output",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    source = inspect.getsource(downstream_module)
    assert "Agent" not in source
    assert "extract_documents" not in source
    assert "flatten_current_extractions" not in source
    assert "input(" not in source
