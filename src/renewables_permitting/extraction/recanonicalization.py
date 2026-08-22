from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd

from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
    preclassify_document_without_model,
)
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.models import (
    BOEProjectExtraction,
    BOESourceDocument,
)
from renewables_permitting.extraction.validation import (
    validate_extraction_against_document,
)
from renewables_permitting.extraction.review import (
    _count_extracted_nodes,
    normalise_ai_extraction_attempts_log,
)


@dataclass(frozen=True)
class HistoricalExtractionIdentity:
    """One explicitly supported frozen extraction identity."""

    extraction_config_id: str
    contract_schema_sha256: str
    instructions_sha256: str
    canonicalization_policy: str
    model_provider: str
    model_name: str


_FREEZE_SOURCE_IDENTITY = HistoricalExtractionIdentity(
    extraction_config_id="67a0bd9d0759a322",
    contract_schema_sha256=(
        "455028c7de0ada067264cd695b4e7dab9de377b31105e141321313d61c3ff283"
    ),
    instructions_sha256=(
        "b48240832d1b274af0435cea42cc6d305d2aec83b5a3395a1d5ce1529eff0607"
    ),
    canonicalization_policy=(
        "termination_object_filter_environmental_terminal_whitelist_"
        "lexical_authorization_grants_v2_"
        "explicit_relation_validation_conservative_grouping_v1"
    ),
    model_provider="gemini",
    model_name="google:gemini-2.5-flash",
)

SUPPORTED_RECANONICALIZATION_SOURCE_IDENTITIES = MappingProxyType({
    _FREEZE_SOURCE_IDENTITY.extraction_config_id: _FREEZE_SOURCE_IDENTITY,
})

RECANONICALIZATION_MATERIALIZATION_VERSION = "2"
_DETERMINISTIC_CODE_FILENAMES = (
    "canonicalization.py",
    "recanonicalization.py",
    "validation.py",
)


@dataclass(frozen=True)
class RecanonicalizationResult:
    """Canonical derivation plus explicit source and active-policy lineage."""

    extraction: BOEProjectExtraction
    adjustments: tuple[str, ...]
    source_attempt_id: str
    source_extraction_config_id: str
    source_contract_schema_sha256: str
    source_instructions_sha256: str
    source_model_provider: str
    source_model_name: str
    source_document_sha256: str
    extraction_config_id: str
    contract_schema_sha256: str
    canonicalization_policy: str


def _required_attempt_text(
    source_attempt: Mapping[str, Any],
    field_name: str,
) -> str:
    value = source_attempt.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"El intento de origen no contiene {field_name!r}."
        )
    return value


def recanonicalize_precanonical_extraction(
    precanonical_extraction_json: str,
    *,
    document: BOESourceDocument,
) -> tuple[BOEProjectExtraction, list[str]]:
    """Reaplica la política vigente al input Pydantic pre-canónico.

    El JSON contiene la salida estructurada del modelo con el sobre
    determinista de BOE y fecha que añade ``build_boe_project_extraction``.
    No es el payload HTTP original del proveedor.
    """

    if (
        not isinstance(precanonical_extraction_json, str)
        or not precanonical_extraction_json.strip()
    ):
        raise ValueError(
            "El intento no dispone de precanonical_extraction_json."
        )
    extraction = BOEProjectExtraction.model_validate_json(
        precanonical_extraction_json
    )
    if (
        extraction.boe_id != document.boe_id
        or extraction.publication_date != document.publication_date
    ):
        raise ValueError(
            "La extracción pre-canónica no corresponde al documento fuente."
        )
    canonical, adjustments = canonicalize_project_extraction(
        extraction,
        source_text=f"{document.title}\n{document.text}",
        document_title=document.title,
    )
    validate_extraction_against_document(
        document=document,
        extraction=canonical,
    )
    return canonical, adjustments


def recanonicalize_attempt_with_provenance(
    source_attempt: Mapping[str, Any],
    *,
    document: BOESourceDocument,
) -> RecanonicalizationResult:
    """Deriva un canonical nuevo sin mutar ni reetiquetar el attempt original."""

    source_document_sha256 = _required_attempt_text(
        source_attempt,
        "source_document_sha256",
    )
    if source_document_sha256 != document.source_document_sha256:
        raise ValueError(
            "El intento de origen no corresponde al hash del documento fuente."
        )
    canonical, adjustments = recanonicalize_precanonical_extraction(
        _required_attempt_text(
            source_attempt,
            "precanonical_extraction_json",
        ),
        document=document,
    )
    return RecanonicalizationResult(
        extraction=canonical,
        adjustments=tuple(adjustments),
        source_attempt_id=_required_attempt_text(source_attempt, "attempt_id"),
        source_extraction_config_id=_required_attempt_text(
            source_attempt,
            "extraction_config_id",
        ),
        source_contract_schema_sha256=_required_attempt_text(
            source_attempt,
            "contract_schema_sha256",
        ),
        source_instructions_sha256=_required_attempt_text(
            source_attempt,
            "instructions_sha256",
        ),
        source_model_provider=_required_attempt_text(
            source_attempt,
            "model_provider",
        ),
        source_model_name=_required_attempt_text(
            source_attempt,
            "model_name",
        ),
        source_document_sha256=source_document_sha256,
        extraction_config_id=EXTRACTION_CONFIG_ID,
        contract_schema_sha256=CONTRACT_SCHEMA_SHA256,
        canonicalization_policy=str(
            EXTRACTION_CONFIG["canonicalization_policy"]
        ),
    )


def historical_recanonicalization_identity(
    extraction_config_id: str,
) -> HistoricalExtractionIdentity:
    """Resolve only frozen source identities explicitly approved for replay."""

    try:
        return SUPPORTED_RECANONICALIZATION_SOURCE_IDENTITIES[
            extraction_config_id
        ]
    except KeyError as error:
        raise ValueError(
            "La configuración histórica no está aprobada para "
            f"recanonicalización: {extraction_config_id!r}."
        ) from error


def active_recanonicalization_identity() -> HistoricalExtractionIdentity:
    """Return the installed identity for an active cumulative replay."""

    return HistoricalExtractionIdentity(
        extraction_config_id=EXTRACTION_CONFIG_ID,
        contract_schema_sha256=CONTRACT_SCHEMA_SHA256,
        instructions_sha256=INSTRUCTIONS_SHA256,
        canonicalization_policy=str(
            EXTRACTION_CONFIG["canonicalization_policy"]
        ),
        model_provider=MODEL_PROVIDER,
        model_name=AI_MODEL_NAME,
    )


def deterministic_recanonicalization_code_sha256() -> str:
    """Fingerprint the exact deterministic implementation used for replay."""

    module_dir = Path(__file__).resolve().parent
    digest = sha256()
    for filename in _DETERMINISTIC_CODE_FILENAMES:
        path = module_dir / filename
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(
                f"No se puede identificar el código determinista: {path}."
            )
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _recanonicalized_attempt_id(
    *,
    source_attempt_id: str,
    source_document_sha256: str,
    deterministic_code_sha256: str,
) -> str:
    identity = (
        f"recanonicalized-attempt-v{RECANONICALIZATION_MATERIALIZATION_VERSION}|"
        f"{source_attempt_id}|{source_document_sha256}|{EXTRACTION_CONFIG_ID}|"
        f"{deterministic_code_sha256}"
    )
    return sha256(identity.encode("utf-8")).hexdigest()[:32]


def build_recanonicalized_attempt_record(
    source_attempt: Mapping[str, Any],
    *,
    document: BOESourceDocument,
    source_identity: HistoricalExtractionIdentity,
    source_run_id: str,
    recanonicalized_at: datetime,
    preserve_source_usage: bool = True,
    deterministic_code_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one target attempt without issuing or impersonating an AI call."""

    source_attempt_id = _required_attempt_text(source_attempt, "attempt_id")
    source_config_id = _required_attempt_text(
        source_attempt, "extraction_config_id"
    )
    if source_config_id != source_identity.extraction_config_id:
        raise ValueError(
            "El intento de origen no coincide con la identidad histórica."
        )
    if _required_attempt_text(
        source_attempt, "contract_schema_sha256"
    ) != source_identity.contract_schema_sha256:
        raise ValueError(
            "El contrato del intento no coincide con la identidad histórica."
        )
    if _required_attempt_text(
        source_attempt, "instructions_sha256"
    ) != source_identity.instructions_sha256:
        raise ValueError(
            "Las instrucciones del intento no coinciden con la identidad "
            "histórica."
        )
    if _required_attempt_text(
        source_attempt, "source_document_sha256"
    ) != document.source_document_sha256:
        raise ValueError(
            "El intento de origen no corresponde al documento fuente."
        )

    precanonical_json = source_attempt.get("precanonical_extraction_json")
    if _is_missing(precanonical_json):
        extraction, adjustments = preclassify_document_without_model(document)
        if extraction is None:
            raise ValueError(
                "Un intento sin payload pre-canónico no puede reproducirse "
                "por la vía determinista vigente."
            )
        source_extraction = BOEProjectExtraction.model_validate_json(
            _required_attempt_text(source_attempt, "extraction_json")
        )
        if source_extraction != extraction:
            raise ValueError(
                "La extracción determinista histórica cambió semánticamente."
            )
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )
        attempt_origin = "deterministic_reissued"
        source_model_provider: Any = pd.NA
        source_model_name: Any = pd.NA
        model_provider: Any = pd.NA
        model_name: Any = pd.NA
        processing_stage = "deterministic_scope_guard"
    else:
        if _required_attempt_text(
            source_attempt, "model_provider"
        ) != source_identity.model_provider:
            raise ValueError(
                "El proveedor del intento no coincide con la identidad fuente."
            )
        if _required_attempt_text(
            source_attempt, "model_name"
        ) != source_identity.model_name:
            raise ValueError(
                "El modelo del intento no coincide con la identidad fuente."
            )
        result = recanonicalize_attempt_with_provenance(
            source_attempt,
            document=document,
        )
        extraction = result.extraction
        adjustments = list(result.adjustments)
        attempt_origin = "recanonicalized"
        source_model_provider = result.source_model_provider
        source_model_name = result.source_model_name
        model_provider = result.source_model_provider
        model_name = result.source_model_name
        processing_stage = "recanonicalized"

    instant = recanonicalized_at
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("recanonicalized_at debe incluir zona horaria.")
    instant = instant.astimezone(timezone.utc)
    counts = _count_extracted_nodes(extraction)
    code_sha256 = (
        deterministic_recanonicalization_code_sha256()
        if deterministic_code_sha256 is None
        else deterministic_code_sha256
    )
    if not isinstance(code_sha256, str) or len(code_sha256) != 64:
        raise ValueError("deterministic_code_sha256 no es una huella SHA-256.")
    record = dict(source_attempt)
    record.update({
        "attempt_id": _recanonicalized_attempt_id(
            source_attempt_id=source_attempt_id,
            source_document_sha256=document.source_document_sha256,
            deterministic_code_sha256=code_sha256,
        ),
        "attempt_origin": attempt_origin,
        "source_attempt_id": source_attempt_id,
        "source_extraction_config_id": source_identity.extraction_config_id,
        "source_contract_schema_sha256": (
            source_identity.contract_schema_sha256
        ),
        "source_instructions_sha256": source_identity.instructions_sha256,
        "source_canonicalization_policy": (
            source_identity.canonicalization_policy
        ),
        "source_model_provider": source_model_provider,
        "source_model_name": source_model_name,
        "target_canonicalization_policy": EXTRACTION_CONFIG[
            "canonicalization_policy"
        ],
        "recanonicalized_at": instant,
        "recanonicalization_source_run": source_run_id,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": model_provider,
        "model_name": model_name,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "classification_status": extraction.classification_status.value,
        "document_scope": (
            extraction.document_scope.value
            if extraction.document_scope is not None
            else None
        ),
        "classification_reason": extraction.classification_reason,
        **counts,
        "extraction_json": extraction.model_dump_json(),
        "extracted_at": instant,
        "duration_seconds": (
            source_attempt.get("duration_seconds")
            if preserve_source_usage
            else 0.0
        ),
        "usage_requests": (
            source_attempt.get("usage_requests")
            if preserve_source_usage
            else 0
        ),
        "usage_input_tokens": (
            source_attempt.get("usage_input_tokens")
            if preserve_source_usage
            else 0
        ),
        "usage_output_tokens": (
            source_attempt.get("usage_output_tokens")
            if preserve_source_usage
            else 0
        ),
        "usage_total_tokens": (
            source_attempt.get("usage_total_tokens")
            if preserve_source_usage
            else 0
        ),
        "extraction_status": "ok",
        "error_type": None,
        "error_message": None,
        "processing_stage": processing_stage,
        "document_validation_status": "passed",
        "document_validation_issue_count": 0,
        "validation_issues_json": None,
        "deterministic_adjustment_count": len(adjustments),
        "deterministic_adjustments_json": (
            json.dumps(adjustments, ensure_ascii=False)
            if adjustments
            else None
        ),
    })
    return normalise_ai_extraction_attempts_log(
        pd.DataFrame([record])
    ).iloc[0].to_dict()
