from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from renewables_permitting.extraction.correction_subset import (
    corrections_subset_code_sha256,
    plan_administrative_action_corrections_subset,
)
from renewables_permitting.extraction.corrections import (
    ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
    LoadedAdministrativeActionCorrections,
    corrections_identity,
    historical_action_exclusion_correction_id,
    load_administrative_action_corrections,
    validate_administrative_action_corrections,
)
from renewables_permitting.extraction.documents import build_source_document
from renewables_permitting.extraction.historical_antecedents import (
    POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE,
    HistoricalAntecedentFinding,
    detect_possible_historical_antecedents,
    reconcile_historical_antecedent_findings,
)
from renewables_permitting.extraction.historical_antecedent_reviews import (
    HISTORICAL_ANTECEDENT_REVIEW_COLUMNS,
    LoadedHistoricalAntecedentReviews,
    historical_antecedent_review_id,
    historical_antecedent_reviews_identity,
    load_historical_antecedent_reviews,
    validate_historical_antecedent_reviews,
)
from renewables_permitting.extraction.models import BOEProjectExtraction
from renewables_permitting.extraction.paths import (
    BOE_AI_MANUAL_REVIEW_DIR,
    CONFIG_DIR,
)
from renewables_permitting.extraction.review import (
    MANUAL_REVIEW_COLUMNS,
    _load_manual_review_files_for_boe_ids,
    _validate_manual_reviews,
)
from renewables_permitting.pipeline import (
    LoadedExtractionSnapshot,
    PipelineError,
    _extraction_snapshot_identity,
    load_extraction_snapshot,
)


CORRECTIONS_PATH = (
    CONFIG_DIR / "corrections" / "administrative_action_corrections.csv"
)
CURRENT_REVIEWS_PATH = (
    CONFIG_DIR / "manual_reviews" / "historical_antecedent_reviews.csv"
)

_GENERIC_REVIEW_REASON_CODES = {
    "classification_uncertain",
    "extraction_error",
    "document_validation_failed",
}
_DECISIVE_MANUAL_STATUSES = {"manually_validated", "rejected"}
_EXIT_SUCCESS = 0
_EXIT_ERROR = 2


class AdminCLIError(ValueError):
    """A requested administrative operation is unsafe or unsupported."""


@dataclass(frozen=True)
class AdminContext:
    """One validated extraction snapshot plus current decision registries."""

    snapshot: LoadedExtractionSnapshot
    extraction_snapshot: Path
    expected_extraction_config_id: str
    corrections: LoadedAdministrativeActionCorrections
    current_reviews: LoadedHistoricalAntecedentReviews


@dataclass(frozen=True)
class ReviewCase:
    """One deterministic operator-facing review case."""

    boe_id: str
    index: int
    reason_code: str
    severity: str
    title: str
    publication_date: str
    review_queue_id: str
    source_document_sha256: str
    source_attempt_id: str | None
    proposed_extraction_json: str | None
    finding: HistoricalAntecedentFinding | None


@dataclass(frozen=True)
class CurrentDecisionCandidate:
    """A validated but not yet persisted CURRENT decision."""

    finding: HistoricalAntecedentFinding
    row: Mapping[str, Any]
    validated_registry: pd.DataFrame
    review_id: str
    target_path: Path
    original_file_sha256: str


@dataclass(frozen=True)
class AntecedentDecisionCandidate:
    """A validated but not yet persisted ANTECEDENT correction."""

    finding: HistoricalAntecedentFinding
    row: Mapping[str, Any]
    validated_registry: pd.DataFrame
    correction_id: str
    target_path: Path
    original_file_sha256: str


@dataclass(frozen=True)
class ManualDecisionCandidate:
    """A validated exact-proposal approval or complete rejection."""

    case: ReviewCase
    review_status: str
    manual_review_id: str
    payload: Mapping[str, Any]
    validated_reviews: pd.DataFrame
    review_dir: Path
    target_path: Path
    original_file_sha256: str | None
    scope_boe_ids: tuple[str, ...]


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC instant."""

    return datetime.now(timezone.utc)


def _reviewed_on(value: date | None = None) -> str:
    """Return the contract date, defaulting to the current UTC date."""

    return (value or _utc_now().date()).isoformat()


def _reviewed_at(value: datetime | None = None) -> datetime:
    """Normalize one review timestamp to timezone-aware UTC."""

    instant = value or _utc_now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise AdminCLIError("reviewed_at debe incluir zona horaria.")
    return instant.astimezone(timezone.utc)


def _required_human_text(value: str, *, field: str) -> str:
    """Validate one explicit human-entered text value."""

    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "<na>"}:
        raise AdminCLIError(f"{field} debe contener texto explícito.")
    return text


def _file_sha256(path: Path) -> str:
    """Hash one regular file without following a replacement candidate."""

    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _optional_regular_file_sha256(path: Path) -> str | None:
    """Return a file hash or None while rejecting unsafe path types."""

    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise AdminCLIError(f"La revisión debe ser un fichero regular: {path}")
    return _file_sha256(path)


def _snapshot_config_id(snapshot_dir: Path) -> str:
    """Read only the config selector needed by the validated snapshot loader."""

    manifest_path = Path(snapshot_dir) / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise PipelineError("Extraction snapshot manifest is missing.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PipelineError("Extraction snapshot manifest is invalid.") from error
    if not isinstance(manifest, dict):
        raise PipelineError("Extraction snapshot manifest is not an object.")
    config_id = manifest.get("extraction_config_id")
    if not isinstance(config_id, str) or not config_id.strip():
        raise PipelineError("Extraction snapshot has no extraction config ID.")
    return config_id


def load_admin_context(
    extraction_snapshot: Path,
    *,
    corrections_path: Path = CORRECTIONS_PATH,
    current_reviews_path: Path = CURRENT_REVIEWS_PATH,
) -> AdminContext:
    """Load the validated snapshot and current versioned decision registries."""

    snapshot_path = Path(extraction_snapshot).absolute()
    expected_config_id = _snapshot_config_id(snapshot_path)
    snapshot = load_extraction_snapshot(
        snapshot_path,
        expected_extraction_config_id=expected_config_id,
    )
    return AdminContext(
        snapshot=snapshot,
        extraction_snapshot=snapshot_path,
        expected_extraction_config_id=expected_config_id,
        corrections=load_administrative_action_corrections(corrections_path),
        current_reviews=load_historical_antecedent_reviews(
            current_reviews_path
        ),
    )


def _source_and_extraction(
    context: AdminContext,
    boe_id: str,
) -> tuple[Any, BOEProjectExtraction]:
    """Recover one exact source document and selected extraction by BOE."""

    source_rows = context.snapshot.documents.loc[
        context.snapshot.documents["identificador"].astype(str).eq(boe_id)
    ]
    extraction_rows = context.snapshot.current_extractions.loc[
        context.snapshot.current_extractions["identificador_boe"]
        .astype(str)
        .eq(boe_id)
    ]
    if len(source_rows) != 1 or len(extraction_rows) != 1:
        raise AdminCLIError(
            f"{boe_id}: se requiere un documento y una extracción vigentes "
            "exactamente."
        )
    document = build_source_document(source_rows.iloc[0])
    extraction = BOEProjectExtraction.model_validate_json(
        str(extraction_rows.iloc[0]["extraction_json"])
    )
    return document, extraction


def pending_historical_findings(
    context: AdminContext,
    boe_id: str,
) -> tuple[HistoricalAntecedentFinding, ...]:
    """Recompute and reconcile the currently pending findings for one BOE."""

    document, extraction = _source_and_extraction(context, boe_id)
    findings = detect_possible_historical_antecedents(
        document=document,
        extraction=extraction,
    )
    reconciliation = reconcile_historical_antecedent_findings(
        findings,
        context.corrections,
        context.current_reviews,
    )
    return reconciliation.pending


def build_review_cases(
    context: AdminContext,
    *,
    boe_id: str | None = None,
    reason_code: str | None = None,
) -> tuple[ReviewCase, ...]:
    """Expand a validated BOE queue into deterministic operator cases."""

    queue = context.snapshot.review_queue.sort_values(
        ["identificador_boe", "reason_code", "review_queue_id"],
        kind="stable",
    )
    cases: list[ReviewCase] = []
    for _, row in queue.iterrows():
        row_boe_id = str(row["identificador_boe"])
        row_reason = str(row["reason_code"])
        if boe_id is not None and row_boe_id != boe_id:
            continue
        if reason_code is not None and row_reason != reason_code:
            continue
        title = "" if pd.isna(row["titulo"]) else str(row["titulo"])
        publication_date = (
            ""
            if pd.isna(row["fecha_publicacion"])
            else pd.Timestamp(row["fecha_publicacion"]).date().isoformat()
        )
        source_attempt_id = (
            None
            if pd.isna(row["source_attempt_id"])
            else str(row["source_attempt_id"])
        )
        proposed_json = (
            None
            if pd.isna(row["proposed_extraction_json"])
            else str(row["proposed_extraction_json"])
        )
        common = {
            "boe_id": row_boe_id,
            "reason_code": row_reason,
            "severity": str(row["reason_severity"]),
            "title": title,
            "publication_date": publication_date,
            "review_queue_id": str(row["review_queue_id"]),
            "source_document_sha256": str(row["source_document_sha256"]),
            "source_attempt_id": source_attempt_id,
            "proposed_extraction_json": proposed_json,
        }
        if row_reason == POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE:
            for index, finding in enumerate(
                pending_historical_findings(context, row_boe_id),
                start=1,
            ):
                cases.append(ReviewCase(
                    **common,
                    index=index,
                    finding=finding,
                ))
            continue
        cases.append(ReviewCase(**common, index=1, finding=None))
    return tuple(cases)


def select_review_case(
    context: AdminContext,
    *,
    boe_id: str,
    index: int | None = None,
) -> ReviewCase:
    """Select one unambiguous case by BOE and optional display index."""

    matches = list(build_review_cases(context, boe_id=boe_id))
    if not matches:
        raise AdminCLIError(
            f"{boe_id}: no existe un caso pendiente en los registros vigentes."
        )
    if index is None:
        if len(matches) != 1:
            raise AdminCLIError(
                f"{boe_id}: hay {len(matches)} findings; indica --index."
            )
        return matches[0]
    if index < 1:
        raise AdminCLIError("--index debe ser un entero positivo.")
    selected = [item for item in matches if item.index == index]
    if len(selected) != 1:
        raise AdminCLIError(
            f"{boe_id}: --index {index} no identifica un finding pendiente."
        )
    return selected[0]


def _select_exact_finding_case(
    context: AdminContext,
    expected: HistoricalAntecedentFinding,
) -> ReviewCase:
    """Recover an unchanged exact finding after confirmation latency."""

    for case in build_review_cases(context, boe_id=expected.boe_id):
        if case.finding == expected:
            return case
    raise AdminCLIError(
        "El finding cambió, dejó de estar pendiente o ya fue resuelto; "
        "no se escribió ninguna decisión."
    )


def _select_exact_generic_case(
    context: AdminContext,
    expected: ReviewCase,
) -> ReviewCase:
    """Recover an unchanged exact generic case after confirmation latency."""

    for case in build_review_cases(context, boe_id=expected.boe_id):
        if case == expected:
            return case
    raise AdminCLIError(
        "El caso genérico cambió o dejó de estar pendiente; no se escribió "
        "ninguna decisión."
    )


def _append_contract_row(
    frame: pd.DataFrame,
    row: Mapping[str, Any],
    columns: Sequence[str],
) -> pd.DataFrame:
    """Append one row without pandas concat dtype inference."""

    return pd.DataFrame.from_records(
        [*frame.to_dict(orient="records"), dict(row)],
        columns=columns,
    )


def prepare_current_decision(
    context: AdminContext,
    case: ReviewCase,
    *,
    reason: str,
    reviewer: str,
    decision_source: str,
    reviewed_on: date | None = None,
) -> CurrentDecisionCandidate:
    """Derive and fully validate one CURRENT registry candidate in memory."""

    if case.finding is None:
        raise AdminCLIError("CURRENT sólo admite findings históricos.")
    _select_exact_finding_case(context, case.finding)
    finding = case.finding
    row = {
        "review_version": 1,
        "status": "approved",
        "outcome": "current",
        "boe_id": finding.boe_id,
        "administrative_action_id": finding.administrative_action_id,
        "source_document_sha256": finding.source_document_sha256,
        "expected_action_type": finding.action_type,
        "expected_decision": finding.decision,
        "expected_evidence_sha256": finding.evidence_sha256,
        "reason_code": finding.reason_code,
        "detector_policy_version": finding.detector_policy_version,
        "review_reason": _required_human_text(reason, field="reason"),
        "decision_source": _required_human_text(
            decision_source, field="decision_source"
        ),
        "reviewed_on": _reviewed_on(reviewed_on),
        "reviewer": _required_human_text(reviewer, field="reviewer"),
    }
    candidate = validate_historical_antecedent_reviews(
        _append_contract_row(
            context.current_reviews.reviews,
            row,
            HISTORICAL_ANTECEDENT_REVIEW_COLUMNS,
        )
    )
    loaded_candidate = LoadedHistoricalAntecedentReviews(
        reviews=candidate,
        source_path=context.current_reviews.source_path,
        logical_path=context.current_reviews.logical_path,
        file_sha256=context.current_reviews.file_sha256,
        semantic_identity=historical_antecedent_reviews_identity(candidate),
    )
    resolved = reconcile_historical_antecedent_findings(
        (finding,),
        context.corrections,
        loaded_candidate,
    )
    if len(resolved.resolved) != 1 or resolved.pending:
        raise AdminCLIError("La decisión CURRENT no resolvió el finding exacto.")
    return CurrentDecisionCandidate(
        finding=finding,
        row=row,
        validated_registry=candidate,
        review_id=historical_antecedent_review_id(row),
        target_path=context.current_reviews.source_path,
        original_file_sha256=context.current_reviews.file_sha256,
    )


def prepare_antecedent_decision(
    context: AdminContext,
    case: ReviewCase,
    *,
    reason: str,
    reviewer: str,
    decision_source: str,
    reviewed_on: date | None = None,
) -> AntecedentDecisionCandidate:
    """Derive and fully validate one ANTECEDENT correction in memory."""

    if case.finding is None:
        raise AdminCLIError("ANTECEDENT sólo admite findings históricos.")
    _select_exact_finding_case(context, case.finding)
    finding = case.finding
    correction_id = historical_action_exclusion_correction_id(
        boe_id=finding.boe_id,
        administrative_action_id=finding.administrative_action_id,
        expected_action_type=finding.action_type,
        expected_decision=finding.decision,
        expected_evidence_sha256=finding.evidence_sha256,
    )
    row = {
        "correction_id": correction_id,
        "correction_version": 1,
        "status": "approved",
        "boe_id": finding.boe_id,
        "entity_type": "administrative_action",
        "operation": "exclude",
        "administrative_action_id": finding.administrative_action_id,
        "expected_action_type": finding.action_type,
        "expected_decision": finding.decision,
        "expected_evidence_sha256": finding.evidence_sha256,
        "reason_code": "historical_antecedent_misattributed",
        "reason": _required_human_text(reason, field="reason"),
        "decision_source": _required_human_text(
            decision_source, field="decision_source"
        ),
        "reviewed_on": _reviewed_on(reviewed_on),
        "reviewer": _required_human_text(reviewer, field="reviewer"),
    }
    candidate = validate_administrative_action_corrections(
        _append_contract_row(
            context.corrections.corrections,
            row,
            ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
        )
    )
    loaded_candidate = LoadedAdministrativeActionCorrections(
        corrections=candidate,
        source_path=context.corrections.source_path,
        logical_path=context.corrections.logical_path,
        file_sha256=context.corrections.file_sha256,
        semantic_identity=corrections_identity(candidate),
    )
    resolved = reconcile_historical_antecedent_findings(
        (finding,),
        loaded_candidate,
        context.current_reviews,
    )
    if len(resolved.resolved) != 1 or resolved.pending:
        raise AdminCLIError(
            "La corrección ANTECEDENT no resolvió el finding exacto."
        )
    plan_administrative_action_corrections_subset(
        corrections=loaded_candidate,
        current_extractions=context.snapshot.current_extractions,
        corpus_boe_ids=context.snapshot.documents["identificador"].astype(str),
        source_extraction_snapshot_id=_extraction_snapshot_identity(
            context.snapshot
        ),
        extraction_config_id=context.expected_extraction_config_id,
        deterministic_code_sha256=corrections_subset_code_sha256(),
    )
    return AntecedentDecisionCandidate(
        finding=finding,
        row=row,
        validated_registry=candidate,
        correction_id=correction_id,
        target_path=context.corrections.source_path,
        original_file_sha256=context.corrections.file_sha256,
    )


def _atomic_write_csv_registry(
    *,
    target_path: Path,
    validated_registry: pd.DataFrame,
    original_file_sha256: str,
    loader: Callable[[Path], Any],
    expected_semantic_identity: str,
) -> Any:
    """Validate, atomically replace and reload one complete CSV registry."""

    target_path = Path(target_path)
    if not target_path.is_file() or target_path.is_symlink():
        raise AdminCLIError(f"El registro debe ser un fichero regular: {target_path}")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=target_path.parent,
    )
    os.close(descriptor)
    temp_path = Path(temp_name)
    try:
        validated_registry.to_csv(
            temp_path,
            index=False,
            lineterminator="\n",
        )
        staged = loader(temp_path)
        if staged.semantic_identity != expected_semantic_identity:
            raise AdminCLIError(
                "La identidad semántica del registro staged no coincide."
            )
        if _file_sha256(target_path) != original_file_sha256:
            raise AdminCLIError(
                "El registro original cambió durante la preparación; "
                "no se reemplazó."
            )
        os.replace(temp_path, target_path)
        installed = loader(target_path)
        if installed.semantic_identity != expected_semantic_identity:
            raise AdminCLIError(
                "La recarga final del registro no conserva su identidad."
            )
        return installed
    finally:
        if temp_path.exists():
            temp_path.unlink()


def persist_current_decision(
    candidate: CurrentDecisionCandidate,
) -> LoadedHistoricalAntecedentReviews:
    """Atomically persist one previously validated CURRENT candidate."""

    return _atomic_write_csv_registry(
        target_path=candidate.target_path,
        validated_registry=candidate.validated_registry,
        original_file_sha256=candidate.original_file_sha256,
        loader=load_historical_antecedent_reviews,
        expected_semantic_identity=historical_antecedent_reviews_identity(
            candidate.validated_registry
        ),
    )


def persist_antecedent_decision(
    candidate: AntecedentDecisionCandidate,
) -> LoadedAdministrativeActionCorrections:
    """Atomically persist one previously validated ANTECEDENT candidate."""

    return _atomic_write_csv_registry(
        target_path=candidate.target_path,
        validated_registry=candidate.validated_registry,
        original_file_sha256=candidate.original_file_sha256,
        loader=load_administrative_action_corrections,
        expected_semantic_identity=corrections_identity(
            candidate.validated_registry
        ),
    )


def _validate_review_dir(review_dir: Path) -> None:
    """Reject unsafe existing manual-review directory path types."""

    if review_dir.exists() and (
        not review_dir.is_dir() or review_dir.is_symlink()
    ):
        raise AdminCLIError(
            f"El directorio de revisiones no es seguro: {review_dir}"
        )


def _manual_reviews_for_snapshot(
    context: AdminContext,
    review_dir: Path,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Load current JSON decisions only for the validated document universe."""

    _validate_review_dir(review_dir)
    scope = tuple(sorted(
        context.snapshot.documents["identificador"].astype(str)
    ))
    reviews = _load_manual_review_files_for_boe_ids(
        context.snapshot.documents,
        context.snapshot.attempts,
        review_dir=review_dir,
        boe_ids=scope,
    )
    return reviews, scope


def prepare_manual_decision(
    context: AdminContext,
    case: ReviewCase,
    *,
    review_status: str,
    reviewer: str,
    notes: str,
    review_dir: Path = BOE_AI_MANUAL_REVIEW_DIR,
    reviewed_at: datetime | None = None,
) -> ManualDecisionCandidate:
    """Validate an exact proposal approval or whole-extraction rejection."""

    if case.finding is not None:
        raise AdminCLIError(
            "Los warnings históricos requieren CURRENT o ANTECEDENT."
        )
    if case.reason_code == "source_not_attempted":
        raise AdminCLIError(
            "source_not_attempted requiere primero un intento de extracción."
        )
    if case.reason_code not in _GENERIC_REVIEW_REASON_CODES:
        raise AdminCLIError(
            f"{case.reason_code}: condición genérica no soportada por el CLI."
        )
    if review_status not in _DECISIVE_MANUAL_STATUSES:
        raise AdminCLIError("Estado de revisión genérica no soportado.")
    corrected_payload = None
    if review_status == "manually_validated":
        if case.proposed_extraction_json is None:
            raise AdminCLIError(
                "El caso no contiene una proposed_extraction_json válida."
            )
        try:
            corrected_payload = json.loads(case.proposed_extraction_json)
        except json.JSONDecodeError as error:
            raise AdminCLIError(
                "La propuesta de extracción no contiene JSON válido."
            ) from error
    _select_exact_generic_case(context, case)

    review_dir = Path(review_dir)
    existing, scope = _manual_reviews_for_snapshot(context, review_dir)
    same_boe = existing.loc[
        existing["identificador_boe"].astype(str).eq(case.boe_id)
    ]
    if len(same_boe) > 1:
        raise AdminCLIError(
            f"{case.boe_id}: existe más de una revisión JSON vigente."
        )
    if len(same_boe) == 1:
        existing_row = same_boe.iloc[0]
        status = str(existing_row["review_status"])
        if status in _DECISIVE_MANUAL_STATUSES:
            raise AdminCLIError(
                f"{case.boe_id}: ya existe una revisión decisiva {status}."
            )
        if review_status == "manually_validated" and pd.notna(
            existing_row["corrected_extraction_json"]
        ):
            if json.loads(str(existing_row["corrected_extraction_json"])) != (
                corrected_payload
            ):
                raise AdminCLIError(
                    "La propuesta pending no coincide con la cola vigente."
                )

    base = existing.loc[
        ~existing["identificador_boe"].astype(str).eq(case.boe_id)
    ].copy()
    instant = _reviewed_at(reviewed_at)
    candidate_row = {
        "manual_review_id": pd.NA,
        "identificador_boe": case.boe_id,
        "source_document_sha256": case.source_document_sha256,
        "source_attempt_id": case.source_attempt_id,
        "extraction_config_id": context.expected_extraction_config_id,
        "review_status": review_status,
        "corrected_extraction_json": (
            case.proposed_extraction_json
            if review_status == "manually_validated"
            else pd.NA
        ),
        "reviewer": _required_human_text(reviewer, field="reviewer"),
        "review_notes": _required_human_text(notes, field="notes"),
        "reviewed_at_utc": instant,
        "contract_schema_sha256": pd.NA,
        "document_validation_version": pd.NA,
    }
    validated = _validate_manual_reviews(
        _append_contract_row(base, candidate_row, MANUAL_REVIEW_COLUMNS),
        context.snapshot.attempts,
        context.snapshot.documents,
    )
    target_rows = validated.loc[
        validated["identificador_boe"].astype(str).eq(case.boe_id)
    ]
    if len(target_rows) != 1:
        raise AdminCLIError("La revisión staged no produjo un target único.")
    target_row = target_rows.iloc[0]
    corrected_json = target_row["corrected_extraction_json"]
    payload = {
        "identificador_boe": case.boe_id,
        "source_document_sha256": case.source_document_sha256,
        "source_attempt_id": str(target_row["source_attempt_id"]),
        "extraction_config_id": str(target_row["extraction_config_id"]),
        "document_validation_version": str(
            target_row["document_validation_version"]
        ),
        "review_status": review_status,
        "reviewer": str(target_row["reviewer"]),
        "review_notes": str(target_row["review_notes"]),
        "reviewed_at_utc": instant.isoformat().replace("+00:00", "Z"),
        "corrected_extraction": (
            None
            if pd.isna(corrected_json)
            else json.loads(str(corrected_json))
        ),
    }
    target_path = review_dir / f"{case.boe_id}.json"
    return ManualDecisionCandidate(
        case=case,
        review_status=review_status,
        manual_review_id=str(target_row["manual_review_id"]),
        payload=payload,
        validated_reviews=validated,
        review_dir=review_dir,
        target_path=target_path,
        original_file_sha256=_optional_regular_file_sha256(target_path),
        scope_boe_ids=scope,
    )


def persist_manual_decision(
    context: AdminContext,
    candidate: ManualDecisionCandidate,
) -> pd.DataFrame:
    """Stage, validate and atomically install one per-BOE review JSON."""

    review_dir = candidate.review_dir
    _validate_review_dir(review_dir)
    parent = review_dir.parent
    if not parent.is_dir() or parent.is_symlink():
        raise AdminCLIError(
            f"El padre del directorio de revisiones no es seguro: {parent}"
        )
    staging_dir = Path(tempfile.mkdtemp(
        prefix=".boe-ai-reviews-",
        dir=parent,
    ))
    created_review_dir = False
    try:
        for boe_id in candidate.scope_boe_ids:
            source = review_dir / f"{boe_id}.json"
            if not source.exists():
                continue
            if not source.is_file() or source.is_symlink():
                raise AdminCLIError(
                    f"La revisión debe ser un fichero regular: {source}"
                )
            shutil.copyfile(source, staging_dir / source.name)
        staged_target = staging_dir / candidate.target_path.name
        staged_target.write_text(
            json.dumps(
                dict(candidate.payload),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        staged = _load_manual_review_files_for_boe_ids(
            context.snapshot.documents,
            context.snapshot.attempts,
            review_dir=staging_dir,
            boe_ids=candidate.scope_boe_ids,
        )
        target_rows = staged.loc[
            staged["identificador_boe"].astype(str).eq(candidate.case.boe_id)
        ]
        if (
            len(target_rows) != 1
            or str(target_rows.iloc[0]["manual_review_id"])
            != candidate.manual_review_id
        ):
            raise AdminCLIError(
                "La revisión JSON staged no conserva la identidad validada."
            )
        current_hash = _optional_regular_file_sha256(candidate.target_path)
        if current_hash != candidate.original_file_sha256:
            raise AdminCLIError(
                "La revisión original cambió durante la preparación; "
                "no se reemplazó."
            )
        if not review_dir.exists():
            review_dir.mkdir()
            created_review_dir = True
        os.replace(staged_target, candidate.target_path)
        installed = _load_manual_review_files_for_boe_ids(
            context.snapshot.documents,
            context.snapshot.attempts,
            review_dir=review_dir,
            boe_ids=candidate.scope_boe_ids,
        )
        installed_rows = installed.loc[
            installed["identificador_boe"].astype(str).eq(
                candidate.case.boe_id
            )
        ]
        if (
            len(installed_rows) != 1
            or str(installed_rows.iloc[0]["manual_review_id"])
            != candidate.manual_review_id
        ):
            raise AdminCLIError(
                "La recarga final de la revisión no conserva su identidad."
            )
        return installed
    except Exception:
        if created_review_dir and review_dir.exists() and not any(
            review_dir.iterdir()
        ):
            review_dir.rmdir()
        raise
    finally:
        shutil.rmtree(staging_dir)


def format_case_list(cases: Sequence[ReviewCase]) -> str:
    """Format deterministic concise case rows for an operator."""

    if not cases:
        return "No pending review cases."
    lines = ["INDEX  BOE  REASON  SEVERITY  FINDINGS  CONTEXT"]
    historical_counts: dict[str, int] = {}
    for case in cases:
        if case.finding is not None:
            historical_counts[case.boe_id] = (
                historical_counts.get(case.boe_id, 0) + 1
            )
    for case in cases:
        count = historical_counts.get(case.boe_id, 1)
        context = (
            case.finding.administrative_action_id
            if case.finding is not None
            else case.title
        )
        lines.append(
            f"{case.index:<5}  {case.boe_id}  {case.reason_code}  "
            f"{case.severity}  {count}  {context}"
        )
    return "\n".join(lines)


def _format_proposed_extraction(value: str | None) -> list[str]:
    """Render a proposed extraction as a non-editable domain summary."""

    if value is None:
        return ["Proposed extraction: unavailable"]
    extraction = BOEProjectExtraction.model_validate_json(value)
    lines = [
        f"Classification: {extraction.classification_status.value}",
        "Document scope: "
        + (
            extraction.document_scope.value
            if extraction.document_scope is not None
            else "none"
        ),
        f"Classification reason: {extraction.classification_reason}",
        f"Publication events: {len(extraction.publication_events)}",
    ]
    for event_index, event in enumerate(
        extraction.publication_events, start=1
    ):
        asset_names = [
            name
            for asset in event.generation_assets
            for name in asset.names_raw
        ]
        lines.append(
            f"Event {event_index}: assets={asset_names}; "
            f"actions={len(event.administrative_actions)}; "
            f"summary={event.event_summary}"
        )
        for action_index, action in enumerate(
            event.administrative_actions, start=1
        ):
            lines.append(
                f"  Action {action_index}: {action.action_type.value} / "
                f"{action.decision.value}; targets={list(action.targets)}"
            )
            lines.append(f"    Evidence: {action.evidence}")
    return lines


def format_case_detail(case: ReviewCase) -> str:
    """Format one pending case with sufficient decision evidence."""

    lines = [
        f"BOE: {case.boe_id}",
        f"Publication date: {case.publication_date}",
        f"Title: {case.title}",
        f"Reason code: {case.reason_code}",
        f"Severity: {case.severity}",
        f"Display index: {case.index}",
    ]
    if case.finding is None:
        lines.extend(_format_proposed_extraction(
            case.proposed_extraction_json
        ))
        return "\n".join(lines)
    finding = case.finding
    lines.extend([
        f"Administrative action ID: {finding.administrative_action_id}",
        f"Action type: {finding.action_type}",
        f"Decision: {finding.decision}",
        f"Original evidence: {finding.evidence}",
        "Temporal signals: " + ", ".join(finding.temporal_signals),
        "Contextual signals: " + ", ".join(finding.contextual_signals),
        f"Detector policy version: {finding.detector_policy_version}",
    ])
    for occurrence_index, occurrence in enumerate(
        finding.occurrences, start=1
    ):
        lines.extend([
            f"Occurrence {occurrence_index}: section={occurrence.section}; "
            f"location={occurrence.start}:{occurrence.end}",
            f"Source passage: {occurrence.source_excerpt}",
            "Occurrence temporal signals: "
            + ", ".join(occurrence.temporal_signals),
            "Occurrence contextual signals: "
            + ", ".join(occurrence.contextual_signals),
        ])
    return "\n".join(lines)


def _print_registry_candidate(
    *,
    kind: str,
    identifier: str,
    row: Mapping[str, Any],
    target_path: Path,
) -> None:
    """Print a complete decision preview before confirmation or dry-run."""

    print(f"Decision: {kind}")
    print(f"Technical ID: {identifier}")
    print(f"Target registry: {target_path}")
    for key, value in row.items():
        print(f"{key}: {value}")


def _print_manual_candidate(candidate: ManualDecisionCandidate) -> None:
    """Print one generic review preview without exposing editable JSON."""

    print(f"Decision: {candidate.review_status}")
    print(f"Manual review ID: {candidate.manual_review_id}")
    print(f"Target review: {candidate.target_path}")
    print(f"BOE: {candidate.case.boe_id}")
    print(f"Reviewer: {candidate.payload['reviewer']}")
    print(f"Notes: {candidate.payload['review_notes']}")


def _confirm() -> bool:
    """Request explicit interactive confirmation for one filesystem write."""

    answer = input("Persist this decision? [y/N] ").strip().casefold()
    return answer in {"y", "yes"}


def _print_next_steps(
    context: AdminContext,
    *,
    corrections_path: Path,
    manual_review_dir: Path | None = None,
) -> None:
    """Print non-executing pipeline templates with known source information."""

    print("Next steps (not executed):")
    print(
        "uv run python -m renewables_permitting.pipeline extract "
        f"--documents {context.extraction_snapshot / 'documents.parquet'} "
        f"--attempts {context.extraction_snapshot} "
        + (
            f"--manual-reviews {manual_review_dir} "
            if manual_review_dir is not None
            else ""
        )
        + "--output-dir <NEW_EXTRACTION_OUTPUT> "
        f"--expected-extraction-config-id {context.expected_extraction_config_id}"
    )
    print(
        "uv run python -m renewables_permitting.pipeline "
        f"corrections-subset --corrections {corrections_path} "
        "--extraction-snapshot <NEW_EXTRACTION_OUTPUT> "
        "--output-dir <NEW_CORRECTIONS_SUBSET_OUTPUT> "
        f"--expected-extraction-config-id {context.expected_extraction_config_id}"
    )
    print(
        "uv run python -m renewables_permitting.pipeline silver "
        "--extraction-snapshot <NEW_EXTRACTION_OUTPUT> "
        "--corrections "
        "<NEW_CORRECTIONS_SUBSET_OUTPUT/administrative_action_corrections.csv> "
        "--output-dir <NEW_SILVER_OUTPUT> "
        f"--expected-extraction-config-id {context.expected_extraction_config_id}"
    )
    print(
        "uv run python -m renewables_permitting.pipeline downstream "
        "--silver-snapshot <NEW_SILVER_OUTPUT> "
        "--municipality-reference <VALIDATED_INE_REFERENCE> "
        "--output-dir <NEW_DOWNSTREAM_OUTPUT> "
        f"--expected-extraction-config-id {context.expected_extraction_config_id}"
    )


def _add_snapshot_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared validated-snapshot and registry path arguments."""

    parser.add_argument("--extraction-snapshot", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, default=CORRECTIONS_PATH)
    parser.add_argument(
        "--current-reviews", type=Path, default=CURRENT_REVIEWS_PATH
    )


def _add_case_arguments(
    parser: argparse.ArgumentParser,
    *,
    require_index: bool = False,
) -> None:
    """Add the BOE and optional finding-index selector arguments."""

    parser.add_argument("--boe-id", required=True)
    parser.add_argument("--index", type=int, required=require_index)


def _add_human_decision_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared human judgement fields for historical decisions."""

    parser.add_argument("--reason", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--decision-source", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _add_manual_decision_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared exact-proposal/rejection human fields."""

    parser.add_argument("--boe-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument(
        "--manual-review-dir",
        type=Path,
        default=BOE_AI_MANUAL_REVIEW_DIR,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    """Build the small administrative argparse command surface."""

    parser = argparse.ArgumentParser(
        prog="python -m renewables_permitting.admin",
        description=(
            "Register validated human review decisions without running the "
            "pipeline or editing analytical data."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list", help="list pending validated review cases"
    )
    _add_snapshot_arguments(list_parser)
    list_parser.add_argument("--boe-id")
    list_parser.add_argument("--reason-code")

    show_parser = subparsers.add_parser(
        "show", help="show one pending validated review case"
    )
    _add_snapshot_arguments(show_parser)
    _add_case_arguments(show_parser)

    for command, help_text in (
        ("current", "register an exact CURRENT historical decision"),
        ("antecedent", "register an exact ANTECEDENT exclusion"),
    ):
        decision_parser = subparsers.add_parser(command, help=help_text)
        _add_snapshot_arguments(decision_parser)
        _add_case_arguments(decision_parser)
        _add_human_decision_arguments(decision_parser)

    for command, help_text in (
        (
            "validate-extraction",
            "approve the exact proposed extraction without editing it",
        ),
        ("reject-extraction", "reject the complete BOE extraction"),
    ):
        review_parser = subparsers.add_parser(command, help=help_text)
        _add_snapshot_arguments(review_parser)
        _add_manual_decision_arguments(review_parser)

    decisions_parser = subparsers.add_parser(
        "list-decisions", help="list validated existing human decisions"
    )
    decisions_parser.add_argument("--extraction-snapshot", type=Path)
    decisions_parser.add_argument("--boe-id")
    decisions_parser.add_argument(
        "--corrections", type=Path, default=CORRECTIONS_PATH
    )
    decisions_parser.add_argument(
        "--current-reviews", type=Path, default=CURRENT_REVIEWS_PATH
    )
    decisions_parser.add_argument(
        "--manual-review-dir",
        type=Path,
        default=BOE_AI_MANUAL_REVIEW_DIR,
    )
    return parser


def _context_from_args(args: argparse.Namespace) -> AdminContext:
    """Load one command context from parsed path arguments."""

    return load_admin_context(
        args.extraction_snapshot,
        corrections_path=args.corrections,
        current_reviews_path=args.current_reviews,
    )


def _handle_list(args: argparse.Namespace) -> int:
    """Handle read-only deterministic pending-case listing."""

    context = _context_from_args(args)
    print(format_case_list(build_review_cases(
        context,
        boe_id=args.boe_id,
        reason_code=args.reason_code,
    )))
    return _EXIT_SUCCESS


def _handle_show(args: argparse.Namespace) -> int:
    """Handle read-only detailed case display."""

    context = _context_from_args(args)
    print(format_case_detail(select_review_case(
        context,
        boe_id=args.boe_id,
        index=args.index,
    )))
    return _EXIT_SUCCESS


def _handle_historical_write(args: argparse.Namespace) -> int:
    """Prepare, confirm, revalidate and persist CURRENT or ANTECEDENT."""

    context = _context_from_args(args)
    case = select_review_case(
        context,
        boe_id=args.boe_id,
        index=args.index,
    )
    if case.finding is None:
        raise AdminCLIError(
            f"{args.command} requiere un finding histórico pendiente."
        )
    reviewed_on = _utc_now().date()
    prepare = (
        prepare_current_decision
        if args.command == "current"
        else prepare_antecedent_decision
    )
    candidate = prepare(
        context,
        case,
        reason=args.reason,
        reviewer=args.reviewer,
        decision_source=args.decision_source,
        reviewed_on=reviewed_on,
    )
    identifier = (
        candidate.review_id
        if isinstance(candidate, CurrentDecisionCandidate)
        else candidate.correction_id
    )
    _print_registry_candidate(
        kind=args.command.upper(),
        identifier=identifier,
        row=candidate.row,
        target_path=candidate.target_path,
    )
    if args.dry_run:
        print("DRY RUN: validation completed; no filesystem mutation performed.")
        return _EXIT_SUCCESS
    if not args.yes and not _confirm():
        print("Cancelled; no filesystem mutation performed.")
        return _EXIT_SUCCESS

    fresh_context = _context_from_args(args)
    fresh_case = _select_exact_finding_case(
        fresh_context, case.finding
    )
    fresh_candidate = prepare(
        fresh_context,
        fresh_case,
        reason=args.reason,
        reviewer=args.reviewer,
        decision_source=args.decision_source,
        reviewed_on=reviewed_on,
    )
    if isinstance(fresh_candidate, CurrentDecisionCandidate):
        persist_current_decision(fresh_candidate)
    else:
        persist_antecedent_decision(fresh_candidate)
    print(f"Persisted {args.command}: {identifier}")
    _print_next_steps(
        fresh_context,
        corrections_path=args.corrections,
    )
    return _EXIT_SUCCESS


def _handle_manual_write(args: argparse.Namespace) -> int:
    """Prepare, confirm, revalidate and persist one generic review decision."""

    context = _context_from_args(args)
    case = select_review_case(context, boe_id=args.boe_id)
    status = (
        "manually_validated"
        if args.command == "validate-extraction"
        else "rejected"
    )
    reviewed_at = _utc_now()
    candidate = prepare_manual_decision(
        context,
        case,
        review_status=status,
        reviewer=args.reviewer,
        notes=args.notes,
        review_dir=args.manual_review_dir,
        reviewed_at=reviewed_at,
    )
    _print_manual_candidate(candidate)
    if args.dry_run:
        print("DRY RUN: validation completed; no filesystem mutation performed.")
        return _EXIT_SUCCESS
    if not args.yes and not _confirm():
        print("Cancelled; no filesystem mutation performed.")
        return _EXIT_SUCCESS

    fresh_context = _context_from_args(args)
    fresh_case = _select_exact_generic_case(fresh_context, case)
    fresh_candidate = prepare_manual_decision(
        fresh_context,
        fresh_case,
        review_status=status,
        reviewer=args.reviewer,
        notes=args.notes,
        review_dir=args.manual_review_dir,
        reviewed_at=reviewed_at,
    )
    persist_manual_decision(fresh_context, fresh_candidate)
    print(f"Persisted {args.command}: {fresh_candidate.manual_review_id}")
    _print_next_steps(
        fresh_context,
        corrections_path=args.corrections,
        manual_review_dir=args.manual_review_dir,
    )
    return _EXIT_SUCCESS


def _print_current_decisions(
    reviews: LoadedHistoricalAntecedentReviews,
    *,
    boe_id: str | None,
) -> None:
    """Print validated CURRENT decisions."""

    print("CURRENT validations:")
    rows = reviews.reviews
    if boe_id is not None:
        rows = rows.loc[rows["boe_id"].astype(str).eq(boe_id)]
    if rows.empty:
        print("  none")
        return
    for row in rows.sort_values(
        ["boe_id", "administrative_action_id"], kind="stable"
    ).to_dict(orient="records"):
        print(
            f"  {historical_antecedent_review_id(row)} | {row['boe_id']} | "
            f"{row['administrative_action_id']} | {row['reviewer']} | "
            f"{row['reviewed_on']} | {row['review_reason']} | "
            f"{row['decision_source']}"
        )


def _print_antecedent_decisions(
    corrections: LoadedAdministrativeActionCorrections,
    *,
    boe_id: str | None,
) -> None:
    """Print validated ANTECEDENT decisions."""

    print("ANTECEDENT corrections:")
    rows = corrections.corrections
    if boe_id is not None:
        rows = rows.loc[rows["boe_id"].astype(str).eq(boe_id)]
    if rows.empty:
        print("  none")
        return
    for row in rows.sort_values("correction_id", kind="stable").to_dict(
        orient="records"
    ):
        print(
            f"  {row['correction_id']} | {row['boe_id']} | "
            f"{row['administrative_action_id']} | {row['reviewer']} | "
            f"{row['reviewed_on']} | {row['reason']} | "
            f"{row['decision_source']}"
        )


def _print_generic_decisions(
    context: AdminContext,
    *,
    review_dir: Path,
    boe_id: str | None,
) -> None:
    """Print current validated generic decisions for the snapshot universe."""

    print("Generic extraction reviews:")
    current, _ = _manual_reviews_for_snapshot(context, review_dir)
    current_boes = set(current["identificador_boe"].astype(str))
    inherited = context.snapshot.manual_reviews.loc[
        ~context.snapshot.manual_reviews["identificador_boe"]
        .astype(str)
        .isin(current_boes)
    ]
    rows = pd.DataFrame.from_records(
        [
            *current.to_dict(orient="records"),
            *inherited.to_dict(orient="records"),
        ],
        columns=MANUAL_REVIEW_COLUMNS,
    )
    rows = rows.loc[
        rows["review_status"].astype(str).isin(_DECISIVE_MANUAL_STATUSES)
    ]
    if boe_id is not None:
        rows = rows.loc[
            rows["identificador_boe"].astype(str).eq(boe_id)
        ]
    if rows.empty:
        print("  none")
        return
    rows["reviewed_at_utc"] = pd.to_datetime(
        rows["reviewed_at_utc"], errors="coerce", utc=True
    )
    for row in rows.sort_values(
        ["identificador_boe", "reviewed_at_utc", "manual_review_id"],
        kind="stable",
    ).to_dict(orient="records"):
        reviewed = row["reviewed_at_utc"]
        reviewed_text = "" if pd.isna(reviewed) else reviewed.isoformat()
        print(
            f"  {row['manual_review_id']} | {row['identificador_boe']} | "
            f"{row['review_status']} | {row['reviewer']} | "
            f"{reviewed_text} | {row['review_notes']}"
        )


def _handle_list_decisions(args: argparse.Namespace) -> int:
    """Handle the read-only validated human-decision audit view."""

    corrections = load_administrative_action_corrections(args.corrections)
    current_reviews = load_historical_antecedent_reviews(
        args.current_reviews
    )
    _print_current_decisions(current_reviews, boe_id=args.boe_id)
    _print_antecedent_decisions(corrections, boe_id=args.boe_id)
    if args.extraction_snapshot is None:
        print("Generic extraction reviews: provide --extraction-snapshot.")
        return _EXIT_SUCCESS
    context = load_admin_context(
        args.extraction_snapshot,
        corrections_path=args.corrections,
        current_reviews_path=args.current_reviews,
    )
    _print_generic_decisions(
        context,
        review_dir=args.manual_review_dir,
        boe_id=args.boe_id,
    )
    return _EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the bounded administrative CLI without pipeline execution."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "list": _handle_list,
        "show": _handle_show,
        "current": _handle_historical_write,
        "antecedent": _handle_historical_write,
        "validate-extraction": _handle_manual_write,
        "reject-extraction": _handle_manual_write,
        "list-decisions": _handle_list_decisions,
    }
    try:
        return handlers[args.command](args)
    except (AdminCLIError, PipelineError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return _EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
