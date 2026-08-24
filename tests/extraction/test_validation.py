from datetime import date
from hashlib import sha256
from inspect import signature

import pytest

from renewables_permitting.extraction.canonicalization import (
    canonicalize_project_extraction,
    preclassify_document_without_model,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    AssociatedComponent,
    AssociatedComponentType,
    BOEProjectExtraction,
    BOESourceDocument,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationAssetRelation,
    GenerationRelationType,
    GenerationType,
    PublicationEvent,
    TechnicalAttributeType,
    TechnicalMention,
)
from renewables_permitting.extraction.validation import (
    DocumentExtractionValidationError,
    build_document_validation_retry_prompt,
    validate_extraction_against_document,
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


def _not_relevant_extraction(document: BOESourceDocument) -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS,
        classification_reason="La fuente no identifica una planta de generación.",
        publication_events=[],
        extraction_notes=None,
        boe_id=document.boe_id,
        publication_date=document.publication_date,
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


def test_carbo_event_target() -> None:
    title = (
        "Anuncio por el que se somete a Información Pública la solicitud de "
        "Declaración, en concreto, de Utilidad Pública de la planta solar "
        "fotovoltaica Carbo, de 81,4 MW de potencia instalada, e infraestructura "
        "de evacuación a 30 kV."
    )
    document = _test_document("BOE-B-2024-27073", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Carbo", GenerationType.PHOTOVOLTAIC, title
            )],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                names_raw=[],
                description_raw="infraestructura de evacuación a 30 kV",
                related_generation_asset_refs=[],
                technical_mentions=[],
                evidence="infraestructura de evacuación a 30 kV",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                title,
            )],
            event_summary="Información pública de la DUP de Carbo y su evacuación.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    event = canonical.publication_events[0]
    assert len(event.generation_assets) == 1
    assert len(event.associated_components) == 1
    assert event.associated_components[0].related_generation_asset_refs == [
        "generation_asset_1"
    ]
    assert event.administrative_actions[0].targets == ["event"]


def test_entrenucleos_component_only() -> None:
    title = (
        "Anuncio por el que se convoca el levantamiento de actas previas a la "
        "ocupación de los bienes afectados por la infraestructura de evacuación "
        "de la planta fotovoltaica HSF Entrenucleos Ten."
    )
    document = _test_document("BOE-B-2026-17277", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "HSF Entrenucleos Ten",
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                description_raw="infraestructura de evacuación",
                related_generation_asset_refs=[],
                evidence=title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_OCCUPATION_RECORDS,
                AdministrativeDecision.ANNOUNCED,
                title,
            )],
            event_summary="Actas previas de la evacuación de Entrenucleos Ten.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    action = canonical.publication_events[0].administrative_actions[0]
    assert action.targets == ["component_1"]


def test_armus_storage_and_evacuation_targets() -> None:
    title = (
        "Resolución por la que se formula informe de impacto ambiental del "
        "proyecto Módulo de almacenamiento de energía «Armus», de 20 MW y "
        "80 MWh, y su infraestructura de evacuación, para su hibridación con "
        "la instalación híbrida «Armus Solar», integrada por 35 MW eólicos "
        "y 49,88 MW fotovoltaicos."
    )
    document = _test_document("BOE-A-2026-11838", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Armus Solar",
                    GenerationType.WIND,
                    title,
                    [TechnicalMention(
                        attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                        value_raw="35 MW",
                        evidence=title,
                    )],
                ),
                _asset(
                    "generation_asset_2",
                    "Armus Solar",
                    GenerationType.PHOTOVOLTAIC,
                    title,
                    [TechnicalMention(
                        attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                        value_raw="49,88 MW",
                        evidence=title,
                    )],
                ),
            ],
            associated_components=[
                AssociatedComponent(
                    local_component_ref="component_1",
                    component_type=AssociatedComponentType.ENERGY_STORAGE,
                    names_raw=["Armus"],
                    description_raw="Módulo de almacenamiento de energía «Armus»",
                    related_generation_asset_refs=[],
                    technical_mentions=[
                        TechnicalMention(
                            attribute_type=TechnicalAttributeType.STORAGE_POWER,
                            value_raw="20 MW",
                            evidence=title,
                        ),
                        TechnicalMention(
                            attribute_type=TechnicalAttributeType.STORAGE_CAPACITY,
                            value_raw="80 MWh",
                            evidence=title,
                        ),
                    ],
                    evidence=title,
                ),
                AssociatedComponent(
                    local_component_ref="component_2",
                    component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                    names_raw=[],
                    description_raw="infraestructura de evacuación",
                    related_generation_asset_refs=[],
                    technical_mentions=[],
                    evidence=title,
                ),
            ],
            administrative_actions=[_action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                AdministrativeDecision.FORMULATED,
                title,
            )],
            generation_relations=[GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_2",
                relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                evidence=title,
            )],
            event_summary="Informe ambiental del almacenamiento Armus y su evacuación.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    event = canonical.publication_events[0]
    storage = next(
        component
        for component in event.associated_components
        if component.component_type == AssociatedComponentType.ENERGY_STORAGE
    )
    evacuation = next(
        component
        for component in event.associated_components
        if component.component_type == AssociatedComponentType.EVACUATION_SYSTEM
    )
    assert set(storage.related_generation_asset_refs) == {
        "generation_asset_1", "generation_asset_2"
    }
    assert set(evacuation.related_generation_asset_refs) == {
        "generation_asset_1", "generation_asset_2"
    }
    assert set(event.administrative_actions[0].targets) == {
        storage.local_component_ref,
        evacuation.local_component_ref,
    }


def test_component_link_does_not_require_same_quote() -> None:
    title = "Autorización de la planta fotovoltaica Prado Gris y su evacuación."
    text = (
        "La planta fotovoltaica Prado Gris se ubica en el municipio indicado. "
        "La infraestructura de evacuación comprende una línea y una subestación."
    )
    document = _test_document("BOE-A-2026-10001", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Prado Gris", GenerationType.PHOTOVOLTAIC,
                "La planta fotovoltaica Prado Gris se ubica en el municipio indicado."
            )],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.POWER_LINE,
                description_raw="La infraestructura de evacuación comprende una línea",
                related_generation_asset_refs=[],
                evidence="La infraestructura de evacuación comprende una línea y una subestación.",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
            )],
            event_summary="Autorización de Prado Gris.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    component = canonical.publication_events[0].associated_components[0]
    assert component.related_generation_asset_refs == ["generation_asset_1"]


def test_auxiliary_components_are_aggregated() -> None:
    title = "Autorización de la planta eólica Norte y sus líneas y subestación de evacuación."
    document = _test_document("BOE-A-2026-10002", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Norte", GenerationType.WIND, title
            )],
            associated_components=[
                AssociatedComponent(
                    local_component_ref="component_1",
                    component_type=AssociatedComponentType.POWER_LINE,
                    description_raw="líneas",
                    related_generation_asset_refs=[],
                    evidence=title,
                ),
                AssociatedComponent(
                    local_component_ref="component_2",
                    component_type=AssociatedComponentType.ELECTRICAL_SUBSTATION,
                    description_raw="subestación",
                    related_generation_asset_refs=[],
                    evidence=title,
                ),
            ],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
            )],
            event_summary="Autorización de Norte.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    components = canonical.publication_events[0].associated_components
    assert len(components) == 1
    assert components[0].component_type == AssociatedComponentType.EVACUATION_SYSTEM


def test_nonliteral_optional_data_is_dropped() -> None:
    title = "Autorización de la planta solar Alba y su infraestructura de evacuación."
    document = _test_document("BOE-A-2026-10003", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Alba",
                GenerationType.PHOTOVOLTAIC,
                title,
                [TechnicalMention(
                    attribute_type=TechnicalAttributeType.INSTALLED_POWER,
                    value_raw="999 MW",
                    evidence="potencia inventada",
                )],
            )],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                names_raw=["SET Alba inventada"],
                description_raw="descripción reconstruida",
                related_generation_asset_refs=[],
                evidence=title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
            )],
            event_summary="Autorización de Alba.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    event = canonical.publication_events[0]
    assert event.generation_assets[0].technical_mentions == []
    assert event.associated_components[0].names_raw == []
    assert event.associated_components[0].description_raw is not None


def test_title_completes_coordinated_aap_aac() -> None:
    title = (
        "Resolución por la que se otorga autorización administrativa previa "
        "de las modificaciones y autorización administrativa de construcción "
        "a la planta fotovoltaica Delta."
    )
    document = _test_document("BOE-A-2026-10004", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Delta", GenerationType.PHOTOVOLTAIC, title
            )],
            administrative_actions=[_action(
                AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
            )],
            event_summary="Autorizaciones de Delta.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    actions = canonical.publication_events[0].administrative_actions
    by_type = {action.action_type: action for action in actions}
    assert AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION in by_type
    assert AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION in by_type
    assert by_type[AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION].is_modification
    assert not by_type[AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION].is_modification


def test_historical_action_is_pruned() -> None:
    title = "Resolución por la que se autoriza la construcción de la planta solar Magaz."
    text = (
        f"{title} Mediante Resolución de 2024 se formuló informe ambiental del proyecto."
    )
    document = _test_document("BOE-A-2026-10005", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Magaz", GenerationType.PHOTOVOLTAIC, title
            )],
            administrative_actions=[
                _action(
                    AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                    AdministrativeDecision.AUTHORIZED,
                    title,
                ),
                _action(
                    AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                    AdministrativeDecision.FORMULATED,
                    "Mediante Resolución de 2024 se formuló informe ambiental del proyecto.",
                ),
            ],
            event_summary="Autorización de construcción de Magaz.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    actions = canonical.publication_events[0].administrative_actions
    assert [action.action_type for action in actions] == [
        AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION
    ]


def test_independent_plants_are_split() -> None:
    title = "Autorización de las plantas solares Alfa y Beta y su evacuación común."
    document = _test_document("BOE-A-2026-10006", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[
                _asset("generation_asset_1", "Alfa", GenerationType.PHOTOVOLTAIC, title),
                _asset("generation_asset_2", "Beta", GenerationType.PHOTOVOLTAIC, title),
            ],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                description_raw="evacuación común",
                related_generation_asset_refs=[
                    "generation_asset_1", "generation_asset_2"
                ],
                evidence=title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
                ["event"],
            )],
            event_summary="Autorización conjunta de Alfa y Beta.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    assert len(canonical.publication_events) == 2
    assert all(len(event.generation_assets) == 1 for event in canonical.publication_events)


def test_same_name_hybrid_relation_is_valid() -> None:
    title = "Hibridación de la instalación Armus Solar con tecnología eólica y fotovoltaica."
    document = _test_document("BOE-A-2026-10007", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[
                _asset("generation_asset_1", "Armus Solar", GenerationType.WIND, title),
                _asset("generation_asset_2", "Armus Solar", GenerationType.PHOTOVOLTAIC, title),
            ],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            generation_relations=[GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_2",
                relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                evidence=title,
            )],
            event_summary="Hibridación de Armus Solar.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    assert len(canonical.publication_events[0].generation_relations) == 1


def test_hybrid_photovoltaic_infrastructure_is_explicit_generation_context() -> None:
    title = (
        "Resolución relativa a la infraestructura híbrida fotovoltaica "
        "«Rincón del Cabello», de 45,25 MWp."
    )
    document = _test_document("BOE-A-2026-14482", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Rincón del Cabello",
                GenerationType.PHOTOVOLTAIC,
                "infraestructura híbrida fotovoltaica «Rincón del Cabello», "
                "de 45,25 MWp",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            event_summary="Actuación relativa a Rincón del Cabello.",
        )],
    )

    validate_extraction_against_document(
        document=document,
        extraction=extraction,
    )


@pytest.mark.parametrize(
    "description",
    [
        "infraestructura de evacuación fotovoltaica «Nudo Norte»",
        "infraestructura fotovoltaica «Nudo Norte»",
    ],
)
def test_photovoltaic_infrastructure_without_hybrid_generation_context_is_rejected(
    description: str,
) -> None:
    title = f"Resolución relativa a la {description}."
    document = _test_document("BOE-A-2026-10071", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Nudo Norte",
                GenerationType.PHOTOVOLTAIC,
                description,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            event_summary="Actuación relativa a Nudo Norte.",
        )],
    )

    with pytest.raises(
        DocumentExtractionValidationError,
        match="no identifica la denominación como planta de generación",
    ):
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )


def test_generation_table_header_applies_only_to_its_structured_rows() -> None:
    title = "Resolución relativa a una evacuación compartida."
    table_intro = (
        "La infraestructura de evacuación es compartida por varias "
        "instalaciones de generación, que son objeto de proyecto y "
        "tramitación independiente. Se detalla en la tabla adjunta:"
    )
    names = [
        "HSF SOL DEL HELIÓPOLIS",
        "HSF SOL DE TARSIS",
        "HSF ALCALÁ DE GUADAIRA 1",
        "HSF ALCALÁ DE GUADAIRA 11",
        "HSF ALCALÁ DE GUADAIRA 111",
        "HSF ALCALÁ IV",
        "HSFALCALÁV",
        "HSF ENTRENUCLEOS TEN",
        "HSF ENTRENUCLEOS 5",
    ]
    rows = "\n".join(
        f"{name}\n{289_400 + index}\nPROMOTOR {index}, S.L."
        for index, name in enumerate(names, start=1)
    )
    text = (
        f"{table_intro}\nDENOMINACIÓN\nN.º EXPEDIENTE\nPROMOTOR\n"
        f"{rows}\nTensión de evacuación: 15 kV\n"
        "EDIFICIO NORTE"
    )
    document = _test_document("BOE-B-2024-29516", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [
            PublicationEvent(
                generation_assets=[_asset(
                    "generation_asset_1",
                    name,
                    GenerationType.PHOTOVOLTAIC,
                    name,
                )],
                administrative_actions=[_action(
                    AdministrativeActionType.OTHER,
                    AdministrativeDecision.OTHER,
                    table_intro,
                    ["event"],
                )],
                event_summary=f"Actuación relativa a {name}.",
            )
            for name in names
        ],
    )

    validate_extraction_against_document(
        document=document,
        extraction=extraction,
    )

    outside_table = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "EDIFICIO NORTE",
                GenerationType.PHOTOVOLTAIC,
                "EDIFICIO NORTE",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                table_intro,
                ["event"],
            )],
            event_summary="Actuación relativa al edificio.",
        )],
    )
    with pytest.raises(
        DocumentExtractionValidationError,
        match="no identifica la denominación como planta de generación",
    ):
        validate_extraction_against_document(
            document=document,
            extraction=outside_table,
        )


def test_two_column_generation_table_recovers_only_its_eight_plant_rows() -> None:
    title = "Resolución relativa a una evacuación compartida."
    table_intro = (
        "La infraestructura de evacuación es compartida con varias "
        "instalaciones de generación, que son objeto de proyecto y "
        "tramitación independiente. Se detalla en la tabla adjunta:"
    )
    names_and_types = (
        ("HSF Sol Morón", GenerationType.PHOTOVOLTAIC),
        ("HSF Las Encarnaciones", GenerationType.PHOTOVOLTAIC),
        ("PE Las Hazas", GenerationType.WIND),
        ("PE Josmanil", GenerationType.WIND),
        ("PE Las Cabreras", GenerationType.WIND),
        ("PE Villanueva 2", GenerationType.WIND),
        ("PE Villanueva 1", GenerationType.WIND),
        ("PE Cortijo Nuevo", GenerationType.WIND),
    )
    rows = "\n".join(
        f"{name}\n{280_440 + index}"
        + (
            " (Delegación Territorial de Energía en Sevilla)"
            if index == 1
            else ""
        )
        for index, (name, _) in enumerate(names_and_types, start=1)
    )
    text = (
        f"{table_intro}\nDENOMINACIÓN\nN.º DE EXPEDIENTE\n{rows}\n"
        "Las características de la SET Torreluenga se describen después."
    )
    document = _test_document("BOE-B-2024-3861", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [
            PublicationEvent(
                generation_assets=[_asset(
                    "generation_asset_1",
                    name,
                    generation_type,
                    name,
                )],
                associated_components=[AssociatedComponent(
                    local_component_ref="component_1",
                    component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                    names_raw=["SET Torreluenga"],
                    description_raw=None,
                    related_generation_asset_refs=["generation_asset_1"],
                    technical_mentions=[],
                    evidence="SET Torreluenga",
                )],
                administrative_actions=[_action(
                    AdministrativeActionType.OTHER,
                    AdministrativeDecision.OTHER,
                    table_intro,
                    ["component_1"],
                )],
                event_summary=f"Actuación compartida relativa a {name}.",
            )
            for name, generation_type in names_and_types
        ],
    )

    validate_extraction_against_document(
        document=document,
        extraction=extraction,
    )

    infrastructure_as_root = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "SET Torreluenga",
                GenerationType.PHOTOVOLTAIC,
                "SET Torreluenga",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            event_summary="Actuación relativa a la subestación.",
        )],
    )
    with pytest.raises(
        DocumentExtractionValidationError,
        match="no identifica la denominación como planta de generación",
    ):
        validate_extraction_against_document(
            document=document,
            extraction=infrastructure_as_root,
        )


def test_generic_two_column_table_does_not_create_generation_context() -> None:
    title = "Resolución relativa a infraestructuras eléctricas compartidas."
    text = (
        "Las infraestructuras eléctricas se detallan en la tabla adjunta:\n"
        "DENOMINACIÓN\nN.º DE EXPEDIENTE\nSUBESTACIÓN NORTE\n289.401"
    )
    document = _test_document("BOE-B-2024-10073", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "SUBESTACIÓN NORTE",
                GenerationType.PHOTOVOLTAIC,
                "SUBESTACIÓN NORTE",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            event_summary="Actuación relativa a la subestación.",
        )],
    )

    with pytest.raises(
        DocumentExtractionValidationError,
        match="no identifica la denominación como planta de generación",
    ):
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )


def test_shared_generation_list_prefix_is_bounded_to_its_items() -> None:
    title = (
        "Anuncio por el que se somete a información pública la solicitud de "
        "autorización administrativa previa de la línea de evacuación a la "
        "Subestación Arguineguín."
    )
    generation_list = (
        "varias instalaciones de generación de energía renovable "
        "(PSF Agueda I, Agueda II, Agueda III, Agueda IV)"
    )
    text = (
        f"La línea permitirá la evacuación de {generation_list}. "
        "El centro de seccionamiento de las PSF Agueda II y Agueda IV "
        "conecta con la subestación."
    )
    document = _test_document("BOE-B-2024-9915", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[
                _asset(
                    f"generation_asset_{index}",
                    name,
                    GenerationType.PHOTOVOLTAIC,
                    name,
                )
                for index, name in enumerate(
                    (
                        "PSF Agueda I",
                        "PSF Agueda II",
                        "PSF Agueda III",
                        "PSF Agueda IV",
                    ),
                    start=1,
                )
            ],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.POWER_LINE,
                names_raw=[],
                description_raw="línea de evacuación a la Subestación Arguineguín",
                related_generation_asset_refs=[
                    f"generation_asset_{index}" for index in range(1, 5)
                ],
                technical_mentions=[],
                evidence=title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                title,
                ["component_1"],
            )],
            event_summary="Información pública de la evacuación de Agueda I-IV.",
        )],
    )

    canonical = _canonicalize_test(document, extraction)

    assert [
        event.generation_assets[0].names_raw[0]
        for event in canonical.publication_events
    ] == ["PSF Agueda I", "Agueda II", "Agueda III", "Agueda IV"]


def test_generic_infrastructure_table_does_not_create_generation_context() -> None:
    title = "Resolución relativa a infraestructuras eléctricas compartidas."
    text = (
        "Las infraestructuras eléctricas se detallan en la tabla adjunta:\n"
        "DENOMINACIÓN\nN.º EXPEDIENTE\nPROMOTOR\n"
        "SUBESTACIÓN NORTE\n289.401\nRED NORTE, S.L."
    )
    document = _test_document("BOE-B-2024-10072", title, text)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "SUBESTACIÓN NORTE",
                GenerationType.PHOTOVOLTAIC,
                "SUBESTACIÓN NORTE",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            event_summary="Actuación relativa a la subestación.",
        )],
    )

    with pytest.raises(
        DocumentExtractionValidationError,
        match="no identifica la denominación como planta de generación",
    ):
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )


def test_nonliteral_asset_and_action_evidence_are_repaired() -> None:
    title = "Resolución por la que se otorga autorización administrativa previa a la planta fotovoltaica Horizonte."
    document = _test_document("BOE-A-2026-10008", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Horizonte",
                GenerationType.PHOTOVOLTAIC,
                "planta fotovoltaica Horizonte con redacción reconstruida",
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                "se autoriza Horizonte con redacción reconstruida",
            )],
            event_summary="Autorización de Horizonte.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    event = canonical.publication_events[0]
    assert event.generation_assets[0].evidence == title
    assert event.administrative_actions[0].evidence == title


def test_environmental_public_information_is_not_final_dia() -> None:
    title = (
        "Anuncio por el que se somete a información pública el estudio de "
        "impacto ambiental y la solicitud de la planta solar Vega."
    )
    document = _test_document("BOE-B-2026-10009", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Vega", GenerationType.PHOTOVOLTAIC, title
            )],
            administrative_actions=[_action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                title,
            )],
            event_summary="Información pública ambiental de Vega.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    action = canonical.publication_events[0].administrative_actions[0]
    assert action.action_type == AdministrativeActionType.ENVIRONMENTAL_IMPACT_ASSESSMENT
    assert action.decision == AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION


def test_error_correction_does_not_republish_original_action() -> None:
    title = (
        "Corrección de errores de la Resolución por la que se formula la "
        "declaración de impacto ambiental de la planta solar Luna."
    )
    document = _test_document("BOE-A-2026-10010", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Luna", GenerationType.PHOTOVOLTAIC, title
            )],
            administrative_actions=[_action(
                AdministrativeActionType.ERROR_CORRECTION,
                AdministrativeDecision.RECTIFIED,
                title,
            )],
            event_summary="Corrección de errores de la resolución ambiental de Luna.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    assert [
        action.action_type
        for action in canonical.publication_events[0].administrative_actions
    ] == [AdministrativeActionType.ERROR_CORRECTION]


def test_contextual_name_inside_evacuation_is_not_generation_target() -> None:
    title = (
        "Anuncio por el que se convoca el levantamiento de actas previas a la "
        "ocupación de fincas afectas por la implantación de la infraestructura "
        "eléctricas de evacuación asociada a la instalación de generación de "
        "energía eléctrica denominada HSF Entrenucleos Ten."
    )
    document = _test_document("BOE-B-2026-17277", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "HSF Entrenucleos Ten",
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            associated_components=[AssociatedComponent(
                local_component_ref="component_1",
                component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                description_raw="infraestructura eléctricas de evacuación",
                related_generation_asset_refs=["generation_asset_1"],
                evidence=title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_OCCUPATION_RECORDS,
                AdministrativeDecision.ANNOUNCED,
                title,
            )],
            event_summary="Actas previas de la evacuación de Entrenucleos Ten.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    assert canonical.publication_events[0].administrative_actions[0].targets == [
        "component_1"
    ]


def test_modified_environmental_resolution_sets_flag() -> None:
    title = (
        "Resolución por la que se modifica la de 28 de febrero de 2018, "
        "por la que se formula declaración de impacto ambiental sobre el "
        "proyecto Parque Eólico Campillo."
    )
    document = _test_document("BOE-A-2022-24405", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Parque Eólico Campillo",
                GenerationType.WIND,
                title,
            )],
            associated_components=[],
            administrative_actions=[_action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
                AdministrativeDecision.FORMULATED,
                title,
            )],
            event_summary="Modificación de la declaración ambiental.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    assert canonical.publication_events[0].administrative_actions[0].is_modification is True


def test_gas_infrastructure_is_preclassified_without_model() -> None:
    title = (
        "Resolución por la que se otorga autorización administrativa y "
        "declaración de utilidad pública del proyecto Anexo al gasoducto "
        "Salamanca-Zamora. Nueva posición O-12X con estación de medida "
        "G-65 para inyección de biometano."
    )
    document = _test_document("BOE-A-2026-10656", title)
    extraction, adjustments = preclassify_document_without_model(document)
    assert extraction is not None
    assert (
        extraction.document_scope
        == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    )
    assert extraction.publication_events == []
    assert any("antes de llamar al modelo" in item for item in adjustments)
    validate_extraction_against_document(
        document=document,
        extraction=extraction,
    )


def test_public_information_decisions_are_canonical() -> None:
    title = (
        "Anuncio por el que se somete a información pública la solicitud de "
        "autorización administrativa previa y autorización administrativa "
        "de construcción de la planta fotovoltaica Prueba."
    )
    document = _test_document("BOE-B-2026-99991", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1", "Prueba", GenerationType.PHOTOVOLTAIC, title
            )],
            associated_components=[],
            administrative_actions=[
                _action(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                    AdministrativeDecision.REQUESTED,
                    title,
                ),
                _action(
                    AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                    AdministrativeDecision.REQUESTED,
                    title,
                ),
                _action(
                    AdministrativeActionType.PUBLIC_INFORMATION,
                    AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                    title,
                ),
            ],
            event_summary="Información pública de autorizaciones.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    actions = canonical.publication_events[0].administrative_actions
    assert {a.action_type for a in actions} == {
        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
        AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
    }
    assert all(
        a.decision == AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
        for a in actions
    )


@pytest.mark.parametrize(
    "utility_wording",
    [
        "reconocimiento, en concreto, de utilidad pública",
        "declaración, en concreto, de utilidad pública",
    ],
)
def test_public_utility_title_wording_validates_as_specific_action(
    utility_wording: str,
) -> None:
    title = (
        "Anuncio por el que se somete a información pública la solicitud de "
        f"{utility_wording} de la planta fotovoltaica Prueba."
    )
    document = _test_document("BOE-B-2025-39508", title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Prueba",
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                title,
                ["event"],
            )],
            event_summary="Información pública de la utilidad pública.",
        )],
    )

    canonical = _canonicalize_test(document, extraction)

    assert [
        action.action_type
        for action in canonical.publication_events[0].administrative_actions
    ] == [AdministrativeActionType.PUBLIC_UTILITY_DECLARATION]


@pytest.mark.parametrize(
    ("boe_id", "utility_wording"),
    [
        ("BOE-B-2024-22754", "reconocimiento de utilidad pública"),
        ("BOE-B-2024-3263", "declaración en concreto de utilidad pública"),
        ("BOE-B-2024-41261", "declaración en concreto de utilidad pública"),
        ("BOE-B-2026-18178", "declaración, en concreto de utilidad pública"),
    ],
)
def test_main02_public_utility_variants_validate_as_specific_action(
    boe_id: str,
    utility_wording: str,
) -> None:
    title = (
        "Anuncio por el que se somete a información pública la solicitud de "
        f"{utility_wording} de la planta fotovoltaica Prueba."
    )
    document = _test_document(boe_id, title)
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Prueba",
                GenerationType.PHOTOVOLTAIC,
                title,
            )],
            administrative_actions=[_action(
                AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
                AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
                title,
                ["event"],
            )],
            event_summary="Información pública de la utilidad pública.",
        )],
    )

    canonical = _canonicalize_test(document, extraction)

    assert [
        action.action_type
        for action in canonical.publication_events[0].administrative_actions
    ] == [AdministrativeActionType.PUBLIC_UTILITY_DECLARATION]


@pytest.mark.parametrize(
    ("boe_id", "title", "text", "generation_contrast"),
    [
        pytest.param(
            "BOE-B-2024-43565",
            "Anuncio de corrección de errores. Objeto: implantación de un "
            "sistema de generación fotovoltaico para suministro "
            "complementario en la IDAM de Alicante I.",
            "Corrección de un contrato de obras para el suministro "
            "complementario de la instalación desaladora.",
            "Anuncio de corrección de errores de la autorización de la planta "
            "fotovoltaica Alicante Solar.",
            id="auxiliary-generation-procurement",
        ),
        pytest.param(
            "BOE-B-2025-7992",
            "Anuncio por el que se convoca para el levantamiento de actas "
            "previas a la ocupación por la construcción de infraestructuras "
            "de evacuación asociadas "
            "a la instalación de generación de energía eléctrica denominada "
            "sustitución de tramo de LAMT 15 kV Castillo.",
            "El objeto es sustituir el tramo de línea entre dos centros de "
            "distribución.",
            "Anuncio por el que se convoca para el levantamiento de actas "
            "previas a la ocupación de la evacuación asociada a la planta "
            "fotovoltaica FV Castillo.",
            id="grid-line-replacement",
        ),
        pytest.param(
            "BOE-B-2026-27232",
            "Anuncio por el que se convoca para el levantamiento de actas "
            "previas a la ocupación por la construcción de infraestructuras "
            "de evacuación asociadas a la instalación de generación de "
            "energía eléctrica denominada \"Sustitución de LAMT 25 kV "
            "Casariche para conversión a doble circuito\".",
            "La finalidad es sustituir el tramo de LAMT y construir un nuevo "
            "tramo de LSMT.",
            "Anuncio por el que se convoca para el levantamiento de actas "
            "previas a la ocupación de la evacuación asociada a la planta "
            "fotovoltaica Casariche Solar.",
            id="quoted-grid-line-replacement-without-tramo-prefix",
        ),
        pytest.param(
            "BOE-B-2026-441",
            "Corrección de errores de la segunda convocatoria de los "
            "programas para la concesión de ayudas a la repotenciación de "
            "instalaciones eólicas y minicentrales hidroeléctricas.",
            "Extracto general de la convocatoria, sin proyecto ni planta "
            "identificados.",
            "Corrección de errores de la Resolución por la que se concede una "
            "ayuda al parque eólico Sierra Norte.",
            id="generic-grant-call",
        ),
        pytest.param(
            "BOE-B-2024-45427",
            "Resolución por la que se declara el desistimiento y archivo de "
            "la declaración de utilidad pública del proyecto de instalación "
            "eléctrica LAAT 220 kV SET Guadalsolar - SET Mirabal 220 kV.",
            "Guadalsolar Uno, S.L. promovió la línea entre ambas "
            "subestaciones.",
            "Resolución por la que se archiva la declaración de utilidad "
            "pública de la LAAT de evacuación de la planta solar Guadalsolar.",
            id="grid-proper-name-generation-substring",
        ),
        pytest.param(
            "BOE-B-2025-26539",
            "Resolución por la que se somete a información pública el Proyecto "
            "de Optimización Energética mediante Instalación Fotovoltaica y "
            "Sustitución de Equipos Electromecánicos en Bombeos de una "
            "comunidad de regantes.",
            "La instalación es auxiliar a los bombeos del proyecto de regadío.",
            "Resolución por la que se somete a información pública la planta "
            "fotovoltaica Rincón del Moro para autoconsumo industrial.",
            id="auxiliary-irrigation-photovoltaic",
        ),
        pytest.param(
            "BOE-B-2025-16990",
            "Resolución por la que se somete a información pública el Proyecto "
            "para la mejora de la eficiencia energética mediante balsa de "
            "acumulación e instalación fotovoltaica en una comunidad de "
            "regantes.",
            "La instalación sirve al proyecto de regadío.",
            "Resolución por la que se somete a información pública la planta "
            "fotovoltaica Trasvase Solar.",
            id="auxiliary-irrigation-energy-efficiency",
        ),
    ],
)
def test_post_model_non_project_context_preserves_scope_v4_preclassification(
    boe_id: str,
    title: str,
    text: str,
    generation_contrast: str,
) -> None:
    document = _test_document(boe_id, title, text)

    preclassified, adjustments = preclassify_document_without_model(document)

    assert preclassified is None
    assert adjustments == []
    validate_extraction_against_document(
        document=document,
        extraction=_not_relevant_extraction(document),
    )

    contrast = _test_document("BOE-B-2026-99999", generation_contrast)
    with pytest.raises(
        DocumentExtractionValidationError,
        match="Posible falso negativo de alcance",
    ):
        validate_extraction_against_document(
            document=contrast,
            extraction=_not_relevant_extraction(contrast),
        )


@pytest.mark.parametrize(
    "title",
    [
        "Resolución por la que se otorga autorización administrativa previa "
        "a la planta solar fotovoltaica Solar Uno.",
        "Resolución por la que se otorga autorización administrativa previa "
        "al parque solar Solar Dos.",
        "Resolución por la que se otorga autorización administrativa previa "
        "al parque eólico Viento Norte.",
        "Resolución por la que se otorga autorización administrativa previa "
        "a la hibridación fotovoltaica de la planta Río.",
    ],
)
def test_post_model_exceptions_do_not_hide_named_generation_projects(
    title: str,
) -> None:
    document = _test_document("BOE-B-2026-99998", title)

    with pytest.raises(
        DocumentExtractionValidationError,
        match="Posible falso negativo de alcance",
    ):
        validate_extraction_against_document(
            document=document,
            extraction=_not_relevant_extraction(document),
        )


def test_water_concession_is_not_prior_authorization() -> None:
    title = (
        "Resolución por la que se otorga la concesión para el aprovechamiento "
        "de agua con destino a producción de energía eléctrica."
    )
    document = _test_document("BOE-B-2023-19087", title, title + " Central Hidroeléctrica Navaleo.")
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Central Hidroeléctrica Navaleo",
                GenerationType.HYDROPOWER,
                "Central Hidroeléctrica Navaleo",
            )],
            associated_components=[],
            administrative_actions=[_action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
            )],
            event_summary="Concesión hidroeléctrica.",
        )],
    )
    canonical = _canonicalize_test(document, extraction)
    assert canonical.publication_events[0].administrative_actions[0].action_type == AdministrativeActionType.WATER_CONCESSION


def _valid_document_and_extraction() -> tuple[
    BOESourceDocument,
    BOEProjectExtraction,
]:
    title = (
        "Resolución por la que se otorga autorización administrativa previa "
        "a la planta solar fotovoltaica Solar Uno."
    )
    document = _test_document("BOE-A-2026-99980", title)
    extraction = _test_extraction(
        document.boe_id,
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Solar Uno",
                        GenerationType.PHOTOVOLTAIC,
                        title,
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
                event_summary="Autorización de la planta Solar Uno.",
            )
        ],
    )
    return document, extraction


def test_validation_public_contract_signatures_are_stable() -> None:
    assert issubclass(DocumentExtractionValidationError, ValueError)
    assert tuple(signature(validate_extraction_against_document).parameters) == (
        "document",
        "extraction",
    )
    assert tuple(signature(build_document_validation_retry_prompt).parameters) == (
        "original_prompt",
        "validation_error",
    )


def test_valid_extraction_has_no_issues_and_is_not_mutated() -> None:
    document, extraction = _valid_document_and_extraction()
    original_json = extraction.model_dump_json()

    validate_extraction_against_document(
        document=document,
        extraction=extraction,
    )

    assert extraction.model_dump_json() == original_json


def test_validation_rejects_event_spanning_multiple_material_groups() -> None:
    title = (
        "Resolución relativa a Parque Solar Alfa, Parque Solar Beta y "
        "Parque Solar Gamma."
    )
    relation_evidence = "Parque Solar Alfa se hibrida con Parque Solar Beta."
    document = _test_document(
        "BOE-A-2026-99980",
        title,
        f"{relation_evidence} Parque Solar Gamma es un proyecto independiente.",
    )
    extraction = _test_extraction(
        document.boe_id,
        [PublicationEvent(
            generation_assets=[
                _asset(
                    f"generation_asset_{index}",
                    name,
                    GenerationType.PHOTOVOLTAIC,
                    title,
                )
                for index, name in enumerate(
                    ("Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"),
                    start=1,
                )
            ],
            administrative_actions=[_action(
                AdministrativeActionType.OTHER,
                AdministrativeDecision.OTHER,
                title,
                ["event"],
            )],
            generation_relations=[GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_2",
                relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                evidence=relation_evidence,
            )],
            event_summary="Dos plantas integradas y una planta independiente.",
        )],
    )

    with pytest.raises(DocumentExtractionValidationError, match="plantas independientes"):
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )


def test_validation_accepts_material_group_and_separate_independent_event() -> None:
    title = (
        "Resolución relativa a Parque Solar Alfa, Parque Solar Beta y "
        "Parque Solar Gamma."
    )
    relation_evidence = "Parque Solar Alfa se hibrida con Parque Solar Beta."
    document = _test_document(
        "BOE-A-2026-99979",
        title,
        f"{relation_evidence} Parque Solar Gamma es un proyecto independiente.",
    )
    extraction = _test_extraction(
        document.boe_id,
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Parque Solar Alfa",
                        GenerationType.PHOTOVOLTAIC,
                        title,
                    ),
                    _asset(
                        "generation_asset_2",
                        "Parque Solar Beta",
                        GenerationType.PHOTOVOLTAIC,
                        title,
                    ),
                ],
                administrative_actions=[_action(
                    AdministrativeActionType.OTHER,
                    AdministrativeDecision.OTHER,
                    title,
                    ["event"],
                )],
                generation_relations=[GenerationAssetRelation(
                    source_generation_asset_ref="generation_asset_1",
                    target_generation_asset_ref="generation_asset_2",
                    relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                    evidence=relation_evidence,
                )],
                event_summary="Grupo material Alfa Beta.",
            ),
            PublicationEvent(
                generation_assets=[_asset(
                    "generation_asset_1",
                    "Parque Solar Gamma",
                    GenerationType.PHOTOVOLTAIC,
                    title,
                )],
                administrative_actions=[_action(
                    AdministrativeActionType.OTHER,
                    AdministrativeDecision.OTHER,
                    title,
                    ["event"],
                )],
                event_summary="Proyecto independiente Gamma.",
            ),
        ],
    )

    validate_extraction_against_document(
        document=document,
        extraction=extraction,
    )


def test_validation_issues_preserve_exact_order() -> None:
    title = "Resolución sobre la planta solar fotovoltaica Solar Uno."
    document = _test_document("BOE-A-2026-99981", title)
    extraction = _test_extraction(
        "BOE-A-2026-99982",
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Planta Inventada",
                        GenerationType.PHOTOVOLTAIC,
                        "evidencia inventada de la planta",
                    )
                ],
                administrative_actions=[
                    _action(
                        AdministrativeActionType.OTHER,
                        AdministrativeDecision.OTHER,
                        "evidencia inventada de la actuación",
                    )
                ],
                event_summary="Extracción deliberadamente incompatible.",
            )
        ],
    ).model_copy(update={"publication_date": date(2025, 1, 1)})

    with pytest.raises(DocumentExtractionValidationError) as exc_info:
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )

    assert exc_info.value.issues == [
        "boe_id no coincide con la fuente.",
        "publication_date no coincide con la fuente.",
        "publication_events[1].generation_asset_1: nombre no documental "
        + repr("Planta Inventada")
        + ".",
        "publication_events[1].generation_asset_1.evidence no es literal.",
        "publication_events[1].administrative_actions[1].evidence no es literal.",
        "publication_events[1].administrative_actions[1]: targets está vacío.",
    ]


def test_generation_name_requires_documentary_generation_context() -> None:
    title = "Resolución relativa a la planta solar fotovoltaica Solar Uno."
    body = "El Edificio Norte alberga oficinas."
    document = _test_document("BOE-A-2026-99983", title, body)
    extraction = _test_extraction(
        document.boe_id,
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Edificio Norte",
                        GenerationType.PHOTOVOLTAIC,
                        body,
                    )
                ],
                administrative_actions=[
                    _action(
                        AdministrativeActionType.OTHER,
                        AdministrativeDecision.OTHER,
                        title,
                        ["event"],
                    )
                ],
                event_summary="Mención sin contexto de generación.",
            )
        ],
    )

    with pytest.raises(DocumentExtractionValidationError) as exc_info:
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )

    assert exc_info.value.issues == [
        "publication_events[1].generation_asset_1: la fuente no identifica "
        "la denominación como planta de generación."
    ]


def test_validation_reports_incompatible_action_reference() -> None:
    document, extraction = _valid_document_and_extraction()
    extraction.publication_events[0].administrative_actions[0].targets = [
        "generation_asset_2"
    ]

    with pytest.raises(DocumentExtractionValidationError) as exc_info:
        validate_extraction_against_document(
            document=document,
            extraction=extraction,
        )

    assert exc_info.value.issues == [
        "publication_events[1].administrative_actions[1]: targets inexistentes "
        "['generation_asset_2']."
    ]


def test_validation_error_preserves_issues_and_preview() -> None:
    issues = ["primera incidencia", "segunda incidencia"]
    error = DocumentExtractionValidationError(issues)

    assert error.issues is issues
    assert str(error) == "primera incidencia; segunda incidencia"


def test_validation_retry_prompt_content_is_exact() -> None:
    original_prompt = "PROMPT ORIGINAL"
    error = DocumentExtractionValidationError(
        ["primera incidencia", "segunda incidencia"]
    )

    prompt = build_document_validation_retry_prompt(
        original_prompt=original_prompt,
        validation_error=error,
    )
    newline = chr(10)
    expected = (
        original_prompt
        + newline
        + newline
        + "La salida anterior cumplió el esquema, pero no las invariantes documentales. "
        + "Genera una salida completa nueva y corrige estas incidencias:"
        + newline
        + "- primera incidencia"
        + newline
        + "- segunda incidencia"
        + newline
        + newline
        + "Recuerda: las únicas raíces son plantas de generación con nombres literales; "
        + "almacenamiento y evacuación son componentes asociados. Usa target='event' "
        + "cuando la actuación recae sobre todo el proyecto y targets concretos solo "
        + "cuando afecta a un subconjunto inequívoco."
    )

    assert prompt == expected
