from __future__ import annotations

import re

from renewables_permitting.extraction.canonicalization import (
    ScopeGuardDecision,
    _GENERATION_DESCRIPTOR_PATTERN,
    _action_types_from_title,
    _bounded_generation_list_contains_name,
    _canonical_documentary_text,
    _documentary_contains,
    _event_is_integrated,
    _evidence_is_supported,
    _find_literal_span,
    _infer_generation_type,
    _modification_expectation,
    _scope_guard_from_document,
)
from renewables_permitting.extraction.models import (
    BOEProjectExtraction,
    BOESourceDocument,
    DocumentScope,
    GenerationAssetMention,
    GenerationRelationType,
)


class DocumentExtractionValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        preview = "; ".join(issues[:10])
        if len(issues) > 10:
            preview += f"; ... ({len(issues) - 10} adicionales)"
        super().__init__(preview)


_HYBRID_PHOTOVOLTAIC_GENERATION_PATTERN = (
    r"\binfraestructura\s+h[ií]brida\s+fotovoltaica\b"
)
_GENERATION_TABLE_CONTEXT_RE = re.compile(
    r"\binstalaciones?\s+de\s+generaci[oó]n\b[^.]{0,240}"
    r"\b(?:objeto\s+de\s+proyecto|de\s+objeto)\s+y\s+"
    r"tramitaci[oó]n\s+independiente\b",
    re.IGNORECASE,
)
_GENERATION_TABLE_HEADER_RE = re.compile(
    r"^denominaci[oó]n$",
    re.IGNORECASE,
)
_POST_MODEL_NON_PROJECT_TITLE_PATTERNS = (
    re.compile(
        r"\bsistema\s+de\s+generaci[oó]n\s+fotovoltaic[oa]\b"
        r"[^.;]{0,180}\bsuministro\s+complementario\b"
        r"[^.;]{0,180}\b(?:idam|desaladora?|desalaci[oó]n)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\binstalaci[oó]n\s+de\s+generaci[oó]n\s+de\s+energ[ií]a\s+"
        r"el[eé]ctrica\s+denominada\s+sustituci[oó]n\s+de\s+tramo\s+de\s+"
        r"(?:lamt|lmt|l[ií]nea)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:segunda\s+)?convocatoria\b[^.;]{0,500}"
        r"\bprogramas?\b[^.;]{0,500}"
        r"\brepotenciaci[oó]n\s+de\s+instalaciones\s+e[oó]licas\b"
        r"[^.;]{0,300}\bminicentrales\s+hidroel[eé]ctricas\b",
        re.IGNORECASE,
    ),
)


def _supports_post_model_non_project_scope(document_title: str) -> bool:
    """Reconoce tres contextos auditados que no constituyen una planta raíz.

    Esta excepción actúa solo al validar un resultado no relevante ya producido
    por el modelo. No altera la elegibilidad histórica ni el guard pre-modelo.
    """

    title = _canonical_documentary_text(document_title)
    return any(
        pattern.search(title)
        for pattern in _POST_MODEL_NON_PROJECT_TITLE_PATTERNS
    )


def _generation_table_names(source_text: str) -> set[str]:
    """Extrae solo denominaciones de tablas con contexto local de generación."""

    lines = [
        _canonical_documentary_text(line).strip()
        for line in str(source_text).splitlines()
        if line.strip()
    ]
    names: set[str] = set()
    for index in range(len(lines) - 2):
        if not _GENERATION_TABLE_HEADER_RE.fullmatch(lines[index]):
            continue
        if "expediente" not in lines[index + 1].casefold():
            continue
        if lines[index + 2].casefold() != "promotor":
            continue
        local_context = " ".join(lines[max(0, index - 2):index])
        if not _GENERATION_TABLE_CONTEXT_RE.search(local_context):
            continue

        row_index = index + 3
        while row_index + 2 < len(lines):
            expediente = lines[row_index + 1]
            if not re.search(r"\d", expediente):
                break
            names.add(lines[row_index].casefold())
            row_index += 3
    return names


def _generation_name_has_documentary_context(
    *,
    asset: GenerationAssetMention,
    name: str,
    source_text: str,
    document_title: str,
) -> bool:
    """Comprueba que el nombre identifica una planta sin imponer una sintaxis única."""

    inferred_from_name = _infer_generation_type(name)
    if (
        inferred_from_name is not None
        and inferred_from_name == asset.generation_type
        and _documentary_contains(name, source_text)
    ):
        return True

    if _find_literal_span(
        source_text,
        anchors=[name],
        semantic_patterns=[_GENERATION_DESCRIPTOR_PATTERN],
        document_title=document_title,
    ) is not None:
        return True

    if _bounded_generation_list_contains_name(name, source_text):
        return True

    if _find_literal_span(
        source_text,
        anchors=[name],
        semantic_patterns=[_HYBRID_PHOTOVOLTAIC_GENERATION_PATTERN],
        document_title=document_title,
    ) is not None:
        return True

    name_key = _canonical_documentary_text(name).casefold()
    return name_key in _generation_table_names(source_text)


def validate_extraction_against_document(
    *,
    document: BOESourceDocument,
    extraction: BOEProjectExtraction,
) -> None:
    source = f"{document.title}\n{document.text}"
    issues: list[str] = []

    scope_decision, scope_reason = _scope_guard_from_document(
        document_title=document.title,
        source_text=source,
    )
    if (
        scope_decision == ScopeGuardDecision.FORCE_NOT_RELEVANT
        and extraction.document_scope == DocumentScope.GENERATION_PROJECT_SPECIFIC
    ):
        issues.append(
            "Falso positivo de alcance: "
            + (scope_reason or "el objeto principal no es una planta de generación.")
        )
    if (
        scope_decision == ScopeGuardDecision.REQUIRE_PROJECT_REVIEW
        and extraction.document_scope != DocumentScope.GENERATION_PROJECT_SPECIFIC
        and not _supports_post_model_non_project_scope(document.title)
    ):
        issues.append(
            "Posible falso negativo de alcance: "
            + (scope_reason or "el título identifica un proyecto de generación.")
        )

    if extraction.boe_id != document.boe_id:
        issues.append("boe_id no coincide con la fuente.")
    if extraction.publication_date != document.publication_date:
        issues.append("publication_date no coincide con la fuente.")

    for event_index, event in enumerate(extraction.publication_events, start=1):
        event_path = f"publication_events[{event_index}]"
        generation_refs = {
            asset.local_generation_asset_ref for asset in event.generation_assets
        }
        component_refs = {
            component.local_component_ref for component in event.associated_components
        }
        all_entities = generation_refs | component_refs

        if not event.generation_assets:
            issues.append(f"{event_path}: no contiene ninguna planta de generación.")

        for asset in event.generation_assets:
            path = f"{event_path}.{asset.local_generation_asset_ref}"
            if not asset.names_raw:
                issues.append(f"{path}: names_raw está vacío.")
            for name in asset.names_raw:
                if not _documentary_contains(name, source):
                    issues.append(f"{path}: nombre no documental {name!r}.")
            if not _evidence_is_supported(asset.evidence, source):
                issues.append(f"{path}.evidence no es literal.")
            elif not any(
                _generation_name_has_documentary_context(
                    asset=asset,
                    name=name,
                    source_text=source,
                    document_title=document.title,
                )
                for name in asset.names_raw
            ):
                issues.append(
                    f"{path}: la fuente no identifica la denominación como planta de generación."
                )
            for mention in asset.technical_mentions:
                if not _documentary_contains(mention.value_raw, source):
                    issues.append(f"{path}: magnitud no documental {mention.value_raw!r}.")
                if not _evidence_is_supported(mention.evidence, source):
                    issues.append(f"{path}: evidence técnica no literal.")

        for component in event.associated_components:
            path = f"{event_path}.{component.local_component_ref}"
            if not _evidence_is_supported(component.evidence, source):
                issues.append(f"{path}.evidence no es literal.")
            if component.description_raw and not _documentary_contains(
                component.description_raw, source
            ):
                issues.append(f"{path}.description_raw no es literal.")
            for name in component.names_raw:
                if not _documentary_contains(name, source):
                    issues.append(f"{path}: nombre no documental {name!r}.")
            if not component.related_generation_asset_refs:
                issues.append(f"{path}: no está vinculado a ninguna planta.")
            missing = set(component.related_generation_asset_refs) - generation_refs
            if missing:
                issues.append(f"{path}: referencias de planta inexistentes {sorted(missing)}.")
            for mention in component.technical_mentions:
                if not _documentary_contains(mention.value_raw, source):
                    issues.append(f"{path}: magnitud no documental {mention.value_raw!r}.")
                if not _evidence_is_supported(mention.evidence, source):
                    issues.append(f"{path}: evidence técnica no literal.")

        for action_index, action in enumerate(event.administrative_actions, start=1):
            path = f"{event_path}.administrative_actions[{action_index}]"
            if not _evidence_is_supported(action.evidence, source):
                issues.append(f"{path}.evidence no es literal.")
            if not action.targets:
                issues.append(f"{path}: targets está vacío.")
            if "event" in action.targets and len(action.targets) != 1:
                issues.append(f"{path}: event no puede combinarse con otros targets.")
            missing = set(action.targets) - {"event"} - all_entities
            if missing:
                issues.append(f"{path}: targets inexistentes {sorted(missing)}.")
            expectation = _modification_expectation(action, document_title=document.title)
            if expectation is not None and action.is_modification != expectation:
                issues.append(f"{path}: is_modification no coincide con el título.")

        for participant in event.participants:
            if not _documentary_contains(participant.participant_name_raw, source):
                issues.append(f"{event_path}: participante no documental.")
            if not _evidence_is_supported(participant.evidence, source):
                issues.append(f"{event_path}: evidence de participante no literal.")

        for location in event.administrative_locations:
            if not _documentary_contains(location.location_name_raw, source):
                issues.append(f"{event_path}: localización no documental.")
            if not _evidence_is_supported(location.evidence, source):
                issues.append(f"{event_path}: evidence de localización no literal.")

        for relation in event.generation_relations:
            path = f"{event_path}.generation_relations"
            if {
                relation.source_generation_asset_ref,
                relation.target_generation_asset_ref,
            } - generation_refs:
                issues.append(f"{path}: referencias inexistentes.")
            if not _evidence_is_supported(relation.evidence, source):
                issues.append(f"{path}: evidence no literal.")
            relation_key = _canonical_documentary_text(relation.evidence).casefold()
            supported = (
                relation.relation_type == GenerationRelationType.HYBRIDIZED_WITH
                and bool(re.search(r"h[ií]brid", relation_key))
            ) or (
                relation.relation_type == GenerationRelationType.REPLACES
                and bool(re.search(r"sustitu|reemplaz", relation_key))
            )
            if not supported:
                issues.append(f"{path}: semántica no respaldada.")

        if len(event.generation_assets) > 1 and not _event_is_integrated(event, source):
            issues.append(
                f"{event_path}: varias plantas independientes deben estar en eventos distintos."
            )

    title_types = _action_types_from_title(document.title)
    extracted_types = {
        action.action_type
        for event in extraction.publication_events
        for action in event.administrative_actions
    }
    missing_title_types = title_types - extracted_types
    if (
        extraction.document_scope == DocumentScope.GENERATION_PROJECT_SPECIFIC
        and missing_title_types
    ):
        issues.append(
            "Faltan actuaciones actuales explícitas del título: "
            f"{sorted(item.value for item in missing_title_types)}."
        )

    if issues:
        raise DocumentExtractionValidationError(issues)


def build_document_validation_retry_prompt(
    *,
    original_prompt: str,
    validation_error: DocumentExtractionValidationError,
) -> str:
    issues = "\n".join(f"- {issue}" for issue in validation_error.issues)
    return (
        f"{original_prompt}\n\n"
        "La salida anterior cumplió el esquema, pero no las invariantes documentales. "
        "Genera una salida completa nueva y corrige estas incidencias:\n"
        f"{issues}\n\n"
        "Recuerda: las únicas raíces son plantas de generación con nombres literales; "
        "almacenamiento y evacuación son componentes asociados. Usa target='event' "
        "cuando la actuación recae sobre todo el proyecto y targets concretos solo "
        "cuando afecta a un subconjunto inequívoco."
    )
