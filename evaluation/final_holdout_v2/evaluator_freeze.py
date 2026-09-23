"""Freeze and verify V2-B code/rules before any primary extraction is run."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from evaluation.final_holdout_v2.artifacts import identity, inventory, new_artifact, utc_now, write_json
from evaluation.final_holdout_v2.contract import (
    CONTRACT_DECLARATION_PATH, CONTRACT_VERSION, FROZEN_PRODUCTION_COMMIT,
    load_truth, sha256_file,
)
from evaluation.final_holdout_v2.predictions import EvaluationError


EVALUATOR_VERSION = "final_holdout_evaluator_v2_b_1"
FREEZE_VERSION = "final_holdout_evaluator_freeze_v2_1"
RULES_PATH = Path(__file__).with_name("scoring_rules.json")
REPO_ROOT = Path(__file__).resolve().parents[2]


def evaluator_declaration(*, repo_root: Path = REPO_ROOT) -> dict:
    """Relative source digests, no Git state, timestamps, input data or paths.

    Includes the isolated evaluation packages and production Python sources
    (transitive imports and the Gold projection reference), plus runtime lock.
    Templates/annotation declarations are included without reading runs/.
    """
    root = Path(repo_root)
    paths = {root / "uv.lock", root / "pyproject.toml", root / "evaluation/__init__.py"}
    for directory in ("evaluation/final_holdout_v1", "evaluation/final_holdout_v2", "src/renewables_permitting"):
        paths.update(p for p in (root / directory).rglob("*") if p.suffix in {".py", ".json", ".csv"} and p.is_file())
    hashes = {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(paths)}
    rules = json.loads((root / "evaluation/final_holdout_v2/scoring_rules.json").read_text(encoding="utf-8"))
    declaration = {
        "evaluator_version": EVALUATOR_VERSION,
        "truth_contract_version": CONTRACT_VERSION,
        "truth_contract_declaration_sha256": sha256_file(root / CONTRACT_DECLARATION_PATH.relative_to(REPO_ROOT)),
        "frozen_production_git_commit": FROZEN_PRODUCTION_COMMIT,
        "scoring_configuration": rules,
        "source_file_sha256": hashes,
    }
    return {**declaration, "evaluator_identity": identity(declaration)}


def _manifest_identity(manifest: dict) -> str:
    return identity({k: v for k, v in manifest.items() if k != "manifest_identity_sha256"})


def validate_evaluator(path: Path, *, expected_evaluator_identity: str | None = None,
                       expected_manifest_sha256: str | None = None) -> dict:
    path = Path(path)
    files = inventory(path)
    if set(files) != {"manifest.json", "scoring_rules.json"}:
        raise EvaluationError("Frozen evaluator inventory mismatch.")
    if expected_manifest_sha256 is not None and files["manifest.json"] != expected_manifest_sha256:
        raise EvaluationError("Frozen evaluator manifest SHA-256 differs from expectation.")
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        declaration = evaluator_declaration()
        required = {"freeze_version", "declaration", "truth_binding", "created_at_utc", "files", "manifest_identity_sha256"}
        if not isinstance(manifest, dict) or set(manifest) != required:
            raise EvaluationError("Frozen evaluator manifest fields mismatch.")
        if manifest["freeze_version"] != FREEZE_VERSION or manifest["declaration"] != declaration:
            raise EvaluationError("Frozen evaluator code/rules identity differs from this checkout.")
        if manifest["manifest_identity_sha256"] != _manifest_identity(manifest):
            raise EvaluationError("Frozen evaluator manifest integrity mismatch.")
        if manifest["files"] != {"scoring_rules.json": files["scoring_rules.json"]} or files["scoring_rules.json"] != sha256_file(RULES_PATH):
            raise EvaluationError("Frozen evaluator scoring rules drift.")
        binding = manifest["truth_binding"]
        if not isinstance(binding, dict) or set(binding) != {"truth_artifact_id", "truth_manifest_sha256", "holdout_artifact_identity", "source_snapshot_identity"}:
            raise EvaluationError("Frozen evaluator truth binding mismatch.")
        if any(not isinstance(v, str) or len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in binding.values()):
            raise EvaluationError("Frozen evaluator requires complete SHA-256 truth bindings.")
        timestamp = pd.Timestamp(manifest["created_at_utc"])
        if pd.isna(timestamp) or timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
            raise EvaluationError("Frozen evaluator timestamp must be UTC.")
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise EvaluationError(f"Invalid frozen evaluator: {error}") from error
    if expected_evaluator_identity is not None and declaration["evaluator_identity"] != expected_evaluator_identity:
        raise EvaluationError("Unexpected evaluator identity.")
    return manifest


def freeze_evaluator(*, truth_dir: Path, output_dir: Path,
                     expected_truth_artifact_id: str, expected_truth_manifest_sha256: str) -> dict:
    truth_dir, output_dir = Path(truth_dir), Path(output_dir)
    before = inventory(truth_dir)
    truth = load_truth(truth_dir, require_frozen=True, expected_manifest_sha256=expected_truth_manifest_sha256)
    if truth.truth_artifact_id != expected_truth_artifact_id:
        raise EvaluationError("Unexpected truth artifact identity.")
    declaration = evaluator_declaration()
    with new_artifact(output_dir, protected=(truth_dir,)) as stage:
        (stage / "scoring_rules.json").write_bytes(RULES_PATH.read_bytes())
        manifest = {
            "freeze_version": FREEZE_VERSION, "declaration": declaration,
            "truth_binding": {"truth_artifact_id": truth.truth_artifact_id,
                              "truth_manifest_sha256": expected_truth_manifest_sha256,
                              "holdout_artifact_identity": truth.holdout_artifact_identity,
                              "source_snapshot_identity": truth.source_snapshot_identity},
            "created_at_utc": utc_now(), "files": {"scoring_rules.json": sha256_file(stage / "scoring_rules.json")},
        }
        manifest["manifest_identity_sha256"] = _manifest_identity(manifest)
        write_json(stage / "manifest.json", manifest)
        validate_evaluator(stage)
        if inventory(truth_dir) != before or evaluator_declaration() != declaration:
            raise EvaluationError("Truth or evaluator changed during publication.")
    return manifest
