import ast
import asyncio
import copy
from datetime import date
from inspect import iscoroutinefunction, signature
from pathlib import Path

import pandas as pd
import pytest

import renewables_permitting.extraction.runner as runner_module
from renewables_permitting.extraction.config import (
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
)
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
from renewables_permitting.extraction.persistence import (
    save_parquet_atomic as real_save_parquet_atomic,
)
from renewables_permitting.extraction.review import (
    AI_EXTRACTION_LOG_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    append_quality_metric as real_append_quality_metric,
    combine_ai_extraction_attempt_frames,
    normalise_ai_extraction_attempts_log,
    normalise_manual_reviews,
)
from renewables_permitting.extraction.runner import (
    run_and_finalize_extractions,
)


def _project(
    boe_id: str,
    *,
    name: str,
    reason: str = "Publicación específica de generación.",
) -> BOEProjectExtraction:
    evidence = f"Autorización de la planta fotovoltaica {name}."
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason=reason,
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
        boe_id=boe_id,
        publication_date=date(2026, 1, 2),
    )


def _source_df(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "identificador": boe_id,
                "fecha_publicacion": pd.Timestamp("2026-01-02"),
                "titulo": title,
                "xml_status": "ok",
                "texto_limpio": title,
                "source_document_sha256": source_hash,
            }
            for boe_id, source_hash, title in rows
        ],
        columns=[
            "identificador",
            "fecha_publicacion",
            "titulo",
            "xml_status",
            "texto_limpio",
            "source_document_sha256",
        ],
    )


def _attempt(
    *,
    attempt_id: str,
    boe_id: str,
    source_hash: str,
    extracted_at: str,
    extraction: BOEProjectExtraction | None,
    status: str = "ok",
    error_message: str | None = None,
    historical_value: str | None = None,
) -> dict:
    passed = status == "ok"
    record = {
        "attempt_id": attempt_id,
        "identificador_boe": boe_id,
        "fecha_publicacion": pd.Timestamp("2026-01-02"),
        "titulo": f"Título {boe_id}",
        "source_document_sha256": source_hash,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "classification_status": (
            extraction.classification_status.value if extraction else None
        ),
        "document_scope": (
            extraction.document_scope.value
            if extraction and extraction.document_scope
            else None
        ),
        "classification_reason": (
            extraction.classification_reason if extraction else None
        ),
        "extraction_json": (
            extraction.model_dump_json() if extraction else None
        ),
        "extracted_at": pd.Timestamp(extracted_at),
        "extraction_status": status,
        "error_type": None if passed else "RuntimeError",
        "error_message": error_message,
        "processing_stage": "completed" if passed else "agent_run",
        "document_validation_status": "passed" if passed else None,
        "document_validation_issue_count": 0,
        "validation_issues_json": None,
    }
    if historical_value is not None:
        record["historical_column"] = historical_value
    return record


def _manual_review(
    *,
    review_id: str,
    extraction: BOEProjectExtraction,
    source_hash: str,
    status: str,
    corrected_extraction: BOEProjectExtraction | None = None,
    source_attempt_id: str = "automatic-attempt",
) -> dict:
    return {
        "manual_review_id": review_id,
        "identificador_boe": extraction.boe_id,
        "source_document_sha256": source_hash,
        "source_attempt_id": source_attempt_id,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "review_status": status,
        "corrected_extraction_json": (
            corrected_extraction.model_dump_json()
            if corrected_extraction is not None
            else None
        ),
        "reviewer": "reviewer",
        "review_notes": f"Decisión {status}.",
        "reviewed_at_utc": pd.Timestamp("2026-01-05T00:00:00Z"),
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }


def _install_real_review_io_doubles(
    monkeypatch,
    *,
    historical_attempts: pd.DataFrame,
    new_records: list[dict],
):
    effects = []
    stored = {
        "attempts": normalise_ai_extraction_attempts_log(
            historical_attempts
        ),
    }

    async def fake_extract_documents(
        run_df,
        *,
        agent,
        attempts_path,
        checkpoint_every,
    ):
        effects.append((
            "extract_documents",
            run_df,
            agent,
            attempts_path,
            checkpoint_every,
        ))
        new_attempts = normalise_ai_extraction_attempts_log(
            pd.DataFrame(new_records)
        )
        stored["attempts"] = combine_ai_extraction_attempt_frames(
            stored["attempts"],
            new_attempts,
        )
        return copy.deepcopy(new_records)

    def fake_load_attempts(path):
        effects.append(("load_ai_extraction_attempts", path))
        return stored["attempts"]

    def fake_save(dataframe, path):
        effects.append((
            "save_parquet_atomic",
            dataframe,
            dataframe.copy(deep=True),
            path,
        ))

    def fake_append_metric(dataframe, path):
        effects.append((
            "append_quality_metric",
            dataframe,
            dataframe.copy(deep=True),
            path,
        ))
        return dataframe

    monkeypatch.setattr(
        runner_module,
        "extract_documents",
        fake_extract_documents,
    )
    monkeypatch.setattr(
        runner_module,
        "load_ai_extraction_attempts",
        fake_load_attempts,
    )
    monkeypatch.setattr(
        runner_module,
        "save_parquet_atomic",
        fake_save,
    )
    monkeypatch.setattr(
        runner_module,
        "append_quality_metric",
        fake_append_metric,
    )
    return effects, stored


def _run_with_real_review_logic(
    monkeypatch,
    *,
    run_df: pd.DataFrame,
    source_df: pd.DataFrame,
    historical_attempts: pd.DataFrame | None = None,
    new_records: list[dict] | None = None,
    manual_reviews: pd.DataFrame | None = None,
):
    effects, stored = _install_real_review_io_doubles(
        monkeypatch,
        historical_attempts=(
            pd.DataFrame()
            if historical_attempts is None
            else historical_attempts
        ),
        new_records=[] if new_records is None else new_records,
    )
    result = asyncio.run(
        run_and_finalize_extractions(
            run_df,
            source_df,
            agent="fake-agent",
            attempts_path=Path("attempts.parquet"),
            current_path=Path("current.parquet"),
            review_queue_path=Path("queue.parquet"),
            quality_metrics_path=Path("quality.parquet"),
            manual_reviews=manual_reviews,
            run_scope="test-scope",
            minimum_auto_validation_rate=0.75,
            checkpoint_every=3,
        )
    )
    return result, effects, stored


def test_exact_operation_order_arguments_and_return_references(
    monkeypatch,
) -> None:
    events = []
    run_df = pd.DataFrame({"candidate": [1]})
    source_df = pd.DataFrame({"source": [1]})
    original_manual = pd.DataFrame({"manual_review_id": ["manual"]})
    records = [{"attempt_id": "new"}]
    attempts = pd.DataFrame({"attempt_id": ["all"]})
    normalized_manual = pd.DataFrame({"manual_review_id": ["normalized"]})
    current = pd.DataFrame({"identificador_boe": ["current"]})
    queue = pd.DataFrame({"review_queue_id": ["queue"]})
    metric = pd.DataFrame({"quality_run_id": ["metric"]})
    normalized_new = pd.DataFrame({"attempt_id": ["normalized-new"]})
    fake_agent = object()

    async def fake_extract(
        received_run_df,
        *,
        agent,
        attempts_path,
        checkpoint_every,
    ):
        events.append("extract_documents")
        assert received_run_df is run_df
        assert agent is fake_agent
        assert attempts_path == Path("attempts.parquet")
        assert checkpoint_every == 7
        return records

    def fake_load(path):
        events.append("load_ai_extraction_attempts")
        assert path == Path("attempts.parquet")
        return attempts

    def fake_normalise_manual(dataframe):
        events.append("normalise_manual_reviews")
        assert dataframe is original_manual
        return normalized_manual

    def fake_select(**kwargs):
        events.append("select_best_valid_extractions")
        assert kwargs == {
            "attempts": attempts,
            "source_df": source_df,
            "manual_reviews": normalized_manual,
        }
        return current

    def fake_save(dataframe, path):
        events.append(
            "save_current" if path.name == "current.parquet" else "save_queue"
        )
        if path.name == "current.parquet":
            assert dataframe is current
        else:
            assert dataframe is queue

    def fake_queue(**kwargs):
        events.append("build_review_queue")
        assert kwargs == {
            "attempts": attempts,
            "source_df": source_df,
            "manual_reviews": normalized_manual,
        }
        return queue

    def fake_metric(**kwargs):
        events.append("build_quality_metric")
        assert kwargs == {
            "attempts": attempts,
            "source_df": source_df,
            "manual_reviews": normalized_manual,
            "run_scope": "pilot",
            "minimum_auto_validation_rate": 0.81,
        }
        return metric

    def fake_append_metric(dataframe, path):
        events.append("append_quality_metric")
        assert dataframe is metric
        assert path == Path("quality.parquet")
        return object()

    def fake_normalise_attempts(dataframe):
        events.append("normalise_new_attempts")
        assert dataframe.to_dict("records") == records
        return normalized_new

    monkeypatch.setattr(runner_module, "extract_documents", fake_extract)
    monkeypatch.setattr(
        runner_module,
        "load_ai_extraction_attempts",
        fake_load,
    )
    monkeypatch.setattr(
        runner_module,
        "normalise_manual_reviews",
        fake_normalise_manual,
    )
    monkeypatch.setattr(
        runner_module,
        "select_best_valid_extractions",
        fake_select,
    )
    monkeypatch.setattr(runner_module, "save_parquet_atomic", fake_save)
    monkeypatch.setattr(runner_module, "build_review_queue", fake_queue)
    monkeypatch.setattr(runner_module, "build_quality_metric", fake_metric)
    monkeypatch.setattr(
        runner_module,
        "append_quality_metric",
        fake_append_metric,
    )
    monkeypatch.setattr(
        runner_module,
        "normalise_ai_extraction_attempts_log",
        fake_normalise_attempts,
    )

    result = asyncio.run(
        run_and_finalize_extractions(
            run_df,
            source_df,
            agent=fake_agent,
            attempts_path=Path("attempts.parquet"),
            current_path=Path("current.parquet"),
            review_queue_path=Path("queue.parquet"),
            quality_metrics_path=Path("quality.parquet"),
            manual_reviews=original_manual,
            run_scope="pilot",
            minimum_auto_validation_rate=0.81,
            checkpoint_every=7,
        )
    )

    assert events == [
        "extract_documents",
        "load_ai_extraction_attempts",
        "normalise_manual_reviews",
        "select_best_valid_extractions",
        "save_current",
        "build_review_queue",
        "save_queue",
        "build_quality_metric",
        "append_quality_metric",
        "normalise_new_attempts",
    ]
    assert list(result) == [
        "new_attempts",
        "all_attempts",
        "current_extractions",
        "review_queue",
        "quality_metric",
    ]
    assert result["new_attempts"] is normalized_new
    assert result["all_attempts"] is attempts
    assert result["current_extractions"] is current
    assert result["review_queue"] is queue
    assert result["quality_metric"] is metric


def test_none_manual_reviews_and_optional_paths_follow_public_flow(
    monkeypatch,
) -> None:
    events = []
    empty_run = pd.DataFrame()
    empty_source = pd.DataFrame()
    empty_manual = pd.DataFrame({"manual": []})
    attempts = pd.DataFrame()
    current = pd.DataFrame()
    queue = pd.DataFrame()
    metric = pd.DataFrame({"quality": [1]})
    normalized_new = pd.DataFrame()

    async def fake_extract(run_df, **kwargs):
        events.append("extract")
        assert run_df is empty_run
        return []

    monkeypatch.setattr(runner_module, "extract_documents", fake_extract)
    monkeypatch.setattr(
        runner_module,
        "load_ai_extraction_attempts",
        lambda path: events.append("load") or attempts,
    )
    monkeypatch.setattr(
        runner_module,
        "empty_manual_reviews",
        lambda: events.append("empty_manual") or empty_manual,
    )
    monkeypatch.setattr(
        runner_module,
        "normalise_manual_reviews",
        lambda dataframe: pytest.fail(
            "No debe normalizar una revisión manual ausente."
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "select_best_valid_extractions",
        lambda **kwargs: events.append("select") or current,
    )

    def fake_save(dataframe, path):
        events.append(("save", path))
        assert dataframe is current

    monkeypatch.setattr(runner_module, "save_parquet_atomic", fake_save)
    monkeypatch.setattr(
        runner_module,
        "build_review_queue",
        lambda **kwargs: events.append("queue") or queue,
    )
    monkeypatch.setattr(
        runner_module,
        "build_quality_metric",
        lambda **kwargs: events.append("metric") or metric,
    )
    monkeypatch.setattr(
        runner_module,
        "append_quality_metric",
        lambda *args: pytest.fail("No debe persistir la métrica."),
    )
    monkeypatch.setattr(
        runner_module,
        "normalise_ai_extraction_attempts_log",
        lambda dataframe: events.append("normalize") or normalized_new,
    )

    result = asyncio.run(
        run_and_finalize_extractions(
            empty_run,
            empty_source,
            agent=None,
            current_path=Path("current.parquet"),
            review_queue_path=None,
            quality_metrics_path=None,
            manual_reviews=None,
        )
    )

    assert events == [
        "extract",
        "load",
        "empty_manual",
        "select",
        ("save", Path("current.parquet")),
        "queue",
        "metric",
        "normalize",
    ]
    assert result["new_attempts"] is normalized_new
    assert result["all_attempts"] is attempts
    assert result["current_extractions"] is current
    assert result["review_queue"] is queue
    assert result["quality_metric"] is metric


def test_no_candidates_and_no_attempt_history(monkeypatch) -> None:
    run_df = _source_df()
    source_df = _source_df()
    before_run = run_df.copy(deep=True)
    before_source = source_df.copy(deep=True)

    result, effects, stored = _run_with_real_review_logic(
        monkeypatch,
        run_df=run_df,
        source_df=source_df,
    )

    assert effects[0][0] == "extract_documents"
    assert effects[0][1] is run_df
    assert result["new_attempts"].empty
    assert result["all_attempts"] is stored["attempts"]
    assert result["all_attempts"].empty
    assert result["current_extractions"].empty
    assert result["review_queue"].empty
    metric = result["quality_metric"].iloc[0]
    assert metric["n_source_documents"] == 0
    assert metric["n_latest_attempts"] == 0
    assert metric["automatic_validation_rate"] == 1.0
    assert metric["effective_validation_rate"] == 1.0
    pd.testing.assert_frame_equal(run_df, before_run)
    pd.testing.assert_frame_equal(source_df, before_source)


def test_candidates_without_attempt_history_return_followup_queue(
    monkeypatch,
) -> None:
    source_df = _source_df(
        ("BOE-A-2026-20001", "hash-1", "Planta Uno"),
        ("BOE-A-2026-20002", "hash-2", "Planta Dos"),
    )
    run_df = source_df.copy(deep=True)

    result, effects, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=run_df,
        source_df=source_df,
    )

    assert effects[0][1] is run_df
    assert result["all_attempts"].empty
    assert result["current_extractions"].empty
    assert result["review_queue"]["identificador_boe"].tolist() == [
        "BOE-A-2026-20001",
        "BOE-A-2026-20002",
    ]
    assert result["review_queue"]["reason_code"].tolist() == [
        "source_not_attempted",
        "source_not_attempted",
    ]
    assert result["review_queue"]["source_attempt_id"].isna().all()
    metric = result["quality_metric"].iloc[0]
    assert metric["n_source_documents"] == 2
    assert metric["n_latest_attempts"] == 0
    assert metric["n_unattempted"] == 2
    assert metric["coverage_rate"] == 0.0
    assert metric["n_review_required"] == 2
    assert metric["quality_status"] == "degraded"


def test_all_processed_candidates_still_call_extract_with_supplied_empty_run(
    monkeypatch,
) -> None:
    extraction = _project("BOE-A-2026-20003", name="Procesada")
    source_df = _source_df(
        (extraction.boe_id, "hash-current", "Planta Procesada"),
    )
    history = pd.DataFrame([
        _attempt(
            attempt_id="processed",
            boe_id=extraction.boe_id,
            source_hash="hash-current",
            extracted_at="2026-01-03T00:00:00Z",
            extraction=extraction,
        ),
    ])
    empty_pending = source_df.iloc[0:0].copy()

    result, effects, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=empty_pending,
        source_df=source_df,
        historical_attempts=history,
    )

    assert effects[0][0] == "extract_documents"
    assert effects[0][1] is empty_pending
    assert result["new_attempts"].empty
    assert result["current_extractions"]["identificador_boe"].tolist() == [
        extraction.boe_id
    ]


def test_previous_error_is_retried_when_caller_supplies_candidate(
    monkeypatch,
) -> None:
    extraction = _project("BOE-A-2026-20004", name="Reintentada")
    source_df = _source_df(
        (extraction.boe_id, "hash-current", "Planta Reintentada"),
    )
    history = pd.DataFrame([
        _attempt(
            attempt_id="old-error",
            boe_id=extraction.boe_id,
            source_hash="hash-current",
            extracted_at="2026-01-03T00:00:00Z",
            extraction=None,
            status="error",
            error_message="Error anterior.",
        ),
    ])
    new_success = _attempt(
        attempt_id="new-success",
        boe_id=extraction.boe_id,
        source_hash="hash-current",
        extracted_at="2026-01-04T00:00:00Z",
        extraction=extraction,
    )

    result, effects, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=source_df.copy(deep=True),
        source_df=source_df,
        historical_attempts=history,
        new_records=[new_success],
    )

    assert effects[0][0] == "extract_documents"
    assert result["all_attempts"]["attempt_id"].tolist() == [
        "old-error",
        "new-success",
    ]
    assert result["current_extractions"]["attempt_id"].tolist() == [
        "new-success"
    ]
    assert result["review_queue"].empty


def test_changed_source_hash_selects_new_attempt_and_preserves_history(
    monkeypatch,
) -> None:
    extraction = _project("BOE-A-2026-20005", name="Fuente Nueva")
    source_df = _source_df(
        (extraction.boe_id, "new-hash", "Planta con fuente nueva"),
    )
    history = pd.DataFrame([
        _attempt(
            attempt_id="old-source",
            boe_id=extraction.boe_id,
            source_hash="old-hash",
            extracted_at="2026-01-03T00:00:00Z",
            extraction=extraction,
            historical_value="kept",
        ),
    ])
    new_attempt = _attempt(
        attempt_id="new-source",
        boe_id=extraction.boe_id,
        source_hash="new-hash",
        extracted_at="2026-01-04T00:00:00Z",
        extraction=extraction,
    )

    result, _, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=source_df.copy(deep=True),
        source_df=source_df,
        historical_attempts=history,
        new_records=[new_attempt],
    )

    assert result["all_attempts"]["attempt_id"].tolist() == [
        "old-source",
        "new-source",
    ]
    assert "historical_column" in result["all_attempts"].columns
    assert result["current_extractions"]["attempt_id"].tolist() == [
        "new-source"
    ]
    assert result["current_extractions"]["source_document_sha256"].tolist() == [
        "new-hash"
    ]


def test_automatic_success_and_extraction_error_build_expected_outputs(
    monkeypatch,
) -> None:
    success = _project("BOE-A-2026-20006", name="Correcta")
    error_id = "BOE-A-2026-20007"
    source_df = _source_df(
        (success.boe_id, "hash-success", "Planta Correcta"),
        (error_id, "hash-error", "Planta con error"),
    )
    new_records = [
        _attempt(
            attempt_id="success",
            boe_id=success.boe_id,
            source_hash="hash-success",
            extracted_at="2026-01-04T00:00:00Z",
            extraction=success,
        ),
        _attempt(
            attempt_id="error",
            boe_id=error_id,
            source_hash="hash-error",
            extracted_at="2026-01-04T00:01:00Z",
            extraction=None,
            status="error",
            error_message="Fallo de extracción.",
        ),
    ]

    result, effects, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=source_df.copy(deep=True),
        source_df=source_df,
        new_records=new_records,
    )

    assert result["new_attempts"]["attempt_id"].tolist() == [
        "success",
        "error",
    ]
    assert result["current_extractions"]["identificador_boe"].tolist() == [
        success.boe_id
    ]
    assert result["review_queue"]["identificador_boe"].tolist() == [error_id]
    assert result["review_queue"]["error_message"].tolist() == [
        "Fallo de extracción."
    ]
    save_effects = [
        effect for effect in effects if effect[0] == "save_parquet_atomic"
    ]
    assert save_effects[0][1] is result["current_extractions"]
    assert save_effects[1][1] is result["review_queue"]
    metric_effect = next(
        effect for effect in effects
        if effect[0] == "append_quality_metric"
    )
    assert metric_effect[1] is result["quality_metric"]


def test_valid_manual_review_precedes_automatic_extraction(monkeypatch) -> None:
    automatic = _project("BOE-A-2026-20008", name="Automática")
    corrected = _project(
        automatic.boe_id,
        name="Corregida",
        reason="Corrección manual.",
    )
    source_df = _source_df(
        (
            automatic.boe_id,
            "hash-current",
            "Autorización de la planta fotovoltaica Corregida.",
        ),
    )
    history = pd.DataFrame([
        _attempt(
            attempt_id="automatic-attempt",
            boe_id=automatic.boe_id,
            source_hash="hash-current",
            extracted_at="2026-01-03T00:00:00Z",
            extraction=automatic,
        ),
    ])
    reviews = pd.DataFrame([
        _manual_review(
            review_id="manual-valid",
            extraction=automatic,
            source_hash="hash-current",
            status="manually_validated",
            corrected_extraction=corrected,
        ),
    ])
    reviews_before = reviews.copy(deep=True)

    result, _, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=source_df.iloc[0:0].copy(),
        source_df=source_df,
        historical_attempts=history,
        manual_reviews=reviews,
    )

    current = result["current_extractions"].iloc[0]
    assert len(current["attempt_id"]) == 24
    assert current["source_attempt_id"] == "automatic-attempt"
    assert current["selection_source"] == "manually_validated"
    assert current["model_provider"] == "manual"
    assert BOEProjectExtraction.model_validate_json(
        str(current["extraction_json"])
    ) == corrected
    assert result["review_queue"].empty
    pd.testing.assert_frame_equal(reviews, reviews_before)


def test_manual_rejection_removes_current_and_resolves_queue(
    monkeypatch,
) -> None:
    automatic = _project("BOE-A-2026-20009", name="Rechazada")
    source_df = _source_df(
        (automatic.boe_id, "hash-current", "Planta rechazada"),
    )
    history = pd.DataFrame([
        _attempt(
            attempt_id="automatic-attempt",
            boe_id=automatic.boe_id,
            source_hash="hash-current",
            extracted_at="2026-01-03T00:00:00Z",
            extraction=automatic,
        ),
    ])
    reviews = pd.DataFrame([
        _manual_review(
            review_id="manual-rejected",
            extraction=automatic,
            source_hash="hash-current",
            status="rejected",
        ),
    ])

    result, _, _ = _run_with_real_review_logic(
        monkeypatch,
        run_df=source_df.iloc[0:0].copy(),
        source_df=source_df,
        historical_attempts=history,
        manual_reviews=reviews,
    )

    assert result["current_extractions"].empty
    assert result["review_queue"].empty
    metric = result["quality_metric"].iloc[0]
    assert metric["n_rejected"] == 1
    assert metric["n_manually_validated"] == 0


def test_stale_manual_review_is_rejected_after_source_change(
    monkeypatch,
) -> None:
    automatic = _project("BOE-A-2026-20010", name="Fuente Actual")
    corrected = _project(automatic.boe_id, name="Corrección Obsoleta")
    source_df = _source_df(
        (automatic.boe_id, "new-hash", "Planta actualizada"),
    )
    history = pd.DataFrame([
        _attempt(
            attempt_id="new-auto",
            boe_id=automatic.boe_id,
            source_hash="new-hash",
            extracted_at="2026-01-04T00:00:00Z",
            extraction=automatic,
        ),
    ])
    stale_reviews = pd.DataFrame([
        _manual_review(
            review_id="stale-manual",
            extraction=automatic,
            source_hash="old-hash",
            status="manually_validated",
            corrected_extraction=corrected,
        ),
    ])

    with pytest.raises(ValueError, match="source_document_sha256"):
        _run_with_real_review_logic(
            monkeypatch,
            run_df=source_df.iloc[0:0].copy(),
            source_df=source_df,
            historical_attempts=history,
            manual_reviews=stale_reviews,
        )


@pytest.mark.parametrize(
    ("failure_stage", "expected_events"),
    [
        ("extract", ["extract"]),
        (
            "save_current",
            ["extract", "load", "empty_manual", "select", "save_current"],
        ),
        (
            "save_queue",
            [
                "extract",
                "load",
                "empty_manual",
                "select",
                "save_current",
                "build_queue",
                "save_queue",
            ],
        ),
        (
            "append_metric",
            [
                "extract",
                "load",
                "empty_manual",
                "select",
                "save_current",
                "build_queue",
                "save_queue",
                "build_metric",
                "append_metric",
            ],
        ),
    ],
)
def test_failures_propagate_without_global_rollback(
    monkeypatch,
    failure_stage,
    expected_events,
) -> None:
    events = []
    expected_error = RuntimeError(f"fallo en {failure_stage}")
    current = pd.DataFrame({"current": [1]})
    queue = pd.DataFrame({"queue": [1]})
    metric = pd.DataFrame({"metric": [1]})

    async def fake_extract(*args, **kwargs):
        events.append("extract")
        if failure_stage == "extract":
            raise expected_error
        return []

    def fake_load(path):
        events.append("load")
        return pd.DataFrame()

    def fake_empty_manual():
        events.append("empty_manual")
        return pd.DataFrame()

    def fake_select(**kwargs):
        events.append("select")
        return current

    def fake_save(dataframe, path):
        stage = (
            "save_current"
            if path == Path("current.parquet")
            else "save_queue"
        )
        events.append(stage)
        if failure_stage == stage:
            raise expected_error

    def fake_queue(**kwargs):
        events.append("build_queue")
        return queue

    def fake_metric(**kwargs):
        events.append("build_metric")
        return metric

    def fake_append(dataframe, path):
        events.append("append_metric")
        if failure_stage == "append_metric":
            raise expected_error

    monkeypatch.setattr(runner_module, "extract_documents", fake_extract)
    monkeypatch.setattr(
        runner_module,
        "load_ai_extraction_attempts",
        fake_load,
    )
    monkeypatch.setattr(
        runner_module,
        "empty_manual_reviews",
        fake_empty_manual,
    )
    monkeypatch.setattr(
        runner_module,
        "select_best_valid_extractions",
        fake_select,
    )
    monkeypatch.setattr(runner_module, "save_parquet_atomic", fake_save)
    monkeypatch.setattr(runner_module, "build_review_queue", fake_queue)
    monkeypatch.setattr(runner_module, "build_quality_metric", fake_metric)
    monkeypatch.setattr(runner_module, "append_quality_metric", fake_append)

    with pytest.raises(RuntimeError) as error_info:
        asyncio.run(
            run_and_finalize_extractions(
                pd.DataFrame(),
                pd.DataFrame(),
                agent=None,
                current_path=Path("current.parquet"),
                review_queue_path=Path("queue.parquet"),
                quality_metrics_path=Path("quality.parquet"),
            )
        )

    assert error_info.value is expected_error
    assert events == expected_events


def test_inputs_and_double_results_are_not_modified(monkeypatch) -> None:
    run_df = pd.DataFrame({"candidate": [1]})
    source_df = pd.DataFrame({"source": [1]})
    manual = pd.DataFrame({"manual_review_id": ["m"]})
    attempts = pd.DataFrame({"attempt_id": ["a"]})
    records = [{"attempt_id": "new", "nested": ["value"]}]
    current = pd.DataFrame({"current": [1]})
    queue = pd.DataFrame({"queue": [1]})
    metric = pd.DataFrame({"metric": [1]})
    snapshots = {
        "run": run_df.copy(deep=True),
        "source": source_df.copy(deep=True),
        "manual": manual.copy(deep=True),
        "attempts": attempts.copy(deep=True),
        "records": copy.deepcopy(records),
        "current": current.copy(deep=True),
        "queue": queue.copy(deep=True),
        "metric": metric.copy(deep=True),
    }

    async def fake_extract(*args, **kwargs):
        return records

    monkeypatch.setattr(runner_module, "extract_documents", fake_extract)
    monkeypatch.setattr(
        runner_module,
        "load_ai_extraction_attempts",
        lambda path: attempts,
    )
    monkeypatch.setattr(
        runner_module,
        "normalise_manual_reviews",
        lambda dataframe: dataframe.copy(deep=True),
    )
    monkeypatch.setattr(
        runner_module,
        "select_best_valid_extractions",
        lambda **kwargs: current,
    )
    monkeypatch.setattr(
        runner_module,
        "build_review_queue",
        lambda **kwargs: queue,
    )
    monkeypatch.setattr(
        runner_module,
        "build_quality_metric",
        lambda **kwargs: metric,
    )
    monkeypatch.setattr(
        runner_module,
        "save_parquet_atomic",
        lambda dataframe, path: None,
    )
    monkeypatch.setattr(
        runner_module,
        "append_quality_metric",
        lambda dataframe, path: None,
    )

    asyncio.run(
        run_and_finalize_extractions(
            run_df,
            source_df,
            agent=None,
            current_path=Path("current.parquet"),
            review_queue_path=Path("queue.parquet"),
            quality_metrics_path=Path("quality.parquet"),
            manual_reviews=manual,
        )
    )

    pd.testing.assert_frame_equal(run_df, snapshots["run"])
    pd.testing.assert_frame_equal(source_df, snapshots["source"])
    pd.testing.assert_frame_equal(manual, snapshots["manual"])
    pd.testing.assert_frame_equal(attempts, snapshots["attempts"])
    assert records == snapshots["records"]
    pd.testing.assert_frame_equal(current, snapshots["current"])
    pd.testing.assert_frame_equal(queue, snapshots["queue"])
    pd.testing.assert_frame_equal(metric, snapshots["metric"])


def test_isolated_integration_writes_only_requested_tmp_paths(
    monkeypatch,
    tmp_path,
) -> None:
    automatic = _project("BOE-A-2026-21001", name="Automática")
    error_id = "BOE-A-2026-21002"
    reviewed_auto = _project("BOE-A-2026-21003", name="Antes")
    reviewed_manual = _project(
        reviewed_auto.boe_id,
        name="Después",
        reason="Corrección manual integrada.",
    )
    rejected = _project("BOE-A-2026-21004", name="Rechazada")
    source_df = _source_df(
        (automatic.boe_id, "hash-auto", "Planta Automática"),
        (error_id, "hash-error", "Planta Error"),
        (
            reviewed_auto.boe_id,
            "hash-review",
            "Autorización de la planta fotovoltaica Después.",
        ),
        (rejected.boe_id, "hash-rejected", "Planta Rechazada"),
    )
    run_df = source_df.loc[
        source_df["identificador"].isin([automatic.boe_id, error_id])
    ].copy()
    new_records = [
        _attempt(
            attempt_id="new-auto",
            boe_id=automatic.boe_id,
            source_hash="hash-auto",
            extracted_at="2026-01-05T00:00:00Z",
            extraction=automatic,
        ),
        _attempt(
            attempt_id="new-error",
            boe_id=error_id,
            source_hash="hash-error",
            extracted_at="2026-01-05T00:01:00Z",
            extraction=None,
            status="error",
            error_message="Requiere revisión.",
        ),
    ]
    historical = pd.DataFrame([
        _attempt(
            attempt_id="reviewed-auto",
            boe_id=reviewed_auto.boe_id,
            source_hash="hash-review",
            extracted_at="2026-01-03T00:00:00Z",
            extraction=reviewed_auto,
        ),
        _attempt(
            attempt_id="rejected-auto",
            boe_id=rejected.boe_id,
            source_hash="hash-rejected",
            extracted_at="2026-01-03T00:01:00Z",
            extraction=rejected,
        ),
    ])
    manual = pd.DataFrame([
        _manual_review(
            review_id="manual-valid",
            extraction=reviewed_auto,
            source_hash="hash-review",
            status="manually_validated",
            corrected_extraction=reviewed_manual,
            source_attempt_id="reviewed-auto",
        ),
        _manual_review(
            review_id="manual-rejected",
            extraction=rejected,
            source_hash="hash-rejected",
            status="rejected",
            source_attempt_id="rejected-auto",
        ),
    ])
    stored = {
        "attempts": normalise_ai_extraction_attempts_log(historical),
    }

    async def fake_extract(
        received_run_df,
        *,
        agent,
        attempts_path,
        checkpoint_every,
    ):
        assert received_run_df is run_df
        assert agent == "fake-agent"
        assert attempts_path == tmp_path / "attempts.parquet"
        stored["attempts"] = combine_ai_extraction_attempt_frames(
            stored["attempts"],
            normalise_ai_extraction_attempts_log(pd.DataFrame(new_records)),
        )
        return copy.deepcopy(new_records)

    monkeypatch.setattr(
        runner_module,
        "extract_documents",
        fake_extract,
    )
    monkeypatch.setattr(
        runner_module,
        "load_ai_extraction_attempts",
        lambda path: stored["attempts"],
    )
    written_paths = []

    def save_under_tmp(dataframe, path):
        assert path.parent == tmp_path
        written_paths.append(path)
        real_save_parquet_atomic(dataframe, path)

    def append_metric_under_tmp(dataframe, path):
        assert path.parent == tmp_path
        written_paths.append(path)
        return real_append_quality_metric(dataframe, path)

    monkeypatch.setattr(
        runner_module,
        "save_parquet_atomic",
        save_under_tmp,
    )
    monkeypatch.setattr(
        runner_module,
        "append_quality_metric",
        append_metric_under_tmp,
    )
    current_path = tmp_path / "current.parquet"
    queue_path = tmp_path / "queue.parquet"
    quality_path = tmp_path / "quality.parquet"

    result = asyncio.run(
        run_and_finalize_extractions(
            run_df,
            source_df,
            agent="fake-agent",
            attempts_path=tmp_path / "attempts.parquet",
            current_path=current_path,
            review_queue_path=queue_path,
            quality_metrics_path=quality_path,
            manual_reviews=manual,
            run_scope="integration",
            checkpoint_every=2,
        )
    )

    assert written_paths == [current_path, queue_path, quality_path]
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "current.parquet",
        "quality.parquet",
        "queue.parquet",
    ]
    assert result["all_attempts"]["attempt_id"].tolist() == [
        "reviewed-auto",
        "rejected-auto",
        "new-auto",
        "new-error",
    ]
    assert result["current_extractions"]["identificador_boe"].tolist() == [
        automatic.boe_id,
        reviewed_auto.boe_id,
    ]
    assert result["current_extractions"]["selection_source"].tolist() == [
        "auto_validated",
        "manually_validated",
    ]
    assert result["review_queue"]["identificador_boe"].tolist() == [error_id]
    metric = result["quality_metric"].iloc[0]
    assert metric["n_source_documents"] == 4
    assert metric["n_latest_attempts"] == 4
    assert metric["n_auto_validated"] == 1
    assert metric["n_manually_validated"] == 1
    assert metric["n_rejected"] == 1
    assert metric["n_review_required"] == 1
    assert (
        metric["n_auto_validated"]
        + metric["n_manually_validated"]
        + metric["n_rejected"]
        <= metric["n_source_documents"]
    )
    assert metric["automatic_validation_rate"] == pytest.approx(0.25)
    assert metric["effective_validation_rate"] == pytest.approx(0.5)
    persisted_current = pd.read_parquet(current_path)
    persisted_queue = pd.read_parquet(queue_path)
    persisted_quality = pd.read_parquet(quality_path)
    assert persisted_current["identificador_boe"].tolist() == [
        automatic.boe_id,
        reviewed_auto.boe_id,
    ]
    assert persisted_queue["identificador_boe"].tolist() == [error_id]
    assert persisted_quality["quality_run_id"].tolist() == (
        result["quality_metric"]["quality_run_id"].tolist()
    )


def test_run_and_finalize_extractions_keeps_async_public_signature() -> None:
    assert iscoroutinefunction(run_and_finalize_extractions)
    assert tuple(signature(run_and_finalize_extractions).parameters) == (
        "run_df",
        "source_df",
        "agent",
        "attempts_path",
        "current_path",
        "review_queue_path",
        "quality_metrics_path",
        "manual_reviews",
        "run_scope",
        "minimum_auto_validation_rate",
        "checkpoint_every",
    )


def test_no_deferred_or_artificial_finalize_code_was_added() -> None:
    # AST is intentional: finalization must not absorb notebook-only review,
    # pilot, or flatten orchestration behind an unconditional wrapper.
    source = Path(runner_module.__file__).read_text()
    tree = ast.parse(source)

    assert "load_manual_review_files" not in source
    assert "save_flattened_extractions" not in source
    assert "load_pilot_scope_labels" not in source
    assert "evaluate_pilot" not in source
    assert not hasattr(runner_module, "agent")
    assert not any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Constant)
        and node.test.value is True
        for node in tree.body
    )
