from __future__ import annotations

from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
)
from renewables_permitting.extraction.models import (
    BOEProjectExtraction,
    BOESourceDocument,
)
from renewables_permitting.extraction.validation import (
    validate_extraction_against_document,
)


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
