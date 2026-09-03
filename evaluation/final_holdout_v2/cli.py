from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from evaluation.final_holdout_v2.contract import (
    CONTRACT_VERSION,
    copy_empty_templates,
    load_truth,
    migrate_v1_truth,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.final_holdout_v2.cli",
        description=(
            "Blind annotation tooling for final_holdout_evaluation_contract_v2. "
            "V2-A does not execute extraction, freeze truth, evaluate or call a model."
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
