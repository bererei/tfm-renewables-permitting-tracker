"""Synthetic primary execution only: no runs/, network or provider outputs."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import itertools
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from evaluation.final_holdout_v1 import evaluator as v1
from evaluation.final_holdout_v1.contract import FROZEN_PRODUCTION_COMMIT, FROZEN_UV_LOCK_SHA256
from evaluation.final_holdout_v2.contract import CONTRACT_VERSION, TABLE_SPECS, load_truth
from evaluation.final_holdout_v2.freeze import freeze_truth
from evaluation.final_holdout_v2.evaluator_freeze import freeze_evaluator, evaluator_declaration
from evaluation.final_holdout_v2.predictions import load_prediction_snapshot, validate_primary_predictions
from evaluation.primary_execution import controller as c, storage as s, verification as g, worker
from evaluation.primary_execution.cli import main
from renewables_permitting import pipeline
from renewables_permitting.extraction import runner as extractor
from renewables_permitting.extraction.config import EXTRACTION_CONFIG_ID, EXTRACTION_CONFIG, MODEL_SETTINGS
from renewables_permitting.extraction.models import BOEAIExtraction
from test_final_holdout_v2 import _document, _write_tables

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_pipeline import _documents, _project_extraction


class FakeAgent:
    def __init__(self, case):
        self.case = case

    async def run(self, prompt, *, model_settings, usage_limits, usage):
        boe = prompt.split("BOE_ID: ")[1].splitlines()[0]
        self.case.calls.append({"boe": boe, "prompt": prompt, "settings": copy.deepcopy(model_settings),
                                "limit": usage_limits.request_limit, "usage": usage})
        if boe in self.case.transient_once:
            from pydantic_ai.exceptions import ModelHTTPError
            self.case.transient_once.remove(boe)
            raise ModelHTTPError(status_code=503, model_name="synthetic")
        if boe in self.case.zero_usage_errors:
            raise ValueError("Synthetic transport failure before reported usage.")
        usage.requests += 1
        usage.input_tokens += 2
        usage.output_tokens += 3
        if boe in self.case.errors:
            raise ValueError("Synthetic terminal failure.")
        row = self.case.documents.set_index("identificador", drop=False).loc[boe]
        payload = _project_extraction(row).model_dump(exclude={"boe_id", "publication_date"})
        return SimpleNamespace(output=BOEAIExtraction.model_validate(payload))


@pytest.fixture
def case(tmp_path, monkeypatch):
    # Block HTTP even if a regression accidentally builds a real provider.
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("Network forbidden"))
    # Frozen runner assigns its last-document diagnostic globally. Restore the
    # pre-fixture value so later import-boundary regression tests remain isolated.
    monkeypatch.setattr(extractor, "debug_state", {})
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-secret-never-log")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    documents = _documents(count=3)
    documents["identificador"] = documents["identificador"].str.replace("2026", "2099")
    documents["fecha_publicacion"] = pd.to_datetime(["2099-01-02", "2099-01-03", "2099-01-04"])
    documents = pipeline.prepare_documents(documents)
    source = tmp_path / "source"
    source.mkdir()
    documents.iloc[::-1].to_parquet(source / "documents.parquet", index=False)
    source_id = pipeline._documents_identity(documents)
    (source / "manifest.json").write_text(json.dumps({
        "stage": "source", "stage_version": "1", "document_identity_sha256": source_id,
        "counts": {"documents": len(documents)},
        "artifacts": {"documents": {"filename": "documents.parquet", "row_count": len(documents),
                                    "sha256": s.file_hash(source / "documents.parquet")}}}))
    selection = documents[["identificador", "source_document_sha256"]].rename(columns={"identificador": "identificador_boe"})
    selection["source_snapshot_id"] = source_id
    selection_path = tmp_path / "selection.csv"
    selection.to_csv(selection_path, index=False)
    rows = {name: [] for name in TABLE_SPECS}
    for row in documents.itertuples():
        record = _document(row.identificador, contract_version=CONTRACT_VERSION,
                           scope="not_relevant_for_generation_projects", status="complete")
        record["source_document_sha256"] = row.source_document_sha256
        rows["documents"].append(record)
    working = _write_tables(tmp_path / "working", TABLE_SPECS, rows)
    (working / "truth_metadata.json").write_text(json.dumps({
        "truth_contract_version": CONTRACT_VERSION, "holdout_artifact_identity": s.file_hash(selection_path),
        "source_snapshot_identity": source_id, "predictions_exposed_during_annotation": False,
        "initialization_mode": "synthetic_fixture"}))
    truth_dir = tmp_path / "truth"
    truth = freeze_truth(working, truth_dir, holdout_path=selection_path, documents_path=source / "documents.parquet")
    evaluator_dir = tmp_path / "evaluator"
    evaluator = freeze_evaluator(truth_dir=truth_dir, output_dir=evaluator_dir,
                                 expected_truth_artifact_id=truth.truth_artifact_id,
                                 expected_truth_manifest_sha256=s.file_hash(truth_dir / "manifest.json"))
    system = tmp_path / "system"
    for relative in ("config/corrections/administrative_action_corrections.csv",
                     "config/manual_reviews/historical_antecedent_reviews.csv"):
        (system / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(g.HARNESS_ROOT / relative, system / relative)
    system_identity = {"commit": FROZEN_PRODUCTION_COMMIT, "extraction_config_id": EXTRACTION_CONFIG_ID,
                       "model_provider": "gemini", "model_name": "google:gemini-2.5-flash",
                       "python_version": "3.10.12", "uv_lock_sha256": FROZEN_UV_LOCK_SHA256,
                       "clean": True, "detached": True, "extraction_config": EXTRACTION_CONFIG}
    monkeypatch.setattr(g, "verify_system", lambda *args: copy.deepcopy(system_identity))
    monkeypatch.setattr(g, "harness_identity", lambda: {"commit": "synthetic_harness", "files_sha256": {}})
    monkeypatch.setattr(v1, "FROZEN_SOURCE_SNAPSHOT_ID", source_id)
    value = SimpleNamespace(root=tmp_path / "synthetic-primary", documents=documents, calls=[], errors=set(),
                            zero_usage_errors=set(), transient_once=set(), truth=truth, working=working,
                            system_identity=system_identity)
    value.args = {"system_root": system, "truth_dir": truth_dir, "evaluator_dir": evaluator_dir,
                  "source": source, "run_root": value.root, "expected_system_commit": FROZEN_PRODUCTION_COMMIT,
                  "expected_config_id": EXTRACTION_CONFIG_ID, "expected_truth_id": truth.truth_artifact_id,
                  "expected_truth_manifest": s.file_hash(truth_dir / "manifest.json"),
                  "expected_evaluator_id": evaluator["declaration"]["evaluator_identity"],
                  "expected_evaluator_manifest": s.file_hash(evaluator_dir / "manifest.json"),
                  "argv": ["synthetic", "prepare-primary-run"],
                  "protocol": g.UniverseProtocol(3, s.file_hash(selection_path), source_id, source_id)}
    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", lambda: FakeAgent(value))
    value.run_worker = lambda meta, directory, **kwargs: worker.execute_job(s.read_json(directory / "job.json"), directory)
    return value


def prepare(case):
    return c.prepare_primary_run(**case.args)


def run(case, **kwargs):
    return c.run_primary(case.root, argv=["synthetic", "run-primary"], runner=case.run_worker, **kwargs)


def finalize(case, **kwargs):
    return c.finalize_primary(case.root, argv=["synthetic", "finalize-primary"], runner=case.run_worker, **kwargs)


def test_prepare_and_readonly_status(case):
    result = prepare(case)
    assert result["counts"]["PENDING"] == 3
    assert not case.calls
    before = s.inventory(case.root)
    assert c.primary_status(case.root) == result
    assert s.inventory(case.root) == before
    assert "synthetic-secret-never-log" not in (case.root / "metadata.json").read_text()


@pytest.mark.parametrize("errors", [False, True])
def test_complete_primary_roundtrip_with_errors_preserved(case, errors):
    if errors:
        case.errors.add(case.documents.iloc[1].identificador)
    prepare(case)
    status = run(case)
    assert status["counts"]["TERMINAL_ERROR"] == int(errors)
    assert len(case.calls) == 3
    run(case)
    assert len(case.calls) == 3
    provenance = finalize(case)
    snapshot = load_prediction_snapshot(case.root / "primary/extraction")
    validate_primary_predictions(snapshot, case.truth)
    assert len(snapshot.attempts) == 3
    assert len(snapshot.current_extractions) == 3 - int(errors)
    assert provenance["document_executions_started"] == 3
    assert provenance["reported_model_usage"]["requests"] == 3
    assert "primary_frozen" in c.primary_status(case.root)["next_safe_action"]
    before = s.inventory(case.root)
    assert finalize(case) == provenance
    assert c.run_primary(case.root, argv=["again"], runner=case.run_worker)["already_finalized"]
    assert s.inventory(case.root) == before


def test_zero_reported_usage_is_preserved_and_evaluator_limit_disclosed(case):
    case.zero_usage_errors.add(case.documents.iloc[1].identificador)
    prepare(case)
    run(case)
    provenance = finalize(case)
    record = s.read_json(case.root / "finalization/execution_record.json")
    assert record["model_usage"]["requests"] == 2
    assert provenance["document_executions_started"] == 3
    assert not provenance["frozen_evaluator_usage_guard_satisfied"]
    assert "not HTTP calls" in provenance["usage_limitation"]


@pytest.mark.parametrize("point,expected_success,expected_indeterminate", [
    ("before_started", 0, 0), ("after_started", 0, 1), ("after_runner", 1, 0), ("after_terminal", 1, 0),
])
def test_interrupt_boundaries_and_safe_resume(case, point, expected_success, expected_indeterminate):
    prepare(case)
    def interrupt(location, document):
        if location == point and document["ordinal"] == 1:
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(case, hook=interrupt)
    status = c.primary_status(case.root)
    assert status["counts"]["TERMINAL_SUCCESS"] == expected_success
    assert status["counts"]["INDETERMINATE"] == expected_indeterminate
    prior = len(case.calls)
    if expected_indeterminate:
        with pytest.raises(s.PrimaryRunError, match="INDETERMINATE"):
            run(case)
        assert len(case.calls) == prior
    else:
        run(case)
        assert [call["boe"] for call in case.calls] == sorted(case.documents.identificador)


@pytest.mark.parametrize("where", ["during_runner", "before_receipt", "after_receipt"])
def test_worker_publication_crash_windows(case, where):
    prepare(case)
    def fail_runner(meta, directory, **kwargs):
        if where == "during_runner":
            raise KeyboardInterrupt
        def fail(point):
            if point == where:
                raise KeyboardInterrupt
        return worker.execute_job(s.read_json(directory / "job.json"), directory, publish_hook=fail)
    with pytest.raises(KeyboardInterrupt):
        c.run_primary(case.root, argv=["synthetic"], runner=fail_runner)
    status = c.primary_status(case.root)
    if where == "after_receipt":
        assert status["counts"]["TERMINAL_SUCCESS"] == 1
        run(case)
        assert len(case.calls) == 3
    else:
        assert status["counts"]["INDETERMINATE"] == 1
        prior = len(case.calls)
        with pytest.raises(s.PrimaryRunError, match="INDETERMINATE"):
            run(case)
        assert len(case.calls) == prior


def test_interrupt_after_two_documents_keeps_third_pending(case):
    prepare(case)
    def stop(point, document):
        if point == "before_started" and document["ordinal"] == 3:
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(case, hook=stop)
    assert c.primary_status(case.root)["counts"]["PENDING"] == 1
    assert len(case.calls) == 2
    run(case)
    assert len(case.calls) == 3


@pytest.mark.parametrize("point", ["after_primary_publication", "after_finalization_publication"])
def test_finalization_publication_recovery_never_repeats_model(case, point):
    prepare(case)
    run(case)
    def interrupt(location, document=None):
        if location == point:
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        finalize(case, hook=interrupt)
    finalize(case)
    assert len(case.calls) == 3
    assert "primary_frozen" in c.primary_status(case.root)["next_safe_action"]


def test_missing_api_key_fails_before_first_document_started(case, monkeypatch):
    prepare(case)
    monkeypatch.delenv("GOOGLE_API_KEY")
    before = (case.root / "journal.jsonl").read_bytes()
    with pytest.raises(s.PrimaryRunError, match="API_KEY"):
        run(case)
    assert (case.root / "journal.jsonl").read_bytes() == before
    assert not case.calls
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-alternative")
    run(case)
    assert len(case.calls) == 3


def test_aggregation_refuses_pending_and_indeterminate(case):
    prepare(case)
    with pytest.raises(s.PrimaryRunError, match="terminal"):
        finalize(case)
    def stop(point, document):
        if point == "after_started":
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(case, hook=stop)
    with pytest.raises(s.PrimaryRunError, match="INDETERMINATE"):
        finalize(case)


@pytest.mark.parametrize("target", ["journal", "metadata", "scope", "receipt", "payload", "logs"])
def test_corruption_stops_without_new_calls(case, target):
    prepare(case)
    run(case)
    first = case.root / "documents/001-BOE-A-2099-101"
    path = {"journal": case.root / "journal.jsonl", "metadata": case.root / "metadata.json",
            "scope": case.root / "scopes/001.csv", "receipt": first / "completion.json",
            "payload": first / "extraction/attempts.parquet", "logs": first / "stdout.log"}[target]
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises((ValueError, OSError)):
        run(case)
    assert len(case.calls) == 3


@pytest.mark.parametrize("kind", ["empty", "torn", "bad_hash", "truncated", "illegal_transition", "bad_event"])
def test_journal_integrity_and_state_transitions(case, kind):
    prepare(case)
    path = case.root / "journal.jsonl"
    if kind == "empty":
        path.write_bytes(b"")
    elif kind == "torn":
        path.write_bytes(path.read_bytes()[:-1])
    elif kind == "bad_hash":
        path.write_bytes(path.read_bytes().replace(b"RUN_PREPARED", b"RUN_INVOKED"))
    elif kind == "truncated":
        s.append_event(case.root, case.root.name, "RUN_INVOKED", {"argv": ["synthetic"]})
        path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
    elif kind == "bad_event":
        path.write_bytes(b'{}\n')
    else:
        meta, _ = c._load(case.root)
        s.append_event(case.root, case.root.name, "DOCUMENT_COMPLETED", meta["documents"][0])
    with pytest.raises(s.PrimaryRunError):
        c.primary_status(case.root)


def test_journal_append_reload_and_no_overwrite(case):
    prepare(case)
    original = (case.root / "journal.jsonl").read_bytes()
    s.append_event(case.root, case.root.name, "RUN_INVOKED", {"argv": ["synthetic"]})
    assert (case.root / "journal.jsonl").read_bytes().startswith(original)
    assert len(s.load_journal(case.root, case.root.name)) == 2
    with pytest.raises(s.PrimaryRunError, match="already exists"):
        prepare(case)


@pytest.mark.parametrize("kind", ["truth_id", "truth_hash", "evaluator_id", "evaluator_hash", "source", "count", "selection"])
def test_preparation_rejects_identity_mismatches(case, kind):
    args = dict(case.args)
    mapping = {"truth_id": "expected_truth_id", "truth_hash": "expected_truth_manifest",
               "evaluator_id": "expected_evaluator_id", "evaluator_hash": "expected_evaluator_manifest"}
    if kind in mapping:
        args[mapping[kind]] = "0" * 64
    elif kind == "source":
        args["protocol"] = replace(args["protocol"], source_identity="0" * 64)
    elif kind == "count":
        args["protocol"] = replace(args["protocol"], document_count=4)
    else:
        args["protocol"] = replace(args["protocol"], holdout_identity="0" * 64)
    with pytest.raises(ValueError):
        c.prepare_primary_run(**args)
    assert not case.root.exists()
    assert not case.calls


@pytest.mark.parametrize("change", ["extra", "missing", "duplicate", "text"])
def test_source_mutations_rejected_before_any_model(case, change):
    source = case.args["source"]
    docs = case.documents.copy()
    if change == "extra":
        extra = docs.iloc[[0]].copy()
        extra["identificador"] = "BOE-A-2099-999"
        docs = pd.concat([docs, extra], ignore_index=True)
    elif change == "missing":
        docs = docs.iloc[:-1]
    elif change == "duplicate":
        docs = pd.concat([docs, docs.iloc[[0]]], ignore_index=True)
    else:
        docs.loc[0, "texto_limpio"] += " Alteración."
    docs.to_parquet(source / "documents.parquet", index=False)
    manifest = s.read_json(source / "manifest.json")
    manifest["artifacts"]["documents"]["sha256"] = s.file_hash(source / "documents.parquet")
    (source / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        prepare(case)
    assert not case.root.exists() and not case.calls


def test_one_writer_lock_and_readonly_running_status(case):
    prepare(case)
    with s.writer_lock(case.root):
        with pytest.raises(s.PrimaryRunError, match="Another controller"):
            run(case)
        assert c.primary_status(case.root)["active_writer"]


@pytest.mark.parametrize("operation", ["prepare-primary-run", "run-primary", "primary-status", "finalize-primary"])
def test_cli_help_has_no_side_effects(operation, capsys):
    with pytest.raises(SystemExit) as error:
        main([operation, "--help"])
    assert error.value.code == 0
    assert "--run-root" in capsys.readouterr().out


@pytest.fixture
def synthetic_git_system(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-system"
    root.mkdir()
    (root / ".gitignore").write_text(".venv/\n")
    shutil.copyfile(g.HARNESS_ROOT / "uv.lock", root / "uv.lock")
    (root / "tracked.txt").write_text("synthetic system")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Synthetic Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm", "synthetic fixture"], check=True)
    commit = g.git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(root), "checkout", "--detach", "-q", commit], check=True)
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("synthetic interpreter stub; never executed")
    monkeypatch.delenv("PYTHONPATH", raising=False)
    actual_run = subprocess.run
    commands = []
    probe = {"extraction_config_id": EXTRACTION_CONFIG_ID, "python_version": "3.10.12",
             "sys_prefix": str(root / ".venv"),
             "module_origins": {"renewables_permitting.pipeline": "src/renewables_permitting/pipeline.py"}}
    value = SimpleNamespace(root=root, commit=commit, commands=commands, probe=probe, lock_ok=True)
    def fake_command(argv, **kwargs):
        if argv[0] == "git":
            return actual_run(argv, **kwargs)
        commands.append((argv, kwargs))
        assert kwargs["env"]["UV_OFFLINE"] == "1"
        assert "PYTHONPATH" not in kwargs["env"]
        if argv[0] == "uv":
            assert "--check" in argv and "--locked" in argv and "--offline" in argv
            if not value.lock_ok:
                raise subprocess.CalledProcessError(1, argv)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        assert argv[0] == str(python) and "-I" in argv and "-B" in argv
        return subprocess.CompletedProcess(argv, 0, json.dumps(probe).encode(), b"")
    monkeypatch.setattr(subprocess, "run", fake_command)
    return value


def test_correct_detached_system_and_locked_interpreter(synthetic_git_system):
    value = synthetic_git_system
    checked = g.verify_system(value.root, value.commit, EXTRACTION_CONFIG_ID)
    assert checked["clean"] and checked["detached"] and checked["lock_environment_checked"]
    assert checked["commit"] == value.commit
    assert len(value.commands) == 2


@pytest.mark.parametrize("kind", ["commit", "dirty", "branch", "lock", "interpreter", "module", "prefix", "config", "pythonpath", "environment", "venv_symlink"])
def test_system_gate_rejects_incompatible_checkouts_and_environment(synthetic_git_system, kind, monkeypatch):
    value = synthetic_git_system
    expected = value.commit
    if kind == "commit":
        expected = "0" * 40
    elif kind == "dirty":
        (value.root / "tracked.txt").write_text("dirty")
    elif kind == "branch":
        subprocess.run(["git", "-C", str(value.root), "checkout", "-qb", "fixture-branch"], check=True)
    elif kind == "lock":
        monkeypatch.setattr(g, "FROZEN_UV_LOCK_SHA256", "0" * 64)
    elif kind == "interpreter":
        (value.root / ".venv/bin/python").unlink()
    elif kind == "module":
        value.probe["module_origins"]["renewables_permitting.pipeline"] = "/different/src/pipeline.py"
    elif kind == "prefix":
        value.probe["sys_prefix"] = "/different/.venv"
    elif kind == "config":
        value.probe["extraction_config_id"] = "different"
    elif kind == "pythonpath":
        monkeypatch.setenv("PYTHONPATH", "/contaminating")
    elif kind == "venv_symlink":
        external = value.root.parent / "external-venv"
        (value.root / ".venv").rename(external)
        (value.root / ".venv").symlink_to(external, target_is_directory=True)
    else:
        value.lock_ok = False
    with pytest.raises(s.PrimaryRunError):
        g.verify_system(value.root, expected, EXTRACTION_CONFIG_ID)


@pytest.mark.parametrize("exists", [False, True])
def test_system_root_must_be_a_git_root(tmp_path, exists):
    path = tmp_path / "not-a-system"
    if exists:
        path.mkdir()
    with pytest.raises(s.PrimaryRunError):
        g.verify_system(path, FROZEN_PRODUCTION_COMMIT, EXTRACTION_CONFIG_ID)


@pytest.mark.parametrize("mode", ["success", "error", "transient_retry"])
def test_batch_and_durable_documents_apply_identical_procedure(case, monkeypatch, mode, tmp_path):
    target = case.documents.iloc[1].identificador
    if mode == "error":
        case.errors.add(target)
    async def no_backoff(_):
        pass
    monkeypatch.setattr(extractor.asyncio, "sleep", no_backoff)
    def reset():
        sequence = itertools.count(1)
        monkeypatch.setattr(extractor, "uuid4", lambda: SimpleNamespace(hex=f"{next(sequence):032x}"))
        case.calls.clear()
        if mode == "transient_retry":
            case.transient_once.add(target)
    reset()
    batch = tmp_path / "logical-batch"
    pipeline.run_extraction_stage(documents=case.args["source"], output_dir=batch,
                                  scope_paths=[case.args["truth_dir"] / "holdout_selection.csv"],
                                  expected_extraction_config_id=EXTRACTION_CONFIG_ID, execute_model=True)
    batch_calls = [{k: (v.requests if k == "usage" else v) for k, v in call.items()} for call in case.calls]
    reset()
    prepare(case)
    run(case)
    durable_calls = [{k: (v.requests if k == "usage" else v) for k, v in call.items()} for call in case.calls]
    assert durable_calls == batch_calls
    assert all(call["settings"] == MODEL_SETTINGS and call["limit"] == 6 for call in case.calls)
    assert len({id(call["usage"]) for call in case.calls}) == 3
    finalize(case)
    batch_snapshot = load_prediction_snapshot(batch)
    durable = load_prediction_snapshot(case.root / "primary/extraction")
    for name in ("documents", "attempts", "current_extractions", "review_queue"):
        left, right = getattr(batch_snapshot, name).copy(), getattr(durable, name).copy()
        # Only wall-clock metadata differs; IDs, payloads, warnings and reported usage remain.
        omitted = {"extracted_at", "duration_seconds"} if name != "review_queue" else {"queued_at"}
        left = left.drop(columns=list(omitted & set(left)))
        right = right.drop(columns=list(omitted & set(right)))
        sort = "identificador" if name == "documents" else "identificador_boe"
        pd.testing.assert_frame_equal(left.sort_values(sort).reset_index(drop=True),
                                      right.sort_values(sort).reset_index(drop=True), check_dtype=False)


def test_aggregation_semantics_ignore_filesystem_order_and_only_queue_clock(case, tmp_path):
    case.errors.add(case.documents.iloc[1].identificador)
    prepare(case)
    run(case)
    first = finalize(case)
    job = s.read_json(case.root / "primary/job.json")
    job["parents"].reverse()
    second = tmp_path / "second-aggregation"
    second.mkdir()
    s.durable_json(second / "job.json", job)
    assert worker.execute_job(job, second) == 4
    snapshot = load_prediction_snapshot(second / "extraction")
    assert c.semantic_snapshot_identity(snapshot) == first["primary_semantic_identity"]
    assert len(case.calls) == 3


@pytest.mark.parametrize("job_exists", [False, True])
def test_interruption_while_preparing_job_still_pending(case, job_exists):
    prepare(case)
    meta, _ = c._load(case.root)
    document = meta["documents"][0]
    directory = case.root / document["output"]
    directory.mkdir()
    if job_exists:
        s.durable_json(directory / "job.json", c._job(case.root, meta, document))
    assert c.primary_status(case.root)["counts"]["PENDING"] == 3
    run(case)
    assert len(case.calls) == 3


@pytest.mark.parametrize("kind", ["unknown_document", "unknown_scope", "started_twice", "malformed_invocation"])
def test_unregistered_outputs_and_illegal_events_fail_closed(case, kind):
    prepare(case)
    if kind == "unknown_document":
        (case.root / "documents/unknown").mkdir()
    elif kind == "unknown_scope":
        (case.root / "scopes/unknown.csv").write_text("identificador_boe\nBOE-A-2099-999\n")
    elif kind == "malformed_invocation":
        s.append_event(case.root, case.root.name, "RUN_INVOKED", {"argv": []})
    else:
        meta, _ = c._load(case.root)
        d = meta["documents"][0]
        directory = case.root / d["output"]
        directory.mkdir()
        s.durable_json(directory / "job.json", c._job(case.root, meta, d))
        data = {**d, "state": "STARTED", "job_sha256": s.file_hash(directory / "job.json")}
        s.append_event(case.root, case.root.name, "DOCUMENT_STARTED", data)
        s.append_event(case.root, case.root.name, "DOCUMENT_STARTED", data)
    with pytest.raises(s.PrimaryRunError):
        run(case)
    assert not case.calls


def test_controller_does_not_change_evaluator_or_protected_inputs(case):
    declaration = evaluator_declaration()
    protected = [case.working, case.args["truth_dir"], case.args["evaluator_dir"]]
    before = [s.inventory(path) for path in protected]
    prepare(case)
    run(case)
    finalize(case)
    assert [s.inventory(path) for path in protected] == before
    assert evaluator_declaration() == declaration


def test_child_retains_writer_lock_after_parent_descriptor_closes(case):
    prepare(case)
    with s.writer_lock(case.root) as fd:
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"],
                                 stdin=subprocess.PIPE, pass_fds=(fd,))
    try:
        assert s.writer_active(case.root)
        with pytest.raises(s.PrimaryRunError, match="Another controller"):
            with s.writer_lock(case.root):
                pass
    finally:
        child.communicate(b"x", timeout=10)
    assert child.returncode == 0
    assert not s.writer_active(case.root)


def test_worker_probe_checks_real_import_origins_without_building_agent(monkeypatch):
    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", lambda: pytest.fail("No agent in probe"))
    result = worker.probe(g.HARNESS_ROOT, EXTRACTION_CONFIG_ID)
    assert result["operational_settings"]["CHECKPOINT_EVERY"] == 5
    assert result["operational_settings"]["MAX_DOCUMENT_CHARS"] is None
    assert result["extraction_config"] == EXTRACTION_CONFIG
    with pytest.raises(ValueError, match="environment"):
        worker.probe(Path("/different/system"), EXTRACTION_CONFIG_ID)
    with pytest.raises(ValueError, match="configuration"):
        worker.probe(g.HARNESS_ROOT, "different")


def test_finalization_checks_terminal_originals_even_after_freeze(case):
    prepare(case)
    run(case)
    finalize(case)
    path = case.root / "documents/001-BOE-A-2099-101/stdout.log"
    path.write_text("changed")
    with pytest.raises(s.PrimaryRunError, match="hash mismatch"):
        finalize(case)


def test_durable_append_fsyncs_files_and_directory(case, monkeypatch):
    prepare(case)
    seen = []
    original = os.fsync
    def sync(fd):
        seen.append(fd)
        original(fd)
    monkeypatch.setattr(os, "fsync", sync)
    s.append_event(case.root, case.root.name, "RUN_INVOKED", {"argv": ["synthetic"]})
    assert len(seen) >= 3  # append file, new head file, containing directory
    assert len(s.load_journal(case.root, case.root.name)) == 2


def test_cross_document_attempt_collision_blocks_aggregation(case, monkeypatch):
    monkeypatch.setattr(extractor, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    prepare(case)
    run(case)
    with pytest.raises(s.PrimaryRunError, match="aggregation failed"):
        finalize(case)
    assert not (case.root / "primary").exists()
    assert len(case.calls) == 3
    assert c.primary_status(case.root)["counts"]["TERMINAL_SUCCESS"] == 3


def test_journal_rejects_out_of_order_start(case):
    prepare(case)
    meta, _ = c._load(case.root)
    document = meta["documents"][1]
    directory = case.root / document["output"]
    directory.mkdir()
    s.durable_json(directory / "job.json", c._job(case.root, meta, document))
    s.append_event(case.root, case.root.name, "DOCUMENT_STARTED", {
        **document, "state": "STARTED", "job_sha256": s.file_hash(directory / "job.json")})
    with pytest.raises(s.PrimaryRunError, match="sequential order"):
        c.primary_status(case.root)


def test_each_worker_checks_its_clean_detached_commit(synthetic_git_system):
    value = synthetic_git_system
    worker.verify_git(value.root, value.commit)
    with pytest.raises(ValueError, match="checkout"):
        worker.verify_git(value.root, "0" * 40)
    (value.root / "tracked.txt").write_text("changed before child launch")
    with pytest.raises(ValueError, match="checkout"):
        worker.verify_git(value.root, value.commit)


def test_run_after_final_seal_publication_only_recovers_missing_final_event(case):
    prepare(case)
    run(case)
    def crash(point, document=None):
        if point == "after_finalization_publication":
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        finalize(case, hook=crash)
    sealed = s.inventory(case.root / "finalization")
    assert "recover_final_journal" in c.primary_status(case.root)["next_safe_action"]
    assert run(case)["already_finalized"]
    assert s.inventory(case.root / "finalization") == sealed
    assert len(case.calls) == 3
    assert c.primary_status(case.root)["next_safe_action"].startswith("primary_frozen")


def test_final_journal_hash_binds_bytes_not_only_parsed_events(case):
    prepare(case)
    run(case)
    finalize(case)
    journal = case.root / "journal.jsonl"
    journal.write_bytes(b" " + journal.read_bytes())
    assert s.load_journal(case.root, case.root.name)  # same parsed events and chain
    with pytest.raises(s.PrimaryRunError, match="journal prefix changed"):
        c.primary_status(case.root)
