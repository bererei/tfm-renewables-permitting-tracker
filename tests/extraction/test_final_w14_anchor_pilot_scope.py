from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = ROOT / "config" / "evaluation"
SCOPE_PATH = EVALUATION_DIR / "final_w14_anchor_pilot_v1.csv"
HOLDOUT_PATH = EVALUATION_DIR / "final_holdout_p2_v1.csv"
P2_SCOPES_DIR = EVALUATION_DIR / "final_p2_execution_scopes_v1"
P2_MANIFEST_PATH = P2_SCOPES_DIR / "manifest.json"

PERIOD_START = "2026-08-07"
PERIOD_END = "2026-08-20"
EXPECTED_SCOPE_SHA256 = (
    "ed07c25e74aaff29c19e28362f70dfa973f40a0aa74b189d0077539b5fe1c2c2"
)
MAIN_SCOPE_COLUMNS = [
    "identificador_boe",
    "publication_date",
    "source_document_sha256",
    "year",
    "boe_series",
    "pre_model_decision",
    "batch_id",
    "batch_rank",
    "batch_hash",
]
MAIN_03_RETRIES = {"BOE-B-2025-41490", "BOE-B-2025-45035"}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def _scope_fingerprint(rows: list[dict[str, str]]) -> str:
    values = [
        "|".join(row[column] for column in MAIN_SCOPE_COLUMNS)
        for row in sorted(rows, key=lambda row: row["identificador_boe"])
    ]
    payload = "".join(f"{value}\n" for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_w14_anchor_scope_is_exact_non_holdout_model_projection() -> None:
    columns, scope = _read_csv(SCOPE_PATH)
    _, holdout = _read_csv(HOLDOUT_PATH)
    manifest = json.loads(P2_MANIFEST_PATH.read_text(encoding="utf-8"))
    main_rows = [
        row
        for entry in manifest["main_scopes"]
        for row in _read_csv(P2_SCOPES_DIR / entry["filename"])[1]
    ]

    expected = [
        row
        for row in main_rows
        if PERIOD_START <= row["publication_date"] <= PERIOD_END
    ]
    holdout_w14 = [
        row
        for row in holdout
        if PERIOD_START <= row["publication_date"] <= PERIOD_END
    ]
    scope_ids = {row["identificador_boe"] for row in scope}

    assert columns == MAIN_SCOPE_COLUMNS
    assert len(scope) == len(scope_ids) == 48
    assert sorted(scope, key=lambda row: row["identificador_boe"]) == sorted(
        expected,
        key=lambda row: row["identificador_boe"],
    )
    assert len(holdout_w14) == 1
    assert scope_ids.isdisjoint(
        row["identificador_boe"] for row in holdout_w14
    )
    assert {row["pre_model_decision"] for row in scope} == {
        "MODEL_REQUIRED"
    }
    assert Counter(row["boe_series"] for row in scope) == {"A": 25, "B": 23}
    assert all(
        PERIOD_START <= row["publication_date"] <= PERIOD_END
        for row in scope
    )
    assert scope_ids.isdisjoint(MAIN_03_RETRIES)
    assert _scope_fingerprint(scope) == EXPECTED_SCOPE_SHA256
