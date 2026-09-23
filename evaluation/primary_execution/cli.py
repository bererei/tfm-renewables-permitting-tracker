"""Explicit operational gates; only run-primary may initiate model work."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluation.final_holdout_v1.contract import FROZEN_PRODUCTION_COMMIT, FROZEN_EXTRACTION_CONFIG_ID
from evaluation.primary_execution.controller import (
    prepare_primary_run, run_primary, primary_status, finalize_primary,
)


def parser():
    result = argparse.ArgumentParser(prog="python -m evaluation.primary_execution.cli", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-primary-run", help="verify frozen inputs/system; publish preparation only")
    for flag in ("system-root", "truth", "evaluator", "source", "run-root"):
        prepare.add_argument(f"--{flag}", type=Path, required=True)
    for flag in ("expected-system-commit", "expected-config-id", "expected-truth-id",
                 "expected-truth-manifest", "expected-evaluator-id", "expected-evaluator-manifest"):
        prepare.add_argument(f"--{flag}", required=True)
    for command, help_text in (("run-primary", "execute only never-started documents; explicit model authorization"),
                               ("primary-status", "read-only journal/output verification and state"),
                               ("finalize-primary", "offline aggregate and seal; never evaluate")):
        child = commands.add_parser(command, help=help_text)
        child.add_argument("--run-root", type=Path, required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    exact_argv = list(sys.orig_argv) if argv is None else [sys.executable, "-m", "evaluation.primary_execution.cli", *argv]
    try:
        if args.command == "prepare-primary-run":
            if args.expected_system_commit != FROZEN_PRODUCTION_COMMIT or args.expected_config_id != FROZEN_EXTRACTION_CONFIG_ID:
                raise ValueError("This CLI requires the approved final system commit/configuration.")
            result = prepare_primary_run(
                system_root=args.system_root, truth_dir=args.truth, evaluator_dir=args.evaluator,
                source=args.source, run_root=args.run_root, expected_system_commit=args.expected_system_commit,
                expected_config_id=args.expected_config_id, expected_truth_id=args.expected_truth_id,
                expected_truth_manifest=args.expected_truth_manifest,
                expected_evaluator_id=args.expected_evaluator_id, expected_evaluator_manifest=args.expected_evaluator_manifest,
                argv=exact_argv)
        elif args.command == "run-primary":
            result = run_primary(args.run_root, argv=exact_argv)
        elif args.command == "primary-status":
            result = primary_status(args.run_root)
        else:
            result = finalize_primary(args.run_root, argv=exact_argv)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        print("Primary operation interrupted; inspect primary-status before any continuation.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError, AssertionError) as error:
        # Operational messages contain paths/identities, never environment values.
        print(f"Primary operation stopped ({type(error).__name__}): {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
