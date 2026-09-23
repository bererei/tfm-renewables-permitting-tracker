"""Entirely invented BOE-2099 fixtures; never read operational runs/."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from evaluation.final_holdout_v1 import contract as v1
from evaluation.final_holdout_v2.contract import CONTRACT_VERSION, TABLE_SPECS, load_truth, sha256_file
from evaluation.final_holdout_v2.predictions import PredictionSnapshot
from evaluation.final_holdout_v2.scoring import evaluate_frames
from test_final_holdout_v2 import PROJECT_BOE, NON_RELEVANT_BOE, _write_v2_truth

BOE = PROJECT_BOE
OTHER = NON_RELEVANT_BOE


@dataclass
class Case:
    truth: object
    payloads: dict
    snapshot: PredictionSnapshot
    working: Path

    @property
    def event(self):
        return self.payloads[BOE]["publication_events"][0]

    def sync(self):
        attempts = self.snapshot.attempts.copy()
        for i, r in attempts.iterrows():
            payload = self.payloads[r["identificador_boe"]]
            attempts.at[i, "extraction_json"] = json.dumps(payload, ensure_ascii=False)
            attempts.at[i, "document_scope"] = payload["document_scope"]
        self.snapshot = replace(self.snapshot, attempts=attempts,
                                current_extractions=attempts.loc[attempts["extraction_status"].eq("ok")].copy())
        return self.snapshot

    def score(self):
        return evaluate_frames(self.truth, self.sync())

    def append_truth(self, table, row):
        frame = self.truth.tables[table]
        self.truth.tables[table] = pd.concat([frame, pd.DataFrame([row], columns=frame.columns).astype("string")], ignore_index=True)

    def add_asset(self, name="Otra Planta", *, event="event_1", predict=True):
        frame = self.truth.tables["generation_assets"]
        row = frame.iloc[0].to_dict()
        key = f"asset_{len(frame) + 1}"
        row.update(asset_key=key, event_key=event, names_json=json.dumps([name]))
        self.append_truth("generation_assets", row)
        if predict:
            asset = copy.deepcopy(self.event["generation_assets"][0])
            asset.update(local_generation_asset_ref=f"generation_asset_{len(self.event['generation_assets']) + 1}", names_raw=[name])
            self.event["generation_assets"].append(asset)
        return key

    def add_action(self, temporal="current", *, predict=True, evidence=None):
        frame = self.truth.tables["administrative_actions"]
        key = f"action_{len(frame) + 1}"
        row = frame.iloc[0].to_dict()
        row.update(action_key=key, temporal_status=temporal)
        self.append_truth("administrative_actions", row)
        evidence = evidence or f"Actuación sintética diferenciada número {len(frame) + 1}."
        passage = self.truth.tables["evidence_passages"].iloc[0].to_dict()
        passage.update(owner_key=key, passage_text=evidence)
        self.append_truth("evidence_passages", passage)
        if predict:
            action = copy.deepcopy(self.event["administrative_actions"][0])
            action["evidence"] = evidence
            self.event["administrative_actions"].append(action)
        return key

    def warn(self, *indices, boe=BOE):
        findings = [{"administrative_action_id": f"{boe}_event_1_action_{i}"} for i in indices]
        row = {"identificador_boe": boe, "reason_code": "possible_historical_antecedent",
               "validation_issues_json": json.dumps(findings)}
        self.snapshot = replace(self.snapshot, review_queue=pd.concat([
            self.snapshot.review_queue, pd.DataFrame([row])], ignore_index=True))


def make_case(tmp_path):
    working = _write_v2_truth(tmp_path / "working")
    truth = load_truth(working, require_complete=True)
    action = {"action_type": "autorizacion_administrativa_previa", "decision": "autorizado",
              "is_modification": False, "targets": ["generation_asset_1"],
              "evidence": "Se otorga autorización a la Planta Sintética."}
    event = {"generation_assets": [{"local_generation_asset_ref": "generation_asset_1",
        "names_raw": ["Planta Sintética"], "generation_type": "fotovoltaica", "evidence": "Planta Sintética"}],
        "administrative_actions": [action], "administrative_locations": [
            {"location_name_raw": "Villa Sintética", "location_level": "municipio"}],
        "associated_components": [], "event_summary": "Evento inventado"}
    payloads = {boe: {"boe_id": boe, "publication_date": "2099-01-01", "classification_status": "classified",
                     "classification_reason": "Caso sintético", "document_scope": scope,
                     "publication_events": [event] if boe == BOE else []}
                for boe, scope in ((BOE, "generation_project_specific"), (OTHER, "not_relevant_for_generation_projects"))}
    attempts = pd.DataFrame([{"attempt_id": f"synthetic_{i}", "identificador_boe": boe,
        "source_document_sha256": "a" * 64 if boe == BOE else "b" * 64,
        "attempt_origin": "model", "source_attempt_id": pd.NA, "extraction_status": "ok",
        "extraction_config_id": v1.FROZEN_EXTRACTION_CONFIG_ID, "model_provider": v1.FROZEN_MODEL_PROVIDER,
        "model_name": v1.FROZEN_MODEL_NAME, "document_scope": payloads[boe]["document_scope"],
        "extraction_json": json.dumps(payloads[boe], ensure_ascii=False)} for i, boe in enumerate(payloads)])
    empty = pd.DataFrame(columns=["identificador_boe", "reason_code", "validation_issues_json"])
    snapshot = PredictionSnapshot(tmp_path / "not_published", {}, "c" * 64, pd.DataFrame(), attempts,
        empty.copy(), attempts.copy(), empty.copy(), pd.DataFrame(columns=["boe_id"]),
        pd.DataFrame(columns=["boe_id"]), {})
    return Case(truth, payloads, snapshot, working)


def publish_case(case: Case, tmp_path: Path):
    """Build real-format synthetic inputs, run only deterministic publication."""
    from evaluation.final_holdout_v2.freeze import freeze_truth
    from evaluation.final_holdout_v2.evaluator_freeze import freeze_evaluator
    from evaluation.final_holdout_v2.predictions import load_prediction_snapshot
    from renewables_permitting.extraction.documents import build_source_document
    from renewables_permitting.pipeline import _documents_identity
    from test_final_holdout_v1 import _build_snapshot, _execution_record, _refresh_snapshot_artifact

    source = pd.DataFrame([{"identificador": boe, "fecha_publicacion": "2099-01-01", "titulo": "Documento inventado",
        "texto_limpio": " ".join(case.truth.tables["evidence_passages"]["passage_text"].tolist())}
        for boe in case.payloads])
    source["source_document_sha256"] = [build_source_document(r).source_document_sha256 for _, r in source.iterrows()]
    hashes = source.set_index("identificador")["source_document_sha256"].to_dict()
    case.truth.tables["documents"]["source_document_sha256"] = case.truth.tables["documents"]["identificador_boe"].map(hashes)
    for table, spec in TABLE_SPECS.items():
        case.truth.tables[table].loc[:, spec.columns].to_csv(case.working / f"{table}.csv", index=False)
    selection = case.truth.tables["documents"][["identificador_boe", "source_document_sha256"]].copy()
    selection["source_snapshot_id"] = v1.FROZEN_SOURCE_SNAPSHOT_ID
    selection_path = tmp_path / "selection.csv"
    selection.to_csv(selection_path, index=False)
    metadata = {"truth_contract_version": CONTRACT_VERSION, "holdout_artifact_identity": sha256_file(selection_path),
                "source_snapshot_identity": v1.FROZEN_SOURCE_SNAPSHOT_ID, "predictions_exposed_during_annotation": False,
                "initialization_mode": "synthetic_blind_fixture"}
    (case.working / "truth_metadata.json").write_text(json.dumps(metadata))
    source_path = tmp_path / "source.parquet"
    source.to_parquet(source_path, index=False)
    frozen_path = tmp_path / "frozen_truth"
    frozen = freeze_truth(case.working, frozen_path, holdout_path=selection_path, documents_path=source_path)
    evaluator_path = tmp_path / "frozen_evaluator"
    freeze_evaluator(truth_dir=frozen_path, output_dir=evaluator_path,
                     expected_truth_artifact_id=frozen.truth_artifact_id,
                     expected_truth_manifest_sha256=sha256_file(frozen_path / "manifest.json"))
    case.sync()
    case.snapshot.attempts["source_document_sha256"] = case.snapshot.attempts["identificador_boe"].map(hashes)
    prediction_path = _build_snapshot(tmp_path / "predictions")
    replacements = {"documents": source, "attempts": case.snapshot.attempts,
        "current_extractions": case.snapshot.attempts.loc[case.snapshot.attempts["extraction_status"].eq("ok")].copy(),
        "manual_reviews": case.snapshot.manual_reviews, "review_queue": case.snapshot.review_queue}
    for name, frame in replacements.items():
        frame.to_parquet(prediction_path / f"{name}.parquet", index=False)
        _refresh_snapshot_artifact(prediction_path, name, len(frame))
    manifest_path = prediction_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["document_identity_sha256"] = _documents_identity(source)
    manifest_path.write_text(json.dumps(manifest))
    snapshot = load_prediction_snapshot(prediction_path)
    record_path = _execution_record(tmp_path / "execution.json", snapshot.snapshot_identity)
    record = json.loads(record_path.read_text())
    record["holdout_artifact_identity"] = frozen.holdout_artifact_identity
    record_path.write_text(json.dumps(record))
    return {"truth_dir": frozen_path, "predictions_dir": prediction_path,
            "evaluator_dir": evaluator_path, "execution_record_path": record_path,
            "output_dir": tmp_path / "report"}
