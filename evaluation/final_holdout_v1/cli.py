from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from evaluation.final_holdout_v1.contract import (
    CONTRACT_VERSION,
    copy_empty_templates,
    freeze_truth,
    initialize_truth,
    load_truth,
)
from evaluation.final_holdout_v1.evaluator import (
    evaluate,
    validate_execution_record,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.final_holdout_v1.cli",
        description=(
            "Evaluation-only tooling for final_holdout_evaluation_contract_v1. "
            "This command never executes extraction or calls a model."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    templates = subparsers.add_parser(
        "create-empty-templates",
        help="copy the versioned header-only truth templates",
    )
    templates.add_argument("--output", type=Path, required=True)

    init_truth = subparsers.add_parser(
        "init-truth",
        help="deliberately break the seal and initialize blind annotation",
    )
    init_truth.add_argument("--holdout", type=Path, required=True)
    init_truth.add_argument("--documents", type=Path, required=True)
    init_truth.add_argument("--output", type=Path, required=True)
    init_truth.add_argument("--holdout-version", required=True)
    init_truth.add_argument("--reviewer-id", required=True)
    init_truth.add_argument("--break-seal", action="store_true")

    validate_truth = subparsers.add_parser(
        "validate-truth",
        help="validate schema, domains, lineage and optional completeness",
    )
    validate_truth.add_argument("--truth", type=Path, required=True)
    validate_truth.add_argument("--require-complete", action="store_true")
    validate_truth.add_argument("--require-frozen", action="store_true")

    freeze = subparsers.add_parser(
        "freeze-truth",
        help="validate and copy complete truth into an immutable new directory",
    )
    freeze.add_argument("--truth", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)

    execution = subparsers.add_parser(
        "validate-execution-record",
        help="validate the later one-shot execution record",
    )
    execution.add_argument("--record", type=Path, required=True)

    evaluator = subparsers.add_parser(
        "evaluate",
        help="score frozen primary predictions against frozen blind truth",
    )
    evaluator.add_argument("--truth", type=Path, required=True)
    evaluator.add_argument("--predictions", type=Path, required=True)
    evaluator.add_argument("--execution-record", type=Path, required=True)
    evaluator.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "create-empty-templates":
        copy_empty_templates(args.output)
        print(f"empty truth templates: {args.output}")
        return 0
    if args.command == "init-truth":
        output = initialize_truth(
            holdout_path=args.holdout,
            documents_path=args.documents,
            output_dir=args.output,
            holdout_version=args.holdout_version,
            reviewer_id=args.reviewer_id,
            break_seal=args.break_seal,
        )
        print(f"blind truth initialized: {output}")
        return 0
    if args.command == "validate-truth":
        truth = load_truth(
            args.truth,
            require_complete=args.require_complete,
            require_frozen=args.require_frozen,
        )
        print(json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "truth_artifact_id": truth.truth_artifact_id,
            "frozen": truth.manifest is not None,
        }, sort_keys=True))
        return 0
    if args.command == "freeze-truth":
        truth = freeze_truth(args.truth, args.output)
        print(json.dumps({
            "truth_contract_version": CONTRACT_VERSION,
            "truth_artifact_id": truth.truth_artifact_id,
            "output": str(args.output),
        }, sort_keys=True))
        return 0
    if args.command == "validate-execution-record":
        record = validate_execution_record(args.record)
        print(json.dumps({
            "record_version": record["record_version"],
            "run_id": record["run_id"],
            "valid": True,
        }, sort_keys=True))
        return 0
    if args.command == "evaluate":
        result = evaluate(
            truth_dir=args.truth,
            predictions_dir=args.predictions,
            execution_record_path=args.execution_record,
            output_dir=args.output,
        )
        print(json.dumps({
            "evaluation_output_id": result.evaluation_output_id,
            "output": str(result.output_dir),
        }, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
