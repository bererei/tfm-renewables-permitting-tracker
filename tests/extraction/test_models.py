import copy
import hashlib
import json
from datetime import date

import pytest
from pydantic import TypeAdapter, ValidationError

from renewables_permitting.extraction.models import (
    BOE_ID_ADAPTER,
    ActionTargetRef,
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    AdministrativeLocationLevel,
    AssociatedComponentType,
    BOEAIExtraction,
    BOEId,
    BOEProjectExtraction,
    ClassificationStatus,
    ComponentRef,
    DocumentScope,
    GenerationAssetRef,
    GenerationRelationType,
    GenerationType,
    ParticipantRole,
    PublicationEvent,
    TechnicalAttributeType,
    TechnicalMention,
    build_boe_project_extraction,
)


EXPECTED_SCHEMA_SHA256 = (
    "7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c"
)


def _stable_json_hash(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _valid_event_payload() -> dict:
    return {
        "generation_assets": [
            {
                "local_generation_asset_ref": "generation_asset_1",
                "names_raw": ["Planta Solar Norte"],
                "generation_type": "fotovoltaica",
                "technical_mentions": [
                    {
                        "attribute_type": "potencia_instalada",
                        "value_raw": "50 MW",
                        "evidence": "potencia instalada de 50 MW",
                    }
                ],
                "evidence": "planta solar fotovoltaica Planta Solar Norte",
            },
            {
                "local_generation_asset_ref": "generation_asset_2",
                "names_raw": ["Parque Eólico Sur"],
                "generation_type": "eolica",
                "technical_mentions": [],
                "evidence": "parque eólico Parque Eólico Sur",
            },
        ],
        "associated_components": [
            {
                "local_component_ref": "component_1",
                "component_type": "almacenamiento",
                "names_raw": ["BESS Norte"],
                "description_raw": "sistema de almacenamiento BESS Norte",
                "related_generation_asset_refs": ["generation_asset_1"],
                "technical_mentions": [],
                "evidence": "sistema de almacenamiento BESS Norte",
            }
        ],
        "administrative_actions": [
            {
                "action_type": "autorizacion_administrativa_previa",
                "decision": "autorizado",
                "is_modification": False,
                "targets": ["generation_asset_1", "component_1"],
                "evidence": "se otorga autorización administrativa previa",
            }
        ],
        "participants": [],
        "administrative_locations": [],
        "generation_relations": [
            {
                "source_generation_asset_ref": "generation_asset_1",
                "target_generation_asset_ref": "generation_asset_2",
                "relation_type": "hibrida_con",
                "evidence": "Planta Solar Norte se hibrida con Parque Eólico Sur",
            }
        ],
        "case_file_references": ["PFot-123"],
        "event_summary": "Autorización de dos instalaciones relacionadas.",
    }


def _valid_project_extraction() -> BOEProjectExtraction:
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de proyecto.",
        publication_events=[_valid_event_payload()],
        extraction_notes=None,
        boe_id="BOE-A-2024-9608",
        publication_date=date(2024, 5, 13),
    )


def test_boe_ai_extraction_json_schema_hash_is_stable() -> None:
    assert (
        _stable_json_hash(BOEAIExtraction.model_json_schema())
        == EXPECTED_SCHEMA_SHA256
    )


def test_contract_rejects_additional_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TechnicalMention(
            attribute_type=TechnicalAttributeType.INSTALLED_POWER,
            value_raw="50 MW",
            evidence="potencia instalada de 50 MW",
            unexpected_field="no permitido",
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize(
    ("adapter", "valid_values", "invalid_values"),
    [
        (
            TypeAdapter(GenerationAssetRef),
            ["generation_asset_1", "generation_asset_10"],
            [
                "generation_asset_0",
                "generation_asset_01",
                "generation_asset",
                "component_1",
            ],
        ),
        (
            TypeAdapter(ComponentRef),
            ["component_1", "component_25"],
            ["component_0", "component_01", "component", "generation_asset_1"],
        ),
        (
            BOE_ID_ADAPTER,
            ["BOE-A-2024-9608", "BOE-B-2021-1"],
            ["BOE-C-2024-9608", "BOE-A-024-9608", "BOE-A-2024", "boe-A-2024-1"],
        ),
    ],
)
def test_reference_patterns(
    adapter: TypeAdapter,
    valid_values: list[str],
    invalid_values: list[str],
) -> None:
    for value in valid_values:
        assert adapter.validate_python(value) == value

    for value in invalid_values:
        with pytest.raises(ValidationError):
            adapter.validate_python(value)


def test_boe_id_type_alias_matches_exported_adapter() -> None:
    assert TypeAdapter(BOEId).validate_python("BOE-A-2024-9608") == (
        BOE_ID_ADAPTER.validate_python("BOE-A-2024-9608")
    )


def test_action_target_ref_pattern() -> None:
    adapter = TypeAdapter(ActionTargetRef)
    assert adapter.validate_python("event") == "event"
    assert adapter.validate_python("generation_asset_1") == "generation_asset_1"
    assert adapter.validate_python("component_1") == "component_1"

    with pytest.raises(ValidationError):
        adapter.validate_python("project_1")


@pytest.mark.parametrize(
    ("enum_type", "expected_members"),
    [
        (
            ClassificationStatus,
            [
                ("CLASSIFIED", "classified"),
                ("UNCERTAIN", "uncertain"),
            ],
        ),
        (
            DocumentScope,
            [
                (
                    "NOT_RELEVANT_FOR_GENERATION_PROJECTS",
                    "not_relevant_for_generation_projects",
                ),
                ("GENERATION_PROJECT_SPECIFIC", "generation_project_specific"),
            ],
        ),
        (
            GenerationType,
            [
                ("PHOTOVOLTAIC", "fotovoltaica"),
                ("WIND", "eolica"),
                ("CONCENTRATED_SOLAR_POWER", "termosolar"),
                ("HYDROPOWER", "hidroelectrica"),
                ("GEOTHERMAL", "geotermica"),
                ("BIOMASS", "biomasa"),
                ("BIOGAS", "biogas"),
                ("OTHER_GENERATION", "otra_generacion"),
            ],
        ),
        (
            AssociatedComponentType,
            [
                ("ENERGY_STORAGE", "almacenamiento"),
                ("EVACUATION_SYSTEM", "sistema_evacuacion"),
                ("ELECTRICAL_SUBSTATION", "subestacion_electrica"),
                ("POWER_LINE", "linea_electrica"),
                ("GRID_CONNECTION", "conexion_red"),
                ("OTHER_ASSOCIATED_COMPONENT", "otro_componente_asociado"),
            ],
        ),
        (
            TechnicalAttributeType,
            [
                ("INSTALLED_POWER", "potencia_instalada"),
                ("PEAK_POWER", "potencia_pico"),
                ("STORAGE_POWER", "potencia_almacenamiento"),
                ("STORAGE_CAPACITY", "capacidad_almacenamiento"),
                ("VOLTAGE", "tension"),
                ("UNIT_COUNT", "numero_unidades"),
                ("UNIT_POWER", "potencia_unitaria"),
                ("OTHER", "otra"),
            ],
        ),
        (
            ParticipantRole,
            [
                ("PROMOTER", "promotor"),
                ("CO_PROMOTER", "copromotor"),
                ("HOLDER", "titular"),
                ("OPERATOR", "operador"),
                ("APPLICANT", "solicitante"),
                ("TRANSFEROR", "cedente"),
                ("TRANSFEREE", "cesionario"),
                ("OTHER", "otro"),
                ("UNKNOWN", "desconocido"),
            ],
        ),
        (
            AdministrativeLocationLevel,
            [
                ("MUNICIPALITY", "municipio"),
                ("PROVINCE", "provincia"),
                ("AUTONOMOUS_COMMUNITY", "comunidad_autonoma"),
            ],
        ),
        (
            GenerationRelationType,
            [
                ("HYBRIDIZED_WITH", "hibrida_con"),
                ("REPLACES", "sustituye_a"),
            ],
        ),
        (
            AdministrativeActionType,
            [
                ("APPLICATION_SUBMISSION", "solicitud_tramitacion"),
                (
                    "ENVIRONMENTAL_APPLICATION_SUBMISSION",
                    "solicitud_tramitacion_ambiental",
                ),
                ("DOCUMENTATION_CORRECTION", "subsanacion_documentacion"),
                (
                    "REQUIREMENTS_VERIFICATION",
                    "verificacion_requisitos_tramitacion",
                ),
                ("ERROR_CORRECTION", "correccion_errores"),
                ("PUBLIC_INFORMATION", "informacion_publica"),
                (
                    "ENVIRONMENTAL_IMPACT_ASSESSMENT",
                    "evaluacion_impacto_ambiental",
                ),
                (
                    "ENVIRONMENTAL_IMPACT_STATEMENT",
                    "declaracion_impacto_ambiental",
                ),
                ("ENVIRONMENTAL_IMPACT_REPORT", "informe_impacto_ambiental"),
                (
                    "ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT",
                    "informe_determinacion_afeccion_ambiental",
                ),
                (
                    "PRIOR_ADMINISTRATIVE_AUTHORIZATION",
                    "autorizacion_administrativa_previa",
                ),
                (
                    "CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION",
                    "autorizacion_administrativa_construccion",
                ),
                ("OPERATING_AUTHORIZATION", "autorizacion_explotacion"),
                ("WATER_CONCESSION", "concesion_aguas"),
                ("PUBLIC_UTILITY_DECLARATION", "declaracion_utilidad_publica"),
                ("FORCED_EXPROPRIATION", "expropiacion_forzosa"),
                (
                    "AFFECTED_ASSETS_AND_RIGHTS_LIST",
                    "relacion_bienes_derechos_afectados",
                ),
                (
                    "PRIOR_OCCUPATION_RECORDS",
                    "levantamiento_actas_previas_ocupacion",
                ),
                ("OCCUPATION_RECORDS", "actas_ocupacion"),
                ("AUTHORIZATION_MODIFICATION", "modificacion_autorizacion"),
                ("DEADLINE_EXTENSION", "prorroga"),
                ("OWNERSHIP_CHANGE", "cambio_titularidad"),
                ("PROCEDURE_TERMINATION", "terminacion_procedimiento"),
                ("OTHER", "otro"),
                ("UNKNOWN", "desconocido"),
            ],
        ),
        (
            AdministrativeDecision,
            [
                ("REQUESTED", "solicitado"),
                ("CORRECTED", "subsanado"),
                ("REQUIREMENTS_VERIFIED", "requisitos_verificados"),
                ("RECTIFIED", "rectificado"),
                (
                    "SUBMITTED_TO_PUBLIC_INFORMATION",
                    "sometido_informacion_publica",
                ),
                ("ANNOUNCED", "convocado"),
                ("FORMULATED", "formulado"),
                ("FAVORABLE", "favorable"),
                ("UNFAVORABLE", "desfavorable"),
                (
                    "NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS",
                    "sin_efectos_adversos_significativos",
                ),
                (
                    "ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED",
                    "requiere_evaluacion_ambiental_ordinaria",
                ),
                (
                    "FURTHER_ENVIRONMENTAL_ASSESSMENT_REQUIRED",
                    "requiere_evaluacion_ambiental_adicional",
                ),
                (
                    "FURTHER_ENVIRONMENTAL_ASSESSMENT_NOT_REQUIRED",
                    "no_requiere_evaluacion_ambiental_adicional",
                ),
                ("AUTHORIZED", "autorizado"),
                ("DECLARED", "declarado"),
                ("MODIFIED", "modificado"),
                ("EXTENDED", "prorrogado"),
                ("DENIED", "denegado"),
                ("DESESTIMADO", "desestimado"),
                ("CLOSED", "archivado"),
                ("WITHDRAWN", "desistido"),
                ("INADMISSIBLE", "inadmitido"),
                ("OTHER", "otro"),
                ("UNKNOWN", "desconocido"),
            ],
        ),
    ],
)
def test_enum_members_are_exact(enum_type: type, expected_members: list) -> None:
    assert [(member.name, member.value) for member in enum_type] == expected_members


def test_prior_authorization_accepts_desestimated_decision() -> None:
    action = AdministrativeAction(
        action_type=AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
        decision="desestimado",
        targets=["event"],
        evidence="Se desestima la autorización administrativa previa.",
    )

    assert action.decision.value == "desestimado"


@pytest.mark.parametrize(
    "decision",
    [
        AdministrativeDecision.FORMULATED,
        AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
        AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
    ],
)
def test_idaa_accepts_approved_existing_decision_domain(
    decision: AdministrativeDecision,
) -> None:
    action = AdministrativeAction(
        action_type=(
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT
        ),
        decision=decision,
        targets=["event"],
        evidence="Se formula informe de determinación de afección ambiental.",
    )

    assert action.decision == decision


def test_legacy_energy_general_scope_is_supported() -> None:
    extraction = BOEAIExtraction(
        classification_status="classified",
        document_scope="energy_general",
        classification_reason="Publicación general del sector energético.",
        publication_events=[],
    )

    assert (
        extraction.document_scope
        == DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    )


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        (
            lambda event: event["generation_assets"][0].update(
                local_generation_asset_ref="generation_asset_2"
            ),
            "Las referencias de plantas deben ser consecutivas y estar ordenadas",
        ),
        (
            lambda event: event["associated_components"][0].update(
                local_component_ref="component_2"
            ),
            "Las referencias de componentes deben ser consecutivas y estar ordenadas",
        ),
        (
            lambda event: event["associated_components"][0].update(
                related_generation_asset_refs=["generation_asset_3"]
            ),
            "AssociatedComponent referencia plantas inexistentes",
        ),
        (
            lambda event: event["administrative_actions"][0].update(
                targets=["component_2"]
            ),
            "AdministrativeAction contiene targets inexistentes",
        ),
        (
            lambda event: event["generation_relations"][0].update(
                target_generation_asset_ref="generation_asset_3"
            ),
            "GenerationAssetRelation contiene referencias inexistentes",
        ),
    ],
)
def test_publication_event_rejects_invalid_references(
    mutation,
    expected_message: str,
) -> None:
    payload = copy.deepcopy(_valid_event_payload())
    mutation(payload)

    with pytest.raises(ValidationError, match=expected_message):
        PublicationEvent.model_validate(payload)


def test_generation_relation_cannot_be_self_referential() -> None:
    payload = copy.deepcopy(_valid_event_payload())
    payload["generation_relations"][0]["target_generation_asset_ref"] = (
        "generation_asset_1"
    )

    with pytest.raises(
        ValidationError,
        match="Una relación no puede ser autorreferencial",
    ):
        PublicationEvent.model_validate(payload)


def test_event_target_cannot_be_combined_with_concrete_references() -> None:
    payload = copy.deepcopy(_valid_event_payload())
    payload["administrative_actions"][0]["targets"] = [
        "event",
        "generation_asset_1",
    ]

    with pytest.raises(
        ValidationError,
        match="El target 'event' no puede combinarse con referencias concretas",
    ):
        PublicationEvent.model_validate(payload)


def test_build_project_extraction_preserves_ai_contract() -> None:
    ai_extraction = BOEAIExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Publicación específica de proyecto.",
        publication_events=[_valid_event_payload()],
    )

    project_extraction = build_boe_project_extraction(
        ai_extraction,
        boe_id="BOE-A-2024-9608",
        publication_date=date(2024, 5, 13),
    )

    assert project_extraction.boe_id == "BOE-A-2024-9608"
    assert project_extraction.publication_date == date(2024, 5, 13)
    assert (
        project_extraction.model_dump(exclude={"boe_id", "publication_date"})
        == ai_extraction.model_dump()
    )


def test_json_serialization_round_trip() -> None:
    extraction = _valid_project_extraction()

    serialized = extraction.model_dump_json()
    restored = BOEProjectExtraction.model_validate_json(serialized)

    assert restored == extraction
    assert restored.model_dump(mode="json") == extraction.model_dump(mode="json")
