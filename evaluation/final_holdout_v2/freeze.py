"""Publish verified V2 human truth; no prediction, pipeline or model inputs."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from evaluation.final_holdout_v2.annotation import (
    _row_frame,
    load_annotation_workspace,
    validate_evidence_literal,
)
from evaluation.final_holdout_v2.contract import (
    CONTRACT_DECLARATION_PATH,
    CONTRACT_VERSION,
    FREEZE_ENTRY_POINT,
    FREEZE_TOOL_VERSION,
    FROZEN_MANIFEST_VERSION,
    FROZEN_SELECTION,
    TABLE_SPECS,
    TRUTH_MANIFEST,
    TRUTH_METADATA,
    TruthArtifact,
    TruthContractError,
    canonical_json_bytes,
    frozen_manifest_identity,
    load_truth,
    sha256_file,
    validate_holdout_selection,
)


def _working_hashes(truth_dir: Path) -> dict[str, str]:
    expected = {f"{table}.csv" for table in TABLE_SPECS} | {TRUTH_METADATA}
    if truth_dir.is_symlink() or not truth_dir.is_dir():
        raise TruthContractError("Freeze requires a regular working truth directory.")
    if {path.name for path in truth_dir.iterdir()} != expected:
        raise TruthContractError(
            "Working truth file set mismatch; frozen inputs are not working truth."
        )
    for name in expected:
        path = truth_dir / name
        if path.is_symlink() or not path.is_file():
            raise TruthContractError(f"Working truth requires a regular file: {name}.")
    return {name: sha256_file(truth_dir / name) for name in sorted(expected)}


def _require_new_destination(output_dir: Path) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(
            f"Output already exists; freeze never overwrites: {output_dir}"
        )


def _tool_source_hash() -> str:
    """Fingerprint the actual freeze/validation sources, including uncommitted code."""
    root = Path(__file__).resolve().parents[2]
    sources = [
        f"evaluation/final_holdout_{version}/{name}.py"
        for version, names in (
            ("v1", ("contract", "annotation", "matching")),
            ("v2", ("contract", "annotation", "freeze", "cli")),
        )
        for name in names
    ] + [
        "src/renewables_permitting/extraction/documents.py",
        "src/renewables_permitting/extraction/models.py",
        "uv.lock",
    ]
    return sha256(canonical_json_bytes({
        name: sha256_file(root / name) for name in sources
    })).hexdigest()


def freeze_truth(
    truth_dir: Path,
    output_dir: Path,
    *,
    holdout_path: Path,
    documents_path: Path,
) -> TruthArtifact:
    """Copy complete human truth atomically under the single-writer convention.

    Selection membership and source evidence are checked before publication.
    No working bytes are rewritten and no existing destination is replaced.
    """
    truth_dir = Path(truth_dir).absolute()
    output_dir = Path(output_dir).absolute()
    holdout_path = Path(holdout_path)
    _require_new_destination(output_dir)
    if output_dir.resolve().is_relative_to(truth_dir.resolve()):
        raise TruthContractError("Freeze output cannot be inside the working truth.")
    before = _working_hashes(truth_dir)
    truth = load_truth(truth_dir, require_complete=True)
    validate_holdout_selection(
        holdout_path, truth.tables["documents"],
        holdout_identity=truth.holdout_artifact_identity,
        source_identity=truth.source_snapshot_identity,
    )
    workspace = load_annotation_workspace(truth_dir, documents_path)
    source_texts = dict(zip(
        workspace.source_documents["identificador"],
        workspace.source_documents["texto_limpio"],
    ))
    for table, frame in truth.tables.items():
        for _, row in frame.iterrows():
            # Reuse the annotation boundary's reserved-key/placeholder check.
            _row_frame(table, row.to_dict())
    for _, evidence in truth.tables["evidence_passages"].iterrows():
        validate_evidence_literal(
            str(evidence["passage_text"]),
            str(source_texts[evidence["identificador_boe"]]),
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{output_dir.name}.staging-", dir=output_dir.parent,
    ))
    published = False
    try:
        for name in before:
            shutil.copyfile(truth_dir / name, staging / name)
        shutil.copyfile(holdout_path, staging / FROZEN_SELECTION)
        copied_hashes = {name: sha256_file(staging / name) for name in before}
        if copied_hashes != before:
            raise TruthContractError("Working truth changed during freeze; publication refused.")
        frozen = load_truth(staging, require_complete=True)
        if frozen.truth_artifact_id != truth.truth_artifact_id:
            raise TruthContractError("Copied V2 truth semantic identity mismatch.")
        documents = frozen.tables["documents"]
        manifest = {
            "manifest_version": FROZEN_MANIFEST_VERSION,
            "status": "frozen",
            "truth_contract_version": CONTRACT_VERSION,
            "truth_contract_declaration_sha256": sha256_file(CONTRACT_DECLARATION_PATH),
            "truth_artifact_id": frozen.truth_artifact_id,
            "holdout_artifact_identity": frozen.holdout_artifact_identity,
            "source_snapshot_identity": frozen.source_snapshot_identity,
            "truth_file_hashes": {
                **copied_hashes,
                FROZEN_SELECTION: sha256_file(staging / FROZEN_SELECTION),
            },
            "table_semantic_sha256": dict(frozen.table_semantic_sha256),
            "document_count": len(documents),
            "reviewer_ids": sorted(set(documents["reviewer_id"].astype(str))),
            "reviewed_on": sorted(set(documents["reviewed_on"].astype(str))),
            "predictions_exposed_during_annotation": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "freeze_tool_version": FREEZE_TOOL_VERSION,
            "freeze_entry_point": FREEZE_ENTRY_POINT,
            "freeze_tool_sha256": _tool_source_hash(),
        }
        manifest["manifest_identity_sha256"] = frozen_manifest_identity(manifest)
        (staging / TRUTH_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verified = load_truth(staging, require_frozen=True)
        if (
            _working_hashes(truth_dir) != before
            or sha256_file(holdout_path) != truth.holdout_artifact_identity
        ):
            raise TruthContractError(
                "Freeze inputs changed; publication refused without restoring inputs."
            )
        _require_new_destination(output_dir)
        staging.rename(output_dir)
        published = True
        return verified
    finally:
        if not published:
            shutil.rmtree(staging)
