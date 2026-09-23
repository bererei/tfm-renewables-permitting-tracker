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
from evaluation.final_holdout_v2.evaluator import evaluate, validate_evaluation
from evaluation.final_holdout_v2.evaluator_freeze import freeze_evaluator, validate_evaluator
from evaluation.final_holdout_v2.predictions import validate_execution_record


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.final_holdout_v2.cli",
        description=(
            "V2 human truth, evaluator freezes and offline evaluation. "
            "Never executes extraction or calls a model."
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

    evaluator_freeze = subparsers.add_parser("freeze-evaluator", help="freeze V2-B code/rules and bind verified frozen truth; new output only")
    evaluator_freeze.add_argument("--truth", type=Path, required=True)
    evaluator_freeze.add_argument("--output", type=Path, required=True)
    evaluator_freeze.add_argument("--expected-truth-artifact-id", required=True)
    evaluator_freeze.add_argument("--expected-truth-manifest-sha256", required=True)

    evaluator_verify = subparsers.add_parser("validate-evaluator", help="verify frozen evaluator against current code/rules")
    evaluator_verify.add_argument("--evaluator", type=Path, required=True)
    evaluator_verify.add_argument("--expected-evaluator-identity")
    evaluator_verify.add_argument("--expected-manifest-sha256")

    execution = subparsers.add_parser("validate-execution-record", help="validate the unchanged V1 execution record schema for V2 predictions")
    execution.add_argument("--record", type=Path, required=True)

    evaluator = subparsers.add_parser("evaluate", help="offline scoring with both freezes and explicit primary predictions; never overwrite")
    for flag in ("truth", "predictions", "evaluator", "execution-record", "output"):
        evaluator.add_argument(f"--{flag}", type=Path, required=True)
    for flag in ("expected-truth-artifact-id", "expected-truth-manifest-sha256", "expected-evaluator-identity", "expected-evaluator-manifest-sha256"):
        evaluator.add_argument(f"--{flag}")

    report = subparsers.add_parser("validate-evaluation", help="verify report hashes and semantic identity without prediction inputs")
    report.add_argument("--evaluation", type=Path, required=True)
    report.add_argument("--expected-manifest-sha256")
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
            "evaluator_implemented": True,
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
            "evaluator_implemented": True,
        }, sort_keys=True))
        return 0
    if args.command == "migrate-v1-truth":
        output = migrate_v1_truth(args.source, args.output)
        truth = load_truth(output)
        print(json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "truth_artifact_id": truth.truth_artifact_id,
            "output": str(output),
            "evaluator_implemented": True,
        }, sort_keys=True))
        return 0
    if args.command in {"freeze-evaluator", "validate-evaluator"}:
        if args.command == "freeze-evaluator":
            manifest = freeze_evaluator(truth_dir=args.truth, output_dir=args.output,
                expected_truth_artifact_id=args.expected_truth_artifact_id,
                expected_truth_manifest_sha256=args.expected_truth_manifest_sha256)
            published = args.output
        else:
            manifest = validate_evaluator(args.evaluator,
                expected_evaluator_identity=args.expected_evaluator_identity,
                expected_manifest_sha256=args.expected_manifest_sha256)
            published = args.evaluator
        print(json.dumps({"evaluator_identity": manifest["declaration"]["evaluator_identity"],
                          "manifest_sha256": sha256_file(published / "manifest.json"), "valid": True}, sort_keys=True))
        return 0
    if args.command == "validate-execution-record":
        record = validate_execution_record(args.record)
        print(json.dumps({"record_version": record["record_version"], "run_id": record["run_id"], "valid": True}, sort_keys=True))
        return 0
    if args.command == "evaluate":
        result = evaluate(truth_dir=args.truth, predictions_dir=args.predictions,
            execution_record_path=args.execution_record, evaluator_dir=args.evaluator, output_dir=args.output,
            expected_truth_artifact_id=args.expected_truth_artifact_id,
            expected_truth_manifest_sha256=args.expected_truth_manifest_sha256,
            expected_evaluator_identity=args.expected_evaluator_identity,
            expected_evaluator_manifest_sha256=args.expected_evaluator_manifest_sha256)
        print(json.dumps({"evaluation_output_id": result.evaluation_output_id, "output": str(result.output_dir)}, sort_keys=True))
        return 0
    if args.command == "validate-evaluation":
        manifest = validate_evaluation(args.evaluation, expected_manifest_sha256=args.expected_manifest_sha256)
        print(json.dumps({"evaluation_output_id": manifest["evaluation_output_id"], "valid": True}, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
