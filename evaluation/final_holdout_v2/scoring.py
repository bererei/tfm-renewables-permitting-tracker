"""Predeclared V2-B matching and scoring. Pure computation, no model or data writes."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from typing import Any, Mapping

import pandas as pd

from evaluation.final_holdout_v1.evaluator import _global, _scored, _truth_passages, _truth_row_maps
from evaluation.final_holdout_v1.matching import (
    MatchResult, deterministic_match, evidence_candidate, evidence_is_correct,
    name_candidate_pairs,
)
from evaluation.final_holdout_v2.contract import NA, TruthArtifact, parse_json_list
from evaluation.final_holdout_v2.metrics import accuracy, detection, ratio
from evaluation.final_holdout_v2.predictions import PredictionSnapshot, flatten_predictions, p0_warnings


ENTITY_TABLES = {
    "generation_assets": "generation_asset", "events": "event",
    "administrative_actions": "administrative_action", "locations": "location",
}
FIELD_SPECS = {
    "generation_assets": [("expected_generation_type", "generation_type")],
    "administrative_actions": [("expected_action_type", "action_type"),
                               ("expected_decision", "decision"),
                               ("expected_is_modification", "is_modification")],
    "locations": [("expected_location_level", "location_level")],
}
FRAME_COLUMNS = {
    "document_results": ["identificador_boe", "extraction_status", "expected_document_scope", "predicted_document_scope", "correct", "entity_tp", "entity_fp", "entity_fn"],
    "entity_results": ["identificador_boe", "entity_type", "truth_key", "predicted_key", "outcome", "reason", "temporal_truth"],
    "candidate_pairs": ["identificador_boe", "entity_type", "truth_key", "predicted_key"],
    "field_results": ["identificador_boe", "entity_type", "truth_key", "predicted_key", "field_name", "expected_value_json", "predicted_value_json", "applicable", "correct"],
    "affected_asset_sets": ["identificador_boe", "truth_action_key", "predicted_action_key", "expected_assets_json", "predicted_assets_json", "unresolved_targets_json", "applicable", "correct", "reason"],
    "action_asset_pairs": ["identificador_boe", "truth_action_key", "predicted_action_key", "asset_key", "outcome"],
    "evidence_results": ["identificador_boe", "truth_action_key", "predicted_action_key", "predicted_evidence", "accepted_passages_json", "evidence_supported"],
    "p0_results": ["identificador_boe", "truth_action_key", "predicted_action_key", "temporal_truth", "p0_warning", "p0_outcome", "reason", "warning_source_json"],
    "error_inventory": ["identificador_boe", "category", "entity_type", "truth_key", "predicted_key", "detail"],
}
BOOL_COLUMNS = {"correct", "applicable", "evidence_supported", "p0_warning"}
INT_COLUMNS = {"entity_tp", "entity_fp", "entity_fn"}


def typed_frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    for column in columns:
        frame[column] = frame[column].astype(
            "boolean" if column in BOOL_COLUMNS else "Int64" if column in INT_COLUMNS else "string")
    return frame.sort_values(columns, kind="stable", na_position="last").reset_index(drop=True)


def event_candidates(truth_assets: Mapping[str, set[str]], predicted_assets: Mapping[str, set[str]],
                     asset_matches: Mapping[str, str]) -> set[tuple[str, str]]:
    """Both complete, nonempty sets; no predicted or truth asset may disappear."""
    matched_truth = set(asset_matches.values())
    return {
        (truth_event, pred_event)
        for truth_event, expected in truth_assets.items()
        for pred_event, actual in predicted_assets.items()
        if expected and actual and expected <= matched_truth and actual <= asset_matches.keys()
        and expected == {asset_matches[key] for key in actual}
    }


def effective_assets(action: Mapping[str, Any], predicted: Mapping[str, dict],
                     asset_matches: Mapping[str, str]) -> tuple[set[str], list[str]]:
    """Project frozen targets as Gold does, retaining unmatched asset identities.

    Known components without explicit links produce no assets in Gold. Retain
    an unresolved-target diagnostic instead of inventing a parent or pair.
    """
    event = str(action["event_global"])
    assets = {key for key, row in predicted["generation_assets"].items() if row["event_global"] == event}
    resolved: set[str] = set()
    unresolved: set[str] = set()
    for target in action["targets"]:
        key = f"{event}:{target}"
        if target == "event":
            resolved.update(assets)
            if not assets:
                unresolved.add("event_without_generation_assets")
        elif key in assets:
            resolved.add(key)
        elif key in predicted["associated_components"]:
            links = predicted["associated_components"][key]["related_generation_asset_refs"]
            if not links:
                unresolved.add(f"{key}:no_explicit_generation_links")
            for ref in links:
                parent = f"{event}:{ref}"
                if parent in assets:
                    resolved.add(parent)
                else:
                    unresolved.add(f"{key}:unknown_parent:{ref}")
        else:
            unresolved.add(f"unknown_target:{key}")
    if not action["targets"]:
        unresolved.add("no_targets")
    return {
        f"truth:{asset_matches[key]}" if key in asset_matches else f"prediction:{key}"
        for key in resolved
    }, sorted(unresolved)


def evaluate_frames(truth: TruthArtifact, snapshot: PredictionSnapshot) -> tuple[dict, dict[str, pd.DataFrame]]:
    """Internal pure scoring entry point; public evaluate requires both freezes."""
    truth_maps = _truth_row_maps(truth)
    passages = _truth_passages(truth, scored_only=True)
    # Unscored owners may shield predictions, but their passages never anchor a
    # scored action. Scored action candidates use accepted scored passages only.
    all_passages = _truth_passages(truth, scored_only=False)
    predicted, scopes = flatten_predictions(snapshot)
    warnings, unresolved_warnings = p0_warnings(snapshot)
    rows: dict[str, list[dict]] = {name: [] for name in FRAME_COLUMNS}
    rows["p0_results"].extend(unresolved_warnings)
    matches: dict[str, dict[str, str]] = {table: {} for table in ENTITY_TABLES}
    excluded_pred: dict[str, set[str]] = {table: set() for table in ENTITY_TABLES}
    outcomes: dict[str, Counter] = {table: Counter() for table in ENTITY_TABLES}
    exclusions: dict[str, Counter] = {table: Counter() for table in ENTITY_TABLES}
    action_pair_outcomes: dict[str, str] = {}

    def error(boe, category, entity, truth_key=None, pred_key=None, detail=None):
        rows["error_inventory"].append({"identificador_boe": boe, "category": category,
                                       "entity_type": entity, "truth_key": truth_key,
                                       "predicted_key": pred_key, "detail": detail})

    def record(table: str, boe: str, result: MatchResult):
        truths = truth_maps[table]
        excluded = set(result.excluded_truth)
        matches[table].update({p: t for t, p in result.matches})
        excluded_pred[table].update(result.excluded_predicted)
        excluded_pred[table].update(p for t, p in result.matches if t in excluded)
        pairs = list(result.matches)
        pairs.extend((t, None) for t in sorted(set(truths) & {
            *result.unmatched_truth, *result.ambiguous_truth,
            *(set(result.excluded_truth) - {t for t, _ in result.matches}),
        }))
        pairs.extend((None, p) for p in sorted({*result.unmatched_predicted,
                     *result.ambiguous_predicted, *result.excluded_predicted}))
        for t, p in pairs:
            temporal = str(truths[t]["temporal_status"]) if t and table == "administrative_actions" else None
            ambiguous = t in result.ambiguous_truth or p in result.ambiguous_predicted
            if t in excluded or p in excluded_pred[table]:
                outcome, reason = "excluded", "truth_excluded_or_temporally_ambiguous"
            elif t and p:
                outcome = "historical_fp" if temporal == "historical_antecedent" else "tp"
                reason = "historical_contamination" if outcome == "historical_fp" else "forced_match"
            elif t:
                outcome = "historical_not_extracted" if temporal == "historical_antecedent" else "fn"
                reason = "ambiguous_matching" if ambiguous else "no_candidate"
            else:
                outcome, reason = "fp", "ambiguous_matching" if ambiguous else "no_candidate"
            rows["entity_results"].append({"identificador_boe": boe, "entity_type": ENTITY_TABLES[table],
                                           "truth_key": t, "predicted_key": p, "outcome": outcome,
                                           "reason": reason, "temporal_truth": temporal})
            outcomes[table][outcome] += 1
            if outcome == "excluded":
                exclusions[table]["truth"] += int(t is not None)
                exclusions[table]["predicted"] += int(p is not None)
            if ambiguous:
                exclusions[table]["ambiguous_truth"] += int(t is not None)
                exclusions[table]["ambiguous_predicted"] += int(p is not None)
            if table == "administrative_actions" and p:
                action_pair_outcomes[p] = outcome
            if outcome in {"fn", "fp", "historical_fp"} or ambiguous:
                error(boe, outcome, ENTITY_TABLES[table], t, p, reason)

    for boe in sorted(scopes):
        for table in ENTITY_TABLES:  # assets -> events -> actions -> locations
            tr = {k: r for k, r in truth_maps[table].items() if r["identificador_boe"] == boe}
            pr = {k: r for k, r in predicted[table].items() if r["boe_id"] == boe}
            excluded = {k for k, r in tr.items() if not _scored(r)}
            if table == "administrative_actions":
                excluded.update(k for k, r in tr.items() if r["temporal_status"] == "ambiguous_not_safely_determinable")
            inherited = {k for k, r in pr.items() if table in {"administrative_actions", "locations"}
                         and r["event_global"] in excluded_pred["events"]}
            if table == "generation_assets":
                candidates = name_candidate_pairs(
                    {k: parse_json_list(str(r["names_json"]), label="names_json") for k, r in tr.items()},
                    {k: r["names"] for k, r in pr.items()})
            elif table == "events":
                ta = {k: {a for a, r in truth_maps["generation_assets"].items()
                          if _global(str(r["identificador_boe"]), str(r["event_key"])) == k} for k in tr}
                pa = {k: {a for a, r in predicted["generation_assets"].items() if r["event_global"] == k} for k in pr}
                candidates = event_candidates(ta, pa, matches["generation_assets"])
            else:
                candidates = set()
                name_pairs = name_candidate_pairs(
                    {k: [str(r["location_name_raw"])] for k, r in tr.items()},
                    {k: r["names"] for k, r in pr.items()}) if table == "locations" else set()
                for t, truth_row in tr.items():
                    accepted = (passages if _scored(truth_row) else all_passages).get((t, "administrative_action"), [])
                    for p, pred_row in pr.items():
                        if matches["events"].get(pred_row["event_global"]) != _global(boe, str(truth_row["event_key"])):
                            continue
                        if (table == "locations" and (t, p) in name_pairs) or (
                            table == "administrative_actions" and evidence_candidate(pred_row["evidence"], accepted)
                        ):
                            candidates.add((t, p))
            rows["candidate_pairs"].extend({"identificador_boe": boe, "entity_type": ENTITY_TABLES[table],
                                           "truth_key": t, "predicted_key": p} for t, p in sorted(candidates))
            result = deterministic_match(truth_keys=tr, predicted_keys=set(pr) - inherited,
                                         candidate_pairs=candidates, excluded_truth_keys=excluded)
            result = replace(result, excluded_predicted=tuple(sorted(set(result.excluded_predicted) | inherited)))
            record(table, boe, result)

    for table, specs in FIELD_SPECS.items():
        for p, t in sorted(matches[table].items()):
            if p in excluded_pred[table] or (table == "administrative_actions" and action_pair_outcomes[p] != "tp"):
                continue
            tr, pr = truth_maps[table][t], predicted[table][p]
            for expected_column, field in specs:
                expected = str(tr[expected_column])
                applicable = expected != NA
                if field == "is_modification" and applicable:
                    expected = expected == "true"
                actual = pr[field]
                correct = expected == actual and type(expected) is type(actual) if applicable else None
                rows["field_results"].append({"identificador_boe": pr["boe_id"], "entity_type": ENTITY_TABLES[table],
                    "truth_key": t, "predicted_key": p, "field_name": expected_column,
                    "expected_value_json": json.dumps(expected, ensure_ascii=False),
                    "predicted_value_json": json.dumps(actual, ensure_ascii=False),
                    "applicable": applicable, "correct": correct})
                if applicable and not correct:
                    error(pr["boe_id"], "incorrect_attribute", ENTITY_TABLES[table], t, p, expected_column)

    current_truth = {t: r for t, r in truth_maps["administrative_actions"].items()
                     if _scored(r) and r["temporal_status"] == "current"}
    expected_sets = {t: {f"truth:{_global(str(r['identificador_boe']), a)}" for a in parse_json_list(
        str(r["expected_affected_generation_asset_keys_json"]), label="affected_assets")}
        for t, r in current_truth.items()}
    matched_current: set[str] = set()
    for p, pr in sorted(predicted["administrative_actions"].items()):
        t = matches["administrative_actions"].get(p)
        outcome = action_pair_outcomes[p]
        actual, unresolved = effective_assets(pr, predicted, matches["generation_assets"])
        applicable = outcome == "tp"
        expected = expected_sets.get(t, set()) if applicable else set()
        correct = actual == expected and not unresolved if applicable else None
        rows["affected_asset_sets"].append({"identificador_boe": pr["boe_id"], "truth_action_key": t,
            "predicted_action_key": p, "expected_assets_json": json.dumps(sorted(expected)),
            "predicted_assets_json": json.dumps(sorted(actual)), "unresolved_targets_json": json.dumps(unresolved),
            "applicable": applicable, "correct": correct, "reason": outcome})
        if unresolved or (applicable and not correct):
            error(pr["boe_id"], "incorrect_or_unresolved_attribution", "administrative_action", t, p,
                  json.dumps(unresolved) if unresolved else "different_effective_asset_set")
        if applicable:
            matched_current.add(t)
            supported = evidence_is_correct(pr["evidence"], passages.get((t, "administrative_action"), []))
            rows["evidence_results"].append({"identificador_boe": pr["boe_id"], "truth_action_key": t,
                "predicted_action_key": p, "predicted_evidence": pr["evidence"],
                "accepted_passages_json": json.dumps(sorted(passages.get((t, "administrative_action"), [])), ensure_ascii=False),
                "evidence_supported": supported})
            if not supported:
                error(pr["boe_id"], "unsupported_evidence", "administrative_action", t, p)
        if outcome != "excluded":
            for asset in sorted(expected | actual):
                pair_outcome = "tp" if asset in expected & actual else "fn" if asset in expected else "fp"
                rows["action_asset_pairs"].append({"identificador_boe": pr["boe_id"], "truth_action_key": t,
                    "predicted_action_key": p, "asset_key": asset, "outcome": pair_outcome})
                if pair_outcome != "tp":
                    error(pr["boe_id"], f"attribution_pair_{pair_outcome}", "administrative_action", t, p, asset)

    for t in sorted(set(current_truth) - matched_current):
        boe = str(current_truth[t]["identificador_boe"])
        rows["affected_asset_sets"].append({"identificador_boe": boe, "truth_action_key": t,
            "predicted_action_key": None, "expected_assets_json": json.dumps(sorted(expected_sets[t])),
            "predicted_assets_json": "[]", "unresolved_targets_json": "[]", "applicable": False,
            "correct": None, "reason": "current_not_matched"})
        for asset in sorted(expected_sets[t]):
            rows["action_asset_pairs"].append({"identificador_boe": boe, "truth_action_key": t,
                "predicted_action_key": None, "asset_key": asset, "outcome": "fn"})
            error(boe, "attribution_pair_fn", "administrative_action", t, None, asset)

    adjudicated_warnings: set[str] = set()
    for p, t in sorted(matches["administrative_actions"].items()):
        tr = truth_maps["administrative_actions"][t]
        temporal, warned = str(tr["temporal_status"]), p in warnings
        if p in excluded_pred["administrative_actions"]:
            outcome = "unadjudicated" if warned else "excluded"
        else:
            outcome = ("tp" if warned else "fn") if temporal == "historical_antecedent" else ("fp" if warned else "tn")
        rows["p0_results"].append({"identificador_boe": str(tr["identificador_boe"]), "truth_action_key": t,
            "predicted_action_key": p, "temporal_truth": temporal, "p0_warning": warned,
            "p0_outcome": outcome, "reason": "temporal_truth_excluded" if outcome in {"excluded", "unadjudicated"} else "matched_extracted_action"})
        if warned:
            adjudicated_warnings.add(p)
        if outcome in {"fp", "fn"}:
            error(str(tr["identificador_boe"]), f"p0_{outcome}", "administrative_action", t, p)
    for p in sorted(warnings - adjudicated_warnings):
        rows["p0_results"].append({"identificador_boe": p.split("|", 1)[0], "truth_action_key": None,
            "predicted_action_key": p, "temporal_truth": None, "p0_warning": True,
            "p0_outcome": "unadjudicated", "reason": "prediction_not_uniquely_adjudicated"})
    for t, tr in sorted(truth_maps["administrative_actions"].items()):
        if _scored(tr) and tr["temporal_status"] == "historical_antecedent" and t not in matches["administrative_actions"].values():
            rows["p0_results"].append({"identificador_boe": str(tr["identificador_boe"]), "truth_action_key": t,
                "predicted_action_key": None, "temporal_truth": "historical_antecedent", "p0_warning": None,
                "p0_outcome": "missing_extraction_not_p0_fn", "reason": "no_extracted_matched_action"})

    document_confusion = {scope: {actual: 0 for actual in (
        "generation_project_specific", "not_relevant_for_generation_projects", "missing")}
        for scope in ("generation_project_specific", "not_relevant_for_generation_projects")}
    for _, tr in truth.tables["documents"].sort_values("identificador_boe").iterrows():
        boe = str(tr["identificador_boe"])
        expected, actual = str(tr["expected_document_scope"]), scopes[boe]
        document_confusion[expected][actual or "missing"] += 1
        counter = Counter(r["outcome"] for r in rows["entity_results"] if r["identificador_boe"] == boe)
        rows["document_results"].append({"identificador_boe": boe,
            "extraction_status": str(snapshot.attempts.loc[snapshot.attempts["identificador_boe"].eq(boe), "extraction_status"].iloc[0]),
            "expected_document_scope": expected, "predicted_document_scope": actual, "correct": expected == actual,
            "entity_tp": counter["tp"], "entity_fp": counter["fp"] + counter["historical_fp"], "entity_fn": counter["fn"]})
        if expected != actual:
            error(boe, "incorrect_document_scope", "document")

    entity_metrics = {ENTITY_TABLES[table]: {
        **detection(c["tp"], c["fp"] + c["historical_fp"], c["fn"]),
        "excluded_truth": exclusions[table]["truth"], "excluded_predicted": exclusions[table]["predicted"],
        "ambiguous_truth": exclusions[table]["ambiguous_truth"], "ambiguous_predicted": exclusions[table]["ambiguous_predicted"],
    } for table, c in outcomes.items()}
    actions = outcomes["administrative_actions"]
    entity_metrics["administrative_action"].update({"historical_contamination_fp": actions["historical_fp"],
        "other_fp": actions["fp"], "historical_not_extracted": actions["historical_not_extracted"],
        "ambiguous_temporal_truth": sum(_scored(r) and r["temporal_status"] == "ambiguous_not_safely_determinable"
                                        for r in truth_maps["administrative_actions"].values())})
    fields = {}
    for table, specs in FIELD_SPECS.items():
        for name, _ in specs:
            group = [r for r in rows["field_results"] if r["field_name"] == name]
            applicable = [r for r in group if r["applicable"]]
            fields[name] = accuracy(sum(r["correct"] for r in applicable), len(applicable), excluded=len(group) - len(applicable))
    pair_counts = Counter(r["outcome"] for r in rows["action_asset_pairs"])
    sets = [r for r in rows["affected_asset_sets"] if r["applicable"]]
    pc = Counter(r["p0_outcome"] for r in rows["p0_results"])
    evidence = rows["evidence_results"]
    metrics = {
        "aggregation_policy": "corpus micro; no macro or global accuracy",
        "document_scope": {**accuracy(sum(r["correct"] for r in rows["document_results"]), len(rows["document_results"])),
                           "aggregation": "micro_document_level", "confusion_matrix": document_confusion},
        "entity_detection": entity_metrics, "field_accuracy": fields,
        "affected_assets_exact_set": accuracy(sum(r["correct"] for r in sets), len(sets),
            excluded=len(rows["affected_asset_sets"]) - len(sets)),
        "action_asset_pairs": detection(pair_counts["tp"], pair_counts["fp"], pair_counts["fn"]),
        "action_evidence_support": {**ratio(sum(r["evidence_supported"] for r in evidence), len(evidence), name="support_rate"),
                                    "supported": sum(r["evidence_supported"] for r in evidence)},
        "p0": {**detection(pc["tp"], pc["fp"], pc["fn"]), "tn": pc["tn"],
               "adjudicated_denominator": pc["tp"] + pc["fp"] + pc["fn"] + pc["tn"],
               "false_warning_rate": ratio(pc["fp"], pc["fp"] + pc["tn"], name="rate"),
               "unadjudicated": pc["unadjudicated"], "excluded": pc["excluded"],
               "ambiguous_temporal_truth": entity_metrics["administrative_action"]["ambiguous_temporal_truth"],
               "missing_extraction_not_p0_fn": pc["missing_extraction_not_p0_fn"]},
        "counts": {"documents": len(scopes), "truth": {ENTITY_TABLES[t]: len(truth_maps[t]) for t in ENTITY_TABLES},
                   "predicted": {ENTITY_TABLES[t]: len(predicted[t]) for t in ENTITY_TABLES},
                   "unresolved_attribution_actions": sum(r["unresolved_targets_json"] != "[]" for r in rows["affected_asset_sets"])},
    }
    frames = {name: typed_frame(rows[name], columns) for name, columns in FRAME_COLUMNS.items()}
    entities = frames["entity_results"]
    frames["entity_matches"] = entities.loc[entities["truth_key"].notna() & entities["predicted_key"].notna()].reset_index(drop=True)
    frames["unmatched_truth"] = entities.loc[entities["predicted_key"].isna()].reset_index(drop=True)
    frames["unmatched_predictions"] = entities.loc[entities["truth_key"].isna()].reset_index(drop=True)
    return metrics, frames
