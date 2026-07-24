import ast
import asyncio
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import renewables_permitting.extraction.runner as runner_module
from renewables_permitting.extraction.agent import RunUsage
from renewables_permitting.extraction.config import (
    DOCUMENT_TIMEOUT_SECONDS,
    DOCUMENT_VALIDATION_RETRY_ATTEMPTS,
    MAX_MODEL_REQUESTS_PER_DOCUMENT,
)
from renewables_permitting.extraction.documents import (
    build_document_prompt,
    build_source_document,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    BOEAIExtraction,
    BOEProjectExtraction,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationType,
    PublicationEvent,
)
from renewables_permitting.extraction.runner import (
    _REQUIRED_INPUT_COLUMNS,
    extract_documents,
    load_and_prepare_candidates,
)
from renewables_permitting.extraction.validation import (
    DocumentExtractionValidationError,
    build_document_validation_retry_prompt,
)


_FIXED_NOW = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)


class _FrozenDateTime:
    @classmethod
    def now(cls, tz):
        assert tz is timezone.utc
        return _FIXED_NOW


class _FixedUUID:
    def __init__(self, value: str):
        self.hex = value


def _candidate_row(
    boe_id: str,
    *,
    publication_date="2026-01-02",
    title: str | None = None,
    xml_status="ok",
    text: object = None,
    extra: object = "extra",
) -> dict:
    effective_title = title or f"Resolución de la planta fotovoltaica {boe_id}."
    effective_text = effective_title if text is None else text
    return {
        "identificador": boe_id,
        "fecha_publicacion": publication_date,
        "titulo": effective_title,
        "xml_status": xml_status,
        "texto_limpio": effective_text,
        "extra_column": extra,
    }


def _candidate_frame(*boe_ids: str) -> pd.DataFrame:
    return pd.DataFrame([_candidate_row(boe_id) for boe_id in boe_ids])


def _source_hash(row: pd.Series) -> str:
    document = build_source_document(row)
    return document.source_document_sha256


def _not_relevant_project(
    boe_id: str,
    publication_date: date = date(2026, 1, 2),
) -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS,
        classification_reason="El objeto principal no es generación.",
        publication_events=[],
        extraction_notes=None,
        boe_id=boe_id,
        publication_date=publication_date,
    )


def _ai_extraction(name: str = "Aurora") -> BOEAIExtraction:
    evidence = f"Resolución de la planta fotovoltaica {name}."
    return BOEAIExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de generación.",
        publication_events=[
            PublicationEvent(
                generation_assets=[
                    GenerationAssetMention(
                        local_generation_asset_ref="generation_asset_1",
                        names_raw=[name],
                        generation_type=GenerationType.PHOTOVOLTAIC,
                        technical_mentions=[],
                        evidence=evidence,
                    ),
                ],
                associated_components=[],
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
                ],
                participants=[],
                administrative_locations=[],
                generation_relations=[],
                case_file_references=[],
                event_summary=f"Autorización de {name}.",
            ),
        ],
        extraction_notes=None,
    )


def _install_no_checkpoint_writer(monkeypatch):
    calls = []

    def fake_append(dataframe, path):
        calls.append({
            "dataframe": dataframe,
            "snapshot": dataframe.copy(deep=True),
            "path": path,
        })
        return dataframe

    monkeypatch.setattr(
        runner_module,
        "append_ai_extraction_attempts",
        fake_append,
    )
    return calls


def _install_immediate_wait_for(monkeypatch):
    timeouts = []

    async def fake_wait_for(awaitable, *, timeout):
        timeouts.append(timeout)
        return await awaitable

    monkeypatch.setattr(runner_module.asyncio, "wait_for", fake_wait_for)
    return timeouts


def _install_fixed_record_values(monkeypatch, *, perf_values, uuid_values):
    perf_iterator = iter(perf_values)
    uuid_iterator = iter(uuid_values)
    monkeypatch.setattr(runner_module, "perf_counter", lambda: next(perf_iterator))
    monkeypatch.setattr(runner_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(
        runner_module,
        "uuid4",
        lambda: _FixedUUID(next(uuid_iterator)),
    )


def _project_from_ai(
    ai_extraction: BOEAIExtraction,
    row: pd.Series,
) -> BOEProjectExtraction:
    return BOEProjectExtraction(
        **ai_extraction.model_dump(),
        boe_id=str(row["identificador"]),
        publication_date=pd.Timestamp(row["fecha_publicacion"]).date(),
    )


def test_required_candidate_columns_are_exact() -> None:
    assert _REQUIRED_INPUT_COLUMNS == {
        "identificador",
        "fecha_publicacion",
        "titulo",
        "xml_status",
        "texto_limpio",
    }


def test_load_candidates_filters_rows_preserves_order_columns_and_extra_data(
    tmp_path,
) -> None:
    input_path = tmp_path / "candidates.parquet"
    candidates = pd.DataFrame(
        [
            _candidate_row(
                "BOE-A-2026-10003",
                publication_date="2026-01-03",
                extra="kept-3",
            ),
            _candidate_row(
                "BOE-A-2026-10001",
                publication_date="2026-01-01",
                extra="kept-1",
            ),
            _candidate_row(
                "BOE-A-2026-10004",
                xml_status="error",
                extra="filtered-status",
            ),
            _candidate_row(
                "BOE-A-2026-10005",
                text=pd.NA,
                extra="filtered-null",
            ),
            _candidate_row(
                "BOE-A-2026-10006",
                text=" \t\n ",
                extra="filtered-blank",
            ),
        ],
        index=[30, 10, 40, 50, 60],
    )
    candidates.to_parquet(input_path)
    original_bytes = input_path.read_bytes()
    original_entries = sorted(path.name for path in tmp_path.iterdir())

    result = load_and_prepare_candidates(input_path)

    assert result.index.tolist() == [30, 10]
    assert result["identificador"].tolist() == [
        "BOE-A-2026-10003",
        "BOE-A-2026-10001",
    ]
    assert result.columns.tolist() == [
        *candidates.columns.tolist(),
        "source_document_sha256",
    ]
    assert result["extra_column"].tolist() == [
        "kept-3",
        "kept-1",
    ]
    assert result["fecha_publicacion"].dtype == pd.to_datetime(
        pd.Series(["2026-01-03", "2026-01-01"])
    ).dtype
    assert result["fecha_publicacion"].tolist() == [
        pd.Timestamp("2026-01-03"),
        pd.Timestamp("2026-01-01"),
    ]
    expected_hashes = [
        _source_hash(result.loc[30]),
        _source_hash(result.loc[10]),
    ]
    assert result["source_document_sha256"].tolist() == expected_hashes
    assert input_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == original_entries


def test_load_candidates_does_not_modify_input_dataframe_or_parquet(
    tmp_path,
) -> None:
    input_path = tmp_path / "source.parquet"
    candidates = _candidate_frame("BOE-A-2026-10101")
    before = candidates.copy(deep=True)
    candidates.to_parquet(input_path)
    source_bytes = input_path.read_bytes()

    load_and_prepare_candidates(input_path)

    pd.testing.assert_frame_equal(candidates, before)
    assert input_path.read_bytes() == source_bytes
    assert list(tmp_path.iterdir()) == [input_path]


def test_load_candidates_reports_missing_columns_in_exact_order(
    tmp_path,
) -> None:
    input_path = tmp_path / "missing.parquet"
    pd.DataFrame({
        "identificador": ["BOE-A-2026-10101"],
        "fecha_publicacion": ["2026-01-01"],
        "xml_status": ["ok"],
    }).to_parquet(input_path)

    with pytest.raises(ValueError) as error_info:
        load_and_prepare_candidates(input_path)

    assert str(error_info.value) == (
        "Faltan columnas obligatorias: ['texto_limpio', 'titulo']"
    )


def test_load_candidates_rejects_invalid_date_after_filtering(tmp_path) -> None:
    input_path = tmp_path / "invalid-date.parquet"
    pd.DataFrame([
        _candidate_row(
            "BOE-A-2026-10101",
            publication_date="fecha inválida",
        ),
        _candidate_row(
            "BOE-A-2026-10102",
            publication_date=None,
        ),
    ]).to_parquet(input_path)

    with pytest.raises(ValueError) as error_info:
        load_and_prepare_candidates(input_path)

    assert str(error_info.value) == (
        "Existen candidatos sin fecha_publicacion válida."
    )


def test_invalid_date_in_filtered_row_is_ignored(tmp_path) -> None:
    input_path = tmp_path / "filtered-invalid-date.parquet"
    pd.DataFrame([
        _candidate_row(
            "BOE-A-2026-10101",
            publication_date="2026-02-01",
        ),
        _candidate_row(
            "BOE-A-2026-10102",
            publication_date="fecha inválida",
            xml_status="error",
        ),
    ]).to_parquet(input_path)

    result = load_and_prepare_candidates(input_path)

    assert result["identificador"].tolist() == ["BOE-A-2026-10101"]


def test_load_candidates_rejects_valid_duplicate_identifiers_in_source_order(
    tmp_path,
) -> None:
    input_path = tmp_path / "duplicates.parquet"
    pd.DataFrame([
        _candidate_row("BOE-A-2026-10102"),
        _candidate_row("BOE-A-2026-10101"),
        _candidate_row("BOE-A-2026-10102", title="Otro título."),
        _candidate_row("BOE-A-2026-10101", title="Título distinto."),
    ]).to_parquet(input_path)

    with pytest.raises(ValueError) as error_info:
        load_and_prepare_candidates(input_path)

    assert str(error_info.value) == (
        "Identificadores BOE duplicados: "
        "['BOE-A-2026-10102', 'BOE-A-2026-10101']"
    )


def test_duplicate_identifier_in_filtered_row_is_ignored(tmp_path) -> None:
    input_path = tmp_path / "filtered-duplicate.parquet"
    pd.DataFrame([
        _candidate_row("BOE-A-2026-10101"),
        _candidate_row("BOE-A-2026-10101", xml_status="error"),
    ]).to_parquet(input_path)

    result = load_and_prepare_candidates(input_path)

    assert result["identificador"].tolist() == ["BOE-A-2026-10101"]


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("identificador", None, "identificador no puede ser nulo."),
        ("titulo", None, "titulo no puede ser nulo."),
    ],
)
def test_null_required_document_values_propagate_exact_document_error(
    tmp_path,
    field_name,
    value,
    message,
) -> None:
    input_path = tmp_path / f"null-{field_name}.parquet"
    row = _candidate_row("BOE-A-2026-10101")
    row[field_name] = value
    pd.DataFrame([row]).to_parquet(input_path)

    with pytest.raises(ValueError) as error_info:
        load_and_prepare_candidates(input_path)

    assert str(error_info.value) == message


def test_empty_candidate_parquet_preserves_notebook_assignment_error(
    tmp_path,
) -> None:
    input_path = tmp_path / "empty.parquet"
    columns = [
        "extra_before",
        "identificador",
        "fecha_publicacion",
        "titulo",
        "xml_status",
        "texto_limpio",
        "extra_after",
    ]
    pd.DataFrame(columns=columns).to_parquet(input_path)

    with pytest.raises(ValueError) as error_info:
        load_and_prepare_candidates(input_path)

    assert str(error_info.value) == (
        "Cannot set a DataFrame with multiple columns to the single column "
        "source_document_sha256"
    )


def test_empty_extraction_returns_empty_and_has_no_effects(monkeypatch) -> None:
    run_df = _candidate_frame().iloc[0:0]
    before = run_df.copy(deep=True)
    sentinel_state = {"sentinel": object()}
    monkeypatch.setattr(runner_module, "debug_state", sentinel_state)
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)

    class FailingAgent:
        async def run(self, *args, **kwargs):
            raise AssertionError("El agente no debe ejecutarse.")

    result = asyncio.run(
        extract_documents(
            run_df,
            agent=FailingAgent(),
            attempts_path=Path("unused.parquet"),
            checkpoint_every=2,
        )
    )

    assert result == []
    assert checkpoint_calls == []
    assert runner_module.debug_state is sentinel_state
    pd.testing.assert_frame_equal(run_df, before)


@pytest.mark.parametrize("checkpoint_every", [0, -1])
def test_extract_documents_rejects_nonpositive_checkpoint_before_work(
    monkeypatch,
    checkpoint_every,
) -> None:
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)

    with pytest.raises(ValueError) as error_info:
        asyncio.run(
            extract_documents(
                _candidate_frame("BOE-A-2026-11001"),
                agent=None,
                checkpoint_every=checkpoint_every,
            )
        )

    assert str(error_info.value) == (
        "checkpoint_every debe ser mayor que cero."
    )
    assert checkpoint_calls == []


def test_preclassified_document_skips_agent_and_preserves_exact_state(
    monkeypatch,
    capsys,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11001")
    row = run_df.iloc[0]
    document = build_source_document(row)
    extraction = _not_relevant_project(document.boe_id, document.publication_date)
    adjustments = ["Clasificación determinista."]
    validation_calls = []
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    monkeypatch.setattr(runner_module, "debug_state", {})
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda received: (extraction, adjustments),
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        lambda **kwargs: validation_calls.append(kwargs),
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[10.0, 11.5],
        uuid_values=["a" * 32],
    )

    class FailingAgent:
        async def run(self, *args, **kwargs):
            raise AssertionError("No se debe llamar al agente.")

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=FailingAgent(),
            attempts_path=Path("attempts.parquet"),
            checkpoint_every=5,
        )
    )

    assert len(records) == 1
    record = records[0]
    assert record["attempt_id"] == "a" * 32
    assert record["identificador_boe"] == document.boe_id
    assert record["source_document_sha256"] == document.source_document_sha256
    assert record["fecha_publicacion"] == pd.Timestamp(document.publication_date)
    assert record["extracted_at"] == pd.Timestamp(_FIXED_NOW)
    assert record["duration_seconds"] == 1.5
    assert record["processing_stage"] == "deterministic_scope_guard"
    assert record["extraction_status"] == "ok"
    assert record["classification_status"] == "classified"
    assert record["document_scope"] == "not_relevant_for_generation_projects"
    assert record["input_text_chars"] is None
    assert record["deterministic_adjustments_json"] == (
        '["Clasificación determinista."]'
    )
    assert record["usage_requests"] == 0
    assert validation_calls == [{
        "document": document,
        "extraction": extraction,
    }]
    assert len(checkpoint_calls) == 1
    assert checkpoint_calls[0]["path"] == Path("attempts.parquet")
    assert checkpoint_calls[0]["dataframe"].to_dict("records") == records
    assert runner_module.debug_state == {
        "document": document,
        "prepared_prompt": None,
        "project_extraction": extraction,
        "adjustments": adjustments,
        "record": record,
    }
    assert capsys.readouterr().out == (
        "[1/1] BOE-A-2026-11001\n"
        "  OK events=0, plants=0, components=0, actions=0\n"
    )


def test_modelled_document_success_uses_exact_prompt_order_and_usage(
    monkeypatch,
) -> None:
    run_df = _candidate_frame(
        "BOE-A-2026-11002",
    )
    row = run_df.iloc[0]
    document = build_source_document(row)
    prepared = build_document_prompt(document)
    ai_extraction = _ai_extraction(document.boe_id)
    ai_snapshot = ai_extraction.model_dump_json()
    call_order = []
    run_calls = []
    validation_calls = []
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    outer_timeouts = _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(runner_module, "debug_state", {})
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda received: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        call_order.append("agent")
        run_calls.append({
            "agent": agent,
            "prompt": prompt,
            "usage": usage,
        })
        usage.incr(RunUsage(requests=1, input_tokens=10, output_tokens=4))
        return SimpleNamespace(output=ai_extraction)

    def fake_canonicalize(
        extraction,
        *,
        source_text,
        document_title,
    ):
        call_order.append("canonicalization")
        assert source_text == f"{document.title}\n{document.text}"
        assert document_title == document.title
        return extraction, ["Canonicalizada."]

    def fake_validate(*, document, extraction):
        call_order.append("validation")
        validation_calls.append((document, extraction))

    fake_agent = object()
    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        fake_canonicalize,
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        fake_validate,
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[100.0, 101.0, 102.0],
        uuid_values=["b" * 32],
    )
    before = run_df.copy(deep=True)

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=fake_agent,
            attempts_path=Path("attempts.parquet"),
            checkpoint_every=3,
        )
    )

    assert call_order == ["agent", "canonicalization", "validation"]
    assert len(run_calls) == 1
    assert run_calls[0]["agent"] is fake_agent
    assert run_calls[0]["prompt"] == prepared.prompt
    assert isinstance(run_calls[0]["usage"], RunUsage)
    assert outer_timeouts == [DOCUMENT_TIMEOUT_SECONDS - 1.0]
    assert validation_calls[0][0] == document
    project_extraction = validation_calls[0][1]
    assert project_extraction.boe_id == document.boe_id
    assert project_extraction.publication_date == document.publication_date
    record = records[0]
    assert record["attempt_id"] == "b" * 32
    assert record["input_text_chars"] == prepared.input_text_chars
    assert record["input_text_sha256"] == prepared.input_text_sha256
    assert record["input_selection_strategy"] == (
        prepared.input_selection_strategy
    )
    assert record["input_selection_marker"] == prepared.input_selection_marker
    assert record["input_excluded_chars"] == prepared.input_excluded_chars
    assert record["source_document_sha256"] == document.source_document_sha256
    assert record["extracted_at"] == pd.Timestamp(_FIXED_NOW)
    assert record["duration_seconds"] == 2.0
    assert record["usage_requests"] == 1
    assert record["usage_input_tokens"] == 10
    assert record["usage_output_tokens"] == 4
    assert record["usage_total_tokens"] == 14
    assert record["processing_stage"] == "completed"
    assert record["deterministic_adjustments_json"] == '["Canonicalizada."]'
    assert len(checkpoint_calls) == 1
    assert checkpoint_calls[0]["dataframe"].to_dict("records") == records
    assert ai_extraction.model_dump_json() == ai_snapshot
    pd.testing.assert_frame_equal(run_df, before)


def test_document_validation_failure_retries_with_exact_corrective_prompt(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11003")
    document = build_source_document(run_df.iloc[0])
    prepared = build_document_prompt(document)
    first_ai = _ai_extraction("Primera")
    second_ai = _ai_extraction("Segunda")
    ai_snapshots = [
        first_ai.model_dump_json(),
        second_ai.model_dump_json(),
    ]
    outputs = [first_ai, second_ai]
    prompts = []
    canonicalized = []
    validation_calls = []
    first_error = DocumentExtractionValidationError([
        "La primera evidencia no está respaldada.",
        "Nombre de planta sin contexto.",
    ])
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    outer_timeouts = _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(runner_module, "debug_state", {})
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        prompts.append(prompt)
        usage.incr(RunUsage(requests=1, input_tokens=12, output_tokens=5))
        return SimpleNamespace(output=outputs.pop(0))

    def fake_canonicalize(extraction, **kwargs):
        canonicalized.append(extraction)
        number = len(canonicalized)
        return extraction, [f"Ajuste {number}."]

    def fake_validate(*, document, extraction):
        validation_calls.append(extraction)
        if len(validation_calls) == 1:
            raise first_error

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        fake_canonicalize,
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        fake_validate,
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[200.0, 201.0, 202.0, 203.0],
        uuid_values=["c" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            attempts_path=Path("attempts.parquet"),
            checkpoint_every=5,
        )
    )

    expected_retry_prompt = build_document_validation_retry_prompt(
        original_prompt=prepared.prompt,
        validation_error=first_error,
    )
    assert prompts == [prepared.prompt, expected_retry_prompt]
    assert len(canonicalized) == 2
    assert validation_calls == canonicalized
    assert outer_timeouts == [
        DOCUMENT_TIMEOUT_SECONDS - 1.0,
        DOCUMENT_TIMEOUT_SECONDS - 2.0,
    ]
    record = records[0]
    assert record["extraction_status"] == "ok"
    assert record["processing_stage"] == "completed"
    assert record["usage_requests"] == 2
    assert record["usage_input_tokens"] == 24
    assert record["usage_output_tokens"] == 10
    assert record["usage_total_tokens"] == 34
    assert record["duration_seconds"] == 3.0
    assert record["deterministic_adjustments_json"] == '["Ajuste 2."]'
    assert BOEProjectExtraction.model_validate_json(
        record["extraction_json"]
    ) == canonicalized[1]
    assert runner_module.debug_state["project_extraction"] == canonicalized[1]
    assert runner_module.debug_state["adjustments"] == ["Ajuste 2."]
    assert len(checkpoint_calls) == 1
    assert first_ai.model_dump_json() == ai_snapshots[0]
    assert second_ai.model_dump_json() == ai_snapshots[1]


def test_exhausted_document_validation_retry_becomes_error_record(
    monkeypatch,
) -> None:
    assert DOCUMENT_VALIDATION_RETRY_ATTEMPTS == 1
    run_df = _candidate_frame("BOE-A-2026-11004")
    first_ai = _ai_extraction("Primera")
    second_ai = _ai_extraction("Segunda")
    outputs = [first_ai, second_ai]
    prompts = []
    errors = [
        DocumentExtractionValidationError(["Issue primero."]),
        DocumentExtractionValidationError(["Issue definitivo."]),
    ]
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(runner_module, "debug_state", {})
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        prompts.append(prompt)
        usage.incr(RunUsage(requests=1, input_tokens=2, output_tokens=1))
        return SimpleNamespace(output=outputs.pop(0))

    canonicalizations = []

    def fake_canonicalize(extraction, **kwargs):
        canonicalizations.append(extraction)
        return extraction, [f"Ajuste {len(canonicalizations)}."]

    def always_invalid(**kwargs):
        raise errors.pop(0)

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        fake_canonicalize,
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        always_invalid,
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[300.0, 301.0, 302.0, 303.0],
        uuid_values=["d" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            attempts_path=Path("attempts.parquet"),
            checkpoint_every=5,
        )
    )

    assert len(prompts) == 2
    assert prompts[1] != prompts[0]
    record = records[0]
    assert record["extraction_status"] == "error"
    assert record["error_type"] == "DocumentExtractionValidationError"
    assert record["error_message"] == "Issue definitivo."
    assert record["processing_stage"] == "document_validation"
    assert record["document_validation_status"] == "failed"
    assert record["document_validation_issue_count"] == 1
    assert record["validation_issues_json"] == '["Issue definitivo."]'
    assert record["usage_requests"] == 2
    assert record["deterministic_adjustments_json"] == '["Ajuste 2."]'
    assert runner_module.debug_state["project_extraction"] == canonicalizations[1]
    assert runner_module.debug_state["record"] is record
    assert len(checkpoint_calls) == 1


def test_request_usage_limit_prevents_document_validation_retry(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11005")
    ai_extraction = _ai_extraction()
    prompts = []
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        prompts.append(prompt)
        usage.incr(RunUsage(
            requests=MAX_MODEL_REQUESTS_PER_DOCUMENT,
            input_tokens=1,
            output_tokens=1,
        ))
        return SimpleNamespace(output=ai_extraction)

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        lambda extraction, **kwargs: (extraction, []),
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        lambda **kwargs: (_ for _ in ()).throw(
            DocumentExtractionValidationError(["No reintentable por uso."])
        ),
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[400.0, 401.0, 402.0],
        uuid_values=["e" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            checkpoint_every=5,
        )
    )

    assert len(prompts) == 1
    assert records[0]["extraction_status"] == "error"
    assert records[0]["error_message"] == "No reintentable por uso."
    assert records[0]["usage_requests"] == MAX_MODEL_REQUESTS_PER_DOCUMENT
    assert len(checkpoint_calls) == 1


def test_model_error_becomes_error_record_and_next_document_continues(
    monkeypatch,
) -> None:
    run_df = _candidate_frame(
        "BOE-A-2026-11006",
        "BOE-A-2026-11007",
    )
    before = run_df.copy(deep=True)
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(runner_module, "debug_state", {})
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )
    calls = []

    async def fake_run_agent(*, agent, prompt, usage):
        calls.append(prompt)
        if len(calls) == 1:
            raise RuntimeError("modelo caído")
        usage.incr(RunUsage(requests=1, input_tokens=3, output_tokens=2))
        return SimpleNamespace(output=_ai_extraction("Segunda"))

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        lambda extraction, **kwargs: (extraction, []),
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        lambda **kwargs: None,
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[500.0, 501.0, 502.0, 510.0, 511.0, 512.0],
        uuid_values=["f" * 32, "1" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            attempts_path=Path("attempts.parquet"),
            checkpoint_every=10,
        )
    )

    assert [record["identificador_boe"] for record in records] == [
        "BOE-A-2026-11006",
        "BOE-A-2026-11007",
    ]
    assert [record["extraction_status"] for record in records] == [
        "error",
        "ok",
    ]
    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["error_message"] == "modelo caído"
    assert records[0]["processing_stage"] == "agent_run"
    assert records[1]["processing_stage"] == "completed"
    assert len(calls) == 2
    assert len(checkpoint_calls) == 1
    assert checkpoint_calls[0]["dataframe"]["extraction_status"].tolist() == [
        "error",
        "ok",
    ]
    assert runner_module.debug_state["document"].boe_id == (
        "BOE-A-2026-11007"
    )
    pd.testing.assert_frame_equal(run_df, before)


def test_unexpected_canonicalization_error_is_recorded_at_exact_stage(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11008")
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        return SimpleNamespace(output=_ai_extraction())

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            LookupError("fallo inesperado")
        ),
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[600.0, 601.0, 602.0],
        uuid_values=["2" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            checkpoint_every=5,
        )
    )

    assert records[0]["extraction_status"] == "error"
    assert records[0]["error_type"] == "LookupError"
    assert records[0]["error_message"] == "fallo inesperado"
    assert records[0]["processing_stage"] == "canonicalization"
    assert runner_module.debug_state["project_extraction"] is not None
    assert len(checkpoint_calls) == 1


def test_invalid_agent_output_is_recorded_without_canonicalization(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11009")
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        return SimpleNamespace(output={"not": "a model"})

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[700.0, 701.0, 702.0],
        uuid_values=["3" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            checkpoint_every=5,
        )
    )

    assert records[0]["error_type"] == "TypeError"
    assert records[0]["error_message"] == (
        "El agente no devolvió BOEAIExtraction."
    )
    assert records[0]["processing_stage"] == "agent_run"
    assert records[0]["extraction_json"] is None
    assert len(checkpoint_calls) == 1


def test_missing_agent_for_nondeterministic_document_is_recorded(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11010")
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[800.0, 801.0],
        uuid_values=["4" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=None,
            checkpoint_every=5,
        )
    )

    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["error_message"] == (
        "El documento requiere IA, pero no se ha construido el agente. "
        "Instala pydantic-ai y configura el proveedor."
    )
    assert records[0]["processing_stage"] == "build_prompt"
    assert runner_module.debug_state["prepared_prompt"] is None
    assert len(checkpoint_calls) == 1


def test_document_build_error_outside_try_propagates_without_checkpoint_or_state(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-11011")
    run_df.loc[0, "identificador"] = None
    sentinel_state = {"before": True}
    monkeypatch.setattr(runner_module, "debug_state", sentinel_state)
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)

    with pytest.raises(ValueError) as error_info:
        asyncio.run(
            extract_documents(
                run_df,
                agent=None,
                checkpoint_every=5,
            )
        )

    assert str(error_info.value) == "identificador no puede ser nulo."
    assert checkpoint_calls == []
    assert runner_module.debug_state is sentinel_state


@pytest.mark.parametrize(
    ("document_count", "checkpoint_every", "expected_sizes"),
    [
        (1, 2, [1]),
        (2, 2, [2]),
        (3, 2, [2, 1]),
        (4, 2, [2, 2]),
        (5, 2, [2, 2, 1]),
        (7, 3, [3, 3, 1]),
    ],
)
def test_checkpoint_batches_are_exact_and_not_mutated_after_delivery(
    monkeypatch,
    document_count,
    checkpoint_every,
    expected_sizes,
) -> None:
    boe_ids = [
        f"BOE-A-2026-{12000 + index}"
        for index in range(document_count)
    ]
    run_df = _candidate_frame(*boe_ids)
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (
            _not_relevant_project(
                document.boe_id,
                document.publication_date,
            ),
            [],
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        lambda **kwargs: None,
    )
    record_number = 0

    def fake_success_record(**kwargs):
        nonlocal record_number
        record_number += 1
        return {
            "attempt_id": f"attempt-{record_number}",
            "identificador_boe": kwargs["document"].boe_id,
            "extraction_status": "ok",
            "n_publication_events": 0,
            "n_generation_assets": 0,
            "n_associated_components": 0,
            "n_administrative_actions": 0,
        }

    monkeypatch.setattr(
        runner_module,
        "build_success_record",
        fake_success_record,
    )
    attempts_path = Path("captured-attempts.parquet")

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=None,
            attempts_path=attempts_path,
            checkpoint_every=checkpoint_every,
        )
    )

    assert [len(call["dataframe"]) for call in checkpoint_calls] == expected_sizes
    assert [call["path"] for call in checkpoint_calls] == (
        [attempts_path] * len(expected_sizes)
    )
    checkpoint_ids = [
        boe_id
        for call in checkpoint_calls
        for boe_id in call["dataframe"]["identificador_boe"].tolist()
    ]
    assert checkpoint_ids == boe_ids
    assert [record["identificador_boe"] for record in records] == boe_ids
    for call in checkpoint_calls:
        pd.testing.assert_frame_equal(
            call["dataframe"],
            call["snapshot"],
        )


def test_error_and_success_share_checkpoint_in_original_order(monkeypatch) -> None:
    run_df = _candidate_frame(
        "BOE-A-2026-13001",
        "BOE-A-2026-13002",
        "BOE-A-2026-13003",
    )
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)

    def fake_preclassify(document):
        if document.boe_id == "BOE-A-2026-13002":
            raise RuntimeError("fallo intermedio")
        return (
            _not_relevant_project(
                document.boe_id,
                document.publication_date,
            ),
            [],
        )

    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        fake_preclassify,
    )
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        lambda **kwargs: None,
    )

    def fake_success_record(**kwargs):
        return {
            "identificador_boe": kwargs["document"].boe_id,
            "extraction_status": "ok",
            "n_publication_events": 0,
            "n_generation_assets": 0,
            "n_associated_components": 0,
            "n_administrative_actions": 0,
        }

    def fake_error_record(**kwargs):
        return {
            "identificador_boe": kwargs["document"].boe_id,
            "extraction_status": "error",
            "error_message": str(kwargs["error"]),
        }

    monkeypatch.setattr(
        runner_module,
        "build_success_record",
        fake_success_record,
    )
    monkeypatch.setattr(
        runner_module,
        "build_error_record",
        fake_error_record,
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=None,
            checkpoint_every=2,
        )
    )

    assert [record["extraction_status"] for record in records] == [
        "ok",
        "error",
        "ok",
    ]
    assert [len(call["dataframe"]) for call in checkpoint_calls] == [2, 1]
    assert checkpoint_calls[0]["dataframe"]["extraction_status"].tolist() == [
        "ok",
        "error",
    ]
    assert checkpoint_calls[1]["dataframe"]["extraction_status"].tolist() == [
        "ok",
    ]


def test_debug_state_after_document_validation_error_has_exact_keys(
    monkeypatch,
) -> None:
    run_df = _candidate_frame("BOE-A-2026-14001")
    checkpoint_calls = _install_no_checkpoint_writer(monkeypatch)
    _install_immediate_wait_for(monkeypatch)
    monkeypatch.setattr(runner_module, "debug_state", {})
    ai_extraction = _ai_extraction()
    monkeypatch.setattr(
        runner_module,
        "preclassify_document_without_model",
        lambda document: (None, []),
    )

    async def fake_run_agent(*, agent, prompt, usage):
        usage.requests = MAX_MODEL_REQUESTS_PER_DOCUMENT
        return SimpleNamespace(output=ai_extraction)

    monkeypatch.setattr(
        runner_module,
        "run_agent_with_transient_retries",
        fake_run_agent,
    )
    monkeypatch.setattr(
        runner_module,
        "canonicalize_project_extraction",
        lambda extraction, **kwargs: (
            extraction,
            ["Ajuste antes del fallo."],
        ),
    )
    validation_error = DocumentExtractionValidationError([
        "Fallo documental final."
    ])
    monkeypatch.setattr(
        runner_module,
        "validate_extraction_against_document",
        lambda **kwargs: (_ for _ in ()).throw(validation_error),
    )
    _install_fixed_record_values(
        monkeypatch,
        perf_values=[900.0, 901.0, 902.0],
        uuid_values=["5" * 32],
    )

    records = asyncio.run(
        extract_documents(
            run_df,
            agent=object(),
            checkpoint_every=5,
        )
    )

    state = runner_module.debug_state
    assert list(state) == [
        "document",
        "prepared_prompt",
        "project_extraction",
        "adjustments",
        "record",
    ]
    assert state["document"].boe_id == "BOE-A-2026-14001"
    assert state["prepared_prompt"] == build_document_prompt(state["document"])
    assert state["project_extraction"] is not None
    assert state["adjustments"] == ["Ajuste antes del fallo."]
    assert state["record"] is records[0]
    assert state["record"]["error_message"] == "Fallo documental final."
    assert len(checkpoint_calls) == 1


def test_runner_fresh_import_has_exact_initial_state_and_no_execution() -> None:
    project_root = Path(__file__).resolve().parents[2]
    command = (
        "import renewables_permitting.extraction.runner as module; "
        "print(hasattr(module, 'agent')); "
        "print(hasattr(module, 'extract_documents')); "
        "print(module.debug_state)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["False", "True", "{}"]
    assert result.stderr == ""


def _top_level_nodes(source: str) -> dict[str, ast.AST]:
    nodes = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nodes[node.target.id] = node
    return nodes


def test_phase_13_nodes_match_notebook_ast_exactly() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text()
    )
    notebook_nodes = {}
    for cell_index in (9, 13):
        notebook_nodes.update(
            _top_level_nodes("".join(notebook["cells"][cell_index]["source"]))
        )
    runner_nodes = _top_level_nodes(
        (
            project_root
            / "src"
            / "renewables_permitting"
            / "extraction"
            / "runner.py"
        ).read_text()
    )
    expected_names = {
        "_REQUIRED_INPUT_COLUMNS",
        "load_and_prepare_candidates",
        "debug_state",
        "extract_documents",
    }

    assert expected_names <= notebook_nodes.keys()
    assert expected_names <= runner_nodes.keys()
    for name in expected_names:
        assert ast.dump(
            runner_nodes[name],
            include_attributes=False,
        ) == ast.dump(
            notebook_nodes[name],
            include_attributes=False,
        )


def test_runner_contains_no_deferred_or_artificial_phase_13_code() -> None:
    source = Path(runner_module.__file__).read_text()
    tree = ast.parse(source)

    assert hasattr(runner_module, "run_and_finalize_extractions")
    assert "load_pilot_scope_labels" not in source
    assert "build_stratified_pilot_sample" not in source
    assert "evaluate_pilot" not in source
    assert not any(
        isinstance(node, ast.If) and isinstance(node.test, ast.Constant)
        and node.test.value is True
        for node in tree.body
    )
    assert not hasattr(runner_module, "agent")
