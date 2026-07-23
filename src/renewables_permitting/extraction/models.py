from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Annotated, Any, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)
from typing_extensions import Self


NonEmptyText: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

GenerationAssetRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^generation_asset_[1-9][0-9]*$"),
]

ComponentRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^component_[1-9][0-9]*$"),
]

EntityRef: TypeAlias = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(?:generation_asset_[1-9][0-9]*|component_[1-9][0-9]*)$"
        )
    ),
]

ActionTargetRef: TypeAlias = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(?:event|generation_asset_[1-9][0-9]*|component_[1-9][0-9]*)$"
        )
    ),
]

BOEId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^BOE-[AB]-[0-9]{4}-[0-9]+$"),
]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


def _text_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _deduplicate_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _text_key(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _reference_sort_key(value: str) -> tuple[int, int]:
    if value == "event":
        return (0, 0)
    prefix, number = value.rsplit("_", 1)
    return (1 if prefix == "generation_asset" else 2, int(number))


def _canonicalize_refs(values: list[str]) -> list[str]:
    return sorted(set(values), key=_reference_sort_key)


class ClassificationStatus(str, Enum):
    CLASSIFIED = "classified"
    UNCERTAIN = "uncertain"


class DocumentScope(str, Enum):
    NOT_RELEVANT_FOR_GENERATION_PROJECTS = (
        "not_relevant_for_generation_projects"
    )
    GENERATION_PROJECT_SPECIFIC = "generation_project_specific"


class GenerationType(str, Enum):
    PHOTOVOLTAIC = "fotovoltaica"
    WIND = "eolica"
    CONCENTRATED_SOLAR_POWER = "termosolar"
    HYDROPOWER = "hidroelectrica"
    GEOTHERMAL = "geotermica"
    BIOMASS = "biomasa"
    BIOGAS = "biogas"
    OTHER_GENERATION = "otra_generacion"


class AssociatedComponentType(str, Enum):
    ENERGY_STORAGE = "almacenamiento"
    EVACUATION_SYSTEM = "sistema_evacuacion"
    ELECTRICAL_SUBSTATION = "subestacion_electrica"
    POWER_LINE = "linea_electrica"
    GRID_CONNECTION = "conexion_red"
    OTHER_ASSOCIATED_COMPONENT = "otro_componente_asociado"


class TechnicalAttributeType(str, Enum):
    INSTALLED_POWER = "potencia_instalada"
    PEAK_POWER = "potencia_pico"
    STORAGE_POWER = "potencia_almacenamiento"
    STORAGE_CAPACITY = "capacidad_almacenamiento"
    VOLTAGE = "tension"
    UNIT_COUNT = "numero_unidades"
    UNIT_POWER = "potencia_unitaria"
    OTHER = "otra"


class ParticipantRole(str, Enum):
    PROMOTER = "promotor"
    CO_PROMOTER = "copromotor"
    HOLDER = "titular"
    OPERATOR = "operador"
    APPLICANT = "solicitante"
    TRANSFEROR = "cedente"
    TRANSFEREE = "cesionario"
    OTHER = "otro"
    UNKNOWN = "desconocido"


class AdministrativeLocationLevel(str, Enum):
    MUNICIPALITY = "municipio"
    PROVINCE = "provincia"
    AUTONOMOUS_COMMUNITY = "comunidad_autonoma"


class GenerationRelationType(str, Enum):
    HYBRIDIZED_WITH = "hibrida_con"
    REPLACES = "sustituye_a"


class AdministrativeActionType(str, Enum):
    APPLICATION_SUBMISSION = "solicitud_tramitacion"
    ENVIRONMENTAL_APPLICATION_SUBMISSION = "solicitud_tramitacion_ambiental"
    DOCUMENTATION_CORRECTION = "subsanacion_documentacion"
    REQUIREMENTS_VERIFICATION = "verificacion_requisitos_tramitacion"
    ERROR_CORRECTION = "correccion_errores"
    PUBLIC_INFORMATION = "informacion_publica"
    ENVIRONMENTAL_IMPACT_ASSESSMENT = "evaluacion_impacto_ambiental"
    ENVIRONMENTAL_IMPACT_STATEMENT = "declaracion_impacto_ambiental"
    ENVIRONMENTAL_IMPACT_REPORT = "informe_impacto_ambiental"
    ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT = (
        "informe_determinacion_afeccion_ambiental"
    )
    PRIOR_ADMINISTRATIVE_AUTHORIZATION = "autorizacion_administrativa_previa"
    CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION = (
        "autorizacion_administrativa_construccion"
    )
    OPERATING_AUTHORIZATION = "autorizacion_explotacion"
    WATER_CONCESSION = "concesion_aguas"
    PUBLIC_UTILITY_DECLARATION = "declaracion_utilidad_publica"
    FORCED_EXPROPRIATION = "expropiacion_forzosa"
    AFFECTED_ASSETS_AND_RIGHTS_LIST = "relacion_bienes_derechos_afectados"
    PRIOR_OCCUPATION_RECORDS = "levantamiento_actas_previas_ocupacion"
    OCCUPATION_RECORDS = "actas_ocupacion"
    AUTHORIZATION_MODIFICATION = "modificacion_autorizacion"
    DEADLINE_EXTENSION = "prorroga"
    OWNERSHIP_CHANGE = "cambio_titularidad"
    PROCEDURE_TERMINATION = "terminacion_procedimiento"
    OTHER = "otro"
    UNKNOWN = "desconocido"


class AdministrativeDecision(str, Enum):
    REQUESTED = "solicitado"
    CORRECTED = "subsanado"
    REQUIREMENTS_VERIFIED = "requisitos_verificados"
    RECTIFIED = "rectificado"
    SUBMITTED_TO_PUBLIC_INFORMATION = "sometido_informacion_publica"
    ANNOUNCED = "convocado"
    FORMULATED = "formulado"
    FAVORABLE = "favorable"
    UNFAVORABLE = "desfavorable"
    NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS = (
        "sin_efectos_adversos_significativos"
    )
    ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED = (
        "requiere_evaluacion_ambiental_ordinaria"
    )
    FURTHER_ENVIRONMENTAL_ASSESSMENT_REQUIRED = (
        "requiere_evaluacion_ambiental_adicional"
    )
    FURTHER_ENVIRONMENTAL_ASSESSMENT_NOT_REQUIRED = (
        "no_requiere_evaluacion_ambiental_adicional"
    )
    AUTHORIZED = "autorizado"
    DECLARED = "declarado"
    MODIFIED = "modificado"
    EXTENDED = "prorrogado"
    DENIED = "denegado"
    CLOSED = "archivado"
    WITHDRAWN = "desistido"
    INADMISSIBLE = "inadmitido"
    OTHER = "otro"
    UNKNOWN = "desconocido"


_ALLOWED_DECISIONS_BY_ACTION_TYPE: dict[
    AdministrativeActionType,
    set[AdministrativeDecision],
] = {
    AdministrativeActionType.APPLICATION_SUBMISSION: {
        AdministrativeDecision.REQUESTED,
    },
    AdministrativeActionType.ENVIRONMENTAL_APPLICATION_SUBMISSION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
    },
    AdministrativeActionType.DOCUMENTATION_CORRECTION: {
        AdministrativeDecision.CORRECTED,
    },
    AdministrativeActionType.REQUIREMENTS_VERIFICATION: {
        AdministrativeDecision.REQUIREMENTS_VERIFIED,
    },
    AdministrativeActionType.ERROR_CORRECTION: {
        AdministrativeDecision.RECTIFIED,
    },
    AdministrativeActionType.PUBLIC_INFORMATION: {
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.ANNOUNCED,
    },
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_ASSESSMENT: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
    },
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT: {
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.FORMULATED,
        AdministrativeDecision.FAVORABLE,
        AdministrativeDecision.UNFAVORABLE,
    },
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT: {
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.FORMULATED,
        AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
        AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
    },
    AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT: {
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.FORMULATED,
        AdministrativeDecision.FAVORABLE,
        AdministrativeDecision.UNFAVORABLE,
        AdministrativeDecision.FURTHER_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
        AdministrativeDecision.FURTHER_ENVIRONMENTAL_ASSESSMENT_NOT_REQUIRED,
    },
    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.OPERATING_AUTHORIZATION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.WATER_CONCESSION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.PUBLIC_UTILITY_DECLARATION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.DECLARED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.FORCED_EXPROPRIATION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.DECLARED,
        AdministrativeDecision.ANNOUNCED,
    },
    AdministrativeActionType.AFFECTED_ASSETS_AND_RIGHTS_LIST: {
        AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
        AdministrativeDecision.ANNOUNCED,
    },
    AdministrativeActionType.PRIOR_OCCUPATION_RECORDS: {
        AdministrativeDecision.ANNOUNCED,
        AdministrativeDecision.FORMULATED,
    },
    AdministrativeActionType.OCCUPATION_RECORDS: {
        AdministrativeDecision.ANNOUNCED,
        AdministrativeDecision.FORMULATED,
    },
    AdministrativeActionType.AUTHORIZATION_MODIFICATION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.MODIFIED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.DEADLINE_EXTENSION: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.EXTENDED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.OWNERSHIP_CHANGE: {
        AdministrativeDecision.REQUESTED,
        AdministrativeDecision.AUTHORIZED,
        AdministrativeDecision.DENIED,
    },
    AdministrativeActionType.PROCEDURE_TERMINATION: {
        AdministrativeDecision.CLOSED,
        AdministrativeDecision.WITHDRAWN,
        AdministrativeDecision.INADMISSIBLE,
    },
}


class TechnicalMention(ContractModel):
    attribute_type: TechnicalAttributeType
    value_raw: NonEmptyText
    evidence: NonEmptyText


class GenerationAssetMention(ContractModel):
    """Planta de generación que será raíz de agrupación y búsqueda."""

    local_generation_asset_ref: GenerationAssetRef
    names_raw: list[NonEmptyText] = Field(min_length=1)
    generation_type: GenerationType
    technical_mentions: list[TechnicalMention] = Field(default_factory=list)
    evidence: NonEmptyText

    @field_validator("names_raw")
    @classmethod
    def canonicalize_names(cls, values: list[str]) -> list[str]:
        return _deduplicate_strings(values)


class AssociatedComponent(ContractModel):
    """Componente vinculado a plantas, pero nunca raíz de agrupación."""

    local_component_ref: ComponentRef
    component_type: AssociatedComponentType
    names_raw: list[NonEmptyText] = Field(default_factory=list)
    description_raw: NonEmptyText | None = None
    related_generation_asset_refs: list[GenerationAssetRef] = Field(
        default_factory=list
    )
    technical_mentions: list[TechnicalMention] = Field(default_factory=list)
    evidence: NonEmptyText

    @field_validator("names_raw")
    @classmethod
    def canonicalize_names(cls, values: list[str]) -> list[str]:
        return _deduplicate_strings(values)

    @field_validator("related_generation_asset_refs")
    @classmethod
    def canonicalize_related_refs(cls, values: list[str]) -> list[str]:
        return _canonicalize_refs(values)


class ParticipantMention(ContractModel):
    """Participante del proyecto representado por el PublicationEvent."""

    participant_name_raw: NonEmptyText
    participant_role: ParticipantRole
    evidence: NonEmptyText


class AdministrativeLocationMention(ContractModel):
    """Localización administrativa del proyecto representado por el evento."""

    location_name_raw: NonEmptyText
    location_level: AdministrativeLocationLevel
    province_hint_raw: NonEmptyText | None = None
    autonomous_community_hint_raw: NonEmptyText | None = None
    evidence: NonEmptyText

    @model_validator(mode="after")
    def validate_hints(self) -> Self:
        if (
            self.location_level == AdministrativeLocationLevel.PROVINCE
            and self.province_hint_raw is not None
        ):
            raise ValueError(
                "Una provincia no debe repetirse en province_hint_raw."
            )
        if self.location_level == AdministrativeLocationLevel.AUTONOMOUS_COMMUNITY:
            if self.province_hint_raw is not None or self.autonomous_community_hint_raw is not None:
                raise ValueError(
                    "Una comunidad autónoma no debe contener hints."
                )
        return self


class GenerationAssetRelation(ContractModel):
    source_generation_asset_ref: GenerationAssetRef
    target_generation_asset_ref: GenerationAssetRef
    relation_type: GenerationRelationType
    evidence: NonEmptyText

    @model_validator(mode="after")
    def validate_relation(self) -> Self:
        if self.source_generation_asset_ref == self.target_generation_asset_ref:
            raise ValueError("Una relación no puede ser autorreferencial.")
        return self


class AdministrativeAction(ContractModel):
    action_type: AdministrativeActionType
    decision: AdministrativeDecision
    is_modification: bool = False
    targets: list[ActionTargetRef] = Field(default_factory=list)
    evidence: NonEmptyText

    @field_validator("targets")
    @classmethod
    def canonicalize_targets(cls, values: list[str]) -> list[str]:
        return _canonicalize_refs(values)

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if "event" in self.targets and len(self.targets) != 1:
            raise ValueError(
                "El target 'event' no puede combinarse con referencias concretas."
            )
        if self.action_type not in {
            AdministrativeActionType.OTHER,
            AdministrativeActionType.UNKNOWN,
        } and self.decision not in {
            AdministrativeDecision.OTHER,
            AdministrativeDecision.UNKNOWN,
        }:
            allowed = _ALLOWED_DECISIONS_BY_ACTION_TYPE.get(self.action_type)
            if allowed is not None and self.decision not in allowed:
                raise ValueError(
                    "Combinación administrativa incoherente: "
                    f"{self.action_type.value} + {self.decision.value}."
                )
        return self


class PublicationEvent(ContractModel):
    generation_assets: list[GenerationAssetMention] = Field(min_length=1)
    associated_components: list[AssociatedComponent] = Field(default_factory=list)
    administrative_actions: list[AdministrativeAction] = Field(min_length=1)
    participants: list[ParticipantMention] = Field(default_factory=list)
    administrative_locations: list[AdministrativeLocationMention] = Field(
        default_factory=list
    )
    generation_relations: list[GenerationAssetRelation] = Field(
        default_factory=list
    )
    case_file_references: list[NonEmptyText] = Field(default_factory=list)
    event_summary: NonEmptyText

    @model_validator(mode="after")
    def validate_event_graph(self) -> Self:
        generation_refs = [
            asset.local_generation_asset_ref for asset in self.generation_assets
        ]
        expected_generation_refs = [
            f"generation_asset_{index}"
            for index in range(1, len(generation_refs) + 1)
        ]
        if generation_refs != expected_generation_refs:
            raise ValueError(
                "Las referencias de plantas deben ser consecutivas y estar ordenadas: "
                f"{expected_generation_refs}."
            )

        component_refs = [
            component.local_component_ref
            for component in self.associated_components
        ]
        expected_component_refs = [
            f"component_{index}"
            for index in range(1, len(component_refs) + 1)
        ]
        if component_refs != expected_component_refs:
            raise ValueError(
                "Las referencias de componentes deben ser consecutivas y estar ordenadas: "
                f"{expected_component_refs}."
            )

        valid_generation_refs = set(generation_refs)
        valid_entity_refs = valid_generation_refs | set(component_refs)

        generation_identity_keys: set[tuple[str, tuple[str, ...]]] = set()
        for asset in self.generation_assets:
            identity_key = (
                asset.generation_type.value,
                tuple(sorted(_text_key(name) for name in asset.names_raw)),
            )
            if identity_key in generation_identity_keys:
                raise ValueError(
                    "Existen plantas de generación duplicadas con el mismo "
                    "tipo y los mismos nombres."
                )
            generation_identity_keys.add(identity_key)

        for component in self.associated_components:
            missing = (
                set(component.related_generation_asset_refs)
                - valid_generation_refs
            )
            if missing:
                raise ValueError(
                    "AssociatedComponent referencia plantas inexistentes: "
                    f"{sorted(missing)}."
                )

        for action in self.administrative_actions:
            concrete_targets = set(action.targets) - {"event"}
            missing = concrete_targets - valid_entity_refs
            if missing:
                raise ValueError(
                    "AdministrativeAction contiene targets inexistentes: "
                    f"{sorted(missing)}."
                )
        for relation in self.generation_relations:
            missing = {
                relation.source_generation_asset_ref,
                relation.target_generation_asset_ref,
            } - valid_generation_refs
            if missing:
                raise ValueError(
                    "GenerationAssetRelation contiene referencias inexistentes: "
                    f"{sorted(missing)}."
                )



        return self


class BOEAIExtraction(ContractModel):
    classification_status: ClassificationStatus
    document_scope: DocumentScope | None = None
    classification_reason: NonEmptyText
    publication_events: list[PublicationEvent] = Field(default_factory=list)
    extraction_notes: NonEmptyText | None = None

    @field_validator("document_scope", mode="before")
    @classmethod
    def normalize_legacy_document_scope(cls, value: Any) -> Any:
        # Compatibilidad de lectura con extracciones anteriores. La versión 23
        # expone solo dos clases al modelo y a las tablas vigentes.
        if value == "energy_general":
            return DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
        return value

    @model_validator(mode="after")
    def validate_classification(self) -> Self:
        if self.classification_status == ClassificationStatus.UNCERTAIN:
            if self.document_scope is not None or self.publication_events:
                raise ValueError(
                    "Una clasificación incierta no debe contener scope ni eventos."
                )
            return self

        if self.document_scope is None:
            raise ValueError("Una publicación clasificada debe tener document_scope.")

        project_specific = (
            self.document_scope == DocumentScope.GENERATION_PROJECT_SPECIFIC
        )
        if project_specific and not self.publication_events:
            raise ValueError(
                "Una publicación específica de proyecto debe contener eventos."
            )
        if not project_specific and self.publication_events:
            raise ValueError(
                "Solo una publicación específica de proyecto puede contener eventos."
            )
        return self


class BOEProjectExtraction(BOEAIExtraction):
    boe_id: BOEId
    publication_date: date


def build_boe_project_extraction(
    ai_extraction: BOEAIExtraction,
    *,
    boe_id: str,
    publication_date: date,
) -> BOEProjectExtraction:
    return BOEProjectExtraction(
        **ai_extraction.model_dump(),
        boe_id=boe_id,
        publication_date=publication_date,
    )


BOE_ID_ADAPTER = TypeAdapter(BOEId)


@dataclass(frozen=True)
class BOESourceDocument:
    boe_id: str
    publication_date: date
    title: str
    text: str
    source_document_sha256: str


@dataclass(frozen=True)
class SelectedDocumentText:
    text: str
    strategy: str
    marker: str | None
    excluded_chars: int
    text_sha256: str


@dataclass(frozen=True)
class PreparedDocumentPrompt:
    prompt: str
    input_text_chars: int
    input_text_sha256: str
    input_selection_strategy: str
    input_selection_marker: str | None
    input_excluded_chars: int
