from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd

from renewables_permitting.extraction.agent import Agent, RunUsage, UsageLimits
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
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
)
from renewables_permitting.extraction.models import BOEProjectExtraction
from renewables_permitting.extraction.review import (
    _count_extracted_nodes,
    normalise_ai_extraction_attempts_log,
)
from renewables_permitting.extraction.validation import (
    DocumentExtractionValidationError,
)


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
