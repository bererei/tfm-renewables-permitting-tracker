import ast
import json
import os
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

import renewables_permitting.extraction.review as review_module
from renewables_permitting.extraction.documents import (
    _source_document_hash,
    build_source_document,
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
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    MANUAL_REVIEW_COLUMNS,
    MODEL_PROVIDER,
    QUALITY_METRIC_COLUMNS,
    REVIEW_QUEUE_COLUMNS,
    append_ai_extraction_attempts,
    append_quality_metric,
    build_quality_metric,
    combine_quality_metrics,
    create_manual_review_file,
    empty_ai_extraction_attempts_log,
    empty_manual_reviews,
    empty_quality_metrics,
    load_ai_extraction_attempts,
    load_manual_review_files,
    normalise_ai_extraction_attempts_log,
)
from renewables_permitting.extraction.validation import (
    DocumentExtractionValidationError,
)


EXPECTED_QUALITY_METRIC_COLUMNS = [
    "quality_run_id",
    "measured_at",
    "run_scope",
    "extraction_config_id",
    "document_validation_version",
    "model_provider",
    "model_name",
    "n_source_documents",
    "n_latest_attempts",
    "n_auto_validated",
    "n_review_required",
    "n_manually_validated",
    "n_rejected",
    "automatic_validation_rate",
    "effective_validation_rate",
    "minimum_auto_validation_rate",
    "n_scope_evaluated",
    "n_scope_mismatches",
    "scope_accuracy",
    "minimum_scope_accuracy",
    "quality_status",
    "quality_alert",
]


def _source_and_extraction(
    *,
    boe_id: str = "BOE-A-2026-10001",
    name: str = "Aurora",
) -> tuple[pd.DataFrame, BOEProjectExtraction]:
    publication_date = date(2026, 1, 2)
    title = (
        "Resolución por la que se otorga autorización administrativa previa "
        f"a la planta fotovoltaica {name}."
    )
    source_hash = _source_document_hash(
        boe_id=boe_id,
        publication_date=publication_date,
        title=title,
        text=title,
    )
    source_df = pd.DataFrame([{
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp(publication_date),
        "titulo": title,
        "xml_status": "ok",
        "texto_limpio": title,
        "source_document_sha256": source_hash,
        "historical_source_column": "preserved",
    }])
    extraction = BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de proyecto.",
        publication_events=[PublicationEvent(
            generation_assets=[GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=[name],
                generation_type=GenerationType.PHOTOVOLTAIC,
                technical_mentions=[],
                evidence=title,
            )],
            administrative_actions=[AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                is_modification=False,
                targets=["event"],
                evidence=title,
            )],
            event_summary=f"Autorización de {name}.",
        )],
        extraction_notes=None,
        boe_id=boe_id,
        publication_date=publication_date,
    )
    return source_df, extraction


def _attempt_record(
    *,
    attempt_id: str,
    boe_id: str,
    source_hash: str,
    status: str,
    validation_status: str | None,
    extracted_at: str = "2026-01-01T00:00:00Z",
    classification_status: str = "classified",
) -> dict:
    return {
        "attempt_id": attempt_id,
        "identificador_boe": boe_id,
        "fecha_publicacion": pd.Timestamp("2026-01-02"),
        "titulo": f"Título {boe_id}",
        "source_document_sha256": source_hash,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "classification_status": classification_status,
        "extracted_at": pd.Timestamp(extracted_at),
        "extraction_status": status,
        "document_validation_status": validation_status,
    }


def _manual_record(
    *,
    manual_review_id: str,
    boe_id: str,
    source_hash: str,
    review_status: str,
    reviewed_at: str,
) -> dict:
    return {
        "manual_review_id": manual_review_id,
        "identificador_boe": boe_id,
        "source_document_sha256": source_hash,
        "source_attempt_id": f"attempt-{boe_id}",
        "review_status": review_status,
        "corrected_extraction_json": None,
        "reviewer": "reviewer",
        "review_notes": "review",
        "reviewed_at": pd.Timestamp(reviewed_at),
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }


def _editable_review_payload(
    source_df: pd.DataFrame,
    extraction: BOEProjectExtraction,
    *,
    status: str = "manually_validated",
    reviewer: str | None = "reviewer",
    reviewed_at: str | None = "2026-02-03T04:05:06Z",
) -> dict:
    payload = {
        "identificador_boe": extraction.boe_id,
        "source_document_sha256": source_df.iloc[0][
            "source_document_sha256"
        ],
        "source_attempt_id": "automatic-attempt",
        "review_status": status,
        "reviewer": reviewer,
        "review_notes": "Corrección manual.",
        "corrected_extraction": extraction.model_dump(mode="json"),
    }
    if reviewed_at is not None:
        payload["reviewed_at"] = reviewed_at
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_quality_metric_columns_and_empty_contract_are_exact() -> None:
    result = empty_quality_metrics()

    assert QUALITY_METRIC_COLUMNS == EXPECTED_QUALITY_METRIC_COLUMNS
    assert len(QUALITY_METRIC_COLUMNS) == 22
    assert result.empty
    assert result.columns.tolist() == EXPECTED_QUALITY_METRIC_COLUMNS


def test_load_attempts_missing_file_returns_canonical_empty(
    tmp_path: Path,
) -> None:
    result = load_ai_extraction_attempts(tmp_path / "missing.parquet")

    assert result.empty
    assert result.columns.tolist() == AI_EXTRACTION_LOG_COLUMNS


def test_load_attempts_existing_file_normalises_and_preserves_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.parquet"
    pd.DataFrame([{
        "attempt_id": "attempt-1",
        "extracted_at": pd.Timestamp("2026-01-01T00:00:00Z"),
        "historical_column": "historical",
    }]).to_parquet(path, index=False)

    result = load_ai_extraction_attempts(path)

    assert result.columns.tolist() == [
        *AI_EXTRACTION_LOG_COLUMNS,
        "historical_column",
    ]
    assert result["attempt_id"].tolist() == ["attempt-1"]
    assert result["historical_column"].tolist() == ["historical"]
    assert str(result["extracted_at"].dtype).startswith("datetime64")


def test_append_attempts_creates_combines_deduplicates_and_is_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "nested" / "attempts.parquet"
    existing = pd.DataFrame([{
        "attempt_id": "old",
        "extraction_status": "error",
        "old_historical_column": "old",
    }])
    real_save_parquet_atomic(existing, path)
    new_attempts = pd.DataFrame([
        {
            "attempt_id": "new",
            "extraction_status": "ok",
            "new_historical_column": "new",
        },
        {
            "attempt_id": "old",
            "extraction_status": "ok",
            "new_historical_column": "replacement",
        },
    ])
    original = new_attempts.copy(deep=True)
    calls: list[Path] = []

    def atomic_spy(dataframe: pd.DataFrame, output_path: Path) -> None:
        calls.append(output_path)
        real_save_parquet_atomic(dataframe, output_path)

    monkeypatch.setattr(review_module, "save_parquet_atomic", atomic_spy)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        combined = append_ai_extraction_attempts(new_attempts, path)

    assert calls == [path]
    assert combined["attempt_id"].tolist() == ["new", "old"]
    assert combined["extraction_status"].tolist() == ["ok", "ok"]
    assert combined.columns.tolist() == [
        *AI_EXTRACTION_LOG_COLUMNS,
        "old_historical_column",
        "new_historical_column",
    ]
    assert combined.index.tolist() == [1, 2]
    assert combined.iloc[1]["new_historical_column"] == "replacement"
    persisted = load_ai_extraction_attempts(path)
    assert persisted["attempt_id"].tolist() == ["new", "old"]
    assert list(tmp_path.rglob("*.tmp")) == []
    pd.testing.assert_frame_equal(new_attempts, original)
    assert not any(
        issubclass(item.category, FutureWarning)
        for item in caught
    )


def test_append_attempts_creates_new_file_without_mutating_input(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.parquet"
    new_attempts = pd.DataFrame([{
        "attempt_id": "first",
        "extraction_status": "ok",
    }], index=[8])
    original = new_attempts.copy(deep=True)

    result = append_ai_extraction_attempts(new_attempts, path)

    assert path.is_file()
    assert result["attempt_id"].tolist() == ["first"]
    assert result.index.tolist() == [8]
    pd.testing.assert_frame_equal(new_attempts, original)
    assert list(tmp_path.rglob("*.tmp")) == []


def test_create_manual_review_file_writes_exact_editable_json(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    queue = pd.DataFrame([{
        "identificador_boe": extraction.boe_id,
        "source_document_sha256": source_df.iloc[0][
            "source_document_sha256"
        ],
        "source_attempt_id": "automatic-attempt",
        "proposed_extraction_json": extraction.model_dump_json(),
    }])
    output_dir = tmp_path / "manual" / "reviews"

    output_path = create_manual_review_file(
        queue,
        extraction.boe_id,
        output_dir=output_dir,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path == output_dir / f"{extraction.boe_id}.json"
    assert output_dir.is_dir()
    assert payload == {
        "identificador_boe": extraction.boe_id,
        "source_document_sha256": source_df.iloc[0][
            "source_document_sha256"
        ],
        "source_attempt_id": "automatic-attempt",
        "review_status": "pending",
        "reviewer": None,
        "review_notes": None,
        "corrected_extraction": extraction.model_dump(mode="json"),
    }
    assert "publication_date" not in payload
    assert output_path.resolve().is_relative_to(tmp_path.resolve())


def test_create_manual_review_file_protects_and_overwrites_exact_path(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    queue = pd.DataFrame([{
        "identificador_boe": extraction.boe_id,
        "source_document_sha256": source_df.iloc[0][
            "source_document_sha256"
        ],
        "source_attempt_id": "first",
        "proposed_extraction_json": extraction.model_dump_json(),
    }])
    output_path = create_manual_review_file(
        queue,
        extraction.boe_id,
        output_dir=tmp_path,
    )
    original_text = output_path.read_text(encoding="utf-8")
    queue.loc[0, "source_attempt_id"] = "second"

    with pytest.raises(FileExistsError) as exc_info:
        create_manual_review_file(
            queue,
            extraction.boe_id,
            output_dir=tmp_path,
        )

    assert str(exc_info.value) == (
        f"Ya existe {output_path}. Usa overwrite=True solo si quieres reemplazarlo."
    )
    assert output_path.read_text(encoding="utf-8") == original_text

    replaced = create_manual_review_file(
        queue,
        extraction.boe_id,
        output_dir=tmp_path,
        overwrite=True,
    )

    assert replaced == output_path
    assert json.loads(replaced.read_text(encoding="utf-8"))[
        "source_attempt_id"
    ] == "second"


@pytest.mark.parametrize("proposed_json", [None, pd.NA, ""])
def test_create_manual_review_file_handles_absent_proposed_extraction(
    tmp_path: Path,
    proposed_json: object,
) -> None:
    queue = pd.DataFrame([{
        "identificador_boe": "BOE-A-2026-10001",
        "source_document_sha256": "hash",
        "source_attempt_id": "attempt",
        "proposed_extraction_json": proposed_json,
    }])

    output_path = create_manual_review_file(
        queue,
        "BOE-A-2026-10001",
        output_dir=tmp_path,
    )

    assert json.loads(output_path.read_text(encoding="utf-8"))[
        "corrected_extraction"
    ] is None


def test_create_manual_review_file_rejects_invalid_proposed_json(
    tmp_path: Path,
) -> None:
    queue = pd.DataFrame([{
        "identificador_boe": "BOE-A-2026-10001",
        "source_document_sha256": "hash",
        "source_attempt_id": "attempt",
        "proposed_extraction_json": "{not-json",
    }])

    with pytest.raises(json.JSONDecodeError):
        create_manual_review_file(
            queue,
            "BOE-A-2026-10001",
            output_dir=tmp_path,
        )


@pytest.mark.parametrize("matching_rows", [0, 2])
def test_create_manual_review_file_requires_exactly_one_queue_row(
    tmp_path: Path,
    matching_rows: int,
) -> None:
    queue = pd.DataFrame([
        {
            "identificador_boe": "BOE-A-2026-10001",
            "source_document_sha256": "hash",
            "source_attempt_id": f"attempt-{index}",
            "proposed_extraction_json": None,
        }
        for index in range(matching_rows)
    ], columns=[
        "identificador_boe",
        "source_document_sha256",
        "source_attempt_id",
        "proposed_extraction_json",
    ])

    with pytest.raises(ValueError) as exc_info:
        create_manual_review_file(
            queue,
            "BOE-A-2026-10001",
            output_dir=tmp_path,
        )

    assert str(exc_info.value) == (
        "Se esperaba un único elemento pendiente para "
        f"'BOE-A-2026-10001'; encontrados={matching_rows}."
    )


def test_load_manual_reviews_missing_and_empty_directories(
    tmp_path: Path,
) -> None:
    source_df, _ = _source_and_extraction()

    missing = load_manual_review_files(
        source_df,
        review_dir=tmp_path / "missing",
        output_path=None,
    )
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    empty = load_manual_review_files(
        source_df,
        review_dir=empty_dir,
        output_path=None,
    )

    assert missing.empty
    assert empty.empty
    assert missing.columns.tolist() == MANUAL_REVIEW_COLUMNS
    assert empty.columns.tolist() == MANUAL_REVIEW_COLUMNS


def test_load_valid_manual_review_canonicalises_validates_and_preserves_fields(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    source_snapshot = source_df.copy(deep=True)
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    payload = _editable_review_payload(source_df, extraction)
    review_path = review_dir / "review.json"
    _write_json(review_path, payload)

    reviews = load_manual_review_files(
        source_df,
        review_dir=review_dir,
        output_path=None,
    )

    assert len(reviews) == 1
    row = reviews.iloc[0]
    assert row["identificador_boe"] == extraction.boe_id
    assert row["source_document_sha256"] == payload[
        "source_document_sha256"
    ]
    assert row["source_attempt_id"] == "automatic-attempt"
    assert row["review_status"] == "manually_validated"
    assert row["reviewer"] == "reviewer"
    assert row["review_notes"] == "Corrección manual."
    assert row["reviewed_at"] == pd.Timestamp("2026-02-03T04:05:06Z")
    parsed = BOEProjectExtraction.model_validate_json(
        str(row["corrected_extraction_json"])
    )
    assert parsed.boe_id == extraction.boe_id
    assert row["contract_schema_sha256"] == CONTRACT_SCHEMA_SHA256
    assert row["document_validation_version"] == DOCUMENT_VALIDATION_VERSION
    pd.testing.assert_frame_equal(source_df, source_snapshot)


def test_load_manual_reviews_reads_files_in_sorted_order(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    payload_b = _editable_review_payload(
        source_df,
        extraction,
        status="rejected",
    )
    payload_b["review_notes"] = "b"
    payload_a = _editable_review_payload(
        source_df,
        extraction,
        status="pending",
    )
    payload_a["review_notes"] = "a"
    _write_json(review_dir / "b.json", payload_b)
    _write_json(review_dir / "a.json", payload_a)

    reviews = load_manual_review_files(
        source_df,
        review_dir=review_dir,
        output_path=None,
    )

    assert reviews["review_notes"].tolist() == ["a", "b"]
    assert reviews["review_status"].tolist() == ["pending", "rejected"]


def test_load_manual_review_uses_file_mtime_when_reviewed_at_is_absent(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    payload = _editable_review_payload(
        source_df,
        extraction,
        status="pending",
        reviewed_at=None,
    )
    review_path = review_dir / "review.json"
    _write_json(review_path, payload)
    timestamp = 1_700_000_000
    os.utime(review_path, (timestamp, timestamp))

    reviews = load_manual_review_files(
        source_df,
        review_dir=review_dir,
        output_path=None,
    )

    assert reviews.iloc[0]["reviewed_at"] == pd.Timestamp(
        timestamp,
        unit="s",
        tz="UTC",
    )


def test_load_manual_reviews_persists_consolidated_table_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_df, extraction = _source_and_extraction()
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    _write_json(
        review_dir / "review.json",
        _editable_review_payload(
            source_df,
            extraction,
            status="rejected",
        ),
    )
    output_path = tmp_path / "silver" / "manual_reviews.parquet"
    calls: list[Path] = []

    def atomic_spy(dataframe: pd.DataFrame, path: Path) -> None:
        calls.append(path)
        real_save_parquet_atomic(dataframe, path)

    monkeypatch.setattr(review_module, "save_parquet_atomic", atomic_spy)
    reviews = load_manual_review_files(
        source_df,
        review_dir=review_dir,
        output_path=output_path,
    )

    assert calls == [output_path]
    assert output_path.is_file()
    persisted = pd.read_parquet(output_path)
    assert persisted["review_status"].tolist() == ["rejected"]
    assert reviews["review_status"].tolist() == ["rejected"]
    assert list(tmp_path.rglob("*.tmp")) == []


def test_load_manual_reviews_missing_directory_can_persist_empty_table(
    tmp_path: Path,
) -> None:
    source_df, _ = _source_and_extraction()
    output_path = tmp_path / "manual_reviews.parquet"

    reviews = load_manual_review_files(
        source_df,
        review_dir=tmp_path / "missing",
        output_path=output_path,
    )

    assert reviews.empty
    assert output_path.is_file()
    assert pd.read_parquet(output_path).empty
    assert list(tmp_path.rglob("*.tmp")) == []


def test_load_manual_review_rejects_syntactically_invalid_json(
    tmp_path: Path,
) -> None:
    source_df, _ = _source_and_extraction()
    review_dir = tmp_path / "reviews"
    review_dir.mkdir()
    (review_dir / "invalid.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_manual_review_files(
            source_df,
            review_dir=review_dir,
            output_path=None,
        )


def test_load_manual_review_rejects_unknown_boe_id(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(source_df, extraction)
    payload["identificador_boe"] = "BOE-A-2026-99999"
    review_path = tmp_path / "unknown.json"
    _write_json(review_path, payload)

    with pytest.raises(ValueError) as exc_info:
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )

    assert str(exc_info.value) == (
        f"{review_path}: identificador_boe no existe en el corpus actual."
    )


def test_load_manual_review_rejects_stale_source_hash(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(source_df, extraction)
    payload["source_document_sha256"] = "obsolete"
    review_path = tmp_path / "stale.json"
    _write_json(review_path, payload)

    with pytest.raises(ValueError) as exc_info:
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )

    assert str(exc_info.value) == (
        f"{review_path}: la fuente BOE cambió; la revisión debe repetirse."
    )


def test_load_manual_review_rejects_invalid_status(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(
        source_df,
        extraction,
        status="invalid",
    )
    review_path = tmp_path / "status.json"
    _write_json(review_path, payload)

    with pytest.raises(ValueError) as exc_info:
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )

    assert str(exc_info.value) == (
        f"{review_path}: review_status debe ser pending, "
        "manually_validated o rejected."
    )


def test_load_manual_review_requires_reviewer_for_manual_validation(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(
        source_df,
        extraction,
        reviewer=None,
    )
    review_path = tmp_path / "reviewer.json"
    _write_json(review_path, payload)

    with pytest.raises(ValueError) as exc_info:
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )

    assert str(exc_info.value) == (
        f"{review_path}: reviewer es obligatorio al validar manualmente."
    )


@pytest.mark.parametrize(
    "corrected_extraction",
    [None, "invalid-json", ["not", "an", "object"]],
)
def test_load_manual_review_requires_corrected_extraction_object(
    tmp_path: Path,
    corrected_extraction: object,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(source_df, extraction)
    payload["corrected_extraction"] = corrected_extraction
    review_path = tmp_path / "extraction.json"
    _write_json(review_path, payload)

    with pytest.raises(ValueError) as exc_info:
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )

    assert str(exc_info.value) == (
        f"{review_path}: corrected_extraction debe contener un objeto JSON."
    )


def test_load_manual_review_rejects_extraction_outside_pydantic_contract(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(source_df, extraction)
    payload["corrected_extraction"] = {"boe_id": extraction.boe_id}
    _write_json(tmp_path / "invalid-contract.json", payload)

    with pytest.raises(ValidationError):
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )


def test_load_manual_review_rejects_documentally_invalid_extraction(
    tmp_path: Path,
) -> None:
    source_df, extraction = _source_and_extraction()
    payload = _editable_review_payload(source_df, extraction)
    payload["corrected_extraction"]["boe_id"] = "BOE-A-2026-99999"
    _write_json(tmp_path / "invalid-document.json", payload)

    with pytest.raises(DocumentExtractionValidationError):
        load_manual_review_files(
            source_df,
            review_dir=tmp_path,
            output_path=None,
        )


def test_build_quality_metric_calculates_v25_1_mixed_workflow_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_rows = [
        (f"BOE-A-2026-1000{index}", f"hash-{index}")
        for index in range(1, 6)
    ]
    source_df = pd.DataFrame([
        {
            "identificador": boe_id,
            "source_document_sha256": source_hash,
        }
        for boe_id, source_hash in source_rows
    ])
    attempts = pd.DataFrame([
        _attempt_record(
            attempt_id="auto-valid",
            boe_id=source_rows[0][0],
            source_hash=source_rows[0][1],
            status="ok",
            validation_status="passed",
        ),
        _attempt_record(
            attempt_id="review-required",
            boe_id=source_rows[1][0],
            source_hash=source_rows[1][1],
            status="error",
            validation_status="failed",
        ),
        _attempt_record(
            attempt_id="manual-valid",
            boe_id=source_rows[2][0],
            source_hash=source_rows[2][1],
            status="error",
            validation_status="failed",
        ),
        _attempt_record(
            attempt_id="uncertain-success",
            boe_id=source_rows[3][0],
            source_hash=source_rows[3][1],
            status="ok",
            validation_status="passed",
            classification_status="uncertain",
        ),
        _attempt_record(
            attempt_id="manual-rejected",
            boe_id=source_rows[4][0],
            source_hash=source_rows[4][1],
            status="error",
            validation_status="failed",
        ),
    ])
    manual_reviews = pd.DataFrame([
        _manual_record(
            manual_review_id="manual-valid",
            boe_id=source_rows[2][0],
            source_hash=source_rows[2][1],
            review_status="manually_validated",
            reviewed_at="2026-02-01T00:00:00Z",
        ),
        _manual_record(
            manual_review_id="manual-rejected",
            boe_id=source_rows[4][0],
            source_hash=source_rows[4][1],
            review_status="rejected",
            reviewed_at="2026-02-01T00:00:00Z",
        ),
    ])
    fixed_time = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)

    class FixedDateTime:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            return fixed_time

    monkeypatch.setattr(review_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        review_module,
        "uuid4",
        lambda: SimpleNamespace(hex="fixed-quality-run"),
    )

    metric = build_quality_metric(
        attempts=attempts,
        source_df=source_df,
        manual_reviews=manual_reviews,
        run_scope="pilot",
        minimum_auto_validation_rate=0.5,
    )

    assert metric.columns.tolist() == QUALITY_METRIC_COLUMNS
    row = metric.iloc[0]
    assert row["quality_run_id"] == "fixed-quality-run"
    assert row["measured_at"] == fixed_time
    assert row["run_scope"] == "pilot"
    assert row["extraction_config_id"] == EXTRACTION_CONFIG_ID
    assert row["document_validation_version"] == DOCUMENT_VALIDATION_VERSION
    assert row["model_provider"] == MODEL_PROVIDER
    assert row["model_name"] == AI_MODEL_NAME
    assert row["n_source_documents"] == 5
    assert row["n_latest_attempts"] == 5
    assert row["n_auto_validated"] == 2
    assert row["n_review_required"] == 1
    assert row["n_manually_validated"] == 1
    assert row["n_rejected"] == 1
    assert row["automatic_validation_rate"] == pytest.approx(0.4)
    assert row["effective_validation_rate"] == pytest.approx(0.6)
    assert row["minimum_auto_validation_rate"] == pytest.approx(0.5)
    assert pd.isna(row["n_scope_evaluated"])
    assert pd.isna(row["n_scope_mismatches"])
    assert pd.isna(row["scope_accuracy"])
    assert pd.isna(row["minimum_scope_accuracy"])
    assert row["quality_status"] == "degraded"
    assert bool(row["quality_alert"]) is True
    for absent_node_metric in (
        "n_publication_events",
        "n_generation_assets",
        "n_associated_components",
        "n_administrative_actions",
    ):
        assert absent_node_metric not in metric.columns


def test_build_quality_metric_empty_denominator_uses_unit_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_module,
        "uuid4",
        lambda: SimpleNamespace(hex="empty-quality-run"),
    )
    source_df = pd.DataFrame(
        columns=["identificador", "source_document_sha256"]
    )

    metric = build_quality_metric(
        attempts=empty_ai_extraction_attempts_log(),
        source_df=source_df,
        manual_reviews=None,
        run_scope="empty",
    )

    row = metric.iloc[0]
    assert row["n_source_documents"] == 0
    assert row["n_latest_attempts"] == 0
    assert row["n_auto_validated"] == 0
    assert row["n_review_required"] == 0
    assert row["n_manually_validated"] == 0
    assert row["n_rejected"] == 0
    assert row["automatic_validation_rate"] == 1.0
    assert row["effective_validation_rate"] == 1.0
    assert row["quality_status"] == "healthy"
    assert bool(row["quality_alert"]) is False


@pytest.mark.parametrize("minimum_rate", [-0.01, 1.01])
def test_build_quality_metric_rejects_invalid_minimum_rate(
    minimum_rate: float,
) -> None:
    source_df = pd.DataFrame(
        columns=["identificador", "source_document_sha256"]
    )

    with pytest.raises(ValueError) as exc_info:
        build_quality_metric(
            attempts=empty_ai_extraction_attempts_log(),
            source_df=source_df,
            manual_reviews=empty_manual_reviews(),
            run_scope="invalid",
            minimum_auto_validation_rate=minimum_rate,
        )

    assert str(exc_info.value) == (
        "minimum_auto_validation_rate debe estar entre 0 y 1."
    )


def test_quality_metric_combination_has_no_future_warning() -> None:
    existing = empty_quality_metrics()
    new_metric = review_module._normalise_table(
        pd.DataFrame([{
            "quality_run_id": "quality_test",
            "run_scope": "pilot",
            "n_source_documents": 1,
            "quality_alert": False,
        }]),
        QUALITY_METRIC_COLUMNS,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        combined = combine_quality_metrics(existing, new_metric)
    assert len(combined) == 1
    assert not any(
        issubclass(item.category, FutureWarning)
        for item in caught
    )


def test_combine_quality_metrics_preserves_history_order_and_inputs() -> None:
    existing = pd.DataFrame([{
        "quality_run_id": "old",
        "quality_status": "healthy",
        "historical_old": "old",
    }], index=[3])
    new_metric = pd.DataFrame([
        {
            "quality_run_id": "new",
            "quality_status": "degraded",
            "historical_new": "new",
        },
        {
            "quality_run_id": "old",
            "quality_status": "degraded",
            "historical_new": "replacement",
        },
    ], index=[7, 8])
    existing_snapshot = existing.copy(deep=True)
    new_snapshot = new_metric.copy(deep=True)

    combined = combine_quality_metrics(existing, new_metric)

    assert combined["quality_run_id"].tolist() == ["new", "old"]
    assert combined["quality_status"].tolist() == ["degraded", "degraded"]
    assert combined.columns.tolist() == [
        *QUALITY_METRIC_COLUMNS,
        "historical_old",
        "historical_new",
    ]
    assert combined.loc[1, "historical_new"] == "replacement"
    pd.testing.assert_frame_equal(existing, existing_snapshot)
    pd.testing.assert_frame_equal(new_metric, new_snapshot)


def test_combine_quality_metrics_empty_branches_return_copies() -> None:
    metric = pd.DataFrame([{
        "quality_run_id": "metric",
        "quality_status": "healthy",
    }])

    from_empty = combine_quality_metrics(empty_quality_metrics(), metric)
    with_empty = combine_quality_metrics(metric, empty_quality_metrics())

    assert from_empty["quality_run_id"].tolist() == ["metric"]
    assert with_empty["quality_run_id"].tolist() == ["metric"]
    assert from_empty is not metric
    assert with_empty is not metric


def test_append_quality_metric_creates_and_appends_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "quality" / "metrics.parquet"
    first = pd.DataFrame([{
        "quality_run_id": "first",
        "quality_status": "healthy",
        "historical_column": "first-history",
    }])
    second = pd.DataFrame([{
        "quality_run_id": "second",
        "quality_status": "degraded",
        "historical_column": "second-history",
    }])
    first_snapshot = first.copy(deep=True)
    second_snapshot = second.copy(deep=True)
    calls: list[Path] = []

    def atomic_spy(dataframe: pd.DataFrame, output_path: Path) -> None:
        calls.append(output_path)
        real_save_parquet_atomic(dataframe, output_path)

    monkeypatch.setattr(review_module, "save_parquet_atomic", atomic_spy)
    initial = append_quality_metric(first, path)
    combined = append_quality_metric(second, path)

    assert calls == [path, path]
    assert initial["quality_run_id"].tolist() == ["first"]
    assert combined["quality_run_id"].tolist() == ["first", "second"]
    assert combined["historical_column"].tolist() == [
        "first-history",
        "second-history",
    ]
    persisted = pd.read_parquet(path)
    assert persisted["quality_run_id"].tolist() == ["first", "second"]
    assert list(tmp_path.rglob("*.tmp")) == []
    pd.testing.assert_frame_equal(first, first_snapshot)
    pd.testing.assert_frame_equal(second, second_snapshot)


def _top_level_nodes(source: str) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            nodes[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node
    return nodes


def test_review_io_functions_and_quality_columns_match_notebook_ast() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text(encoding="utf-8")
    )
    notebook_nodes: dict[str, ast.AST] = {}
    for cell_index in (9, 15):
        notebook_nodes.update(
            _top_level_nodes("".join(notebook["cells"][cell_index]["source"]))
        )
    module_nodes = _top_level_nodes(
        (
            project_root
            / "src"
            / "renewables_permitting"
            / "extraction"
            / "review.py"
        ).read_text(encoding="utf-8")
    )
    expected_names = {
        "QUALITY_METRIC_COLUMNS",
        "load_ai_extraction_attempts",
        "append_ai_extraction_attempts",
        "create_manual_review_file",
        "load_manual_review_files",
        "empty_quality_metrics",
        "build_quality_metric",
        "combine_quality_metrics",
        "append_quality_metric",
    }

    assert expected_names <= notebook_nodes.keys()
    assert expected_names <= module_nodes.keys()
    for name in expected_names:
        assert ast.dump(module_nodes[name], include_attributes=False) == ast.dump(
            notebook_nodes[name],
            include_attributes=False,
        ), name


def test_existing_review_column_contracts_remain_unchanged() -> None:
    assert len(AI_EXTRACTION_LOG_COLUMNS) == 43
    assert len(REVIEW_QUEUE_COLUMNS) == 15
    assert len(MANUAL_REVIEW_COLUMNS) == 11
