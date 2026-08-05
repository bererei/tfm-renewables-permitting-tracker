from datetime import date
from hashlib import sha256
from inspect import signature

from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
    preclassify_document_without_model,
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
    TechnicalMention,
)


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
    technical_mentions: list[TechnicalMention] | None = None,
) -> GenerationAssetMention:
    return GenerationAssetMention(
        local_generation_asset_ref=ref,
        names_raw=[name],
        generation_type=generation_type,
        technical_mentions=technical_mentions or [],
        evidence=evidence,
    )


def _action(
    action_type: AdministrativeActionType,
    decision: AdministrativeDecision,
    evidence: str,
    targets: list[str] | None = None,
    *,
    is_modification: bool = False,
) -> AdministrativeAction:
    return AdministrativeAction(
        action_type=action_type,
        decision=decision,
        is_modification=is_modification,
        targets=targets or [],
        evidence=evidence,
    )


def test_descriptive_irrigation_project_is_not_generation_project() -> None:
    title = (
        "Resolución por la que se somete a información pública el Proyecto de "
        "«Implementación de energías renovables mediante paneles fotovoltaicos "
        "flotantes en la Comunidad de Regantes de Balazote - La Herrera»."
    )
    document = _test_document("BOE-B-2022-40999", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                (
                    "Implementación de energías renovables mediante paneles "
                    "fotovoltaicos flotantes en la Comunidad de Regantes de "
                    "Balazote - La Herrera"
                ),
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PUBLIC_INFORMATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                title,
            )],
            event_summary="Información pública de una obra de regadío.",
        )],
    )
    canonical, _ = canonicalize_project_extraction(
        extraction,
        source_text=title,
        document_title=title,
    )
    assert canonical.document_scope == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    assert canonical.publication_events == []


def test_contract_procurement_is_not_generation_project() -> None:
    title = (
        "Anuncio de formalización de contratos. Objeto: Contratación del "
        "suministro e instalación de placas fotovoltaicas para autoconsumo "
        "en el edificio sede."
    )
    document = _test_document("BOE-B-2022-40990", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "placas fotovoltaicas para autoconsumo en el edificio sede",
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            associated_components=[],
            administrative_actions=[_action(
                AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
                ["event"],
            )],
            event_summary="Instalación de placas en un edificio.",
        )],
    )
    canonical, adjustments = canonicalize_project_extraction(
        extraction,
        source_text=title,
        document_title=title,
    )
    assert canonical.document_scope == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    assert canonical.publication_events == []
    assert any("Alcance corregido" in item for item in adjustments)


def test_auxiliary_pv_in_water_project_is_not_generation_project() -> None:
    title = (
        "Resolución por la que se formula informe de impacto ambiental del "
        "proyecto Construcción para la mejora del abastecimiento de agua."
    )
    source = title + " Se instala una planta solar fotovoltaica de 60 kWp para alimentar el bombeo."
    document = _test_document("BOE-A-2026-10868", title, source)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "planta solar fotovoltaica",
                GenerationType.PHOTOVOLTAIC,
                "planta solar fotovoltaica de 60 kWp",
            )],
            associated_components=[],
            administrative_actions=[_action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                AdministrativeDecision.FORMULATED,
                title,
                ["event"],
            )],
            event_summary="Informe ambiental de abastecimiento.",
        )],
    )
    canonical, _ = canonicalize_project_extraction(
        extraction,
        source_text=source,
        document_title=title,
    )
    assert canonical.document_scope == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    assert canonical.publication_events == []


def test_contract_procurement_is_preclassified_without_model() -> None:
    title = (
        "Anuncio de formalización de contratos de un suministro e instalación "
        "de placas fotovoltaicas para autoconsumo en un edificio público."
    )
    document = _test_document("BOE-B-2022-40990", title)
    extraction, adjustments = preclassify_document_without_model(document)
    assert extraction is not None
    assert (
        extraction.document_scope
        == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    )
    assert extraction.publication_events == []
    assert any("antes de llamar al modelo" in item for item in adjustments)


def test_standalone_storage_is_preclassified_without_model() -> None:
    title = (
        "Resolución por la que se otorga autorización administrativa previa "
        "para la planta de almacenamiento de energía Glauco Almacena, de "
        "55,384 MW, y su infraestructura de evacuación."
    )
    document = _test_document("BOE-A-2026-10655", title)
    extraction, adjustments = preclassify_document_without_model(document)
    assert extraction is not None
    assert (
        extraction.document_scope
        == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    )
    assert extraction.publication_events == []
    assert any("almacenamiento" in item.casefold() for item in adjustments)


def test_storage_linked_to_generation_is_not_preclassified() -> None:
    title = (
        "Anuncio por el que se somete a información pública el módulo de "
        "almacenamiento BESS Hibridación FV Andévalo, asociado a la planta "
        "fotovoltaica FV Andévalo."
    )
    document = _test_document("BOE-B-2026-99992", title)
    extraction, adjustments = preclassify_document_without_model(document)
    assert extraction is None
    assert adjustments == []


def test_canonicalization_public_signature_is_stable() -> None:
    parameters = signature(canonicalize_project_extraction).parameters

    assert tuple(parameters) == (
        "extraction",
        "source_text",
        "document_title",
    )
    assert parameters["source_text"].kind.name == "KEYWORD_ONLY"
    assert parameters["document_title"].kind.name == "KEYWORD_ONLY"


def test_canonicalization_is_idempotent() -> None:
    title = (
        "Resolución por la que se otorga autorización administrativa previa "
        "a la planta solar fotovoltaica Idempotencia."
    )
    document = _test_document("BOE-A-2026-99990", title)
    extraction = _test_extraction(
        document.boe_id,
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Idempotencia",
                        GenerationType.PHOTOVOLTAIC,
                        "planta solar fotovoltaica Idempotencia",
                    )
                ],
                administrative_actions=[
                    _action(
                        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                        AdministrativeDecision.AUTHORIZED,
                        title,
                        ["generation_asset_1"],
                    )
                ],
                event_summary="Autorización de la planta Idempotencia.",
            )
        ],
    )
    source_text = f"{document.title}\n{document.text}"

    canonical_once, _ = canonicalize_project_extraction(
        extraction,
        source_text=source_text,
        document_title=document.title,
    )
    canonical_twice, _ = canonicalize_project_extraction(
        canonical_once,
        source_text=source_text,
        document_title=document.title,
    )

    assert canonical_twice.model_dump_json() == canonical_once.model_dump_json()


def test_preclassification_does_not_require_agent_or_external_client() -> None:
    assert tuple(signature(preclassify_document_without_model).parameters) == (
        "document",
    )

    title = (
        "Anuncio de formalización de contratos de suministro e instalación "
        "de placas fotovoltaicas para autoconsumo en un edificio público."
    )
    extraction, _ = preclassify_document_without_model(
        _test_document("BOE-B-2026-99991", title)
    )

    assert extraction is not None
