from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import pandas as pd

from renewables_permitting.extraction.agent import Agent, RunUsage, UsageLimits
from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
    preclassify_document_without_model,
)
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CHECKPOINT_EVERY,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_TIMEOUT_SECONDS,
    DOCUMENT_VALIDATION_RETRY_ATTEMPTS,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MAX_MODEL_REQUESTS_PER_DOCUMENT,
    MODEL_PROVIDER,
    MODEL_RUN_TIMEOUT_SECONDS,
    MODEL_SETTINGS,
    TRANSIENT_RETRY_BASE_SECONDS,
    TRANSIENT_RUN_ATTEMPTS,
)
from renewables_permitting.extraction.documents import (
    BOESourceDocument,
    PreparedDocumentPrompt,
    build_document_prompt,
    build_source_document,
)
from renewables_permitting.extraction.models import (
    BOEAIExtraction,
    BOEProjectExtraction,
    build_boe_project_extraction,
)
from renewables_permitting.extraction.paths import (
    BOE_AI_EXTRACTIONS_PATH,
    BOE_AI_EXTRACTION_ATTEMPTS_PATH,
    BOE_CANDIDATES_DOCS_TEXT_PATH,
)
from renewables_permitting.extraction.persistence import save_parquet_atomic
from renewables_permitting.extraction.review import (
    _count_extracted_nodes,
    append_ai_extraction_attempts,
    append_quality_metric,
    build_quality_metric,
    build_review_queue,
    empty_manual_reviews,
    load_ai_extraction_attempts,
    normalise_ai_extraction_attempts_log,
    normalise_manual_reviews,
    select_best_valid_extractions,
)
from renewables_permitting.extraction.validation import (
    DocumentExtractionValidationError,
    build_document_validation_retry_prompt,
    validate_extraction_against_document,
)
from renewables_permitting.utils import validate_required_columns


_REQUIRED_INPUT_COLUMNS = {
    "identificador",
    "fecha_publicacion",
    "titulo",
    "xml_status",
    "texto_limpio",
}


def load_and_prepare_candidates(
    input_path: Path = BOE_CANDIDATES_DOCS_TEXT_PATH,
) -> pd.DataFrame:
    candidates = pd.read_parquet(input_path)
    validate_required_columns(candidates, _REQUIRED_INPUT_COLUMNS)
    candidates = candidates.loc[
        candidates["xml_status"].eq("ok")
        & candidates["texto_limpio"].notna()
        & candidates["texto_limpio"].astype("string").str.strip().ne("")
    ].copy()
    candidates["fecha_publicacion"] = pd.to_datetime(
        candidates["fecha_publicacion"], errors="coerce"
    )
    if candidates["fecha_publicacion"].isna().any():
        raise ValueError("Existen candidatos sin fecha_publicacion válida.")
    if candidates["identificador"].duplicated().any():
        duplicated = candidates.loc[
            candidates["identificador"].duplicated(keep=False),
            "identificador",
        ].astype(str).unique().tolist()
        raise ValueError(f"Identificadores BOE duplicados: {duplicated[:20]}")
    candidates["source_document_sha256"] = candidates.apply(
        lambda row: build_source_document(row).source_document_sha256,
        axis=1,
    )
    return candidates


_RETRYABLE_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _usage_values(usage: RunUsage) -> dict[str, int | None]:
    return {
        "usage_requests": getattr(usage, "requests", None),
        "usage_input_tokens": getattr(usage, "input_tokens", None),
        "usage_output_tokens": getattr(usage, "output_tokens", None),
        "usage_total_tokens": getattr(usage, "total_tokens", None),
    }


def _is_retryable_model_error(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return True
    status_code = getattr(error, "status_code", None)
    return status_code in _RETRYABLE_HTTP_STATUS_CODES


async def run_agent_with_transient_retries(
    *,
    agent: Agent,
    prompt: str,
    usage: RunUsage,
):
    for attempt_number in range(1, TRANSIENT_RUN_ATTEMPTS + 1):
        try:
            return await asyncio.wait_for(
                agent.run(
                    prompt,
                    model_settings=MODEL_SETTINGS,
                    usage_limits=UsageLimits(
                        request_limit=MAX_MODEL_REQUESTS_PER_DOCUMENT
                    ),
                    usage=usage,
                ),
                timeout=MODEL_RUN_TIMEOUT_SECONDS,
            )
        except Exception as error:
            if (
                attempt_number == TRANSIENT_RUN_ATTEMPTS
                or not _is_retryable_model_error(error)
            ):
                raise
            await asyncio.sleep(
                TRANSIENT_RETRY_BASE_SECONDS * (2 ** (attempt_number - 1))
            )
    raise RuntimeError("Flujo de reintentos inalcanzable.")


def _base_record(
    *,
    document: BOESourceDocument,
    prepared: PreparedDocumentPrompt | None,
) -> dict[str, Any]:
    return {
        "attempt_id": uuid4().hex,
        "identificador_boe": document.boe_id,
        "fecha_publicacion": pd.Timestamp(document.publication_date),
        "titulo": document.title,
        "source_document_sha256": document.source_document_sha256,
        "input_text_chars": prepared.input_text_chars if prepared else None,
        "input_text_sha256": prepared.input_text_sha256 if prepared else None,
        "input_selection_strategy": prepared.input_selection_strategy if prepared else None,
        "input_selection_marker": prepared.input_selection_marker if prepared else None,
        "input_excluded_chars": prepared.input_excluded_chars if prepared else None,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }


def build_success_record(
    *,
    document: BOESourceDocument,
    prepared: PreparedDocumentPrompt | None,
    extraction: BOEProjectExtraction,
    duration_seconds: float,
    usage: RunUsage,
    adjustments: list[str],
    processing_stage: str = "completed",
) -> dict[str, Any]:
    counts = _count_extracted_nodes(extraction)
    record = {
        **_base_record(document=document, prepared=prepared),
        "classification_status": extraction.classification_status.value,
        "document_scope": extraction.document_scope.value if extraction.document_scope else None,
        "classification_reason": extraction.classification_reason,
        **counts,
        "extraction_json": extraction.model_dump_json(),
        "extracted_at": datetime.now(timezone.utc),
        "duration_seconds": duration_seconds,
        **_usage_values(usage),
        "extraction_status": "ok",
        "error_type": None,
        "error_message": None,
        "processing_stage": processing_stage,
        "document_validation_status": "passed",
        "document_validation_issue_count": 0,
        "validation_issues_json": None,
        "deterministic_adjustment_count": len(adjustments),
        "deterministic_adjustments_json": (
            json.dumps(adjustments, ensure_ascii=False) if adjustments else None
        ),
    }
    return normalise_ai_extraction_attempts_log(pd.DataFrame([record])).iloc[0].to_dict()


def build_error_record(
    *,
    document: BOESourceDocument,
    prepared: PreparedDocumentPrompt | None,
    error: Exception,
    processing_stage: str,
    duration_seconds: float,
    usage: RunUsage,
    extraction: BOEProjectExtraction | None,
    adjustments: list[str],
) -> dict[str, Any]:
    issues = error.issues if isinstance(error, DocumentExtractionValidationError) else []
    counts = _count_extracted_nodes(extraction) if extraction else {
        "n_publication_events": None,
        "n_generation_assets": None,
        "n_associated_components": None,
        "n_administrative_actions": None,
        "n_participants": None,
        "n_administrative_locations": None,
        "n_generation_relations": None,
        "n_technical_mentions": None,
    }
    record = {
        **_base_record(document=document, prepared=prepared),
        "classification_status": extraction.classification_status.value if extraction else None,
        "document_scope": (
            extraction.document_scope.value
            if extraction and extraction.document_scope
            else None
        ),
        "classification_reason": extraction.classification_reason if extraction else None,
        **counts,
        "extraction_json": extraction.model_dump_json() if extraction else None,
        "extracted_at": datetime.now(timezone.utc),
        "duration_seconds": duration_seconds,
        **_usage_values(usage),
        "extraction_status": "error",
        "error_type": type(error).__name__,
        "error_message": str(error)[:100_000],
        "processing_stage": processing_stage,
        "document_validation_status": "failed" if issues else None,
        "document_validation_issue_count": len(issues),
        "validation_issues_json": (
            json.dumps(issues, ensure_ascii=False) if issues else None
        ),
        "deterministic_adjustment_count": len(adjustments),
        "deterministic_adjustments_json": (
            json.dumps(adjustments, ensure_ascii=False) if adjustments else None
        ),
    }
    return normalise_ai_extraction_attempts_log(pd.DataFrame([record])).iloc[0].to_dict()


debug_state: dict[str, Any] = {}


async def extract_documents(
    run_df: pd.DataFrame,
    *,
    agent: Agent,
    attempts_path: Path = BOE_AI_EXTRACTION_ATTEMPTS_PATH,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> list[dict[str, Any]]:
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every debe ser mayor que cero.")

    records: list[dict[str, Any]] = []
    checkpoint: list[dict[str, Any]] = []
    global debug_state

    for position, (_, row) in enumerate(run_df.iterrows(), start=1):
        document = build_source_document(row)
        prepared: PreparedDocumentPrompt | None = None
        project_extraction: BOEProjectExtraction | None = None
        adjustments: list[str] = []
        usage = RunUsage()
        processing_stage = "build_prompt"
        started = perf_counter()
        print(f"[{position}/{len(run_df)}] {document.boe_id}")

        try:
            project_extraction, adjustments = preclassify_document_without_model(
                document
            )
            if project_extraction is not None:
                processing_stage = "deterministic_scope_guard"
                validate_extraction_against_document(
                    document=document,
                    extraction=project_extraction,
                )
                record = build_success_record(
                    document=document,
                    prepared=None,
                    extraction=project_extraction,
                    duration_seconds=perf_counter() - started,
                    usage=usage,
                    adjustments=adjustments,
                    processing_stage=processing_stage,
                )
            else:
                if agent is None:
                    raise RuntimeError(
                        "El documento requiere IA, pero no se ha construido el agente. "
                        "Instala pydantic-ai y configura el proveedor."
                    )
                prepared = build_document_prompt(document)
                original_prompt = prepared.prompt
                effective_prompt = original_prompt
                validation_retry_count = 0

                while True:
                    remaining = DOCUMENT_TIMEOUT_SECONDS - (perf_counter() - started)
                    if remaining <= 0:
                        raise TimeoutError(
                            f"{document.boe_id} superó {DOCUMENT_TIMEOUT_SECONDS:.0f} s."
                        )

                    processing_stage = "agent_run"
                    result = await asyncio.wait_for(
                        run_agent_with_transient_retries(
                            agent=agent,
                            prompt=effective_prompt,
                            usage=usage,
                        ),
                        timeout=remaining,
                    )
                    ai_extraction = result.output
                    if not isinstance(ai_extraction, BOEAIExtraction):
                        raise TypeError("El agente no devolvió BOEAIExtraction.")

                    processing_stage = "canonicalization"
                    project_extraction = build_boe_project_extraction(
                        ai_extraction,
                        boe_id=document.boe_id,
                        publication_date=document.publication_date,
                    )
                    project_extraction, adjustments = canonicalize_project_extraction(
                        project_extraction,
                        source_text=f"{document.title}\n{document.text}",
                        document_title=document.title,
                    )

                    processing_stage = "document_validation"
                    try:
                        validate_extraction_against_document(
                            document=document,
                            extraction=project_extraction,
                        )
                    except DocumentExtractionValidationError as validation_error:
                        can_retry = (
                            validation_retry_count < DOCUMENT_VALIDATION_RETRY_ATTEMPTS
                            and getattr(usage, "requests", 0)
                            < MAX_MODEL_REQUESTS_PER_DOCUMENT
                        )
                        if not can_retry:
                            raise
                        validation_retry_count += 1
                        effective_prompt = build_document_validation_retry_prompt(
                            original_prompt=original_prompt,
                            validation_error=validation_error,
                        )
                        continue
                    break

                record = build_success_record(
                    document=document,
                    prepared=prepared,
                    extraction=project_extraction,
                    duration_seconds=perf_counter() - started,
                    usage=usage,
                    adjustments=adjustments,
                    processing_stage="completed",
                )
            print(
                "  OK "
                f"events={record['n_publication_events']}, "
                f"plants={record['n_generation_assets']}, "
                f"components={record['n_associated_components']}, "
                f"actions={record['n_administrative_actions']}"
            )
        except Exception as error:
            record = build_error_record(
                document=document,
                prepared=prepared,
                error=error,
                processing_stage=processing_stage,
                duration_seconds=perf_counter() - started,
                usage=usage,
                extraction=project_extraction,
                adjustments=adjustments,
            )
            print(f"  ERROR {type(error).__name__}: {error}")

        debug_state = {
            "document": document,
            "prepared_prompt": prepared,
            "project_extraction": project_extraction,
            "adjustments": adjustments,
            "record": record,
        }
        records.append(record)
        checkpoint.append(record)
        if len(checkpoint) >= checkpoint_every or position == len(run_df):
            append_ai_extraction_attempts(pd.DataFrame(checkpoint), attempts_path)
            checkpoint.clear()

    return records


async def run_and_finalize_extractions(
    run_df: pd.DataFrame,
    source_df: pd.DataFrame,
    *,
    agent: Agent,
    attempts_path: Path = BOE_AI_EXTRACTION_ATTEMPTS_PATH,
    current_path: Path = BOE_AI_EXTRACTIONS_PATH,
    review_queue_path: Path | None = None,
    quality_metrics_path: Path | None = None,
    manual_reviews: pd.DataFrame | None = None,
    run_scope: str = "production",
    minimum_auto_validation_rate: float = 0.95,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> dict[str, pd.DataFrame]:
    records = await extract_documents(
        run_df,
        agent=agent,
        attempts_path=attempts_path,
        checkpoint_every=checkpoint_every,
    )
    attempts = load_ai_extraction_attempts(attempts_path)
    manual_reviews = (
        empty_manual_reviews()
        if manual_reviews is None
        else normalise_manual_reviews(manual_reviews)
    )
    current = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )
    save_parquet_atomic(current, current_path)

    review_queue = build_review_queue(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )
    if review_queue_path is not None:
        save_parquet_atomic(review_queue, review_queue_path)

    quality_metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
        run_scope=run_scope,
        minimum_auto_validation_rate=minimum_auto_validation_rate,
    )
    if quality_metrics_path is not None:
        append_quality_metric(quality_metric, quality_metrics_path)

    return {
        "new_attempts": normalise_ai_extraction_attempts_log(pd.DataFrame(records)),
        "all_attempts": attempts,
        "current_extractions": current,
        "review_queue": review_queue,
        "quality_metric": quality_metric,
    }


def get_extraction_model(
    current_extractions: pd.DataFrame,
    boe_id: str,
) -> BOEProjectExtraction:
    rows = current_extractions.loc[
        current_extractions["identificador_boe"].astype(str).eq(boe_id)
        & current_extractions["extraction_status"].eq("ok")
        & current_extractions["document_validation_status"].eq("passed")
        & current_extractions["document_validation_version"].eq(
            DOCUMENT_VALIDATION_VERSION
        )
    ]
    if len(rows) != 1:
        raise ValueError(
            f"Se esperaba una extracción vigente para {boe_id!r}; encontradas={len(rows)}."
        )
    return BOEProjectExtraction.model_validate_json(
        str(rows.iloc[0]["extraction_json"])
    )
