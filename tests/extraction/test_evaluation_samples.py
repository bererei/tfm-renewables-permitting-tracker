import csv
import hashlib
import re
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_CONFIG_DIR = REPOSITORY_ROOT / "config" / "evaluation"
CHALLENGE_PATH = EVALUATION_CONFIG_DIR / "development_challenge_sample.csv"
USED_DOCUMENTS_PATH = EVALUATION_CONFIG_DIR / "development_used_documents.csv"
HOLDOUT_PROVENANCE_PATH = (
    REPOSITORY_ROOT / "docs" / "HOLDOUT_EXPOSURE_PROVENANCE.md"
)
HUMAN_AUDIT_PATH = (
    EVALUATION_CONFIG_DIR / "development_challenge_human_audit.csv"
)
HUMAN_AUDIT_V2_PATH = (
    EVALUATION_CONFIG_DIR / "development_challenge_v2_human_audit.csv"
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
HUMAN_AUDIT_V2_COLUMNS = [
    "audit_version",
    "challenge_sample_version",
    "run_scope",
    "identificador_boe",
    "source_attempt_id",
    "source_document_sha256",
    "extraction_config_id",
    "check_type",
    "candidate_assessment",
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
    "classifier_audit",
}
EXPECTED_USED_DOCUMENT_IDS_SHA256 = (
    "2e9da51070304ac15d5d941cdc2f1f9861da0c71d34cb6fb64cac34905e90f80"
)
EXPECTED_HISTORICAL_USED_ROWS_SHA256 = (
    "d1168bbeb9b4cc907c8dad9ba31fdc38f438bde6068b890c24ff7174867959a6"
)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def _lines_sha256(lines: list[str]) -> str:
    payload = "\n".join(lines) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


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
    used_ids = {row["identificador_boe"] for row in used_rows}
    assert len(used_rows) == 479
    assert len(used_ids) == 479
    assert all(
        value.strip()
        for row in used_rows
        for value in (row[column] for column in USED_DOCUMENT_COLUMNS)
    )

    usage_counts = Counter(row["usage_type"] for row in used_rows)
    assert set(usage_counts) == ALLOWED_USAGE_TYPES
    assert usage_counts["pilot"] == 100
    assert usage_counts["challenge_sample"] == 40
    assert usage_counts["development_example"] == 9
    assert usage_counts["regression_case"] == 3
    assert usage_counts["classifier_audit"] == 327

    assert _lines_sha256(sorted(used_ids)) == EXPECTED_USED_DOCUMENT_IDS_SHA256

    historical_rows = [
        row for row in used_rows if row["usage_type"] != "classifier_audit"
    ]
    assert len(historical_rows) == 152
    assert _lines_sha256(
        [
            ",".join(row[column] for column in USED_DOCUMENT_COLUMNS)
            for row in historical_rows
        ]
    ) == EXPECTED_HISTORICAL_USED_ROWS_SHA256

    classifier_rows = [
        row for row in used_rows if row["usage_type"] == "classifier_audit"
    ]
    classifier_ids = [row["identificador_boe"] for row in classifier_rows]
    assert classifier_ids == sorted(classifier_ids)
    assert all(
        row["usage_reason"] == "classifier_development_exposure"
        and row["source_reference"]
        == "docs/HOLDOUT_EXPOSURE_PROVENANCE.md"
        for row in classifier_rows
    )

    provenance = HOLDOUT_PROVENANCE_PATH.read_text(encoding="utf-8")
    provenance_rows = provenance.split(
        "<!-- classifier-audit-provenance:start -->", 1
    )[1].split("<!-- classifier-audit-provenance:end -->", 1)[0]
    documented_classifier_ids = re.findall(
        r"BOE-[AB]-\d{4}-\d+", provenance_rows
    )
    assert documented_classifier_ids == classifier_ids

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
    assert len(audit_rows) == 17
    assert len({row["identificador_boe"] for row in audit_rows}) == 10
    assert {row["audit_version"] for row in audit_rows} == {"1"}
    assert {row["challenge_sample_version"] for row in audit_rows} == {"1"}
    assert {row["run_scope"] for row in audit_rows} == {
        "development_challenge_v1"
    }
    assert Counter(row["human_decision"] for row in audit_rows) == {
        "CONFIRMED_MAJOR": 15,
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


def test_development_challenge_v2_human_audit_contract() -> None:
    challenge_columns, challenge_rows = _read_csv(CHALLENGE_PATH)
    v1_audit_columns, v1_audit_rows = _read_csv(HUMAN_AUDIT_PATH)
    v2_audit_columns, v2_audit_rows = _read_csv(HUMAN_AUDIT_V2_PATH)

    assert challenge_columns == CHALLENGE_COLUMNS
    assert v1_audit_columns == HUMAN_AUDIT_COLUMNS
    assert v2_audit_columns == HUMAN_AUDIT_V2_COLUMNS
    assert len(v2_audit_rows) == 9
    assert len({row["identificador_boe"] for row in v2_audit_rows}) == 9
    assert {row["audit_version"] for row in v2_audit_rows} == {"1"}
    assert {row["challenge_sample_version"] for row in v2_audit_rows} == {
        "1"
    }
    assert {row["run_scope"] for row in v2_audit_rows} == {
        "development_challenge_v2"
    }
    assert {row["extraction_config_id"] for row in v2_audit_rows} == {
        "24a5bff975c6fd66"
    }
    assert Counter(row["human_decision"] for row in v2_audit_rows) == {
        "CORRECTED_OK": 9,
    }
    assert Counter(row["candidate_assessment"] for row in v2_audit_rows) == {
        "appears_resolved": 7,
        "appears_correct": 2,
    }
    assert Counter(row["check_type"] for row in v2_audit_rows) == {
        "wrong_decision_v1": 6,
        "contradictory_action_v1": 1,
        "new_terminal_decision_v2": 2,
    }

    challenge_ids = {row["identificador_boe"] for row in challenge_rows}
    v2_audit_ids = {row["identificador_boe"] for row in v2_audit_rows}
    assert v2_audit_ids <= challenge_ids
    assert len(
        {
            (row["identificador_boe"], row["check_type"])
            for row in v2_audit_rows
        }
    ) == len(v2_audit_rows)
    assert all(
        value.strip()
        for row in v2_audit_rows
        for value in (row[column] for column in HUMAN_AUDIT_V2_COLUMNS)
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{32}", row["source_attempt_id"])
        for row in v2_audit_rows
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", row["source_document_sha256"])
        for row in v2_audit_rows
    )
    assert {row["reviewer_id"] for row in v2_audit_rows} == {
        "human_reviewer_1"
    }
    assert {row["reviewed_on"] for row in v2_audit_rows} == {"2026-08-08"}

    corresponding_v1_defect = {
        "wrong_decision_v1": "wrong_decision",
        "contradictory_action_v1": "contradictory_action",
    }
    v1_defects = {
        (row["identificador_boe"], row["defect_code"])
        for row in v1_audit_rows
    }
    derived_v1_checks = [
        row
        for row in v2_audit_rows
        if row["check_type"] in corresponding_v1_defect
    ]
    assert len(derived_v1_checks) == 7
    assert all(
        (
            row["identificador_boe"],
            corresponding_v1_defect[row["check_type"]],
        )
        in v1_defects
        for row in derived_v1_checks
    )

    new_v2_checks = [
        row
        for row in v2_audit_rows
        if row["check_type"] == "new_terminal_decision_v2"
    ]
    assert {row["identificador_boe"] for row in new_v2_checks} == {
        "BOE-A-2023-1938",
        "BOE-A-2025-18283",
    }
    v1_audit_ids = {row["identificador_boe"] for row in v1_audit_rows}
    assert {row["identificador_boe"] for row in new_v2_checks}.isdisjoint(
        v1_audit_ids
    )
