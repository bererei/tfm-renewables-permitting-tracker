"""Read-only system, freeze and document-universe gates."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from evaluation.final_holdout_v1.contract import FROZEN_UV_LOCK_SHA256
from evaluation.final_holdout_v2.contract import load_truth
from evaluation.final_holdout_v2.evaluator_freeze import validate_evaluator
from evaluation.primary_execution.storage import PrimaryRunError, file_hash, parse_json


HARNESS_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("worker.py").resolve()


@dataclass(frozen=True)
class UniverseProtocol:
    document_count: int = 48
    holdout_identity: str = "4e71f86cbaf23ba2d26c97fbd5a65b2acb0ccc7cd41616b626ec603f4f4fab4a"
    source_identity: str = "1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf"
    subset_identity: str = "c22187d73cfae19c078b29171bb5f757906a9a9ff9c1bea40e220d3738c2d2de"


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise PrimaryRunError("Git verification failed.") from error


def child_environment() -> dict[str, str]:
    if os.environ.get("PYTHONPATH"):
        raise PrimaryRunError("Unset PYTHONPATH before using the primary controller.")
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV"}
           and not key.startswith("UV_")}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", UV_OFFLINE="1",
               UV_PYTHON_DOWNLOADS="never")
    return env


def require_api_key() -> None:
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        raise PrimaryRunError("GOOGLE_API_KEY or GEMINI_API_KEY is required; no document started.")


def harness_identity() -> dict:
    if git(HARNESS_ROOT, "status", "--porcelain", "--untracked-files=all"):
        raise PrimaryRunError("Commit/review the controller before preparing a real run.")
    return {"commit": git(HARNESS_ROOT, "rev-parse", "HEAD"),
            "files_sha256": {p.name: file_hash(p) for p in sorted(WORKER.parent.glob("*.py"))}}


def verify_system(root: Path, expected_commit: str, expected_config: str) -> dict:
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise PrimaryRunError("system-root must exist and be a regular Git worktree.")
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise PrimaryRunError("system-root is not the worktree root.")
    if git(root, "rev-parse", "HEAD") != expected_commit:
        raise PrimaryRunError("System HEAD differs from the expected frozen commit.")
    if git(root, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD":
        raise PrimaryRunError("The system worktree must be detached.")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise PrimaryRunError("System working tree is dirty.")
    if file_hash(root / "uv.lock") != FROZEN_UV_LOCK_SHA256:
        raise PrimaryRunError("System lockfile differs from the frozen lockfile.")
    if (root / ".venv").is_symlink() or not (root / ".venv").is_dir():
        raise PrimaryRunError("The system requires its own regular .venv directory.")
    python = root / ".venv/bin/python"
    if not python.is_file():
        raise PrimaryRunError("Create the system's own locked .venv first.")
    env = child_environment()
    try:
        subprocess.run(["uv", "sync", "--check", "--locked", "--offline",
                        "--no-python-downloads", "--python", str(python)],
                       cwd=root, env=env, check=True, capture_output=True)
        checked = subprocess.run([str(python), "-I", "-B", str(WORKER), "probe",
                                  "--system-root", str(root), "--expected-config-id", expected_config,
                                  "--expected-system-commit", expected_commit],
                                 cwd=root, env=env, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise PrimaryRunError("Locked environment/import verification failed; no model called.") from error
    probe = parse_json(checked.stdout)
    if (probe["extraction_config_id"] != expected_config or not probe["python_version"].startswith("3.10.")
            or Path(probe["sys_prefix"]).resolve() != (root / ".venv").resolve()
            or not probe["module_origins"]
            or any(not name.startswith("src/renewables_permitting/")
                   or ".." in Path(name).parts for name in probe["module_origins"].values())):
        raise PrimaryRunError("System interpreter/module probe is inconsistent.")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise PrimaryRunError("Environment verification changed the system worktree.")
    return {"commit": expected_commit, "detached": True, "clean": True,
            "pythonpath_absent": True, "lock_environment_checked": True,
            "uv_lock_sha256": file_hash(root / "uv.lock"), **probe}


def verify_inputs(*, truth_dir: Path, evaluator_dir: Path, source: Path,
                  expected_truth_id: str, expected_truth_manifest: str,
                  expected_evaluator_id: str, expected_evaluator_manifest: str,
                  protocol: UniverseProtocol = UniverseProtocol()) -> tuple[object, dict, list[dict]]:
    import pandas as pd
    from renewables_permitting.pipeline import load_documents_input, apply_document_scopes, _documents_identity

    truth = load_truth(truth_dir, require_frozen=True,
                       expected_manifest_sha256=expected_truth_manifest)
    if truth.truth_artifact_id != expected_truth_id:
        raise PrimaryRunError("Unexpected frozen truth identity.")
    evaluator = validate_evaluator(evaluator_dir, expected_evaluator_identity=expected_evaluator_id,
                                   expected_manifest_sha256=expected_evaluator_manifest)
    expected_binding = {"truth_artifact_id": expected_truth_id,
                        "truth_manifest_sha256": expected_truth_manifest,
                        "holdout_artifact_identity": protocol.holdout_identity,
                        "source_snapshot_identity": protocol.source_identity}
    if truth.holdout_artifact_identity != protocol.holdout_identity or truth.source_snapshot_identity != protocol.source_identity:
        raise PrimaryRunError("Truth metadata differs from primary selection/source protocol.")
    if evaluator["truth_binding"] != expected_binding:
        raise PrimaryRunError("Evaluator is not bound to this truth/selection/source.")
    selection_path = truth_dir / "holdout_selection.csv"
    if file_hash(selection_path) != protocol.holdout_identity:
        raise PrimaryRunError("Frozen selection differs from primary protocol.")
    documents = load_documents_input(source)
    if _documents_identity(documents) != protocol.source_identity:
        raise PrimaryRunError("Full source identity mismatch.")
    scoped, _ = apply_document_scopes(documents, [selection_path])
    selection = pd.read_csv(selection_path, dtype="string")
    expected = truth.tables["documents"].set_index("identificador_boe")["source_document_sha256"].to_dict()
    actual = scoped.set_index("identificador")["source_document_sha256"].to_dict()
    selected = selection.set_index("identificador_boe")["source_document_sha256"].to_dict()
    if (len(scoped) != protocol.document_count or len(selection) != protocol.document_count
            or len(expected) != protocol.document_count or actual != expected or actual != selected
            or _documents_identity(scoped) != protocol.subset_identity):
        raise PrimaryRunError("Primary universe has missing/extra/duplicate/different documents.")
    return truth, evaluator, [
        {"ordinal": i, "boe_id": boe, "source_document_sha256": actual[boe],
         "output": f"documents/{i:03d}-{boe}"}
        for i, boe in enumerate(sorted(actual), 1)]
