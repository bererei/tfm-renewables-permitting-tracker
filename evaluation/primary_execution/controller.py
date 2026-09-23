"""Durable orchestration around an unchanged, independently checked extractor."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pandas as pd

from evaluation.final_holdout_v2.predictions import (
    load_prediction_snapshot, validate_primary_predictions, validate_execution_record,
)
from evaluation.primary_execution import verification as gates
from evaluation.primary_execution.storage import (
    PrimaryRunError, append_event, canonical, digest, durable_json, file_hash,
    fsync_directory, inventory, load_journal, publish_directory, read_json,
    utc_now, writer_active, writer_lock,
)

USAGE_LIMITATION = (
    "model_usage is reported PydanticAI/product usage, unchanged. Failed HTTP calls "
    "may be absent from RunUsage.requests/tokens. Document starts are not HTTP calls. "
    "No provider instrumentation, estimation or extra model retry is performed."
)
TERMINAL = {"TERMINAL_SUCCESS", "TERMINAL_ERROR"}


def _input_checks(meta):
    values = meta["inputs"]
    return gates.verify_inputs(
        truth_dir=Path(values["truth_dir"]), evaluator_dir=Path(values["evaluator_dir"]),
        source=Path(values["source"]), **meta["expectations"],
        protocol=gates.UniverseProtocol(**meta["universe_protocol"]))


def _reverify(meta):
    system = gates.verify_system(Path(meta["system_root"]), meta["system"]["commit"],
                                 meta["system"]["extraction_config_id"])
    if system != meta["system"] or gates.harness_identity() != meta["harness"]:
        raise PrimaryRunError("System environment or harness changed since preparation.")
    truth, evaluator, documents = _input_checks(meta)
    if documents != meta["documents"]:
        raise PrimaryRunError("Registered document universe changed.")
    return truth


def prepare_primary_run(*, system_root: Path, truth_dir: Path, evaluator_dir: Path,
                        source: Path, run_root: Path, expected_system_commit: str,
                        expected_config_id: str, expected_truth_id: str,
                        expected_truth_manifest: str, expected_evaluator_id: str,
                        expected_evaluator_manifest: str, argv: list[str],
                        protocol=gates.UniverseProtocol()) -> dict:
    run_root = Path(run_root).absolute()
    if run_root.exists() or run_root.is_symlink():
        raise PrimaryRunError("Run output already exists.")
    protected = [Path(p).resolve() for p in (system_root, truth_dir, evaluator_dir, source)]
    if any(run_root.resolve().is_relative_to(p) or p.is_relative_to(run_root.resolve()) for p in protected):
        raise PrimaryRunError("Run output overlaps a protected input/system.")
    system = gates.verify_system(system_root, expected_system_commit, expected_config_id)
    expectations = {"expected_truth_id": expected_truth_id, "expected_truth_manifest": expected_truth_manifest,
                    "expected_evaluator_id": expected_evaluator_id, "expected_evaluator_manifest": expected_evaluator_manifest}
    truth, evaluator, documents = gates.verify_inputs(
        truth_dir=truth_dir, evaluator_dir=evaluator_dir, source=source,
        **expectations, protocol=protocol)
    # Registries are frozen production inputs; no holdout-specific human decisions.
    registries = {}
    for relative in ("config/corrections/administrative_action_corrections.csv",
                     "config/manual_reviews/historical_antecedent_reviews.csv"):
        path = Path(system_root) / relative
        frame = pd.read_csv(path, dtype="string")
        if "boe_id" not in frame or set(frame["boe_id"].dropna()) & {d["boe_id"] for d in documents}:
            raise PrimaryRunError("Productive registry targets a primary document or lacks BOE identity.")
        registries[relative] = file_hash(path)
    meta = {"version": 1, "run_id": run_root.name, "prepared_at_utc": utc_now(),
            "system_root": str(Path(system_root).resolve()), "system": system,
            "harness": gates.harness_identity(), "expectations": expectations,
            "inputs": {"truth_dir": str(truth_dir.resolve()), "evaluator_dir": str(evaluator_dir.resolve()),
                       "source": str(source.resolve())},
            "universe_protocol": asdict(protocol), "documents": documents,
            "registry_sha256": registries, "prepare_argv": argv,
            "evaluator_created_at_utc": evaluator["created_at_utc"],
            "usage_limitation": USAGE_LIMITATION}
    run_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{run_root.name}.prepare-", dir=run_root.parent))
    # Failed preparations retain forensic staging; they never publish a partial run.
    (stage / ".writer.lock").touch(mode=0o600, exist_ok=False)
    (stage / "documents").mkdir()
    (stage / "scopes").mkdir()
    scopes = {}
    for document in documents:
        name = f"scopes/{document['ordinal']:03d}.csv"
        (stage / name).write_text("identificador_boe\n" + document["boe_id"] + "\n", encoding="utf-8")
        scopes[name] = file_hash(stage / name)
    meta["scope_sha256"] = scopes
    durable_json(stage / "metadata.json", meta)
    append_event(stage, meta["run_id"], "RUN_PREPARED",
                 {"metadata_sha256": file_hash(stage / "metadata.json")}, initial=True)
    publish_directory(stage, run_root)
    return primary_status(run_root)


def _load(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise PrimaryRunError("Run root must be a regular directory.")
    meta = read_json(root / "metadata.json")
    if meta.get("version") != 1:
        raise PrimaryRunError("Unknown primary-run version.")
    events = load_journal(root, meta["run_id"])
    if events[0]["event"] != "RUN_PREPARED" or events[0]["data"] != {
        "metadata_sha256": file_hash(root / "metadata.json")
    }:
        raise PrimaryRunError("Prepared metadata/journal anchor changed.")
    for name, expected in meta["scope_sha256"].items():
        if file_hash(root / name) != expected:
            raise PrimaryRunError("Registered scope changed.")
    if inventory(root / "scopes") != {Path(k).name: v for k, v in meta["scope_sha256"].items()}:
        raise PrimaryRunError("Scope inventory differs from preparation.")
    expected_directories = {Path(d["output"]).name for d in meta["documents"]}
    if (root / "documents").is_symlink() or any(
        p.name not in expected_directories or p.is_symlink() or not p.is_dir()
        for p in (root / "documents").iterdir()
    ):
        raise PrimaryRunError("Unregistered document output.")
    return meta, events


def _receipt(directory: Path, *, expected_operation: str):
    path = directory / "completion.json"
    if not path.exists() and not path.is_symlink():
        return None
    value = read_json(path)
    required = {"version", "operation", "files", "started_at_utc", "ended_at_utc",
                "exit_code", "diagnostic", "job_sha256"}
    if (set(value) != required or value["version"] != 1 or value["operation"] != expected_operation
            or type(value["exit_code"]) is not int or value["exit_code"] not in (0, 4)
            or value["job_sha256"] != file_hash(directory / "job.json")
            or value["started_at_utc"] > value["ended_at_utc"]):
        raise PrimaryRunError("Invalid worker completion receipt.")
    actual = inventory(directory)
    actual.pop("completion.json")
    if actual != value["files"]:
        raise PrimaryRunError("Completed output/log hash mismatch.")
    return value


def _document_result(root, meta, document, truth):
    directory = root / document["output"]
    receipt = _receipt(directory, expected_operation="extract") if directory.exists() else None
    if receipt is None:
        return None
    if read_json(directory / "job.json") != _job(root, meta, document):
        raise PrimaryRunError("Completed document belongs to a different job.")
    snapshot = load_prediction_snapshot(directory / "extraction")
    subset = replace(truth, tables={**truth.tables, "documents": truth.tables["documents"].loc[
        truth.tables["documents"]["identificador_boe"].eq(document["boe_id"])].copy()})
    validate_primary_predictions(snapshot, subset)
    status = snapshot.attempts.iloc[0]["extraction_status"]
    return {"state": "TERMINAL_SUCCESS" if status == "ok" else "TERMINAL_ERROR",
            "completion_sha256": file_hash(directory / "completion.json"),
            "snapshot_identity": snapshot.snapshot_identity, "exit_code": receipt["exit_code"],
            "ended_at_utc": receipt["ended_at_utc"]}


def _states(root, meta, events, *, active=False, truth=None):
    from evaluation.final_holdout_v2.contract import load_truth
    truth = truth or load_truth(Path(meta["inputs"]["truth_dir"]), require_frozen=True,
                               expected_manifest_sha256=meta["expectations"]["expected_truth_manifest"])
    states = {d["boe_id"]: {"state": "PENDING"} for d in meta["documents"]}
    by_boe = {d["boe_id"]: d for d in meta["documents"]}
    finalized = False
    for event in events[1:]:
        name, data = event["event"], event["data"]
        if finalized or name == "RUN_PREPARED":
            raise PrimaryRunError("Illegal event after finalization/repeated preparation.")
        if name.startswith("DOCUMENT_"):
            boe = data.get("boe_id")
            if boe not in by_boe or any(data.get(k) != v for k, v in by_boe[boe].items()):
                raise PrimaryRunError("Journal document identity differs.")
            prior = states[boe]["state"]
            if name == "DOCUMENT_STARTED":
                if (prior != "PENDING" or data.get("state") != "STARTED"
                        or set(data) != set(by_boe[boe]) | {"state", "job_sha256"}):
                    raise PrimaryRunError("Document may only start once.")
                if any(s["state"] in {"STARTED", "INDETERMINATE"} for s in states.values()) or boe != next(
                    key for key, value in states.items() if value["state"] == "PENDING"
                ):
                    raise PrimaryRunError("Document starts must follow the registered sequential order.")
                if file_hash(root / data["output"] / "job.json") != data.get("job_sha256"):
                    raise PrimaryRunError("Started job changed.")
                states[boe] = {"state": "STARTED"}
            else:
                if prior != "STARTED":
                    raise PrimaryRunError("Terminal event requires a single STARTED event.")
                result = _document_result(root, meta, by_boe[boe], truth)
                expected_state = "TERMINAL_SUCCESS" if name == "DOCUMENT_COMPLETED" else "TERMINAL_ERROR"
                if (result is None or result["state"] != expected_state
                        or set(data) != set(by_boe[boe]) | set(result)
                        or any(data.get(k) != v for k, v in result.items())):
                    raise PrimaryRunError("Terminal event has no matching durable output.")
                states[boe] = result
        elif name == "RUN_INVOKED":
            if set(data) != {"argv"} or not isinstance(data["argv"], list) or not data["argv"] or any(
                not isinstance(v, str) or not v for v in data["argv"]
            ):
                raise PrimaryRunError("Malformed run invocation.")
        elif name == "INCIDENT" and data.get("state") == "INDETERMINATE":
            boe = data.get("boe_id")
            if (boe not in states or states[boe]["state"] != "STARTED"
                    or any(data.get(k) != v for k, v in by_boe[boe].items())
                    or not isinstance(data.get("diagnostic"), str)):
                raise PrimaryRunError("Illegal INDETERMINATE transition.")
            states[boe] = {"state": "INDETERMINATE"}
        elif name == "INCIDENT":
            raise PrimaryRunError("Malformed incident.")
        elif name == "RUN_INTERRUPTED":
            if (set(data) != {"boe_id", "diagnostic"} or not isinstance(data["diagnostic"], str)
                    or (data["boe_id"] is not None and data["boe_id"] not in states)):
                raise PrimaryRunError("Malformed interruption.")
        elif name in {"RUN_EXECUTION_COMPLETED", "RUN_FINALIZED"}:
            if any(s["state"] not in TERMINAL for s in states.values()):
                raise PrimaryRunError("Run completed/finalized with nonterminal documents.")
            finalized = name == "RUN_FINALIZED"
            if name == "RUN_EXECUTION_COMPLETED" and (data != {"exit_code": 0} or type(data["exit_code"]) is not int):
                raise PrimaryRunError("Malformed controller completion.")
    for document in meta["documents"]:
        boe = document["boe_id"]
        directory = root / document["output"]
        state = states[boe]["state"]
        if directory.is_symlink():
            raise PrimaryRunError("Document directory cannot be a symlink.")
        if state == "PENDING" and directory.exists():
            files = set(inventory(directory))
            if files not in (set(), {"job.json"}) or (
                files and read_json(directory / "job.json") != _job(root, meta, document)
            ):
                raise PrimaryRunError("Unregistered output exists for a PENDING document.")
        if state == "STARTED":
            result = _document_result(root, meta, document, truth)
            states[boe] = ({**result, "recovered": True} if result else
                           {"state": "STARTED" if active else "INDETERMINATE"})
    if (root / "primary").exists() and any(v["state"] not in TERMINAL for v in states.values()):
        raise PrimaryRunError("Primary output exists with nonterminal documents.")
    return states


def primary_status(run_root: Path) -> dict:
    root = Path(run_root)
    active = writer_active(root)
    meta, events = _load(root)
    states = _states(root, meta, events, active=active)
    counts = {name: sum(s["state"] == name for s in states.values()) for name in
              ("PENDING", "STARTED", "TERMINAL_SUCCESS", "TERMINAL_ERROR", "INDETERMINATE")}
    action = ("wait_for_active_controller" if active else "human_decision_required" if counts["INDETERMINATE"]
              else "run-primary" if counts["PENDING"] else "finalize-primary")
    if events[-1]["event"] == "RUN_FINALIZED" or (root / "finalization").exists():
        _verify_final(root, meta, events)
        action = ("primary_frozen; evaluation_is_a_separate_gate" if events[-1]["event"] == "RUN_FINALIZED"
                  else "finalize-primary; recover_final_journal_event")
    return {"run_id": meta["run_id"], "active_writer": active, "counts": counts,
            "documents": states, "next_safe_action": action}


def _job(root, meta, document):
    directory = root / document["output"]
    args = ["extract", "--documents", meta["inputs"]["source"], "--scope",
            str(root / f"scopes/{document['ordinal']:03d}.csv"), "--output-dir", str(directory / "extraction"),
            "--expected-extraction-config-id", meta["system"]["extraction_config_id"], "--execute-model"]
    return {"operation": "extract", "expected_config_id": meta["system"]["extraction_config_id"],
            "pipeline_argv": args, **document}


def run_worker(meta, directory, *, lock_fd):
    system_root = Path(meta["system_root"])
    command = [str(system_root / ".venv/bin/python"), "-I", "-B", str(gates.WORKER), "job",
               "--system-root", str(system_root), "--expected-config-id", meta["system"]["extraction_config_id"],
               "--expected-system-commit", meta["system"]["commit"],
               "--job", str(directory / "job.json")]
    with (directory / "launcher.stdout.log").open("xb") as out, (directory / "launcher.stderr.log").open("xb") as err:
        child = subprocess.Popen(command, cwd=system_root, env=gates.child_environment(),
                                 stdout=out, stderr=err, start_new_session=True, pass_fds=(lock_fd,))
        try:
            code = child.wait()
        except BaseException:
            # The child inherits the advisory lock, including after a parent crash.
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            child.wait()
            raise
        finally:
            out.flush()
            err.flush()
            os.fsync(out.fileno())
            os.fsync(err.fileno())
    return code


def _noop(point, document=None):
    pass


def _recover(root, meta, events, truth):
    states = _states(root, meta, events, truth=truth)
    for document in meta["documents"]:
        result = states[document["boe_id"]]
        if result.get("recovered"):
            data = {k: v for k, v in result.items() if k != "recovered"}
            append_event(root, meta["run_id"], "DOCUMENT_COMPLETED" if result["state"] == "TERMINAL_SUCCESS"
                         else "DOCUMENT_ERROR", {**document, **data})
        if result["state"] == "INDETERMINATE":
            already = any(e["event"] == "INCIDENT" and e["data"].get("boe_id") == document["boe_id"]
                          and e["data"].get("state") == "INDETERMINATE" for e in events)
            if not already:
                append_event(root, meta["run_id"], "INCIDENT", {**document, "state": "INDETERMINATE",
                             "diagnostic": "STARTED without a verifiable durable completion; no retry permitted."})
            raise PrimaryRunError("INDETERMINATE document: explicit later human decision required.")
    return states


def run_primary(run_root: Path, *, argv: list[str], runner=run_worker, hook=_noop) -> dict:
    root = Path(run_root).absolute()
    with writer_lock(root) as lock_fd:
        meta, events = _load(root)
        truth = _reverify(meta)
        if events[-1]["event"] == "RUN_FINALIZED" or (root / "finalization").exists():
            _verify_final(root, meta, events)
            if events[-1]["event"] != "RUN_FINALIZED":
                append_event(root, meta["run_id"], "RUN_FINALIZED", {
                    "final_manifest_sha256": file_hash(root / "finalization/manifest.json")})
            return {"run_id": meta["run_id"], "already_finalized": True}
        states = _recover(root, meta, events, truth)
        if any(s["state"] == "PENDING" for s in states.values()):
            gates.require_api_key()  # before any DOCUMENT_STARTED
        append_event(root, meta["run_id"], "RUN_INVOKED", {"argv": argv})
        active_document = None
        try:
            for document in meta["documents"]:
                if states[document["boe_id"]]["state"] in TERMINAL:
                    continue
                active_document = document
                hook("before_started", document)
                directory = root / document["output"]
                if not directory.exists():
                    directory.mkdir()
                    fsync_directory(directory.parent)
                if not (directory / "job.json").exists():
                    durable_json(directory / "job.json", _job(root, meta, document))
                append_event(root, meta["run_id"], "DOCUMENT_STARTED", {
                    **document, "state": "STARTED", "job_sha256": file_hash(directory / "job.json")})
                hook("after_started", document)
                code = runner(meta, directory, lock_fd=lock_fd)
                hook("after_runner", document)
                result = _document_result(root, meta, document, truth)
                if result is None or result["exit_code"] != code:
                    append_event(root, meta["run_id"], "INCIDENT", {
                        **document, "state": "INDETERMINATE", "exit_code": code,
                        "diagnostic": "Worker ended without a matching durable terminal receipt."})
                    raise PrimaryRunError("Worker result is indeterminate; no automatic retry.")
                append_event(root, meta["run_id"], "DOCUMENT_COMPLETED" if result["state"] == "TERMINAL_SUCCESS"
                             else "DOCUMENT_ERROR", {**document, **result})
                hook("after_terminal", document)
                active_document = None
            append_event(root, meta["run_id"], "RUN_EXECUTION_COMPLETED", {"exit_code": 0})
        except BaseException as error:
            append_event(root, meta["run_id"], "RUN_INTERRUPTED", {
                "boe_id": active_document["boe_id"] if active_document else None,
                "diagnostic": type(error).__name__})
            raise
    return primary_status(root)


def semantic_snapshot_identity(snapshot) -> str:
    """Relational content identity; exclude only the regenerated queue timestamp.

    Native V2 snapshot IDs additionally include physical Parquet hashes. No stored
    payload or queue value is rewritten to compute this operational audit identity.
    """
    tables = {}
    for name in ("documents", "attempts", "manual_reviews", "current_extractions", "review_queue",
                 "historical_corrections", "historical_reviews"):
        frame = getattr(snapshot, name)
        columns = [c for c in frame if not (name == "review_queue" and c == "queued_at")]
        rows = []
        for record in frame[columns].to_dict(orient="records"):
            rows.append({k: None if pd.isna(v) else v.isoformat() if hasattr(v, "isoformat")
                         else v.item() if hasattr(v, "item") else v for k, v in record.items()})
        tables[name] = {"columns": columns, "rows": sorted(rows, key=lambda r: canonical(r))}
    return digest(tables)


def _verify_final(root, meta, events):
    _states(root, meta, events)
    directory = root / "finalization"
    seal = read_json(directory / "manifest.json")
    files = inventory(directory)
    files.pop("manifest.json")
    if seal != {"files_sha256": files, "primary_files_sha256": inventory(root / "primary")}:
        raise PrimaryRunError("Final primary publication changed.")
    provenance = read_json(directory / "provenance.json")
    suffix = events[provenance["journal_event_count"]:]
    if len(suffix) > 1 or (suffix and suffix[0]["event"] != "RUN_FINALIZED"):
        raise PrimaryRunError("Unexpected journal events after the final provenance prefix.")
    prefix = b"".join((root / "journal.jsonl").read_bytes().splitlines(keepends=True)[:provenance["journal_event_count"]])
    if sha256(prefix).hexdigest() != provenance["journal_sha256"]:
        raise PrimaryRunError("Final journal prefix changed.")
    if events[-1]["event"] == "RUN_FINALIZED" and events[-1]["data"] != {
        "final_manifest_sha256": file_hash(directory / "manifest.json")
    }:
        raise PrimaryRunError("Final journal seal mismatch.")
    return provenance


def finalize_primary(run_root: Path, *, argv: list[str], runner=run_worker, hook=_noop) -> dict:
    root = Path(run_root).absolute()
    with writer_lock(root) as lock_fd:
        meta, events = _load(root)
        truth = _reverify(meta)
        if (root / "finalization").exists():
            provenance = _verify_final(root, meta, events)
            if events[-1]["event"] != "RUN_FINALIZED":
                append_event(root, meta["run_id"], "RUN_FINALIZED", {
                    "final_manifest_sha256": file_hash(root / "finalization/manifest.json")})
            return provenance
        states = _recover(root, meta, events, truth)
        if any(s["state"] not in TERMINAL for s in states.values()):
            raise PrimaryRunError("Finalize requires every registered document to be terminal.")
        events = load_journal(root, meta["run_id"])
        finished = [e for e in events if e["event"] == "RUN_EXECUTION_COMPLETED"]
        invocations = [e for e in events if e["event"] == "RUN_INVOKED"]
        if not finished or not invocations:
            raise PrimaryRunError("Complete run-primary recovery before finalization.")
        primary = root / "primary"
        job = {"operation": "aggregate", "expected_config_id": meta["system"]["extraction_config_id"],
               "source": meta["inputs"]["source"], "scope": str(Path(meta["inputs"]["truth_dir"]) / "holdout_selection.csv"),
               "parents": [str(root / d["output"] / "extraction") for d in meta["documents"]],
               "boe_ids": [d["boe_id"] for d in meta["documents"]]}
        if not primary.exists():
            stage = Path(tempfile.mkdtemp(prefix=".aggregate-", dir=root))
            durable_json(stage / "job.json", job)
            code = runner(meta, stage, lock_fd=lock_fd)  # operation=aggregate cannot call a model
            receipt = _receipt(stage, expected_operation="aggregate")
            if receipt is None or code != receipt["exit_code"]:
                raise PrimaryRunError("Offline aggregation failed; original documents retained.")
            candidate = load_prediction_snapshot(stage / "extraction")
            validate_primary_predictions(candidate, truth)
            publish_directory(stage, primary)
            hook("after_primary_publication")
        receipt = _receipt(primary, expected_operation="aggregate")
        if receipt is None or read_json(primary / "job.json") != job:
            raise PrimaryRunError("Unrecognized existing primary publication.")
        snapshot = load_prediction_snapshot(primary / "extraction")
        validate_primary_predictions(snapshot, truth)
        original = {}
        for document in meta["documents"]:
            parent = load_prediction_snapshot(root / document["output"] / "extraction")
            for record in parent.attempts.to_dict(orient="records"):
                original[record["attempt_id"]] = record
        actual = snapshot.attempts.set_index("attempt_id", drop=False).sort_index()
        expected = pd.DataFrame(list(original.values())).set_index("attempt_id", drop=False).sort_index()
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False)
        usage = {}
        for label in ("requests", "input_tokens", "output_tokens", "total_tokens"):
            values = pd.to_numeric(snapshot.attempts[f"usage_{label}"], errors="raise")
            if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
                raise PrimaryRunError("Reported usage is missing/invalid; do not estimate it.")
            usage[label] = int(values.sum())
        frozen_at = utc_now()  # only after a verified primary snapshot has been published
        starts = [e for e in events if e["event"] == "DOCUMENT_STARTED"]
        model_attempts = int(snapshot.attempts["attempt_origin"].eq("model").sum())
        provenance = {"version": 1, "run_id": meta["run_id"], "system": meta["system"],
                      "system_root": meta["system_root"], "harness": meta["harness"],
                      "freeze_expectations": meta["expectations"], "universe": meta["universe_protocol"],
                      "prepared_metadata_sha256": file_hash(root / "metadata.json"),
                      "run_invocations": invocations, "finalize_argv": argv,
                      "started_at_utc": starts[0]["timestamp_utc"],
                      "ended_at_utc": finished[-1]["timestamp_utc"],
                      "primary_predictions_frozen_at_utc": frozen_at,
                      "journal_event_count": len(events), "journal_sha256": file_hash(root / "journal.jsonl"),
                      "subruns": [{**d, **states[d["boe_id"]]} for d in meta["documents"]],
                      "incidents": [e for e in events if e["event"] in {"INCIDENT", "RUN_INTERRUPTED"}],
                      "reported_model_usage": usage, "document_executions_started": len(starts),
                      "usage_limitation": USAGE_LIMITATION,
                      "frozen_evaluator_usage_guard_satisfied": usage["requests"] >= model_attempts,
                      "manual_intervention_before_primary_freeze": False,
                      "prediction_snapshot_identity": snapshot.snapshot_identity,
                      "primary_semantic_identity": semantic_snapshot_identity(snapshot)}
        stage = Path(tempfile.mkdtemp(prefix=".finalization-", dir=root))
        durable_json(stage / "provenance.json", provenance)
        record = {"record_version": "final_holdout_execution_record_v1", "run_id": meta["run_id"],
                  "started_at_utc": provenance["started_at_utc"], "ended_at_utc": provenance["ended_at_utc"],
                  "exact_command": invocations[0]["data"]["argv"], "exit_code": finished[-1]["data"]["exit_code"],
                  "frozen_production_git_commit": meta["system"]["commit"],
                  "extraction_config_id": meta["system"]["extraction_config_id"],
                  "model_provider": meta["system"]["model_provider"], "model_name": meta["system"]["model_name"],
                  "source_snapshot_identity": meta["universe_protocol"]["source_identity"],
                  "holdout_artifact_identity": meta["universe_protocol"]["holdout_identity"],
                  "extraction_output_identity": snapshot.snapshot_identity,
                  "stdout_log_path": "primary/stdout.log", "stderr_log_path": "primary/stderr.log",
                  "python_version": meta["system"]["python_version"], "uv_lock_sha256": meta["system"]["uv_lock_sha256"],
                  "model_usage": usage, "incident_retry_notes": USAGE_LIMITATION +
                  " Operational provenance (relative to run root): finalization/provenance.json; SHA-256=" +
                  file_hash(stage / "provenance.json") + ". Per-document logs and process exit codes are sealed there.",
                  "manual_intervention_before_primary_freeze": False,
                  "primary_predictions_frozen_at_utc": frozen_at}
        durable_json(stage / "execution_record.json", record)
        validate_execution_record(stage / "execution_record.json", snapshot_identity=snapshot.snapshot_identity, truth=truth)
        durable_json(stage / "manifest.json", {"files_sha256": inventory(stage),
                                               "primary_files_sha256": inventory(primary)})
        publish_directory(stage, root / "finalization")
        hook("after_finalization_publication")
        append_event(root, meta["run_id"], "RUN_FINALIZED", {
            "final_manifest_sha256": file_hash(root / "finalization/manifest.json")})
        return provenance
