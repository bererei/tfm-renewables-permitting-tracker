from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
    SCOPE_CLASSIFICATION_POLICY,
)


ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = ROOT / "config" / "evaluation"
HOLDOUT_PATH = EVALUATION_DIR / "final_holdout_p2_v1.csv"
SCOPES_DIR = EVALUATION_DIR / "final_p2_execution_scopes_v1"
MANIFEST_PATH = SCOPES_DIR / "manifest.json"
P2_SCOPE_PATH = SCOPES_DIR / "p2_all.csv"
EXPOSURE_PATH = EVALUATION_DIR / "development_used_documents.csv"

SOURCE_SNAPSHOT_ID = (
    "1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf"
)
PERIOD_START = "2024-01-01"
PERIOD_END = "2026-08-20"
SEED = "20260821"
HOLDOUT_POLICY = "sha256_rank_year_boe_series_equal_quota_v1"
BATCH_POLICY = "sha256_rank_fixed_max_250_v1"
EXPECTED_FINGERPRINTS = {
    "holdout_sha256": (
        "617e3a9379cbe7b8f041330d4579fea6f34ea592956c19dc29ad65325bd0fb17"
    ),
    "main_scope_collection_sha256": (
        "ec619d4b3f160ee516b51ca801aec6e2931175e2ffae6d381d48d31a7597f4ca"
    ),
    "model_required_universe_sha256": (
        "1b14f5b07520a0c36e94368d59a6669737eea3a49b56be761b76cd44cba1e124"
    ),
    "p2_scope_sha256": (
        "86c2d9ad0abb4c82654b0ce68d2cf2e61b9a58b35ef85571031562697f67f3f7"
    ),
}

HOLDOUT_COLUMNS = [
    "holdout_version",
    "identificador_boe",
    "publication_date",
    "source_document_sha256",
    "year",
    "boe_series",
    "pre_model_decision",
    "stratum_population",
    "stratum_quota",
    "selection_rank",
    "selection_hash",
    "seed",
    "source_snapshot_id",
    "extraction_config_id",
    "scope_policy",
    "period_start",
    "period_end",
    "selection_policy",
]
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
P2_SCOPE_COLUMNS = [
    "identificador_boe",
    "publication_date",
    "source_document_sha256",
]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def _sha256_lines(lines: list[str]) -> str:
    payload = "".join(f"{line}\n" for line in lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _selection_hash(boe_id: str) -> str:
    payload = (
        f"{SEED}|{SOURCE_SNAPSHOT_ID}|{EXTRACTION_CONFIG_ID}|{boe_id}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _batch_hash(boe_id: str) -> str:
    payload = (
        f"{SEED}|{SOURCE_SNAPSHOT_ID}|{EXTRACTION_CONFIG_ID}|main|{boe_id}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _holdout_fingerprint(rows: list[dict[str, str]]) -> str:
    header = "|".join([
        "holdout_v1",
        PERIOD_START,
        PERIOD_END,
        SOURCE_SNAPSHOT_ID,
        EXTRACTION_CONFIG_ID,
        SCOPE_CLASSIFICATION_POLICY,
        SEED,
        HOLDOUT_POLICY,
    ])
    values = [
        "|".join(row[column] for column in HOLDOUT_COLUMNS)
        for row in sorted(rows, key=lambda row: row["identificador_boe"])
    ]
    return _sha256_lines([header, *values])


def _scope_fingerprint(
    rows: list[dict[str, str]], columns: list[str]
) -> str:
    values = [
        "|".join(row[column] for column in columns)
        for row in sorted(rows, key=lambda row: row["identificador_boe"])
    ]
    return _sha256_lines(values)


def test_final_p2_holdout_is_reproducible_and_development_unexposed() -> None:
    columns, holdout = _read_csv(HOLDOUT_PATH)
    _, exposure = _read_csv(EXPOSURE_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["fingerprints"] == EXPECTED_FINGERPRINTS
    assert columns == HOLDOUT_COLUMNS
    assert len(holdout) == 48
    assert len({row["identificador_boe"] for row in holdout}) == 48
    assert all(PERIOD_START <= row["publication_date"] <= PERIOD_END for row in holdout)
    assert {row["pre_model_decision"] for row in holdout} == {"MODEL_REQUIRED"}
    assert {row["seed"] for row in holdout} == {SEED}
    assert {row["source_snapshot_id"] for row in holdout} == {
        SOURCE_SNAPSHOT_ID
    }
    assert {row["extraction_config_id"] for row in holdout} == {
        EXTRACTION_CONFIG_ID
    }
    assert {row["scope_policy"] for row in holdout} == {
        SCOPE_CLASSIFICATION_POLICY
    }
    assert {row["selection_policy"] for row in holdout} == {
        HOLDOUT_POLICY
    }
    assert Counter((row["year"], row["boe_series"]) for row in holdout) == {
        (year, series): 8
        for year in ("2024", "2025", "2026")
        for series in ("A", "B")
    }
    exposed_ids = {row["identificador_boe"] for row in exposure}
    assert exposed_ids.isdisjoint(
        row["identificador_boe"] for row in holdout
    )
    assert all(
        row["selection_hash"] == _selection_hash(row["identificador_boe"])
        for row in holdout
    )
    assert _holdout_fingerprint(holdout) == manifest["fingerprints"][
        "holdout_sha256"
    ]


def test_final_p2_holdout_matches_hash_rank_over_versioned_model_scope() -> None:
    _, holdout = _read_csv(HOLDOUT_PATH)
    _, exposure = _read_csv(EXPOSURE_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    main_rows: list[dict[str, str]] = []
    for entry in manifest["main_scopes"]:
        _, rows = _read_csv(SCOPES_DIR / entry["filename"])
        main_rows.extend(rows)

    model_rows = [*main_rows, *holdout]
    assert len(model_rows) == 5_037
    assert len({row["identificador_boe"] for row in model_rows}) == 5_037
    assert {row["pre_model_decision"] for row in model_rows} == {
        "MODEL_REQUIRED"
    }
    exposed_ids = {row["identificador_boe"] for row in exposure}
    eligible = [
        row for row in model_rows
        if row["identificador_boe"] not in exposed_ids
    ]
    assert len(eligible) == 4_898
    model_fingerprint = _sha256_lines(sorted(
        "|".join([
            row["identificador_boe"],
            row["publication_date"],
            row["source_document_sha256"],
        ])
        for row in model_rows
    ))
    assert model_fingerprint == EXPECTED_FINGERPRINTS[
        "model_required_universe_sha256"
    ]

    expected_ids: set[str] = set()
    for year in ("2024", "2025", "2026"):
        for series in ("A", "B"):
            stratum = [
                row for row in eligible
                if row["year"] == year and row["boe_series"] == series
            ]
            stratum.sort(
                key=lambda row: (
                    _selection_hash(row["identificador_boe"]),
                    row["identificador_boe"],
                )
            )
            expected_ids.update(
                row["identificador_boe"] for row in stratum[:8]
            )
    assert {row["identificador_boe"] for row in holdout} == expected_ids


def test_final_p2_main_scopes_are_disjoint_complete_and_deterministic() -> None:
    _, holdout = _read_csv(HOLDOUT_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["source_snapshot_id"] == SOURCE_SNAPSHOT_ID
    assert manifest["extraction_config_id"] == EXTRACTION_CONFIG_ID
    assert manifest["instructions_sha256"] == INSTRUCTIONS_SHA256
    assert manifest["contract_schema_sha256"] == CONTRACT_SCHEMA_SHA256
    assert manifest["model_provider"] == MODEL_PROVIDER
    assert manifest["model_name"] == AI_MODEL_NAME
    assert manifest["scope_policy"] == SCOPE_CLASSIFICATION_POLICY
    assert manifest["period"] == {"start": PERIOD_START, "end": PERIOD_END}
    assert manifest["batch_policy"] == BATCH_POLICY
    assert len(manifest["main_scopes"]) == 20

    main_rows: list[dict[str, str]] = []
    scope_fingerprints: list[str] = []
    for index, entry in enumerate(manifest["main_scopes"], start=1):
        columns, rows = _read_csv(SCOPES_DIR / entry["filename"])
        assert columns == MAIN_SCOPE_COLUMNS
        assert len(rows) == entry["row_count"]
        assert len(rows) <= 250
        assert {row["batch_id"] for row in rows} == {f"main-{index:02d}"}
        assert [int(row["batch_rank"]) for row in rows] == list(
            range(1, len(rows) + 1)
        )
        fingerprint = _scope_fingerprint(rows, MAIN_SCOPE_COLUMNS)
        assert fingerprint == entry["scope_sha256"]
        scope_fingerprints.append(fingerprint)
        main_rows.extend(rows)

    main_ids = [row["identificador_boe"] for row in main_rows]
    holdout_ids = {row["identificador_boe"] for row in holdout}
    assert len(main_rows) == 4_989
    assert len(set(main_ids)) == 4_989
    assert holdout_ids.isdisjoint(main_ids)

    expected_order = sorted(
        main_rows,
        key=lambda row: (
            _batch_hash(row["identificador_boe"]),
            row["identificador_boe"],
        ),
    )
    expected_membership = {
        row["identificador_boe"]: f"main-{position // 250 + 1:02d}"
        for position, row in enumerate(expected_order)
    }
    assert all(
        row["batch_hash"] == _batch_hash(row["identificador_boe"])
        and row["batch_id"] == expected_membership[row["identificador_boe"]]
        for row in main_rows
    )

    collection_payload = [
        f"{entry['batch_id']}|{entry['row_count']}|{fingerprint}"
        for entry, fingerprint in zip(
            manifest["main_scopes"], scope_fingerprints, strict=True
        )
    ]
    assert _sha256_lines(collection_payload) == manifest["fingerprints"][
        "main_scope_collection_sha256"
    ]


def test_final_p2_scope_covers_model_universe_and_full_period() -> None:
    p2_columns, p2_rows = _read_csv(P2_SCOPE_PATH)
    _, holdout = _read_csv(HOLDOUT_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    main_rows = [
        row
        for entry in manifest["main_scopes"]
        for row in _read_csv(SCOPES_DIR / entry["filename"])[1]
    ]

    assert p2_columns == P2_SCOPE_COLUMNS
    assert len(p2_rows) == 19_489
    assert len({row["identificador_boe"] for row in p2_rows}) == 19_489
    assert all(
        PERIOD_START <= row["publication_date"] <= PERIOD_END
        for row in p2_rows
    )
    p2_ids = {row["identificador_boe"] for row in p2_rows}
    model_ids = {
        row["identificador_boe"] for row in [*main_rows, *holdout]
    }
    assert model_ids <= p2_ids
    p2_hashes = {
        row["identificador_boe"]: row["source_document_sha256"]
        for row in p2_rows
    }
    assert all(
        p2_hashes[row["identificador_boe"]]
        == row["source_document_sha256"]
        for row in [*main_rows, *holdout]
    )
    assert len(main_rows) + len(holdout) == 5_037
    assert _scope_fingerprint(p2_rows, P2_SCOPE_COLUMNS) == manifest[
        "fingerprints"
    ]["p2_scope_sha256"]
