from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Sequence


_EVIDENCE_SEPARATOR = re.compile(r"\s*\[\.\.\.\]\s*")
_POWER_NUMBER_PATTERN = (
    r"(?:[0-9]{1,3}(?:[.\s][0-9]{3})*(?:,[0-9]+)?|"
    r"[0-9]+(?:\.[0-9]+)?)"
)
_POWER_RE = re.compile(
    rf"(?<!\d)({_POWER_NUMBER_PATTERN})\s*(gw|mw|kw|w)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_POWER_SEQUENCE_RE = re.compile(
    rf"(?<!\d){_POWER_NUMBER_PATTERN}\s*"
    rf"(?:[-–—/+x×]|a|hasta|y|,\s+|;\s*)\s*"
    rf"{_POWER_NUMBER_PATTERN}\s*(?:gw|mw|kw|w)\b",
    re.IGNORECASE,
)


def normalize_name(value: str) -> str:
    """Frozen identity normalization: accents/punctuation/order independent."""

    decomposed = unicodedata.normalize("NFKD", str(value)).casefold()
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    alphanumeric = "".join(
        char if char.isalnum() else " " for char in without_marks
    )
    return " ".join(alphanumeric.split())


def normalize_evidence(value: str) -> str:
    """Frozen literal normalization; punctuation remains documentary evidence."""

    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def evidence_fragments(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for fragment in _EVIDENCE_SEPARATOR.split(str(value))
        if (normalized := normalize_evidence(fragment))
    )


def evidence_is_correct(
    predicted_evidence: str,
    accepted_passages: Sequence[str],
) -> bool:
    """Every predicted fragment must lie inside an entity-specific truth passage."""

    fragments = evidence_fragments(predicted_evidence)
    accepted = tuple(normalize_evidence(value) for value in accepted_passages)
    return bool(fragments) and all(
        any(fragment in passage for passage in accepted)
        for fragment in fragments
    )


def evidence_candidate(
    predicted_evidence: str,
    accepted_passages: Sequence[str],
) -> bool:
    """At least one fragment anchors an entity candidate to its truth evidence."""

    fragments = evidence_fragments(predicted_evidence)
    accepted = tuple(normalize_evidence(value) for value in accepted_passages)
    return any(fragment in passage for fragment in fragments for passage in accepted)


def parse_power_mw(value: str) -> Decimal | None:
    """Parse one unambiguous W/kW/MW/GW literal into exact decimal MW."""

    raw_value = str(value)
    matches = list(_POWER_RE.finditer(raw_value))
    if len(matches) != 1 or _AMBIGUOUS_POWER_SEQUENCE_RE.search(raw_value):
        return None
    number_text = matches[0].group(1).replace(" ", "")
    if "," in number_text:
        number_text = number_text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})+", number_text):
        number_text = number_text.replace(".", "")
    try:
        number = Decimal(number_text)
    except InvalidOperation:
        return None
    factor = {
        "gw": Decimal("1000"),
        "mw": Decimal("1"),
        "kw": Decimal("0.001"),
        "w": Decimal("0.000001"),
    }[matches[0].group(2).casefold()]
    return number * factor


@dataclass(frozen=True)
class MatchResult:
    matches: tuple[tuple[str, str], ...]
    unmatched_truth: tuple[str, ...]
    unmatched_predicted: tuple[str, ...]
    ambiguous_truth: tuple[str, ...]
    ambiguous_predicted: tuple[str, ...]
    excluded_truth: tuple[str, ...]
    excluded_predicted: tuple[str, ...]


def _connected_components(
    truth_keys: set[str],
    predicted_keys: set[str],
    pairs: set[tuple[str, str]],
) -> list[tuple[set[str], set[str]]]:
    components: list[tuple[set[str], set[str]]] = []
    remaining_truth = set(truth_keys)
    remaining_predicted = set(predicted_keys)
    while remaining_truth or remaining_predicted:
        if remaining_truth:
            pending_truth = {min(remaining_truth)}
            pending_predicted: set[str] = set()
        else:
            pending_truth = set()
            pending_predicted = {min(remaining_predicted)}
        component_truth: set[str] = set()
        component_predicted: set[str] = set()
        while pending_truth or pending_predicted:
            while pending_truth:
                truth_key = pending_truth.pop()
                if truth_key in component_truth:
                    continue
                component_truth.add(truth_key)
                pending_predicted.update(
                    predicted
                    for truth, predicted in pairs
                    if truth == truth_key and predicted not in component_predicted
                )
            while pending_predicted:
                predicted_key = pending_predicted.pop()
                if predicted_key in component_predicted:
                    continue
                component_predicted.add(predicted_key)
                pending_truth.update(
                    truth
                    for truth, predicted in pairs
                    if predicted == predicted_key and truth not in component_truth
                )
        remaining_truth -= component_truth
        remaining_predicted -= component_predicted
        components.append((component_truth, component_predicted))
    return components


def _maximum_matching(
    truth_keys: set[str],
    predicted_keys: set[str],
    pairs: set[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Return one deterministic maximum-cardinality bipartite matching."""

    adjacency = {
        truth_key: sorted(
            predicted_key
            for candidate_truth, predicted_key in pairs
            if candidate_truth == truth_key and predicted_key in predicted_keys
        )
        for truth_key in truth_keys
    }
    predicted_to_truth: dict[str, str] = {}

    def augment(truth_key: str, visited: set[str]) -> bool:
        for predicted_key in adjacency[truth_key]:
            if predicted_key in visited:
                continue
            visited.add(predicted_key)
            incumbent = predicted_to_truth.get(predicted_key)
            if incumbent is None or augment(incumbent, visited):
                predicted_to_truth[predicted_key] = truth_key
                return True
        return False

    for truth_key in sorted(truth_keys):
        augment(truth_key, set())
    return {
        (truth_key, predicted_key)
        for predicted_key, truth_key in predicted_to_truth.items()
    }


def deterministic_match(
    *,
    truth_keys: Iterable[str],
    predicted_keys: Iterable[str],
    candidate_pairs: Iterable[tuple[str, str]],
    excluded_truth_keys: Iterable[str] = (),
) -> MatchResult:
    """Resolve only forced 1:1 pairs; never break an equally valid tie.

    Edges present in every maximum-cardinality matching are removed
    iteratively. A remaining component containing scored truth is a matching
    ambiguity and is penalized as unresolved. A component containing only
    explicitly excluded/ambiguous truth shields its related predictions from
    precision denominators.
    """

    truth = set(truth_keys)
    predicted = set(predicted_keys)
    excluded = set(excluded_truth_keys)
    if not excluded.issubset(truth):
        raise ValueError("Excluded truth keys must belong to the truth universe.")
    pairs = {
        (truth_key, predicted_key)
        for truth_key, predicted_key in candidate_pairs
        if truth_key in truth and predicted_key in predicted
    }
    remaining_truth = set(truth)
    remaining_predicted = set(predicted)
    matches: list[tuple[str, str]] = []

    while True:
        remaining_pairs = {
            (truth_key, predicted_key)
            for truth_key, predicted_key in pairs
            if truth_key in remaining_truth and predicted_key in remaining_predicted
        }
        maximum = _maximum_matching(
            remaining_truth,
            remaining_predicted,
            remaining_pairs,
        )
        maximum_size = len(maximum)
        forced = sorted(
            edge
            for edge in maximum
            if len(
                _maximum_matching(
                    remaining_truth,
                    remaining_predicted,
                    remaining_pairs - {edge},
                )
            )
            < maximum_size
        )
        if not forced:
            break
        for truth_key, predicted_key in forced:
            matches.append((truth_key, predicted_key))
            remaining_truth.remove(truth_key)
            remaining_predicted.remove(predicted_key)

    remaining_pairs = {
        (truth_key, predicted_key)
        for truth_key, predicted_key in pairs
        if truth_key in remaining_truth and predicted_key in remaining_predicted
    }
    ambiguous_truth: set[str] = set()
    ambiguous_predicted: set[str] = set()
    excluded_predicted: set[str] = set()
    candidate_truth = {truth_key for truth_key, _ in remaining_pairs}
    candidate_predicted = {predicted_key for _, predicted_key in remaining_pairs}
    for component_truth, component_predicted in _connected_components(
        candidate_truth,
        candidate_predicted,
        remaining_pairs,
    ):
        if component_truth and component_truth.issubset(excluded):
            excluded_predicted.update(component_predicted)
        else:
            ambiguous_truth.update(component_truth - excluded)
            ambiguous_predicted.update(component_predicted)

    matched_truth = {truth_key for truth_key, _ in matches}
    matched_predicted = {predicted_key for _, predicted_key in matches}
    unmatched_truth = remaining_truth - excluded - ambiguous_truth
    unmatched_predicted = (
        remaining_predicted
        - excluded_predicted
        - ambiguous_predicted
    )
    return MatchResult(
        matches=tuple(sorted(matches)),
        unmatched_truth=tuple(sorted(unmatched_truth)),
        unmatched_predicted=tuple(sorted(unmatched_predicted)),
        ambiguous_truth=tuple(sorted(ambiguous_truth)),
        ambiguous_predicted=tuple(sorted(ambiguous_predicted)),
        excluded_truth=tuple(sorted(excluded)),
        excluded_predicted=tuple(sorted(excluded_predicted)),
    )


def name_candidate_pairs(
    truth_names: Mapping[str, Sequence[str]],
    predicted_names: Mapping[str, Sequence[str]],
) -> set[tuple[str, str]]:
    truth_normalized = {
        key: {normalize_name(value) for value in values if normalize_name(value)}
        for key, values in truth_names.items()
    }
    predicted_normalized = {
        key: {normalize_name(value) for value in values if normalize_name(value)}
        for key, values in predicted_names.items()
    }
    return {
        (truth_key, predicted_key)
        for truth_key, expected in truth_normalized.items()
        for predicted_key, actual in predicted_normalized.items()
        if expected & actual
    }


def metric_from_counts(tp: int, fp: int, fn: int) -> dict[str, int | float | None]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else 0.0
        if precision is not None and recall is not None
        else None
    )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
