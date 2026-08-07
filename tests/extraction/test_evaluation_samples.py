import csv
import re
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_CONFIG_DIR = REPOSITORY_ROOT / "config" / "evaluation"
CHALLENGE_PATH = EVALUATION_CONFIG_DIR / "development_challenge_sample.csv"
USED_DOCUMENTS_PATH = EVALUATION_CONFIG_DIR / "development_used_documents.csv"
HUMAN_AUDIT_PATH = (
    EVALUATION_CONFIG_DIR / "development_challenge_human_audit.csv"
)

CHALLENGE_COLUMNS = [
    "sample_version",
    "identificador_boe",
    "selection_category",
    "selection_reason",
    "selection_signals",
    "source_corpus_sha256",
]
USED_DOCUMENT_COLUMNS = [
    "identificador_boe",
    "usage_type",
    "usage_reason",
    "source_reference",
]
HUMAN_AUDIT_COLUMNS = [
    "audit_version",
    "challenge_sample_version",
    "run_scope",
    "identificador_boe",
    "source_attempt_id",
    "source_document_sha256",
    "extraction_config_id",
    "defect_code",
    "defect_description",
    "human_decision",
    "human_notes",
    "reviewer_id",
    "reviewed_on",
]
EXPECTED_CATEGORY_COUNTS = {
    "A": 6,
    "B": 5,
    "C": 5,
    "D": 5,
    "E": 5,
    "F": 5,
    "G": 5,
    "H": 4,
}
EXPECTED_CORPUS_SHA256 = (
    "17b852ed832ebe53b3e49075590a352ae4affb26da8a7ac9f16977e3bcbde470"
)
ALLOWED_USAGE_TYPES = {
    "pilot",
    "development_example",
    "regression_case",
    "challenge_sample",
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def test_development_challenge_sample_contract() -> None:
    columns, rows = _read_csv(CHALLENGE_PATH)

    assert columns == CHALLENGE_COLUMNS
    assert len(rows) == 40
    assert len({row["identificador_boe"] for row in rows}) == 40
    assert {row["sample_version"] for row in rows} == {"1"}
    assert Counter(row["selection_category"] for row in rows) == (
        EXPECTED_CATEGORY_COUNTS
    )
    assert {row["source_corpus_sha256"] for row in rows} == {
        EXPECTED_CORPUS_SHA256
    }
    assert all(
        value.strip()
        for row in rows
        for value in (row[column] for column in CHALLENGE_COLUMNS)
    )
    assert [
        (row["selection_category"], row["identificador_boe"])
        for row in rows
    ] == sorted(
        (row["selection_category"], row["identificador_boe"])
        for row in rows
    )


def test_development_used_documents_contract_and_separation() -> None:
    challenge_columns, challenge_rows = _read_csv(CHALLENGE_PATH)
    used_columns, used_rows = _read_csv(USED_DOCUMENTS_PATH)

    assert challenge_columns == CHALLENGE_COLUMNS
    assert used_columns == USED_DOCUMENT_COLUMNS
    assert len(used_rows) == 152
    assert len({row["identificador_boe"] for row in used_rows}) == 152
    assert all(
        value.strip()
        for row in used_rows
        for value in (row[column] for column in USED_DOCUMENT_COLUMNS)
    )

    usage_counts = Counter(row["usage_type"] for row in used_rows)
    assert set(usage_counts) <= ALLOWED_USAGE_TYPES
    assert usage_counts["pilot"] == 100
    assert usage_counts["challenge_sample"] == 40
    assert (
        usage_counts["development_example"]
        + usage_counts["regression_case"]
        == 12
    )

    challenge_ids = {row["identificador_boe"] for row in challenge_rows}
    pilot_ids = {
        row["identificador_boe"]
        for row in used_rows
        if row["usage_type"] == "pilot"
    }
    registered_challenge_ids = {
        row["identificador_boe"]
        for row in used_rows
        if row["usage_type"] == "challenge_sample"
    }
    assert challenge_ids.isdisjoint(pilot_ids)
    assert registered_challenge_ids == challenge_ids


def test_development_challenge_human_audit_contract() -> None:
    challenge_columns, challenge_rows = _read_csv(CHALLENGE_PATH)
    audit_columns, audit_rows = _read_csv(HUMAN_AUDIT_PATH)

    assert challenge_columns == CHALLENGE_COLUMNS
    assert audit_columns == HUMAN_AUDIT_COLUMNS
    assert len(audit_rows) == 15
    assert len({row["identificador_boe"] for row in audit_rows}) == 8
    assert {row["audit_version"] for row in audit_rows} == {"1"}
    assert {row["challenge_sample_version"] for row in audit_rows} == {"1"}
    assert {row["run_scope"] for row in audit_rows} == {
        "development_challenge_v1"
    }
    assert Counter(row["human_decision"] for row in audit_rows) == {
        "CONFIRMED_MAJOR": 13,
        "CONFIRMED_MINOR": 2,
    }

    challenge_ids = {row["identificador_boe"] for row in challenge_rows}
    audit_ids = {row["identificador_boe"] for row in audit_rows}
    assert audit_ids <= challenge_ids
    assert len(
        {(row["identificador_boe"], row["defect_code"]) for row in audit_rows}
    ) == len(audit_rows)
    assert all(
        value.strip()
        for row in audit_rows
        for value in (row[column] for column in HUMAN_AUDIT_COLUMNS)
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{32}", row["source_attempt_id"])
        for row in audit_rows
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", row["source_document_sha256"])
        for row in audit_rows
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{16}", row["extraction_config_id"])
        for row in audit_rows
    )
    assert {row["reviewer_id"] for row in audit_rows} == {
        "human_reviewer_1"
    }
    assert {row["reviewed_on"] for row in audit_rows} == {"2026-08-07"}
