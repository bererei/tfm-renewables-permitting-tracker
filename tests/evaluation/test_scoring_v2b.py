from __future__ import annotations

import copy
import json
from dataclasses import replace

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from evaluation.final_holdout_v1.matching import deterministic_match, evidence_is_correct, name_candidate_pairs, normalize_name
from evaluation.final_holdout_v2.evaluator_freeze import evaluator_declaration
from evaluation.final_holdout_v2.metrics import detection
from evaluation.final_holdout_v2.predictions import EvaluationError, flatten_predictions
from evaluation.final_holdout_v2.scoring import effective_assets, event_candidates
from v2b_fixtures import BOE, OTHER, make_case


@pytest.fixture
def case(tmp_path):
    return make_case(tmp_path)


def counts(metrics, entity, expected):
    assert tuple(metrics["entity_detection"][entity][k] for k in ("tp", "fp", "fn")) == expected


def test_perfect_current_case_and_reduced_scope(case):
    metrics, frames = case.score()
    for entity in ("event", "generation_asset", "administrative_action", "location"):
        counts(metrics, entity, (1, 0, 0))
    assert metrics["document_scope"]["correct"] == metrics["document_scope"]["denominator"] == 2
    assert all(m["accuracy"] == 1 for m in metrics["field_accuracy"].values())
    assert metrics["affected_assets_exact_set"]["accuracy"] == 1
    assert metrics["action_asset_pairs"]["tp"] == 1
    assert metrics["action_evidence_support"]["support_rate"] == 1
    assert metrics["p0"]["tn"] == 1
    assert frames["error_inventory"].empty
    assert set(metrics["entity_detection"]) == {"event", "generation_asset", "administrative_action", "location"}
    assert "temporal_status" not in metrics["field_accuracy"]


@pytest.mark.parametrize("alias", ["PLANTA SINTETICA", "Plánta-Sintética", "  Planta   SINTÉTICA  ", "Alias secundario"])
def test_exact_alias_normalization_and_alternative(case, alias):
    if alias == "Alias secundario":
        case.truth.tables["generation_assets"].loc[0, "names_json"] = '["Planta Sintética", "Alias secundario"]'
    case.event["generation_assets"][0]["names_raw"] = [alias]
    metrics, _ = case.score()
    counts(metrics, "generation_asset", (1, 0, 0))


def test_normalization_preserves_word_order_and_is_not_fuzzy():
    assert normalize_name("  ÉÓLica—ÁLFA. ") == "eolica alfa"
    assert normalize_name("Alfa Planta") != normalize_name("Planta Alfa")
    assert not name_candidate_pairs({"a": ["Planta Alfa"]}, {"b": ["Planta Alffa"]})


@pytest.mark.parametrize("kind,expected", [("wrong_name", (0, 1, 1)), ("extra", (1, 1, 0)), ("missing", (1, 0, 1))])
def test_asset_detection_errors_block_complete_event(case, kind, expected):
    if kind == "wrong_name":
        case.event["generation_assets"][0]["names_raw"] = ["Sin relación"]
    elif kind == "extra":
        asset = copy.deepcopy(case.event["generation_assets"][0])
        asset.update(local_generation_asset_ref="generation_asset_2", names_raw=["Extra inventada"])
        case.event["generation_assets"].append(asset)
    else:
        case.add_asset(predict=False)
    metrics, _ = case.score()
    counts(metrics, "generation_asset", expected)
    counts(metrics, "event", (0, 1, 1))
    counts(metrics, "administrative_action", (0, 1, 1))


def test_incorrect_generation_type_does_not_affect_matching(case):
    case.event["generation_assets"][0]["generation_type"] = "eolica"
    metrics, _ = case.score()
    counts(metrics, "generation_asset", (1, 0, 0))
    counts(metrics, "event", (1, 0, 0))
    assert metrics["field_accuracy"]["expected_generation_type"]["correct"] == 0


def test_2_by_2_asset_tie_has_no_arbitrary_pair(case):
    case.add_asset("Planta Sintética")
    metrics, frames = case.score()
    counts(metrics, "generation_asset", (0, 2, 2))
    assert metrics["entity_detection"]["generation_asset"]["ambiguous_truth"] == 2
    assert frames["entity_matches"].empty


@pytest.mark.parametrize("truth_sets,pred_sets,mapping,expected", [
    ({"t": {"a", "b"}}, {"p": {"x", "y"}}, {"x": "a", "y": "b"}, {("t", "p")}),
    ({"t": {"a", "b"}}, {"p": {"x"}}, {"x": "a"}, set()),
    ({"t": {"a"}}, {"p": {"x", "y"}}, {"x": "a"}, set()),
    ({"t": {"a", "b"}}, {"p": {"x"}, "q": {"y"}}, {"x": "a", "y": "b"}, set()),
    ({"t": {"a"}, "u": {"b"}}, {"p": {"x", "y"}}, {"x": "a", "y": "b"}, set()),
    ({"t": set()}, {"p": set()}, {}, set()),
])
def test_event_complete_sets_missing_extra_split_merge(truth_sets, pred_sets, mapping, expected):
    assert event_candidates(truth_sets, pred_sets, mapping) == expected


def test_forced_event_assignment_handles_tie_and_order():
    candidates = event_candidates({"t1": {"a"}, "t2": {"a"}}, {"p1": {"x"}, "p2": {"x"}}, {"x": "a"})
    a = deterministic_match(truth_keys=["t1", "t2"], predicted_keys=["p1", "p2"], candidate_pairs=candidates)
    b = deterministic_match(truth_keys=["t2", "t1"], predicted_keys=["p2", "p1"], candidate_pairs=reversed(sorted(candidates)))
    assert a == b and not a.matches
    assert len(a.ambiguous_truth) == len(a.ambiguous_predicted) == 2


@pytest.mark.parametrize("split", [True, False])
def test_event_split_merge_visible_end_to_end(case, split):
    case.add_asset()
    if split:
        second = copy.deepcopy(case.event)
        second["generation_assets"] = [case.event["generation_assets"].pop()]
        second["administrative_actions"][0]["targets"] = ["generation_asset_2"]
        case.payloads[BOE]["publication_events"].append(second)
        expected = (0, 2, 1)
    else:
        event = case.truth.tables["events"].iloc[0].to_dict()
        event["event_key"] = "event_2"
        case.append_truth("events", event)
        case.truth.tables["generation_assets"].loc[1, "event_key"] = "event_2"
        expected = (0, 1, 2)
    metrics, _ = case.score()
    counts(metrics, "generation_asset", (2, 0, 0))
    counts(metrics, "event", expected)


def test_current_omission_and_extra_action(case):
    case.add_action(predict=False)
    extra = copy.deepcopy(case.event["administrative_actions"][0])
    extra["evidence"] = "Actuación sin ningún pasaje truth."
    case.event["administrative_actions"].append(extra)
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (1, 1, 1))
    assert tuple(metrics["action_asset_pairs"][k] for k in ("tp", "fp", "fn")) == (1, 1, 1)


def test_historical_prediction_counted_once_and_omission_never_fn(case):
    case.add_action("historical_antecedent")
    case.add_action("historical_antecedent", predict=False)
    metrics, frames = case.score()
    counts(metrics, "administrative_action", (1, 1, 0))
    action = metrics["entity_detection"]["administrative_action"]
    assert action["historical_contamination_fp"] == action["historical_not_extracted"] == 1
    assert action["other_fp"] == 0
    assert len(frames["field_results"].query("entity_type == 'administrative_action'")) == 3
    assert tuple(metrics["action_asset_pairs"][k] for k in ("tp", "fp", "fn")) == (1, 1, 0)


@pytest.mark.parametrize("field,value", [("action_type", "other"), ("decision", "other"), ("is_modification", True),
                                          ("action_type", None), ("decision", None), ("is_modification", None)])
def test_action_attributes_never_select_matching_missing_incorrect(case, field, value):
    case.event["administrative_actions"][0][field] = value
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (1, 0, 0))
    result = metrics["field_accuracy"][f"expected_{field}"]
    assert result["denominator"] == 1 and result["correct"] == 0


def test_shared_evidence_ambiguous_without_attribute_tiebreak(case):
    shared = case.event["administrative_actions"][0]["evidence"]
    case.add_action("historical_antecedent", evidence=shared)
    case.event["administrative_actions"][1]["action_type"] = "other"
    case.warn(1, 2)
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (0, 2, 1))
    assert metrics["entity_detection"]["administrative_action"]["historical_contamination_fp"] == 0
    assert metrics["p0"]["unadjudicated"] == 2
    assert metrics["p0"]["adjudicated_denominator"] == 0


def test_forced_pairs_survive_unrelated_ambiguity():
    r = deterministic_match(truth_keys=["a", "b", "c"], predicted_keys=["x", "y", "z"],
        candidate_pairs=[("a", "x"), ("b", "y"), ("b", "z"), ("c", "y"), ("c", "z")])
    assert r.matches == (("a", "x"),)


@pytest.mark.parametrize("targets,expected_exact,expected_pairs", [
    (["generation_asset_1", "generation_asset_2"], 1, (2, 0, 0)),
    (["event"], 1, (2, 0, 0)),
    (["generation_asset_1"], 0, (1, 0, 1)),
    ([], 0, (0, 0, 2)),
    (["unknown_target"], 0, (0, 0, 2)),
])
def test_attribution_exact_set_and_pairs(case, targets, expected_exact, expected_pairs):
    case.add_asset()
    case.truth.tables["administrative_actions"].loc[0, "expected_affected_generation_asset_keys_json"] = '["asset_1", "asset_2"]'
    case.event["administrative_actions"][0]["targets"] = targets
    metrics, frames = case.score()
    counts(metrics, "administrative_action", (1, 0, 0))
    assert metrics["affected_assets_exact_set"]["correct"] == expected_exact
    assert tuple(metrics["action_asset_pairs"][k] for k in ("tp", "fp", "fn")) == expected_pairs
    if not targets or targets == ["unknown_target"]:
        assert frames["affected_asset_sets"].iloc[0]["unresolved_targets_json"] != "[]"


def test_extra_affected_asset_penalizes_attribution_only(case):
    case.add_asset()
    case.event["administrative_actions"][0]["targets"] = ["event"]
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (1, 0, 0))
    assert metrics["affected_assets_exact_set"]["accuracy"] == 0
    assert tuple(metrics["action_asset_pairs"][k] for k in ("tp", "fp", "fn")) == (1, 1, 0)


def test_unmatched_asset_is_retained_in_pairs_when_event_fails(case):
    asset = copy.deepcopy(case.event["generation_assets"][0])
    asset.update(local_generation_asset_ref="generation_asset_2", names_raw=["Extra"])
    case.event["generation_assets"].append(asset)
    case.event["administrative_actions"][0]["targets"] = ["event"]
    metrics, frames = case.score()
    assert tuple(metrics["action_asset_pairs"][k] for k in ("tp", "fp", "fn")) == (0, 2, 1)
    assert frames["action_asset_pairs"]["asset_key"].str.startswith("prediction:").sum() == 1


@pytest.mark.parametrize("links,expected", [(["generation_asset_1"], 1), ([], 0), (["generation_asset_99"], 0)])
def test_component_projection_only_explicit_links(case, links, expected):
    case.event["associated_components"] = [{"local_component_ref": "component_1", "related_generation_asset_refs": links}]
    case.event["administrative_actions"][0]["targets"] = ["component_1"]
    metrics, _ = case.score()
    assert metrics["affected_assets_exact_set"]["correct"] == expected
    assert metrics["action_asset_pairs"]["tp"] == expected
    assert metrics["action_asset_pairs"]["fn"] == 1 - expected


@pytest.mark.parametrize("targets,links,expected", [(["event"], [], {"generation_asset_1", "generation_asset_2"}),
    (["generation_asset_2"], [], {"generation_asset_2"}), (["component_1"], ["generation_asset_1"], {"generation_asset_1"}),
    (["component_1"], [], set())])
def test_projection_agrees_with_gold_code(case, targets, links, expected):
    from renewables_permitting.gold import _action_project_attributions
    case.add_asset()
    case.event["associated_components"] = [{"local_component_ref": "component_1", "related_generation_asset_refs": links}]
    case.event["administrative_actions"][0]["targets"] = targets
    predicted, _ = flatten_predictions(case.sync())
    action = next(iter(predicted["administrative_actions"].values()))
    result, _ = effective_assets(action, predicted, {})
    assert {key.rsplit(":", 1)[1] for key in result} == expected
    targets_frame = pd.DataFrame([{"event_id": "event", "administrative_action_id": "action",
        "target_entity_id": t, "target_kind": "event" if t == "event" else "associated_component" if t.startswith("component") else "generation_asset"} for t in targets])
    links_frame = pd.DataFrame([{"event_id": "event", "associated_component_id": "component_1", "generation_asset_mention_id": ref} for ref in links],
                              columns=["event_id", "associated_component_id", "generation_asset_mention_id"])
    asset_projects = pd.DataFrame([{"event_id": "event", "generation_asset_mention_id": ref, "project_id": ref}
                                  for ref in ("generation_asset_1", "generation_asset_2")])
    gold = _action_project_attributions(targets_frame, links_frame, asset_projects)
    assert set(gold["project_id"]) == expected


@pytest.mark.parametrize("kind,expected", [("wrong_level", (1, 0, 0)), ("extra", (1, 1, 0)),
                                           ("missing", (0, 0, 1)), ("homonym", (0, 2, 2))])
def test_locations_name_only_level_and_detection(case, kind, expected):
    locations = case.event["administrative_locations"]
    if kind == "wrong_level":
        locations[0].update(location_name_raw="VILLA SINTETICA", location_level="provincia")
    elif kind == "extra":
        locations.append({"location_name_raw": "Otra Villa", "location_level": "municipio"})
    elif kind == "missing":
        locations.clear()
    else:
        row = case.truth.tables["locations"].iloc[0].to_dict()
        row.update(location_key="location_2", expected_location_level="provincia")
        case.append_truth("locations", row)
        locations.append({"location_name_raw": "Villa Sintética", "location_level": "provincia"})
    metrics, _ = case.score()
    counts(metrics, "location", expected)
    if kind == "wrong_level":
        assert metrics["field_accuracy"]["expected_location_level"]["correct"] == 0


@pytest.mark.parametrize("evidence,matched,supported", [
    ("Se otorga autorización [...] Planta Sintética.", True, True),
    ("Se otorga autorización [...] Fragmento inventado.", True, False),
    ("", False, False), (None, False, False),
    ("Evidencia de otro owner.", False, False),
])
def test_evidence_all_fragments_and_owner(case, evidence, matched, supported):
    # This text exists in another owner, so it must not anchor the action.
    row = case.truth.tables["evidence_passages"].iloc[0].to_dict()
    row.update(owner_type="generation_asset", owner_key="asset_1", passage_text="Evidencia de otro owner.")
    case.append_truth("evidence_passages", row)
    case.event["administrative_actions"][0]["evidence"] = evidence
    metrics, _ = case.score()
    assert metrics["entity_detection"]["administrative_action"]["tp"] == int(matched)
    assert metrics["action_evidence_support"]["denominator"] == int(matched)
    assert metrics["action_evidence_support"]["supported"] == int(supported)
    assert not evidence_is_correct("", ["Pasaje aceptado"])


def test_full_p0_confusion_and_omitted_history(case):
    case.add_action("historical_antecedent")  # warned TP
    case.add_action("historical_antecedent")  # unwarned FN
    case.add_action("current")  # unwarned TN
    case.add_action("historical_antecedent", predict=False)
    case.warn(1, 2, 99)  # current FP, historical TP, unmatched warning
    metrics, _ = case.score()
    p0 = metrics["p0"]
    assert tuple(p0[k] for k in ("tp", "fp", "fn", "tn")) == (1, 1, 1, 1)
    assert p0["precision"] == p0["recall"] == p0["f1"] == .5
    assert p0["false_warning_rate"]["rate"] == .5
    assert p0["false_warning_rate"]["denominator"] == 2
    assert p0["unadjudicated"] == p0["missing_extraction_not_p0_fn"] == 1


def test_p0_duplicates_and_cross_document_warning_identity(case):
    case.warn(1, 1)
    case.warn(1)
    case.snapshot.review_queue.loc[1, "validation_issues_json"] = json.dumps([
        {"administrative_action_id": f"{OTHER}_event_1_action_1"}])
    metrics, _ = case.score()
    assert metrics["p0"]["fp"] == 1
    assert metrics["p0"]["unadjudicated"] == 1


@pytest.mark.parametrize("warn", [False, True])
def test_ambiguous_temporal_truth_is_excluded_explicitly(case, warn):
    case.add_action("ambiguous_not_safely_determinable")
    if warn:
        case.warn(2)
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (1, 0, 0))
    assert metrics["entity_detection"]["administrative_action"]["ambiguous_temporal_truth"] == 1
    assert metrics["p0"]["adjudicated_denominator"] == 1
    assert metrics["p0"]["unadjudicated"] == int(warn)
    assert metrics["action_asset_pairs"]["fp"] == 0


@pytest.mark.parametrize("tp,fp,fn,precision,recall,f1", [(0, 0, 0, None, None, None),
    (0, 0, 2, None, 0., None), (0, 2, 0, 0., None, None), (0, 2, 2, 0., 0., 0.), (1, 1, 1, .5, .5, .5)])
def test_zero_denominator_convention(tp, fp, fn, precision, recall, f1):
    m = detection(tp, fp, fn)
    assert (m["precision"], m["recall"], m["f1"]) == (precision, recall, f1)
    assert m["precision_denominator"] == tp + fp
    assert m["recall_denominator"] == tp + fn
    assert (m["undefined_reasons"]["f1"] is not None) == (f1 is None)


def test_scope_both_classification_errors_and_no_truth_derivation(case):
    case.payloads[OTHER]["publication_events"] = copy.deepcopy(case.payloads[BOE]["publication_events"])
    case.payloads[OTHER]["document_scope"] = "generation_project_specific"
    case.payloads[BOE]["publication_events"] = []
    case.payloads[BOE]["document_scope"] = "not_relevant_for_generation_projects"
    metrics, _ = case.score()
    m = metrics["document_scope"]
    assert m["correct"] == 0 and m["denominator"] == 2
    assert m["confusion_matrix"]["generation_project_specific"]["not_relevant_for_generation_projects"] == 1
    assert m["confusion_matrix"]["not_relevant_for_generation_projects"]["generation_project_specific"] == 1
    counts(metrics, "generation_asset", (0, 1, 1))


@pytest.mark.parametrize("kind", ["failed", "uncertain"])
def test_missing_scope_is_incorrect_not_excluded(case, kind):
    case.payloads[BOE]["publication_events"] = []
    case.payloads[BOE]["document_scope"] = None
    if kind == "failed":
        case.snapshot.attempts.loc[0, "extraction_status"] = "error"
    metrics, _ = case.score()
    assert metrics["document_scope"]["correct"] == 1
    assert metrics["document_scope"]["denominator"] == 2
    assert metrics["document_scope"]["confusion_matrix"]["generation_project_specific"]["missing"] == 1
    assert metrics["p0"]["false_warning_rate"]["rate"] is None


def test_attribute_na_excludes_only_that_field(case):
    case.truth.tables["generation_assets"].loc[0, "expected_generation_type"] = "__NA__"
    metrics, _ = case.score()
    counts(metrics, "generation_asset", (1, 0, 0))
    assert metrics["field_accuracy"]["expected_generation_type"]["excluded"] == 1
    assert metrics["field_accuracy"]["expected_generation_type"]["accuracy"] is None


def test_row_order_invariance_all_tables_and_inputs(case):
    case.add_asset()
    case.add_action("historical_antecedent")
    case.warn(2, 1, 99)
    metrics, frames = case.score()
    declaration = evaluator_declaration()
    case.truth.tables.update({k: f.sample(frac=1, random_state=42).reset_index(drop=True)
                              for k, f in case.truth.tables.items()})
    case.snapshot = replace(case.snapshot, **{field: getattr(case.snapshot, field).sample(frac=1, random_state=7).reset_index(drop=True)
        for field in ("attempts", "current_extractions", "review_queue", "documents", "manual_reviews", "historical_corrections", "historical_reviews")})
    actual, actual_frames = case.score()
    assert actual == metrics
    for name in frames:
        assert_frame_equal(actual_frames[name], frames[name])
    assert evaluator_declaration() == declaration


def test_scoring_never_mutates_inputs(case):
    snapshot = case.sync()
    before = {k: f.copy(deep=True) for k, f in case.truth.tables.items()}
    attempts = snapshot.attempts.copy(deep=True)
    case.score()
    for name, frame in before.items():
        assert_frame_equal(case.truth.tables[name], frame)
    assert_frame_equal(snapshot.attempts, attempts)


def test_duplicate_prediction_refs_rejected_instead_of_overwritten(case):
    case.event["generation_assets"].append(copy.deepcopy(case.event["generation_assets"][0]))
    with pytest.raises(EvaluationError, match="Duplicate"):
        case.score()


@pytest.mark.parametrize("mixed", [False, True])
def test_excluded_truth_shields_only_exclusively_excluded_candidates(case, mixed):
    passage = "Actuación expresamente excluida de evaluación."
    case.add_action(evidence=passage)
    case.truth.tables["administrative_actions"].loc[1, "adjudication"] = "excluded_from_scoring"
    case.truth.tables["evidence_passages"].loc[1, "adjudication"] = "excluded_from_scoring"
    if mixed:
        case.truth.tables["evidence_passages"].loc[0, "passage_text"] = passage
        case.event["administrative_actions"][0]["evidence"] = passage
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (0, 2, 1) if mixed else (1, 0, 0))
    assert metrics["entity_detection"]["administrative_action"]["excluded_truth"] == 1
    assert metrics["entity_detection"]["administrative_action"]["excluded_predicted"] == (0 if mixed else 1)


def test_secondary_truth_entities_never_enter_metrics(case):
    from test_final_holdout_v2 import _v2_rows
    rows = _v2_rows(include_secondary=True)
    before, _ = case.score()
    for table in ("associated_components", "technical_mentions", "participants", "action_targets"):
        for row in rows[table]:
            case.append_truth(table, row)
    after, _ = case.score()
    assert before == after


def test_no_predictions_yields_no_p0_fn_and_explicit_empty_schemas(case):
    case.add_action("historical_antecedent", predict=False)
    case.payloads[BOE]["publication_events"] = []
    case.payloads[BOE]["document_scope"] = None
    metrics, frames = case.score()
    assert metrics["p0"]["fn"] == 0
    assert metrics["p0"]["recall"] is None
    assert metrics["p0"]["false_warning_rate"]["undefined_reason"] == "zero_denominator"
    assert metrics["action_evidence_support"]["support_rate"] is None
    assert metrics["affected_assets_exact_set"]["accuracy"] is None
    assert frames["field_results"].empty and len(frames["field_results"].columns) == 9
    assert str(frames["field_results"]["correct"].dtype) == "boolean"


def test_micro_entity_precision_uses_corpus_counts(case):
    for i in range(3):
        event = copy.deepcopy(case.event)
        event["generation_assets"][0]["names_raw"] = [f"Extra {i}"]
        case.payloads[OTHER]["publication_events"].append(event)
    case.payloads[OTHER]["document_scope"] = "generation_project_specific"
    metrics, _ = case.score()
    counts(metrics, "generation_asset", (1, 3, 0))
    assert metrics["entity_detection"]["generation_asset"]["precision"] == .25
    assert metrics["entity_detection"]["generation_asset"]["precision_denominator"] == 4


def test_missing_is_modification_is_not_defaulted_to_false(case):
    del case.event["administrative_actions"][0]["is_modification"]
    metrics, _ = case.score()
    assert metrics["field_accuracy"]["expected_is_modification"]["correct"] == 0


def test_unaccepted_passage_cannot_anchor_scored_action(case):
    row = case.truth.tables["evidence_passages"].iloc[0].to_dict()
    row.update(passage_text="Pasaje descartado por la revisión.", adjudication="excluded_from_scoring")
    case.append_truth("evidence_passages", row)
    case.event["administrative_actions"][0]["evidence"] = row["passage_text"]
    metrics, _ = case.score()
    counts(metrics, "administrative_action", (0, 1, 1))
