from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

import pandas as pd

from renewables_permitting.boe_candidates import (
    CANDIDATE_POLICY_ID,
    CANDIDATE_POLICY_VERSION,
    empty_energy_candidates,
    materialize_energy_candidates,
    select_energy_candidates,
)
from renewables_permitting.boe_documents import (
    BOE_DOCUMENT_INPUT_COLUMNS,
    build_extractor_document_input,
    fetch_boe_document_xml,
    materialize_boe_document_xml,
    materialize_extractor_document_input,
    materialize_xml_download_log,
)
from renewables_permitting.boe_source import (
    empty_boe_items,
    fetch_boe_summaries,
    inclusive_date_range,
    materialize_boe_items,
    materialize_boe_summary,
    parse_boe_summary,
)
from renewables_permitting.downstream import DownstreamError, run_downstream
from renewables_permitting.extraction.agent import (
    build_boe_extraction_agent,
    validate_runtime_configuration,
)
from renewables_permitting.extraction.canonicalization import (
    preclassify_document_without_model,
)
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CHECKPOINT_EVERY,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.documents import (
    build_source_document,
)
from renewables_permitting.extraction.corrections import (
    apply_administrative_action_corrections,
    load_administrative_action_corrections,
)
from renewables_permitting.extraction.flat_materialization import (
    FlatMaterializationError,
    FlatMaterializationResult,
    load_flat_materialization,
    materialize_current_extractions,
)
from renewables_permitting.extraction.flat_validation import (
    validate_flat_tables,
)
from renewables_permitting.extraction.flatten import (
    flatten_current_extractions,
)
from renewables_permitting.extraction.models import BOEProjectExtraction
from renewables_permitting.extraction.persistence import save_parquet_atomic
from renewables_permitting.extraction.recanonicalization import (
    build_recanonicalized_attempt_record,
    historical_recanonicalization_identity,
)
from renewables_permitting.extraction.review import (
    build_review_queue,
    empty_ai_extraction_attempts_log,
    empty_manual_reviews,
    load_ai_extraction_attempts,
    load_manual_review_files,
    normalise_ai_extraction_attempts_log,
    normalise_manual_reviews,
    select_best_valid_extractions,
)
from renewables_permitting.extraction.runner import extract_documents
from renewables_permitting.ine_reference import (
    build_municipality_dimension,
    compare_municipality_dimensions,
    compute_municipality_reference_hash,
    load_ine_source_tables,
    load_municipality_reference,
    materialize_municipality_dimension,
)


PIPELINE_STAGE_VERSION = "1"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_MODEL_PERMISSION_REQUIRED = 3
EXIT_REVIEW_REQUIRED = 4

_SOURCE_MANIFEST = "manifest.json"
_SOURCE_DOCUMENTS = "documents.parquet"
_SOURCE_ITEMS = "boe_items.parquet"
_SOURCE_CANDIDATES = "candidates.parquet"
_SOURCE_XML_LOG = "xml_download_log.parquet"
_SOURCE_SUMMARIES_DIR = "summaries"
_SOURCE_XML_DIR = "xml"

_EXTRACTION_MANIFEST = "manifest.json"
_EXTRACTION_DOCUMENTS = "documents.parquet"
_EXTRACTION_ATTEMPTS = "attempts.parquet"
_EXTRACTION_MANUAL_REVIEWS = "manual_reviews.parquet"
_EXTRACTION_CURRENT = "current_extractions.parquet"
_EXTRACTION_REVIEW_QUEUE = "review_queue.parquet"
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


class PipelineError(RuntimeError):
    """An orchestration boundary failed without changing domain semantics."""


class ModelPermissionRequired(PipelineError):
    """Documents need AI execution but the caller did not opt in."""


class ReviewRequired(PipelineError):
    """Blocking human review prevents Silver publication."""


@dataclass(frozen=True)
class SourceStageResult:
    """Published source snapshot and its canonical document boundary."""

    output_dir: Path
    documents_path: Path
    manifest_path: Path
    document_count: int
    candidate_count: int


@dataclass(frozen=True)
class ScopeSummary:
    """Deterministic union statistics for explicit BOE scope files."""

    paths: tuple[Path, ...]
    input_sizes: tuple[int, ...]
    overlap_count: int
    final_unique_count: int


@dataclass(frozen=True)
class ExtractionPlan:
    """Side-effect-free plan for one extraction snapshot."""

    documents: pd.DataFrame
    attempts: pd.DataFrame
    manual_reviews: pd.DataFrame
    scope_summary: ScopeSummary | None
    total_documents: int
    compatible_existing_count: int
    pending_document_count: int
    deterministic_pending_count: int
    model_required_count: int
    model_calls_planned: int
    execution_document_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionStageResult:
    """Paths and gate state of one published extraction snapshot."""

    output_dir: Path
    documents_path: Path
    attempts_path: Path
    manual_reviews_path: Path
    current_extractions_path: Path
    review_queue_path: Path
    manifest_path: Path
    total_documents: int
    compatible_existing_count: int
    pending_document_count: int
    model_calls_planned: int
    blocking_review_count: int


@dataclass(frozen=True)
class LoadedExtractionSnapshot:
    """Extraction snapshot revalidated before entering the Silver stage."""

    input_dir: Path
    documents: pd.DataFrame
    attempts: pd.DataFrame
    manual_reviews: pd.DataFrame
    current_extractions: pd.DataFrame
    review_queue: pd.DataFrame
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class RecanonicalizationPlan:
    """Validated, write-free plan for a frozen extraction snapshot."""

    source_snapshot: Path
    output_dir: Path
    documents: pd.DataFrame
    source: LoadedExtractionSnapshot
    source_run_id: str
    source_attempt_count: int
    precanonical_record_count: int
    deterministic_record_count: int
    target_record_count: int
    model_calls: int = 0


@dataclass(frozen=True)
class RecanonicalizationStageResult(ExtractionStageResult):
    """Published recanonicalized extraction snapshot and migration counts."""

    source_attempt_count: int
    precanonical_record_count: int
    deterministic_record_count: int
    model_calls: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _created_at() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _normalise_created_at(value: datetime | None) -> datetime:
    instant = _utc_now() if value is None else value
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("created_at must include timezone information.")
    return instant.astimezone(timezone.utc)


def _format_created_at(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    value = dict(payload)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if json.loads(path.read_text(encoding="utf-8")) != value:
        raise PipelineError(f"Manifest round trip failed: {path}")


def _artifact(path: Path, dataframe: pd.DataFrame) -> dict[str, Any]:
    return {
        "filename": path.name,
        "row_count": len(dataframe),
        "sha256": _sha256_file(path),
    }


def _validate_new_output(output_dir: Path) -> Path:
    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    return output_dir


def _staging_directory(output_dir: Path) -> tuple[Path, str]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{output_dir.name}.staging-"
    return Path(tempfile.mkdtemp(prefix=prefix, dir=output_dir.parent)), prefix


def _cleanup_staging(staging_dir: Path, output_dir: Path, prefix: str) -> None:
    if staging_dir.parent != output_dir.parent:
        raise RuntimeError("Refusing to clean staging outside output parent.")
    if not staging_dir.name.startswith(prefix) or staging_dir.is_symlink():
        raise RuntimeError("Refusing to clean an unexpected staging path.")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)


def _validate_expected_config(expected_extraction_config_id: str) -> None:
    if expected_extraction_config_id != EXTRACTION_CONFIG_ID:
        raise PipelineError(
            "Extraction configuration mismatch: "
            f"expected={expected_extraction_config_id!r}; "
            f"active={EXTRACTION_CONFIG_ID!r}."
        )


def _frame_equal(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    sort_by: Sequence[str],
    ignore_columns: Sequence[str] = (),
) -> bool:
    common = [
        column for column in left.columns
        if column in right.columns and column not in ignore_columns
    ]
    if set(left.columns) - set(ignore_columns) != set(right.columns) - set(
        ignore_columns
    ):
        return False
    left_ordered = left.loc[:, common].sort_values(
        list(sort_by), kind="stable"
    ).reset_index(drop=True)
    right_ordered = right.loc[:, common].sort_values(
        list(sort_by), kind="stable"
    ).reset_index(drop=True)
    for column in common:
        left_values = left_ordered[column]
        right_values = right_ordered[column]
        for left_value, right_value in zip(
            left_values, right_values, strict=True
        ):
            left_missing = bool(pd.isna(left_value))
            right_missing = bool(pd.isna(right_value))
            if left_missing or right_missing:
                if left_missing and right_missing:
                    continue
                return False
            if not bool(left_value == right_value):
                return False
    return True


def prepare_documents(documents: pd.DataFrame) -> pd.DataFrame:
    """Validate canonical document rows and derive their extraction hashes."""

    if not isinstance(documents, pd.DataFrame):
        raise TypeError("documents must be a pandas.DataFrame.")
    if documents.columns.duplicated().any():
        raise ValueError("Canonical documents contain duplicate columns.")
    required = {
        "identificador",
        "fecha_publicacion",
        "titulo",
        "xml_status",
        "texto_limpio",
    }
    missing = required - set(documents.columns)
    if missing:
        raise ValueError(f"Canonical documents miss columns: {sorted(missing)}")
    prepared = documents.copy(deep=True)
    prepared["fecha_publicacion"] = pd.to_datetime(
        prepared["fecha_publicacion"], errors="raise"
    )
    xml_status = prepared["xml_status"].astype("string")
    invalid = (
        xml_status.isna()
        | ~xml_status.eq("ok").fillna(False)
        | prepared["texto_limpio"].isna()
        | prepared["texto_limpio"].astype("string").str.strip().eq("")
    )
    if invalid.any():
        raise ValueError("Canonical documents include invalid XML/text rows.")
    identifiers = prepared["identificador"].astype("string")
    if identifiers.isna().any() or identifiers.str.strip().eq("").any():
        raise ValueError("Canonical documents contain empty BOE identifiers.")
    if identifiers.duplicated().any():
        raise ValueError("Canonical documents contain duplicate BOE identifiers.")
    prepared["identificador"] = identifiers
    prepared["source_document_sha256"] = prepared.apply(
        lambda row: build_source_document(row).source_document_sha256,
        axis=1,
    ).astype("string")
    return prepared.sort_values("identificador", kind="stable").reset_index(
        drop=True
    )


def _documents_identity(documents: pd.DataFrame) -> str:
    records = documents.loc[
        :, ["identificador", "source_document_sha256"]
    ].sort_values("identificador", kind="stable").to_dict(orient="records")
    return sha256(_canonical_json_bytes(records)).hexdigest()


def _verify_artifact(
    snapshot_dir: Path,
    manifest: Mapping[str, Any],
    artifact_name: str,
) -> Path:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise PipelineError("Snapshot manifest has no artifact metadata.")
    entry = artifacts.get(artifact_name)
    if not isinstance(entry, Mapping):
        raise PipelineError(f"Snapshot manifest misses {artifact_name!r}.")
    filename = entry.get("filename")
    expected_hash = entry.get("sha256")
    if not isinstance(filename, str) or not isinstance(expected_hash, str):
        raise PipelineError(f"Invalid metadata for {artifact_name!r}.")
    path = snapshot_dir / filename
    if not path.is_file() or path.is_symlink():
        raise PipelineError(f"Snapshot artifact is missing: {path}")
    if _sha256_file(path) != expected_hash:
        raise PipelineError(f"Snapshot artifact hash mismatch: {artifact_name}")
    return path


def load_documents_input(path: Path) -> pd.DataFrame:
    """Load a canonical document Parquet or a verified source snapshot."""

    path = Path(path)
    if path.is_dir():
        manifest_path = path / _SOURCE_MANIFEST
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise PipelineError("Source snapshot manifest is missing.")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PipelineError("Source snapshot manifest is invalid.") from error
        document_path = _verify_artifact(path, manifest, "documents")
    else:
        document_path = path
    if not document_path.is_file() or document_path.is_symlink():
        raise FileNotFoundError(f"Canonical document input not found: {path}")
    return prepare_documents(pd.read_parquet(document_path))


def _scope_ids(path: Path) -> tuple[str, ...]:
    path = Path(path)
    if path.suffix.casefold() == ".csv":
        frame = pd.read_csv(path, dtype="string")
    elif path.suffix.casefold() in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported scope format: {path}")
    id_column = next(
        (column for column in ("identificador_boe", "identificador")
         if column in frame.columns),
        None,
    )
    if id_column is None:
        raise ValueError(f"Scope {path} has no BOE identifier column.")
    identifiers = frame[id_column].astype("string").str.strip()
    if identifiers.isna().any() or identifiers.eq("").any():
        raise ValueError(f"Scope {path} contains empty BOE identifiers.")
    if identifiers.duplicated().any():
        raise ValueError(f"Scope {path} contains duplicate BOE identifiers.")
    return tuple(sorted(identifiers.astype(str)))


def apply_document_scopes(
    documents: pd.DataFrame,
    scope_paths: Sequence[Path],
) -> tuple[pd.DataFrame, ScopeSummary | None]:
    """Apply the deterministic union of explicit CSV/Parquet BOE scopes."""

    if not scope_paths:
        return documents.copy(deep=True), None
    paths = tuple(Path(path) for path in scope_paths)
    scopes = tuple(_scope_ids(path) for path in paths)
    union = set().union(*(set(scope) for scope in scopes))
    overlap = sum(len(scope) for scope in scopes) - len(union)
    available = set(documents["identificador"].astype(str))
    missing = sorted(union - available)
    if missing:
        raise ValueError(
            f"Scope contains BOE IDs absent from documents: {missing[:20]}"
        )
    scoped = documents.loc[
        documents["identificador"].astype(str).isin(union)
    ].sort_values("identificador", kind="stable").reset_index(drop=True)
    return scoped, ScopeSummary(
        paths=paths,
        input_sizes=tuple(len(scope) for scope in scopes),
        overlap_count=overlap,
        final_unique_count=len(union),
    )


def _load_json_manifest(path: Path, *, stage: str) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise PipelineError(f"{stage} snapshot manifest is missing.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PipelineError(f"{stage} snapshot manifest is invalid.") from error
    if not isinstance(manifest, dict):
        raise PipelineError(f"{stage} snapshot manifest is not an object.")
    return manifest


def run_source_stage(
    *,
    start_date: date,
    end_date: date,
    output_dir: Path,
    dry_run: bool = False,
) -> SourceStageResult | None:
    """Fetch and atomically publish one canonical BOE document snapshot.

    Network access occurs only when this function is explicitly called with
    ``dry_run=False``. All parsing, candidate selection and XML conversion are
    delegated to the existing production modules.
    """

    output_dir = _validate_new_output(output_dir)
    dates = inclusive_date_range(start_date, end_date)
    if dry_run:
        print(
            f"source: dates={len(dates)} range={start_date}..{end_date} "
            f"output={output_dir}"
        )
        return None

    summaries = fetch_boe_summaries(start_date, end_date)
    failed = [result for result in summaries if result.status == "failed"]
    if failed:
        details = [
            f"{result.publication_date}:{result.error_type}"
            for result in failed[:10]
        ]
        raise PipelineError(f"BOE source failed: {details}")

    item_frames: list[pd.DataFrame] = []
    for result in summaries:
        if result.status != "success":
            continue
        if result.payload is None:
            raise PipelineError("Successful BOE summary has no payload.")
        parsed = parse_boe_summary(result.payload)
        if not parsed.empty:
            item_frames.append(parsed)
    items = (
        pd.concat(item_frames, ignore_index=True)
        if item_frames
        else empty_boe_items()
    )
    if not items.empty:
        items = items.sort_values(
            ["fecha_publicacion", "identificador"], kind="stable"
        ).reset_index(drop=True)
    if items["identificador"].duplicated().any():
        raise PipelineError("BOE source contains duplicate IDs across summaries.")
    candidates = (
        select_energy_candidates(items)
        if not items.empty
        else empty_energy_candidates()
    )

    xml_results = [
        fetch_boe_document_xml(
            boe_id=str(row.identificador),
            publication_date=pd.Timestamp(row.fecha_publicacion).date(),
            source_url=(
                None if pd.isna(row.url_xml) else str(row.url_xml)
            ),
        )
        for row in candidates.itertuples(index=False)
    ]
    xml_failures = [
        result for result in xml_results if result.status != "downloaded"
    ]
    if xml_failures:
        details = [
            f"{result.boe_id}:{result.status}"
            for result in xml_failures[:10]
        ]
        raise PipelineError(f"BOE XML source failed: {details}")

    staging_dir, prefix = _staging_directory(output_dir)
    published = False
    try:
        summaries_dir = staging_dir / _SOURCE_SUMMARIES_DIR
        xml_dir = staging_dir / _SOURCE_XML_DIR
        for result in summaries:
            materialize_boe_summary(result, output_dir=summaries_dir)
        item_path = staging_dir / _SOURCE_ITEMS
        candidate_path = staging_dir / _SOURCE_CANDIDATES
        xml_log_path = staging_dir / _SOURCE_XML_LOG
        document_path = staging_dir / _SOURCE_DOCUMENTS
        materialize_boe_items(items, output_path=item_path)
        materialize_energy_candidates(candidates, output_path=candidate_path)
        for result in xml_results:
            materialize_boe_document_xml(result, output_dir=xml_dir)
        materialize_xml_download_log(xml_results, output_path=xml_log_path)
        documents = build_extractor_document_input(
            candidates,
            xml_dir=xml_dir,
        )
        materialize_extractor_document_input(
            documents,
            output_path=document_path,
        )
        prepared_documents = prepare_documents(documents)

        summary_records: list[dict[str, Any]] = []
        for result in summaries:
            summary_hash = result.summary_sha256
            if result.status == "success" and result.payload is not None:
                matching = items.loc[
                    items["fecha_publicacion"].eq(
                        pd.Timestamp(result.publication_date)
                    )
                ]
                hashes = sorted(set(matching["summary_sha256"].dropna()))
                if len(hashes) == 1:
                    summary_hash = str(hashes[0])
            summary_records.append({
                "publication_date": result.publication_date.isoformat(),
                "status": result.status,
                "source_url": result.source_url,
                "summary_sha256": summary_hash,
                "item_count": result.item_count,
            })
        xml_records = [{
            "boe_id": result.boe_id,
            "source_url": result.source_url,
            "xml_sha256": result.xml_sha256,
            "byte_count": result.byte_count,
        } for result in xml_results]
        manifest = {
            "stage": "source",
            "stage_version": PIPELINE_STAGE_VERSION,
            "created_at": _created_at(),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "candidate_policy_version": CANDIDATE_POLICY_VERSION,
            "candidate_policy_id": CANDIDATE_POLICY_ID,
            "document_identity_sha256": _documents_identity(
                prepared_documents
            ),
            "counts": {
                "dates": len(dates),
                "successful_summaries": sum(
                    result.status == "success" for result in summaries
                ),
                "no_publication": sum(
                    result.status == "no_publication" for result in summaries
                ),
                "items": len(items),
                "candidates": len(candidates),
                "documents": len(documents),
            },
            "summaries": summary_records,
            "xml_documents": xml_records,
            "artifacts": {
                "boe_items": _artifact(item_path, items),
                "candidates": _artifact(candidate_path, candidates),
                "xml_download_log": _artifact(
                    xml_log_path,
                    pd.read_parquet(xml_log_path),
                ),
                "documents": _artifact(document_path, documents),
            },
        }
        manifest_path = staging_dir / _SOURCE_MANIFEST
        _write_json(manifest_path, manifest)
        _validate_new_output(output_dir)
        staging_dir.rename(output_dir)
        published = True
    finally:
        if not published:
            _cleanup_staging(staging_dir, output_dir, prefix)

    return SourceStageResult(
        output_dir=output_dir,
        documents_path=output_dir / _SOURCE_DOCUMENTS,
        manifest_path=output_dir / _SOURCE_MANIFEST,
        document_count=len(documents),
        candidate_count=len(candidates),
    )


def _validate_resume_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_extraction_config_id: str,
) -> None:
    expected = {
        "stage": "extraction",
        "stage_version": PIPELINE_STAGE_VERSION,
        "extraction_config_id": expected_extraction_config_id,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "scope_classification_policy": EXTRACTION_CONFIG[
            "scope_classification_policy"
        ],
    }
    mismatches = [
        key for key, expected_value in expected.items()
        if manifest.get(key) != expected_value
    ]
    if mismatches:
        raise PipelineError(
            "Resume snapshot configuration is incompatible: "
            f"{mismatches}."
        )


def _validate_resume_attempts(
    attempts: pd.DataFrame,
    documents: pd.DataFrame,
    *,
    expected_extraction_config_id: str,
) -> pd.DataFrame:
    """Fail closed before reusing paid work from a previous extraction."""

    attempts = normalise_ai_extraction_attempts_log(attempts)
    if attempts.empty:
        return attempts
    if attempts.columns.duplicated().any():
        raise PipelineError("Resume attempts contain duplicate columns.")

    required_text = {
        "attempt_id",
        "identificador_boe",
        "source_document_sha256",
        "extraction_config_id",
        "contract_schema_sha256",
        "instructions_sha256",
        "model_provider",
        "model_name",
        "document_validation_version",
        "extraction_status",
        "extracted_at",
    }
    invalid_fields: list[str] = []
    for column in sorted(required_text):
        values = attempts[column].astype("string")
        if values.isna().any() or values.str.strip().eq("").any():
            invalid_fields.append(column)
    if invalid_fields:
        raise PipelineError(
            f"Resume attempts contain incomplete fields: {invalid_fields}."
        )

    attempt_ids = attempts["attempt_id"].astype("string")
    if attempt_ids.duplicated(keep=False).any():
        raise PipelineError("Resume attempts contain duplicate attempt_id values.")

    identity_columns = {
        "extraction_config_id": expected_extraction_config_id,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }
    mismatches = [
        column for column, expected_value in identity_columns.items()
        if not attempts[column].astype("string").eq(expected_value).all()
    ]
    if mismatches:
        raise PipelineError(
            "Resume attempt configuration is incompatible: "
            f"{mismatches}."
        )

    statuses = attempts["extraction_status"].astype("string")
    if not statuses.isin(["ok", "error"]).all():
        raise PipelineError("Resume attempts contain an invalid extraction status.")
    extracted_at = pd.to_datetime(
        attempts["extracted_at"], errors="coerce", utc=True
    )
    if extracted_at.isna().any():
        raise PipelineError("Resume attempts contain an invalid extracted_at.")

    sources = {
        str(row.identificador): str(row.source_document_sha256)
        for row in documents.itertuples(index=False)
    }
    attempt_boe_ids = attempts["identificador_boe"].astype("string")
    outside = sorted(set(attempt_boe_ids.astype(str)) - set(sources))
    if outside:
        raise PipelineError(
            "Resume attempts contain BOE IDs outside the cumulative scope: "
            f"{outside[:20]}."
        )
    stale = attempts.loc[
        [
            str(source_hash) != sources[str(boe_id)]
            for boe_id, source_hash in zip(
                attempt_boe_ids,
                attempts["source_document_sha256"].astype("string"),
                strict=True,
            )
        ]
    ]
    if not stale.empty:
        raise PipelineError(
            "Resume attempt source hash is incompatible with the current "
            "document scope."
        )

    successful = attempts.loc[statuses.eq("ok")]
    for row in successful.itertuples(index=False):
        try:
            extraction = BOEProjectExtraction.model_validate_json(
                str(row.extraction_json)
            )
        except (TypeError, ValueError) as error:
            raise PipelineError(
                f"Resume attempt {row.attempt_id!r} has invalid extraction JSON."
            ) from error
        if extraction.boe_id != str(row.identificador_boe):
            raise PipelineError(
                f"Resume attempt {row.attempt_id!r} has inconsistent BOE lineage."
            )
    return attempts


def _read_attempts_input(
    path: Path | None,
    *,
    expected_extraction_config_id: str,
) -> tuple[pd.DataFrame, Path | None]:
    if path is None:
        return empty_ai_extraction_attempts_log(), None
    path = Path(path)
    if not path.exists() or path.is_symlink():
        raise FileNotFoundError(f"Attempt input not found: {path}")
    inherited_manual: Path | None = None
    if path.is_dir():
        manifest = _load_json_manifest(path, stage="Extraction")
        _validate_resume_manifest(
            manifest,
            expected_extraction_config_id=expected_extraction_config_id,
        )
        attempt_path = _verify_artifact(path, manifest, "attempts")
        manual_entry = manifest.get("artifacts", {}).get("manual_reviews")
        if isinstance(manual_entry, Mapping):
            inherited_manual = _verify_artifact(
                path, manifest, "manual_reviews"
            )
    else:
        attempt_path = path
    return load_ai_extraction_attempts(attempt_path), inherited_manual


def _read_manual_reviews(
    path: Path | None,
    *,
    inherited_path: Path | None,
    documents: pd.DataFrame,
    attempts: pd.DataFrame,
) -> pd.DataFrame:
    selected = Path(path) if path is not None else inherited_path
    if selected is None:
        return empty_manual_reviews()
    if selected.is_dir():
        return load_manual_review_files(
            documents,
            attempts,
            review_dir=selected,
            output_path=None,
        )
    if not selected.is_file() or selected.is_symlink():
        raise FileNotFoundError(f"Manual review input not found: {selected}")
    return normalise_manual_reviews(pd.read_parquet(selected))


def build_extraction_plan(
    *,
    documents: Path,
    attempts: Path | None = None,
    manual_reviews: Path | None = None,
    scope_paths: Sequence[Path] = (),
    execute_model: bool,
    expected_extraction_config_id: str,
) -> ExtractionPlan:
    """Plan compatible reuse and new model work without side effects."""

    _validate_expected_config(expected_extraction_config_id)
    source = load_documents_input(documents)
    source, scope_summary = apply_document_scopes(source, scope_paths)
    attempts_frame, inherited_manual = _read_attempts_input(
        attempts,
        expected_extraction_config_id=expected_extraction_config_id,
    )
    attempts_frame = _validate_resume_attempts(
        attempts_frame,
        source,
        expected_extraction_config_id=expected_extraction_config_id,
    )
    manual_frame = _read_manual_reviews(
        manual_reviews,
        inherited_path=inherited_manual,
        documents=source,
        attempts=attempts_frame,
    )
    queue = build_review_queue(
        attempts=attempts_frame,
        source_df=source,
        manual_reviews=manual_frame,
    )
    unattempted_ids = tuple(sorted(
        queue.loc[
            queue["reason_code"].eq("source_not_attempted"),
            "identificador_boe",
        ].astype(str)
    ))
    source_by_id = {
        str(row["identificador"]): row
        for _, row in source.iterrows()
    }
    model_ids: list[str] = []
    deterministic_ids: list[str] = []
    for boe_id in unattempted_ids:
        decision, _ = preclassify_document_without_model(
            build_source_document(source_by_id[boe_id])
        )
        if decision is None:
            model_ids.append(boe_id)
        else:
            deterministic_ids.append(boe_id)
    return ExtractionPlan(
        documents=source,
        attempts=attempts_frame,
        manual_reviews=manual_frame,
        scope_summary=scope_summary,
        total_documents=len(source),
        compatible_existing_count=len(source) - len(unattempted_ids),
        pending_document_count=len(unattempted_ids),
        deterministic_pending_count=len(deterministic_ids),
        model_required_count=len(model_ids),
        model_calls_planned=len(model_ids) if execute_model else 0,
        execution_document_ids=unattempted_ids,
    )


def _print_scope_summary(summary: ScopeSummary | None) -> None:
    if summary is None:
        return
    for path, size in zip(summary.paths, summary.input_sizes, strict=True):
        print(f"scope: path={path} size={size}")
    print(f"scope overlap: {summary.overlap_count}")
    print(f"scope final unique BOE count: {summary.final_unique_count}")


def _print_extraction_plan(plan: ExtractionPlan) -> None:
    _print_scope_summary(plan.scope_summary)
    print(f"documents total: {plan.total_documents}")
    print(f"compatible existing: {plan.compatible_existing_count}")
    print(f"pending: {plan.pending_document_count}")
    print(f"deterministic pending: {plan.deterministic_pending_count}")
    print(f"model calls required: {plan.model_required_count}")
    print(f"model calls planned: {plan.model_calls_planned}")
    print(f"extraction config: {EXTRACTION_CONFIG_ID}")
    print(f"provider: {MODEL_PROVIDER}")
    print(f"model: {AI_MODEL_NAME}")
    print(f"instructions hash: {INSTRUCTIONS_SHA256}")
    print(f"contract hash: {CONTRACT_SCHEMA_SHA256}")
    print(f"document validation version: {DOCUMENT_VALIDATION_VERSION}")


def run_extraction_stage(
    *,
    documents: Path,
    output_dir: Path,
    expected_extraction_config_id: str,
    attempts: Path | None = None,
    manual_reviews: Path | None = None,
    scope_paths: Sequence[Path] = (),
    execute_model: bool = False,
    dry_run: bool = False,
    checkpoint_every: int = CHECKPOINT_EVERY,
) -> ExtractionStageResult | ExtractionPlan:
    """Reuse compatible attempts and publish selection/review state.

    New AI calls are possible only when ``execute_model`` is true. Existing
    failed or uncertain attempts are routed to review rather than repeated.
    """

    output_dir = _validate_new_output(output_dir)
    plan = build_extraction_plan(
        documents=documents,
        attempts=attempts,
        manual_reviews=manual_reviews,
        scope_paths=scope_paths,
        execute_model=execute_model,
        expected_extraction_config_id=expected_extraction_config_id,
    )
    _print_extraction_plan(plan)
    if dry_run:
        print("DRY RUN: no model/network/write execution performed")
        return plan
    if plan.model_required_count and not execute_model:
        raise ModelPermissionRequired(
            f"{plan.model_required_count} documents require model execution. "
            "Re-run with explicit --execute-model to allow these calls."
        )

    staging_dir, prefix = _staging_directory(output_dir)
    published = False
    try:
        document_path = staging_dir / _EXTRACTION_DOCUMENTS
        attempt_path = staging_dir / _EXTRACTION_ATTEMPTS
        manual_path = staging_dir / _EXTRACTION_MANUAL_REVIEWS
        current_path = staging_dir / _EXTRACTION_CURRENT
        queue_path = staging_dir / _EXTRACTION_REVIEW_QUEUE
        plan.documents.to_parquet(document_path, index=False)
        save_parquet_atomic(plan.attempts, attempt_path)

        if plan.execution_document_ids:
            execution = plan.documents.loc[
                plan.documents["identificador"].astype(str).isin(
                    plan.execution_document_ids
                )
            ].reset_index(drop=True)
            agent = None
            if plan.model_required_count:
                validate_runtime_configuration()
                agent = build_boe_extraction_agent()
                if agent is None:
                    raise PipelineError(
                        "The configured extraction agent could not be built."
                    )
            asyncio.run(extract_documents(
                execution,
                agent=agent,
                attempts_path=attempt_path,
                checkpoint_every=checkpoint_every,
            ))

        all_attempts = load_ai_extraction_attempts(attempt_path)
        current = select_best_valid_extractions(
            attempts=all_attempts,
            source_df=plan.documents,
            manual_reviews=plan.manual_reviews,
        )
        review_queue = build_review_queue(
            attempts=all_attempts,
            source_df=plan.documents,
            manual_reviews=plan.manual_reviews,
        )
        save_parquet_atomic(plan.manual_reviews, manual_path)
        save_parquet_atomic(current, current_path)
        save_parquet_atomic(review_queue, queue_path)
        blocking_count = int(
            review_queue["reason_severity"].eq("blocking").fillna(False).sum()
        )
        manifest = {
            "stage": "extraction",
            "stage_version": PIPELINE_STAGE_VERSION,
            "created_at": _created_at(),
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "model_provider": MODEL_PROVIDER,
            "model_name": AI_MODEL_NAME,
            "instructions_sha256": INSTRUCTIONS_SHA256,
            "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
            "canonicalization_policy": EXTRACTION_CONFIG[
                "canonicalization_policy"
            ],
            "scope_classification_policy": EXTRACTION_CONFIG[
                "scope_classification_policy"
            ],
            "document_validation_version": DOCUMENT_VALIDATION_VERSION,
            "document_identity_sha256": _documents_identity(plan.documents),
            "counts": {
                "documents": len(plan.documents),
                "compatible_existing_before_run": (
                    plan.compatible_existing_count
                ),
                "pending_before_run": plan.pending_document_count,
                "model_calls_planned": plan.model_calls_planned,
                "attempts": len(all_attempts),
                "current_extractions": len(current),
                "blocking_review": blocking_count,
            },
            "artifacts": {
                "documents": _artifact(document_path, plan.documents),
                "attempts": _artifact(attempt_path, all_attempts),
                "manual_reviews": _artifact(
                    manual_path, plan.manual_reviews
                ),
                "current_extractions": _artifact(current_path, current),
                "review_queue": _artifact(queue_path, review_queue),
            },
        }
        manifest_path = staging_dir / _EXTRACTION_MANIFEST
        _write_json(manifest_path, manifest)
        _validate_new_output(output_dir)
        staging_dir.rename(output_dir)
        published = True
    finally:
        if not published:
            _cleanup_staging(staging_dir, output_dir, prefix)

    return ExtractionStageResult(
        output_dir=output_dir,
        documents_path=output_dir / _EXTRACTION_DOCUMENTS,
        attempts_path=output_dir / _EXTRACTION_ATTEMPTS,
        manual_reviews_path=output_dir / _EXTRACTION_MANUAL_REVIEWS,
        current_extractions_path=output_dir / _EXTRACTION_CURRENT,
        review_queue_path=output_dir / _EXTRACTION_REVIEW_QUEUE,
        manifest_path=output_dir / _EXTRACTION_MANIFEST,
        total_documents=plan.total_documents,
        compatible_existing_count=plan.compatible_existing_count,
        pending_document_count=plan.pending_document_count,
        model_calls_planned=plan.model_calls_planned,
        blocking_review_count=blocking_count,
    )


def load_extraction_snapshot(
    snapshot_dir: Path,
    *,
    expected_extraction_config_id: str,
    allow_historical: bool = False,
) -> LoadedExtractionSnapshot:
    """Recompute selection and the blocking queue from a stage snapshot."""

    historical_identity = None
    if allow_historical:
        try:
            historical_identity = historical_recanonicalization_identity(
                expected_extraction_config_id
            )
        except ValueError as error:
            raise PipelineError(
                "Historical extraction configuration is incompatible."
            ) from error
    else:
        _validate_expected_config(expected_extraction_config_id)
    snapshot_dir = Path(snapshot_dir).absolute()
    manifest = _load_json_manifest(snapshot_dir, stage="Extraction")
    if (
        manifest.get("stage") != "extraction"
        or manifest.get("stage_version") != PIPELINE_STAGE_VERSION
        or manifest.get("extraction_config_id")
        != expected_extraction_config_id
    ):
        raise PipelineError("Extraction snapshot metadata is incompatible.")
    if historical_identity is not None and (
        manifest.get("contract_schema_sha256")
        != historical_identity.contract_schema_sha256
        or manifest.get("instructions_sha256")
        != historical_identity.instructions_sha256
        or manifest.get("model_provider")
        != historical_identity.model_provider
        or manifest.get("model_name") != historical_identity.model_name
    ):
        raise PipelineError(
            "Historical extraction snapshot identity is incompatible."
        )
    if not allow_historical and (
        manifest.get("contract_schema_sha256") != CONTRACT_SCHEMA_SHA256
        or manifest.get("instructions_sha256") != INSTRUCTIONS_SHA256
        or manifest.get("document_validation_version")
        != DOCUMENT_VALIDATION_VERSION
    ):
        raise PipelineError("Extraction snapshot provenance is incompatible.")
    expected_files = {
        _EXTRACTION_MANIFEST,
        _EXTRACTION_DOCUMENTS,
        _EXTRACTION_ATTEMPTS,
        _EXTRACTION_MANUAL_REVIEWS,
        _EXTRACTION_CURRENT,
        _EXTRACTION_REVIEW_QUEUE,
    }
    if not snapshot_dir.is_dir() or {
        path.name for path in snapshot_dir.iterdir()
    } != expected_files:
        raise PipelineError("Extraction snapshot has unexpected artifacts.")
    document_path = _verify_artifact(snapshot_dir, manifest, "documents")
    attempt_path = _verify_artifact(snapshot_dir, manifest, "attempts")
    manual_path = _verify_artifact(snapshot_dir, manifest, "manual_reviews")
    current_path = _verify_artifact(
        snapshot_dir, manifest, "current_extractions"
    )
    queue_path = _verify_artifact(snapshot_dir, manifest, "review_queue")
    documents = prepare_documents(pd.read_parquet(document_path))
    attempts = load_ai_extraction_attempts(attempt_path)
    manual = normalise_manual_reviews(pd.read_parquet(manual_path))
    persisted_current = normalise_ai_extraction_attempts_log(
        pd.read_parquet(current_path)
    )
    persisted_queue = pd.read_parquet(queue_path)
    manifest_validation_version = manifest.get("document_validation_version")
    if not isinstance(manifest_validation_version, str):
        raise PipelineError(
            "Extraction manifest has no document validation identity."
        )
    if allow_historical and not manual.empty:
        raise PipelineError(
            "Historical snapshots with manual decisions cannot be replayed "
            "automatically."
        )
    if allow_historical:
        for label, frame in (
            ("attempts", attempts),
            ("current_extractions", persisted_current),
        ):
            if frame.empty:
                continue
            expected_lineage = {
                "extraction_config_id": expected_extraction_config_id,
                "contract_schema_sha256": (
                    historical_identity.contract_schema_sha256
                ),
                "instructions_sha256": (
                    historical_identity.instructions_sha256
                ),
                "model_provider": historical_identity.model_provider,
                "model_name": historical_identity.model_name,
                "document_validation_version": manifest_validation_version,
            }
            for column, expected_value in expected_lineage.items():
                matches = frame[column].astype("string").eq(
                    expected_value
                ).fillna(False)
                if not matches.all():
                    raise PipelineError(
                        f"Historical {label} lineage mismatch: {column}."
                    )
    current = select_best_valid_extractions(
        attempts=attempts,
        source_df=documents,
        manual_reviews=manual,
        expected_extraction_config_id=expected_extraction_config_id,
        expected_document_validation_version=manifest_validation_version,
    )
    queue = build_review_queue(
        attempts=attempts,
        source_df=documents,
        manual_reviews=manual,
        expected_extraction_config_id=expected_extraction_config_id,
        expected_document_validation_version=manifest_validation_version,
    )
    if manifest.get("document_identity_sha256") != _documents_identity(
        documents
    ):
        raise PipelineError("Extraction document identity does not match.")
    if not _frame_equal(
        persisted_current,
        current,
        sort_by=("identificador_boe", "attempt_id"),
    ):
        raise PipelineError("Persisted current selection is not reproducible.")
    if not _frame_equal(
        persisted_queue,
        queue,
        sort_by=("identificador_boe", "review_queue_id"),
        ignore_columns=("queued_at",),
    ):
        raise PipelineError("Persisted review queue is not reproducible.")
    blocking_count = int(
        queue["reason_severity"].eq("blocking").fillna(False).sum()
    )
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping) or (
        counts.get("documents") != len(documents)
        or counts.get("attempts") != len(attempts)
        or counts.get("current_extractions") != len(current)
        or counts.get("blocking_review") != blocking_count
    ):
        raise PipelineError("Extraction manifest counts are inconsistent.")
    return LoadedExtractionSnapshot(
        input_dir=snapshot_dir,
        documents=documents,
        attempts=attempts,
        manual_reviews=manual,
        current_extractions=current,
        review_queue=queue,
        manifest=manifest,
    )


def _extraction_snapshot_identity(
    loaded: LoadedExtractionSnapshot,
) -> str:
    """Return a path-independent identity for a verified extraction snapshot."""

    persisted = loaded.manifest.get("snapshot_identity_sha256")
    if isinstance(persisted, str) and re.fullmatch(r"[0-9a-f]{64}", persisted):
        return persisted
    artifacts = loaded.manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise PipelineError("Extraction snapshot has no artifact identity.")
    artifact_hashes: dict[str, str] = {}
    for name in sorted(artifacts):
        entry = artifacts[name]
        if not isinstance(entry, Mapping) or not isinstance(
            entry.get("sha256"), str
        ):
            raise PipelineError("Extraction artifact identity is incomplete.")
        artifact_hashes[name] = str(entry["sha256"])
    return sha256(_canonical_json_bytes({
        "stage": loaded.manifest.get("stage"),
        "stage_version": loaded.manifest.get("stage_version"),
        "extraction_config_id": loaded.manifest.get("extraction_config_id"),
        "document_identity_sha256": loaded.manifest.get(
            "document_identity_sha256"
        ),
        "artifact_sha256": artifact_hashes,
    })).hexdigest()


def plan_recanonicalization_snapshot(
    *,
    source_snapshot: Path,
    documents: Path | pd.DataFrame,
    output_dir: Path,
    source_expected_extraction_config_id: str,
    target_expected_extraction_config_id: str,
) -> RecanonicalizationPlan:
    """Validate one frozen source and classify its replayable records."""

    output_dir = _validate_new_output(output_dir)
    _validate_expected_config(target_expected_extraction_config_id)
    source_snapshot = Path(source_snapshot).absolute()
    source = load_extraction_snapshot(
        source_snapshot,
        expected_extraction_config_id=(
            source_expected_extraction_config_id
        ),
        allow_historical=True,
    )
    if not source.manual_reviews.empty:
        raise PipelineError(
            "Manual review decisions are not transferred by recanonicalization."
        )
    source_blocking = int(
        source.review_queue["reason_severity"]
        .eq("blocking")
        .fillna(False)
        .sum()
    )
    if source_blocking:
        raise PipelineError(
            "The source extraction snapshot has blocking review records."
        )

    prepared_documents = (
        prepare_documents(documents)
        if isinstance(documents, pd.DataFrame)
        else load_documents_input(Path(documents))
    )
    if _documents_identity(prepared_documents) != _documents_identity(
        source.documents
    ):
        raise PipelineError(
            "Recanonicalization documents do not match the source snapshot."
        )
    if len(source.current_extractions) != len(prepared_documents):
        raise PipelineError(
            "The source snapshot does not contain one current extraction per "
            "document."
        )
    selection_sources = source.current_extractions.get("selection_source")
    if selection_sources is None or not selection_sources.astype(
        "string"
    ).eq("auto_validated").fillna(False).all():
        raise PipelineError(
            "The source snapshot contains non-automatic current selections."
        )
    if source.attempts["attempt_id"].astype("string").duplicated().any():
        raise PipelineError("The source snapshot contains duplicate attempt IDs.")

    source_attempt_ids = set(source.attempts["attempt_id"].astype(str))
    selected_attempt_ids = set(
        source.current_extractions["attempt_id"].astype(str)
    )
    if not selected_attempt_ids.issubset(source_attempt_ids):
        raise PipelineError(
            "A current source extraction has no matching attempt record."
        )
    selected_attempts = source.attempts.loc[
        source.attempts["attempt_id"].astype(str).isin(selected_attempt_ids)
    ].copy()
    if len(selected_attempts) != len(prepared_documents):
        raise PipelineError(
            "The source current selection is not one-to-one with attempts."
        )
    has_precanonical = selected_attempts[
        "precanonical_extraction_json"
    ].notna() & selected_attempts["precanonical_extraction_json"].astype(
        "string"
    ).str.strip().ne("")
    source_run_id = source_snapshot.parent.name
    if not source_run_id:
        raise PipelineError("The source snapshot has no stable run name.")
    return RecanonicalizationPlan(
        source_snapshot=source_snapshot,
        output_dir=output_dir,
        documents=prepared_documents,
        source=source,
        source_run_id=source_run_id,
        source_attempt_count=len(source.attempts),
        precanonical_record_count=int(has_precanonical.sum()),
        deterministic_record_count=int((~has_precanonical).sum()),
        target_record_count=len(selected_attempts),
    )


def _print_recanonicalization_plan(plan: RecanonicalizationPlan) -> None:
    print(f"source records: {plan.source_attempt_count}")
    print(f"precanonical records: {plan.precanonical_record_count}")
    print(f"deterministic records: {plan.deterministic_record_count}")
    print(f"target records: {plan.target_record_count}")
    print(f"model calls: {plan.model_calls}")
    print(f"target extraction config: {EXTRACTION_CONFIG_ID}")
    print(f"output: {plan.output_dir}")


def build_recanonicalized_attempts(
    plan: RecanonicalizationPlan,
    *,
    recanonicalized_at: datetime,
) -> pd.DataFrame:
    """Apply the batch transformation in memory without any stage writes."""

    source_identity = historical_recanonicalization_identity(
        str(plan.source.manifest["extraction_config_id"])
    )
    instant = _normalise_created_at(recanonicalized_at)
    source_attempts = {
        str(row["attempt_id"]): row
        for _, row in plan.source.attempts.iterrows()
    }
    source_current = plan.source.current_extractions.sort_values(
        "identificador_boe", kind="stable"
    )
    documents_by_id = {
        str(row["identificador"]): row
        for _, row in plan.documents.iterrows()
    }
    records: list[dict[str, Any]] = []
    for _, selected in source_current.iterrows():
        boe_id = str(selected["identificador_boe"])
        if boe_id not in documents_by_id:
            raise PipelineError(
                f"Source selection has no matching document: {boe_id}."
            )
        source_attempt = source_attempts[str(selected["attempt_id"])]
        records.append(build_recanonicalized_attempt_record(
            source_attempt,
            document=build_source_document(documents_by_id[boe_id]),
            source_identity=source_identity,
            source_run_id=plan.source_run_id,
            recanonicalized_at=instant,
        ))
    return normalise_ai_extraction_attempts_log(
        pd.DataFrame(records)
    ).sort_values("identificador_boe", kind="stable").reset_index(drop=True)


def recanonicalize_extraction_snapshot(
    *,
    source_snapshot: Path,
    documents: Path | pd.DataFrame,
    output_dir: Path,
    source_expected_extraction_config_id: str,
    target_expected_extraction_config_id: str,
    created_at: datetime | None = None,
) -> RecanonicalizationStageResult:
    """Publish a target snapshot by replaying only deterministic policy code."""

    plan = plan_recanonicalization_snapshot(
        source_snapshot=source_snapshot,
        documents=documents,
        output_dir=output_dir,
        source_expected_extraction_config_id=(
            source_expected_extraction_config_id
        ),
        target_expected_extraction_config_id=(
            target_expected_extraction_config_id
        ),
    )
    _print_recanonicalization_plan(plan)
    instant = _normalise_created_at(created_at)
    source_identity = historical_recanonicalization_identity(
        source_expected_extraction_config_id
    )
    attempts = build_recanonicalized_attempts(
        plan,
        recanonicalized_at=instant,
    )
    manual_reviews = empty_manual_reviews()
    current = select_best_valid_extractions(
        attempts=attempts,
        source_df=plan.documents,
        manual_reviews=manual_reviews,
    )
    review_queue = build_review_queue(
        attempts=attempts,
        source_df=plan.documents,
        manual_reviews=manual_reviews,
    )
    blocking_count = int(
        review_queue["reason_severity"].eq("blocking").fillna(False).sum()
    )

    staging_dir, prefix = _staging_directory(plan.output_dir)
    published = False
    try:
        document_path = staging_dir / _EXTRACTION_DOCUMENTS
        attempt_path = staging_dir / _EXTRACTION_ATTEMPTS
        manual_path = staging_dir / _EXTRACTION_MANUAL_REVIEWS
        current_path = staging_dir / _EXTRACTION_CURRENT
        queue_path = staging_dir / _EXTRACTION_REVIEW_QUEUE
        plan.documents.to_parquet(document_path, index=False)
        save_parquet_atomic(attempts, attempt_path)
        save_parquet_atomic(manual_reviews, manual_path)
        save_parquet_atomic(current, current_path)
        save_parquet_atomic(review_queue, queue_path)

        source_artifacts = plan.source.manifest.get("artifacts")
        if not isinstance(source_artifacts, Mapping):
            raise PipelineError("Source manifest has no artifact lineage.")
        source_attempt_artifact = source_artifacts.get("attempts")
        if not isinstance(source_attempt_artifact, Mapping) or not isinstance(
            source_attempt_artifact.get("sha256"), str
        ):
            raise PipelineError("Source attempt hash lineage is missing.")
        source_manifest_hash = _sha256_file(
            plan.source_snapshot / _EXTRACTION_MANIFEST
        )
        snapshot_identity = sha256(_canonical_json_bytes({
            "document_identity_sha256": _documents_identity(plan.documents),
            "source_manifest_sha256": source_manifest_hash,
            "source_attempts_sha256": source_attempt_artifact["sha256"],
            "source_extraction_config_id": (
                source_identity.extraction_config_id
            ),
            "target_extraction_config_id": EXTRACTION_CONFIG_ID,
        })).hexdigest()
        manifest = {
            "stage": "extraction",
            "stage_version": PIPELINE_STAGE_VERSION,
            "snapshot_type": "recanonicalized_extraction",
            "snapshot_identity_sha256": snapshot_identity,
            "created_at": _format_created_at(instant),
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "model_provider": MODEL_PROVIDER,
            "model_name": AI_MODEL_NAME,
            "instructions_sha256": INSTRUCTIONS_SHA256,
            "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
            "canonicalization_policy": EXTRACTION_CONFIG[
                "canonicalization_policy"
            ],
            "document_validation_version": DOCUMENT_VALIDATION_VERSION,
            "document_identity_sha256": _documents_identity(plan.documents),
            "source": {
                "run_id": plan.source_run_id,
                "snapshot_name": plan.source_snapshot.name,
                "manifest_sha256": source_manifest_hash,
                "attempts_sha256": source_attempt_artifact["sha256"],
                "extraction_config_id": source_identity.extraction_config_id,
                "contract_schema_sha256": (
                    source_identity.contract_schema_sha256
                ),
                "instructions_sha256": source_identity.instructions_sha256,
                "canonicalization_policy": (
                    source_identity.canonicalization_policy
                ),
                "model_provider": source_identity.model_provider,
                "model_name": source_identity.model_name,
            },
            "target": {
                "extraction_config_id": EXTRACTION_CONFIG_ID,
                "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
                "instructions_sha256": INSTRUCTIONS_SHA256,
                "canonicalization_policy": EXTRACTION_CONFIG[
                    "canonicalization_policy"
                ],
            },
            "counts": {
                "documents": len(plan.documents),
                "source_attempts": plan.source_attempt_count,
                "precanonical_recanonicalized": (
                    plan.precanonical_record_count
                ),
                "deterministic_preserved": plan.deterministic_record_count,
                "model_calls": 0,
                "attempts": len(attempts),
                "current_extractions": len(current),
                "blocking_review": blocking_count,
            },
            "artifacts": {
                "documents": _artifact(document_path, plan.documents),
                "attempts": _artifact(attempt_path, attempts),
                "manual_reviews": _artifact(
                    manual_path, manual_reviews
                ),
                "current_extractions": _artifact(current_path, current),
                "review_queue": _artifact(queue_path, review_queue),
            },
        }
        manifest_path = staging_dir / _EXTRACTION_MANIFEST
        _write_json(manifest_path, manifest)
        load_extraction_snapshot(
            staging_dir,
            expected_extraction_config_id=target_expected_extraction_config_id,
        )
        _validate_new_output(plan.output_dir)
        staging_dir.rename(plan.output_dir)
        published = True
    finally:
        if not published:
            _cleanup_staging(staging_dir, plan.output_dir, prefix)

    return RecanonicalizationStageResult(
        output_dir=plan.output_dir,
        documents_path=plan.output_dir / _EXTRACTION_DOCUMENTS,
        attempts_path=plan.output_dir / _EXTRACTION_ATTEMPTS,
        manual_reviews_path=plan.output_dir / _EXTRACTION_MANUAL_REVIEWS,
        current_extractions_path=plan.output_dir / _EXTRACTION_CURRENT,
        review_queue_path=plan.output_dir / _EXTRACTION_REVIEW_QUEUE,
        manifest_path=plan.output_dir / _EXTRACTION_MANIFEST,
        total_documents=len(plan.documents),
        compatible_existing_count=0,
        pending_document_count=0,
        model_calls_planned=0,
        blocking_review_count=blocking_count,
        source_attempt_count=plan.source_attempt_count,
        precanonical_record_count=plan.precanonical_record_count,
        deterministic_record_count=plan.deterministic_record_count,
        model_calls=0,
    )


def run_silver_stage(
    *,
    extraction_snapshot: Path,
    output_dir: Path,
    expected_extraction_config_id: str,
    corrections: Path | None = None,
    dry_run: bool = False,
) -> FlatMaterializationResult | LoadedExtractionSnapshot:
    """Publish Silver only after recomputing a zero-blocker review gate."""

    output_dir = _validate_new_output(output_dir)
    loaded = load_extraction_snapshot(
        extraction_snapshot,
        expected_extraction_config_id=expected_extraction_config_id,
    )
    blocking_count = int(
        loaded.review_queue["reason_severity"]
        .eq("blocking")
        .fillna(False)
        .sum()
    )
    if blocking_count:
        raise ReviewRequired(
            f"{blocking_count} documents require blocking human review."
        )
    print(
        f"silver: current={len(loaded.current_extractions)} "
        f"output={output_dir}"
    )
    loaded_corrections = (
        load_administrative_action_corrections(corrections)
        if corrections is not None
        else None
    )
    if loaded_corrections is not None:
        print(
            "silver corrections: "
            f"approved={len(loaded_corrections.corrections)} "
            f"identity={loaded_corrections.semantic_identity}"
        )
    if dry_run:
        if loaded_corrections is not None:
            correction_application = apply_administrative_action_corrections(
                loaded.current_extractions,
                loaded_corrections,
                source_extraction_snapshot_id=(
                    _extraction_snapshot_identity(loaded)
                ),
            )
            validate_flat_tables(flatten_current_extractions(
                correction_application.effective_current_extractions
            ))
        print("DRY RUN: Silver was not materialized")
        return loaded
    return materialize_current_extractions(
        loaded.current_extractions,
        output_dir=output_dir,
        expected_extraction_config_id=expected_extraction_config_id,
        corrections=loaded_corrections,
        source_extraction_snapshot_id=(
            _extraction_snapshot_identity(loaded)
            if loaded_corrections is not None
            else None
        ),
    )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def _add_expected_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-extraction-config-id", required=True)


def _add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m renewables_permitting.pipeline",
        description="Run the reproducible BOE permitting pipeline by stage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    source = subparsers.add_parser("source", help="BOE API to documents")
    source.add_argument("--start-date", type=_parse_date, required=True)
    source.add_argument("--end-date", type=_parse_date, required=True)
    source.add_argument("--output-dir", type=Path, required=True)
    _add_dry_run(source)

    extract = subparsers.add_parser("extract", help="documents to selection")
    extract.add_argument("--documents", type=Path, required=True)
    extract.add_argument("--output-dir", type=Path, required=True)
    extract.add_argument("--attempts", type=Path)
    extract.add_argument("--manual-reviews", type=Path)
    extract.add_argument("--scope", type=Path, action="append", default=[])
    extract.add_argument("--execute-model", action="store_true")
    _add_expected_config(extract)
    _add_dry_run(extract)

    recanonicalize = subparsers.add_parser(
        "recanonicalize",
        help="replay a frozen extraction snapshot without model calls",
    )
    recanonicalize.add_argument(
        "--source-extraction-snapshot", type=Path, required=True
    )
    recanonicalize.add_argument("--documents", type=Path, required=True)
    recanonicalize.add_argument("--output-dir", type=Path, required=True)
    recanonicalize.add_argument(
        "--source-expected-extraction-config-id", required=True
    )
    recanonicalize.add_argument(
        "--target-expected-extraction-config-id", required=True
    )
    _add_dry_run(recanonicalize)

    silver = subparsers.add_parser("silver", help="selection to Silver")
    silver.add_argument("--extraction-snapshot", type=Path, required=True)
    silver.add_argument("--output-dir", type=Path, required=True)
    silver.add_argument(
        "--corrections",
        type=Path,
        help="explicit approved administrative-action corrections CSV",
    )
    _add_expected_config(silver)
    _add_dry_run(silver)

    downstream = subparsers.add_parser(
        "downstream", help="Silver and INE to Gold"
    )
    downstream.add_argument("--silver-snapshot", type=Path, required=True)
    downstream.add_argument(
        "--municipality-reference", type=Path, required=True
    )
    downstream.add_argument("--output-dir", type=Path, required=True)
    _add_expected_config(downstream)
    _add_dry_run(downstream)

    build_reference = subparsers.add_parser(
        "build-reference-data", help="build a candidate INE snapshot"
    )
    build_reference.add_argument("--codine", type=Path, required=True)
    build_reference.add_argument("--dictionary", type=Path, required=True)
    build_reference.add_argument("--output-dir", type=Path, required=True)
    _add_dry_run(build_reference)

    refresh = subparsers.add_parser(
        "refresh-reference-data",
        help="compare INE and confirm a full downstream rebuild",
    )
    refresh.add_argument("--codine", type=Path, required=True)
    refresh.add_argument("--dictionary", type=Path, required=True)
    refresh.add_argument("--current-reference", type=Path, required=True)
    refresh.add_argument(
        "--candidate-reference-output", type=Path, required=True
    )
    refresh.add_argument("--silver-snapshot", type=Path, required=True)
    refresh.add_argument("--downstream-output", type=Path, required=True)
    refresh.add_argument("--yes", action="store_true")
    _add_expected_config(refresh)
    _add_dry_run(refresh)

    run = subparsers.add_parser("run", help="orchestrate all pipeline stages")
    run.add_argument("--documents", type=Path)
    run.add_argument("--start-date", type=_parse_date)
    run.add_argument("--end-date", type=_parse_date)
    run.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run.add_argument("--run-id")
    run.add_argument("--attempts", type=Path)
    run.add_argument("--manual-reviews", type=Path)
    run.add_argument("--scope", type=Path, action="append", default=[])
    run.add_argument("--execute-model", action="store_true")
    run.add_argument(
        "--municipality-reference", type=Path, required=True
    )
    _add_expected_config(run)
    _add_dry_run(run)
    return parser


def _build_reference(
    *,
    codine_path: Path,
    dictionary_path: Path,
) -> pd.DataFrame:
    codine, dictionary = load_ine_source_tables(
        codine_path,
        dictionary_path,
    )
    return build_municipality_dimension(codine, dictionary)


def _handle_source(args: argparse.Namespace) -> int:
    result = run_source_stage(
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    if result is not None:
        print(
            f"source complete: documents={result.document_count} "
            f"path={result.documents_path}"
        )
    return EXIT_SUCCESS


def _handle_extract(args: argparse.Namespace) -> int:
    result = run_extraction_stage(
        documents=args.documents,
        attempts=args.attempts,
        manual_reviews=args.manual_reviews,
        scope_paths=args.scope,
        output_dir=args.output_dir,
        expected_extraction_config_id=args.expected_extraction_config_id,
        execute_model=args.execute_model,
        dry_run=args.dry_run,
    )
    if isinstance(result, ExtractionStageResult):
        print(
            f"extraction complete: output={result.output_dir} "
            f"blocking_review={result.blocking_review_count}"
        )
        if result.blocking_review_count:
            return EXIT_REVIEW_REQUIRED
    return EXIT_SUCCESS


def _handle_recanonicalize(args: argparse.Namespace) -> int:
    arguments = {
        "source_snapshot": args.source_extraction_snapshot,
        "documents": args.documents,
        "output_dir": args.output_dir,
        "source_expected_extraction_config_id": (
            args.source_expected_extraction_config_id
        ),
        "target_expected_extraction_config_id": (
            args.target_expected_extraction_config_id
        ),
    }
    if args.dry_run:
        plan = plan_recanonicalization_snapshot(**arguments)
        _print_recanonicalization_plan(plan)
        print("DRY RUN: no model/network/write execution performed")
        return EXIT_SUCCESS
    result = recanonicalize_extraction_snapshot(**arguments)
    print(
        f"recanonicalization complete: output={result.output_dir} "
        f"blocking_review={result.blocking_review_count}"
    )
    return (
        EXIT_REVIEW_REQUIRED
        if result.blocking_review_count
        else EXIT_SUCCESS
    )


def _handle_silver(args: argparse.Namespace) -> int:
    result = run_silver_stage(
        extraction_snapshot=args.extraction_snapshot,
        output_dir=args.output_dir,
        expected_extraction_config_id=args.expected_extraction_config_id,
        corrections=args.corrections,
        dry_run=args.dry_run,
    )
    if isinstance(result, FlatMaterializationResult):
        print(
            f"Silver complete: id={result.materialization_id} "
            f"path={result.output_dir}"
        )
    return EXIT_SUCCESS


def _handle_downstream(args: argparse.Namespace) -> int:
    _validate_expected_config(args.expected_extraction_config_id)
    _validate_new_output(args.output_dir)
    if args.dry_run:
        silver = load_flat_materialization(
            args.silver_snapshot,
            expected_extraction_config_id=args.expected_extraction_config_id,
        )
        reference = load_municipality_reference(
            args.municipality_reference
        )
        print(f"Silver materialization: {silver.materialization_id}")
        print(f"INE reference: {reference.semantic_reference_id}")
        print(f"downstream target: {args.output_dir}")
        print("DRY RUN: downstream was not executed")
        return EXIT_SUCCESS
    result = run_downstream(
        silver_snapshot=args.silver_snapshot,
        municipality_reference=args.municipality_reference,
        output_dir=args.output_dir,
        expected_extraction_config_id=args.expected_extraction_config_id,
    )
    print(
        f"downstream complete: id={result.materialization_id} "
        f"path={args.output_dir}"
    )
    return EXIT_SUCCESS


def _handle_build_reference(args: argparse.Namespace) -> int:
    output_dir = _validate_new_output(args.output_dir)
    dimension = _build_reference(
        codine_path=args.codine,
        dictionary_path=args.dictionary,
    )
    semantic_hash = compute_municipality_reference_hash(dimension)
    print(f"INE rows: {len(dimension)}")
    print(f"INE semantic reference ID: {semantic_hash[:16]}")
    print(f"reference target: {output_dir}")
    if args.dry_run:
        print("DRY RUN: reference data was not materialized")
        return EXIT_SUCCESS
    result = materialize_municipality_dimension(
        dimension,
        output_dir=output_dir,
        codine_source_path=args.codine,
        dictionary_source_path=args.dictionary,
    )
    print(f"reference complete: {result.semantic_reference_id}")
    return EXIT_SUCCESS


def _refresh_warning(
    *,
    old_id: str,
    new_id: str,
    added: int,
    removed: int,
    changed: int,
    silver_snapshot: Path,
) -> None:
    print("The INE reference contains semantic changes.")
    print(f"old INE reference ID: {old_id}")
    print(f"new INE reference ID: {new_id}")
    print(f"added: {added}; removed: {removed}; changed: {changed}")
    print(f"Silver snapshot: {silver_snapshot}")
    print()
    print("This will rebuild, for the full historical Silver snapshot:")
    print("- location resolution")
    print("- project grouping")
    print("- Gold")
    print()
    print("It will NOT call the AI model or regenerate Silver.")


def _handle_refresh_reference(args: argparse.Namespace) -> int:
    _validate_expected_config(args.expected_extraction_config_id)
    candidate = _build_reference(
        codine_path=args.codine,
        dictionary_path=args.dictionary,
    )
    current = load_municipality_reference(args.current_reference)
    comparison = compare_municipality_dimensions(
        current.dimension,
        candidate,
    )
    if not comparison.semantic_changed:
        print("No semantic INE changes.")
        print("Downstream rebuild not required.")
        return EXIT_SUCCESS

    load_flat_materialization(
        args.silver_snapshot,
        expected_extraction_config_id=args.expected_extraction_config_id,
    )
    candidate_output = _validate_new_output(
        args.candidate_reference_output
    )
    _validate_new_output(args.downstream_output)
    _refresh_warning(
        old_id=comparison.old_reference_id,
        new_id=comparison.new_reference_id,
        added=len(comparison.added_codes),
        removed=len(comparison.removed_codes),
        changed=len(comparison.changed_codes),
        silver_snapshot=args.silver_snapshot,
    )
    if args.dry_run:
        print("DRY RUN: no reference or downstream snapshot was written")
        return EXIT_SUCCESS
    confirmed = bool(args.yes)
    if not confirmed:
        try:
            confirmed = input("Continue? [y/N] ").strip().casefold() in {
                "y", "yes"
            }
        except EOFError:
            confirmed = False
    if not confirmed:
        print("INE downstream rebuild declined; no output was written.")
        return EXIT_SUCCESS

    reference = materialize_municipality_dimension(
        candidate,
        output_dir=candidate_output,
        codine_source_path=args.codine,
        dictionary_source_path=args.dictionary,
    )
    result = run_downstream(
        silver_snapshot=args.silver_snapshot,
        municipality_reference=reference.output_dir,
        output_dir=args.downstream_output,
        expected_extraction_config_id=args.expected_extraction_config_id,
    )
    print(f"downstream complete: id={result.materialization_id}")
    return EXIT_SUCCESS


def _run_id(value: str | None) -> str:
    if value is None:
        return (
            _utc_now().strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid4().hex[:8]
        )
    if not _RUN_ID_PATTERN.fullmatch(value):
        raise PipelineError(
            "run_id must contain only letters, numbers, dot, underscore or dash."
        )
    return value


def _validate_run_source_args(args: argparse.Namespace) -> None:
    has_documents = args.documents is not None
    has_start = args.start_date is not None
    has_end = args.end_date is not None
    if has_documents and (has_start or has_end):
        raise PipelineError(
            "run accepts either --documents or a date range, not both."
        )
    if not has_documents and not (has_start and has_end):
        raise PipelineError(
            "run requires --documents or both --start-date and --end-date."
        )


def _handle_run(args: argparse.Namespace) -> int:
    _validate_expected_config(args.expected_extraction_config_id)
    _validate_run_source_args(args)
    run_id = _run_id(args.run_id)
    run_root = _validate_new_output(Path(args.runs_dir) / run_id)
    reference = load_municipality_reference(args.municipality_reference)
    print(f"run_id: {run_id}")
    print(f"INE reference: {reference.semantic_reference_id}")
    print(f"run root: {run_root}")

    if args.dry_run and args.documents is None:
        print(
            f"source plan: {args.start_date}..{args.end_date}; "
            "document counts unavailable without BOE access"
        )
        print(f"Silver target: {run_root / 'silver'}")
        print(f"downstream target: {run_root / 'downstream'}")
        print("DRY RUN: no model/network/write execution performed")
        return EXIT_SUCCESS

    document_input = args.documents
    if args.documents is None:
        source = run_source_stage(
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=run_root / "source",
        )
        if source is None:
            raise PipelineError("Source stage did not return a snapshot.")
        document_input = source.documents_path

    if args.dry_run:
        plan = build_extraction_plan(
            documents=document_input,
            attempts=args.attempts,
            manual_reviews=args.manual_reviews,
            scope_paths=args.scope,
            execute_model=args.execute_model,
            expected_extraction_config_id=args.expected_extraction_config_id,
        )
        _print_extraction_plan(plan)
        print(f"Silver target: {run_root / 'silver'}")
        print(f"downstream target: {run_root / 'downstream'}")
        print("DRY RUN: no model/network/write execution performed")
        return EXIT_SUCCESS

    extraction = run_extraction_stage(
        documents=document_input,
        attempts=args.attempts,
        manual_reviews=args.manual_reviews,
        scope_paths=args.scope,
        output_dir=run_root / "extraction",
        expected_extraction_config_id=args.expected_extraction_config_id,
        execute_model=args.execute_model,
    )
    if not isinstance(extraction, ExtractionStageResult):
        raise PipelineError("Extraction stage did not publish a snapshot.")
    if extraction.blocking_review_count:
        print(
            f"REVIEW REQUIRED: {extraction.blocking_review_count} documents. "
            f"Queue: {extraction.review_queue_path}"
        )
        return EXIT_REVIEW_REQUIRED

    silver = run_silver_stage(
        extraction_snapshot=extraction.output_dir,
        output_dir=run_root / "silver",
        expected_extraction_config_id=args.expected_extraction_config_id,
    )
    if not isinstance(silver, FlatMaterializationResult):
        raise PipelineError("Silver stage did not publish a snapshot.")
    downstream = run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=args.municipality_reference,
        output_dir=run_root / "downstream",
        expected_extraction_config_id=args.expected_extraction_config_id,
    )
    _write_json(run_root / "run_manifest.json", {
        "run_id": run_id,
        "created_at": _created_at(),
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "source_mode": (
            "existing_documents" if args.documents is not None else "boe_source"
        ),
        "documents": str(document_input),
        "extraction_snapshot": str(extraction.output_dir),
        "silver_materialization_id": silver.materialization_id,
        "ine_reference_id": reference.semantic_reference_id,
        "downstream_materialization_id": downstream.materialization_id,
    })
    print(
        f"run complete: silver={silver.materialization_id} "
        f"downstream={downstream.materialization_id}"
    )
    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the stage-oriented command line without implicit network/AI."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "source": _handle_source,
        "extract": _handle_extract,
        "recanonicalize": _handle_recanonicalize,
        "silver": _handle_silver,
        "downstream": _handle_downstream,
        "build-reference-data": _handle_build_reference,
        "refresh-reference-data": _handle_refresh_reference,
        "run": _handle_run,
    }
    try:
        return handlers[args.command](args)
    except ModelPermissionRequired as error:
        print(str(error), file=sys.stderr)
        return EXIT_MODEL_PERMISSION_REQUIRED
    except ReviewRequired as error:
        print(str(error), file=sys.stderr)
        return EXIT_REVIEW_REQUIRED
    except (
        PipelineError,
        DownstreamError,
        FlatMaterializationError,
        FileExistsError,
        FileNotFoundError,
        ValueError,
    ) as error:
        print(f"pipeline failed: {error}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
