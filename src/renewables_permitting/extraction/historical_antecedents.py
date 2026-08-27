from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

from renewables_permitting.extraction.canonicalization import (
    _action_types_from_title,
)
from renewables_permitting.extraction.corrections import (
    LoadedAdministrativeActionCorrections,
    corrections_identity,
    evidence_sha256,
    validate_administrative_action_corrections,
)
from renewables_permitting.extraction.historical_antecedent_reviews import (
    HISTORICAL_ANTECEDENT_REASON_CODE,
    LoadedHistoricalAntecedentReviews,
    historical_antecedent_review_id,
    historical_antecedent_reviews_identity,
    validate_historical_antecedent_reviews,
)
from renewables_permitting.extraction.models import (
    BOEProjectExtraction,
    BOESourceDocument,
)


HISTORICAL_ANTECEDENT_POLICY_VERSION = "1"
POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE = (
    HISTORICAL_ANTECEDENT_REASON_CODE
)

_MAX_COMPOSITE_GAP = 6_000
_MAX_LOCATION_CANDIDATES = 128
_SOURCE_EXCERPT_CONTEXT = 180
_TEMPORAL_CONTEXT = 260

_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_SPANISH_DATE_RE = re.compile(
    r"\b([0-3]?\d)\s+de\s+("
    + "|".join(_MONTHS)
    + r")\s+de\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_NUMERIC_DATE_RE = re.compile(
    r"\b([0-3]?\d)[/-]([01]?\d)[/-]((?:19|20)\d{2})\b"
)
_RETROSPECTIVE_RE = re.compile(
    r"\b(?:"
    r"habiendo\s+sido|hab[ií]a\s+sido|"
    r"fue(?:ron)?\s+(?:sometid[ao]s?|formulad[ao]s?|notificad[ao]s?|"
    r"publicad[ao]s?|emitid[ao]s?|otorgad[ao]s?|declarad[ao]s?|dictad[ao]s?)|"
    r"se\s+(?:formul[oó]|notific[oó]|public[oó]|someti[oó]|emiti[oó]|dict[oó])|"
    r"solicit[oó]|subsanad[ao]s?"
    r")\b",
    re.IGNORECASE,
)
_EARLIER_RESOLUTION_RE = re.compile(
    r"\b(?:por|mediante|concretad[ao]\s+mediante)\s+(?:la\s+)?"
    r"resoluci[oó]n\s+de\s+"
    r"([0-3]?\d\s+de\s+(?:"
    + "|".join(_MONTHS)
    + r")\s+de\s+(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_EARLIER_PUBLICATION_RE = re.compile(
    r"\bpublicaci[oó]n\s+(?:de\s+fecha\s+|el\s+)?"
    r"([0-3]?\d\s+de\s+(?:"
    + "|".join(_MONTHS)
    + r")\s+de\s+(?:19|20)\d{2})\b"
    r"[^.]{0,180}\bbolet[ií]n\s+oficial\b",
    re.IGNORECASE,
)
_ANTECEDENT_HEADING_RE = re.compile(
    r"\bantecedentes?(?:\s+de)?\s+hecho\b",
    re.IGNORECASE,
)
_FUNDAMENTOS_HEADING_RE = re.compile(
    r"\bfundamentos?\s+de\s+derecho\b",
    re.IGNORECASE,
)
_OPERATIVE_RE = re.compile(
    r"\b(?:resuelve|resuelvo|acuerda)\b"
    r"(?=\s*(?::|\.|la\b|el\b|formular\b|otorgar\b|conceder\b|"
    r"declarar\b|autorizar\b|aprobar\b|someter\b|primero\b|[0-9]+\.))",
    re.IGNORECASE,
)

_CHAR_REPLACEMENTS = {
    "\u00a0": " ",
    "«": '"',
    "»": '"',
    "“": '"',
    "”": '"',
    "’": "'",
    "–": "-",
    "—": "-",
}


@dataclass(frozen=True)
class EvidenceOccurrence:
    """One auditable source span supporting a detector finding."""

    start: int
    end: int
    section: str
    source_excerpt: str
    temporal_signals: tuple[str, ...]
    contextual_signals: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialize the occurrence with stable field and signal ordering."""

        return {
            "start": self.start,
            "end": self.end,
            "section": self.section,
            "source_excerpt": self.source_excerpt,
            "temporal_signals": list(self.temporal_signals),
            "contextual_signals": list(self.contextual_signals),
        }


@dataclass(frozen=True)
class HistoricalAntecedentFinding:
    """Non-destructive warning for one extracted administrative action."""

    administrative_action_id: str
    boe_id: str
    source_document_sha256: str
    action_type: str
    decision: str
    evidence: str
    evidence_sha256: str
    reason_code: str
    detector_policy_version: str
    temporal_signals: tuple[str, ...]
    contextual_signals: tuple[str, ...]
    occurrences: tuple[EvidenceOccurrence, ...]

    def as_dict(self) -> dict[str, Any]:
        """Build the deterministic diagnostic stored in the review queue."""

        return {
            "administrative_action_id": self.administrative_action_id,
            "boe_id": self.boe_id,
            "source_document_sha256": self.source_document_sha256,
            "action_type": self.action_type,
            "decision": self.decision,
            "evidence": self.evidence,
            "evidence_sha256": self.evidence_sha256,
            "reason_code": self.reason_code,
            "detector_policy_version": self.detector_policy_version,
            "temporal_signals": list(self.temporal_signals),
            "contextual_signals": list(self.contextual_signals),
            "occurrences": [item.as_dict() for item in self.occurrences],
        }


@dataclass(frozen=True)
class ResolvedHistoricalAntecedentFinding:
    """Finding matched exactly to one approved human resolution."""

    finding: HistoricalAntecedentFinding
    resolution_kind: str
    correction_id: str | None
    correction_version: int | None
    review_decision_id: str | None
    review_version: int | None
    decision_source: str
    reviewed_on: str
    reviewer: str


@dataclass(frozen=True)
class HistoricalAntecedentReconciliation:
    """Pending and already-resolved findings without changing extraction data."""

    pending: tuple[HistoricalAntecedentFinding, ...]
    resolved: tuple[ResolvedHistoricalAntecedentFinding, ...]


@dataclass(frozen=True)
class _NormalizedSource:
    text: str
    original_offsets: tuple[int, ...]


@dataclass(frozen=True)
class _LocatedSpan:
    normalized_start: int
    normalized_end: int
    original_start: int
    original_end: int


def _normalize_character(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(_CHAR_REPLACEMENTS.get(char, char) for char in normalized)


def _normalize_source(value: str) -> _NormalizedSource:
    characters: list[str] = []
    offsets: list[int] = []
    previous_was_space = True
    for original_offset, original_character in enumerate(str(value)):
        for character in _normalize_character(original_character).casefold():
            if character.isspace():
                if not previous_was_space:
                    characters.append(" ")
                    offsets.append(original_offset)
                previous_was_space = True
                continue
            characters.append(character)
            offsets.append(original_offset)
            previous_was_space = False
    if characters and characters[-1] == " ":
        characters.pop()
        offsets.pop()
    return _NormalizedSource("".join(characters), tuple(offsets))


def _normalize_fragment(value: str) -> str:
    return _normalize_source(value).text.strip()


def _evidence_segments(evidence: str) -> tuple[str, ...]:
    return tuple(
        segment.strip()
        for segment in re.split(r"\s*\[\.\.\.\]\s*", str(evidence))
        if segment.strip()
    )


def _all_positions(haystack: str, needle: str) -> tuple[tuple[int, int], ...]:
    if not needle:
        return ()
    positions: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = haystack.find(needle, cursor)
        if start < 0:
            break
        positions.append((start, start + len(needle)))
        if len(positions) > _MAX_LOCATION_CANDIDATES:
            return ()
        cursor = start + 1
    return tuple(positions)


def _ordered_composite_spans(
    positions_by_segment: tuple[tuple[tuple[int, int], ...], ...],
) -> tuple[tuple[int, int], ...]:
    chains: list[tuple[int, int]] = []

    def extend(segment_index: int, first: int, previous_end: int) -> bool:
        if len(chains) > _MAX_LOCATION_CANDIDATES:
            return False
        if segment_index == len(positions_by_segment):
            chains.append((first, previous_end))
            return True
        for start, end in positions_by_segment[segment_index]:
            if start < previous_end or start - previous_end > _MAX_COMPOSITE_GAP:
                continue
            if not extend(segment_index + 1, first, end):
                return False
        return True

    for start, end in positions_by_segment[0]:
        if not extend(1, start, end):
            return ()
    if not chains or len(chains) > _MAX_LOCATION_CANDIDATES:
        return ()
    return tuple(sorted(set(chains)))


def _locate_evidence(
    evidence: str,
    source: _NormalizedSource,
) -> tuple[_LocatedSpan, ...]:
    segments = tuple(
        _normalize_fragment(segment) for segment in _evidence_segments(evidence)
    )
    if not segments or any(not segment for segment in segments):
        return ()
    positions_by_segment = tuple(
        _all_positions(source.text, segment) for segment in segments
    )
    if any(not positions for positions in positions_by_segment):
        return ()
    normalized_spans = (
        positions_by_segment[0]
        if len(segments) == 1
        else _ordered_composite_spans(positions_by_segment)
    )
    located: list[_LocatedSpan] = []
    for start, end in normalized_spans:
        if start >= len(source.original_offsets) or end <= start:
            continue
        located.append(_LocatedSpan(
            normalized_start=start,
            normalized_end=end,
            original_start=source.original_offsets[start],
            original_end=source.original_offsets[end - 1] + 1,
        ))
    return tuple(located)


def _parsed_dates(value: str) -> tuple[date, ...]:
    parsed: set[date] = set()
    for match in _SPANISH_DATE_RE.finditer(value):
        try:
            parsed.add(date(
                int(match.group(3)),
                _MONTHS[match.group(2).casefold()],
                int(match.group(1)),
            ))
        except ValueError:
            continue
    for match in _NUMERIC_DATE_RE.finditer(value):
        try:
            parsed.add(date(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
            ))
        except ValueError:
            continue
    return tuple(sorted(parsed))


def _contains_earlier_date(value: str, publication_date: date) -> bool:
    return any(item < publication_date for item in _parsed_dates(value))


def _marker_starts(pattern: re.Pattern[str], text: str) -> tuple[int, ...]:
    return tuple(match.start() for match in pattern.finditer(text))


def _first_after(positions: tuple[int, ...], start: int) -> int | None:
    return next((position for position in positions if position > start), None)


def _section_for_position(
    position: int,
    *,
    antecedent_starts: tuple[int, ...],
    fundamentos_starts: tuple[int, ...],
    operative_starts: tuple[int, ...],
) -> str:
    previous_antecedent = max(
        (item for item in antecedent_starts if item <= position),
        default=None,
    )
    if previous_antecedent is not None:
        boundary_candidates = [
            item
            for item in (*fundamentos_starts, *operative_starts)
            if item > previous_antecedent
        ]
        if position < min(boundary_candidates, default=float("inf")):
            return "antecedentes_de_hecho"
    previous_fundamentos = max(
        (item for item in fundamentos_starts if item <= position),
        default=None,
    )
    if previous_fundamentos is not None:
        next_operative = _first_after(operative_starts, previous_fundamentos)
        if next_operative is None or position < next_operative:
            return "fundamentos_de_derecho"
    if operative_starts and position >= operative_starts[0]:
        return "operative"
    if operative_starts and position < operative_starts[0]:
        return "pre_operative"
    return "body"


def _temporal_signals(
    *,
    source_text: str,
    span: _LocatedSpan,
    section: str,
    publication_date: date,
) -> tuple[str, ...]:
    start = max(0, span.normalized_start - _TEMPORAL_CONTEXT)
    end = min(len(source_text), span.normalized_end + _TEMPORAL_CONTEXT)
    context = source_text[start:end]
    signals: list[str] = []
    if section == "antecedentes_de_hecho":
        signals.append("evidence_in_antecedentes")
    earlier_dates = _contains_earlier_date(context, publication_date)
    if earlier_dates and _RETROSPECTIVE_RE.search(context):
        signals.append("earlier_date_linked_to_retrospective_wording")
    for pattern, signal in (
        (_EARLIER_RESOLUTION_RE, "explicit_earlier_resolution"),
        (_EARLIER_PUBLICATION_RE, "explicit_earlier_boe_publication"),
    ):
        for match in pattern.finditer(context):
            if _contains_earlier_date(match.group(0), publication_date):
                signals.append(signal)
                break
    return tuple(dict.fromkeys(signals))


def _contextual_signals(
    *,
    span: _LocatedSpan,
    section: str,
    action_type: Any,
    title_action_types: set[Any],
    fundamentos_starts: tuple[int, ...],
    operative_starts: tuple[int, ...],
) -> tuple[str, ...]:
    signals: list[str] = []
    first_operative = operative_starts[0] if operative_starts else None
    if first_operative is not None and span.normalized_end <= first_operative:
        signals.append("evidence_before_operative_block")
    if section == "antecedentes_de_hecho" and (
        _first_after(fundamentos_starts, span.normalized_start) is not None
        or _first_after(operative_starts, span.normalized_start) is not None
    ):
        signals.append("documentary_section_separation")
    if (
        first_operative is None
        and title_action_types
        and action_type not in title_action_types
    ):
        signals.append("title_declares_different_current_act")
    return tuple(dict.fromkeys(signals))


def detect_possible_historical_antecedents(
    *,
    document: BOESourceDocument,
    extraction: BOEProjectExtraction,
) -> tuple[HistoricalAntecedentFinding, ...]:
    """Return deterministic warnings without mutating or filtering actions.

    Every finding requires both a strong temporal/structural signal and an
    independent contextual signal. Evidence that cannot be located as one
    literal span or as an ordered composite span is left unresolved and is not
    flagged. Any occurrence in the operative block suppresses the automatic
    warning so repeated wording is handled conservatively.
    """

    if document.boe_id != extraction.boe_id:
        raise ValueError("document.boe_id no coincide con extraction.boe_id.")
    if document.publication_date != extraction.publication_date:
        raise ValueError(
            "document.publication_date no coincide con la extracción."
        )

    source = _normalize_source(document.text)
    title_key = _normalize_fragment(document.title)
    antecedent_starts = _marker_starts(_ANTECEDENT_HEADING_RE, source.text)
    fundamentos_starts = _marker_starts(_FUNDAMENTOS_HEADING_RE, source.text)
    operative_starts = _marker_starts(_OPERATIVE_RE, source.text)
    title_action_types = _action_types_from_title(document.title)
    findings: list[HistoricalAntecedentFinding] = []

    for event_index, event in enumerate(extraction.publication_events, start=1):
        for action_index, action in enumerate(
            event.administrative_actions, start=1
        ):
            if _normalize_fragment(action.evidence) == title_key:
                continue
            located = _locate_evidence(action.evidence, source)
            if not located:
                continue
            occurrences: list[EvidenceOccurrence] = []
            reject_as_ambiguous = False
            for span in located:
                section = _section_for_position(
                    span.normalized_start,
                    antecedent_starts=antecedent_starts,
                    fundamentos_starts=fundamentos_starts,
                    operative_starts=operative_starts,
                )
                if section == "operative":
                    reject_as_ambiguous = True
                    break
                temporal = _temporal_signals(
                    source_text=source.text,
                    span=span,
                    section=section,
                    publication_date=document.publication_date,
                )
                contextual = _contextual_signals(
                    span=span,
                    section=section,
                    action_type=action.action_type,
                    title_action_types=title_action_types,
                    fundamentos_starts=fundamentos_starts,
                    operative_starts=operative_starts,
                )
                if not temporal or not contextual:
                    reject_as_ambiguous = True
                    break
                excerpt_start = max(
                    0, span.original_start - _SOURCE_EXCERPT_CONTEXT
                )
                excerpt_end = min(
                    len(document.text),
                    span.original_end + _SOURCE_EXCERPT_CONTEXT,
                )
                occurrences.append(EvidenceOccurrence(
                    start=span.original_start,
                    end=span.original_end,
                    section=section,
                    source_excerpt=document.text[excerpt_start:excerpt_end],
                    temporal_signals=temporal,
                    contextual_signals=contextual,
                ))
            if reject_as_ambiguous or not occurrences:
                continue
            temporal_signals = tuple(sorted({
                signal
                for occurrence in occurrences
                for signal in occurrence.temporal_signals
            }))
            contextual_signals = tuple(sorted({
                signal
                for occurrence in occurrences
                for signal in occurrence.contextual_signals
            }))
            findings.append(HistoricalAntecedentFinding(
                administrative_action_id=(
                    f"{extraction.boe_id}_event_{event_index}"
                    f"_action_{action_index}"
                ),
                boe_id=extraction.boe_id,
                source_document_sha256=document.source_document_sha256,
                action_type=action.action_type.value,
                decision=action.decision.value,
                evidence=action.evidence,
                evidence_sha256=evidence_sha256(action.evidence),
                reason_code=POSSIBLE_HISTORICAL_ANTECEDENT_REASON_CODE,
                detector_policy_version=HISTORICAL_ANTECEDENT_POLICY_VERSION,
                temporal_signals=temporal_signals,
                contextual_signals=contextual_signals,
                occurrences=tuple(occurrences),
            ))
    return tuple(sorted(
        findings,
        key=lambda item: item.administrative_action_id,
    ))


def reconcile_historical_antecedent_findings(
    findings: tuple[HistoricalAntecedentFinding, ...],
    corrections: LoadedAdministrativeActionCorrections | None,
    current_reviews: LoadedHistoricalAntecedentReviews | None = None,
) -> HistoricalAntecedentReconciliation:
    """Resolve exact ANTECEDENT corrections or exact CURRENT validations."""

    ordered = tuple(sorted(
        findings,
        key=lambda item: item.administrative_action_id,
    ))
    if corrections is not None and not isinstance(
        corrections, LoadedAdministrativeActionCorrections
    ):
        raise TypeError(
            "corrections debe proceder de "
            "load_administrative_action_corrections."
        )
    if current_reviews is not None and not isinstance(
        current_reviews, LoadedHistoricalAntecedentReviews
    ):
        raise TypeError(
            "current_reviews debe proceder de "
            "load_historical_antecedent_reviews."
        )

    correction_index: dict[tuple[str, ...], Any] = {}
    if corrections is not None:
        registry = validate_administrative_action_corrections(
            corrections.corrections
        )
        if corrections.semantic_identity != corrections_identity(registry):
            raise ValueError(
                "La identidad semántica del registro de correcciones no "
                "coincide."
            )
        correction_index = {
            (
                str(row.boe_id),
                str(row.administrative_action_id),
                str(row.expected_action_type),
                str(row.expected_decision),
                str(row.expected_evidence_sha256),
            ): row
            for row in registry.itertuples(index=False)
        }

    current_index: dict[tuple[str, ...], Any] = {}
    if current_reviews is not None:
        review_registry = validate_historical_antecedent_reviews(
            current_reviews.reviews
        )
        if current_reviews.semantic_identity != (
            historical_antecedent_reviews_identity(review_registry)
        ):
            raise ValueError(
                "La identidad semántica del registro de revisiones CURRENT "
                "no coincide."
            )
        current_index = {
            (
                str(row.boe_id),
                str(row.administrative_action_id),
                str(row.source_document_sha256),
                str(row.expected_action_type),
                str(row.expected_decision),
                str(row.expected_evidence_sha256),
                str(row.reason_code),
                str(row.detector_policy_version),
            ): row
            for row in review_registry.itertuples(index=False)
        }

    pending: list[HistoricalAntecedentFinding] = []
    resolved: list[ResolvedHistoricalAntecedentFinding] = []
    for finding in ordered:
        correction = correction_index.get((
            finding.boe_id,
            finding.administrative_action_id,
            finding.action_type,
            finding.decision,
            finding.evidence_sha256,
        ))
        current_review = current_index.get((
            finding.boe_id,
            finding.administrative_action_id,
            finding.source_document_sha256,
            finding.action_type,
            finding.decision,
            finding.evidence_sha256,
            finding.reason_code,
            finding.detector_policy_version,
        ))
        if correction is not None and current_review is not None:
            raise ValueError(
                "El finding tiene decisiones humanas contradictorias: "
                "ANTECEDENT y CURRENT."
            )
        if correction is None and current_review is None:
            pending.append(finding)
            continue
        if correction is not None:
            resolved.append(ResolvedHistoricalAntecedentFinding(
                finding=finding,
                resolution_kind="correction",
                correction_id=str(correction.correction_id),
                correction_version=int(correction.correction_version),
                review_decision_id=None,
                review_version=None,
                decision_source=str(correction.decision_source),
                reviewed_on=str(correction.reviewed_on),
                reviewer=str(correction.reviewer),
            ))
            continue
        review_record = current_review._asdict()
        resolved.append(ResolvedHistoricalAntecedentFinding(
            finding=finding,
            resolution_kind="current_validation",
            correction_id=None,
            correction_version=None,
            review_decision_id=historical_antecedent_review_id(
                review_record
            ),
            review_version=int(current_review.review_version),
            decision_source=str(current_review.decision_source),
            reviewed_on=str(current_review.reviewed_on),
            reviewer=str(current_review.reviewer),
        ))
    return HistoricalAntecedentReconciliation(
        pending=tuple(pending),
        resolved=tuple(resolved),
    )
