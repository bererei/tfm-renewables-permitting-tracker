from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
)
from renewables_permitting.extraction.config import (
    CONTRACT_SCHEMA_SHA256,
    EXTRACTION_CONFIG,
    EXTRACTION_CONFIG_ID,
)
from renewables_permitting.extraction.models import (
    BOEProjectExtraction,
    BOESourceDocument,
)
from renewables_permitting.extraction.validation import (
    validate_extraction_against_document,
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
