from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from evaluation.final_holdout_v2.contract import (
    CONTRACT_VERSION,
    TRUTH_MANIFEST,
    copy_empty_templates,
    load_truth,
    migrate_v1_truth,
    sha256_file,
)
from evaluation.final_holdout_v2.freeze import freeze_truth


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.final_holdout_v2.cli",
        description=(
            "Blind annotation tooling for final_holdout_evaluation_contract_v2. "
            "Annotation and immutable truth publication only; no extraction, "
            "matching, evaluation or model calls."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    templates = subparsers.add_parser(
        "create-empty-templates",
        help="copy the versioned V2 header-only truth templates",
    )
    templates.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate-truth",
        help="validate V2 schema, domains, lineage and completion",
    )
    validate.add_argument("--truth", type=Path, required=True)
    validate.add_argument("--require-complete", action="store_true")

    freeze = subparsers.add_parser(
        "freeze-truth",
        help="publish an immutable copy of valid, complete V2 truth; never overwrite",
        description=(
            "Publish an immutable copy of valid, complete V2 human truth. "
            "The destination must be new; existing destinations are never overwritten."
        ),
    )
    freeze.add_argument("--truth", type=Path, required=True, help="source working truth")
    freeze.add_argument("--output", type=Path, required=True, help="new frozen destination")
    freeze.add_argument("--holdout", type=Path, required=True, help="exact selection CSV")
    freeze.add_argument(
        "--documents", type=Path, required=True,
        help="canonical source directory or Parquet",
    )

    verify = subparsers.add_parser(
        "validate-frozen-truth", help="read-only verification of frozen V2 truth integrity",
    )
    verify.add_argument("--truth", type=Path, required=True)
    verify.add_argument(
        "--expected-manifest-sha256",
        help="optional externally recorded manifest SHA-256",
    )

    migration = subparsers.add_parser(
        "migrate-v1-truth",
        help="copy human V1 truth into a new V2 annotation workspace",
    )
    migration.add_argument("--source", type=Path, required=True)
    migration.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "create-empty-templates":
        copy_empty_templates(args.output)
        print(f"empty V2 truth templates: {args.output}")
        return 0
    if args.command == "validate-truth":
        truth = load_truth(args.truth, require_complete=args.require_complete)
        documents = truth.tables["documents"]
        print(json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "truth_artifact_id": truth.truth_artifact_id,
            "complete": bool(len(documents))
            and not documents["annotation_status"].eq("draft").any(),
            "evaluator_implemented": False,
            "frozen": truth.manifest is not None,
        }, sort_keys=True))
        return 0
    if args.command in {"freeze-truth", "validate-frozen-truth"}:
        if args.command == "freeze-truth":
            truth = freeze_truth(
                args.truth, args.output,
                holdout_path=args.holdout, documents_path=args.documents,
            )
            published_path = args.output
        else:
            truth = load_truth(
                args.truth, require_frozen=True,
                expected_manifest_sha256=args.expected_manifest_sha256,
            )
            published_path = args.truth
        print(json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "truth_artifact_id": truth.truth_artifact_id,
            "document_count": len(truth.tables["documents"]),
            "manifest_sha256": sha256_file(published_path / TRUTH_MANIFEST),
            "frozen_truth_intact": True,
            "evaluator_implemented": False,
        }, sort_keys=True))
        return 0
    if args.command == "migrate-v1-truth":
        output = migrate_v1_truth(args.source, args.output)
        truth = load_truth(output)
        print(json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "truth_artifact_id": truth.truth_artifact_id,
            "output": str(output),
            "evaluator_implemented": False,
        }, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
