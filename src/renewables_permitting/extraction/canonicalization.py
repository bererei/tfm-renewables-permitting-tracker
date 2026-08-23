from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any

from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    AdministrativeLocationMention,
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
    ParticipantMention,
    PublicationEvent,
    TechnicalAttributeType,
    TechnicalMention,
    _canonicalize_refs,
    _deduplicate_strings,
    _reference_sort_key,
    _text_key,
)


def _canonical_documentary_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value))
    replacements = {
        "\u00a0": " ",
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "’": "'",
        "–": "-",
        "—": "-",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _documentary_contains(needle: str, haystack: str) -> bool:
    canonical_needle = _canonical_documentary_text(needle).casefold()
    canonical_haystack = _canonical_documentary_text(haystack).casefold()
    return bool(canonical_needle) and canonical_needle in canonical_haystack


def _evidence_segments(evidence: str) -> list[str]:
    return [
        segment.strip()
        for segment in re.split(r"\s*\[\.\.\.\]\s*", str(evidence))
        if segment.strip()
    ]


def _evidence_is_supported(evidence: str, source_text: str) -> bool:
    segments = _evidence_segments(evidence)
    return bool(segments) and all(
        _documentary_contains(segment, source_text) for segment in segments
    )


def _source_units(source_text: str, document_title: str | None = None) -> list[str]:
    """Devuelve fragmentos literales de la fuente, del más informativo al más local."""

    candidates: list[str] = []
    if document_title and document_title.strip():
        candidates.append(document_title.strip())

    for line in str(source_text).splitlines():
        line = line.strip()
        if line:
            candidates.append(line)

    # Las frases ayudan a reparar una evidence demasiado extensa o reconstruida.
    for part in re.split(r"(?<=[.;:])\s+|\n+", str(source_text)):
        part = part.strip()
        if part:
            candidates.append(part)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _canonical_documentary_text(candidate).casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _find_literal_span(
    source_text: str,
    *,
    anchors: list[str] | tuple[str, ...] = (),
    semantic_patterns: list[str] | tuple[str, ...] = (),
    document_title: str | None = None,
) -> str | None:
    """Selecciona el fragmento literal más corto que contiene los anclajes."""

    canonical_anchors = [
        _canonical_documentary_text(anchor).casefold()
        for anchor in anchors
        if anchor and _canonical_documentary_text(anchor)
    ]
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in semantic_patterns]

    candidates: list[tuple[int, int, str]] = []
    for position, unit in enumerate(_source_units(source_text, document_title)):
        key = _canonical_documentary_text(unit).casefold()
        if canonical_anchors and not all(anchor in key for anchor in canonical_anchors):
            continue
        if compiled and not all(pattern.search(key) for pattern in compiled):
            continue
        candidates.append((len(key), position, unit))

    if candidates:
        return min(candidates, key=lambda item: (item[0], item[1]))[2]

    # Segundo intento: basta con un anclaje y todos los patrones semánticos.
    if canonical_anchors:
        relaxed: list[tuple[int, int, str]] = []
        for position, unit in enumerate(_source_units(source_text, document_title)):
            key = _canonical_documentary_text(unit).casefold()
            if not any(anchor in key for anchor in canonical_anchors):
                continue
            if compiled and not all(pattern.search(key) for pattern in compiled):
                continue
            relaxed.append((len(key), position, unit))
        if relaxed:
            return min(relaxed, key=lambda item: (item[0], item[1]))[2]

    return None


def _repair_evidence(
    evidence: str,
    *,
    source_text: str,
    anchors: list[str] | tuple[str, ...] = (),
    semantic_patterns: list[str] | tuple[str, ...] = (),
    document_title: str | None = None,
) -> str | None:
    if _evidence_is_supported(evidence, source_text):
        if not anchors or all(_documentary_contains(anchor, evidence) for anchor in anchors):
            return evidence
    return _find_literal_span(
        source_text,
        anchors=anchors,
        semantic_patterns=semantic_patterns,
        document_title=document_title,
    )


def _dedupe_technical_mentions(
    mentions: list[TechnicalMention],
) -> list[TechnicalMention]:
    result: list[TechnicalMention] = []
    seen: set[tuple[str, str]] = set()
    for mention in mentions:
        key = (mention.attribute_type.value, _text_key(mention.value_raw))
        if key not in seen:
            seen.add(key)
            result.append(mention)
    return result


_GENERATION_TYPE_PATTERNS: dict[GenerationType, str] = {
    GenerationType.WIND: r"\be[oó]lic|aerogenerador|parque\s+e[oó]lico",
    GenerationType.PHOTOVOLTAIC: r"fotovolta|\bplanta\s+solar\b|\bpsfv\b|\bfv\b",
    GenerationType.CONCENTRATED_SOLAR_POWER: r"termosolar|solar\s+termoel[eé]ctr",
    GenerationType.HYDROPOWER: r"hidroel[eé]ctr|central\s+hidr[aá]ul",
    GenerationType.BIOMASS: r"biomasa",
    GenerationType.BIOGAS: r"biog[aá]s",
    GenerationType.GEOTHERMAL: r"geot[eé]rm",
}


def _infer_generation_type(text: str) -> GenerationType | None:
    key = _canonical_documentary_text(text).casefold()
    matches = [
        item
        for item, pattern in _GENERATION_TYPE_PATTERNS.items()
        if re.search(pattern, key)
    ]
    return matches[0] if len(matches) == 1 else None


_GENERATION_DESCRIPTOR_PATTERN = (
    r"(?:"
    r"(?:(?:la|el)\s+)?(?:planta|parque|central|instalaci[oó]n|proyecto)"
    r"(?:\s+(?:de\s+generaci[oó]n(?:\s+de\s+energ[ií]a\s+el[eé]ctrica)?|"
    r"solar|fotovoltaic[ao]s?|e[oó]lic[ao]s?|termosolar|"
    r"hidroel[eé]ctric[ao]s?|h[ií]brid[ao]s?))*"
    r"|panel(?:es)?\s+fotovoltaic[ao]s?(?:\s+flotantes?)?"
    r"|m[oó]dulos?\s+fotovoltaic[ao]s?"
    r"|aerogeneradores?"
    r"|aprovechamiento\s+hidroel[eé]ctrico"
    r")"
)


_BOUNDED_SHARED_GENERATION_LIST_RE = re.compile(
    r"\b(?:varias\s+)?instalaciones\s+de\s+generaci[oó]n\s+de\s+"
    r"energ[ií]a\s+renovable\s*\((?P<items>[^()\n]{1,300})\)",
    re.IGNORECASE,
)
_SHARED_GENERATION_PREFIX_RE = re.compile(
    r"^(?P<prefix>PSF)\s+(?P<name>\S.*)$",
    re.IGNORECASE,
)


def _bounded_shared_generation_items(source_text: str) -> list[tuple[str, ...]]:
    """Devuelve listas literales que declaran instalaciones de generación.

    El reconocimiento queda limitado a una gramática local y acotada. No
    interpreta como plantas listas genéricas de infraestructuras ni propaga el
    prefijo fuera de los paréntesis que lo comparten.
    """

    source = _canonical_documentary_text(source_text)
    lists: list[tuple[str, ...]] = []
    for match in _BOUNDED_SHARED_GENERATION_LIST_RE.finditer(source):
        items = tuple(
            item.strip(" \t\"'«»")
            for item in re.split(r"\s*[,;]\s*", match.group("items"))
            if item.strip(" \t\"'«»")
        )
        if len(items) >= 2 and _SHARED_GENERATION_PREFIX_RE.fullmatch(items[0]):
            lists.append(items)
    return lists


def _bounded_shared_generation_name(
    name: str,
    *,
    source_text: str,
) -> str | None:
    """Recupera la forma literal de un nombre con prefijo compartido."""

    requested_key = _canonical_documentary_text(name).casefold()
    matches: set[str] = set()
    for items in _bounded_shared_generation_items(source_text):
        prefix_match = _SHARED_GENERATION_PREFIX_RE.fullmatch(items[0])
        if prefix_match is None:
            continue
        prefix = prefix_match.group("prefix")
        for position, literal_name in enumerate(items):
            expanded_name = (
                literal_name if position == 0 else f"{prefix} {literal_name}"
            )
            if (
                _canonical_documentary_text(expanded_name).casefold()
                == requested_key
            ):
                matches.add(literal_name)

    if len(matches) != 1:
        return None
    literal_name = next(iter(matches))
    if _canonical_documentary_text(literal_name).casefold() == requested_key:
        return None
    return literal_name


def _bounded_generation_list_contains_name(name: str, source_text: str) -> bool:
    """Comprueba pertenencia literal a una lista acotada de generación."""

    name_key = _canonical_documentary_text(name).casefold()
    return any(
        name_key == _canonical_documentary_text(item).casefold()
        for items in _bounded_shared_generation_items(source_text)
        for item in items
    )


_COMPONENT_PATTERNS: dict[AssociatedComponentType, str] = {
    AssociatedComponentType.ENERGY_STORAGE: (
        r"(?:m[oó]dulo|sistema|instalaci[oó]n)?\s*(?:de\s+)?"
        r"(?:almacenamiento|bater[ií]as|bess)"
    ),
    AssociatedComponentType.EVACUATION_SYSTEM: (
        r"infraestructuras?\s+(?:el[eé]ctricas?\s+)?de\s+evacuaci[oó]n|"
        r"sistema\s+de\s+evacuaci[oó]n"
    ),
    AssociatedComponentType.ELECTRICAL_SUBSTATION: (
        r"subestaci[oó]n(?:\s+el[eé]ctrica)?|\bset\b"
    ),
    AssociatedComponentType.POWER_LINE: (
        r"l[ií]nea(?:\s+el[eé]ctrica)?|l[ií]nea\s+de\s+evacuaci[oó]n"
    ),
    AssociatedComponentType.GRID_CONNECTION: (
        r"(?:punto|posici[oó]n|permiso)\s+de\s+(?:acceso\s+y\s+)?conexi[oó]n"
    ),
}


_AUXILIARY_COMPONENT_TYPES = {
    AssociatedComponentType.EVACUATION_SYSTEM,
    AssociatedComponentType.ELECTRICAL_SUBSTATION,
    AssociatedComponentType.POWER_LINE,
    AssociatedComponentType.GRID_CONNECTION,
    AssociatedComponentType.OTHER_ASSOCIATED_COMPONENT,
}


def _component_pattern(component_type: AssociatedComponentType) -> str:
    if component_type in _AUXILIARY_COMPONENT_TYPES:
        return (
            r"infraestructuras?\s+(?:el[eé]ctricas?\s+)?de\s+evacuaci[oó]n|"
            r"sistema\s+de\s+evacuaci[oó]n|l[ií]nea(?:\s+el[eé]ctrica)?|"
            r"subestaci[oó]n(?:\s+el[eé]ctrica)?|\bset\b|"
            r"(?:punto|posici[oó]n|permiso)\s+de\s+(?:acceso\s+y\s+)?conexi[oó]n"
        )
    return _COMPONENT_PATTERNS[component_type]


def _generation_name_is_direct_target(name: str, text: str) -> bool:
    """Distingue el destinatario jurídico de una referencia contextual.

    Un nombre de planta contenido en expresiones como «infraestructura de
    evacuación de la planta X» o «almacenamiento para su hibridación con X»
    identifica la planta relacionada, pero no implica que la actuación recaiga
    también sobre ella.
    """

    canonical_text = _canonical_documentary_text(text).casefold()
    canonical_name = _canonical_documentary_text(name).casefold()
    if not canonical_name:
        return False

    component_or_integration_pattern = (
        rf"(?:{_component_pattern(AssociatedComponentType.EVACUATION_SYSTEM)}|"
        rf"{_component_pattern(AssociatedComponentType.ENERGY_STORAGE)})"
    )
    contextual_link_pattern = re.compile(
        r"(?:"
        r"\bde(?:l|\s+la)?\b|"
        r"\basociad[ao]s?\s+a(?:l|\s+la)?\b|"
        r"\bpara\s+su\s+hibridaci[oó]n\s+con\b|"
        r"\bhibridaci[oó]n\s+(?:de|con)\b"
        r")",
        re.IGNORECASE,
    )

    start = 0
    found_neutral = False
    while True:
        index = canonical_text.find(canonical_name, start)
        if index < 0:
            break

        before = canonical_text[max(0, index - 360):index]
        around = canonical_text[
            max(0, index - 160):index + len(canonical_name) + 100
        ]

        component_matches = list(
            re.finditer(component_or_integration_pattern, before, re.IGNORECASE)
        )
        is_contextual = False
        if component_matches:
            last_component = component_matches[-1]
            link_text = before[last_component.end():]
            if len(link_text) <= 280 and contextual_link_pattern.search(link_text):
                is_contextual = True

        if is_contextual:
            start = index + len(canonical_name)
            continue

        if re.search(_GENERATION_DESCRIPTOR_PATTERN, around, re.IGNORECASE):
            return True

        found_neutral = True
        start = index + len(canonical_name)

    return found_neutral


def _generation_refs_mentioned(
    event: PublicationEvent,
    text: str,
    *,
    direct_only: bool = False,
) -> list[str]:
    refs: list[str] = []
    for asset in event.generation_assets:
        for name in asset.names_raw:
            matches = (
                _generation_name_is_direct_target(name, text)
                if direct_only
                else _documentary_contains(name, text)
            )
            if matches:
                refs.append(asset.local_generation_asset_ref)
                break
    return _canonicalize_refs(refs)


def _component_refs_mentioned(event: PublicationEvent, text: str) -> list[str]:
    canonical = _canonical_documentary_text(text).casefold()
    refs: list[str] = []
    by_type: dict[AssociatedComponentType, list[AssociatedComponent]] = {}
    for component in event.associated_components:
        by_type.setdefault(component.component_type, []).append(component)
        if any(_documentary_contains(name, text) for name in component.names_raw):
            refs.append(component.local_component_ref)
            continue
        if component.description_raw and _documentary_contains(component.description_raw, text):
            refs.append(component.local_component_ref)

    for component_type, components in by_type.items():
        if len(components) == 1 and re.search(_component_pattern(component_type), canonical):
            refs.append(components[0].local_component_ref)
    return _canonicalize_refs(refs)


def _entity_refs_mentioned(event: PublicationEvent, text: str) -> list[str]:
    return _canonicalize_refs(
        _generation_refs_mentioned(event, text, direct_only=True)
        + _component_refs_mentioned(event, text)
    )


class ScopeGuardDecision(str, Enum):
    FORCE_NOT_RELEVANT = "force_not_relevant"
    REQUIRE_PROJECT_REVIEW = "require_project_review"
    NO_DETERMINISTIC_DECISION = "no_deterministic_decision"


_PROCUREMENT_TITLE_RE = re.compile(
    r"formalizaci[oó]n\s+de\s+contratos?|anuncio\s+de\s+(?:licitaci[oó]n|"
    r"adjudicaci[oó]n)|contrataci[oó]n\s+del?\s+(?:suministro|servicio|obra)|"
    r"contrato\s+de\s+suministro",
    re.IGNORECASE,
)


_NON_GENERATION_MAIN_OBJECT_RE = re.compile(
    r"abastecimiento\s+de\s+agua|mejora\s+del\s+abastecimiento|"
    r"estaci[oó]n\s+depuradora|\bedar\b|saneamiento|depuraci[oó]n\s+de\s+aguas|"
    r"modernizaci[oó]n\s+de\s+regad[ií]os?|comunidad\s+de\s+regantes|"
    r"equipos?\s+de\s+bombeo|obras?\s+de\s+regad[ií]o|"
    r"proyecto\s+de\s+construcci[oó]n\s+de\s+(?:carretera|ferrocarril)|"
    r"vertederos?\s+asociados?\s+al\s+proyecto\s+de\s+construcci[oó]n",
    re.IGNORECASE,
)


_EXPLICIT_ELECTRIC_GENERATION_RE = re.compile(
    r"(?:planta|parque|central|instalaci[oó]n|m[oó]dulo\s+de\s+generaci[oó]n)"
    r"[^.;]{0,180}(?:fotovolta|solar|e[oó]lic|hidroel[eé]ct|termosolar|biomasa|"
    r"biog[aá]s|generaci[oó]n\s+de\s+energ[ií]a\s+el[eé]ctrica)|"
    r"(?:fotovolta|e[oó]lic|hidroel[eé]ct|termosolar)[^.;]{0,100}"
    r"(?:planta|parque|central|instalaci[oó]n)|"
    r"(?:aprovechamiento|central)[^.;]{0,100}producci[oó]n\s+de\s+energ[ií]a\s+el[eé]ctrica|"
    r"\b(?:psfv|pfv|fv|pe)\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'-]+",
    re.IGNORECASE,
)


_AUXILIARY_RENEWABLE_RE = re.compile(
    r"paneles?\s+fotovoltaicos?|placas?\s+fotovoltaicas?|"
    r"instalaci[oó]n\s+solar\s+fotovoltaica|energ[ií]as?\s+renovables?",
    re.IGNORECASE,
)


_NON_ELECTRIC_GAS_INFRASTRUCTURE_RE = re.compile(
    r"\bgasoductos?\b|instalaciones?\s+gasistas?|"
    r"estaci[oó]n\s+(?:de\s+)?(?:medida|regulaci[oó]n|compresi[oó]n)|"
    r"posici[oó]n\s+[A-Z0-9.-]+[^.;]{0,120}(?:gas|biometano)|"
    r"inyecci[oó]n\s+de\s+(?:biometano|hidr[oó]geno)[^.;]{0,120}"
    r"(?:gasoducto|red\s+gasista|red\s+de\s+gas)",
    re.IGNORECASE,
)


_STANDALONE_STORAGE_MAIN_OBJECT_RE = re.compile(
    r"(?:planta|sistema|instalaci[oó]n|m[oó]dulo)\s+de\s+"
    r"almacenamiento(?:\s+de\s+energ[ií]a)?|"
    r"\b(?:bess|sistema\s+de\s+bater[ií]as)\b",
    re.IGNORECASE,
)


_STORAGE_LINKED_TO_GENERATION_RE = re.compile(
    r"hibridaci[oó]n|hibridad[oa]|hibrida\s+con|"
    r"(?:asociad[oa]|vinculad[oa]|integrado|incorporado)\s+(?:a|al|en)\s+"
    r"(?:la\s+|el\s+)?(?:planta|parque|central|instalaci[oó]n)[^.;]{0,160}"
    r"(?:fotovolta|solar|e[oó]lic|hidroel[eé]ct|termosolar|biomasa|biog[aá]s)|"
    r"(?:planta|parque|central|instalaci[oó]n)[^.;]{0,160}"
    r"(?:fotovolta|e[oó]lic|hidroel[eé]ct|termosolar|biomasa|biog[aá]s)",
    re.IGNORECASE,
)


_WATER_AUTHORITY_TITLE_RE = re.compile(
    r"confederaci[oó]n\s+hidrogr[aá]fica|comisar[ií]a\s+de\s+aguas",
    re.IGNORECASE,
)


_TRANSPORT_OR_COASTAL_AUTHORITY_TITLE_RE = re.compile(
    r"demarcaci[oó]n\s+de\s+carreteras|"
    r"administrador\s+de\s+infraestructuras\s+ferroviarias|\badif\b|"
    r"demarcaci[oó]n\s+de\s+costas|servicio\s+provincial\s+de\s+costas|"
    r"autoridad\s+portuaria|puertos\s+del\s+estado",
    re.IGNORECASE,
)


_APPROVED_GENERATION_OR_HYDRO_SAFEGUARD_RE = re.compile(
    r"hidroel[eé]ct|producci[oó]n\s+de\s+energ[ií]a\s+el[eé]ctrica|"
    r"(?:central(?:es)?|generaci[oó]n)\s+hidr[aá]ulic",
    re.IGNORECASE,
)


_NON_GENERATION_WATER_AUTHORITY_REASON = (
    "non_generation_water_authority: organismo de cuenca o Comisaría de "
    "Aguas sin lenguaje explícito de generación eléctrica o hidroeléctrica."
)
_NON_GENERATION_TRANSPORT_OR_COASTAL_REASON = (
    "non_generation_transport_or_coastal: organismo de carreteras, "
    "ferrocarril, costas o puertos sin lenguaje explícito de generación "
    "eléctrica o hidroeléctrica."
)


def _scope_guard_from_document(
    *,
    document_title: str,
    source_text: str,
) -> tuple[ScopeGuardDecision, str | None]:
    """Aplica solo decisiones de alcance de alta precisión.

    No determina la categoría de todos los BOE. Su objetivo es impedir dos errores
    graves: convertir contratación/obras sectoriales en plantas y aceptar como no
    relevante un título que identifica inequívocamente una planta y un acto actual.
    """

    title = _canonical_documentary_text(document_title)
    source = _canonical_documentary_text(source_text)

    if _PROCUREMENT_TITLE_RE.search(title):
        return (
            ScopeGuardDecision.FORCE_NOT_RELEVANT,
            "Anuncio de contratación pública; no constituye un acto administrativo del ciclo de una planta de generación.",
        )

    explicit_generation_in_title = bool(_EXPLICIT_ELECTRIC_GENERATION_RE.search(title))
    non_generation_main_object = bool(_NON_GENERATION_MAIN_OBJECT_RE.search(title))
    non_electric_gas_infrastructure = bool(
        _NON_ELECTRIC_GAS_INFRASTRUCTURE_RE.search(title)
    )
    standalone_storage_main_object = bool(
        _STANDALONE_STORAGE_MAIN_OBJECT_RE.search(title)
    )
    storage_linked_to_generation = bool(
        _STORAGE_LINKED_TO_GENERATION_RE.search(title)
    )
    auxiliary_renewable = bool(_AUXILIARY_RENEWABLE_RE.search(source))
    explicit_hydroelectric_use = bool(
        _APPROVED_GENERATION_OR_HYDRO_SAFEGUARD_RE.search(title)
    )

    if non_electric_gas_infrastructure and not explicit_generation_in_title:
        return (
            ScopeGuardDecision.FORCE_NOT_RELEVANT,
            "Infraestructura gasista o de inyección a la red de gas sin una planta de generación eléctrica identificable.",
        )

    if (
        standalone_storage_main_object
        and not storage_linked_to_generation
        and not explicit_generation_in_title
    ):
        return (
            ScopeGuardDecision.FORCE_NOT_RELEVANT,
            "Instalación autónoma de almacenamiento: el objeto actual no identifica una planta de generación eléctrica asociada.",
        )

    if (
        non_generation_main_object
        and not explicit_generation_in_title
        and not explicit_hydroelectric_use
    ):
        detail = (
            "La generación aparece como elemento auxiliar de un proyecto sectorial cuyo objeto principal no es una planta de generación."
            if auxiliary_renewable
            else "El objeto principal del título es un proyecto sectorial no perteneciente a la generación eléctrica."
        )
        return ScopeGuardDecision.FORCE_NOT_RELEVANT, detail

    approved_generation_or_hydro = (
        explicit_generation_in_title or explicit_hydroelectric_use
    )
    if (
        _WATER_AUTHORITY_TITLE_RE.search(title)
        and not approved_generation_or_hydro
    ):
        return (
            ScopeGuardDecision.FORCE_NOT_RELEVANT,
            _NON_GENERATION_WATER_AUTHORITY_REASON,
        )

    if (
        _TRANSPORT_OR_COASTAL_AUTHORITY_TITLE_RE.search(title)
        and not approved_generation_or_hydro
    ):
        return (
            ScopeGuardDecision.FORCE_NOT_RELEVANT,
            _NON_GENERATION_TRANSPORT_OR_COASTAL_REASON,
        )

    title_actions = _action_types_from_title(document_title)
    if explicit_generation_in_title and title_actions:
        return (
            ScopeGuardDecision.REQUIRE_PROJECT_REVIEW,
            "El título identifica una planta de generación y una actuación administrativa actual.",
        )

    return ScopeGuardDecision.NO_DETERMINISTIC_DECISION, None


def _force_non_relevant_extraction(
    extraction: BOEProjectExtraction,
    *,
    reason: str,
) -> BOEProjectExtraction:
    extraction = extraction.model_copy(deep=True)
    extraction.classification_status = ClassificationStatus.CLASSIFIED
    extraction.document_scope = DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
    extraction.classification_reason = reason
    extraction.publication_events = []
    extraction.extraction_notes = None
    return BOEProjectExtraction.model_validate(extraction.model_dump())


def preclassify_document_without_model(
    document: BOESourceDocument,
) -> tuple[BOEProjectExtraction | None, list[str]]:
    """Descarta antes de la IA solo documentos inequívocamente fuera de alcance.

    Devuelve ``None`` cuando la decisión requiere comprensión generativa. Esta
    función no intenta clasificar todos los BOE y prioriza evitar falsos negativos.
    """

    decision, reason = _scope_guard_from_document(
        document_title=document.title,
        source_text=f"{document.title}\n{document.text}",
    )
    if decision != ScopeGuardDecision.FORCE_NOT_RELEVANT:
        return None, []

    resolved_reason = reason or "Documento inequívocamente fuera del alcance del TFM."
    extraction = BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS,
        classification_reason=resolved_reason,
        publication_events=[],
        extraction_notes=None,
        boe_id=document.boe_id,
        publication_date=document.publication_date,
    )
    return extraction, [
        "Alcance resuelto antes de llamar al modelo: " + resolved_reason
    ]


_ACTION_PATTERNS: dict[AdministrativeActionType, str] = {
    AdministrativeActionType.ERROR_CORRECTION: (
        r"(?:correcci[oó]n|rectificaci[oó]n)(?:\s+de)?\s+errores?"
    ),
    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION: (
        r"autorizaci[oó]n\s+administrativa\s+previa|\baap\b"
    ),
    AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION: (
        r"autorizaci[oó]n\s+administrativa\s+(?:de\s+)?construcci[oó]n|autorizaci[oó]n\s+(?:de\s+)?construcci[oó]n|autoriza[^.;]{0,50}construcci[oó]n|\baac\b"
    ),
    AdministrativeActionType.OPERATING_AUTHORIZATION: (
        r"autorizaci[oó]n\s+(?:de\s+)?explotaci[oó]n"
    ),
    AdministrativeActionType.WATER_CONCESSION: (
        r"(?:otorga|concede|solicitud\s+de)\s+(?:la\s+)?concesi[oó]n|"
        r"concesi[oó]n\s+para\s+el\s+aprovechamiento"
    ),
    AdministrativeActionType.PUBLIC_UTILITY_DECLARATION: (
        r"(?:declaraci[oó]n|reconocimiento)(?:\s*,\s*|\s+)"
        r"(?:en\s+concreto(?:\s*,\s*|\s+))?"
        r"de\s+utilidad\s+p[uú]blica|"
        r"\bdup\b"
    ),
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT: (
        r"declaraci[oó]n\s+de\s+impacto\s+ambiental|\bdia\b"
    ),
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT: (
        r"informe\s+de\s+impacto\s+ambiental"
    ),
    AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT: (
        r"informe\s+de\s+determinaci[oó]n\s+de\s+afecci[oó]n\s+ambiental|\bidaa\b"
    ),
    AdministrativeActionType.PRIOR_OCCUPATION_RECORDS: (
        r"levantamiento\s+de\s+actas\s+previas\s+a\s+la\s+ocupaci[oó]n"
    ),
    AdministrativeActionType.OCCUPATION_RECORDS: r"actas\s+de\s+ocupaci[oó]n",
    AdministrativeActionType.AFFECTED_ASSETS_AND_RIGHTS_LIST: (
        r"relaci[oó]n(?:\s+concreta\s+e\s+individualizada)?\s+de\s+bienes\s+y\s+derechos\s+afectados"
    ),
    AdministrativeActionType.OWNERSHIP_CHANGE: r"cambio\s+de\s+titularidad|transmisi[oó]n\s+de\s+titularidad",
    AdministrativeActionType.DEADLINE_EXTENSION: r"pr[oó]rroga",
    AdministrativeActionType.PROCEDURE_TERMINATION: r"archivo|desistimiento|inadmisi[oó]n",
}


_TERMINATION_OBJECT_INTRO_RE = re.compile(
    r"(?:"
    r"\bde\s+(?:la\s+|las\s+)?solicitud(?:es)?\s+de\s+|"
    r"\bdel\s+(?:expediente|procedimiento)\s+de\s+|"
    r",\s*de\s+|"
    r"\bde\s+"
    r")$"
)
_INDEPENDENT_TITLE_ACTION_RE = re.compile(
    r"(?:[,;]\s*)?(?:y\s+)?se\s+(?:"
    r"otorga|concede|autoriza|deniega|somete|formula|aprueba|declara"
    r")\b"
)


def _termination_object_action_types(
    title: str,
) -> set[AdministrativeActionType]:
    """Identifica actos citados solo como objeto de una terminación actual."""

    key = _canonical_documentary_text(title).casefold()
    termination = re.search(r"\b(?:desistimiento|archivo|inadmisi[oó]n)\b", key)
    if termination is None:
        return set()

    matches_by_type = {
        action_type: list(re.finditer(pattern, key))
        for action_type, pattern in _ACTION_PATTERNS.items()
        if action_type != AdministrativeActionType.PROCEDURE_TERMINATION
    }
    matches_after_termination = [
        match
        for matches in matches_by_type.values()
        for match in matches
        if match.start() >= termination.end()
    ]
    if not matches_after_termination:
        return set()

    first_object_match = min(matches_after_termination, key=lambda match: match.start())
    intro = key[termination.end():first_object_match.start()]
    if not _TERMINATION_OBJECT_INTRO_RE.search(intro):
        return set()

    independent_action = _INDEPENDENT_TITLE_ACTION_RE.search(
        key,
        first_object_match.end(),
    )
    object_end = independent_action.start() if independent_action else len(key)

    return {
        action_type
        for action_type, matches in matches_by_type.items()
        if matches
        and all(
            first_object_match.start() <= match.start() < object_end
            for match in matches
        )
    }


def _action_types_from_title(title: str) -> set[AdministrativeActionType]:
    key = _canonical_documentary_text(title).casefold()
    result = {
        action_type
        for action_type, pattern in _ACTION_PATTERNS.items()
        if re.search(pattern, key)
    }

    # Una publicación de corrección no vuelve a publicar el acto corregido.
    if AdministrativeActionType.ERROR_CORRECTION in result:
        return {AdministrativeActionType.ERROR_CORRECTION}

    # Los permisos enumerados como objeto de una terminación describen el
    # procedimiento terminado; no son por sí solos actos actuales adicionales.
    result -= _termination_object_action_types(title)

    is_public_information = bool(re.search(
        r"(?:somete|sometimiento|anuncio)[^.;]{0,180}informaci[oó]n\s+p[uú]blica",
        key,
    ))
    if is_public_information:
        environmental_products = {
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
        }
        explicit_environmental_process = bool(re.search(
            r"estudio\s+de\s+impacto\s+ambiental|"
            r"evaluaci[oó]n\s+de\s+impacto\s+ambiental",
            key,
        ))
        if result & environmental_products or explicit_environmental_process:
            result -= environmental_products
            result.add(AdministrativeActionType.ENVIRONMENTAL_IMPACT_ASSESSMENT)
        elif not result:
            result.add(AdministrativeActionType.PUBLIC_INFORMATION)
    return result


_ENVIRONMENTAL_TERMINAL_DECISIONS_BY_ACTION_TYPE = {
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT: frozenset({
        AdministrativeDecision.FAVORABLE,
        AdministrativeDecision.UNFAVORABLE,
    }),
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT: frozenset({
        AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
        AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
    }),
    AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT: (
        frozenset({
            AdministrativeDecision.FAVORABLE,
            AdministrativeDecision.UNFAVORABLE,
            AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS,
            AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
            AdministrativeDecision.FURTHER_ENVIRONMENTAL_ASSESSMENT_REQUIRED,
            AdministrativeDecision.FURTHER_ENVIRONMENTAL_ASSESSMENT_NOT_REQUIRED,
        })
    ),
}
_IDAA_RESOLUTIVE_INTRO_RE = re.compile(
    r"\bresuelve\s+la\s+formulaci[oó]n\s+de(?:l)?\s+informe\s+de\s+"
    r"determinaci[oó]n\s+de\s+afecci[oó]n\s+ambiental\s+en\s+el\s+"
    r"sentido\s+de\s+que\b",
    re.IGNORECASE,
)
_IDAA_ORDINARY_ASSESSMENT_RE = re.compile(
    r"\b(?:"
    r"se\s+someta\s+a|"
    r"deb[ae]\s+someterse\s+a|"
    r"contin[uú]e\s+con"
    r")\b[^.;]{0,700}\b(?:procedimiento\s+de\s+)?"
    r"evaluaci[oó]n\s+ambiental\s+ordinari[oa]\b",
    re.IGNORECASE,
)
_IDAA_NO_SIGNIFICANT_EFFECTS_RE = re.compile(
    r"\bno\s+(?:se\s+)?(?:aprecian|apreciarse|prev[eé]n)\s+"
    r"efectos\s+adversos\s+significativos\b",
    re.IGNORECASE,
)
_AUTHORIZATION_GRANT_RE = re.compile(
    r"\b(?:"
    r"otorga(?:n|r|d[ao]s?)?|"
    r"concede(?:n|r)?|concedid[ao]s?|"
    r"autoriza(?:n|r|d[ao]s?)?"
    r")\b"
)
_AUTHORIZATION_DESESTIMATION_RE = re.compile(
    r"(?:"
    r"\bdesestim(?:a(?:n)?|ar|ad[ao]s?|aci[oó]n(?:es)?)\b"
    r"[^.;]{0,160}\b(?:solicitud(?:es)?|procedimiento)\b|"
    r"\b(?:solicitud(?:es)?|procedimiento)\b[^.;]{0,160}"
    r"\bdesestim(?:a(?:n)?|ar|ad[ao]s?|aci[oó]n(?:es)?)\b"
    r")"
)


def _authorization_decision_from_title(
    title_key: str,
    *,
    action_type: AdministrativeActionType,
) -> AdministrativeDecision:
    """Prioriza resultados explícitos sobre una solicitud procedimental."""

    if (
        action_type
        == AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
        and _AUTHORIZATION_DESESTIMATION_RE.search(title_key)
    ):
        return AdministrativeDecision.DESESTIMADO
    if re.search(r"\b(?:deniega|denegaci[oó]n)\b", title_key):
        return AdministrativeDecision.DENIED
    if _AUTHORIZATION_GRANT_RE.search(title_key):
        return AdministrativeDecision.AUTHORIZED
    if re.search(r"\b(?:solicitud|solicita)\b", title_key):
        return AdministrativeDecision.REQUESTED
    return AdministrativeDecision.AUTHORIZED


def _decision_from_title(
    title: str,
    action_type: AdministrativeActionType,
) -> AdministrativeDecision:
    key = _canonical_documentary_text(title).casefold()
    if action_type == AdministrativeActionType.ERROR_CORRECTION:
        return AdministrativeDecision.RECTIFIED
    if re.search(r"informaci[oó]n\s+p[uú]blica", key):
        return AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
    if action_type in _ENVIRONMENTAL_TERMINAL_DECISIONS_BY_ACTION_TYPE:
        if re.search(r"desfavorable|no\s+favorable", key):
            return AdministrativeDecision.UNFAVORABLE
        if re.search(r"favorable", key):
            return AdministrativeDecision.FAVORABLE
        return AdministrativeDecision.FORMULATED
    if action_type in {
        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
        AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
        AdministrativeActionType.OPERATING_AUTHORIZATION,
        AdministrativeActionType.OWNERSHIP_CHANGE,
    }:
        return _authorization_decision_from_title(
            key,
            action_type=action_type,
        )
    if action_type == AdministrativeActionType.WATER_CONCESSION:
        if re.search(r"deniega|denegaci[oó]n", key):
            return AdministrativeDecision.DENIED
        if re.search(r"informaci[oó]n\s+p[uú]blica", key):
            return AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
        if re.search(r"solicitud|solicita", key) and not re.search(r"otorga|concede", key):
            return AdministrativeDecision.REQUESTED
        return AdministrativeDecision.AUTHORIZED
    if action_type == AdministrativeActionType.PUBLIC_UTILITY_DECLARATION:
        if re.search(r"solicitud|informaci[oó]n\s+p[uú]blica", key):
            return AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
        return AdministrativeDecision.DECLARED
    if action_type in {
        AdministrativeActionType.PRIOR_OCCUPATION_RECORDS,
        AdministrativeActionType.OCCUPATION_RECORDS,
        AdministrativeActionType.AFFECTED_ASSETS_AND_RIGHTS_LIST,
    }:
        return AdministrativeDecision.ANNOUNCED
    if action_type == AdministrativeActionType.DEADLINE_EXTENSION:
        return AdministrativeDecision.EXTENDED
    if action_type == AdministrativeActionType.PROCEDURE_TERMINATION:
        if re.search(r"desist", key):
            return AdministrativeDecision.WITHDRAWN
        if re.search(r"inadmis", key):
            return AdministrativeDecision.INADMISSIBLE
        return AdministrativeDecision.CLOSED
    return AdministrativeDecision.OTHER


def _should_replace_decision_from_title(
    *,
    action_type: AdministrativeActionType,
    existing: AdministrativeDecision,
    inferred: AdministrativeDecision,
) -> bool:
    """Aplica precedencia explícita sin degradar resultados informativos."""

    if (
        inferred == AdministrativeDecision.REQUESTED
        and existing != AdministrativeDecision.UNKNOWN
    ):
        return False

    if (
        inferred == AdministrativeDecision.FORMULATED
        and existing
        in _ENVIRONMENTAL_TERMINAL_DECISIONS_BY_ACTION_TYPE.get(
            action_type,
            frozenset(),
        )
    ):
        return False
    return inferred != AdministrativeDecision.OTHER


def _idaa_substantive_decision(
    action: AdministrativeAction,
    *,
    source_text: str,
    document_title: str,
) -> AdministrativeDecision | None:
    """Deriva solo el sentido explícito del IDAA resolutivo actual."""

    if action.action_type != (
        AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT
    ):
        return None
    if action.action_type not in _action_types_from_title(document_title):
        return None

    candidates = [action.evidence, *_source_units(source_text)]
    seen: set[str] = set()
    for candidate in candidates:
        key = _canonical_documentary_text(candidate).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        intro = _IDAA_RESOLUTIVE_INTRO_RE.search(key)
        if intro is None:
            continue
        conclusion = key[intro.end():]
        if _IDAA_ORDINARY_ASSESSMENT_RE.search(conclusion):
            return (
                AdministrativeDecision.ORDINARY_ENVIRONMENTAL_ASSESSMENT_REQUIRED
            )
        if _IDAA_NO_SIGNIFICANT_EFFECTS_RE.search(conclusion):
            return (
                AdministrativeDecision.NO_SIGNIFICANT_ADVERSE_ENVIRONMENTAL_EFFECTS
            )
    return None


_MODIFIABLE_ACTION_TYPES = {
    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
    AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
    AdministrativeActionType.OPERATING_AUTHORIZATION,
    AdministrativeActionType.PUBLIC_UTILITY_DECLARATION,
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
    AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
    AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
}


def _modification_expectation(
    action: AdministrativeAction,
    *,
    document_title: str,
) -> bool | None:
    if action.action_type not in _MODIFIABLE_ACTION_TYPES:
        return False
    key = _canonical_documentary_text(document_title).casefold()
    pattern = _ACTION_PATTERNS.get(action.action_type)
    if pattern is None or not re.search(pattern, key):
        return None

    coordinated_prior_only = re.search(
        r"autorizaci[oó]n\s+administrativa\s+previa[^.;]{0,100}"
        r"modificaci[oó]n(?:es)?[^.;]{0,100}\by\s+"
        r"autorizaci[oó]n\s+administrativa\s+(?:de\s+)?construcci[oó]n",
        key,
    )
    if coordinated_prior_only:
        if action.action_type == AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION:
            return True
        if action.action_type == AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION:
            construction_tail = key[coordinated_prior_only.end():]
            return bool(re.search(r"modificaci[oó]n|modificad[ao]|\bmodifica(?:n|da|do)?\b", construction_tail))

    # Busca «modificación» en la cláusula local del acto, no en todo el título.
    match = re.search(pattern, key)
    assert match is not None
    left = max(key.rfind(";", 0, match.start()), key.rfind(".", 0, match.start()))
    right_positions = [
        position
        for token in (";", ".")
        if (position := key.find(token, match.end())) >= 0
    ]
    right = min(right_positions) if right_positions else len(key)
    clause = key[left + 1:right]
    return bool(re.search(r"modificaci[oó]n|modificad[ao]|\bmodifica(?:n|da|do)?\b", clause))


def _is_clearly_historical(evidence: str) -> bool:
    key = _canonical_documentary_text(evidence).casefold()
    return bool(re.search(
        r"^(?:mediante|por)\s+(?:resoluci[oó]n|orden)|"
        r"^con\s+fecha\s+\d|^en\s+fecha\s+\d|"
        r"antecedentes?|previamente|con\s+anterioridad|"
        r"hab[ií]a\s+(?:sido|obtenido|solicitado|autorizado)",
        key,
    ))


def _repair_technical_mentions(
    mentions: list[TechnicalMention],
    *,
    source_text: str,
    document_title: str,
    storage: bool,
) -> tuple[list[TechnicalMention], list[str]]:
    repaired: list[TechnicalMention] = []
    adjustments: list[str] = []
    for mention in _dedupe_technical_mentions(mentions):
        if not _documentary_contains(mention.value_raw, source_text):
            adjustments.append(
                f"Magnitud opcional descartada por no ser literal: {mention.value_raw!r}."
            )
            continue
        evidence = _repair_evidence(
            mention.evidence,
            source_text=source_text,
            anchors=[mention.value_raw],
            document_title=document_title,
        )
        if evidence is None:
            adjustments.append(
                f"Magnitud opcional descartada por carecer de cita: {mention.value_raw!r}."
            )
            continue
        attribute_type = mention.attribute_type
        value_key = _canonical_documentary_text(mention.value_raw).casefold()
        if storage and attribute_type == TechnicalAttributeType.INSTALLED_POWER:
            attribute_type = (
                TechnicalAttributeType.STORAGE_CAPACITY
                if re.search(r"\b(?:mwh|kwh|gwh)\b", value_key)
                else TechnicalAttributeType.STORAGE_POWER
            )
        repaired.append(mention.model_copy(update={
            "attribute_type": attribute_type,
            "evidence": evidence,
        }))
    return _dedupe_technical_mentions(repaired), adjustments


def _salvage_generation_names(
    asset: GenerationAssetMention,
    *,
    source_text: str,
) -> tuple[list[str], list[str]]:
    names: list[str] = []
    adjustments: list[str] = []
    for name in _deduplicate_strings(asset.names_raw):
        bounded_name = _bounded_shared_generation_name(
            name,
            source_text=source_text,
        )
        if bounded_name is not None:
            names.append(bounded_name)
            adjustments.append(
                "Nombre de planta reparado desde una lista acotada con "
                f"prefijo compartido: {name!r} -> {bounded_name!r}."
            )
            continue
        if _documentary_contains(name, source_text):
            names.append(name)
            continue
        stripped = re.sub(
            r"\s+(?:e[oó]lic[oa]|fotovoltaic[oa]|solar|fv)$",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip(" \"'«»")
        if stripped and _documentary_contains(stripped, source_text):
            names.append(stripped)
            adjustments.append(
                f"Nombre de planta reparado eliminando un sufijo no documental: {name!r}."
            )
        else:
            adjustments.append(f"Nombre de planta no documental descartado: {name!r}.")
    return _deduplicate_strings(names), adjustments


def _repair_generation_asset(
    asset: GenerationAssetMention,
    *,
    source_text: str,
    document_title: str,
) -> tuple[GenerationAssetMention | None, list[str]]:
    adjustments: list[str] = []
    names, current = _salvage_generation_names(asset, source_text=source_text)
    adjustments.extend(current)
    if not names:
        return None, adjustments + [
            f"{asset.local_generation_asset_ref}: planta descartada al no conservar un nombre literal."
        ]

    evidence = _repair_evidence(
        asset.evidence,
        source_text=source_text,
        anchors=[names[0]],
        semantic_patterns=[_GENERATION_DESCRIPTOR_PATTERN],
        document_title=document_title,
    )
    if evidence is None:
        evidence = _repair_evidence(
            asset.evidence,
            source_text=source_text,
            anchors=[names[0]],
            document_title=document_title,
        )
    if evidence is None:
        return None, adjustments + [
            f"{asset.local_generation_asset_ref}: planta descartada al no localizar cita literal."
        ]

    generation_type = asset.generation_type
    if generation_type == GenerationType.OTHER_GENERATION:
        inferred = _infer_generation_type(f"{evidence} {' '.join(names)}")
        if inferred is not None:
            generation_type = inferred
            adjustments.append(
                f"{asset.local_generation_asset_ref}: tipo de generación inferido como {inferred.value}."
            )

    mentions, current = _repair_technical_mentions(
        asset.technical_mentions,
        source_text=source_text,
        document_title=document_title,
        storage=False,
    )
    adjustments.extend(current)
    return asset.model_copy(update={
        "names_raw": names,
        "generation_type": generation_type,
        "technical_mentions": mentions,
        "evidence": evidence,
    }), adjustments


def _expand_multitechnology_generation_assets(
    event: PublicationEvent,
    *,
    source_text: str,
) -> tuple[PublicationEvent, list[str]]:
    """Desdobla una instalación híbrida condensada solo con evidencia inequívoca."""

    assets: list[GenerationAssetMention] = []
    ref_mapping: dict[str, list[str]] = {}
    adjustments: list[str] = []
    relation_evidence = _find_literal_span(
        source_text,
        semantic_patterns=[r"h[ií]brid"],
    )

    for asset in event.generation_assets:
        by_type: dict[GenerationType, list[TechnicalMention]] = {}
        for mention in asset.technical_mentions:
            inferred = _infer_generation_type(f"{mention.evidence} {mention.value_raw}")
            if inferred is not None:
                by_type.setdefault(inferred, []).append(mention)
        should_split = (
            asset.generation_type == GenerationType.OTHER_GENERATION
            and len(by_type) >= 2
            and relation_evidence is not None
        )
        if not should_split:
            new_ref = f"generation_asset_{len(assets) + 1}"
            assets.append(asset.model_copy(update={"local_generation_asset_ref": new_ref}))
            ref_mapping[asset.local_generation_asset_ref] = [new_ref]
            continue

        new_refs: list[str] = []
        for generation_type in sorted(by_type, key=lambda item: item.value):
            new_ref = f"generation_asset_{len(assets) + 1}"
            new_refs.append(new_ref)
            assets.append(asset.model_copy(update={
                "local_generation_asset_ref": new_ref,
                "generation_type": generation_type,
                "technical_mentions": by_type[generation_type],
            }))
        ref_mapping[asset.local_generation_asset_ref] = new_refs
        adjustments.append(
            f"{asset.local_generation_asset_ref}: instalación híbrida multitecnología desdoblada en {new_refs}."
        )

    if not any(len(values) > 1 for values in ref_mapping.values()):
        return event.model_copy(update={"generation_assets": assets}), adjustments

    components: list[AssociatedComponent] = []
    for component in event.associated_components:
        refs: list[str] = []
        for ref in component.related_generation_asset_refs:
            refs.extend(ref_mapping.get(ref, [ref]))
        components.append(component.model_copy(update={
            "related_generation_asset_refs": _canonicalize_refs(refs),
        }))

    actions: list[AdministrativeAction] = []
    for action in event.administrative_actions:
        targets: list[str] = []
        for target in action.targets:
            if target.startswith("generation_asset_"):
                targets.extend(ref_mapping.get(target, [target]))
            else:
                targets.append(target)
        actions.append(action.model_copy(update={"targets": _canonicalize_refs(targets)}))

    relations: list[GenerationAssetRelation] = []
    discarded_relations = 0
    for relation in event.generation_relations:
        source_refs = ref_mapping[relation.source_generation_asset_ref]
        target_refs = ref_mapping[relation.target_generation_asset_ref]
        if len(source_refs) != 1 or len(target_refs) != 1:
            discarded_relations += 1
            continue
        relations.append(relation.model_copy(update={
            "source_generation_asset_ref": source_refs[0],
            "target_generation_asset_ref": target_refs[0],
        }))
    if discarded_relations:
        noun = "relación" if discarded_relations == 1 else "relaciones"
        adjective = "descartada" if discarded_relations == 1 else "descartadas"
        adjustments.append(
            f"{discarded_relations} {noun} entre plantas {adjective} al "
            "desdoblar un extremo multitecnología ambiguo."
        )

    return event.model_copy(update={
        "generation_assets": assets,
        "associated_components": components,
        "administrative_actions": actions,
        "generation_relations": relations,
    }), adjustments


def _exact_component_description(
    component_type: AssociatedComponentType,
    *,
    source_text: str,
    evidence: str,
) -> str | None:
    pattern = _component_pattern(component_type)
    for text in (evidence, source_text):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip(" ,.;:")
    return None


def _repair_component(
    component: AssociatedComponent,
    *,
    source_text: str,
    document_title: str,
) -> tuple[AssociatedComponent | None, list[str]]:
    adjustments: list[str] = []
    component_type = (
        AssociatedComponentType.EVACUATION_SYSTEM
        if component.component_type in _AUXILIARY_COMPONENT_TYPES
        else component.component_type
    )
    if component_type != component.component_type:
        adjustments.append(
            f"{component.local_component_ref}: infraestructura auxiliar agregada como sistema_evacuacion."
        )

    names = [
        name
        for name in _deduplicate_strings(component.names_raw)
        if _documentary_contains(name, source_text)
    ]
    if len(names) != len(component.names_raw):
        adjustments.append(
            f"{component.local_component_ref}: nombres no documentales del componente descartados."
        )

    pattern = _component_pattern(component_type)
    evidence = _repair_evidence(
        component.evidence,
        source_text=source_text,
        anchors=names[:1],
        semantic_patterns=[pattern],
        document_title=document_title,
    )
    if evidence is None:
        evidence = _find_literal_span(
            source_text,
            semantic_patterns=[pattern],
            document_title=document_title,
        )
    if evidence is None:
        return None, adjustments + [
            f"{component.local_component_ref}: componente opcional descartado al no localizar cita literal."
        ]

    description = component.description_raw
    if description and not _documentary_contains(description, source_text):
        description = None
    if description is None:
        description = _exact_component_description(
            component_type,
            source_text=source_text,
            evidence=evidence,
        )

    mentions, current = _repair_technical_mentions(
        component.technical_mentions,
        source_text=source_text,
        document_title=document_title,
        storage=component_type == AssociatedComponentType.ENERGY_STORAGE,
    )
    adjustments.extend(current)
    return component.model_copy(update={
        "component_type": component_type,
        "names_raw": names,
        "description_raw": description,
        "technical_mentions": mentions,
        "evidence": evidence,
    }), adjustments


def _merge_auxiliary_components(
    components: list[AssociatedComponent],
    *,
    preserve_distinct: bool = False,
) -> tuple[list[AssociatedComponent], dict[str, str], list[str]]:
    """Agrega línea/subestación/conexión en un único sistema de evacuación."""

    if preserve_distinct:
        preserved: list[AssociatedComponent] = []
        mapping: dict[str, str] = {}
        for index, component in enumerate(components, start=1):
            new_ref = f"component_{index}"
            mapping[component.local_component_ref] = new_ref
            preserved.append(component.model_copy(update={
                "local_component_ref": new_ref,
            }))
        return preserved, mapping, []

    storage: list[AssociatedComponent] = []
    auxiliary: list[AssociatedComponent] = []
    for component in components:
        if component.component_type == AssociatedComponentType.ENERGY_STORAGE:
            storage.append(component)
        else:
            auxiliary.append(component)

    merged: list[AssociatedComponent] = []
    mapping: dict[str, str] = {}
    adjustments: list[str] = []

    # Almacenamientos con nombre/evidencia distinta se conservan separados.
    for component in storage:
        new_ref = f"component_{len(merged) + 1}"
        mapping[component.local_component_ref] = new_ref
        merged.append(component.model_copy(update={"local_component_ref": new_ref}))

    if auxiliary:
        base = auxiliary[0]
        new_ref = f"component_{len(merged) + 1}"
        for component in auxiliary:
            mapping[component.local_component_ref] = new_ref
        names = _deduplicate_strings([
            name for component in auxiliary for name in component.names_raw
        ])
        related = _canonicalize_refs([
            ref
            for component in auxiliary
            for ref in component.related_generation_asset_refs
        ])
        technical = _dedupe_technical_mentions([
            mention
            for component in auxiliary
            for mention in component.technical_mentions
        ])
        evidence = min(
            (component.evidence for component in auxiliary),
            key=lambda value: len(_canonical_documentary_text(value)),
        )
        description = next(
            (component.description_raw for component in auxiliary if component.description_raw),
            None,
        )
        merged.append(base.model_copy(update={
            "local_component_ref": new_ref,
            "component_type": AssociatedComponentType.EVACUATION_SYSTEM,
            "names_raw": names,
            "description_raw": description,
            "related_generation_asset_refs": related,
            "technical_mentions": technical,
            "evidence": evidence,
        }))
        if len(auxiliary) > 1:
            adjustments.append(
                f"{len(auxiliary)} elementos auxiliares agregados en {new_ref} como sistema de evacuación."
            )

    return merged, mapping, adjustments


def _infer_component_links(
    event: PublicationEvent,
    *,
    source_text: str,
    preserve_existing: bool = False,
) -> tuple[PublicationEvent, list[str]]:
    event = event.model_copy(deep=True)
    all_refs = [asset.local_generation_asset_ref for asset in event.generation_assets]
    adjustments: list[str] = []
    if preserve_existing:
        valid_refs = set(all_refs)
        for component in event.associated_components:
            if not component.related_generation_asset_refs:
                raise ValueError(
                    f"{component.local_component_ref}: no está vinculado a "
                    "ninguna planta en la revisión manual."
                )
            missing = set(component.related_generation_asset_refs) - valid_refs
            if missing:
                raise ValueError(
                    f"{component.local_component_ref}: referencias de planta "
                    f"inexistentes en la revisión manual: {sorted(missing)}."
                )
        return event, adjustments

    hybrid_context = bool(re.search(
        r"h[ií]brid|incorporaci[oó]n\s+de\s+almacenamiento",
        _canonical_documentary_text(source_text).casefold(),
    ))

    for component in event.associated_components:
        valid = [ref for ref in component.related_generation_asset_refs if ref in all_refs]
        if len(all_refs) == 1:
            inferred = all_refs
        else:
            context = " ".join(filter(None, [
                component.evidence,
                component.description_raw,
                " ".join(component.names_raw),
            ]))
            mentioned = _generation_refs_mentioned(event, context)
            if mentioned:
                inferred = mentioned
            elif (
                component.component_type == AssociatedComponentType.ENERGY_STORAGE
                and hybrid_context
            ):
                inferred = all_refs
            else:
                inferred = valid
        inferred = _canonicalize_refs(inferred)
        if inferred != component.related_generation_asset_refs:
            adjustments.append(
                f"{component.local_component_ref}: enlaces a plantas canonicalizados como {inferred}."
            )
        component.related_generation_asset_refs = inferred
    return event, adjustments


def _normalize_action_type(action: AdministrativeAction) -> AdministrativeActionType:
    if (
        action.decision == AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
        and action.action_type in {
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
            AdministrativeActionType.ENVIRONMENTAL_IMPACT_REPORT,
            AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
        }
    ):
        return AdministrativeActionType.ENVIRONMENTAL_IMPACT_ASSESSMENT
    return action.action_type


def _normalize_action_type_from_context(
    action: AdministrativeAction,
    *,
    document_title: str,
) -> AdministrativeActionType:
    normalized = _normalize_action_type(action)
    title_types = _action_types_from_title(document_title)
    title_key = _canonical_documentary_text(document_title).casefold()

    if (
        AdministrativeActionType.WATER_CONCESSION in title_types
        and normalized == AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
        and not re.search(_ACTION_PATTERNS[AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION], title_key)
    ):
        return AdministrativeActionType.WATER_CONCESSION
    return normalized


def _action_pattern(action_type: AdministrativeActionType) -> str:
    if action_type == AdministrativeActionType.ENVIRONMENTAL_IMPACT_ASSESSMENT:
        return r"evaluaci[oó]n\s+de\s+impacto\s+ambiental|impacto\s+ambiental"
    if action_type == AdministrativeActionType.PUBLIC_INFORMATION:
        return r"informaci[oó]n\s+p[uú]blica"
    return _ACTION_PATTERNS.get(action_type, re.escape(action_type.value.replace("_", " ")))


def _repair_action_evidence(
    action: AdministrativeAction,
    *,
    source_text: str,
    document_title: str,
    title_types: set[AdministrativeActionType],
) -> str | None:
    effective = _normalize_action_type(action)
    if effective in title_types and _documentary_contains(document_title, source_text):
        return document_title
    return _repair_evidence(
        action.evidence,
        source_text=source_text,
        semantic_patterns=[_action_pattern(effective)],
        document_title=document_title,
    )


def _infer_action_targets(
    event: PublicationEvent,
    *,
    action: AdministrativeAction,
    context: str,
    preserve_existing: bool = False,
) -> list[str]:
    generation_refs = _generation_refs_mentioned(event, context, direct_only=True)
    component_refs = _component_refs_mentioned(event, context)
    mentioned = _canonicalize_refs(generation_refs + component_refs)
    all_entities = _canonicalize_refs(
        [asset.local_generation_asset_ref for asset in event.generation_assets]
        + [component.local_component_ref for component in event.associated_components]
    )

    if preserve_existing and action.targets:
        missing = set(action.targets) - {"event"} - set(all_entities)
        if missing:
            raise ValueError(
                "La revisión manual contiene targets inexistentes: "
                f"{sorted(missing)}."
            )
        return _canonicalize_refs(action.targets)

    # Si la cita enumera todos los elementos del proyecto, «event» expresa la
    # semántica con menor ambigüedad y evita duplicar la lista.
    if mentioned and set(mentioned) == set(all_entities):
        return ["event"]
    if mentioned:
        return mentioned

    valid_existing = [
        target
        for target in action.targets
        if target == "event" or target in all_entities
    ]
    if valid_existing:
        if set(valid_existing) == set(all_entities):
            return ["event"]
        return _canonicalize_refs(valid_existing)
    return ["event"]


def _canonicalize_actions(
    event: PublicationEvent,
    *,
    source_text: str,
    document_title: str,
    preserve_explicit_targets: bool = False,
) -> tuple[PublicationEvent, list[str]]:
    event = event.model_copy(deep=True)
    title_types = _action_types_from_title(document_title)
    adjustments: list[str] = []
    actions: list[AdministrativeAction] = []

    for index, original in enumerate(event.administrative_actions, start=1):
        action = original.model_copy(deep=True)
        normalized_type = _normalize_action_type_from_context(
            action,
            document_title=document_title,
        )
        if normalized_type != action.action_type:
            adjustments.append(
                f"action_{index}: producto ambiental no final normalizado a evaluación_impacto_ambiental."
            )
            action.action_type = normalized_type

        if (
            action.action_type == AdministrativeActionType.AUTHORIZATION_MODIFICATION
            and title_types & {
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeActionType.CONSTRUCTION_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeActionType.OPERATING_AUTHORIZATION,
            }
        ):
            adjustments.append(
                f"action_{index}: modificación genérica omitida; se conserva en is_modification de la autorización concreta."
            )
            continue

        # La inferencia desde título puede completar una decisión, pero el fallback
        # ambiental ``formulado`` no degrada un resultado terminal ya validado.
        if action.action_type in title_types:
            title_decision = _decision_from_title(document_title, action.action_type)
            if (
                title_decision != action.decision
                and _should_replace_decision_from_title(
                    action_type=action.action_type,
                    existing=action.decision,
                    inferred=title_decision,
                )
            ):
                previous_decision = action.decision
                action.decision = title_decision
                adjustments.append(
                    f"action_{index}: decisión canonicalizada desde el título: "
                    f"{previous_decision.value} -> {title_decision.value}."
                )

        substantive_idaa_decision = _idaa_substantive_decision(
            action,
            source_text=source_text,
            document_title=document_title,
        )
        if (
            substantive_idaa_decision is not None
            and substantive_idaa_decision != action.decision
        ):
            previous_decision = action.decision
            action.decision = substantive_idaa_decision
            adjustments.append(
                f"action_{index}: decisión IDAA canonicalizada desde el "
                f"sentido resolutivo: {previous_decision.value} -> "
                f"{substantive_idaa_decision.value}."
            )

        # Elimina antecedentes cuando el título define el objeto actual y el
        # tipo de la cita no forma parte de ese objeto.
        if (
            title_types
            and action.action_type not in title_types
            and _is_clearly_historical(action.evidence)
        ):
            adjustments.append(
                f"action_{index}: antecedente histórico omitido ({action.action_type.value})."
            )
            continue

        evidence = _repair_action_evidence(
            action,
            source_text=source_text,
            document_title=document_title,
            title_types=title_types,
        )
        if evidence is None:
            adjustments.append(
                f"action_{index}: actuación descartada al no localizar evidencia literal."
            )
            continue
        action.evidence = evidence

        expectation = _modification_expectation(action, document_title=document_title)
        if expectation is not None:
            action.is_modification = expectation

        action.targets = _infer_action_targets(
            event,
            action=action,
            context=evidence,
            preserve_existing=preserve_explicit_targets,
        )
        actions.append(action)

    existing_types = {action.action_type for action in actions}
    for action_type in sorted(title_types - existing_types, key=lambda item: item.value):
        decision = _decision_from_title(document_title, action_type)
        action = AdministrativeAction(
            action_type=action_type,
            decision=decision,
            is_modification=False,
            targets=["event"],
            evidence=document_title,
        )
        expectation = _modification_expectation(action, document_title=document_title)
        if expectation is not None:
            action.is_modification = expectation
        action.targets = _infer_action_targets(
            event,
            action=action,
            context=document_title,
        )
        actions.append(action)
        adjustments.append(
            f"Actuación actual añadida determinísticamente desde el título: {action_type.value}."
        )

    has_specific_public_info = any(
        action.decision == AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION
        and action.action_type != AdministrativeActionType.PUBLIC_INFORMATION
        for action in actions
    )
    deduped: list[AdministrativeAction] = []
    seen: set[tuple[Any, ...]] = set()
    for action in actions:
        if (
            has_specific_public_info
            and action.action_type == AdministrativeActionType.PUBLIC_INFORMATION
        ):
            adjustments.append("Información pública genérica omitida por redundancia.")
            continue
        key = (
            action.action_type,
            action.decision,
            action.is_modification,
            tuple(action.targets),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)

    event.administrative_actions = deduped
    return event, adjustments


def _remap_component_targets(
    actions: list[AdministrativeAction],
    mapping: dict[str, str],
) -> list[AdministrativeAction]:
    result: list[AdministrativeAction] = []
    for action in actions:
        targets = [mapping.get(target, target) for target in action.targets]
        targets = _canonicalize_refs(targets)
        if "event" in targets:
            targets = ["event"]
        result.append(action.model_copy(update={"targets": targets}))
    return result


def _canonicalize_generation_relations(
    event: PublicationEvent,
    *,
    source_text: str,
) -> tuple[PublicationEvent, list[str]]:
    event = event.model_copy(deep=True)
    supported: list[GenerationAssetRelation] = []
    discarded = 0
    for proposed in event.generation_relations:
        relation = proposed.model_copy(deep=True)
        source_ref = relation.source_generation_asset_ref
        target_ref = relation.target_generation_asset_ref
        if (
            relation.relation_type == GenerationRelationType.HYBRIDIZED_WITH
            and _reference_sort_key(source_ref) > _reference_sort_key(target_ref)
        ):
            source_ref, target_ref = target_ref, source_ref
        relation = relation.model_copy(update={
            "source_generation_asset_ref": source_ref,
            "target_generation_asset_ref": target_ref,
        })
        if _generation_relation_has_documentary_support(
            event,
            relation,
            source_text=source_text,
        ):
            supported.append(relation)
        else:
            discarded += 1

    unique: dict[tuple[str, str, str], GenerationAssetRelation] = {}
    for relation in supported:
        key = (
            relation.source_generation_asset_ref,
            relation.target_generation_asset_ref,
            relation.relation_type.value,
        )
        unique.setdefault(key, relation)
    event.generation_relations = list(unique.values())

    adjustments: list[str] = []
    if discarded:
        noun = "relación" if discarded == 1 else "relaciones"
        adjective = "descartada" if discarded == 1 else "descartadas"
        adjustments.append(
            f"{discarded} {noun} entre plantas {adjective} por "
            "soporte documental insuficiente."
        )
    return event, adjustments


def _generation_relation_semantic_pattern(
    relation_type: GenerationRelationType,
) -> str:
    if relation_type == GenerationRelationType.HYBRIDIZED_WITH:
        return r"h[ií]brid"
    return r"sustitu|reemplaz"


def _relation_evidence_units(
    evidence: str,
    source_text: str,
) -> list[tuple[str, int, int]]:
    segments = [
        _canonical_documentary_text(segment).casefold()
        for segment in _evidence_segments(evidence)
    ]
    if not segments:
        return []
    aligned_units: list[tuple[str, int, int]] = []
    for source_unit in _source_units(source_text):
        source_key = _canonical_documentary_text(source_unit).casefold()
        for first_match in re.finditer(re.escape(segments[0]), source_key):
            cursor = first_match.end()
            positions = [first_match.span()]
            for segment in segments[1:]:
                position = source_key.find(segment, cursor)
                if position < 0:
                    break
                cursor = position + len(segment)
                positions.append((position, cursor))
            else:
                evidence_start = positions[0][0]
                evidence_end = positions[-1][1]
                candidate = (source_key, evidence_start, evidence_end)
                if candidate not in aligned_units:
                    aligned_units.append(candidate)

    return sorted(
        aligned_units,
        key=lambda item: (len(item[0]), item[1], item[2]),
    )


_HYBRID_CONNECTOR_RE = re.compile(
    r"\b(?:"
    r"(?:se\s+)?h[ií]brid(?:a(?:n)?|ar[aá]n?|ad[oa]s?)|"
    r"ser[aá]n?\s+h[ií]bridad[oa]s?|"
    r"(?:para\s+su|y\s+su|su)\s+hibridaci[oó]n|"
    r"h[ií]brid[oa]s?"
    r")\b"
    r"(?:\s+(?:materialmente|directamente|expresamente|expl[ií]citamente))?"
    r"\s+con\b",
    re.IGNORECASE,
)
_ACTIVE_REPLACEMENT_RE = re.compile(
    r"\b(?:sustituye(?:n)?|sustituir[aá]n?|reemplaza(?:n)?|reemplazar[aá]n?)\b"
    r"(?:\s+(?:materialmente|directamente|expresamente|expl[ií]citamente|"
    r"[ií]ntegramente))?\s+(?:a|al)\b",
    re.IGNORECASE,
)
_PASSIVE_REPLACEMENT_RE = re.compile(
    r"\b(?:ser[aá]n?|es|son|fue(?:ron)?|ha(?:n)?\s+sido)\s+"
    r"(?:sustituid[oa]s?|reemplazad[oa]s?)\s+por\b",
    re.IGNORECASE,
)
_RELATION_SUFFIX_REJECTION_RE = re.compile(
    r"\b(?:queda\s+)?(?:descartad[ao]s?|excluid[ao]s?|rechazad[ao]s?)\b|"
    r"\bopci[oó]n\s+descartada\b|"
    r"\bno\s+siendo\s+autorizad[oa]s?\b|"
    r"\b(?:relaci[oó]n|hibridaci[oó]n|sustituci[oó]n|reemplazo)\s+"
    r"(?:no\s+autorizad[oa]s?|denegad[oa]s?)\b|"
    r"\bsin\s+autorizaci[oó]n\b",
    re.IGNORECASE,
)
_GENERATION_ENDPOINT_ROLE_RE = re.compile(
    r"\b(?:psf(?:v)?|fv|peol)\b|"
    r"\b(?:plantas?|parques?|centrales?|instalaciones?|m[oó]dulos?)\s+"
    r"(?:de\s+generaci[oó]n(?:\s+de\s+energ[ií]a\s+el[eé]ctrica)?|"
    r"(?:solares?\s+)?fotovoltaic[ao]s?|solares?|e[oó]lic[ao]s?|"
    r"termosolares?|solar\s+termoel[eé]ctric[ao]s?|"
    r"hidroel[eé]ctric[ao]s?|de\s+cogeneraci[oó]n"
    r"(?:\s+termoel[eé]ctrica)?)\b|"
    r"\baerogeneradores?\b",
    re.IGNORECASE,
)


def _relation_clause_bounds(
    unit: str,
    start: int,
    end: int,
) -> tuple[int, int]:
    clause_start = max(
        unit.rfind(".", 0, start),
        unit.rfind(";", 0, start),
        unit.rfind(":", 0, start),
    ) + 1
    clause_ends = [
        position
        for mark in ".;:"
        if (position := unit.find(mark, end)) >= 0
    ]
    return clause_start, min(clause_ends, default=len(unit))


def _strict_alias_spans(text: str, alias: str) -> list[tuple[int, int]]:
    return [
        match.span()
        for match in re.finditer(
            rf"(?<!\w){re.escape(alias)}(?!\w)",
            text,
            re.IGNORECASE,
        )
    ]


def _resolved_generation_name_spans(
    unit: str,
    event: PublicationEvent,
) -> list[tuple[int, int, set[str]]]:
    aliases_by_owner: dict[str, set[str]] = {}
    for asset in event.generation_assets:
        for name in asset.names_raw:
            alias = _canonical_documentary_text(name).casefold()
            if alias:
                aliases_by_owner.setdefault(alias, set()).add(
                    asset.local_generation_asset_ref
                )

    candidates: list[tuple[int, int, set[str]]] = []
    for alias in sorted(aliases_by_owner, key=lambda item: (-len(item), item)):
        owners = aliases_by_owner[alias]
        for start, end in _strict_alias_spans(unit, alias):
            candidates.append((start, end, owners))

    ambiguous: set[int] = set()
    for index, (start, end, _) in enumerate(candidates):
        for other_index, (other_start, other_end, _) in enumerate(
            candidates[index + 1:],
            start=index + 1,
        ):
            if not (start < other_end and other_start < end):
                continue
            contains_other = start <= other_start and other_end <= end
            other_contains = other_start <= start and end <= other_end
            if not contains_other and not other_contains:
                ambiguous.update((index, other_index))

    accepted: list[tuple[int, int, set[str]]] = []
    unambiguous = [
        candidate
        for index, candidate in enumerate(candidates)
        if index not in ambiguous
    ]
    for start, end, owners in sorted(
        unambiguous,
        key=lambda item: (-(item[1] - item[0]), item[0], item[1]),
    ):
        if any(
            start < existing_end and existing_start < end
            for existing_start, existing_end, _ in accepted
        ):
            continue
        accepted.append((start, end, owners))
    return sorted(accepted, key=lambda item: (item[0], item[1]))


def _generation_relation_name_span_pairs(
    unit: str,
    resolved_spans: list[tuple[int, int, set[str]]],
    event: PublicationEvent,
    source_asset: GenerationAssetMention,
    target_asset: GenerationAssetMention,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    assets_by_ref = {
        asset.local_generation_asset_ref: asset
        for asset in event.generation_assets
    }

    def identifies(
        span: tuple[int, int],
        owners: set[str],
        asset: GenerationAssetMention,
    ) -> bool:
        ref = asset.local_generation_asset_ref
        if owners == {ref}:
            return True
        typed_owners = {
            owner
            for owner in owners
            if owner in assets_by_ref
            and _generation_span_declares_type(
                unit,
                span,
                assets_by_ref[owner].generation_type,
            )
        }
        return typed_owners == {ref}

    return [
        ((source_start, source_end), (target_start, target_end))
        for source_start, source_end, source_owners in resolved_spans
        if identifies(
            (source_start, source_end),
            source_owners,
            source_asset,
        )
        for target_start, target_end, target_owners in resolved_spans
        if identifies(
            (target_start, target_end),
            target_owners,
            target_asset,
        )
        and (
            source_end <= target_start
            or target_end <= source_start
        )
    ]


def _generation_span_declares_type(
    unit: str,
    span: tuple[int, int],
    generation_type: GenerationType,
) -> bool:
    pattern = _GENERATION_TYPE_PATTERNS.get(generation_type)
    if pattern is None:
        return False
    if re.search(pattern, unit[span[0]:span[1]], re.IGNORECASE):
        return True

    clause_start, _ = _relation_clause_bounds(unit, span[0], span[1])
    prefix = unit[clause_start:span[0]]
    qualifiers = (
        r"(?:\s+(?:existente|en\s+operaci[oó]n|denominad[oa]s?"
        r"(?:\s+como)?|llamad[oa]s?))*"
    )
    return bool(re.search(
        rf"(?:{pattern})\w*{qualifiers}\s*[\"']?\s*$",
        prefix,
        re.IGNORECASE,
    ))


def _generation_span_is_storage_context(
    unit: str,
    span: tuple[int, int],
) -> bool:
    clause_start, clause_end = _relation_clause_bounds(unit, span[0], span[1])
    prefix = unit[clause_start:span[0]]
    suffix = unit[span[1]:clause_end]
    storage_pattern = _component_pattern(AssociatedComponentType.ENERGY_STORAGE)

    if re.match(
        r"[\s,\"']*(?:bess\b|bater[ií]as?\b|"
        r"(?:m[oó]dulos?|sistemas?|instalaciones?)\s+"
        r"(?:de\s+)?almacenamiento\b)",
        suffix,
        re.IGNORECASE,
    ):
        return True

    scope_start = clause_start
    connectors = list(_HYBRID_CONNECTOR_RE.finditer(prefix))
    if connectors:
        scope_start += connectors[-1].end()
    scope = unit[scope_start:span[1]]
    storage_positions = [
        match.start()
        for match in re.finditer(storage_pattern, scope, re.IGNORECASE)
    ]
    generation_positions = [
        match.start() for match in _GENERATION_ENDPOINT_ROLE_RE.finditer(scope)
    ]
    if max(storage_positions, default=-1) >= max(generation_positions, default=-1) >= 0:
        return True
    if not re.search(storage_pattern, prefix, re.IGNORECASE):
        return False
    if re.search(
        r"\b(?:para\s+su|y\s+su|su)\s+h[ií]brid",
        suffix,
        re.IGNORECASE,
    ):
        return True
    return bool(re.search(
        storage_pattern
        + r"[^.;:]*(?:(?:asociad[oa]s?|vinculad[oa]s?|destinad[oa]s?)\s+"
        + r"(?:a|al|con)\b|(?:perteneciente|adscrit[oa]s?|ligad[oa]s?)\s+"
        + r"(?:a|al)\b|de(?:l|\s+la)\b)[^.;:]*$",
        prefix,
        re.IGNORECASE,
    ))


def _relation_target_tail_is_clean(value: str) -> bool:
    if re.search(r"[.;:]", value):
        return False
    if "," in value and not re.fullmatch(
        r"[^,]*,\s*(?:denominad[oa]s?|llamad[oa]s?)\s*[\"«»]?\s*",
        value,
        re.IGNORECASE,
    ):
        return False
    if re.search(
        _component_pattern(AssociatedComponentType.ENERGY_STORAGE),
        value,
        re.IGNORECASE,
    ):
        return False
    return not re.search(
        r"\b(?:y|e|pero|mientras|aunque|junto|con|transformadores?|"
        r"expedientes?|tramita\w*|comparte\w*|estudia\w*)\b",
        value,
        re.IGNORECASE,
    )


def _relation_predicate_is_negative(
    unit: str,
    left_span: tuple[int, int],
    connector_start: int,
) -> bool:
    clause_start, _ = _relation_clause_bounds(
        unit,
        left_span[0],
        left_span[1],
    )
    introduction = re.split(
        r"\bpero\b",
        unit[clause_start:left_span[0]],
        flags=re.IGNORECASE,
    )[-1]
    if re.search(
        r"\b(?:no\s+se\s+autoriza\w*\s+que|sin\s+que)\s*$",
        introduction,
        re.IGNORECASE,
    ):
        return True

    predicate_prefix = unit[left_span[1]:connector_start]
    return bool(re.search(
        r"\bno\s+(?!solo\b)(?:se\s+)?$",
        predicate_prefix,
        re.IGNORECASE,
    ))


def _relation_clause_suffix_is_rejected(
    unit: str,
    source_span: tuple[int, int],
    target_span: tuple[int, int],
) -> bool:
    right_end = max(source_span[1], target_span[1])
    _, clause_end = _relation_clause_bounds(unit, right_end, right_end)
    return bool(_RELATION_SUFFIX_REJECTION_RE.search(unit[right_end:clause_end]))


def _intervening_generation_names_are_coordinated(
    unit: str,
    *,
    left_end: int,
    connector_start: int,
    resolved_spans: list[tuple[int, int, set[str]]],
) -> bool:
    intervening = [
        (start, end)
        for start, end, _ in resolved_spans
        if left_end <= start and end <= connector_start
    ]
    if not intervening:
        return True

    cursor = left_end
    for start, end in intervening:
        if not re.fullmatch(
            r"\s*(?:,\s*)?(?:y|e)\s+",
            unit[cursor:start],
            re.IGNORECASE,
        ):
            return False
        cursor = end
    return not unit[cursor:connector_start].strip()


def _relation_context_has_no_other_generation_name(
    *,
    context_start: int,
    context_end: int,
    resolved_spans: list[tuple[int, int, set[str]]],
) -> bool:
    return not any(
        context_start <= start and end <= context_end
        for start, end, _ in resolved_spans
    )


def _positive_relation_structure_is_supported(
    unit: str,
    relation_type: GenerationRelationType,
    source_span: tuple[int, int],
    target_span: tuple[int, int],
    *,
    resolved_spans: list[tuple[int, int, set[str]]],
) -> bool:
    left_span, right_span = sorted((source_span, target_span))
    between = unit[left_span[1]:right_span[0]]
    if re.search(r"[.;:]", between):
        return False
    if _relation_clause_suffix_is_rejected(unit, source_span, target_span):
        return False

    def connector_is_local(connector: re.Match[str]) -> bool:
        connector_start = left_span[1] + connector.start()
        connector_end = left_span[1] + connector.end()
        if _relation_predicate_is_negative(unit, left_span, connector_start):
            return False
        if not _intervening_generation_names_are_coordinated(
            unit,
            left_end=left_span[1],
            connector_start=connector_start,
            resolved_spans=resolved_spans,
        ):
            return False
        if not _relation_context_has_no_other_generation_name(
            context_start=connector_end,
            context_end=right_span[0],
            resolved_spans=resolved_spans,
        ):
            return False
        return _relation_target_tail_is_clean(
            unit[connector_end:right_span[0]]
        )

    if relation_type == GenerationRelationType.HYBRIDIZED_WITH:
        for connector in _HYBRID_CONNECTOR_RE.finditer(between):
            connector_key = connector.group().strip().casefold()
            source_gap = between[:connector.start()]
            has_storage = bool(re.search(
                _component_pattern(AssociatedComponentType.ENERGY_STORAGE),
                source_gap,
                re.IGNORECASE,
            ))
            allows_storage_bundle = bool(re.match(
                r"(?:para\s+su|y\s+su|su)\s+hibridaci[oó]n",
                connector_key,
            )) and not _generation_span_is_storage_context(unit, left_span)
            if has_storage and not allows_storage_bundle:
                continue
            if connector_is_local(connector):
                return True

        clause_start, _ = _relation_clause_bounds(
            unit,
            left_span[0],
            right_span[1],
        )
        before_left = unit[clause_start:left_span[0]]
        nominal = re.search(
            r"\bhibridaci[oó]n\s+de\s+(?:la\s+|el\s+|los\s+|las\s+)?$",
            before_left,
            re.IGNORECASE,
        )
        if nominal is None or re.search(
            r"\b(?:carece\s+de|renuncia\s+a\s+la|no\s+se\s+autoriza\w*)\s*$",
            before_left[:nominal.start()],
            re.IGNORECASE,
        ):
            return False
        connector = re.match(r"\s+con\b", between, re.IGNORECASE)
        return bool(
            connector
            and _relation_context_has_no_other_generation_name(
                context_start=left_span[1] + connector.end(),
                context_end=right_span[0],
                resolved_spans=resolved_spans,
            )
            and _relation_target_tail_is_clean(between[connector.end():])
        )

    if source_span[1] <= target_span[0]:
        connector = _ACTIVE_REPLACEMENT_RE.search(between)
        return bool(connector and connector_is_local(connector))

    connector = _PASSIVE_REPLACEMENT_RE.search(between)
    return bool(connector and connector_is_local(connector))


def _explicit_shared_name_hybrid_is_supported(
    unit: str,
    source_asset: GenerationAssetMention,
    target_asset: GenerationAssetMention,
    resolved_spans: list[tuple[int, int, set[str]]],
) -> bool:
    if source_asset.generation_type == target_asset.generation_type:
        return False
    source_pattern = _GENERATION_TYPE_PATTERNS.get(source_asset.generation_type)
    target_pattern = _GENERATION_TYPE_PATTERNS.get(target_asset.generation_type)
    if source_pattern is None or target_pattern is None:
        return False

    endpoint_refs = {
        source_asset.local_generation_asset_ref,
        target_asset.local_generation_asset_ref,
    }
    shared_aliases = sorted({
        _canonical_documentary_text(name).casefold()
        for name in source_asset.names_raw
    } & {
        _canonical_documentary_text(name).casefold()
        for name in target_asset.names_raw
    }, key=lambda item: (-len(item), item))
    if not shared_aliases:
        return False
    alias_pattern = "(?:" + "|".join(map(re.escape, shared_aliases)) + ")"

    for alias_start, alias_end, owners in resolved_spans:
        if not endpoint_refs <= owners:
            continue
        clause_start, clause_end = _relation_clause_bounds(
            unit, alias_start, alias_end
        )
        if any(
            clause_start <= start < clause_end and bool(owners - endpoint_refs)
            for start, _, owners in resolved_spans
        ):
            continue
        clause = unit[clause_start:clause_end]
        aliases = [
            (start - clause_start, end - clause_start)
            for start, end, owners in resolved_spans
            if clause_start <= start < clause_end and endpoint_refs <= owners
        ]
        named_template = re.search(
            r"(?:\bhibridaci[oó]n\s+de\s+(?:la\s+|el\s+)?"
            r"(?:instalaci[oó]n|planta)\s+[\"']?" + alias_pattern
            + r"[\"']?\s+con\s+tecnolog[ií]a\b|"
            r"\b(?:instalaci[oó]n|planta)\s+h[ií]brid[ao]\s+[\"']?"
            + alias_pattern + r"[\"']?)",
            clause,
            re.IGNORECASE,
        )
        source_types = re.finditer(source_pattern, clause, re.IGNORECASE)
        target_type_spans = [
            match.span()
            for match in re.finditer(target_pattern, clause, re.IGNORECASE)
        ]
        for source_match in source_types:
            for target_type in target_type_spans:
                source_type = source_match.span()
                if not (
                    source_type[1] <= target_type[0]
                    or target_type[1] <= source_type[0]
                ):
                    continue
                left_type, right_type = sorted((source_type, target_type))
                type_gap = clause[left_type[1]:right_type[0]]
                connector = _HYBRID_CONNECTOR_RE.search(type_gap)
                if connector:
                    connector_start = left_type[1] + connector.start()
                    alias_encloses_types = any(
                        start <= left_type[0] and right_type[1] <= end
                        for start, end in aliases
                    )
                    if alias_encloses_types or (
                        not any(
                            left_type[1] <= start < connector_start
                            for start, _ in aliases
                        )
                        and any(start >= right_type[1] for start, _ in aliases)
                    ):
                        return True
                if named_template and re.search(
                    r"\b(?:y|e)\b", type_gap, re.IGNORECASE
                ):
                    return True
    return False


def _generation_relation_has_documentary_support(
    event: PublicationEvent,
    relation: GenerationAssetRelation,
    *,
    source_text: str,
) -> bool:
    """Exige una relación material literal que identifique ambos activos."""

    assets_by_ref = {
        asset.local_generation_asset_ref: asset
        for asset in event.generation_assets
    }
    source_asset = assets_by_ref.get(relation.source_generation_asset_ref)
    target_asset = assets_by_ref.get(relation.target_generation_asset_ref)
    if source_asset is None or target_asset is None:
        return False
    if not _evidence_is_supported(relation.evidence, source_text):
        return False
    evidence_key = " ".join(
        _canonical_documentary_text(segment).casefold()
        for segment in _evidence_segments(relation.evidence)
    )
    if not re.search(
        _generation_relation_semantic_pattern(relation.relation_type),
        evidence_key,
        re.IGNORECASE,
    ):
        return False

    for unit, evidence_start, evidence_end in _relation_evidence_units(
        relation.evidence,
        source_text,
    ):
        context_spans = _resolved_generation_name_spans(unit, event)
        resolved_spans = [
            (start, end, owners)
            for start, end, owners in context_spans
            if evidence_start <= start and end <= evidence_end
        ]
        span_pairs = _generation_relation_name_span_pairs(
            unit,
            resolved_spans,
            event,
            source_asset,
            target_asset,
        )
        for source_span, target_span in span_pairs:
            if (
                _generation_span_is_storage_context(unit, source_span)
                or _generation_span_is_storage_context(unit, target_span)
            ):
                continue
            if _positive_relation_structure_is_supported(
                unit,
                relation.relation_type,
                source_span,
                target_span,
                resolved_spans=context_spans,
            ):
                return True
        if (
            relation.relation_type == GenerationRelationType.HYBRIDIZED_WITH
            and _explicit_shared_name_hybrid_is_supported(
                unit,
                source_asset,
                target_asset,
                resolved_spans,
            )
        ):
            return True
    return False


def _supported_generation_relations(
    event: PublicationEvent,
    source_text: str,
) -> list[GenerationAssetRelation]:
    return [
        relation
        for relation in event.generation_relations
        if _generation_relation_has_documentary_support(
            event,
            relation,
            source_text=source_text,
        )
    ]


def _material_generation_groups(
    event: PublicationEvent,
    source_text: str,
    *,
    supported_relations: list[GenerationAssetRelation] | None = None,
) -> list[list[str]]:
    refs = [
        asset.local_generation_asset_ref
        for asset in event.generation_assets
    ]
    neighbors = {ref: set() for ref in refs}
    relations = (
        supported_relations
        if supported_relations is not None
        else _supported_generation_relations(event, source_text)
    )
    for relation in relations:
        source_ref = relation.source_generation_asset_ref
        target_ref = relation.target_generation_asset_ref
        neighbors[source_ref].add(target_ref)
        neighbors[target_ref].add(source_ref)

    groups: list[list[str]] = []
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        pending = [ref]
        group_refs: set[str] = set()
        while pending:
            current = pending.pop()
            if current in group_refs:
                continue
            group_refs.add(current)
            pending.extend(neighbors[current] - group_refs)
        seen.update(group_refs)
        groups.append([item for item in refs if item in group_refs])
    return groups


def _event_is_integrated(event: PublicationEvent, source_text: str) -> bool:
    return len(_material_generation_groups(event, source_text)) == 1


def _renumber_event(event: PublicationEvent) -> PublicationEvent:
    event = event.model_copy(deep=True)
    generation_mapping = {
        asset.local_generation_asset_ref: f"generation_asset_{index}"
        for index, asset in enumerate(event.generation_assets, start=1)
    }
    for asset in event.generation_assets:
        asset.local_generation_asset_ref = generation_mapping[asset.local_generation_asset_ref]

    component_mapping = {
        component.local_component_ref: f"component_{index}"
        for index, component in enumerate(event.associated_components, start=1)
    }
    for component in event.associated_components:
        component.local_component_ref = component_mapping[component.local_component_ref]
        component.related_generation_asset_refs = _canonicalize_refs([
            generation_mapping[ref]
            for ref in component.related_generation_asset_refs
            if ref in generation_mapping
        ])

    for action in event.administrative_actions:
        targets: list[str] = []
        for target in action.targets:
            if target == "event":
                targets = ["event"]
                break
            if target in generation_mapping:
                targets.append(generation_mapping[target])
            elif target in component_mapping:
                targets.append(component_mapping[target])
        action.targets = _canonicalize_refs(targets) if targets else ["event"]

    for relation in event.generation_relations:
        relation.source_generation_asset_ref = generation_mapping[
            relation.source_generation_asset_ref
        ]
        relation.target_generation_asset_ref = generation_mapping[
            relation.target_generation_asset_ref
        ]
    return event


def _event_for_material_generation_group(
    event: PublicationEvent,
    *,
    group_refs: list[str],
    supported_relations: list[GenerationAssetRelation],
) -> PublicationEvent | None:
    event = event.model_copy(deep=True)
    group_set = set(group_refs)
    generation_assets = [
        asset
        for asset in event.generation_assets
        if asset.local_generation_asset_ref in group_set
    ]

    associated_components: list[AssociatedComponent] = []
    for component in event.associated_components:
        original_refs = component.related_generation_asset_refs
        if not original_refs:
            continue
        related_refs = [ref for ref in original_refs if ref in group_set]
        if not related_refs:
            continue
        associated_components.append(component.model_copy(update={
            "related_generation_asset_refs": related_refs,
        }))
    component_refs = {
        component.local_component_ref
        for component in associated_components
    }

    actions: list[AdministrativeAction] = []
    for action in event.administrative_actions:
        if action.targets == ["event"]:
            actions.append(action.model_copy(deep=True))
            continue
        targets = _canonicalize_refs([
            target
            for target in action.targets
            if target in group_set or target in component_refs
        ])
        if targets:
            actions.append(action.model_copy(update={"targets": targets}))
    if not actions:
        return None

    generation_relations = [
        relation.model_copy(deep=True)
        for relation in supported_relations
        if {
            relation.source_generation_asset_ref,
            relation.target_generation_asset_ref,
        } <= group_set
    ]
    grouped_event = event.model_copy(update={
        "generation_assets": generation_assets,
        "associated_components": associated_components,
        "administrative_actions": actions,
        "generation_relations": generation_relations,
    })
    return _renumber_event(grouped_event)


def _split_independent_generation_event(
    event: PublicationEvent,
    *,
    source_text: str,
) -> tuple[list[PublicationEvent], list[str]]:
    supported_relations = _supported_generation_relations(event, source_text)
    groups = _material_generation_groups(
        event,
        source_text,
        supported_relations=supported_relations,
    )
    discarded_relations = len(event.generation_relations) - len(supported_relations)
    relation_adjustments: list[str] = []
    if discarded_relations:
        noun = "relación" if discarded_relations == 1 else "relaciones"
        adjective = "descartada" if discarded_relations == 1 else "descartadas"
        relation_adjustments.append(
            f"{discarded_relations} {noun} entre plantas {adjective} por "
            "soporte documental insuficiente."
        )
    if len(groups) == 1:
        event = event.model_copy(deep=True, update={
            "generation_relations": [
                relation.model_copy(deep=True)
                for relation in supported_relations
            ]
        })
        return [_renumber_event(event)], relation_adjustments

    split_events: list[PublicationEvent] = []
    discarded_groups = 0
    for group_refs in groups:
        grouped_event = _event_for_material_generation_group(
            event,
            group_refs=group_refs,
            supported_relations=supported_relations,
        )
        if grouped_event is None:
            discarded_groups += 1
        else:
            split_events.append(grouped_event)

    adjustments = list(relation_adjustments)
    unlinked_components = sum(
        not component.related_generation_asset_refs
        for component in event.associated_components
    )
    if unlinked_components:
        noun = "componente" if unlinked_components == 1 else "componentes"
        adjective = "descartado" if unlinked_components == 1 else "descartados"
        adjustments.append(
            f"{unlinked_components} {noun} sin vínculos de generación {adjective} "
            "durante el split por grupos materiales."
        )
    if discarded_groups:
        noun = "grupo" if discarded_groups == 1 else "grupos"
        material = "material" if discarded_groups == 1 else "materiales"
        adjective = "descartado" if discarded_groups == 1 else "descartados"
        adjustments.append(
            f"{discarded_groups} {noun} {material} {adjective} al no conservar "
            "ninguna actuación vinculada."
        )
    adjustments.append(
        f"Evento con {len(event.generation_assets)} plantas dividido en "
        f"{len(groups)} grupos materiales independientes."
    )
    return split_events, adjustments


def _canonicalize_optional_mentions(
    event: PublicationEvent,
    *,
    source_text: str,
    document_title: str,
) -> tuple[PublicationEvent, list[str]]:
    event = event.model_copy(deep=True)
    adjustments: list[str] = []

    participants: list[ParticipantMention] = []
    for participant in event.participants:
        if not _documentary_contains(participant.participant_name_raw, source_text):
            adjustments.append(
                f"Participante no documental descartado: {participant.participant_name_raw!r}."
            )
            continue
        evidence = _repair_evidence(
            participant.evidence,
            source_text=source_text,
            anchors=[participant.participant_name_raw],
            document_title=document_title,
        )
        if evidence is not None:
            participants.append(participant.model_copy(update={"evidence": evidence}))
    event.participants = participants

    locations: list[AdministrativeLocationMention] = []
    for location in event.administrative_locations:
        if not _documentary_contains(location.location_name_raw, source_text):
            adjustments.append(
                f"Localización no documental descartada: {location.location_name_raw!r}."
            )
            continue
        evidence = _repair_evidence(
            location.evidence,
            source_text=source_text,
            anchors=[location.location_name_raw],
            document_title=document_title,
        )
        if evidence is not None:
            locations.append(location.model_copy(update={"evidence": evidence}))
    event.administrative_locations = locations
    event.case_file_references = [
        value
        for value in _deduplicate_strings(event.case_file_references)
        if _documentary_contains(value, source_text)
    ]
    return event, adjustments


def canonicalize_project_extraction(
    extraction: BOEProjectExtraction,
    *,
    source_text: str,
    document_title: str,
) -> tuple[BOEProjectExtraction, list[str]]:
    return _canonicalize_project_extraction(
        extraction,
        source_text=source_text,
        document_title=document_title,
        preserve_explicit_semantics=False,
    )


def canonicalize_reviewed_project_extraction(
    extraction: BOEProjectExtraction,
    *,
    source_text: str,
    document_title: str,
) -> tuple[BOEProjectExtraction, list[str]]:
    """Canonicaliza una revisión sin sobrescribir sus relaciones explícitas."""

    return _canonicalize_project_extraction(
        extraction,
        source_text=source_text,
        document_title=document_title,
        preserve_explicit_semantics=True,
    )


def _canonicalize_project_extraction(
    extraction: BOEProjectExtraction,
    *,
    source_text: str,
    document_title: str,
    preserve_explicit_semantics: bool,
) -> tuple[BOEProjectExtraction, list[str]]:
    extraction = extraction.model_copy(deep=True)
    adjustments: list[str] = []

    scope_decision, scope_reason = _scope_guard_from_document(
        document_title=document_title,
        source_text=source_text,
    )
    if scope_decision == ScopeGuardDecision.FORCE_NOT_RELEVANT:
        if (
            extraction.document_scope != DocumentScope.NOT_RELEVANT_FOR_GENERATION_PROJECTS
            or extraction.publication_events
        ):
            adjustments.append(
                "Alcance corregido determinísticamente a no relevante: "
                f"{scope_reason}"
            )
        return (
            _force_non_relevant_extraction(
                extraction,
                reason=scope_reason or "Documento fuera del alcance del TFM.",
            ),
            adjustments,
        )

    canonical_events: list[PublicationEvent] = []

    for original_event in extraction.publication_events:
        event = original_event.model_copy(deep=True)

        repaired_assets: list[GenerationAssetMention] = []
        old_to_new: dict[str, str] = {}
        for asset in event.generation_assets:
            repaired, current = _repair_generation_asset(
                asset,
                source_text=source_text,
                document_title=document_title,
            )
            adjustments.extend(current)
            if repaired is None:
                continue
            new_ref = f"generation_asset_{len(repaired_assets) + 1}"
            old_to_new[asset.local_generation_asset_ref] = new_ref
            repaired_assets.append(repaired.model_copy(update={
                "local_generation_asset_ref": new_ref,
            }))
        event.generation_assets = repaired_assets
        if not event.generation_assets:
            adjustments.append("Evento descartado al no conservar ninguna planta de generación identificable.")
            continue

        # Reasigna referencias del modelo a las plantas conservadas.
        for component in event.associated_components:
            component.related_generation_asset_refs = _canonicalize_refs([
                old_to_new[ref]
                for ref in component.related_generation_asset_refs
                if ref in old_to_new
            ])
        for action in event.administrative_actions:
            remapped: list[str] = []
            for target in action.targets:
                if target.startswith("generation_asset_"):
                    if target in old_to_new:
                        remapped.append(old_to_new[target])
                    elif preserve_explicit_semantics:
                        raise ValueError(
                            "La revisión manual referencia una planta que no "
                            "pudo conservarse durante la canonicalización."
                        )
                else:
                    remapped.append(target)
            action.targets = _canonicalize_refs(remapped) if remapped else []
        remapped_relations: list[GenerationAssetRelation] = []
        discarded_relation_count = 0
        for relation in event.generation_relations:
            source_ref = relation.source_generation_asset_ref
            target_ref = relation.target_generation_asset_ref
            if source_ref not in old_to_new or target_ref not in old_to_new:
                discarded_relation_count += 1
                continue
            remapped_relations.append(relation.model_copy(update={
                "source_generation_asset_ref": old_to_new[source_ref],
                "target_generation_asset_ref": old_to_new[target_ref],
            }))
        event.generation_relations = remapped_relations
        if discarded_relation_count:
            noun = "relación" if discarded_relation_count == 1 else "relaciones"
            adjective = (
                "descartada" if discarded_relation_count == 1 else "descartadas"
            )
            adjustments.append(
                f"{discarded_relation_count} {noun} entre plantas {adjective} "
                "al eliminar un extremo no documental."
            )

        event, current = _expand_multitechnology_generation_assets(
            event,
            source_text=source_text,
        )
        adjustments.extend(current)

        repaired_components: list[AssociatedComponent] = []
        for component in event.associated_components:
            repaired, current = _repair_component(
                component,
                source_text=source_text,
                document_title=document_title,
            )
            adjustments.extend(current)
            if repaired is not None:
                repaired_components.append(repaired)
            elif preserve_explicit_semantics:
                raise ValueError(
                    f"{component.local_component_ref}: el componente revisado "
                    "no pudo validarse contra el documento."
                )
        event.associated_components = repaired_components

        # Si el título menciona evacuación y no existe componente, se crea una
        # única entidad secundaria con evidencia literal. El almacenamiento no
        # se fabrica porque requiere identidad y magnitudes propias.
        title_key = _canonical_documentary_text(document_title).casefold()
        if (
            re.search(_component_pattern(AssociatedComponentType.EVACUATION_SYSTEM), title_key)
            and not any(
                component.component_type in _AUXILIARY_COMPONENT_TYPES
                or component.component_type == AssociatedComponentType.EVACUATION_SYSTEM
                for component in event.associated_components
            )
        ):
            description = _exact_component_description(
                AssociatedComponentType.EVACUATION_SYSTEM,
                source_text=source_text,
                evidence=document_title,
            )
            event.associated_components.append(AssociatedComponent(
                local_component_ref=f"component_{len(event.associated_components) + 1}",
                component_type=AssociatedComponentType.EVACUATION_SYSTEM,
                names_raw=[],
                description_raw=description,
                related_generation_asset_refs=[],
                technical_mentions=[],
                evidence=document_title,
            ))
            adjustments.append("Sistema de evacuación materializado desde el título literal.")

        merged_components, component_mapping, current = _merge_auxiliary_components(
            event.associated_components,
            preserve_distinct=preserve_explicit_semantics,
        )
        adjustments.extend(current)
        event.associated_components = merged_components
        event.administrative_actions = _remap_component_targets(
            event.administrative_actions,
            component_mapping,
        )

        event, current = _infer_component_links(
            event,
            source_text=source_text,
            preserve_existing=preserve_explicit_semantics,
        )
        adjustments.extend(current)
        event, current = _canonicalize_actions(
            event,
            source_text=source_text,
            document_title=document_title,
            preserve_explicit_targets=preserve_explicit_semantics,
        )
        adjustments.extend(current)
        event, current = _canonicalize_generation_relations(
            event,
            source_text=source_text,
        )
        adjustments.extend(current)
        event, current = _canonicalize_optional_mentions(
            event,
            source_text=source_text,
            document_title=document_title,
        )
        adjustments.extend(current)

        split_events, current = _split_independent_generation_event(
            event,
            source_text=source_text,
        )
        adjustments.extend(current)
        canonical_events.extend(split_events)

    extraction.publication_events = canonical_events
    if (
        extraction.document_scope == DocumentScope.GENERATION_PROJECT_SPECIFIC
        and not canonical_events
    ):
        extraction.classification_status = ClassificationStatus.UNCERTAIN
        extraction.document_scope = None
        extraction.classification_reason = (
            "No se pudo conservar una planta de generación con nombre literal y evidencia suficiente."
        )
        extraction.extraction_notes = (
            "La publicación requiere revisión porque el modelo no identificó de forma inequívoca la raíz de generación."
        )

    canonical = BOEProjectExtraction.model_validate(extraction.model_dump())
    return canonical, adjustments
