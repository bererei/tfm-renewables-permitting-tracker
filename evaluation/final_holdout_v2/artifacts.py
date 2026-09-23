"""Small shared V2-B artifact primitives; one writer per destination."""
from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from evaluation.final_holdout_v2.contract import canonical_json_bytes, sha256_file
from evaluation.final_holdout_v2.predictions import EvaluationError


def identity(value) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def inventory(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_dir():
        raise EvaluationError("Artifact input must be a regular directory.")
    files = {}
    for entry in sorted(path.rglob("*")):
        if entry.is_symlink() or (not entry.is_file() and not entry.is_dir()):
            raise EvaluationError("Artifact symlinks and special files are not supported.")
        if entry.is_file():
            files[entry.relative_to(path).as_posix()] = sha256_file(entry)
    return files


def require_new_output(output: Path, protected: tuple[Path, ...] = ()) -> None:
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Output already exists: {output}")
    if any(output.resolve().is_relative_to(path.resolve()) for path in protected):
        raise EvaluationError("Output cannot be inside an input artifact.")


@contextmanager
def new_artifact(output: Path, *, protected: tuple[Path, ...] = ()):
    output = Path(output).absolute()
    require_new_output(output, protected)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        yield stage
        require_new_output(output, protected)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
