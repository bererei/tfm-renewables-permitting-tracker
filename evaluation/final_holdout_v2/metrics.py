"""Corpus micro counts and explicit undefined-denominator conventions for V2-B."""
from __future__ import annotations

from typing import Any

from evaluation.final_holdout_v1.matching import metric_from_counts


def ratio(numerator: int, denominator: int, *, name: str) -> dict[str, Any]:
    if not 0 <= numerator <= denominator:
        raise ValueError("Ratio requires 0 <= numerator <= denominator.")
    return {
        "numerator": numerator,
        "denominator": denominator,
        name: numerator / denominator if denominator else None,
        "undefined_reason": None if denominator else "zero_denominator",
    }


def detection(tp: int, fp: int, fn: int) -> dict[str, Any]:
    if any(type(value) is not int or value < 0 for value in (tp, fp, fn)):
        raise ValueError("Detection counts must be non-negative integers.")
    values = metric_from_counts(tp, fp, fn)
    precision, recall = values["precision"], values["recall"]
    return {
        **values,
        "precision_denominator": tp + fp,
        "recall_denominator": tp + fn,
        "f1_denominator": (
            precision + recall if precision is not None and recall is not None else None
        ),
        "undefined_reasons": {
            "precision": None if tp + fp else "zero_denominator",
            "recall": None if tp + fn else "zero_denominator",
            "f1": "undefined_precision_or_recall" if values["f1"] is None else None,
        },
        "aggregation": "micro",
    }


def accuracy(correct: int, denominator: int, *, excluded: int = 0) -> dict[str, Any]:
    return {
        **ratio(correct, denominator, name="accuracy"),
        "correct": correct,
        "excluded": excluded,
        "aggregation": "micro_over_applicable_matched_pairs",
    }
