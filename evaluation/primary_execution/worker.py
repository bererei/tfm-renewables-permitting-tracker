"""Standalone child entry point: run with the verified system's Python -I.

Only stdlib is imported before checking module origins. No evaluation code or
provider instrumentation is injected into the frozen production package.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


def verify_git(root: Path, expected_commit: str) -> None:
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    if (Path(git("rev-parse", "--show-toplevel")).resolve() != root.resolve()
            or git("rev-parse", "HEAD") != expected_commit
            or git("rev-parse", "--abbrev-ref", "HEAD") != "HEAD"
            or git("status", "--porcelain", "--untracked-files=all")):
        raise ValueError("Frozen worker checkout is not the expected clean detached system.")


def probe(system_root: Path, expected_config: str) -> dict:
    import renewables_permitting.pipeline as pipeline
    from renewables_permitting.extraction import config

    root = system_root.resolve()
    if (root / ".venv").is_symlink() or Path(sys.prefix).resolve() != (root / ".venv").resolve():
        raise ValueError("Interpreter does not belong to the system environment.")
    if config.EXTRACTION_CONFIG_ID != expected_config:
        raise ValueError("Effective extraction configuration differs.")
    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name == "renewables_permitting" or name.startswith("renewables_permitting."):
            origin = getattr(module, "__file__", None)
            if not origin or not Path(origin).resolve().is_relative_to(root / "src"):
                raise ValueError("Productive module loaded outside system-root/src.")
            origins[name] = Path(origin).resolve().relative_to(root).as_posix()
    settings = {key: getattr(config, key) for key in (
        "AGENT_RETRIES", "MODEL_SETTINGS", "DOCUMENT_TIMEOUT_SECONDS",
        "MODEL_RUN_TIMEOUT_SECONDS", "MAX_MODEL_REQUESTS_PER_DOCUMENT",
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS", "TRANSIENT_RUN_ATTEMPTS",
        "TRANSIENT_RETRY_BASE_SECONDS", "CHECKPOINT_EVERY", "USE_NATIVE_OUTPUT")}
    from renewables_permitting.extraction.documents import MAX_DOCUMENT_CHARS
    settings["MAX_DOCUMENT_CHARS"] = MAX_DOCUMENT_CHARS
    return {"python_version": platform.python_version(), "sys_prefix": str(Path(sys.prefix)),
            "module_origins": origins, "extraction_config_id": config.EXTRACTION_CONFIG_ID,
            "model_provider": config.MODEL_PROVIDER, "model_name": config.AI_MODEL_NAME,
            "extraction_config": config.EXTRACTION_CONFIG, "operational_settings": settings,
            "packages": {name: importlib.metadata.version(name) for name in (
                "pydantic-ai", "google-genai", "pydantic", "pandas", "pyarrow")}}


def aggregate(job: dict, output: Path) -> int:
    """Use frozen combination and standard publication, including terminal errors."""
    import pandas as pd
    from renewables_permitting import pipeline
    from renewables_permitting.extraction.persistence import save_parquet_atomic
    from renewables_permitting.extraction.review import (
        combine_ai_extraction_attempt_frames, empty_ai_extraction_attempts_log,
    )

    attempts = empty_ai_extraction_attempts_log()
    seen = set()
    for parent in job["parents"]:  # supplied in the registered BOE order
        loaded = pipeline.load_extraction_snapshot(
            Path(parent), expected_extraction_config_id=job["expected_config_id"])
        ids = loaded.attempts["identificador_boe"].astype(str)
        if len(ids) != 1 or seen.intersection(ids):
            raise ValueError("Aggregate parent overlap/granularity mismatch.")
        seen.update(ids)
        attempts = combine_ai_extraction_attempt_frames(attempts, loaded.attempts)
    if attempts["attempt_id"].duplicated().any() or set(seen) != set(job["boe_ids"]):
        raise ValueError("Aggregate attempt/document identities differ.")
    attempts = attempts.sort_values("identificador_boe", kind="stable").reset_index(drop=True)
    combined = output.parent / "combined_attempts.parquet"
    if combined.exists():
        raise FileExistsError("Intermediate aggregate already exists.")
    save_parquet_atomic(attempts, combined)
    result = pipeline.run_extraction_stage(
        documents=Path(job["source"]), scope_paths=[Path(job["scope"])],
        attempts=combined, output_dir=output,
        expected_extraction_config_id=job["expected_config_id"], execute_model=False)
    loaded = pipeline.load_extraction_snapshot(
        output, expected_extraction_config_id=job["expected_config_id"])
    # Verify all original columns/values, including payloads and every error.
    pd.testing.assert_frame_equal(
        attempts, loaded.attempts.sort_values("identificador_boe").reset_index(drop=True),
        check_dtype=False)
    combined.unlink()
    return 4 if result.blocking_review_count else 0


def execute_job(job: dict, directory: Path, *, clock=None, publish_hook=None) -> int:
    """Receipt is the durable commit point; unsealed results remain indeterminate.

    Tests replace only the productive runner/clock. Production calls the unchanged
    CLI main or the unchanged offline publication API above.
    """
    # This file is also importable by synthetic tests; filesystem helpers remain
    # external to production. In the isolated child, load this exact sibling file.
    import importlib.util
    spec = importlib.util.spec_from_file_location("primary_worker_storage", Path(__file__).with_name("storage.py"))
    storage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(storage)
    now = clock or storage.utc_now
    started = now()
    output = directory / "extraction"
    exit_code = 1
    diagnostic = None
    with (directory / "stdout.log").open("xb") as out, (directory / "stderr.log").open("xb") as err:
        # Text redirection records production diagnostics without storing env/secrets.
        import io
        stdout = io.TextIOWrapper(out, encoding="utf-8", write_through=True)
        stderr = io.TextIOWrapper(err, encoding="utf-8", write_through=True)
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                if job["operation"] == "extract":
                    from renewables_permitting import pipeline
                    exit_code = pipeline.main(job["pipeline_argv"])
                elif job["operation"] == "aggregate":
                    exit_code = aggregate(job, output)
                else:
                    raise ValueError("Unknown worker operation.")
        except SystemExit as error:
            exit_code = error.code if type(error.code) is int else 1
            diagnostic = "SystemExit"
        except BaseException as error:
            exit_code = 130 if isinstance(error, KeyboardInterrupt) else 1
            diagnostic = type(error).__name__
        finally:
            stdout.flush()
            stderr.flush()
            os.fsync(out.fileno())
            os.fsync(err.fileno())
            stdout.detach()
            stderr.detach()
    process = {"started_at_utc": started, "ended_at_utc": now(),
               "exit_code": exit_code, "diagnostic": diagnostic,
               "job_sha256": storage.file_hash(directory / "job.json")}
    storage.durable_json(directory / "process.json", process)
    if exit_code not in (0, 4) or not output.is_dir():
        return exit_code if exit_code not in (0, 4) else 1
    from renewables_permitting.pipeline import load_extraction_snapshot
    load_extraction_snapshot(output, expected_extraction_config_id=job["expected_config_id"])
    files = storage.inventory(directory)
    storage.fsync_tree(directory)
    if publish_hook:
        publish_hook("before_receipt")
    storage.durable_json(directory / "completion.json", {
        "version": 1, "operation": job["operation"], "files": files, **process})
    if publish_hook:
        publish_hook("after_receipt")
    return exit_code


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("probe", "job"))
    parser.add_argument("--system-root", type=Path, required=True)
    parser.add_argument("--expected-config-id", required=True)
    parser.add_argument("--expected-system-commit", required=True)
    parser.add_argument("--job", type=Path)
    args = parser.parse_args(argv)
    verify_git(args.system_root, args.expected_system_commit)
    result = probe(args.system_root, args.expected_config_id)
    if args.operation == "probe":
        print(json.dumps(result, sort_keys=True))
        return 0
    job = json.loads(args.job.read_text())
    if job["expected_config_id"] != args.expected_config_id:
        raise ValueError("Worker job config mismatch.")
    if job["operation"] == "extract" and not (
        os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    ):
        raise ValueError("Missing productive API key.")
    return execute_job(job, args.job.parent)


if __name__ == "__main__":
    raise SystemExit(main())
