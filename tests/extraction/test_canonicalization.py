from datetime import date
from hashlib import sha256
from inspect import signature

import pytest

from renewables_permitting.extraction.canonicalization import (
    _should_replace_decision_from_title,
    _split_independent_generation_event,
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


def _canonicalize_test_actions(
    *,
    title: str,
    actions: list[AdministrativeAction],
    source_text: str | None = None,
) -> tuple[list[AdministrativeAction], list[str]]:
    extraction = _test_extraction(
        "BOE-A-2026-99989",
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Prueba",
                        GenerationType.PHOTOVOLTAIC,
                        "planta solar fotovoltaica Prueba",
                    )
                ],
                administrative_actions=actions,
                event_summary="Actuación administrativa de la planta Prueba.",
            )
        ],
    )
    canonical, adjustments = canonicalize_project_extraction(
        extraction,
        source_text=source_text or title,
        document_title=title,
    )
    return canonical.publication_events[0].administrative_actions, adjustments


def _canonicalize_test_event(
    *,
    boe_id: str,
    title: str,
    text: str,
    event: PublicationEvent,
) -> tuple[BOEProjectExtraction, list[str]]:
    extraction = _test_extraction(boe_id, [event])
    return canonicalize_project_extraction(
        extraction,
        source_text=f"{title}\n{text}",
        document_title=title,
    )


def _authorization_action(evidence: str) -> AdministrativeAction:
    return _action(
        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
        AdministrativeDecision.AUTHORIZED,
        evidence,
        ["event"],
    )


def _canonicalize_generation_relation_scenario(
    *,
    boe_id: str,
    names: list[str],
    relation_specs: list[tuple[int, int, GenerationRelationType, str]],
    generation_types: list[GenerationType] | None = None,
    text: str | None = None,
) -> tuple[BOEProjectExtraction, list[str]]:
    title = f"Resolución relativa a {', '.join(names)}."
    event = PublicationEvent(
        generation_assets=[
            _asset(
                f"generation_asset_{index}",
                name,
                (
                    generation_types[index - 1]
                    if generation_types is not None
                    else GenerationType.PHOTOVOLTAIC
                ),
                title,
            )
            for index, name in enumerate(names, start=1)
        ],
        administrative_actions=[_action(
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.AUTHORIZED,
            title,
            ["event"],
        )],
        generation_relations=[
            GenerationAssetRelation(
                source_generation_asset_ref=f"generation_asset_{source_index}",
                target_generation_asset_ref=f"generation_asset_{target_index}",
                relation_type=relation_type,
                evidence=evidence,
            )
            for source_index, target_index, relation_type, evidence in relation_specs
        ],
        event_summary="Relaciones materiales entre plantas de generación.",
    )
    canonical, adjustments = _canonicalize_test_event(
        boe_id=boe_id,
        title=title,
        text=text or " ".join(spec[3] for spec in relation_specs),
        event=event,
    )
    return canonical, adjustments


def _three_asset_event_for_split(
    *,
    administrative_actions: list[AdministrativeAction],
    associated_components: list[AssociatedComponent] | None = None,
) -> tuple[PublicationEvent, str]:
    relation_evidence = (
        "Parque Solar Alfa se hibrida con Parque Solar Beta."
    )
    event = PublicationEvent(
        generation_assets=[
            _asset(
                f"generation_asset_{index}",
                name,
                GenerationType.PHOTOVOLTAIC,
                name,
            )
            for index, name in enumerate(
                (
                    "Parque Solar Alfa",
                    "Parque Solar Beta",
                    "Parque Solar Gamma",
                ),
                start=1,
            )
        ],
        associated_components=associated_components or [],
        administrative_actions=administrative_actions,
        generation_relations=[GenerationAssetRelation(
            source_generation_asset_ref="generation_asset_1",
            target_generation_asset_ref="generation_asset_2",
            relation_type=GenerationRelationType.HYBRIDIZED_WITH,
            evidence=relation_evidence,
        )],
        event_summary="Dos plantas integradas y una independiente.",
    )
    return event, relation_evidence


def test_ecological_substitution_does_not_integrate_generation_assets() -> None:
    title = "Resolución por la que se autorizan las plantas solares Alfa y Beta."
    text = (
        "La planta solar fotovoltaica Alfa y la planta solar fotovoltaica Beta "
        "son instalaciones independientes. Junto a la planta Alfa existen "
        "matorrales de sustitución termófilos."
    )
    canonical, adjustments = _canonicalize_test_event(
        boe_id="BOE-A-2026-99001",
        title=title,
        text=text,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Alfa",
                ),
                _asset(
                    "generation_asset_2",
                    "Beta",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Beta",
                ),
            ],
            administrative_actions=[_authorization_action(title)],
            event_summary="Autorización de dos plantas independientes.",
        ),
    )

    assert len(canonical.publication_events) == 2
    assert any("2 grupos materiales" in item for item in adjustments)


def test_single_named_asset_does_not_support_generation_relation() -> None:
    title = "Resolución por la que se autorizan las plantas solares Alfa y Beta."
    weak_relation_evidence = (
        "Se estudia la hibridación de la planta solar fotovoltaica Alfa con "
        "un sistema de almacenamiento."
    )
    text = (
        f"{weak_relation_evidence} La planta solar fotovoltaica Beta es una "
        "instalación independiente."
    )
    canonical, adjustments = _canonicalize_test_event(
        boe_id="BOE-A-2026-99002",
        title=title,
        text=text,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Alfa",
                ),
                _asset(
                    "generation_asset_2",
                    "Beta",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Beta",
                ),
            ],
            administrative_actions=[_authorization_action(title)],
            generation_relations=[
                GenerationAssetRelation(
                    source_generation_asset_ref="generation_asset_1",
                    target_generation_asset_ref="generation_asset_2",
                    relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                    evidence=weak_relation_evidence,
                )
            ],
            event_summary="Autorización de dos plantas independientes.",
        ),
    )

    assert len(canonical.publication_events) == 2


def test_parallel_storage_hybridizations_do_not_integrate_generation_assets() -> None:
    title = "Resolución por la que se autorizan tres plantas solares y sus baterías."
    text = (
        "La planta solar fotovoltaica Solar Uno es independiente. "
        "La planta solar fotovoltaica Solar Dos es independiente. "
        "La planta solar fotovoltaica Solar Tres es independiente. "
        "El BESS Uno se destina a la hibridación con la PSFV Solar Uno. "
        "El BESS Dos se destina a la hibridación con la PSFV Solar Dos. "
        "El BESS Tres se destina a la hibridación con la PSFV Solar Tres."
    )
    assets = [
        _asset(
            f"generation_asset_{index}",
            f"Solar {name}",
            GenerationType.PHOTOVOLTAIC,
            f"planta solar fotovoltaica Solar {name}",
        )
        for index, name in enumerate(("Uno", "Dos", "Tres"), start=1)
    ]
    components = [
        AssociatedComponent(
            local_component_ref=f"component_{index}",
            component_type=AssociatedComponentType.ENERGY_STORAGE,
            names_raw=[f"BESS {name}"],
            description_raw=f"BESS {name}",
            related_generation_asset_refs=[f"generation_asset_{index}"],
            evidence=(
                f"El BESS {name} se destina a la hibridación con la PSFV "
                f"Solar {name}."
            ),
        )
        for index, name in enumerate(("Uno", "Dos", "Tres"), start=1)
    ]
    canonical, _ = _canonicalize_test_event(
        boe_id="BOE-A-2026-99003",
        title=title,
        text=text,
        event=PublicationEvent(
            generation_assets=assets,
            associated_components=components,
            administrative_actions=[_authorization_action(title)],
            event_summary="Tres plantas con almacenamientos asociados uno a uno.",
        ),
    )

    assert len(canonical.publication_events) == 3
    assert all(
        len(event.generation_assets) == 1
        and len(event.associated_components) == 1
        for event in canonical.publication_events
    )


def test_multilink_storage_alone_does_not_integrate_generation_assets() -> None:
    title = "Resolución por la que se autorizan las plantas solares Alfa y Beta."
    text = (
        "La planta solar fotovoltaica Alfa y la planta solar fotovoltaica Beta "
        "son instalaciones independientes. Existe un sistema de almacenamiento común."
    )
    canonical, _ = _canonicalize_test_event(
        boe_id="BOE-A-2026-99004",
        title=title,
        text=text,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Alfa",
                ),
                _asset(
                    "generation_asset_2",
                    "Beta",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Beta",
                ),
            ],
            associated_components=[
                AssociatedComponent(
                    local_component_ref="component_1",
                    component_type=AssociatedComponentType.ENERGY_STORAGE,
                    names_raw=[],
                    description_raw="sistema de almacenamiento común",
                    related_generation_asset_refs=[
                        "generation_asset_1",
                        "generation_asset_2",
                    ],
                    evidence="sistema de almacenamiento común",
                )
            ],
            administrative_actions=[_authorization_action(title)],
            event_summary="Dos plantas con un almacenamiento común.",
        ),
    )

    assert len(canonical.publication_events) == 2


@pytest.mark.parametrize(
    ("relation_type", "relation_evidence"),
    [
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "La planta solar fotovoltaica Alfa se hibrida materialmente con "
            "el parque eólico Beta.",
        ),
        (
            GenerationRelationType.REPLACES,
            "La planta solar fotovoltaica Alfa sustituye explícitamente al "
            "parque eólico Beta.",
        ),
    ],
)
def test_documented_material_generation_relation_preserves_integrated_event(
    relation_type: GenerationRelationType,
    relation_evidence: str,
) -> None:
    title = "Resolución por la que se autoriza la instalación Alfa Beta."
    canonical, adjustments = _canonicalize_test_event(
        boe_id="BOE-A-2026-99005",
        title=title,
        text=relation_evidence,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    relation_evidence,
                ),
                _asset(
                    "generation_asset_2",
                    "Beta",
                    GenerationType.WIND,
                    relation_evidence,
                ),
            ],
            administrative_actions=[_authorization_action(title)],
            generation_relations=[
                GenerationAssetRelation(
                    source_generation_asset_ref="generation_asset_1",
                    target_generation_asset_ref="generation_asset_2",
                    relation_type=relation_type,
                    evidence=relation_evidence,
                )
            ],
            event_summary="Autorización de una instalación integrada.",
        ),
    )

    assert len(canonical.publication_events) == 1
    assert len(canonical.publication_events[0].generation_relations) == 1
    assert not any("grupos materiales" in item for item in adjustments)


def test_single_generation_asset_with_storage_remains_one_event() -> None:
    title = "Resolución por la que se autoriza la planta solar Alfa con BESS Alfa."
    text = (
        "La planta solar fotovoltaica Alfa incorpora el sistema de almacenamiento "
        "BESS Alfa."
    )
    canonical, _ = _canonicalize_test_event(
        boe_id="BOE-A-2026-99006",
        title=title,
        text=text,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Alfa",
                )
            ],
            associated_components=[
                AssociatedComponent(
                    local_component_ref="component_1",
                    component_type=AssociatedComponentType.ENERGY_STORAGE,
                    names_raw=["BESS Alfa"],
                    description_raw="sistema de almacenamiento BESS Alfa",
                    related_generation_asset_refs=["generation_asset_1"],
                    evidence="sistema de almacenamiento BESS Alfa",
                )
            ],
            administrative_actions=[_authorization_action(title)],
            event_summary="Una planta con almacenamiento asociado.",
        ),
    )

    assert len(canonical.publication_events) == 1


def test_accumulated_procedure_does_not_integrate_generation_assets() -> None:
    title = "Resolución por la que se autorizan las plantas solares Alfa y Beta."
    text = (
        "La planta solar fotovoltaica Alfa y la planta solar fotovoltaica Beta "
        "son instalaciones independientes. Sus expedientes se acumularon en un "
        "único procedimiento ambiental."
    )
    canonical, _ = _canonicalize_test_event(
        boe_id="BOE-A-2026-99007",
        title=title,
        text=text,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Alfa",
                ),
                _asset(
                    "generation_asset_2",
                    "Beta",
                    GenerationType.PHOTOVOLTAIC,
                    "planta solar fotovoltaica Beta",
                ),
            ],
            administrative_actions=[_authorization_action(title)],
            event_summary="Procedimiento acumulado de dos plantas independientes.",
        ),
    )

    assert len(canonical.publication_events) == 2


@pytest.mark.parametrize("reverse_aliases", [False, True], ids=["documental-first", "alias-first"])
def test_generation_relation_support_is_independent_of_alias_order(
    reverse_aliases: bool,
) -> None:
    title = "Resolución relativa a Formal Alfa y Formal Beta."
    evidence = "Alias Alfa se hibrida con Alias Beta."
    alias_pairs = [
        ["Formal Alfa", "Alias Alfa"],
        ["Formal Beta", "Alias Beta"],
    ]
    if reverse_aliases:
        alias_pairs = [list(reversed(names)) for names in alias_pairs]

    canonical, _ = _canonicalize_test_event(
        boe_id="BOE-A-2026-99132",
        title=title,
        text=evidence,
        event=PublicationEvent(
            generation_assets=[
                GenerationAssetMention(
                    local_generation_asset_ref=f"generation_asset_{index}",
                    names_raw=names,
                    generation_type=GenerationType.PHOTOVOLTAIC,
                    technical_mentions=[],
                    evidence=title,
                )
                for index, names in enumerate(alias_pairs, start=1)
            ],
            administrative_actions=[_authorization_action(title)],
            generation_relations=[GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_2",
                relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                evidence=evidence,
            )],
            event_summary="Hibridación entre dos plantas con aliases documentales.",
        ),
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]
    assert len(canonical.publication_events[0].generation_relations) == 1


@pytest.mark.parametrize(
    ("short_name", "long_name"),
    [
        ("Los Naipes", "Los Naipes II"),
        ("Parque Solar X", "Parque Solar X II"),
        ("Encinar", "El Encinar I"),
    ],
)
def test_overlapping_name_requires_two_distinct_documentary_mentions(
    short_name: str,
    long_name: str,
) -> None:
    evidence = f"{long_name} se hibrida con un sistema de almacenamiento."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99101",
        names=[short_name, long_name],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


def test_overlapping_names_with_two_real_mentions_support_relation() -> None:
    evidence = "Los Naipes se hibrida materialmente con Los Naipes II."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99102",
        names=["Los Naipes", "Los Naipes II"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]


def test_longer_name_of_third_asset_cannot_support_short_name_endpoint() -> None:
    evidence = "Los Naipes II se hibrida materialmente con Parque Eólico Beta."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99112",
        names=["Los Naipes", "Los Naipes II", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            3,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
        1,
    ]


def test_crossing_name_spans_are_treated_as_ambiguous() -> None:
    evidence = "Los Naipes II se hibrida materialmente con Parque Eólico Beta."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99123",
        names=["Los Naipes", "Naipes II", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            3,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
        1,
    ]


def test_storage_name_occurrences_do_not_support_generation_relation() -> None:
    evidence = (
        "Módulos de almacenamiento Los Naipes y Naipes II, para su "
        "hibridación con las PSF existentes Los Naipes y Naipes II."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99113",
        names=["Los Naipes", "Naipes II"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


def test_extracted_relation_does_not_turn_ecological_substitution_into_integration() -> None:
    evidence = (
        "Las plantas Alfa y Beta se localizan junto a matorrales de "
        "sustitución termófilos."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99103",
        names=["Alfa", "Beta"],
        relation_specs=[(1, 2, GenerationRelationType.REPLACES, evidence)],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    ("relation_type", "evidence"),
    [
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibrida con un BESS y se tramita junto con "
            "Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa estudia la hibridación con BESS y comparte "
            "expediente con Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Solar Alfa sustituirá un transformador y se tramitará "
            "junto a Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Sustitución de Parque Eólico Beta descartada. El expediente fue "
            "promovido por Parque Solar Alfa.",
        ),
    ],
)
def test_distant_relational_vocabulary_does_not_support_relation(
    relation_type: GenerationRelationType,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99114",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(1, 2, relation_type, evidence)],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    ("evidence", "generation_types"),
    [
        (
            "El BESS se destina a la hibridación con la planta fotovoltaica "
            "Armus Solar. El parque eólico vecino no forma parte del proyecto.",
            [GenerationType.WIND, GenerationType.PHOTOVOLTAIC],
        ),
        (
            "La planta solar termoeléctrica Sol es una instalación híbrida con "
            "almacenamiento.",
            [GenerationType.CONCENTRATED_SOLAR_POWER, GenerationType.PHOTOVOLTAIC],
        ),
    ],
)
def test_same_name_requires_explicit_multitechnology_construction(
    evidence: str,
    generation_types: list[GenerationType],
) -> None:
    shared_name = "Armus Solar" if "Armus" in evidence else "Sol"
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99117",
        names=[shared_name, shared_name],
        generation_types=generation_types,
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


def test_same_name_types_cannot_be_taken_from_another_named_asset() -> None:
    evidence = (
        "La planta fotovoltaica Armus Solar se hibrida con el parque eólico "
        "Beta."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99121",
        names=["Armus Solar", "Armus Solar", "Beta"],
        generation_types=[
            GenerationType.PHOTOVOLTAIC,
            GenerationType.WIND,
            GenerationType.WIND,
        ],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
        1,
    ]


def test_shared_name_cannot_be_attributed_to_wrong_technology_endpoint() -> None:
    evidence = (
        "La planta fotovoltaica Armus Solar se hibrida con Parque Eólico Beta."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99135",
        names=["Armus Solar", "Armus Solar", "Parque Eólico Beta"],
        generation_types=[
            GenerationType.WIND,
            GenerationType.PHOTOVOLTAIC,
            GenerationType.WIND,
        ],
        relation_specs=[(
            1,
            3,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
        1,
    ]
    assert all(not event.generation_relations for event in canonical.publication_events)


def test_shared_name_type_cannot_belong_to_preceding_third_asset() -> None:
    evidence = (
        "El parque eólico Vecina cita Armus Solar, que se hibrida con la "
        "planta fotovoltaica Armus Solar."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99129",
        names=["Armus Solar", "Armus Solar", "Vecina"],
        generation_types=[
            GenerationType.WIND,
            GenerationType.PHOTOVOLTAIC,
            GenerationType.WIND,
        ],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
        1,
    ]


def test_repeated_shared_name_requires_technology_disambiguation() -> None:
    evidence = "Armus Solar se hibrida con Armus Solar."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99125",
        names=["Armus Solar", "Armus Solar"],
        generation_types=[GenerationType.WIND, GenerationType.PHOTOVOLTAIC],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
    ]


@pytest.mark.parametrize(
    "evidence",
    [
        (
            "El BESS asociado a la planta fotovoltaica Alfa para su hibridación "
            "con la planta fotovoltaica Beta."
        ),
        "Alfa BESS para su hibridación con Beta BESS.",
        "Alfa, módulo de almacenamiento, para su hibridación con Beta.",
        (
            "El BESS vinculado al parque fotovoltaico Alfa para su "
            "hibridación con la planta fotovoltaica Beta."
        ),
        "Alfa se hibrida con Beta, sistema de almacenamiento.",
        "Alfa se hibrida con Beta instalaciones de almacenamiento.",
        (
            "El BESS asociado con la planta fotovoltaica Alfa para su "
            "hibridación con la planta fotovoltaica Beta."
        ),
        (
            "El BESS perteneciente a la planta fotovoltaica Alfa para su "
            "hibridación con la planta fotovoltaica Beta."
        ),
        (
            "El sistema de baterías de la planta fotovoltaica Alfa para su "
            "hibridación con la planta fotovoltaica Beta."
        ),
    ],
)
def test_storage_subject_does_not_link_associated_generation_assets(
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99122",
        names=["Alfa", "Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    ("name", "generation_types", "evidence"),
    [
        (
            "Solgest-1",
            [GenerationType.CONCENTRATED_SOLAR_POWER, GenerationType.PHOTOVOLTAIC],
            "Planta Termosolar, híbrido con fotovoltaica, Solgest-1.",
        ),
        (
            "Armus Solar",
            [GenerationType.WIND, GenerationType.PHOTOVOLTAIC],
            "Hibridación de la instalación Armus Solar con tecnología eólica y "
            "fotovoltaica.",
        ),
        (
            "Armus Solar",
            [GenerationType.WIND, GenerationType.PHOTOVOLTAIC],
            "Hibridación de la instalación Armus Solar con tecnología eólica y "
            "fotovoltaica, denominada Armus Solar.",
        ),
    ],
)
def test_same_name_explicit_multitechnology_construction_is_supported(
    name: str,
    generation_types: list[GenerationType],
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99118",
        names=[name, name],
        generation_types=generation_types,
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]


@pytest.mark.parametrize(
    ("relation_type", "evidence"),
    [
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa no se hibridará con Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Solar Alfa no sustituirá a Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "No se autoriza que Parque Solar Alfa se hibrida con Parque Eólico "
            "Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Sin que por razón técnica alguna Parque Solar Alfa se pueda "
            "hibridar con Parque Eólico Beta.",
        ),
    ],
)
def test_negated_material_relation_is_not_supported(
    relation_type: GenerationRelationType,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99115",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(1, 2, relation_type, evidence)],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    "evidence",
    [
        pytest.param(
            "Parque Solar Alfa carece de hibridación con Parque Eólico Beta.",
            id="carece-de-hibridacion",
        ),
        pytest.param(
            "Parque Solar Alfa renuncia a la hibridación con Parque Eólico Beta.",
            id="renuncia-a-la-hibridacion",
        ),
        pytest.param(
            "Parque Solar Alfa dejó de hibridarse con Parque Eólico Beta.",
            id="dejo-de-hibridarse",
        ),
    ],
)
def test_explicitly_negative_hybridization_is_not_supported(
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99133",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]
    assert all(not event.generation_relations for event in canonical.publication_events)


def test_unrelated_administrative_negation_does_not_hide_positive_relation() -> None:
    evidence = (
        "No se autoriza X, pero Parque Solar Alfa se hibrida con Parque Eólico "
        "Beta."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99134",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]
    assert len(canonical.publication_events[0].generation_relations) == 1


@pytest.mark.parametrize(
    ("relation_type", "evidence"),
    [
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Hibridación de Parque Solar Alfa con Parque Eólico Beta queda "
            "descartada.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Solar Alfa sustituirá a Parque Eólico Beta, opción descartada.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibridará con Parque Eólico Beta no siendo "
            "autorizada dicha hibridación.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibridará con Parque Eólico Beta, relación "
            "no autorizada.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibridará con Parque Eólico Beta, sin "
            "autorización.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibridará con Parque Eólico Beta, "
            "hibridación denegada.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Solar Alfa sustituirá a Parque Eólico Beta, sustitución "
            "no autorizada.",
        ),
    ],
)
def test_explicitly_rejected_material_relation_is_not_supported(
    relation_type: GenerationRelationType,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99119",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(1, 2, relation_type, evidence)],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    ("source_text", "evidence"),
    [
        (
            "Parque Solar Alfa no se hibrida con Parque Eólico Beta.",
            "Parque Solar Alfa [...] se hibrida con Parque Eólico Beta",
        ),
        (
            "Parque Solar Alfa es independiente, mientras el sistema BESS se "
            "hibrida con Parque Eólico Beta.",
            "Parque Solar Alfa [...] se hibrida con Parque Eólico Beta",
        ),
        (
            "Parque Solar Alfa se hibrida con Parque Eólico Beta.",
            "Parque Solar Alfa [...] Parque Eólico Beta",
        ),
    ],
)
def test_composite_evidence_cannot_hide_relation_context(
    source_text: str,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99116",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
        text=source_text,
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    ("source_text", "evidence"),
    [
        (
            "No se autoriza que Parque Solar Alfa se hibrida con Parque Eólico "
            "Beta.",
            "Parque Solar Alfa se hibrida con Parque Eólico Beta",
        ),
        (
            "Parque Solar Alfa se hibrida con Parque Eólico Beta, opción "
            "descartada.",
            "Parque Solar Alfa se hibrida con Parque Eólico Beta",
        ),
        (
            "No se autoriza que Parque Solar Alfa se hibrida con Parque Eólico "
            "Beta.",
            "Parque Solar Alfa [...] se hibrida con Parque Eólico Beta",
        ),
    ],
)
def test_partial_evidence_cannot_hide_source_context(
    source_text: str,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99126",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
        text=source_text,
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize("boundary", [".", ";", ":"])
def test_relation_cannot_cross_unspaced_clause_boundary(boundary: str) -> None:
    evidence = (
        f"Parque Solar Alfa obtiene autorización{boundary}La instalación se "
        "hibrida con Parque Eólico Beta."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99130",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]


@pytest.mark.parametrize(
    ("relation_type", "evidence"),
    [
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa para su hibridación con Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Hibridación de Parque Solar Alfa con Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa será hibridada con Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa, sin modificar su potencia, se hibridará con "
            "Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibridará con el parque eólico, denominado "
            "Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Solar Alfa sustituirá a Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Eólico Beta será sustituido por Parque Solar Alfa.",
        ),
    ],
)
def test_explicit_material_relation_constructions_preserve_group(
    relation_type: GenerationRelationType,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99104",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(1, 2, relation_type, evidence)],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]


def test_ordered_composite_evidence_can_support_material_relation() -> None:
    first_fragment = "Parque Solar Alfa, de 40 MW"
    second_fragment = "se hibrida con Parque Eólico Beta"
    source_span = f"{first_fragment}, mediante un módulo común, y {second_fragment}."
    evidence = f"{first_fragment} [...] {second_fragment}"
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99105",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
        text=source_span,
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]


def test_coordinated_generation_assets_form_one_connected_group() -> None:
    evidence = (
        "Parque Solar Alfa y Parque Solar Gamma se hibridan con Parque Eólico "
        "Beta."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99124",
        names=["Parque Solar Alfa", "Parque Eólico Beta", "Parque Solar Gamma"],
        relation_specs=[
            (1, 2, GenerationRelationType.HYBRIDIZED_WITH, evidence),
            (3, 2, GenerationRelationType.HYBRIDIZED_WITH, evidence),
        ],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [3]
    assert len(canonical.publication_events[0].generation_relations) == 2


def test_relation_cue_is_assigned_to_its_actual_named_subject() -> None:
    evidence = (
        "Parque Solar Alfa observa cómo Parque Solar Gamma se hibrida con "
        "Parque Eólico Beta."
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99127",
        names=["Parque Solar Alfa", "Parque Eólico Beta", "Parque Solar Gamma"],
        relation_specs=[
            (1, 2, GenerationRelationType.HYBRIDIZED_WITH, evidence),
            (3, 2, GenerationRelationType.HYBRIDIZED_WITH, evidence),
        ],
    )

    assert [
        [asset.names_raw[0] for asset in event.generation_assets]
        for event in canonical.publication_events
    ] == [
        ["Parque Solar Alfa"],
        ["Parque Eólico Beta", "Parque Solar Gamma"],
    ]
    assert len(canonical.publication_events[1].generation_relations) == 1


@pytest.mark.parametrize(
    ("relation_type", "evidence"),
    [
        (
            GenerationRelationType.REPLACES,
            "Parque Eólico Beta observa cómo Parque Solar Gamma será "
            "sustituido por Parque Solar Alfa.",
        ),
        (
            GenerationRelationType.REPLACES,
            "Parque Solar Alfa sustituye a Parque Solar Gamma denominado "
            "Parque Eólico Beta.",
        ),
        (
            GenerationRelationType.HYBRIDIZED_WITH,
            "Parque Solar Alfa se hibrida con Parque Solar Gamma denominado "
            "Parque Eólico Beta.",
        ),
    ],
)
def test_relation_cue_cannot_skip_third_named_endpoint(
    relation_type: GenerationRelationType,
    evidence: str,
) -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99131",
        names=["Parque Solar Alfa", "Parque Eólico Beta", "Parque Solar Gamma"],
        relation_specs=[(1, 2, relation_type, evidence)],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [
        1,
        1,
        1,
    ]


def test_mixed_material_group_is_split_from_independent_asset() -> None:
    evidence = "Parque Solar Alfa se hibrida con Parque Solar Beta."
    canonical, adjustments = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99106",
        names=["Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"],
        relation_specs=[(
            1,
            2,
            GenerationRelationType.HYBRIDIZED_WITH,
            evidence,
        )],
    )

    assert [
        [asset.names_raw[0] for asset in event.generation_assets]
        for event in canonical.publication_events
    ] == [
        ["Parque Solar Alfa", "Parque Solar Beta"],
        ["Parque Solar Gamma"],
    ]
    assert len(canonical.publication_events[0].generation_relations) == 1
    assert canonical.publication_events[1].generation_relations == []
    assert any("2 grupos materiales" in item for item in adjustments)


def test_two_material_groups_are_split_and_relations_are_remapped() -> None:
    first_evidence = "Parque Solar Alfa se hibrida con Parque Solar Beta."
    second_evidence = "Parque Solar Gamma se hibrida con Parque Solar Delta."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99107",
        names=[
            "Parque Solar Alfa",
            "Parque Solar Beta",
            "Parque Solar Gamma",
            "Parque Solar Delta",
        ],
        relation_specs=[
            (1, 2, GenerationRelationType.HYBRIDIZED_WITH, first_evidence),
            (3, 4, GenerationRelationType.HYBRIDIZED_WITH, second_evidence),
        ],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2, 2]
    assert [
        (
            event.generation_relations[0].source_generation_asset_ref,
            event.generation_relations[0].target_generation_asset_ref,
        )
        for event in canonical.publication_events
    ] == [
        ("generation_asset_1", "generation_asset_2"),
        ("generation_asset_1", "generation_asset_2"),
    ]


def test_connected_material_relation_chain_remains_one_event() -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99108",
        names=["Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"],
        relation_specs=[
            (
                1,
                2,
                GenerationRelationType.HYBRIDIZED_WITH,
                "Parque Solar Alfa se hibrida con Parque Solar Beta.",
            ),
            (
                2,
                3,
                GenerationRelationType.HYBRIDIZED_WITH,
                "Parque Solar Beta se hibrida con Parque Solar Gamma.",
            ),
        ],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [3]
    assert len(canonical.publication_events[0].generation_relations) == 2


def test_connected_group_discards_unsupported_internal_relation() -> None:
    weak_evidence = (
        "Parque Solar Alfa y Parque Solar Gamma se sitúan junto a matorrales "
        "de sustitución termófilos."
    )
    canonical, adjustments = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99111",
        names=["Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"],
        relation_specs=[
            (
                1,
                2,
                GenerationRelationType.HYBRIDIZED_WITH,
                "Parque Solar Alfa se hibrida con Parque Solar Beta.",
            ),
            (
                2,
                3,
                GenerationRelationType.HYBRIDIZED_WITH,
                "Parque Solar Beta se hibrida con Parque Solar Gamma.",
            ),
            (1, 3, GenerationRelationType.REPLACES, weak_evidence),
        ],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [3]
    assert [
        relation.relation_type
        for relation in canonical.publication_events[0].generation_relations
    ] == [
        GenerationRelationType.HYBRIDIZED_WITH,
        GenerationRelationType.HYBRIDIZED_WITH,
    ]
    assert any(
        "1 relación entre plantas descartada por soporte documental insuficiente"
        in adjustment
        for adjustment in adjustments
    )


@pytest.mark.parametrize("weak_relation_first", [True, False])
def test_duplicate_relation_prefers_documentarily_supported_evidence(
    weak_relation_first: bool,
) -> None:
    weak_evidence = (
        "Parque Solar Alfa y Parque Solar Beta estudian la hibridación con "
        "baterías independientes."
    )
    strong_evidence = "Parque Solar Alfa se hibrida con Parque Solar Beta."
    evidence_order = (
        [weak_evidence, strong_evidence]
        if weak_relation_first
        else [strong_evidence, weak_evidence]
    )
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99120",
        names=["Parque Solar Alfa", "Parque Solar Beta"],
        relation_specs=[
            (1, 2, GenerationRelationType.HYBRIDIZED_WITH, evidence)
            for evidence in evidence_order
        ],
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [2]
    assert canonical.publication_events[0].generation_relations[0].evidence == (
        strong_evidence
    )


def test_relation_with_discarded_endpoint_cannot_attach_to_renumbered_asset() -> None:
    title = "Resolución relativa a Parque Solar Alfa y Parque Solar Beta."
    relation_evidence = "Parque Solar Alfa sustituirá a Parque Solar Beta."
    canonical, adjustments = _canonicalize_test_event(
        boe_id="BOE-A-2026-99128",
        title=title,
        text=relation_evidence,
        event=PublicationEvent(
            generation_assets=[
                _asset(
                    "generation_asset_1",
                    "Parque Solar Fantasma",
                    GenerationType.PHOTOVOLTAIC,
                    "Parque Solar Fantasma",
                ),
                _asset(
                    "generation_asset_2",
                    "Parque Solar Alfa",
                    GenerationType.PHOTOVOLTAIC,
                    title,
                ),
                _asset(
                    "generation_asset_3",
                    "Parque Solar Beta",
                    GenerationType.PHOTOVOLTAIC,
                    title,
                ),
            ],
            administrative_actions=[_authorization_action(title)],
            generation_relations=[GenerationAssetRelation(
                source_generation_asset_ref="generation_asset_1",
                target_generation_asset_ref="generation_asset_3",
                relation_type=GenerationRelationType.REPLACES,
                evidence=relation_evidence,
            )],
            event_summary="Relación cuyo extremo no es documental.",
        ),
    )

    assert [
        [asset.names_raw[0] for asset in event.generation_assets]
        for event in canonical.publication_events
    ] == [["Parque Solar Alfa"], ["Parque Solar Beta"]]
    assert all(not event.generation_relations for event in canonical.publication_events)
    assert any(
        "relación entre plantas descartada al eliminar un extremo no documental"
        in adjustment
        for adjustment in adjustments
    )


def test_three_assets_without_relations_become_three_groups() -> None:
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99109",
        names=["Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"],
        relation_specs=[],
        text="Las tres plantas son proyectos independientes.",
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1, 1]


def test_document_text_never_autocompletes_missing_generation_relations() -> None:
    evidence = "Parque Solar Alfa se hibrida con Parque Eólico Beta."
    canonical, _ = _canonicalize_generation_relation_scenario(
        boe_id="BOE-A-2026-99136",
        names=["Parque Solar Alfa", "Parque Eólico Beta"],
        relation_specs=[],
        text=evidence,
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]
    assert all(not event.generation_relations for event in canonical.publication_events)


def test_multitechnology_expansion_never_synthesizes_generation_relation() -> None:
    evidence = "Planta Termosolar, híbrido con fotovoltaica, Solgest-1."
    canonical, _ = _canonicalize_test_event(
        boe_id="BOE-A-2026-99137",
        title="Resolución relativa a Solgest-1.",
        text=evidence,
        event=PublicationEvent(
            generation_assets=[_asset(
                "generation_asset_1",
                "Solgest-1",
                GenerationType.OTHER_GENERATION,
                evidence,
                technical_mentions=[
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.OTHER,
                        value_raw="Planta Termosolar",
                        evidence="Planta Termosolar",
                    ),
                    TechnicalMention(
                        attribute_type=TechnicalAttributeType.OTHER,
                        value_raw="fotovoltaica",
                        evidence="fotovoltaica",
                    ),
                ],
            )],
            administrative_actions=[_authorization_action(evidence)],
            generation_relations=[],
            event_summary="Instalación híbrida multitecnología.",
        ),
    )

    assert [len(event.generation_assets) for event in canonical.publication_events] == [1, 1]
    assert all(not event.generation_relations for event in canonical.publication_events)


def test_split_keeps_concrete_action_only_where_its_target_survives() -> None:
    action_evidence = "Se autoriza exclusivamente Parque Solar Gamma."
    event, relation_evidence = _three_asset_event_for_split(
        administrative_actions=[_action(
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.AUTHORIZED,
            action_evidence,
            ["generation_asset_3"],
        )],
    )
    original_json = event.model_dump_json()

    split_events, adjustments = _split_independent_generation_event(
        event,
        source_text=f"{relation_evidence} {action_evidence}",
    )

    assert [len(item.generation_assets) for item in split_events] == [1]
    assert len(split_events[0].administrative_actions) == 1
    assert split_events[0].administrative_actions[0].targets == [
        "generation_asset_1"
    ]
    assert any(
        "grupo material" in adjustment.casefold()
        and "actuación vinculada" in adjustment.casefold()
        for adjustment in adjustments
    )
    assert event.model_dump_json() == original_json


def test_split_drops_component_without_generation_links() -> None:
    component_evidence = "Subestación Compartida, de 220 kV."
    component = AssociatedComponent(
        local_component_ref="component_1",
        component_type=AssociatedComponentType.ELECTRICAL_SUBSTATION,
        names_raw=["Subestación Compartida"],
        description_raw="subestación compartida de 220 kV",
        related_generation_asset_refs=[],
        evidence=component_evidence,
    )
    event, relation_evidence = _three_asset_event_for_split(
        administrative_actions=[_authorization_action("Se autoriza el proyecto.")],
        associated_components=[component],
    )
    original_json = event.model_dump_json()

    split_events, adjustments = _split_independent_generation_event(
        event,
        source_text=f"{relation_evidence} {component_evidence}",
    )

    assert [len(item.generation_assets) for item in split_events] == [2, 1]
    assert all(not item.associated_components for item in split_events)
    assert any(
        "componente" in adjustment.casefold()
        and "víncul" in adjustment.casefold()
        and "descartad" in adjustment.casefold()
        for adjustment in adjustments
    )
    assert event.model_dump_json() == original_json


def test_group_split_preserves_input_and_filters_component_links_and_targets() -> None:
    evidence = "Parque Solar Alfa se hibrida con Parque Solar Beta."
    event = PublicationEvent(
        generation_assets=[
            _asset(
                f"generation_asset_{index}",
                name,
                GenerationType.PHOTOVOLTAIC,
                name,
            )
            for index, name in enumerate(
                ("Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"),
                start=1,
            )
        ],
        associated_components=[AssociatedComponent(
            local_component_ref="component_1",
            component_type=AssociatedComponentType.EVACUATION_SYSTEM,
            names_raw=["Línea compartida"],
            description_raw="línea eléctrica compartida",
            related_generation_asset_refs=[
                "generation_asset_1",
                "generation_asset_3",
            ],
            evidence="línea eléctrica compartida",
        )],
        administrative_actions=[_action(
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.AUTHORIZED,
            "Se autoriza el proyecto.",
            ["generation_asset_1", "component_1"],
        )],
        generation_relations=[GenerationAssetRelation(
            source_generation_asset_ref="generation_asset_1",
            target_generation_asset_ref="generation_asset_2",
            relation_type=GenerationRelationType.HYBRIDIZED_WITH,
            evidence=evidence,
        )],
        event_summary="Dos plantas integradas y una independiente.",
    )
    original_json = event.model_dump_json()
    split_events, _ = _split_independent_generation_event(
        event,
        source_text=f"{evidence} Existe una línea eléctrica compartida.",
    )

    first_event, second_event = split_events
    assert [len(event.associated_components) for event in (first_event, second_event)] == [1, 1]
    assert first_event.associated_components[0].related_generation_asset_refs == [
        "generation_asset_1"
    ]
    assert second_event.associated_components[0].related_generation_asset_refs == [
        "generation_asset_1"
    ]
    assert first_event.administrative_actions[0].targets == [
        "generation_asset_1",
        "component_1",
    ]
    assert second_event.administrative_actions[0].targets == ["component_1"]
    assert event.model_dump_json() == original_json


def test_generic_title_preserves_unfavorable_environmental_statement() -> None:
    title = (
        "Resolución por la que se formula declaración de impacto ambiental "
        "de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        source_text=f"{title} La declaración de impacto ambiental es desfavorable.",
        actions=[
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
                AdministrativeDecision.UNFAVORABLE,
                "La declaración de impacto ambiental es desfavorable.",
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.UNFAVORABLE


def test_generic_title_preserves_terminal_environmental_screening() -> None:
    title = (
        "Resolución por la que se formula informe de impacto ambiental "
        "de la planta solar fotovoltaica Prueba."
    )
    conclusion = "No se prevén efectos adversos significativos."
    actions, _ = _canonicalize_test_actions(
        title=title,
        source_text=f"{title} {conclusion}",
        actions=[
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
                conclusion,
                ["event"],
            )
        ],
    )

    assert (
        actions[0].decision
        == AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS
    )


def test_formulated_remains_environmental_fallback_without_adjustment() -> None:
    title = (
        "Resolución por la que se formula informe de impacto ambiental "
        "de la planta solar fotovoltaica Prueba."
    )
    actions, adjustments = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
                AdministrativeDecision.FORMULATED,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.FORMULATED
    assert not any("decisión" in adjustment for adjustment in adjustments)


@pytest.mark.parametrize(
    ("action_type", "terminal_decision", "product_title"),
    [
        (
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
            AdministrativeDecision.FAVORABLE,
            "declaración de impacto ambiental",
        ),
        (
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
            AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
            "informe de impacto ambiental",
        ),
        (
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
            AdministrativeDecision.FAVORABLE,
            "informe de determinación de afección ambiental",
        ),
        (
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
            AdministrativeDecision.UNFAVORABLE,
            "informe de determinación de afección ambiental",
        ),
        (
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
            AdministrativeDecision.FURTHER_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
            "informe de determinación de afección ambiental",
        ),
        (
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
            AdministrativeDecision.FURTHER_ENVIRONMENTAL_ASSESSMENT_NOT_REQUIRED,
            "informe de determinación de afección ambiental",
        ),
    ],
)
def test_generic_environmental_title_preserves_other_terminal_decisions(
    action_type: AdministrativeActionType,
    terminal_decision: AdministrativeDecision,
    product_title: str,
) -> None:
    title = (
        f"Resolución por la que se formula {product_title} de la planta solar "
        "fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                action_type,
                terminal_decision,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == terminal_decision


def test_withdrawn_authorization_request_is_not_canonicalized_as_granted() -> None:
    title = (
        "Resolución por la que se acepta el desistimiento de la solicitud de "
        "autorización administrativa previa de la planta solar fotovoltaica "
        "Prueba y se archiva el expediente."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PROCEDURE_TERMINATION,
                AdministrativeDecision.WITHDRAWN,
                title,
                ["event"],
            )
        ],
    )

    assert any(
        action.action_type == AdministrativeActionType.PROCEDURE_TERMINATION
        and action.decision == AdministrativeDecision.WITHDRAWN
        for action in actions
    )
    assert not any(
        action.action_type
        == AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
        for action in actions
    )


def test_withdrawal_does_not_synthesize_multiple_object_procedures() -> None:
    title = (
        "Resolución por la que se acepta el desistimiento de las solicitudes de "
        "autorización administrativa previa, autorización administrativa de "
        "construcción y declaración de impacto ambiental de la planta solar "
        "fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PROCEDURE_TERMINATION,
                AdministrativeDecision.WITHDRAWN,
                title,
                ["event"],
            )
        ],
    )

    assert [action.action_type for action in actions] == [
        AdministrativeActionType.PROCEDURE_TERMINATION
    ]


@pytest.mark.parametrize(
    ("termination_wording", "termination_decision"),
    [
        (
            "se acuerda el archivo de la solicitud de",
            AdministrativeDecision.CLOSED,
        ),
        (
            "se declara la inadmisión de la solicitud de",
            AdministrativeDecision.INADMISSIBLE,
        ),
    ],
)
def test_other_terminations_do_not_synthesize_the_object_authorization(
    termination_wording: str,
    termination_decision: AdministrativeDecision,
) -> None:
    title = (
        f"Resolución por la que {termination_wording} autorización administrativa "
        "previa de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PROCEDURE_TERMINATION,
                termination_decision,
                title,
                ["event"],
            )
        ],
    )

    assert [(action.action_type, action.decision) for action in actions] == [
        (
            AdministrativeActionType.PROCEDURE_TERMINATION,
            termination_decision,
        )
    ]


def test_termination_title_does_not_remove_independent_body_action() -> None:
    title = (
        "Resolución por la que se acepta el desistimiento de la solicitud de "
        "autorización administrativa previa de una fase de la planta solar "
        "fotovoltaica Prueba."
    )
    granted_evidence = (
        "Asimismo, se otorga autorización administrativa previa para la segunda "
        "fase de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        source_text=f"{title} {granted_evidence}",
        actions=[
            _action(
                AdministrativeActionType.PROCEDURE_TERMINATION,
                AdministrativeDecision.WITHDRAWN,
                title,
                ["event"],
            ),
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                granted_evidence,
                ["event"],
            ),
        ],
    )

    assert {
        (action.action_type, action.decision)
        for action in actions
    } == {
        (
            AdministrativeActionType.PROCEDURE_TERMINATION,
            AdministrativeDecision.WITHDRAWN,
        ),
        (
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.AUTHORIZED,
        ),
    }


@pytest.mark.parametrize("grant_wording", ["se otorga la", "se autoriza la"])
def test_granted_authorization_title_remains_authorized(
    grant_wording: str,
) -> None:
    title = (
        f"Resolución por la que {grant_wording} autorización administrativa previa "
        "de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.REQUESTED,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.AUTHORIZED


def test_denied_authorization_title_remains_current_denial() -> None:
    title = (
        "Resolución por la que se deniega la autorización administrativa previa "
        "de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.REQUESTED,
                title,
                ["event"],
            )
        ],
    )

    assert [(action.action_type, action.decision) for action in actions] == [
        (
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            AdministrativeDecision.DENIED,
        )
    ]


@pytest.mark.parametrize(
    "decision_wording",
    [
        "se desestima la solicitud de",
        "la solicitud desestimada de",
        "se declara desestimado el procedimiento de",
        "se resuelve la desestimación de la solicitud de",
        "se acuerda desestimar la solicitud de",
    ],
)
def test_desestimation_wording_is_a_terminal_authorization_decision(
    decision_wording: str,
) -> None:
    title = (
        f"Resolución por la que {decision_wording} autorización administrativa "
        "previa de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title.upper(),
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.UNKNOWN,
                title,
                ["event"],
            )
        ],
        source_text=title,
    )

    assert actions[0].decision.value == "desestimado"


@pytest.mark.parametrize(
    "existing_decision",
    [
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.DENIED,
    ],
)
def test_explicit_desestimation_refines_existing_authorization_decision(
    existing_decision: AdministrativeDecision,
) -> None:
    title = (
        "Resolución por la que se desestima la solicitud de autorización "
        "administrativa previa de la planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                existing_decision,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision.value == "desestimado"


def test_generic_request_title_does_not_degrade_existing_denial() -> None:
    title = (
        "Anuncio de solicitud de autorización administrativa previa para la "
        "planta solar fotovoltaica Prueba."
    )
    actions, adjustments = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.DENIED,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.DENIED
    assert not any("decisión canonicalizada" in item for item in adjustments)


def test_unrelated_desestimation_does_not_override_explicit_authorization_grant() -> None:
    title = (
        "Resolución por la que se desestiman las alegaciones y se otorga la "
        "autorización administrativa previa de la planta solar fotovoltaica "
        "Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.REQUESTED,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.AUTHORIZED


def test_desestimated_authorization_and_archived_termination_remain_separate() -> None:
    title = (
        "Resolución por la que se desestima la solicitud de autorización "
        "administrativa previa de la planta solar fotovoltaica Prueba."
    )
    archive_evidence = (
        "Desestimar la solicitud de autorización administrativa previa, "
        "acordando el archivo del expediente PFot-Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        source_text=f"{title} {archive_evidence}",
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.UNKNOWN,
                title,
                ["event"],
            ),
            _action(
                AdministrativeActionType.PROCEDURE_TERMINATION,
                AdministrativeDecision.CLOSED,
                archive_evidence,
                ["event"],
            ),
        ],
    )

    assert [(action.action_type.value, action.decision.value) for action in actions] == [
        ("autorizacion_administrativa_previa", "desestimado"),
        ("terminacion_procedimiento", "archivado"),
    ]


@pytest.mark.parametrize(
    ("boe_id", "title", "precanonical_decision", "archive_evidence"),
    [
        (
            "BOE-A-2025-26112",
            "Resolución de 3 de diciembre de 2025, de la Dirección General de "
            "Política Energética y Minas, por la que se desestima la solicitud "
            "de Benbros Solar IV, SL, de autorización administrativa previa de "
            "la instalación fotovoltaica FV Vizmalo, de 113,016 MW de potencia "
            "instalada, y de su infraestructura de evacuación, en las provincias "
            "de Burgos y Palencia.",
            AdministrativeDecision.UNKNOWN,
            "Desestimar la solicitud de autorización administrativa previa de la "
            "instalación fotovoltaica FV Vizmalo, acordando el archivo del "
            "expediente PFot-1098.",
        ),
        (
            "BOE-A-2026-9582",
            "Resolución de 16 de abril de 2026, de la Dirección General de "
            "Política Energética y Minas, por la que se desestima la solicitud "
            "de FRV Sotillos, SLU, de autorización administrativa previa del "
            "parque eólico «Crecente», de 54 MW de potencia instalada, y de su "
            "infraestructura de evacuación, en la provincia de Pontevedra.",
            AdministrativeDecision.DENIED,
            None,
        ),
        (
            "BOE-A-2024-16662",
            "Resolución de 10 de julio de 2024, de la Dirección General de "
            "Política Energética y Minas, por la que se desestima la solicitud "
            "de El Refugio Fotovoltaico, SLU, de autorización administrativa "
            "previa del parque fotovoltaico El Refugio, de 116,55 MW de potencia "
            "instalada, y de su infraestructura de evacuación, en las provincias "
            "de Toledo y Madrid.",
            AdministrativeDecision.UNKNOWN,
            None,
        ),
    ],
)
def test_known_desestimation_titles_are_canonicalized_as_desestimated(
    boe_id: str,
    title: str,
    precanonical_decision: AdministrativeDecision,
    archive_evidence: str | None,
) -> None:
    actions = [
        _action(
            AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
            precanonical_decision,
            title,
            ["event"],
        )
    ]
    if archive_evidence is not None:
        actions.append(_action(
            AdministrativeActionType.PROCEDURE_TERMINATION,
            AdministrativeDecision.CLOSED,
            archive_evidence,
            ["event"],
        ))
    extraction = _test_extraction(
        boe_id,
        [
            PublicationEvent(
                generation_assets=[
                    _asset(
                        "generation_asset_1",
                        "Prueba",
                        GenerationType.PHOTOVOLTAIC,
                        "planta solar fotovoltaica Prueba",
                    )
                ],
                administrative_actions=actions,
                event_summary="Actuación administrativa de la planta Prueba.",
            )
        ],
    )

    canonical, _ = canonicalize_project_extraction(
        extraction,
        source_text=" ".join(filter(None, [
            title,
            archive_evidence,
            "planta solar fotovoltaica Prueba",
        ])),
        document_title=title,
    )

    canonical_actions = canonical.publication_events[0].administrative_actions
    assert canonical_actions[0].decision.value == "desestimado"
    if archive_evidence is not None:
        assert [(action.action_type.value, action.decision.value) for action in canonical_actions] == [
            ("autorizacion_administrativa_previa", "desestimado"),
            ("terminacion_procedimiento", "archivado"),
        ]


def test_authorization_noun_alone_does_not_match_authorize_verb() -> None:
    title = (
        "Anuncio de solicitud de autorización administrativa previa para la "
        "planta solar fotovoltaica Prueba."
    )
    actions, _ = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.REQUESTED,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.REQUESTED


def test_effective_title_decision_change_is_recorded() -> None:
    title = (
        "Resolución por la que se otorga la autorización administrativa previa "
        "de la planta solar fotovoltaica Prueba."
    )
    actions, adjustments = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.REQUESTED,
                title,
                ["event"],
            )
        ],
    )

    assert actions[0].decision == AdministrativeDecision.AUTHORIZED
    decision_adjustments = [
        adjustment
        for adjustment in adjustments
        if adjustment.startswith("action_1: decisión canonicalizada desde el título:")
    ]
    assert len(decision_adjustments) == 1
    assert "solicitado" in decision_adjustments[0]
    assert "autorizado" in decision_adjustments[0]

    unchanged_actions, unchanged_adjustments = _canonicalize_test_actions(
        title=title,
        actions=[
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                title,
                ["event"],
            )
        ],
    )

    assert unchanged_actions[0].decision == AdministrativeDecision.AUTHORIZED
    assert not any(
        adjustment.startswith(
            "action_1: decisión canonicalizada desde el título:"
        )
        for adjustment in unchanged_adjustments
    )


@pytest.mark.parametrize(
    "incompatible_decision",
    [
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.WITHDRAWN,
    ],
)
def test_incompatible_decision_is_not_protected_as_environmental_terminal(
    incompatible_decision: AdministrativeDecision,
) -> None:
    assert _should_replace_decision_from_title(
        action_type=AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
        existing=incompatible_decision,
        inferred=AdministrativeDecision.FORMULATED,
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


@pytest.mark.parametrize(
    ("asset_names", "relation_pairs", "expected_group_sizes"),
    [
        pytest.param(
            ("Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"),
            (),
            [1, 1, 1],
            id="three-isolated-assets",
        ),
        pytest.param(
            ("Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"),
            ((1, 2),),
            [2, 1],
            id="one-pair-and-one-isolated",
        ),
        pytest.param(
            (
                "Parque Solar Alfa",
                "Parque Solar Beta",
                "Parque Solar Gamma",
                "Parque Solar Delta",
            ),
            ((1, 2), (3, 4)),
            [2, 2],
            id="two-independent-pairs",
        ),
        pytest.param(
            ("Parque Solar Alfa", "Parque Solar Beta", "Parque Solar Gamma"),
            ((1, 2), (2, 3)),
            [3],
            id="connected-chain",
        ),
    ],
)
def test_canonicalization_is_idempotent_for_material_graphs(
    asset_names: tuple[str, ...],
    relation_pairs: tuple[tuple[int, int], ...],
    expected_group_sizes: list[int],
) -> None:
    title = f"Resolución relativa a {', '.join(asset_names)}."
    relation_evidence = [
        f"{asset_names[source - 1]} se hibrida con {asset_names[target - 1]}."
        for source, target in relation_pairs
    ]
    extraction = _test_extraction(
        "BOE-A-2026-99990",
        [PublicationEvent(
            generation_assets=[
                _asset(
                    f"generation_asset_{index}",
                    name,
                    GenerationType.PHOTOVOLTAIC,
                    title,
                )
                for index, name in enumerate(asset_names, start=1)
            ],
            administrative_actions=[_authorization_action(title)],
            generation_relations=[
                GenerationAssetRelation(
                    source_generation_asset_ref=f"generation_asset_{source}",
                    target_generation_asset_ref=f"generation_asset_{target}",
                    relation_type=GenerationRelationType.HYBRIDIZED_WITH,
                    evidence=evidence,
                )
                for (source, target), evidence in zip(
                    relation_pairs,
                    relation_evidence,
                    strict=True,
                )
            ],
            event_summary="Grafo material para comprobar idempotencia.",
        )],
    )
    source_text = "\n".join([title, *relation_evidence])

    canonical_once, _ = canonicalize_project_extraction(
        extraction,
        source_text=source_text,
        document_title=title,
    )
    canonical_twice, second_adjustments = canonicalize_project_extraction(
        canonical_once,
        source_text=source_text,
        document_title=title,
    )

    assert [
        len(event.generation_assets) for event in canonical_once.publication_events
    ] == expected_group_sizes
    assert canonical_twice.model_dump_json() == canonical_once.model_dump_json()
    assert second_adjustments == []


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
