import ast
import json
from datetime import date
from hashlib import sha256
from inspect import signature
from pathlib import Path

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


EXPECTED_CANONICALIZATION_SYMBOLS = {
    "ScopeGuardDecision",
    "_GENERATION_DESCRIPTOR_PATTERN",
    "_COMPONENT_PATTERNS",
    "_AUXILIARY_COMPONENT_TYPES",
    "_PROCUREMENT_TITLE_RE",
    "_NON_GENERATION_MAIN_OBJECT_RE",
    "_EXPLICIT_ELECTRIC_GENERATION_RE",
    "_AUXILIARY_RENEWABLE_RE",
    "_NON_ELECTRIC_GAS_INFRASTRUCTURE_RE",
    "_STANDALONE_STORAGE_MAIN_OBJECT_RE",
    "_STORAGE_LINKED_TO_GENERATION_RE",
    "_ACTION_PATTERNS",
    "_MODIFIABLE_ACTION_TYPES",
    "_canonical_documentary_text",
    "_documentary_contains",
    "_evidence_segments",
    "_evidence_is_supported",
    "_source_units",
    "_find_literal_span",
    "_repair_evidence",
    "_dedupe_technical_mentions",
    "_infer_generation_type",
    "_component_pattern",
    "_generation_name_is_direct_target",
    "_generation_refs_mentioned",
    "_component_refs_mentioned",
    "_entity_refs_mentioned",
    "_scope_guard_from_document",
    "_force_non_relevant_extraction",
    "preclassify_document_without_model",
    "_action_types_from_title",
    "_decision_from_title",
    "_modification_expectation",
    "_is_clearly_historical",
    "_repair_technical_mentions",
    "_salvage_generation_names",
    "_repair_generation_asset",
    "_expand_multitechnology_generation_assets",
    "_exact_component_description",
    "_repair_component",
    "_merge_auxiliary_components",
    "_infer_component_links",
    "_normalize_action_type",
    "_normalize_action_type_from_context",
    "_action_pattern",
    "_repair_action_evidence",
    "_infer_action_targets",
    "_canonicalize_actions",
    "_remap_component_targets",
    "_canonicalize_generation_relations",
    "_event_is_integrated",
    "_renumber_event",
    "_split_independent_generation_event",
    "_canonicalize_optional_mentions",
    "canonicalize_project_extraction",
}


def _node_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def test_canonicalization_nodes_match_notebook_ast() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb").read_text()
    )
    notebook_tree = ast.parse("".join(notebook["cells"][11]["source"]))
    module_tree = ast.parse(
        (
            project_root
            / "src"
            / "renewables_permitting"
            / "extraction"
            / "canonicalization.py"
        ).read_text()
    )

    notebook_nodes = [
        node
        for node in notebook_tree.body
        if _node_name(node) in EXPECTED_CANONICALIZATION_SYMBOLS
    ]
    module_nodes = [
        node
        for node in module_tree.body
        if _node_name(node) is not None
    ]

    assert [_node_name(node) for node in module_nodes] == [
        _node_name(node) for node in notebook_nodes
    ]
    assert {_node_name(node) for node in module_nodes} == (
        EXPECTED_CANONICALIZATION_SYMBOLS
    )

    notebook_by_name = {_node_name(node): node for node in notebook_nodes}
    module_by_name = {_node_name(node): node for node in module_nodes}
    for name in EXPECTED_CANONICALIZATION_SYMBOLS:
        assert ast.dump(
            module_by_name[name],
            include_attributes=False,
        ) == ast.dump(
            notebook_by_name[name],
            include_attributes=False,
        )


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
