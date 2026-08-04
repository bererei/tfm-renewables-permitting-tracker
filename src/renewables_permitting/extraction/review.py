from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

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
from renewables_permitting.extraction.documents import build_source_document
from renewables_permitting.extraction.models import BOEProjectExtraction
from renewables_permitting.extraction.paths import (
    BOE_AI_EXTRACTION_ATTEMPTS_PATH,
    BOE_AI_MANUAL_REVIEW_DIR,
    BOE_AI_MANUAL_REVIEWS_PATH,
    BOE_AI_QUALITY_METRICS_PATH,
)
from renewables_permitting.extraction.persistence import save_parquet_atomic
from renewables_permitting.extraction.validation import (
    validate_extraction_against_document,
)


AI_EXTRACTION_LOG_COLUMNS = [
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


def empty_ai_extraction_attempts_log() -> pd.DataFrame:
    return pd.DataFrame(columns=AI_EXTRACTION_LOG_COLUMNS)


def normalise_ai_extraction_attempts_log(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Añade el contrato vigente sin eliminar columnas históricas."""

    dataframe = dataframe.copy()
    for column in AI_EXTRACTION_LOG_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = pd.NA
    extra_columns = [
        column
        for column in dataframe.columns
        if column not in AI_EXTRACTION_LOG_COLUMNS
    ]
    return dataframe[AI_EXTRACTION_LOG_COLUMNS + extra_columns]


def combine_ai_extraction_attempt_frames(
    existing: pd.DataFrame,
    new_attempts: pd.DataFrame,
) -> pd.DataFrame:
    """Combina lotes de intentos sin depender de ``pd.concat``.

    Los registros correctos tienen varias columnas completamente nulas
    (por ejemplo ``error_type`` y ``validation_issues_json``). Pandas 2.x
    emite un ``FutureWarning`` al concatenar repetidamente esos bloques y
    anuncia un cambio futuro en la inferencia de tipos. Reconstruir la tabla
    desde registros evita esa inferencia ambigua y preserva todas las
    columnas históricas.
    """

    existing = normalise_ai_extraction_attempts_log(existing)
    new_attempts = normalise_ai_extraction_attempts_log(new_attempts)

    if existing.empty:
        return new_attempts.copy()
    if new_attempts.empty:
        return existing.copy()

    column_order = list(
        dict.fromkeys([*existing.columns.tolist(), *new_attempts.columns.tolist()])
    )
    records = [
        *existing.to_dict(orient="records"),
        *new_attempts.to_dict(orient="records"),
    ]
    combined = pd.DataFrame.from_records(records, columns=column_order)
    return normalise_ai_extraction_attempts_log(combined)


def current_successful_ai_extractions(
    attempts: pd.DataFrame,
    source_df: pd.DataFrame,
) -> pd.DataFrame:
    attempts = normalise_ai_extraction_attempts_log(attempts)
    successful = attempts.loc[
        attempts["extraction_status"].eq("ok").fillna(False)
        & attempts["document_validation_status"].eq("passed").fillna(False)
        & attempts["document_validation_version"]
        .eq(DOCUMENT_VALIDATION_VERSION)
        .fillna(False)
        & attempts["extraction_config_id"].eq(EXTRACTION_CONFIG_ID).fillna(False)
    ].copy()
    sources = source_df[
        ["identificador", "source_document_sha256"]
    ].rename(columns={"identificador": "identificador_boe"})
    successful = successful.merge(
        sources,
        on=["identificador_boe", "source_document_sha256"],
        how="inner",
        validate="many_to_one",
    )
    if successful.empty:
        return normalise_ai_extraction_attempts_log(successful)
    current = (
        successful.sort_values(
            ["extracted_at", "attempt_id"],
            na_position="first",
            kind="stable",
        )
        .drop_duplicates("identificador_boe", keep="last")
        .reset_index(drop=True)
    )
    for row in current.itertuples(index=False):
        BOEProjectExtraction.model_validate_json(str(row.extraction_json))
    return normalise_ai_extraction_attempts_log(current)


def build_pending_candidates(
    source_df: pd.DataFrame,
    attempts: pd.DataFrame,
    manual_reviews: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if manual_reviews is None:
        current = current_successful_ai_extractions(attempts, source_df)
    else:
        current = select_best_valid_extractions(
            attempts=attempts,
            source_df=source_df,
            manual_reviews=manual_reviews,
        )
    processed = set(current["identificador_boe"].astype(str))
    pending = source_df.loc[
        ~source_df["identificador"].astype(str).isin(processed)
    ].copy()
    return current, pending


def _count_extracted_nodes(extraction: BOEProjectExtraction) -> dict[str, int]:
    events = extraction.publication_events
    return {
        "n_publication_events": len(events),
        "n_generation_assets": sum(len(event.generation_assets) for event in events),
        "n_associated_components": sum(len(event.associated_components) for event in events),
        "n_administrative_actions": sum(len(event.administrative_actions) for event in events),
        "n_participants": sum(len(event.participants) for event in events),
        "n_administrative_locations": sum(len(event.administrative_locations) for event in events),
        "n_generation_relations": sum(len(event.generation_relations) for event in events),
        "n_technical_mentions": sum(
            sum(len(asset.technical_mentions) for asset in event.generation_assets)
            + sum(
                len(component.technical_mentions)
                for component in event.associated_components
            )
            for event in events
        ),
    }


REVIEW_QUEUE_COLUMNS = [
    "review_queue_id",
    "identificador_boe",
    "fecha_publicacion",
    "titulo",
    "source_document_sha256",
    "source_attempt_id",
    "extraction_config_id",
    "document_validation_version",
    "error_type",
    "error_message",
    "processing_stage",
    "validation_issues_json",
    "proposed_extraction_json",
    "queue_status",
    "queued_at",
]

MANUAL_REVIEW_COLUMNS = [
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

QUALITY_METRIC_COLUMNS = [
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


def _normalise_table(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    dataframe = dataframe.copy()
    for column in columns:
        if column not in dataframe.columns:
            dataframe[column] = pd.NA
    extra = [column for column in dataframe.columns if column not in columns]
    return dataframe[columns + extra]


def empty_review_queue() -> pd.DataFrame:
    return pd.DataFrame(columns=REVIEW_QUEUE_COLUMNS)


def empty_manual_reviews() -> pd.DataFrame:
    return pd.DataFrame(columns=MANUAL_REVIEW_COLUMNS)


def normalise_manual_reviews(dataframe: pd.DataFrame) -> pd.DataFrame:
    return _normalise_table(dataframe, MANUAL_REVIEW_COLUMNS)


def _latest_attempts_for_current_sources(
    attempts: pd.DataFrame,
    source_df: pd.DataFrame,
) -> pd.DataFrame:
    attempts = normalise_ai_extraction_attempts_log(attempts)
    if attempts.empty or source_df.empty:
        return attempts.iloc[0:0].copy()

    sources = source_df[
        ["identificador", "source_document_sha256"]
    ].rename(columns={"identificador": "identificador_boe"})
    current = attempts.loc[
        attempts["extraction_config_id"].eq(EXTRACTION_CONFIG_ID).fillna(False)
        & attempts["document_validation_version"]
        .eq(DOCUMENT_VALIDATION_VERSION)
        .fillna(False)
    ].merge(
        sources,
        on=["identificador_boe", "source_document_sha256"],
        how="inner",
        validate="many_to_one",
    )
    if current.empty:
        return normalise_ai_extraction_attempts_log(current)

    current["extracted_at"] = pd.to_datetime(
        current["extracted_at"],
        errors="coerce",
        utc=True,
    )
    return (
        current.sort_values(
            ["extracted_at", "attempt_id"],
            na_position="first",
            kind="stable",
        )
        .drop_duplicates("identificador_boe", keep="last")
        .reset_index(drop=True)
    )


def _latest_manual_reviews_for_current_sources(
    manual_reviews: pd.DataFrame,
    source_df: pd.DataFrame,
) -> pd.DataFrame:
    manual_reviews = normalise_manual_reviews(manual_reviews)
    if manual_reviews.empty or source_df.empty:
        return manual_reviews.iloc[0:0].copy()

    sources = source_df[
        ["identificador", "source_document_sha256"]
    ].rename(columns={"identificador": "identificador_boe"})
    current = manual_reviews.merge(
        sources,
        on=["identificador_boe", "source_document_sha256"],
        how="inner",
        validate="many_to_one",
    )
    if current.empty:
        return normalise_manual_reviews(current)

    current["reviewed_at"] = pd.to_datetime(
        current["reviewed_at"],
        errors="coerce",
        utc=True,
    )
    return (
        current.sort_values(
            ["reviewed_at", "manual_review_id"],
            na_position="first",
            kind="stable",
        )
        .drop_duplicates("identificador_boe", keep="last")
        .reset_index(drop=True)
    )


def build_review_queue(
    *,
    attempts: pd.DataFrame,
    source_df: pd.DataFrame,
    manual_reviews: pd.DataFrame | None = None,
) -> pd.DataFrame:
    latest_attempts = _latest_attempts_for_current_sources(attempts, source_df)
    if latest_attempts.empty:
        return empty_review_queue()

    manual_reviews = (
        empty_manual_reviews()
        if manual_reviews is None
        else normalise_manual_reviews(manual_reviews)
    )
    latest_manual = _latest_manual_reviews_for_current_sources(
        manual_reviews,
        source_df,
    )
    resolved_ids = set(
        latest_manual.loc[
            latest_manual["review_status"].isin(
                ["manually_validated", "rejected"]
            ),
            "identificador_boe",
        ].astype(str)
    )

    needs_review = latest_attempts.loc[
        ~(
            latest_attempts["extraction_status"].eq("ok").fillna(False)
            & latest_attempts["document_validation_status"].eq("passed").fillna(False)
        )
        & ~latest_attempts["identificador_boe"].astype(str).isin(resolved_ids)
    ].copy()
    if needs_review.empty:
        return empty_review_queue()

    queued_at = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    for row in needs_review.itertuples(index=False):
        queue_key = (
            f"{row.identificador_boe}|{row.source_document_sha256}|"
            f"{row.attempt_id}"
        )
        records.append({
            "review_queue_id": sha256(queue_key.encode("utf-8")).hexdigest()[:24],
            "identificador_boe": row.identificador_boe,
            "fecha_publicacion": row.fecha_publicacion,
            "titulo": row.titulo,
            "source_document_sha256": row.source_document_sha256,
            "source_attempt_id": row.attempt_id,
            "extraction_config_id": row.extraction_config_id,
            "document_validation_version": row.document_validation_version,
            "error_type": row.error_type,
            "error_message": row.error_message,
            "processing_stage": row.processing_stage,
            "validation_issues_json": row.validation_issues_json,
            "proposed_extraction_json": row.extraction_json,
            "queue_status": "pending",
            "queued_at": queued_at,
        })
    return _normalise_table(pd.DataFrame(records), REVIEW_QUEUE_COLUMNS)


def _manual_review_as_extraction_record(
    review: pd.Series,
    source_row: pd.Series,
) -> dict[str, Any]:
    extraction = BOEProjectExtraction.model_validate_json(
        str(review["corrected_extraction_json"])
    )
    counts = _count_extracted_nodes(extraction)
    return {
        **{column: pd.NA for column in AI_EXTRACTION_LOG_COLUMNS},
        "attempt_id": str(review["manual_review_id"]),
        "identificador_boe": extraction.boe_id,
        "fecha_publicacion": pd.Timestamp(extraction.publication_date),
        "titulo": source_row["titulo"],
        "source_document_sha256": source_row["source_document_sha256"],
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": "manual",
        "model_name": "human_review",
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "classification_status": extraction.classification_status.value,
        "document_scope": (
            extraction.document_scope.value
            if extraction.document_scope
            else None
        ),
        "classification_reason": extraction.classification_reason,
        **counts,
        "extraction_json": extraction.model_dump_json(),
        "extracted_at": review["reviewed_at"],
        "extraction_status": "ok",
        "processing_stage": "manual_review",
        "document_validation_status": "passed",
        "document_validation_issue_count": 0,
        "deterministic_adjustment_count": 0,
        "selection_source": "manually_validated",
        "manual_review_id": review["manual_review_id"],
        "reviewer": review["reviewer"],
        "review_notes": review["review_notes"],
    }


def select_best_valid_extractions(
    *,
    attempts: pd.DataFrame,
    source_df: pd.DataFrame,
    manual_reviews: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Selecciona una única extracción vigente por BOE.

    Precedencia:
    1. última revisión manual válida para la fuente actual;
    2. última extracción automática validada;
    3. ninguna extracción si la última revisión manual la rechaza.
    """

    auto = current_successful_ai_extractions(attempts, source_df).copy()
    if not auto.empty:
        auto["selection_source"] = "auto_validated"

    manual_reviews = (
        empty_manual_reviews()
        if manual_reviews is None
        else normalise_manual_reviews(manual_reviews)
    )
    latest_manual = _latest_manual_reviews_for_current_sources(
        manual_reviews,
        source_df,
    )
    manual_decision_ids = set(
        latest_manual.loc[
            latest_manual["review_status"].isin(
                ["manually_validated", "rejected"]
            ),
            "identificador_boe",
        ].astype(str)
    )
    if not auto.empty and manual_decision_ids:
        auto = auto.loc[
            ~auto["identificador_boe"].astype(str).isin(manual_decision_ids)
        ].copy()

    source_rows = {
        str(row["identificador"]): row
        for _, row in source_df.iterrows()
    }
    manual_records: list[dict[str, Any]] = []
    for _, review in latest_manual.loc[
        latest_manual["review_status"].eq("manually_validated")
    ].iterrows():
        boe_id = str(review["identificador_boe"])
        manual_records.append(
            _manual_review_as_extraction_record(review, source_rows[boe_id])
        )

    manual = (
        normalise_ai_extraction_attempts_log(pd.DataFrame(manual_records))
        if manual_records
        else normalise_ai_extraction_attempts_log(pd.DataFrame())
    )

    frames = [frame for frame in (auto, manual) if not frame.empty]
    if not frames:
        return normalise_ai_extraction_attempts_log(pd.DataFrame())
    if len(frames) == 1:
        selected = frames[0].copy()
    else:
        selected = pd.concat(frames, ignore_index=True)

    selected = (
        selected.sort_values(
            ["identificador_boe", "extracted_at", "attempt_id"],
            kind="stable",
        )
        .drop_duplicates("identificador_boe", keep="last")
        .reset_index(drop=True)
    )
    for row in selected.itertuples(index=False):
        BOEProjectExtraction.model_validate_json(str(row.extraction_json))
    return normalise_ai_extraction_attempts_log(selected)


def load_ai_extraction_attempts(
    path: Path = BOE_AI_EXTRACTION_ATTEMPTS_PATH,
) -> pd.DataFrame:
    if not path.exists():
        return empty_ai_extraction_attempts_log()
    return normalise_ai_extraction_attempts_log(pd.read_parquet(path))


def append_ai_extraction_attempts(
    new_attempts: pd.DataFrame,
    path: Path = BOE_AI_EXTRACTION_ATTEMPTS_PATH,
) -> pd.DataFrame:
    existing = load_ai_extraction_attempts(path)
    combined = combine_ai_extraction_attempt_frames(existing, new_attempts)
    combined = combined.drop_duplicates(subset=["attempt_id"], keep="last")
    save_parquet_atomic(combined, path)
    return combined


def empty_quality_metrics() -> pd.DataFrame:
    return pd.DataFrame(columns=QUALITY_METRIC_COLUMNS)


def create_manual_review_file(
    review_queue: pd.DataFrame,
    boe_id: str,
    *,
    output_dir: Path = BOE_AI_MANUAL_REVIEW_DIR,
    overwrite: bool = False,
) -> Path:
    rows = review_queue.loc[
        review_queue["identificador_boe"].astype(str).eq(str(boe_id))
    ]
    if len(rows) != 1:
        raise ValueError(
            f"Se esperaba un único elemento pendiente para {boe_id!r}; "
            f"encontrados={len(rows)}."
        )

    row = rows.iloc[0]
    proposed_json = row.get("proposed_extraction_json")
    proposed_extraction = None
    if pd.notna(proposed_json) and str(proposed_json).strip():
        proposed_extraction = json.loads(str(proposed_json))

    payload = {
        "identificador_boe": str(row["identificador_boe"]),
        "source_document_sha256": str(row["source_document_sha256"]),
        "source_attempt_id": str(row["source_attempt_id"]),
        "review_status": "pending",
        "reviewer": None,
        "review_notes": None,
        "corrected_extraction": proposed_extraction,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{boe_id}.json"
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Ya existe {output_path}. Usa overwrite=True solo si quieres reemplazarlo."
        )
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def load_manual_review_files(
    source_df: pd.DataFrame,
    *,
    review_dir: Path = BOE_AI_MANUAL_REVIEW_DIR,
    output_path: Path | None = BOE_AI_MANUAL_REVIEWS_PATH,
) -> pd.DataFrame:
    if not review_dir.exists():
        reviews = empty_manual_reviews()
        if output_path is not None:
            save_parquet_atomic(reviews, output_path)
        return reviews

    source_rows = {
        str(row["identificador"]): row
        for _, row in source_df.iterrows()
    }
    records: list[dict[str, Any]] = []

    for review_path in sorted(review_dir.glob("*.json")):
        payload = json.loads(review_path.read_text(encoding="utf-8"))
        boe_id = str(payload.get("identificador_boe", "")).strip()
        if boe_id not in source_rows:
            raise ValueError(
                f"{review_path}: identificador_boe no existe en el corpus actual."
            )

        document = build_source_document(source_rows[boe_id])
        if payload.get("source_document_sha256") != document.source_document_sha256:
            raise ValueError(
                f"{review_path}: la fuente BOE cambió; la revisión debe repetirse."
            )

        status = str(payload.get("review_status", "")).strip()
        if status not in {"pending", "manually_validated", "rejected"}:
            raise ValueError(
                f"{review_path}: review_status debe ser pending, "
                "manually_validated o rejected."
            )

        corrected_json: str | None = None
        if status == "manually_validated":
            reviewer = str(payload.get("reviewer") or "").strip()
            if not reviewer:
                raise ValueError(
                    f"{review_path}: reviewer es obligatorio al validar manualmente."
                )
            corrected_payload = payload.get("corrected_extraction")
            if not isinstance(corrected_payload, dict):
                raise ValueError(
                    f"{review_path}: corrected_extraction debe contener un objeto JSON."
                )
            extraction = BOEProjectExtraction.model_validate(corrected_payload)
            extraction, _ = canonicalize_project_extraction(
                extraction,
                source_text=f"{document.title}\n{document.text}",
                document_title=document.title,
            )
            validate_extraction_against_document(
                document=document,
                extraction=extraction,
            )
            corrected_json = extraction.model_dump_json()

        reviewed_at_raw = payload.get("reviewed_at")
        reviewed_at = (
            pd.to_datetime(reviewed_at_raw, utc=True)
            if reviewed_at_raw
            else pd.Timestamp(review_path.stat().st_mtime, unit="s", tz="UTC")
        )
        review_key = (
            f"{boe_id}|{document.source_document_sha256}|"
            f"{payload.get('source_attempt_id')}|{status}|{reviewed_at.isoformat()}"
        )
        records.append({
            "manual_review_id": sha256(review_key.encode("utf-8")).hexdigest()[:24],
            "identificador_boe": boe_id,
            "source_document_sha256": document.source_document_sha256,
            "source_attempt_id": payload.get("source_attempt_id"),
            "review_status": status,
            "corrected_extraction_json": corrected_json,
            "reviewer": payload.get("reviewer"),
            "review_notes": payload.get("review_notes"),
            "reviewed_at": reviewed_at,
            "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
            "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        })

    reviews = normalise_manual_reviews(pd.DataFrame(records))
    if output_path is not None:
        save_parquet_atomic(reviews, output_path)
    return reviews


def build_quality_metric(
    *,
    attempts: pd.DataFrame,
    source_df: pd.DataFrame,
    manual_reviews: pd.DataFrame | None,
    run_scope: str,
    minimum_auto_validation_rate: float = 0.95,
) -> pd.DataFrame:
    if not 0 <= minimum_auto_validation_rate <= 1:
        raise ValueError("minimum_auto_validation_rate debe estar entre 0 y 1.")

    latest_attempts = _latest_attempts_for_current_sources(attempts, source_df)
    auto_ids = set(
        latest_attempts.loc[
            latest_attempts["extraction_status"].eq("ok").fillna(False)
            & latest_attempts["document_validation_status"].eq("passed").fillna(False),
            "identificador_boe",
        ].astype(str)
    )

    manual_reviews = (
        empty_manual_reviews()
        if manual_reviews is None
        else normalise_manual_reviews(manual_reviews)
    )
    latest_manual = _latest_manual_reviews_for_current_sources(
        manual_reviews,
        source_df,
    )
    manual_valid_ids = set(
        latest_manual.loc[
            latest_manual["review_status"].eq("manually_validated"),
            "identificador_boe",
        ].astype(str)
    )
    rejected_ids = set(
        latest_manual.loc[
            latest_manual["review_status"].eq("rejected"),
            "identificador_boe",
        ].astype(str)
    )
    manual_decision_ids = manual_valid_ids | rejected_ids
    effective_valid_ids = (auto_ids - manual_decision_ids) | manual_valid_ids

    evaluated_ids = set(latest_attempts["identificador_boe"].astype(str))
    effective_evaluated_ids = effective_valid_ids & evaluated_ids
    rejected_evaluated_ids = rejected_ids & evaluated_ids

    n_source = int(len(source_df))
    n_evaluated = len(evaluated_ids)
    n_auto = len(auto_ids & evaluated_ids)
    n_effective = len(effective_evaluated_ids)
    n_review_required = max(
        0,
        n_evaluated - n_effective - len(rejected_evaluated_ids),
    )
    auto_rate = n_auto / n_evaluated if n_evaluated else 1.0
    effective_rate = n_effective / n_evaluated if n_evaluated else 1.0
    quality_alert = auto_rate < minimum_auto_validation_rate

    record = {
        "quality_run_id": uuid4().hex,
        "measured_at": datetime.now(timezone.utc),
        "run_scope": run_scope,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "n_source_documents": n_source,
        "n_latest_attempts": n_evaluated,
        "n_auto_validated": n_auto,
        "n_review_required": n_review_required,
        "n_manually_validated": len(manual_valid_ids & evaluated_ids),
        "n_rejected": len(rejected_evaluated_ids),
        "automatic_validation_rate": auto_rate,
        "effective_validation_rate": effective_rate,
        "minimum_auto_validation_rate": minimum_auto_validation_rate,
        "n_scope_evaluated": pd.NA,
        "n_scope_mismatches": pd.NA,
        "scope_accuracy": pd.NA,
        "minimum_scope_accuracy": pd.NA,
        "quality_status": "degraded" if quality_alert else "healthy",
        "quality_alert": quality_alert,
    }
    return _normalise_table(pd.DataFrame([record]), QUALITY_METRIC_COLUMNS)


def combine_quality_metrics(
    existing: pd.DataFrame,
    new_metric: pd.DataFrame,
) -> pd.DataFrame:
    """Combina métricas sin concatenar columnas vacías o totalmente nulas.

    `DataFrame.from_records` evita el `FutureWarning` de pandas asociado a
    `pd.concat` con columnas all-NA y conserva una fila completa por ejecución.
    """

    existing = _normalise_table(existing, QUALITY_METRIC_COLUMNS)
    new_metric = _normalise_table(new_metric, QUALITY_METRIC_COLUMNS)

    if existing.empty:
        combined = new_metric.copy()
    elif new_metric.empty:
        combined = existing.copy()
    else:
        records = [
            *existing.to_dict(orient="records"),
            *new_metric.to_dict(orient="records"),
        ]
        combined = _normalise_table(
            pd.DataFrame.from_records(records),
            QUALITY_METRIC_COLUMNS,
        )

    return combined.drop_duplicates(
        subset=["quality_run_id"],
        keep="last",
    ).reset_index(drop=True)


def append_quality_metric(
    new_metric: pd.DataFrame,
    path: Path = BOE_AI_QUALITY_METRICS_PATH,
) -> pd.DataFrame:
    if path.exists():
        existing = pd.read_parquet(path)
    else:
        existing = empty_quality_metrics()

    combined = combine_quality_metrics(existing, new_metric)
    save_parquet_atomic(combined, path)
    return combined
