from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from renewables_permitting.extraction.models import (
    AdministrativeActionType,
    AdministrativeDecision,
)


HISTORICAL_ANTECEDENT_REVIEW_COLUMNS = (
    "review_version",
    "status",
    "outcome",
    "boe_id",
    "administrative_action_id",
    "source_document_sha256",
    "expected_action_type",
    "expected_decision",
    "expected_evidence_sha256",
    "reason_code",
    "detector_policy_version",
    "review_reason",
    "decision_source",
    "reviewed_on",
    "reviewer",
)
HISTORICAL_ANTECEDENT_CURRENT_OUTCOME = "current"
HISTORICAL_ANTECEDENT_REASON_CODE = "possible_historical_antecedent"

_STRING_COLUMNS = tuple(
    column
    for column in HISTORICAL_ANTECEDENT_REVIEW_COLUMNS
    if column != "review_version"
)
_BOE_ID_PATTERN = re.compile(r"BOE-[AB]-\d{4}-\d+")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_VERSION_PATTERN = re.compile(r"[1-9]\d*")


class HistoricalAntecedentReviewError(ValueError):
    """A persistent human resolution is invalid or ambiguous."""


@dataclass(frozen=True)
class LoadedHistoricalAntecedentReviews:
    """Validated CURRENT decisions plus physical and semantic identities."""

    reviews: pd.DataFrame
    source_path: Path
    logical_path: str
    file_sha256: str
    semantic_identity: str


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _logical_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def empty_historical_antecedent_reviews() -> pd.DataFrame:
    """Return the typed, header-only v1 decision contract."""

    dataframe = pd.DataFrame(columns=HISTORICAL_ANTECEDENT_REVIEW_COLUMNS)
    for column in HISTORICAL_ANTECEDENT_REVIEW_COLUMNS:
        dataframe[column] = dataframe[column].astype(
            "Int64" if column == "review_version" else "string"
        )
    return dataframe


def _non_empty_text(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return dataframe[column].notna() & dataframe[column].str.strip().ne("")


def validate_historical_antecedent_reviews(
    reviews: pd.DataFrame,
) -> pd.DataFrame:
    """Validate explicit action-level CURRENT decisions without data edits."""

    if not isinstance(reviews, pd.DataFrame):
        raise TypeError("reviews debe ser un pandas.DataFrame.")
    if not reviews.columns.is_unique:
        raise HistoricalAntecedentReviewError(
            "El registro de revisiones contiene columnas duplicadas."
        )
    if tuple(reviews.columns) != HISTORICAL_ANTECEDENT_REVIEW_COLUMNS:
        raise HistoricalAntecedentReviewError(
            "Las columnas del registro de revisiones históricas no coinciden "
            f"con el contrato: {list(HISTORICAL_ANTECEDENT_REVIEW_COLUMNS)!r}."
        )
    if reviews.empty:
        return empty_historical_antecedent_reviews()

    validated = reviews.copy(deep=True)
    for column in _STRING_COLUMNS:
        validated[column] = validated[column].astype("string")
        if not _non_empty_text(validated, column).all():
            raise HistoricalAntecedentReviewError(
                f"La columna {column!r} contiene valores vacíos o nulos."
            )

    version_text = validated["review_version"].astype("string")
    if not version_text.map(
        lambda value: bool(_VERSION_PATTERN.fullmatch(str(value)))
    ).all():
        raise HistoricalAntecedentReviewError(
            "review_version debe contener enteros positivos."
        )
    validated["review_version"] = version_text.astype("Int64")
    if not validated["review_version"].eq(1).all():
        raise HistoricalAntecedentReviewError(
            "review_version solo admite la versión 1."
        )

    for column, expected in (
        ("status", "approved"),
        ("outcome", HISTORICAL_ANTECEDENT_CURRENT_OUTCOME),
        ("reason_code", HISTORICAL_ANTECEDENT_REASON_CODE),
    ):
        invalid = ~validated[column].eq(expected)
        if invalid.any():
            raise HistoricalAntecedentReviewError(
                f"{column} contiene un dominio no admitido: "
                f"{sorted(validated.loc[invalid, column].unique())!r}."
            )

    if not validated["boe_id"].map(
        lambda value: bool(_BOE_ID_PATTERN.fullmatch(str(value)))
    ).all():
        raise HistoricalAntecedentReviewError(
            "boe_id contiene identificadores BOE no válidos."
        )
    expected_action_ids = validated.apply(
        lambda row: bool(re.fullmatch(
            re.escape(str(row["boe_id"]))
            + r"_event_[1-9]\d*_action_[1-9]\d*",
            str(row["administrative_action_id"]),
        )),
        axis=1,
    )
    if not expected_action_ids.all():
        raise HistoricalAntecedentReviewError(
            "administrative_action_id no pertenece al BOE declarado."
        )

    action_types = {member.value for member in AdministrativeActionType}
    decisions = {member.value for member in AdministrativeDecision}
    if not validated["expected_action_type"].isin(action_types).all():
        raise HistoricalAntecedentReviewError(
            "expected_action_type contiene valores fuera del contrato."
        )
    if not validated["expected_decision"].isin(decisions).all():
        raise HistoricalAntecedentReviewError(
            "expected_decision contiene valores fuera del contrato."
        )
    for column in (
        "source_document_sha256",
        "expected_evidence_sha256",
    ):
        if not validated[column].map(
            lambda value: bool(_SHA256_PATTERN.fullmatch(str(value)))
        ).all():
            raise HistoricalAntecedentReviewError(
                f"{column} debe ser SHA-256 hexadecimal minúsculo."
            )

    exact_identity_columns = [
        "boe_id",
        "administrative_action_id",
        "source_document_sha256",
        "expected_action_type",
        "expected_decision",
        "expected_evidence_sha256",
        "reason_code",
        "detector_policy_version",
    ]
    if validated.duplicated(subset=exact_identity_columns).any():
        raise HistoricalAntecedentReviewError(
            "El mismo finding contiene más de una decisión CURRENT."
        )

    try:
        normalized_dates = validated["reviewed_on"].map(
            lambda value: date.fromisoformat(str(value)).isoformat()
        )
    except ValueError as error:
        raise HistoricalAntecedentReviewError(
            "reviewed_on debe usar una fecha ISO YYYY-MM-DD válida."
        ) from error
    validated["reviewed_on"] = normalized_dates.astype("string")
    absolute_source = validated["decision_source"].str.match(
        r"^(?:/|[A-Za-z]:[\\/])"
    )
    if absolute_source.any():
        raise HistoricalAntecedentReviewError(
            "decision_source no puede contener rutas absolutas."
        )
    return validated.reset_index(drop=True)


def historical_antecedent_reviews_identity(reviews: pd.DataFrame) -> str:
    """Return a row-order-independent semantic SHA-256 for the registry."""

    validated = validate_historical_antecedent_reviews(reviews)
    records = [
        {
            column: (
                int(row[column])
                if column == "review_version"
                else str(row[column])
            )
            for column in HISTORICAL_ANTECEDENT_REVIEW_COLUMNS
        }
        for row in validated.to_dict(orient="records")
    ]
    records.sort(key=lambda record: tuple(
        str(record[column])
        for column in HISTORICAL_ANTECEDENT_REVIEW_COLUMNS
    ))
    return sha256(_canonical_json_bytes({
        "contract": "historical_antecedent_reviews_v1",
        "records": records,
    })).hexdigest()


def historical_antecedent_review_id(row: Mapping[str, Any]) -> str:
    """Derive a stable identifier; humans never enter hashes by hand."""

    record = {
        column: (
            int(row[column])
            if column == "review_version"
            else str(row[column])
        )
        for column in HISTORICAL_ANTECEDENT_REVIEW_COLUMNS
    }
    return sha256(_canonical_json_bytes(record)).hexdigest()[:24]


def load_historical_antecedent_reviews(
    path: Path,
) -> LoadedHistoricalAntecedentReviews:
    """Load one explicit, versioned CURRENT-decision CSV."""

    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(
            f"No existe un fichero regular de revisiones históricas: {path}"
        )
    try:
        raw = pd.read_csv(path, dtype="string", keep_default_na=False)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as error:
        raise HistoricalAntecedentReviewError(
            "No se pudo leer el CSV de revisiones históricas."
        ) from error
    validated = validate_historical_antecedent_reviews(raw)
    return LoadedHistoricalAntecedentReviews(
        reviews=validated,
        source_path=path.absolute(),
        logical_path=_logical_path(path),
        file_sha256=_file_sha256(path),
        semantic_identity=historical_antecedent_reviews_identity(validated),
    )
