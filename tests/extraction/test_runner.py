import ast
import asyncio
import copy
from dataclasses import asdict
from datetime import date, datetime, timezone
from inspect import iscoroutinefunction, signature
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError

import renewables_permitting.extraction.runner as runner_module
from renewables_permitting.extraction.agent import RunUsage
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
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    AdministrativeLocationLevel,
    AdministrativeLocationMention,
    AssociatedComponent,
    AssociatedComponentType,
    BOEProjectExtraction,
    BOESourceDocument,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationAssetRelation,
    GenerationRelationType,
    GenerationType,
    ParticipantMention,
    ParticipantRole,
    PreparedDocumentPrompt,
    PublicationEvent,
    TechnicalAttributeType,
    TechnicalMention,
)
from renewables_permitting.extraction.review import AI_EXTRACTION_LOG_COLUMNS
from renewables_permitting.extraction.runner import (
    _RETRYABLE_HTTP_STATUS_CODES,
    _base_record,
    _is_retryable_model_error,
    _usage_values,
    build_error_record,
    build_success_record,
    get_extraction_model,
    run_agent_with_transient_retries,
)
from renewables_permitting.extraction.validation import (
    DocumentExtractionValidationError,
)


_FIXED_NOW = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
_FIXED_ATTEMPT_ID = "0123456789abcdef0123456789abcdef"


class _FrozenDateTime:
    @classmethod
    def now(cls, tz):
        assert tz is timezone.utc
        return _FIXED_NOW


class _FixedUUID:
    hex = _FIXED_ATTEMPT_ID


class _FakeAgent:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def run(
        self,
        prompt,
        *,
        model_settings,
        usage_limits,
        usage,
    ):
        self.calls.append({
            "prompt": prompt,
            "model_settings": model_settings,
            "usage_limits": usage_limits,
            "usage": usage,
        })
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _run_with_controlled_asyncio(monkeypatch, *, agent, prompt, usage):
    wait_for_timeouts = []
    sleep_delays = []

    async def fake_wait_for(awaitable, *, timeout):
        wait_for_timeouts.append(timeout)
        return await awaitable

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)
    result = asyncio.run(
        run_agent_with_transient_retries(
            agent=agent,
            prompt=prompt,
            usage=usage,
        )
    )
    return result, wait_for_timeouts, sleep_delays


def _document() -> BOESourceDocument:
    return BOESourceDocument(
        boe_id="BOE-A-2026-12345",
        publication_date=date(2026, 1, 2),
        title="Resolución de la planta fotovoltaica Aurora.",
        text="Texto íntegro de la planta fotovoltaica Aurora.",
        source_document_sha256="source-document-sha256",
    )


def _prepared() -> PreparedDocumentPrompt:
    return PreparedDocumentPrompt(
        prompt="PROMPT DOCUMENTAL",
        input_text_chars=51,
        input_text_sha256="input-text-sha256",
        input_selection_strategy="before_affected_assets_annex",
        input_selection_marker="ANEXO RELACIÓN DE BIENES",
        input_excluded_chars=17,
    )


def _extraction() -> BOEProjectExtraction:
    evidence = "Resolución de la planta fotovoltaica Aurora."
    event = PublicationEvent(
        generation_assets=[
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=["Aurora"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                        value_raw="50 MW",
                        evidence=evidence,
                    ),
                ],
                evidence=evidence,
            ),
            GenerationAssetMention(
                local_generation_asset_ref="generation_asset_2",
                names_raw=["Aurora II"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[],
                evidence=evidence,
            ),
        ],
        associated_components=[
            AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.POWER_LINE,
                names_raw=["LAT Aurora"],
                description_raw="Línea aérea de evacuación.",
                related_generation_asset_refs=["generation_asset_1"],
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.VOLTAGE,
                        value_raw="220 kV",
                        evidence=evidence,
                    ),
                ],
                evidence=evidence,
            ),
        ],
        administrative_actions=[
            AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                is_modification=False,
                targets=["generation_asset_1", "component_1"],
                evidence=evidence,
            ),
        ],
        participants=[
            ParticipantMention(
                participant_name_raw="Aurora Renovables, S.L.",
                participant_role=ParticipantRole.PROMOTER,
                evidence=evidence,
            ),
        ],
        administrative_locations=[
            AdministrativeLocationMention(
                location_name_raw="Villa Solar",
                location_level=AdministrativeLocationLevel.MUNICIPALITY,
                province_hint_raw="Las Palmas",
                autonomous_community_hint_raw="Canarias",
                evidence=evidence,
            ),
        ],
        generation_relations=[
            GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_2",
                relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                evidence=evidence,
            ),
        ],
        case_file_references=["PFot-123"],
        event_summary="Autorización de Aurora y Aurora II.",
    )
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de generación.",
        publication_events=[event],
        extraction_notes="Extracción de prueba.",
        boe_id="BOE-A-2026-12345",
        publication_date=date(2026, 1, 2),
    )


def _usage_double():
    return SimpleNamespace(
        requests=3,
        input_tokens=101,
        output_tokens=29,
        total_tokens=130,
    )


def _freeze_record_variability(monkeypatch) -> None:
    monkeypatch.setattr(runner_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(runner_module, "uuid4", lambda: _FixedUUID())


def _expected_base_record(
    document: BOESourceDocument,
    prepared: PreparedDocumentPrompt | None,
) -> dict:
    return {
        "attempt_id": _FIXED_ATTEMPT_ID,
        "identificador_boe": document.boe_id,
        "fecha_publicacion": pd.Timestamp(document.publication_date),
        "titulo": document.title,
        "source_document_sha256": document.source_document_sha256,
        "input_text_chars": prepared.input_text_chars if prepared else None,
        "input_text_sha256": prepared.input_text_sha256 if prepared else None,
        "input_selection_strategy": (
            prepared.input_selection_strategy if prepared else None
        ),
        "input_selection_marker": (
            prepared.input_selection_marker if prepared else None
        ),
        "input_excluded_chars": prepared.input_excluded_chars if prepared else None,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }


def test_usage_values_reads_exact_fields_from_run_usage_without_mutation() -> None:
    usage = RunUsage(requests=2, input_tokens=11, output_tokens=7)
    before = copy.deepcopy(usage)

    values = _usage_values(usage)

    assert values == {
        "usage_requests": usage.requests,
        "usage_input_tokens": usage.input_tokens,
        "usage_output_tokens": usage.output_tokens,
        "usage_total_tokens": usage.total_tokens,
    }
    assert list(values) == [
        "usage_requests",
        "usage_input_tokens",
        "usage_output_tokens",
        "usage_total_tokens",
    ]
    assert usage == before


def test_usage_values_returns_none_for_none_and_missing_attributes() -> None:
    expected = {
        "usage_requests": None,
        "usage_input_tokens": None,
        "usage_output_tokens": None,
        "usage_total_tokens": None,
    }

    assert _usage_values(None) == expected
    assert _usage_values(object()) == expected


def test_retryable_http_status_codes_are_exact() -> None:
    assert _RETRYABLE_HTTP_STATUS_CODES == {
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    }


@pytest.mark.parametrize(
    "status_code",
    [408, 425, 429, 500, 502, 503, 504],
)
def test_installed_model_http_errors_with_retryable_codes_are_retried(
    status_code: int,
) -> None:
    error = ModelHTTPError(
        status_code=status_code,
        model_name="test:model",
        body={"error": "transient"},
    )

    assert _is_retryable_model_error(error) is True


@pytest.mark.parametrize(
    "status_code",
    [200, 400, 401, 403, 404, 409, 422, 501, 505],
)
def test_installed_model_http_errors_with_other_codes_are_not_retried(
    status_code: int,
) -> None:
    error = ModelHTTPError(
        status_code=status_code,
        model_name="test:model",
        body=None,
    )

    assert _is_retryable_model_error(error) is False


@pytest.mark.parametrize("error", [TimeoutError(), asyncio.TimeoutError()])
def test_timeouts_are_retryable(error: Exception) -> None:
    assert _is_retryable_model_error(error) is True


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid"),
        RuntimeError("unknown"),
        SimpleNamespace(status_code=None),
        SimpleNamespace(status_code="429"),
    ],
)
def test_unknown_or_statusless_errors_are_not_retryable(error) -> None:
    assert _is_retryable_model_error(error) is False


def test_agent_success_on_first_attempt_has_exact_call_arguments(monkeypatch) -> None:
    expected_result = object()
    usage = RunUsage()
    agent = _FakeAgent([expected_result])

    result, timeouts, sleeps = _run_with_controlled_asyncio(
        monkeypatch,
        agent=agent,
        prompt="PROMPT",
        usage=usage,
    )

    assert result is expected_result
    assert timeouts == [MODEL_RUN_TIMEOUT_SECONDS]
    assert sleeps == []
    assert len(agent.calls) == 1
    assert agent.calls[0]["prompt"] == "PROMPT"
    assert agent.calls[0]["model_settings"] is MODEL_SETTINGS
    assert agent.calls[0]["usage"] is usage
    assert (
        agent.calls[0]["usage_limits"].request_limit
        == MAX_MODEL_REQUESTS_PER_DOCUMENT
    )


def test_transient_model_http_error_then_success(monkeypatch) -> None:
    transient_error = ModelHTTPError(429, "test:model", {"retry": True})
    expected_result = {"output": "ok"}
    usage = RunUsage()
    agent = _FakeAgent([transient_error, expected_result])

    result, timeouts, sleeps = _run_with_controlled_asyncio(
        monkeypatch,
        agent=agent,
        prompt="PROMPT",
        usage=usage,
    )

    assert result is expected_result
    assert len(agent.calls) == 2
    assert timeouts == [MODEL_RUN_TIMEOUT_SECONDS] * 2
    assert sleeps == [TRANSIENT_RETRY_BASE_SECONDS]
    assert all(call["usage"] is usage for call in agent.calls)
    assert all(call["model_settings"] is MODEL_SETTINGS for call in agent.calls)
    assert [
        call["usage_limits"].request_limit for call in agent.calls
    ] == [MAX_MODEL_REQUESTS_PER_DOCUMENT] * 2


def test_multiple_transient_errors_then_success_use_exponential_backoff(
    monkeypatch,
) -> None:
    monkeypatch.setattr(runner_module, "TRANSIENT_RUN_ATTEMPTS", 4)
    expected_result = "completed"
    agent = _FakeAgent([
        TimeoutError("first"),
        ModelHTTPError(503, "test:model"),
        ModelHTTPError(504, "test:model"),
        expected_result,
    ])

    result, timeouts, sleeps = _run_with_controlled_asyncio(
        monkeypatch,
        agent=agent,
        prompt="PROMPT",
        usage=RunUsage(),
    )

    assert result == expected_result
    assert len(agent.calls) == 4
    assert timeouts == [MODEL_RUN_TIMEOUT_SECONDS] * 4
    assert sleeps == [
        TRANSIENT_RETRY_BASE_SECONDS,
        TRANSIENT_RETRY_BASE_SECONDS * 2,
        TRANSIENT_RETRY_BASE_SECONDS * 4,
    ]


def test_exhausted_transient_attempts_raise_last_error(monkeypatch) -> None:
    first_error = ModelHTTPError(500, "test:model", "first")
    last_error = ModelHTTPError(502, "test:model", "last")
    agent = _FakeAgent([first_error, last_error])
    wait_for_timeouts = []
    sleep_delays = []

    async def fake_wait_for(awaitable, *, timeout):
        wait_for_timeouts.append(timeout)
        return await awaitable

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(ModelHTTPError) as error_info:
        asyncio.run(
            run_agent_with_transient_retries(
                agent=agent,
                prompt="PROMPT",
                usage=RunUsage(),
            )
        )

    assert error_info.value is last_error
    assert len(agent.calls) == TRANSIENT_RUN_ATTEMPTS
    assert wait_for_timeouts == [MODEL_RUN_TIMEOUT_SECONDS] * TRANSIENT_RUN_ATTEMPTS
    assert sleep_delays == [TRANSIENT_RETRY_BASE_SECONDS]


def test_non_retryable_error_is_raised_immediately(monkeypatch) -> None:
    expected_error = ModelHTTPError(400, "test:model", "bad request")
    agent = _FakeAgent([expected_error])
    sleep_delays = []

    async def fake_wait_for(awaitable, *, timeout):
        assert timeout == MODEL_RUN_TIMEOUT_SECONDS
        return await awaitable

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(ModelHTTPError) as error_info:
        asyncio.run(
            run_agent_with_transient_retries(
                agent=agent,
                prompt="PROMPT",
                usage=RunUsage(),
            )
        )

    assert error_info.value is expected_error
    assert len(agent.calls) == 1
    assert sleep_delays == []


def test_timeout_then_success_is_retried_without_real_wait(monkeypatch) -> None:
    expected_result = SimpleNamespace(output="ok")
    agent = _FakeAgent([TimeoutError("timeout"), expected_result])

    result, timeouts, sleeps = _run_with_controlled_asyncio(
        monkeypatch,
        agent=agent,
        prompt="PROMPT",
        usage=RunUsage(),
    )

    assert result is expected_result
    assert len(agent.calls) == 2
    assert timeouts == [MODEL_RUN_TIMEOUT_SECONDS] * 2
    assert sleeps == [TRANSIENT_RETRY_BASE_SECONDS]


def test_retry_loop_with_one_configured_attempt_never_sleeps(monkeypatch) -> None:
    monkeypatch.setattr(runner_module, "TRANSIENT_RUN_ATTEMPTS", 1)
    expected_error = TimeoutError("timeout")
    agent = _FakeAgent([expected_error])
    sleep_delays = []

    async def fake_wait_for(awaitable, *, timeout):
        assert timeout == MODEL_RUN_TIMEOUT_SECONDS
        return await awaitable

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(runner_module.asyncio, "wait_for", fake_wait_for)
    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(TimeoutError) as error_info:
        asyncio.run(
            run_agent_with_transient_retries(
                agent=agent,
                prompt="PROMPT",
                usage=RunUsage(),
            )
        )

    assert error_info.value is expected_error
    assert len(agent.calls) == 1
    assert sleep_delays == []


def test_base_record_has_exact_keys_order_and_values(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)
    document = _document()
    prepared = _prepared()

    record = _base_record(document=document, prepared=prepared)

    expected = _expected_base_record(document, prepared)
    assert record == expected
    assert list(record) == list(expected)


def test_base_record_uses_exact_nulls_without_prepared_prompt(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)
    document = _document()

    record = _base_record(document=document, prepared=None)

    assert record == _expected_base_record(document, None)
    assert record["input_text_chars"] is None
    assert record["input_text_sha256"] is None
    assert record["input_selection_strategy"] is None
    assert record["input_selection_marker"] is None
    assert record["input_excluded_chars"] is None


def test_complete_success_record_matches_contract_and_values(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)
    document = _document()
    prepared = _prepared()
    extraction = _extraction()
    usage = _usage_double()
    adjustments = ["Ajuste uno.", "Ajuste ñ."]

    record = build_success_record(
        document=document,
        prepared=prepared,
        extraction=extraction,
        duration_seconds=1.25,
        usage=usage,
        adjustments=adjustments,
        processing_stage="deterministic_scope_guard",
    )

    expected = {
        **_expected_base_record(document, prepared),
        "classification_status": "classified",
        "document_scope": "generation_project_specific",
        "classification_reason": "Publicación específica de generación.",
        "n_publication_events": 1,
        "n_generation_assets": 2,
        "n_associated_components": 1,
        "n_administrative_actions": 1,
        "n_participants": 1,
        "n_administrative_locations": 1,
        "n_generation_relations": 1,
        "n_technical_mentions": 2,
        "extraction_json": extraction.model_dump_json(),
        "extracted_at": pd.Timestamp(_FIXED_NOW),
        "duration_seconds": 1.25,
        "usage_requests": 3,
        "usage_input_tokens": 101,
        "usage_output_tokens": 29,
        "usage_total_tokens": 130,
        "extraction_status": "ok",
        "error_type": None,
        "error_message": None,
        "processing_stage": "deterministic_scope_guard",
        "document_validation_status": "passed",
        "document_validation_issue_count": 0,
        "validation_issues_json": None,
        "deterministic_adjustment_count": 2,
        "deterministic_adjustments_json": '["Ajuste uno.", "Ajuste ñ."]',
    }
    assert record == expected
    assert list(record) == AI_EXTRACTION_LOG_COLUMNS
    assert record["extraction_json"] == extraction.model_dump_json()


def test_success_record_default_stage_and_empty_adjustments(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)

    record = build_success_record(
        document=_document(),
        prepared=None,
        extraction=_extraction(),
        duration_seconds=0.0,
        usage=SimpleNamespace(),
        adjustments=[],
    )

    assert record["processing_stage"] == "completed"
    assert record["deterministic_adjustment_count"] == 0
    assert record["deterministic_adjustments_json"] is None
    assert record["usage_requests"] is None
    assert record["usage_input_tokens"] is None
    assert record["usage_output_tokens"] is None
    assert record["usage_total_tokens"] is None


def test_complete_error_record_without_extraction_matches_contract(
    monkeypatch,
) -> None:
    _freeze_record_variability(monkeypatch)
    document = _document()
    error = RuntimeError("falló el modelo")

    record = build_error_record(
        document=document,
        prepared=None,
        error=error,
        processing_stage="agent_run",
        duration_seconds=9.5,
        usage=_usage_double(),
        extraction=None,
        adjustments=[],
    )

    expected = {
        **_expected_base_record(document, None),
        "classification_status": None,
        "document_scope": None,
        "classification_reason": None,
        "n_publication_events": None,
        "n_generation_assets": None,
        "n_associated_components": None,
        "n_administrative_actions": None,
        "n_participants": None,
        "n_administrative_locations": None,
        "n_generation_relations": None,
        "n_technical_mentions": None,
        "extraction_json": None,
        "extracted_at": pd.Timestamp(_FIXED_NOW),
        "duration_seconds": 9.5,
        "usage_requests": 3,
        "usage_input_tokens": 101,
        "usage_output_tokens": 29,
        "usage_total_tokens": 130,
        "extraction_status": "error",
        "error_type": "RuntimeError",
        "error_message": "falló el modelo",
        "processing_stage": "agent_run",
        "document_validation_status": None,
        "document_validation_issue_count": 0,
        "validation_issues_json": None,
        "deterministic_adjustment_count": 0,
        "deterministic_adjustments_json": None,
    }
    assert record == expected
    assert list(record) == AI_EXTRACTION_LOG_COLUMNS


def test_validation_error_record_preserves_extraction_issues_and_adjustments(
    monkeypatch,
) -> None:
    _freeze_record_variability(monkeypatch)
    extraction = _extraction()
    issues = ["Evidencia ausente.", "Referencia incompatible: ñ."]
    error = DocumentExtractionValidationError(issues)

    record = build_error_record(
        document=_document(),
        prepared=_prepared(),
        error=error,
        processing_stage="document_validation",
        duration_seconds=2.0,
        usage=_usage_double(),
        extraction=extraction,
        adjustments=["Corrección determinista."],
    )

    assert record["classification_status"] == "classified"
    assert record["document_scope"] == "generation_project_specific"
    assert record["classification_reason"] == extraction.classification_reason
    assert record["n_publication_events"] == 1
    assert record["n_generation_assets"] == 2
    assert record["n_associated_components"] == 1
    assert record["n_administrative_actions"] == 1
    assert record["n_participants"] == 1
    assert record["n_administrative_locations"] == 1
    assert record["n_generation_relations"] == 1
    assert record["n_technical_mentions"] == 2
    assert record["extraction_json"] == extraction.model_dump_json()
    assert record["error_type"] == "DocumentExtractionValidationError"
    assert record["error_message"] == "; ".join(issues)
    assert record["document_validation_status"] == "failed"
    assert record["document_validation_issue_count"] == 2
    assert record["validation_issues_json"] == (
        '["Evidencia ausente.", "Referencia incompatible: ñ."]'
    )
    assert record["deterministic_adjustment_count"] == 1
    assert record["deterministic_adjustments_json"] == (
        '["Corrección determinista."]'
    )
    assert list(record) == AI_EXTRACTION_LOG_COLUMNS


def test_error_without_message_is_preserved_as_empty_string(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)

    record = build_error_record(
        document=_document(),
        prepared=None,
        error=RuntimeError(),
        processing_stage="agent_run",
        duration_seconds=0.1,
        usage=_usage_double(),
        extraction=None,
        adjustments=[],
    )

    assert record["error_message"] == ""


def test_error_message_is_truncated_at_exact_contract_limit(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)

    record = build_error_record(
        document=_document(),
        prepared=None,
        error=RuntimeError("x" * 100_001),
        processing_stage="agent_run",
        duration_seconds=0.1,
        usage=_usage_double(),
        extraction=None,
        adjustments=[],
    )

    assert record["error_message"] == "x" * 100_000


def test_record_builders_do_not_mutate_any_received_argument(monkeypatch) -> None:
    _freeze_record_variability(monkeypatch)
    document = _document()
    prepared = _prepared()
    extraction = _extraction()
    usage = _usage_double()
    adjustments = ["Ajuste."]
    error = DocumentExtractionValidationError(["Issue ñ."])
    before = {
        "document": asdict(document),
        "prepared": asdict(prepared),
        "extraction": extraction.model_dump_json(),
        "usage": copy.deepcopy(vars(usage)),
        "adjustments": copy.deepcopy(adjustments),
        "issues": copy.deepcopy(error.issues),
    }

    build_success_record(
        document=document,
        prepared=prepared,
        extraction=extraction,
        duration_seconds=1.0,
        usage=usage,
        adjustments=adjustments,
    )
    build_error_record(
        document=document,
        prepared=prepared,
        error=error,
        processing_stage="document_validation",
        duration_seconds=1.0,
        usage=usage,
        extraction=extraction,
        adjustments=adjustments,
    )

    assert asdict(document) == before["document"]
    assert asdict(prepared) == before["prepared"]
    assert extraction.model_dump_json() == before["extraction"]
    assert vars(usage) == before["usage"]
    assert adjustments == before["adjustments"]
    assert error.issues == before["issues"]


def _current_row(
    extraction: BOEProjectExtraction,
    **overrides,
) -> dict:
    row = {
        "identificador_boe": extraction.boe_id,
        "extraction_status": "ok",
        "document_validation_status": "passed",
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "extraction_json": extraction.model_dump_json(),
    }
    row.update(overrides)
    return row


def test_get_extraction_model_filters_and_deserializes_exact_model() -> None:
    extraction = _extraction()
    current = pd.DataFrame([
        _current_row(
            extraction,
            identificador_boe="BOE-A-2026-99999",
        ),
        _current_row(
            extraction,
            extraction_status="error",
        ),
        _current_row(
            extraction,
            document_validation_status="failed",
        ),
        _current_row(
            extraction,
            document_validation_version="24",
        ),
        _current_row(extraction),
    ])
    before = current.copy(deep=True)

    result = get_extraction_model(current, extraction.boe_id)

    assert result == extraction
    assert result is not extraction
    pd.testing.assert_frame_equal(current, before)


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_current_row(_extraction()), _current_row(_extraction())],
    ],
)
def test_get_extraction_model_requires_exactly_one_current_row(rows) -> None:
    boe_id = _extraction().boe_id
    current = pd.DataFrame(
        rows,
        columns=[
            "identificador_boe",
            "extraction_status",
            "document_validation_status",
            "document_validation_version",
            "extraction_json",
        ],
    )

    with pytest.raises(
        ValueError,
        match=(
            rf"Se esperaba una extracción vigente para '{boe_id}'; "
            rf"encontradas={len(rows)}\."
        ),
    ):
        get_extraction_model(current, boe_id)


def test_get_extraction_model_propagates_contract_validation_error() -> None:
    extraction = _extraction()
    current = pd.DataFrame([
        _current_row(extraction, extraction_json='{"invalid": true}'),
    ])

    with pytest.raises(ValidationError):
        get_extraction_model(current, extraction.boe_id)


def test_get_extraction_model_does_not_add_fallback_for_missing_columns() -> None:
    with pytest.raises(KeyError, match="identificador_boe"):
        get_extraction_model(pd.DataFrame(), "BOE-A-2026-12345")


def test_runner_public_call_signatures_are_stable() -> None:
    assert iscoroutinefunction(run_agent_with_transient_retries)
    assert tuple(signature(run_agent_with_transient_retries).parameters) == (
        "agent",
        "prompt",
        "usage",
    )
    assert tuple(signature(build_success_record).parameters) == (
        "document",
        "prepared",
        "extraction",
        "duration_seconds",
        "usage",
        "adjustments",
        "processing_stage",
    )
    assert tuple(signature(build_error_record).parameters) == (
        "document",
        "prepared",
        "error",
        "processing_stage",
        "duration_seconds",
        "usage",
        "extraction",
        "adjustments",
    )
    assert tuple(signature(get_extraction_model).parameters) == (
        "current_extractions",
        "boe_id",
    )


def test_runner_import_surface_has_no_agent_or_top_level_execution() -> None:
    # AST is intentional: the runner import boundary forbids orchestration at
    # module load time, which cannot be proven from one observed import alone.
    source = Path(runner_module.__file__).read_text()
    tree = ast.parse(source)

    assert not hasattr(runner_module, "agent")
    assert [
        node
        for node in tree.body
        if not isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.Assign,
                ast.AnnAssign,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
    ] == []
    assert not any(
        isinstance(node, (ast.For, ast.While, ast.With, ast.Try))
        for node in tree.body
    )
    assert hasattr(runner_module, "extract_documents")
    assert runner_module.debug_state == {}
    assert hasattr(runner_module, "run_and_finalize_extractions")
    assert "ModelHTTPError" not in source
    assert "random" not in source
