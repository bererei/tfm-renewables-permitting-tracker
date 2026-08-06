import warnings
from datetime import date, datetime, timezone
from hashlib import sha256
from inspect import signature
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

import renewables_permitting.extraction.review as review_module
from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
)
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    BOEProjectExtraction,
    BOESourceDocument,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationType,
    PublicationEvent,
)
from renewables_permitting.extraction.review import (
    AI_EXTRACTION_LOG_COLUMNS,
    MANUAL_REVIEW_COLUMNS,
    REVIEW_QUEUE_COLUMNS,
    _latest_attempts_for_current_sources,
    _latest_manual_reviews_for_current_sources,
    _normalise_table,
    build_pending_candidates,
    build_quality_metric,
    build_review_queue,
    combine_ai_extraction_attempt_frames,
    current_successful_ai_extractions,
    empty_ai_extraction_attempts_log,
    empty_manual_reviews,
    empty_review_queue,
    normalise_ai_extraction_attempts_log,
    normalise_manual_reviews,
    select_best_valid_extractions,
)
from renewables_permitting.extraction.validation import (
    validate_extraction_against_document,
)


EXPECTED_AI_EXTRACTION_LOG_COLUMNS = [
    "attempt_id",
    "identificador_boe",
    "fecha_publicacion",
    "titulo",
    "source_document_sha256",
    "input_text_chars",
    "input_text_sha256",
    "input_selection_strategy",
    "input_selection_marker",
    "input_excluded_chars",
    "extraction_config_id",
    "contract_schema_sha256",
    "instructions_sha256",
    "model_provider",
    "model_name",
    "document_validation_version",
    "classification_status",
    "document_scope",
    "classification_reason",
    "n_publication_events",
    "n_generation_assets",
    "n_associated_components",
    "n_administrative_actions",
    "n_participants",
    "n_administrative_locations",
    "n_generation_relations",
    "n_technical_mentions",
    "extraction_json",
    "extracted_at",
    "duration_seconds",
    "usage_requests",
    "usage_input_tokens",
    "usage_output_tokens",
    "usage_total_tokens",
    "extraction_status",
    "error_type",
    "error_message",
    "processing_stage",
    "document_validation_status",
    "document_validation_issue_count",
    "validation_issues_json",
    "deterministic_adjustment_count",
    "deterministic_adjustments_json",
]

EXPECTED_REVIEW_QUEUE_COLUMNS = [
    "review_queue_id",
    "identificador_boe",
    "fecha_publicacion",
    "titulo",
    "source_document_sha256",
    "source_attempt_id",
    "extraction_config_id",
    "document_validation_version",
    "classification_reason",
    "reason_code",
    "reason_severity",
    "reason_message",
    "error_type",
    "error_message",
    "processing_stage",
    "validation_issues_json",
    "proposed_extraction_json",
    "queue_status",
    "queued_at",
]

EXPECTED_MANUAL_REVIEW_COLUMNS = [
    "manual_review_id",
    "identificador_boe",
    "source_document_sha256",
    "source_attempt_id",
    "review_status",
    "corrected_extraction_json",
    "reviewer",
    "review_notes",
    "reviewed_at",
    "contract_schema_sha256",
    "document_validation_version",
]

_DEFAULT_EXTRACTION_JSON = object()


def _source_document_hash(
    *,
    boe_id: str,
    publication_date: date,
    title: str,
    text: str,
) -> str:
    value = "\n".join([boe_id, publication_date.isoformat(), title, text])
    return sha256(value.encode("utf-8")).hexdigest()


def _test_document(
    boe_id: str,
    title: str,
    text: str | None = None,
) -> BOESourceDocument:
    body = text or title
    publication_date = date(2026, 1, 1)
    return BOESourceDocument(
        boe_id=boe_id,
        publication_date=publication_date,
        title=title,
        text=body,
        source_document_sha256=_source_document_hash(
            boe_id=boe_id,
            publication_date=publication_date,
            title=title,
            text=body,
        ),
    )


def _test_extraction(
    boe_id: str,
    events: list[PublicationEvent],
) -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación relativa a una planta de generación.",
        publication_events=events,
        extraction_notes=None,
        boe_id=boe_id,
        publication_date=date(2026, 1, 1),
    )


def _asset(
    ref: str,
    name: str,
    generation_type: GenerationType,
    evidence: str,
) -> GenerationAssetMention:
    return GenerationAssetMention(
        local_generation_asset_ref=ref,
        names_raw=[name],
        generation_type=generation_type,
        technical_mentions=[],
        evidence=evidence,
    )


def _action(
    action_type: AdministrativeActionType,
    decision: AdministrativeDecision,
    evidence: str,
    targets: list[str] | None = None,
) -> AdministrativeAction:
    return AdministrativeAction(
        action_type=action_type,
        decision=decision,
        is_modification=False,
        targets=targets or [],
        evidence=evidence,
    )


def _canonicalize_test(
    document: BOESourceDocument,
    extraction: BOEProjectExtraction,
) -> BOEProjectExtraction:
    canonical, _ = canonicalize_project_extraction(
        extraction,
        source_text=f"{document.title}\n{document.text}",
        document_title=document.title,
    )
    validate_extraction_against_document(
        document=document,
        extraction=canonical,
    )
    return canonical


def _extraction(
    boe_id: str = "BOE-A-2026-10001",
    *,
    name: str = "Aurora",
    classification_status: ClassificationStatus = ClassificationStatus.CLASSIFIED,
) -> BOEProjectExtraction:
    if classification_status == ClassificationStatus.UNCERTAIN:
        return BOEProjectExtraction(
            classification_status=classification_status,
            document_scope=None,
            classification_reason="Clasificación incierta.",
            publication_events=[],
            extraction_notes=None,
            boe_id=boe_id,
            publication_date=date(2026, 1, 1),
        )
    title = f"Autorización de la planta fotovoltaica {name}."
    return _test_extraction(
        boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                name,
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
                ["event"],
            )],
            event_summary=f"Autorización de {name}.",
        )],
    )


def _source_df(
    *rows: tuple[str, str, str],
) -> pd.DataFrame:
    records = []
    for position, (boe_id, source_hash, title) in enumerate(rows, start=1):
        records.append({
            "identificador": boe_id,
            "fecha_publicacion": pd.Timestamp("2026-01-01"),
            "titulo": title,
            "texto_limpio": title,
            "source_document_sha256": source_hash,
            "candidate_order": position,
        })
    return pd.DataFrame(records)


def _attempt(
    *,
    attempt_id: str,
    extraction: BOEProjectExtraction | None,
    source_hash: str,
    extracted_at: str,
    boe_id: str | None = None,
    extraction_status: str = "ok",
    document_validation_status: str = "passed",
    extraction_json: object = _DEFAULT_EXTRACTION_JSON,
    error_type: str | None = None,
    error_message: str | None = None,
    processing_stage: str = "completed",
    validation_issues_json: str | None = None,
    extraction_config_id: str = EXTRACTION_CONFIG_ID,
    document_validation_version: str = DOCUMENT_VALIDATION_VERSION,
) -> dict:
    effective_boe_id = boe_id or (extraction.boe_id if extraction else None)
    if extraction_json is _DEFAULT_EXTRACTION_JSON:
        extraction_json = extraction.model_dump_json() if extraction else None
    return {
        "attempt_id": attempt_id,
        "identificador_boe": effective_boe_id,
        "fecha_publicacion": pd.Timestamp("2026-01-01"),
        "titulo": f"Título {effective_boe_id}",
        "source_document_sha256": source_hash,
        "extraction_config_id": extraction_config_id,
        "document_validation_version": document_validation_version,
        "classification_status": (
            extraction.classification_status.value if extraction else None
        ),
        "classification_reason": (
            extraction.classification_reason if extraction else None
        ),
        "extraction_json": extraction_json,
        "extracted_at": pd.Timestamp(extracted_at),
        "extraction_status": extraction_status,
        "error_type": error_type,
        "error_message": error_message,
        "processing_stage": processing_stage,
        "document_validation_status": document_validation_status,
        "validation_issues_json": validation_issues_json,
    }


def _manual_review(
    *,
    review_id: str,
    extraction: BOEProjectExtraction,
    source_hash: str,
    reviewed_at: str,
    review_status: str,
    corrected_extraction_json: str | None = None,
) -> dict:
    return {
        "manual_review_id": review_id,
        "identificador_boe": extraction.boe_id,
        "source_document_sha256": source_hash,
        "source_attempt_id": "automatic",
        "review_status": review_status,
        "corrected_extraction_json": (
            extraction.model_dump_json()
            if corrected_extraction_json is None
            else corrected_extraction_json
        ),
        "reviewer": "reviewer",
        "review_notes": "Revisión.",
        "reviewed_at": pd.Timestamp(reviewed_at),
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }


def test_column_contracts_are_exact() -> None:
    assert AI_EXTRACTION_LOG_COLUMNS == EXPECTED_AI_EXTRACTION_LOG_COLUMNS
    assert REVIEW_QUEUE_COLUMNS == EXPECTED_REVIEW_QUEUE_COLUMNS
    assert MANUAL_REVIEW_COLUMNS == EXPECTED_MANUAL_REVIEW_COLUMNS
    assert len(AI_EXTRACTION_LOG_COLUMNS) == 43
    assert len(REVIEW_QUEUE_COLUMNS) == 19
    assert len(MANUAL_REVIEW_COLUMNS) == 11


def test_empty_tables_have_exact_column_contracts() -> None:
    attempts = empty_ai_extraction_attempts_log()
    queue = empty_review_queue()
    reviews = empty_manual_reviews()

    assert attempts.empty
    assert queue.empty
    assert reviews.empty
    assert attempts.columns.tolist() == EXPECTED_AI_EXTRACTION_LOG_COLUMNS
    assert queue.columns.tolist() == EXPECTED_REVIEW_QUEUE_COLUMNS
    assert reviews.columns.tolist() == EXPECTED_MANUAL_REVIEW_COLUMNS
    assert str(queue["identificador_boe"].dtype) == "string"
    assert str(queue["fecha_publicacion"].dtype) == "datetime64[ns]"
    assert str(queue["queued_at"].dtype) == "datetime64[ns, UTC]"


@pytest.mark.parametrize(
    ("normalise", "required_columns"),
    [
        (normalise_ai_extraction_attempts_log, AI_EXTRACTION_LOG_COLUMNS),
        (normalise_manual_reviews, MANUAL_REVIEW_COLUMNS),
    ],
)
def test_normalisation_adds_required_columns_preserves_history_and_does_not_mutate(
    normalise,
    required_columns: list[str],
) -> None:
    original = pd.DataFrame({
        required_columns[0]: ["value"],
        "historical_column": ["historical"],
    }, index=[7])
    snapshot = original.copy(deep=True)

    result = normalise(original)

    pd.testing.assert_frame_equal(original, snapshot)
    assert result.columns.tolist() == [*required_columns, "historical_column"]
    assert result.index.tolist() == [7]
    assert result.loc[7, "historical_column"] == "historical"


@pytest.mark.parametrize(
    ("normalise", "required_columns"),
    [
        (normalise_ai_extraction_attempts_log, AI_EXTRACTION_LOG_COLUMNS),
        (normalise_manual_reviews, MANUAL_REVIEW_COLUMNS),
    ],
)
def test_normalisation_preserves_extra_columns_for_empty_frames(
    normalise,
    required_columns: list[str],
) -> None:
    original = pd.DataFrame(columns=["historical_column"])
    result = normalise(original)

    assert result.empty
    assert result.columns.tolist() == [*required_columns, "historical_column"]
    assert original.columns.tolist() == ["historical_column"]


def test_normalise_table_uses_requested_contract_and_preserves_extras() -> None:
    original = pd.DataFrame({"b": [2], "historical": [3]})
    snapshot = original.copy(deep=True)

    result = _normalise_table(original, ["a", "b"])

    pd.testing.assert_frame_equal(original, snapshot)
    assert result.columns.tolist() == ["a", "b", "historical"]
    assert pd.isna(result.loc[0, "a"])


def test_combine_empty_history_and_new_attempts() -> None:
    new_attempts = pd.DataFrame([{
        "attempt_id": "new",
        "historical_column": "kept",
    }])

    combined = combine_ai_extraction_attempt_frames(
        empty_ai_extraction_attempts_log(),
        new_attempts,
    )

    assert combined["attempt_id"].tolist() == ["new"]
    assert combined["historical_column"].tolist() == ["kept"]
    assert combined is not new_attempts


def test_combine_history_and_new_attempts_preserves_order_and_extra_columns() -> None:
    existing = pd.DataFrame([{
        "attempt_id": "old",
        "old_historical_column": "old",
    }])
    new_attempts = pd.DataFrame([{
        "attempt_id": "new",
        "new_historical_column": "new",
    }])

    combined = combine_ai_extraction_attempt_frames(existing, new_attempts)

    assert combined["attempt_id"].tolist() == ["old", "new"]
    assert combined.columns.tolist() == [
        *AI_EXTRACTION_LOG_COLUMNS,
        "old_historical_column",
        "new_historical_column",
    ]
    assert combined.loc[0, "old_historical_column"] == "old"
    assert combined.loc[1, "new_historical_column"] == "new"


def test_attempt_log_combination_has_no_future_warning() -> None:
    existing = normalise_ai_extraction_attempts_log(
        pd.DataFrame([{
            "attempt_id": "attempt_1",
            "identificador_boe": "BOE-A-TEST-1",
            "extraction_status": "ok",
            "error_type": pd.NA,
            "error_message": pd.NA,
            "validation_issues_json": pd.NA,
        }])
    )
    new_attempts = normalise_ai_extraction_attempts_log(
        pd.DataFrame([{
            "attempt_id": "attempt_2",
            "identificador_boe": "BOE-A-TEST-2",
            "extraction_status": "ok",
            "error_type": pd.NA,
            "error_message": pd.NA,
            "validation_issues_json": pd.NA,
        }])
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        combined = combine_ai_extraction_attempt_frames(
            existing,
            new_attempts,
        )
    assert set(combined["attempt_id"].astype(str)) == {
        "attempt_1",
        "attempt_2",
    }
    assert not any(
        issubclass(item.category, FutureWarning)
        for item in caught
    )


def test_current_successful_selects_latest_current_source_and_excludes_errors() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="older",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
        _attempt(
            attempt_id="newer",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-02T00:00:00Z",
        ),
        _attempt(
            attempt_id="latest_error",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-03T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
        ),
        _attempt(
            attempt_id="changed_source",
            extraction=extraction,
            source_hash="old",
            extracted_at="2026-01-04T00:00:00Z",
        ),
    ])

    current = current_successful_ai_extractions(attempts, source_df)

    assert current["attempt_id"].tolist() == ["newer"]


def test_current_sources_distinguish_changed_document_hash() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "new-hash", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="old-source",
            extraction=extraction,
            source_hash="old-hash",
            extracted_at="2026-01-02T00:00:00Z",
        ),
    ])

    current = current_successful_ai_extractions(attempts, source_df)
    queue = build_review_queue(attempts=attempts, source_df=source_df)
    metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=None,
        run_scope="hash-mismatch",
    ).iloc[0]

    assert current.empty
    assert queue["reason_code"].tolist() == ["source_not_attempted"]
    assert queue["source_attempt_id"].isna().all()
    assert metric["n_source_documents"] == 1
    assert metric["n_latest_attempts"] == 0
    assert metric["n_unattempted"] == 1
    assert metric["coverage_rate"] == 0.0
    assert metric["quality_status"] == "degraded"


@pytest.mark.parametrize("invalid_json", [None, "", "{not-json"])
def test_current_successful_rejects_null_empty_or_invalid_extraction_json(
    invalid_json: str | None,
) -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="invalid",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_json=invalid_json,
        ),
    ])

    with pytest.raises(ValidationError):
        current_successful_ai_extractions(attempts, source_df)


def test_invalid_json_in_error_attempt_is_not_parsed() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="error",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
            extraction_json="{not-json",
        ),
    ])

    assert current_successful_ai_extractions(attempts, source_df).empty


def test_build_pending_candidates_respects_success_errors_and_source_changes() -> None:
    first = _extraction("BOE-A-2026-10001", name="Aurora")
    second = _extraction("BOE-A-2026-10002", name="Boreal")
    third = _extraction("BOE-A-2026-10003", name="Cierzo")
    source_df = _source_df(
        (first.boe_id, "hash-a", "Aurora"),
        (second.boe_id, "hash-b", "Boreal"),
        (third.boe_id, "new-hash-c", "Cierzo"),
    )
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="success-a",
            extraction=first,
            source_hash="hash-a",
            extracted_at="2026-01-01T00:00:00Z",
        ),
        _attempt(
            attempt_id="error-b",
            extraction=second,
            source_hash="hash-b",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
        ),
        _attempt(
            attempt_id="old-success-c",
            extraction=third,
            source_hash="old-hash-c",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])

    current, pending = build_pending_candidates(source_df, attempts)

    assert current["identificador_boe"].tolist() == [first.boe_id]
    assert pending["identificador"].tolist() == [second.boe_id, third.boe_id]
    assert pending.columns.tolist() == source_df.columns.tolist()
    assert pending["candidate_order"].tolist() == [2, 3]


def test_manual_validation_precedes_automatic_and_outputs_valid_contract() -> None:
    automatic = _extraction(name="Aurora")
    corrected = _extraction(name="Aurora Corregida")
    source_df = _source_df((automatic.boe_id, "current", "Título actual"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="automatic",
            extraction=automatic,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="manual",
            extraction=corrected,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="manually_validated",
        ),
    ])
    attempts_snapshot = attempts.copy(deep=True)
    sources_snapshot = source_df.copy(deep=True)
    reviews_snapshot = manual_reviews.copy(deep=True)

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )

    assert selected["selection_source"].tolist() == ["manually_validated"]
    assert selected["attempt_id"].tolist() == ["manual"]
    parsed = BOEProjectExtraction.model_validate_json(
        str(selected.iloc[0]["extraction_json"])
    )
    assert parsed.publication_events[0].generation_assets[0].names_raw == [
        "Aurora Corregida"
    ]
    pd.testing.assert_frame_equal(attempts, attempts_snapshot)
    pd.testing.assert_frame_equal(source_df, sources_snapshot)
    pd.testing.assert_frame_equal(manual_reviews, reviews_snapshot)


def test_manual_rejection_removes_automatic_extraction() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="automatic",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="rejected",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="rejected",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )

    assert selected.empty


def test_old_manual_review_does_not_apply_after_source_changes() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "new-source", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="automatic",
            extraction=extraction,
            source_hash="new-source",
            extracted_at="2026-01-02T00:00:00Z",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="old-rejection",
            extraction=extraction,
            source_hash="old-source",
            reviewed_at="2026-01-03T00:00:00Z",
            review_status="rejected",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )

    assert selected["attempt_id"].tolist() == ["automatic"]
    assert selected["selection_source"].tolist() == ["auto_validated"]


def test_latest_manual_review_uses_reviewed_at_then_review_id() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="automatic",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="a",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="manually_validated",
        ),
        _manual_review(
            review_id="b",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="rejected",
        ),
        _manual_review(
            review_id="newer",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-03T00:00:00Z",
            review_status="manually_validated",
        ),
    ])

    latest = _latest_manual_reviews_for_current_sources(
        manual_reviews,
        source_df,
    )

    assert latest["manual_review_id"].tolist() == ["newer"]
    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )
    assert selected["attempt_id"].tolist() == ["newer"]
    assert selected["selection_source"].tolist() == ["manually_validated"]


def test_unknown_manual_status_does_not_override_automatic() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="automatic",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="invalid-status",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="invalid",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )

    assert selected["attempt_id"].tolist() == ["automatic"]
    assert selected["selection_source"].tolist() == ["auto_validated"]


def test_invalid_manually_validated_json_is_rejected() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="invalid-json",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="manually_validated",
            corrected_extraction_json="{not-json",
        ),
    ])

    with pytest.raises(ValidationError):
        select_best_valid_extractions(
            attempts=empty_ai_extraction_attempts_log(),
            source_df=source_df,
            manual_reviews=manual_reviews,
        )


def test_latest_attempts_order_and_deduplication_are_stable() -> None:
    first = _extraction("BOE-A-2026-10001", name="Aurora")
    second = _extraction("BOE-A-2026-10002", name="Boreal")
    source_df = _source_df(
        (first.boe_id, "hash-a", "Aurora"),
        (second.boe_id, "hash-b", "Boreal"),
    )
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="b-late",
            extraction=second,
            source_hash="hash-b",
            extracted_at="2026-01-03T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
        ),
        _attempt(
            attempt_id="a-old",
            extraction=first,
            source_hash="hash-a",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
        ),
        _attempt(
            attempt_id="a-new",
            extraction=first,
            source_hash="hash-a",
            extracted_at="2026-01-02T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
        ),
    ])

    latest = _latest_attempts_for_current_sources(attempts, source_df)

    assert latest["attempt_id"].tolist() == ["a-new", "b-late"]
    assert latest["identificador_boe"].is_unique


def test_review_queue_empty_and_successful_cases() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    successful = pd.DataFrame([
        _attempt(
            attempt_id="success",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])

    unattempted = build_review_queue(
        attempts=empty_ai_extraction_attempts_log(),
        source_df=source_df,
    )
    assert unattempted["reason_code"].tolist() == ["source_not_attempted"]
    assert unattempted["source_attempt_id"].isna().all()
    assert unattempted[
        [
            "extraction_config_id",
            "document_validation_version",
            "classification_reason",
            "error_type",
            "error_message",
            "processing_stage",
            "validation_issues_json",
            "proposed_extraction_json",
        ]
    ].isna().all().all()
    assert build_review_queue(
        attempts=successful,
        source_df=source_df,
    ).empty
    assert build_review_queue(
        attempts=empty_ai_extraction_attempts_log(),
        source_df=_source_df(),
    ).empty


def test_review_queue_preserves_exact_error_reason_state_order_and_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _extraction("BOE-A-2026-10001", name="Aurora")
    second = _extraction("BOE-A-2026-10002", name="Boreal")
    source_df = _source_df(
        (first.boe_id, "hash-a", "Aurora"),
        (second.boe_id, "hash-b", "Boreal"),
    )
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="second-error",
            extraction=second,
            source_hash="hash-b",
            extracted_at="2026-01-03T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
            error_type="RuntimeError",
            error_message="fallo del agente",
            processing_stage="agent_run",
        ),
        _attempt(
            attempt_id="first-validation",
            extraction=first,
            source_hash="hash-a",
            extracted_at="2026-01-02T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
            error_type="DocumentExtractionValidationError",
            error_message="evidence no es literal.",
            processing_stage="document_validation",
            validation_issues_json='["evidence no es literal."]',
        ),
        _attempt(
            attempt_id="first-older",
            extraction=first,
            source_hash="hash-a",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
            error_type="OldError",
        ),
    ])
    fixed_now = datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc)

    class FixedDateTime:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            return fixed_now

    monkeypatch.setattr(review_module, "datetime", FixedDateTime)

    queue = build_review_queue(attempts=attempts, source_df=source_df)

    assert queue["source_attempt_id"].tolist() == [
        "first-validation",
        "second-error",
    ]
    assert queue["error_type"].tolist() == [
        "DocumentExtractionValidationError",
        "RuntimeError",
    ]
    assert queue["error_message"].tolist() == [
        "evidence no es literal.",
        "fallo del agente",
    ]
    assert queue["processing_stage"].tolist() == [
        "document_validation",
        "agent_run",
    ]
    assert queue["validation_issues_json"].iloc[0] == (
        '["evidence no es literal."]'
    )
    assert queue["queue_status"].tolist() == ["pending", "pending"]
    assert queue["queued_at"].tolist() == [fixed_now, fixed_now]
    assert queue["identificador_boe"].is_unique
    assert queue["reason_code"].tolist() == [
        "document_validation_failed",
        "document_validation_failed",
    ]
    assert queue["reason_severity"].tolist() == ["blocking", "blocking"]
    assert queue["review_queue_id"].tolist() == [
        sha256(
            (
                f"{first.boe_id}|hash-a|first-validation|"
                "document_validation_failed"
            ).encode("utf-8")
        ).hexdigest()[:24],
        sha256(
            (
                f"{second.boe_id}|hash-b|second-error|"
                "document_validation_failed"
            ).encode("utf-8")
        ).hexdigest()[:24],
    ]


def test_successful_uncertain_extraction_is_queued_with_lineage() -> None:
    extraction = _extraction(
        classification_status=ClassificationStatus.UNCERTAIN
    )
    source_df = _source_df((extraction.boe_id, "current", "Título incierto"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="uncertain",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])

    queue = build_review_queue(attempts=attempts, source_df=source_df)
    metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=None,
        run_scope="uncertain-without-previous",
    ).iloc[0]

    assert queue["reason_code"].tolist() == ["classification_uncertain"]
    assert queue["reason_severity"].tolist() == ["blocking"]
    assert queue["source_attempt_id"].tolist() == ["uncertain"]
    assert queue["classification_reason"].tolist() == [
        "Clasificación incierta."
    ]
    assert queue["proposed_extraction_json"].tolist() == [
        extraction.model_dump_json()
    ]
    assert queue["source_document_sha256"].tolist() == ["current"]
    assert queue["extraction_config_id"].tolist() == [EXTRACTION_CONFIG_ID]
    assert queue["document_validation_version"].tolist() == [
        DOCUMENT_VALIDATION_VERSION
    ]
    assert current_successful_ai_extractions(attempts, source_df).empty
    assert metric["n_auto_validated"] == 0
    assert metric["n_uncertain"] == 1
    assert metric["automatic_validation_rate"] == 0.0
    assert metric["effective_validation_rate"] == 0.0
    assert metric["n_review_required"] == 1
    assert metric["quality_status"] == "degraded"


def test_manual_validation_can_resolve_uncertain_extraction() -> None:
    uncertain = _extraction(
        classification_status=ClassificationStatus.UNCERTAIN
    )
    corrected = _extraction(uncertain.boe_id, name="Aurora validada")
    source_df = _source_df((uncertain.boe_id, "current", "Título incierto"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="uncertain",
            extraction=uncertain,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="manual-valid",
            extraction=corrected,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status="manually_validated",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )

    assert selected["attempt_id"].tolist() == ["manual-valid"]
    assert selected["selection_source"].tolist() == ["manually_validated"]
    assert build_review_queue(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    ).empty


def test_latest_uncertain_keeps_older_classified_current_and_is_queued() -> None:
    classified = _extraction()
    uncertain = _extraction(
        classification_status=ClassificationStatus.UNCERTAIN
    )
    source_df = _source_df((classified.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="classified-old",
            extraction=classified,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
        _attempt(
            attempt_id="uncertain-new",
            extraction=uncertain,
            source_hash="current",
            extracted_at="2026-01-02T00:00:00Z",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
    )
    queue = build_review_queue(attempts=attempts, source_df=source_df)
    metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=None,
        run_scope="uncertain-after-valid",
    ).iloc[0]

    assert selected["attempt_id"].tolist() == ["classified-old"]
    assert queue["source_attempt_id"].tolist() == ["uncertain-new"]
    assert queue["reason_code"].tolist() == ["classification_uncertain"]
    assert metric["n_auto_validated"] == 1
    assert metric["automatic_validation_rate"] == 1.0
    assert metric["effective_validation_rate"] == 1.0
    assert metric["n_uncertain"] == 1
    assert metric["n_review_required"] == 1
    assert metric["quality_status"] == "degraded"


def test_latest_failed_attempt_keeps_older_valid_current_and_is_queued() -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="valid-old",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
        ),
        _attempt(
            attempt_id="failed-new",
            extraction=None,
            boe_id=extraction.boe_id,
            source_hash="current",
            extracted_at="2026-01-02T00:00:00Z",
            extraction_status="error",
            document_validation_status=None,
            error_type="RuntimeError",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
    )
    queue = build_review_queue(attempts=attempts, source_df=source_df)
    metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=None,
        run_scope="failure-after-valid",
    ).iloc[0]

    assert selected["attempt_id"].tolist() == ["valid-old"]
    assert queue["source_attempt_id"].tolist() == ["failed-new"]
    assert queue["reason_code"].tolist() == ["extraction_error"]
    assert metric["n_auto_validated"] == 1
    assert metric["automatic_validation_rate"] == 1.0
    assert metric["effective_validation_rate"] == 1.0
    assert metric["n_review_required"] == 1
    assert metric["quality_status"] == "degraded"


def test_latest_failed_attempt_without_previous_valid_is_not_auto_validated() -> None:
    boe_id = "BOE-A-2026-10001"
    source_df = _source_df((boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="failed",
            extraction=None,
            boe_id=boe_id,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_status="error",
            document_validation_status=None,
            error_type="RuntimeError",
        ),
    ])

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
    )
    queue = build_review_queue(attempts=attempts, source_df=source_df)
    metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=None,
        run_scope="failure-without-previous",
    ).iloc[0]

    assert selected.empty
    assert queue["source_attempt_id"].tolist() == ["failed"]
    assert queue["reason_code"].tolist() == ["extraction_error"]
    assert metric["n_auto_validated"] == 0
    assert metric["automatic_validation_rate"] == 0.0
    assert metric["effective_validation_rate"] == 0.0
    assert metric["n_review_required"] == 1
    assert metric["quality_status"] == "degraded"


@pytest.mark.parametrize("status", ["manually_validated", "rejected"])
def test_resolved_manual_review_removes_item_from_queue(status: str) -> None:
    extraction = _extraction()
    source_df = _source_df((extraction.boe_id, "current", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="error",
            extraction=extraction,
            source_hash="current",
            extracted_at="2026-01-01T00:00:00Z",
            extraction_status="error",
            document_validation_status="failed",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_review(
            review_id="resolved",
            extraction=extraction,
            source_hash="current",
            reviewed_at="2026-01-02T00:00:00Z",
            review_status=status,
        ),
    ])

    queue = build_review_queue(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )

    assert queue.empty


def test_review_queue_and_manual_precedence() -> None:
    title = "Autorización de la planta fotovoltaica Aurora."
    document = _test_document("BOE-A-2026-10100", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Aurora",
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
                ["event"],
            )],
            event_summary="Autorización de Aurora.",
        )],
    )
    extraction = _canonicalize_test(document, extraction)
    source_df = pd.DataFrame([{
        "identificador": document.boe_id,
        "fecha_publicacion": pd.Timestamp(document.publication_date),
        "titulo": document.title,
        "texto_limpio": document.text,
        "source_document_sha256": document.source_document_sha256,
    }])
    attempt_record = {
        **{column: pd.NA for column in AI_EXTRACTION_LOG_COLUMNS},
        "attempt_id": "automatic_error",
        "identificador_boe": document.boe_id,
        "fecha_publicacion": pd.Timestamp(document.publication_date),
        "titulo": document.title,
        "source_document_sha256": document.source_document_sha256,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "extraction_json": extraction.model_dump_json(),
        "extracted_at": pd.Timestamp("2026-01-01", tz="UTC"),
        "extraction_status": "error",
        "error_type": "DocumentExtractionValidationError",
        "error_message": "Revisión necesaria.",
        "processing_stage": "document_validation",
        "document_validation_status": "failed",
    }
    attempts = normalise_ai_extraction_attempts_log(
        pd.DataFrame([attempt_record])
    )
    queue = build_review_queue(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=empty_manual_reviews(),
    )
    assert len(queue) == 1

    manual_reviews = normalise_manual_reviews(pd.DataFrame([{
        "manual_review_id": "manual_valid",
        "identificador_boe": document.boe_id,
        "source_document_sha256": document.source_document_sha256,
        "source_attempt_id": "automatic_error",
        "review_status": "manually_validated",
        "corrected_extraction_json": extraction.model_dump_json(),
        "reviewer": "test",
        "review_notes": "Validación de regresión.",
        "reviewed_at": pd.Timestamp("2026-01-02", tz="UTC"),
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }]))
    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    )
    assert len(selected) == 1
    assert selected.iloc[0]["selection_source"] == "manually_validated"
    assert build_review_queue(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
    ).empty


@pytest.mark.parametrize("invalid_value", [None, pd.NA, "   "])
def test_target_corpus_rejects_null_or_empty_boe_id(invalid_value) -> None:
    source_df = _source_df(("BOE-A-2026-10001", "hash-a", "Aurora"))
    source_df.loc[0, "identificador"] = invalid_value

    with pytest.raises(ValueError, match="identificadores BOE nulos o vacíos"):
        build_review_queue(
            attempts=empty_ai_extraction_attempts_log(),
            source_df=source_df,
        )


def test_target_corpus_rejects_duplicate_boe_ids() -> None:
    source_df = _source_df(
        ("BOE-A-2026-10001", "hash-a", "Aurora"),
        ("BOE-A-2026-10001", "hash-b", "Aurora duplicada"),
    )

    with pytest.raises(ValueError, match="identificadores BOE duplicados"):
        build_review_queue(
            attempts=empty_ai_extraction_attempts_log(),
            source_df=source_df,
        )


def test_target_corpus_rejects_null_source_hash() -> None:
    source_df = _source_df(("BOE-A-2026-10001", "hash-a", "Aurora"))
    source_df.loc[0, "source_document_sha256"] = pd.NA

    with pytest.raises(ValueError, match="source_document_sha256"):
        build_review_queue(
            attempts=empty_ai_extraction_attempts_log(),
            source_df=source_df,
        )


def test_attempt_outside_target_corpus_is_ignored() -> None:
    target = _extraction("BOE-A-2026-10001", name="Aurora")
    external = _extraction("BOE-A-2026-99999", name="Externa")
    source_df = _source_df((target.boe_id, "target-hash", "Aurora"))
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="external",
            extraction=external,
            source_hash="external-hash",
            extracted_at="2026-01-01T00:00:00Z",
        ),
    ])

    queue = build_review_queue(attempts=attempts, source_df=source_df)

    assert current_successful_ai_extractions(attempts, source_df).empty
    assert queue["identificador_boe"].tolist() == [target.boe_id]
    assert queue["reason_code"].tolist() == ["source_not_attempted"]
    assert queue["source_attempt_id"].isna().all()


def test_selection_and_queue_are_independent_of_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _extraction("BOE-A-2026-10001", name="Aurora")
    second = _extraction("BOE-A-2026-10002", name="Boreal")
    third = _extraction("BOE-A-2026-10003", name="Cierzo")
    source_df = _source_df(
        (first.boe_id, "hash-a", "Aurora"),
        (second.boe_id, "hash-b", "Boreal"),
        (third.boe_id, "hash-c", "Cierzo"),
    )
    attempts = pd.DataFrame([
        _attempt(
            attempt_id="classified",
            extraction=first,
            source_hash="hash-a",
            extracted_at="2026-01-01T00:00:00Z",
        ),
        _attempt(
            attempt_id="uncertain",
            extraction=_extraction(
                second.boe_id,
                classification_status=ClassificationStatus.UNCERTAIN,
            ),
            source_hash="hash-b",
            extracted_at="2026-01-02T00:00:00Z",
        ),
    ])
    fixed_now = datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc)

    class FixedDateTime:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            return fixed_now

    monkeypatch.setattr(review_module, "datetime", FixedDateTime)

    selected = select_best_valid_extractions(
        attempts=attempts,
        source_df=source_df,
    )
    queue = build_review_queue(attempts=attempts, source_df=source_df)
    reordered_selected = select_best_valid_extractions(
        attempts=attempts.iloc[::-1].reset_index(drop=True),
        source_df=source_df.iloc[::-1].reset_index(drop=True),
    )
    reordered_queue = build_review_queue(
        attempts=attempts.iloc[::-1].reset_index(drop=True),
        source_df=source_df.iloc[::-1].reset_index(drop=True),
    )

    pd.testing.assert_frame_equal(selected, reordered_selected)
    pd.testing.assert_frame_equal(queue, reordered_queue)


def test_review_public_workflow_signatures_are_stable() -> None:
    assert tuple(signature(build_review_queue).parameters) == (
        "attempts",
        "source_df",
        "manual_reviews",
    )
    assert tuple(signature(select_best_valid_extractions).parameters) == (
        "attempts",
        "source_df",
        "manual_reviews",
    )
    assert tuple(signature(build_pending_candidates).parameters) == (
        "source_df",
        "attempts",
        "manual_reviews",
    )


def test_selection_lineage_values_match_validated_snapshots() -> None:
    assert DOCUMENT_VALIDATION_VERSION == "25"
    assert EXTRACTION_CONFIG_ID == "db2bc8c3564ce062"
    assert CONTRACT_SCHEMA_SHA256 == (
        "455028c7de0ada067264cd695b4e7dab9de377b31105e141321313d61c3ff283"
    )
    assert INSTRUCTIONS_SHA256 == (
        "4d9b67eba25460e912d7bee361def17272b0d9335738e6306b5a7c45de24561d"
    )
