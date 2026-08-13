from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

import renewables_permitting.pipeline as pipeline
from renewables_permitting.extraction.agent import RunUsage
from renewables_permitting.extraction.canonicalization import (
    preclassify_document_without_model,
)
from renewables_permitting.extraction.config import (
    CONTRACT_SCHEMA_SHA256,
    EXTRACTION_CONFIG,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
)
from renewables_permitting.extraction.documents import build_source_document
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
from renewables_permitting.extraction.review import (
    AI_EXTRACTION_LOG_COLUMNS,
    empty_manual_reviews,
    empty_review_queue,
    normalise_ai_extraction_attempts_log,
)
from renewables_permitting.extraction.recanonicalization import (
    build_recanonicalized_attempt_record,
    historical_recanonicalization_identity,
)
from renewables_permitting.extraction.runner import build_success_record


NOW = datetime(2026, 8, 13, 10, tzinfo=timezone.utc)
SOURCE_CONFIG_ID = "67a0bd9d0759a322"
SOURCE_CONTRACT_SHA256 = (
    "455028c7de0ada067264cd695b4e7dab9de377b31105e141321313d61c3ff283"
)
SOURCE_POLICY = (
    "termination_object_filter_environmental_terminal_whitelist_"
    "lexical_authorization_grants_v2_"
    "explicit_relation_validation_conservative_grouping_v1"
)
RECANONICALIZATION_LINEAGE_COLUMNS = {
    "attempt_origin",
    "source_attempt_id",
    "source_extraction_config_id",
    "source_contract_schema_sha256",
    "source_instructions_sha256",
    "source_canonicalization_policy",
    "source_model_provider",
    "source_model_name",
    "target_canonicalization_policy",
    "recanonicalized_at",
    "recanonicalization_source_run",
}


def _mixed_documents() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "identificador": "BOE-A-2026-101",
            "fecha_publicacion": pd.Timestamp("2026-01-02"),
            "titulo": "Se autoriza la planta fotovoltaica Aurora Solar.",
            "texto_limpio": "Se autoriza la planta fotovoltaica Aurora Solar.",
            "xml_status": "ok",
        },
        {
            "identificador": "BOE-B-2026-102",
            "fecha_publicacion": pd.Timestamp("2026-01-03"),
            "titulo": "Anuncio de licitacion de un contrato de suministro.",
            "texto_limpio": "Anuncio de licitación de un contrato de suministro.",
            "xml_status": "ok",
        },
    ])


def _model_extraction(row: pd.Series) -> BOEProjectExtraction:
    evidence = str(row["texto_limpio"])
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Documento específico de generación.",
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
            event_summary="Autorización publicada.",
        )],
        boe_id=str(row["identificador"]),
        publication_date=pd.Timestamp(row["fecha_publicacion"]).date(),
    )


def _historical_attempts(documents: pd.DataFrame) -> pd.DataFrame:
    prepared = pipeline.prepare_documents(documents)
    records = []
    for _, row in prepared.iterrows():
        document = build_source_document(row)
        deterministic, adjustments = preclassify_document_without_model(document)
        extraction = deterministic or _model_extraction(row)
        record = build_success_record(
            document=document,
            prepared=None,
            extraction=extraction,
            duration_seconds=0.25,
            usage=RunUsage(
                requests=0 if deterministic is not None else 1,
                input_tokens=0 if deterministic is not None else 123,
                output_tokens=0 if deterministic is not None else 45,
            ),
            adjustments=adjustments,
            processing_stage=(
                "deterministic_scope_guard"
                if deterministic is not None
                else "completed"
            ),
            precanonical_extraction=(
                None if deterministic is not None else extraction
            ),
        )
        record.update({
            "attempt_id": (
                "source-deterministic" if deterministic is not None
                else "source-model"
            ),
            "extraction_config_id": SOURCE_CONFIG_ID,
            "contract_schema_sha256": SOURCE_CONTRACT_SHA256,
        })
        records.append(record)
    legacy_columns = [
        column for column in AI_EXTRACTION_LOG_COLUMNS
        if column not in RECANONICALIZATION_LINEAGE_COLUMNS
    ]
    return normalise_ai_extraction_attempts_log(
        pd.DataFrame(records)
    ).loc[:, legacy_columns]


def _write_historical_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    snapshot = tmp_path / "historical-run" / "extraction"
    snapshot.mkdir(parents=True)
    documents = pipeline.prepare_documents(_mixed_documents())
    attempts = _historical_attempts(documents)
    current = attempts.copy()
    current["selection_source"] = "auto_validated"
    manual = empty_manual_reviews()
    queue = empty_review_queue()
    paths = {
        "documents": snapshot / "documents.parquet",
        "attempts": snapshot / "attempts.parquet",
        "manual_reviews": snapshot / "manual_reviews.parquet",
        "current_extractions": snapshot / "current_extractions.parquet",
        "review_queue": snapshot / "review_queue.parquet",
    }
    frames = {
        "documents": documents,
        "attempts": attempts,
        "manual_reviews": manual,
        "current_extractions": current,
        "review_queue": queue,
    }
    for name, path in paths.items():
        frames[name].to_parquet(path, index=False)
    manifest = {
        "stage": "extraction",
        "stage_version": pipeline.PIPELINE_STAGE_VERSION,
        "created_at": "2026-08-11T16:49:46Z",
        "extraction_config_id": SOURCE_CONFIG_ID,
        "model_provider": "gemini",
        "model_name": "google:gemini-2.5-flash",
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "contract_schema_sha256": SOURCE_CONTRACT_SHA256,
        "document_validation_version": "25",
        "document_identity_sha256": pipeline._documents_identity(documents),
        "counts": {
            "documents": 2,
            "attempts": 2,
            "current_extractions": 2,
            "blocking_review": 0,
        },
        "artifacts": {
            name: pipeline._artifact(path, frames[name])
            for name, path in paths.items()
        },
    }
    (snapshot / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    documents_path = tmp_path / "input-documents.parquet"
    documents.to_parquet(documents_path, index=False)
    return snapshot, documents_path


def _run_batch(tmp_path: Path):
    source, documents = _write_historical_snapshot(tmp_path)
    output = tmp_path / "target-extraction"
    result = pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=output,
        source_expected_extraction_config_id=SOURCE_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=NOW,
    )
    return source, output, result


def test_historical_snapshot_requires_the_explicit_matching_identity(
    tmp_path,
) -> None:
    source, _ = _write_historical_snapshot(tmp_path)

    loaded = pipeline.load_extraction_snapshot(
        source,
        expected_extraction_config_id=SOURCE_CONFIG_ID,
        allow_historical=True,
    )

    assert len(loaded.current_extractions) == 2
    with pytest.raises(pipeline.PipelineError, match="incompatible|mismatch"):
        pipeline.load_extraction_snapshot(
            source,
            expected_extraction_config_id="wrong-config",
            allow_historical=True,
        )


def test_batch_recanonicalizes_payload_and_reissues_deterministic_record(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("model must not run")),
    )

    _, output, result = _run_batch(tmp_path)
    loaded = pipeline.load_extraction_snapshot(
        output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert result.precanonical_record_count == 1
    assert result.deterministic_record_count == 1
    assert result.model_calls == 0
    assert len(loaded.attempts) == len(loaded.current_extractions) == 2
    by_boe = loaded.attempts.set_index("identificador_boe")
    model = by_boe.loc["BOE-A-2026-101"]
    deterministic = by_boe.loc["BOE-B-2026-102"]
    assert model["attempt_origin"] == "recanonicalized"
    assert model["source_attempt_id"] == "source-model"
    assert model["source_model_provider"] == "gemini"
    assert model["source_model_name"] == "google:gemini-2.5-flash"
    assert model["usage_requests"] == 1
    assert model["usage_input_tokens"] == 123
    assert model["usage_output_tokens"] == 45
    assert model["usage_total_tokens"] == 168
    assert deterministic["attempt_origin"] == "deterministic_reissued"
    assert pd.isna(deterministic["precanonical_extraction_json"])
    assert pd.isna(deterministic["model_provider"])
    assert pd.isna(deterministic["model_name"])
    assert deterministic["usage_requests"] == 0
    assert deterministic["extraction_json"] == (
        _historical_attempts(_mixed_documents())
        .set_index("identificador_boe")
        .loc["BOE-B-2026-102", "extraction_json"]
    )


def test_batch_records_target_lineage_and_rebuilds_selection_and_review(
    tmp_path,
) -> None:
    source, output, _ = _run_batch(tmp_path)
    loaded = pipeline.load_extraction_snapshot(
        output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    manifest = loaded.manifest

    assert loaded.review_queue.empty
    assert loaded.current_extractions["selection_source"].tolist() == [
        "auto_validated", "auto_validated"
    ]
    assert set(loaded.attempts["extraction_config_id"]) == {
        EXTRACTION_CONFIG_ID
    }
    assert set(loaded.attempts["contract_schema_sha256"]) == {
        CONTRACT_SCHEMA_SHA256
    }
    assert set(loaded.attempts["target_canonicalization_policy"]) == {
        EXTRACTION_CONFIG["canonicalization_policy"]
    }
    assert set(loaded.attempts["source_canonicalization_policy"]) == {
        SOURCE_POLICY
    }
    assert set(loaded.attempts["recanonicalization_source_run"]) == {
        source.parent.name
    }
    assert manifest["snapshot_type"] == "recanonicalized_extraction"
    assert manifest["source"]["extraction_config_id"] == SOURCE_CONFIG_ID
    assert manifest["source"]["canonicalization_policy"] == SOURCE_POLICY
    assert manifest["target"]["extraction_config_id"] == EXTRACTION_CONFIG_ID
    assert manifest["counts"]["precanonical_recanonicalized"] == 1
    assert manifest["counts"]["deterministic_preserved"] == 1
    assert manifest["counts"]["model_calls"] == 0
    assert not str(manifest["source"]["run_id"]).startswith("/")


def test_batch_is_atomic_on_failure_and_refuses_overwrite(
    tmp_path,
    monkeypatch,
) -> None:
    source, documents = _write_historical_snapshot(tmp_path)
    output = tmp_path / "failed-target"
    monkeypatch.setattr(
        pipeline,
        "_write_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("synthetic publication failure")
        ),
    )
    with pytest.raises(ValueError, match="publication"):
        pipeline.recanonicalize_extraction_snapshot(
            source_snapshot=source,
            documents=documents,
            output_dir=output,
            source_expected_extraction_config_id=SOURCE_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            created_at=NOW,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".failed-target.staging-*"))

    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        pipeline.recanonicalize_extraction_snapshot(
            source_snapshot=source,
            documents=documents,
            output_dir=existing,
            source_expected_extraction_config_id=SOURCE_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            created_at=NOW,
        )
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_recanonicalized_snapshot_can_feed_silver(tmp_path) -> None:
    _, output, _ = _run_batch(tmp_path)

    silver = pipeline.run_silver_stage(
        extraction_snapshot=output,
        output_dir=tmp_path / "silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert silver.output_dir.is_dir()
    assert (silver.output_dir / "manifest.json").is_file()


def test_recanonicalize_dry_run_validates_and_writes_nothing(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    source, documents = _write_historical_snapshot(tmp_path)
    output = tmp_path / "dry-target"
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("model must not run")),
    )

    code = pipeline.main([
        "recanonicalize",
        "--source-extraction-snapshot", str(source),
        "--documents", str(documents),
        "--output-dir", str(output),
        "--source-expected-extraction-config-id", SOURCE_CONFIG_ID,
        "--target-expected-extraction-config-id", EXTRACTION_CONFIG_ID,
        "--dry-run",
    ])

    assert code == 0
    text = capsys.readouterr().out
    assert "precanonical records: 1" in text
    assert "deterministic records: 1" in text
    assert "model calls: 0" in text
    assert str(output.absolute()) in text
    assert not output.exists()


def test_recanonicalize_cli_help_is_available_without_side_effects() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "renewables_permitting.pipeline",
            "recanonicalize",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--source-extraction-snapshot" in completed.stdout
    assert "--target-expected-extraction-config-id" in completed.stdout


@pytest.mark.parametrize(
    "boe_id",
    [
        "BOE-A-2024-16662",
        "BOE-A-2025-26112",
        "BOE-A-2026-9582",
    ],
)
def test_batch_record_applies_only_the_explicit_desestimation_decision(
    boe_id,
) -> None:
    title = (
        "Resolución por la que se desestima la solicitud de autorización "
        "administrativa previa de la planta fotovoltaica Aurora Solar."
    )
    row = pd.Series({
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp("2026-01-02"),
        "titulo": title,
        "texto_limpio": title,
        "xml_status": "ok",
    })
    document = build_source_document(row)
    precanonical = _model_extraction(row)
    precanonical.publication_events[0].administrative_actions[
        0
    ].decision = AdministrativeDecision.REQUESTED
    source_attempt = build_success_record(
        document=document,
        prepared=None,
        extraction=precanonical,
        duration_seconds=0.2,
        usage=RunUsage(requests=1, input_tokens=10, output_tokens=5),
        adjustments=[],
        precanonical_extraction=precanonical,
    )
    source_attempt.update({
        "attempt_id": f"source-{boe_id}",
        "extraction_config_id": SOURCE_CONFIG_ID,
        "contract_schema_sha256": SOURCE_CONTRACT_SHA256,
    })

    record = build_recanonicalized_attempt_record(
        source_attempt,
        document=document,
        source_identity=historical_recanonicalization_identity(
            SOURCE_CONFIG_ID
        ),
        source_run_id="historical-run",
        recanonicalized_at=NOW,
    )

    old_payload = json.loads(source_attempt["extraction_json"])
    new_payload = json.loads(record["extraction_json"])
    assert old_payload["publication_events"][0][
        "administrative_actions"
    ][0]["decision"] == "solicitado"
    assert new_payload["publication_events"][0][
        "administrative_actions"
    ][0]["decision"] == "desestimado"
    old_payload["publication_events"][0]["administrative_actions"][0][
        "decision"
    ] = "desestimado"
    assert new_payload == old_payload
