"""Durable local journal and publication primitives (POSIX, one locked writer)."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


class PrimaryRunError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PrimaryRunError(f"Expected regular file: {path}")
    return sha256(path.read_bytes()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PrimaryRunError("Duplicate JSON key.")
        result[key] = value
    return result


def parse_json(raw: bytes):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              PrimaryRunError("Non-finite JSON value.")))
    except (ValueError, UnicodeError) as error:
        raise PrimaryRunError("Malformed JSON.") from error


def read_json(path: Path):
    file_hash(path)
    return parse_json(path.read_bytes())


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_json(path: Path, value, *, replace: bool = False) -> None:
    """Publish a complete JSON file; replacement is only for the journal head."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            if path.is_symlink():
                raise PrimaryRunError("Refusing symlink journal head.")
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # atomic, refuses even a dangling destination
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def inventory(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_dir():
        raise PrimaryRunError("Expected regular artifact directory.")
    result = {}
    for entry in sorted(path.rglob("*")):
        if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
            raise PrimaryRunError("Artifact contains symlink/special file.")
        if entry.is_file():
            result[entry.relative_to(path).as_posix()] = file_hash(entry)
    return result


def fsync_tree(path: Path) -> None:
    for name in inventory(path):
        with (path / name).open("rb") as stream:
            os.fsync(stream.fileno())
    for directory in sorted((p for p in path.rglob("*") if p.is_dir()), reverse=True):
        fsync_directory(directory)
    fsync_directory(path)


def publish_directory(stage: Path, output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise PrimaryRunError(f"Output already exists: {output}")
    fsync_tree(stage)
    stage.rename(output)
    fsync_directory(output.parent)


@contextmanager
def writer_lock(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise PrimaryRunError("Invalid run root.")
    fd = os.open(root / ".writer.lock", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PrimaryRunError("Another controller owns this run.") from error
        yield fd
    finally:
        os.close(fd)


def writer_active(root: Path) -> bool:
    try:
        with writer_lock(root):
            return False
    except PrimaryRunError as error:
        if str(error) == "Another controller owns this run.":
            return True
        raise


EVENTS = {"RUN_PREPARED", "RUN_INVOKED", "DOCUMENT_STARTED", "DOCUMENT_COMPLETED",
          "DOCUMENT_ERROR", "RUN_INTERRUPTED", "INCIDENT", "RUN_EXECUTION_COMPLETED",
          "RUN_FINALIZED"}


def load_journal(root: Path, run_id: str) -> list[dict]:
    path = root / "journal.jsonl"
    file_hash(path)
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise PrimaryRunError("Empty or torn journal; never infer PENDING from it.")
    previous = None
    events = []
    for ordinal, line in enumerate(raw.splitlines(), 1):
        event = parse_json(line)
        required = {"version", "seq", "previous_sha256", "sha256", "run_id",
                    "timestamp_utc", "event", "data"}
        if not isinstance(event, dict) or set(event) != required:
            raise PrimaryRunError("Malformed journal event.")
        try:
            instant = datetime.fromisoformat(event["timestamp_utc"])
            utc = instant.utcoffset() is not None and instant.utcoffset().total_seconds() == 0
        except (TypeError, ValueError):
            utc = False
        body = {k: v for k, v in event.items() if k != "sha256"}
        if (event["version"] != 1 or type(event["seq"]) is not int
                or event["seq"] != ordinal or event["previous_sha256"] != previous
                or event["sha256"] != digest(body) or event["run_id"] != run_id
                or event["event"] not in EVENTS or not isinstance(event["data"], dict) or not utc):
            raise PrimaryRunError("Journal identity/chain/time mismatch.")
        if events and event["timestamp_utc"] < events[-1]["timestamp_utc"]:
            raise PrimaryRunError("Journal time moved backwards.")
        events.append(event)
        previous = event["sha256"]
    head = read_json(root / "journal.head.json")
    if (set(head) != {"seq", "sha256"} or type(head["seq"]) is not int
            or not 1 <= head["seq"] <= len(events)
            or events[head["seq"] - 1]["sha256"] != head["sha256"]):
        raise PrimaryRunError("Journal was truncated or its durable head changed.")
    return events


def append_event(root: Path, run_id: str, event: str, data: dict,
                 *, initial: bool = False) -> dict:
    if event not in EVENTS:
        raise PrimaryRunError("Unknown journal event.")
    previous = [] if initial else load_journal(root, run_id)
    body = {"version": 1, "seq": len(previous) + 1,
            "previous_sha256": previous[-1]["sha256"] if previous else None,
            "run_id": run_id, "timestamp_utc": utc_now(), "event": event, "data": data}
    body["sha256"] = digest(body)
    flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
    if initial:
        flags |= os.O_CREAT | os.O_EXCL
    fd = os.open(root / "journal.jsonl", flags, 0o600)
    with os.fdopen(fd, "ab", buffering=0) as stream:
        raw = canonical(body) + b"\n"
        if stream.write(raw) != len(raw):
            raise PrimaryRunError("Partial journal append; stop for recovery review.")
        stream.flush()
        os.fsync(stream.fileno())
    durable_json(root / "journal.head.json",
                 {"seq": body["seq"], "sha256": body["sha256"]}, replace=not initial)
    return body
