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
from renewables_permitting.extraction.runner import build_error_record


NOW = datetime(2026, 8, 13, 10, tzinfo=timezone.utc)
ACTIVE_NOW = datetime(2026, 8, 23, 10, tzinfo=timezone.utc)
SOURCE_CONFIG_ID = "67a0bd9d0759a322"
SOURCE_CONTRACT_SHA256 = (
    "455028c7de0ada067264cd695b4e7dab9de377b31105e141321313d61c3ff283"
)
SOURCE_INSTRUCTIONS_SHA256 = (
    "b48240832d1b274af0435cea42cc6d305d2aec83b5a3395a1d5ce1529eff0607"
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
            "instructions_sha256": SOURCE_INSTRUCTIONS_SHA256,
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
        "instructions_sha256": SOURCE_INSTRUCTIONS_SHA256,
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


def _write_active_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    snapshot = tmp_path / "active-run" / "extraction"
    snapshot.mkdir(parents=True)
    documents = pipeline.prepare_documents(_mixed_documents().iloc[:1])
    attempts = _historical_attempts(documents)
    attempts.loc[:, "extraction_config_id"] = EXTRACTION_CONFIG_ID
    attempts.loc[:, "contract_schema_sha256"] = CONTRACT_SCHEMA_SHA256
    attempts.loc[:, "instructions_sha256"] = pipeline.INSTRUCTIONS_SHA256
    attempts.loc[:, "attempt_origin"] = "model"
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
        "created_at": "2026-08-21T12:00:00Z",
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "model_provider": pipeline.MODEL_PROVIDER,
        "model_name": pipeline.AI_MODEL_NAME,
        "instructions_sha256": pipeline.INSTRUCTIONS_SHA256,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "canonicalization_policy": EXTRACTION_CONFIG[
            "canonicalization_policy"
        ],
        "scope_classification_policy": EXTRACTION_CONFIG[
            "scope_classification_policy"
        ],
        "document_validation_version": pipeline.DOCUMENT_VALIDATION_VERSION,
        "document_identity_sha256": pipeline._documents_identity(documents),
        "counts": {
            "documents": 1,
            "attempts": 1,
            "current_extractions": 1,
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
    documents_path = tmp_path / "active-documents.parquet"
    documents.to_parquet(documents_path, index=False)
    return snapshot, documents_path


def _active_incomplete_documents() -> pd.DataFrame:
    rows = []
    for index in range(1, 6):
        evidence = (
            "Resolución por la que se desestima la solicitud de autorización "
            "administrativa previa de la planta fotovoltaica Aurora Solar."
            if index == 1
            else "Se autoriza la planta fotovoltaica Aurora Solar."
        )
        rows.append({
            "identificador": f"BOE-A-2026-{200 + index}",
            "fecha_publicacion": pd.Timestamp(2026, 2, index),
            "titulo": evidence,
            "texto_limpio": evidence,
            "xml_status": "ok",
        })
    return pd.DataFrame(rows)


def _write_active_incomplete_snapshot(
    tmp_path: Path,
) -> tuple[Path, Path, pd.DataFrame]:
    prepared = pipeline.prepare_documents(_active_incomplete_documents())
    records = []
    for position, (_, row) in enumerate(prepared.iterrows(), start=1):
        document = build_source_document(row)
        extraction = _model_extraction(row)
        if position == 1:
            extraction.publication_events[0].administrative_actions[
                0
            ].decision = AdministrativeDecision.REQUESTED
        if position == 3:
            record = build_error_record(
                document=document,
                prepared=None,
                error=RuntimeError("synthetic operational error"),
                processing_stage="agent_run",
                duration_seconds=0.2,
                usage=RunUsage(requests=1, input_tokens=10, output_tokens=5),
                extraction=None,
                adjustments=[],
            )
            record["attempt_origin"] = "model"
        else:
            record = build_success_record(
                document=document,
                prepared=None,
                extraction=extraction,
                duration_seconds=0.2,
                usage=RunUsage(requests=1, input_tokens=10, output_tokens=5),
                adjustments=[],
                precanonical_extraction=extraction,
            )
            record["attempt_origin"] = "model"
            if position == 2:
                record.update({
                    "extraction_status": "error",
                    "error_type": "DocumentExtractionValidationError",
                    "error_message": "synthetic historical validation error",
                    "processing_stage": "document_validation",
                    "document_validation_status": "failed",
                    "document_validation_issue_count": 1,
                    "validation_issues_json": json.dumps(["historical"]),
                })
        record["attempt_id"] = f"active-source-{position}"
        records.append(record)
    attempts = normalise_ai_extraction_attempts_log(pd.DataFrame(records))
    attempts_path = tmp_path / "active-attempts.parquet"
    attempts.to_parquet(attempts_path, index=False)
    documents_path = tmp_path / "active-incomplete-documents.parquet"
    prepared.to_parquet(documents_path, index=False)
    result = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        output_dir=tmp_path / "active-incomplete" / "extraction",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    return result.output_dir, documents_path, attempts


def _write_active_reviews(
    tmp_path: Path,
    documents_path: Path,
    attempts: pd.DataFrame,
) -> Path:
    documents = pipeline.load_documents_input(documents_path)
    documents_by_id = documents.set_index("identificador")
    attempts_by_id = attempts.set_index("identificador_boe")
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    rejected_boe = "BOE-A-2026-204"
    manual_boe = "BOE-A-2026-205"
    payloads = {
        rejected_boe: {
            "identificador_boe": rejected_boe,
            "source_document_sha256": str(
                documents_by_id.loc[rejected_boe, "source_document_sha256"]
            ),
            "source_attempt_id": str(
                attempts_by_id.loc[rejected_boe, "attempt_id"]
            ),
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "document_validation_version": pipeline.DOCUMENT_VALIDATION_VERSION,
            "review_status": "rejected",
            "reviewer": "human_tfm_review",
            "review_notes": "Documento rechazado por decisión humana.",
            "reviewed_at_utc": "2026-08-22T12:00:00Z",
            "corrected_extraction": None,
        },
        manual_boe: {
            "identificador_boe": manual_boe,
            "source_document_sha256": str(
                documents_by_id.loc[manual_boe, "source_document_sha256"]
            ),
            "source_attempt_id": str(
                attempts_by_id.loc[manual_boe, "attempt_id"]
            ),
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "document_validation_version": pipeline.DOCUMENT_VALIDATION_VERSION,
            "review_status": "manually_validated",
            "reviewer": "human_tfm_review",
            "review_notes": "Extracción validada manualmente.",
            "reviewed_at_utc": "2026-08-22T12:01:00Z",
            "corrected_extraction": json.loads(
                str(attempts_by_id.loc[manual_boe, "extraction_json"])
            ),
        },
    }
    for boe_id, payload in payloads.items():
        (review_dir / f"{boe_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return review_dir


def test_active_config_snapshot_is_accepted_for_cumulative_recanonicalization(
    tmp_path,
) -> None:
    source, documents = _write_active_snapshot(tmp_path)

    plan = pipeline.plan_recanonicalization_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=tmp_path / "active-target",
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert plan.target_record_count == 1
    assert plan.model_calls == 0


def test_active_cumulative_replay_preserves_history_reviews_and_usage(
    tmp_path,
    monkeypatch,
) -> None:
    source, documents, original_attempts = _write_active_incomplete_snapshot(
        tmp_path
    )
    reviews = _write_active_reviews(tmp_path, documents, original_attempts)
    original_attempt_hash = pipeline._sha256_file(source / "attempts.parquet")
    output = tmp_path / "active-cumulative-target"
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("model must not run")),
    )

    result = pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        manual_reviews=reviews,
        created_at=ACTIVE_NOW,
    )
    loaded = pipeline.load_extraction_snapshot(
        output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert result.source_attempt_count == 5
    assert result.precanonical_record_count == 4
    assert result.changed_record_count == 1
    assert result.unchanged_record_count == 3
    assert result.operational_error_count == 1
    assert result.model_calls == 0
    assert len(loaded.attempts) == 9
    assert set(original_attempts["attempt_id"]).issubset(
        set(loaded.attempts["attempt_id"])
    )
    original_rows = loaded.attempts.loc[
        loaded.attempts["attempt_id"].isin(original_attempts["attempt_id"]),
        original_attempts.columns,
    ].reset_index(drop=True)
    assert pipeline._frame_equal(
        original_rows,
        original_attempts.reset_index(drop=True),
        sort_by=("attempt_id",),
    )
    derived = loaded.attempts.loc[
        loaded.attempts["attempt_origin"].eq("recanonicalized")
    ]
    assert len(derived) == 4
    assert derived["usage_requests"].fillna(0).eq(0).all()
    assert derived["usage_input_tokens"].fillna(0).eq(0).all()
    assert derived["usage_output_tokens"].fillna(0).eq(0).all()
    assert derived["usage_total_tokens"].fillna(0).eq(0).all()
    assert set(loaded.current_extractions["identificador_boe"]) == {
        "BOE-A-2026-201",
        "BOE-A-2026-202",
        "BOE-A-2026-205",
    }
    manual = loaded.current_extractions.set_index("identificador_boe").loc[
        "BOE-A-2026-205"
    ]
    assert manual["selection_source"] == "manually_validated"
    assert manual["source_attempt_id"] == "active-source-5"
    assert "BOE-A-2026-204" not in set(
        loaded.current_extractions["identificador_boe"]
    )
    assert loaded.review_queue["identificador_boe"].tolist() == [
        "BOE-A-2026-203"
    ]
    assert pipeline._sha256_file(source / "attempts.parquet") == (
        original_attempt_hash
    )
    manifest = loaded.manifest
    assert manifest["snapshot_type"] == "recanonicalized_extraction"
    assert manifest["recanonicalization"]["mode"] == "active_cumulative"
    assert manifest["recanonicalization"]["model_requests_added"] == 0
    assert len(manifest["target"]["deterministic_code_sha256"]) == 64
    assert manifest["counts"]["human_rejected"] == 1
    assert manifest["counts"]["manually_validated"] == 1
    assert manifest["counts"]["operational_errors_preserved"] == 1


def test_active_recanonicalization_is_idempotent_across_two_snapshots(
    tmp_path,
) -> None:
    source, documents, original_attempts = _write_active_incomplete_snapshot(
        tmp_path
    )
    reviews = _write_active_reviews(tmp_path, documents, original_attempts)
    first_output = tmp_path / "active-cumulative-first"
    second_output = tmp_path / "active-cumulative-second"
    second_instant = ACTIVE_NOW.replace(hour=11)

    pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=first_output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        manual_reviews=reviews,
        created_at=ACTIVE_NOW,
    )
    first = pipeline.load_extraction_snapshot(
        first_output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    plan = pipeline.plan_recanonicalization_snapshot(
        source_snapshot=first_output,
        documents=documents,
        output_dir=second_output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=second_instant,
    )

    assert plan.reused_derived_attempt_count == 4
    assert plan.derived_attempts.empty
    assert plan.changed_boe_ids == ()
    assert plan.unchanged_record_count == 0
    result = pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=first_output,
        documents=documents,
        output_dir=second_output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=second_instant,
    )
    second = pipeline.load_extraction_snapshot(
        second_output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert len(second.attempts) == len(first.attempts) == 9
    assert second.attempts["attempt_id"].is_unique
    assert set(second.attempts["attempt_id"]) == set(first.attempts["attempt_id"])
    assert pipeline._frame_equal(
        second.attempts,
        first.attempts,
        sort_by=("attempt_id",),
    )
    assert pipeline._frame_equal(
        second.current_extractions,
        first.current_extractions,
        sort_by=("identificador_boe", "attempt_id"),
    )
    assert pipeline._frame_equal(
        second.manual_reviews,
        first.manual_reviews,
        sort_by=("manual_review_id",),
    )
    assert result.model_calls == 0
    assert result.changed_record_count == 0
    assert second.manifest["recanonicalization"]["model_requests_added"] == 0
    assert second.manifest["recanonicalization"]["input_tokens_added"] == 0
    assert second.manifest["recanonicalization"]["output_tokens_added"] == 0


def test_active_recanonicalization_preserves_one_retry_attempt_once(
    tmp_path,
) -> None:
    source, documents, original_attempts = _write_active_incomplete_snapshot(
        tmp_path
    )
    reviews = _write_active_reviews(tmp_path, documents, original_attempts)
    first_output = tmp_path / "active-cumulative-first"
    pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=first_output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        manual_reviews=reviews,
        created_at=ACTIVE_NOW,
    )
    first = pipeline.load_extraction_snapshot(
        first_output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    retry_boe = "BOE-A-2026-203"
    retry_row = first.documents.loc[
        first.documents["identificador"].astype(str).eq(retry_boe)
    ].iloc[0]
    retry_document = build_source_document(retry_row)
    retry_extraction = _model_extraction(retry_row)
    retry_record = build_success_record(
        document=retry_document,
        prepared=None,
        extraction=retry_extraction,
        duration_seconds=0.3,
        usage=RunUsage(requests=1, input_tokens=20, output_tokens=8),
        adjustments=[],
        precanonical_extraction=retry_extraction,
    )
    retry_record["attempt_id"] = "active-retry-success"
    retry_record["attempt_origin"] = "model"
    retry_attempt = normalise_ai_extraction_attempts_log(
        pd.DataFrame([retry_record])
    )
    retry_attempts = pipeline.combine_ai_extraction_attempt_frames(
        first.attempts,
        retry_attempt,
    )
    retry_attempts_path = tmp_path / "retry-attempts.parquet"
    retry_attempts.to_parquet(retry_attempts_path, index=False)
    retry_snapshot = tmp_path / "active-retry-snapshot"
    pipeline.run_extraction_stage(
        documents=documents,
        attempts=retry_attempts_path,
        manual_reviews=first_output / "manual_reviews.parquet",
        output_dir=retry_snapshot,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    final_output = tmp_path / "active-final"
    pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=retry_snapshot,
        documents=documents,
        output_dir=final_output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=ACTIVE_NOW.replace(hour=11),
    )
    final = pipeline.load_extraction_snapshot(
        final_output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert final.attempts["attempt_id"].is_unique
    assert final.attempts["attempt_id"].eq("active-retry-success").sum() == 1
    retry_derived = final.attempts.loc[
        final.attempts["identificador_boe"].astype(str).eq(retry_boe)
        & final.attempts["attempt_origin"].astype(str).eq("recanonicalized")
    ]
    assert len(retry_derived) == 1
    assert retry_derived.iloc[0]["source_attempt_id"] == "active-retry-success"
    second_plan = pipeline.plan_recanonicalization_snapshot(
        source_snapshot=final_output,
        documents=documents,
        output_dir=tmp_path / "active-second-pass",
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=ACTIVE_NOW.replace(hour=12),
    )
    assert second_plan.reused_derived_attempt_count == 5
    assert second_plan.derived_attempts.empty


def test_active_recanonicalization_rejects_conflicting_derived_collision(
    tmp_path,
    monkeypatch,
) -> None:
    source, documents, original_attempts = _write_active_incomplete_snapshot(
        tmp_path
    )
    reviews = _write_active_reviews(tmp_path, documents, original_attempts)
    first_output = tmp_path / "active-cumulative-first"
    pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=first_output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        manual_reviews=reviews,
        created_at=ACTIVE_NOW,
    )
    real_builder = pipeline.build_recanonicalized_attempt_record

    def conflicting_builder(*args, **kwargs):
        record = real_builder(*args, **kwargs)
        payload = json.loads(str(record["extraction_json"]))
        payload["classification_reason"] += " Conflicto sintético."
        record["classification_reason"] = payload["classification_reason"]
        record["extraction_json"] = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return record

    monkeypatch.setattr(
        pipeline,
        "build_recanonicalized_attempt_record",
        conflicting_builder,
    )

    with pytest.raises(
        pipeline.PipelineError,
        match="attempt_id collision.*inconsistent",
    ):
        pipeline.plan_recanonicalization_snapshot(
            source_snapshot=first_output,
            documents=documents,
            output_dir=tmp_path / "conflicting-target",
            source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            created_at=ACTIVE_NOW.replace(hour=11),
        )


def test_extraction_loader_rejects_duplicate_attempt_ids(tmp_path) -> None:
    source, documents, original_attempts = _write_active_incomplete_snapshot(
        tmp_path
    )
    reviews = _write_active_reviews(tmp_path, documents, original_attempts)
    output = tmp_path / "active-cumulative-target"
    pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        manual_reviews=reviews,
        created_at=ACTIVE_NOW,
    )
    attempts_path = output / "attempts.parquet"
    attempts = pd.read_parquet(attempts_path)
    duplicate_id = str(attempts.iloc[0]["attempt_id"])
    attempts = pd.concat([attempts, attempts.iloc[[0]]], ignore_index=True)
    attempts.to_parquet(attempts_path, index=False)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["attempts"] = len(attempts)
    manifest["artifacts"]["attempts"] = pipeline._artifact(
        attempts_path,
        attempts,
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        pipeline.PipelineError,
        match=rf"duplicate attempt_id.*{duplicate_id}",
    ):
        pipeline.load_extraction_snapshot(
            output,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_recanonicalization_rejects_duplicate_attempts_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    source, documents, original_attempts = _write_active_incomplete_snapshot(
        tmp_path
    )
    reviews = _write_active_reviews(tmp_path, documents, original_attempts)
    output = tmp_path / "duplicate-publication-target"
    real_build = pipeline.build_recanonicalized_attempts

    def duplicate_build(plan, *, recanonicalized_at):
        derived = real_build(plan, recanonicalized_at=recanonicalized_at)
        return pd.concat([derived, derived.iloc[[0]]], ignore_index=True)

    monkeypatch.setattr(
        pipeline,
        "build_recanonicalized_attempts",
        duplicate_build,
    )

    with pytest.raises(
        pipeline.PipelineError,
        match="duplicate attempt_id",
    ):
        pipeline.recanonicalize_extraction_snapshot(
            source_snapshot=source,
            documents=documents,
            output_dir=output,
            source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            manual_reviews=reviews,
            created_at=ACTIVE_NOW,
        )

    assert not output.exists()


def test_active_cumulative_snapshot_is_a_valid_explicit_retry_input(
    tmp_path,
) -> None:
    source, documents, attempts = _write_active_incomplete_snapshot(tmp_path)
    reviews = _write_active_reviews(tmp_path, documents, attempts)
    output = tmp_path / "active-cumulative-target"
    pipeline.recanonicalize_extraction_snapshot(
        source_snapshot=source,
        documents=documents,
        output_dir=output,
        source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        manual_reviews=reviews,
        created_at=ACTIVE_NOW,
    )

    plan = pipeline.build_extraction_plan(
        documents=documents,
        attempts=output,
        retry_error_boe_ids=["BOE-A-2026-203"],
        execute_model=False,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert plan.retry_error_document_ids == ("BOE-A-2026-203",)
    assert plan.model_required_count == 1
    assert plan.model_calls_planned == 0
    assert plan.compatible_existing_count == 4


def test_active_cumulative_replay_rejects_corrupt_persisted_output(
    tmp_path,
) -> None:
    source, documents, _ = _write_active_incomplete_snapshot(tmp_path)
    attempts_path = source / "attempts.parquet"
    attempts = pd.read_parquet(attempts_path)
    attempts.loc[
        attempts["identificador_boe"].eq("BOE-A-2026-202"),
        "precanonical_extraction_json",
    ] = "{"
    attempts.to_parquet(attempts_path, index=False)
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["attempts"] = pipeline._artifact(
        attempts_path, attempts
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(pipeline.PipelineError, match="corrupt"):
        pipeline.plan_recanonicalization_snapshot(
            source_snapshot=source,
            documents=documents,
            output_dir=tmp_path / "corrupt-target",
            source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_active_cumulative_replay_rejects_conflicting_reviews(
    tmp_path,
) -> None:
    source, documents, attempts = _write_active_incomplete_snapshot(tmp_path)
    reviews = _write_active_reviews(tmp_path, documents, attempts)
    original = json.loads(
        (reviews / "BOE-A-2026-204.json").read_text(encoding="utf-8")
    )
    original["review_notes"] = "Conflicting human disposition."
    (reviews / "conflict.json").write_text(
        json.dumps(original, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(pipeline.PipelineError, match="conflicting"):
        pipeline.plan_recanonicalization_snapshot(
            source_snapshot=source,
            documents=documents,
            output_dir=tmp_path / "conflict-target",
            source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            manual_reviews=reviews,
        )


def test_active_cumulative_replay_rejects_source_mismatch(tmp_path) -> None:
    source, documents, attempts = _write_active_incomplete_snapshot(tmp_path)
    reviews = _write_active_reviews(tmp_path, documents, attempts)
    mismatched = pipeline.load_documents_input(documents)
    mismatched.loc[0, "texto_limpio"] += " Alteración no contractual."

    with pytest.raises(pipeline.PipelineError, match="do not match"):
        pipeline.plan_recanonicalization_snapshot(
            source_snapshot=source,
            documents=mismatched,
            output_dir=tmp_path / "mismatched-target",
            source_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            target_expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            manual_reviews=reviews,
        )


def test_main01_versioned_human_reviews_encode_closed_dispositions() -> None:
    review_dir = Path("config/manual_reviews/boe_ai")
    rejected = json.loads(
        (review_dir / "BOE-B-2024-46241.json").read_text(encoding="utf-8")
    )
    rectification = json.loads(
        (review_dir / "BOE-B-2026-4032.json").read_text(encoding="utf-8")
    )

    assert rejected["source_attempt_id"] == (
        "cde570883d314230af0ff882e4eb070b"
    )
    assert rejected["review_status"] == "rejected"
    assert rejected["corrected_extraction"] is None
    assert "out_of_scope_non_generation" in rejected["review_notes"]
    assert rectification["source_attempt_id"] == (
        "ae5811ffa7ce49c9bf454d7c49f31f34"
    )
    assert rectification["review_status"] == "manually_validated"
    extraction = BOEProjectExtraction.model_validate(
        rectification["corrected_extraction"]
    )
    actions = extraction.publication_events[0].administrative_actions
    assert len(actions) == 1
    assert actions[0].action_type.value == "correccion_errores"
    assert actions[0].decision.value == "rectificado"
    assert actions[0].targets == ["event"]
    for payload in (rejected, rectification):
        assert payload["reviewer"] == "human_tfm_review"
        assert pd.Timestamp(payload["reviewed_at_utc"]).tzinfo is not None


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
        "instructions_sha256": SOURCE_INSTRUCTIONS_SHA256,
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
