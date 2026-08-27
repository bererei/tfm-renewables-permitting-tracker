from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    BOEProjectExtraction,
)


ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS = (
    "correction_id",
    "correction_version",
    "status",
    "boe_id",
    "entity_type",
    "operation",
    "administrative_action_id",
    "expected_action_type",
    "expected_decision",
    "expected_evidence_sha256",
    "reason_code",
    "reason",
    "decision_source",
    "reviewed_on",
    "reviewer",
)
APPLIED_CORRECTION_COLUMNS = (
    "correction_id",
    "correction_version",
    "boe_id",
    "entity_type",
    "entity_id",
    "operation",
    "reason_code",
    "source_action_type",
    "source_decision",
    "source_evidence_sha256",
    "corrections_file_sha256",
    "corrections_identity",
    "source_extraction_snapshot_id",
    "source_extraction_config_id",
    "applied",
)

_STRING_CORRECTION_COLUMNS = tuple(
    column
    for column in ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS
    if column != "correction_version"
)
_CORRECTION_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_BOE_ID_PATTERN = re.compile(r"BOE-[AB]-\d{4}-\d+")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_VERSION_PATTERN = re.compile(r"[1-9]\d*")
_REASON_CODE = "historical_antecedent_misattributed"


class AdministrativeActionCorrectionError(ValueError):
    """An approved entity correction is invalid or cannot match exactly."""


@dataclass(frozen=True)
class LoadedAdministrativeActionCorrections:
    """Validated registry plus its physical and semantic identities."""

    corrections: pd.DataFrame
    source_path: Path
    logical_path: str
    file_sha256: str
    semantic_identity: str


@dataclass(frozen=True)
class AdministrativeActionCorrectionResult:
    """Effective extraction copy and one audit row per applied correction."""

    effective_current_extractions: pd.DataFrame
    applied_corrections: pd.DataFrame


@dataclass(frozen=True)
class _ActionTarget:
    """One action located in the immutable source extraction structure."""

    row_position: int
    event_index: int
    action_index: int
    action: AdministrativeAction
    extraction_config_id: str


def _canonical_json_bytes(value: Any) -> bytes:
    """Serialize a correction identity without ordering or spacing ambiguity."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _logical_path(path: Path) -> str:
    """Represent a registry path without leaking an absolute machine path."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _file_sha256(path: Path) -> str:
    """Hash the exact versioned registry bytes read from disk."""

    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalise_evidence_for_sha256(evidence: str) -> str:
    """Apply minimal stable NFC, line-ending and edge-space normalization."""

    if not isinstance(evidence, str) or not evidence.strip():
        raise AdministrativeActionCorrectionError(
            "La evidencia debe ser texto no vacío para calcular su huella."
        )
    normalized = unicodedata.normalize("NFC", evidence)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.strip()


def evidence_sha256(evidence: str) -> str:
    """Hash minimally normalized evidence as UTF-8 SHA-256."""

    return sha256(
        normalise_evidence_for_sha256(evidence).encode("utf-8")
    ).hexdigest()


def historical_action_exclusion_correction_id(
    *,
    boe_id: str,
    administrative_action_id: str,
    expected_action_type: str,
    expected_decision: str,
    expected_evidence_sha256: str,
) -> str:
    """Derive the stable technical ID for one exact historical exclusion.

    The complete correction row remains subject to the closed v1 registry
    validator.  Keeping human reason, reviewer and date outside this identity
    makes repeated derivation of the same target deterministic.
    """

    payload = {
        "contract": "administrative_action_corrections_v1",
        "correction_version": 1,
        "entity_type": "administrative_action",
        "operation": "exclude",
        "reason_code": _REASON_CODE,
        "boe_id": str(boe_id),
        "administrative_action_id": str(administrative_action_id),
        "expected_action_type": str(expected_action_type),
        "expected_decision": str(expected_decision),
        "expected_evidence_sha256": str(expected_evidence_sha256),
    }
    digest = sha256(_canonical_json_bytes(payload)).hexdigest()[:24]
    return f"historical-action-exclusion-v1-{digest}"


def _non_empty_text(dataframe: pd.DataFrame, column: str) -> pd.Series:
    """Return a null-safe mask for required non-empty string cells."""

    return dataframe[column].notna() & dataframe[column].str.strip().ne("")


def validate_administrative_action_corrections(
    corrections: pd.DataFrame,
) -> pd.DataFrame:
    """Validate and type the closed v1 administrative-action registry."""

    if not isinstance(corrections, pd.DataFrame):
        raise TypeError("corrections debe ser un pandas.DataFrame.")
    if not corrections.columns.is_unique:
        raise AdministrativeActionCorrectionError(
            "El registro contiene columnas duplicadas."
        )
    if tuple(corrections.columns) != ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS:
        raise AdministrativeActionCorrectionError(
            "Las columnas del registro de correcciones no coinciden exactamente "
            f"con el contrato: {list(ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS)!r}."
        )
    if corrections.empty:
        raise AdministrativeActionCorrectionError(
            "El registro de correcciones no puede estar vacío."
        )

    validated = corrections.copy(deep=True)
    for column in _STRING_CORRECTION_COLUMNS:
        validated[column] = validated[column].astype("string")
        if not _non_empty_text(validated, column).all():
            raise AdministrativeActionCorrectionError(
                f"La columna {column!r} contiene valores vacíos o nulos."
            )

    version_text = validated["correction_version"].astype("string")
    if not version_text.map(
        lambda value: bool(_VERSION_PATTERN.fullmatch(str(value)))
    ).all():
        raise AdministrativeActionCorrectionError(
            "correction_version debe contener enteros positivos."
        )
    validated["correction_version"] = version_text.astype("Int64")
    if not validated["correction_version"].eq(1).all():
        raise AdministrativeActionCorrectionError(
            "correction_version solo admite la versión 1."
        )

    if not validated["correction_id"].map(
        lambda value: bool(_CORRECTION_ID_PATTERN.fullmatch(str(value)))
    ).all():
        raise AdministrativeActionCorrectionError(
            "correction_id debe usar un identificador estable lower-kebab-case."
        )
    if validated["correction_id"].duplicated().any():
        raise AdministrativeActionCorrectionError(
            "correction_id contiene identificadores duplicados."
        )
    for column, expected in (
        ("status", "approved"),
        ("entity_type", "administrative_action"),
        ("operation", "exclude"),
        ("reason_code", _REASON_CODE),
    ):
        invalid = ~validated[column].eq(expected)
        if invalid.any():
            raise AdministrativeActionCorrectionError(
                f"{column} contiene un dominio no admitido: "
                f"{sorted(validated.loc[invalid, column].unique())!r}."
            )

    if not validated["boe_id"].map(
        lambda value: bool(_BOE_ID_PATTERN.fullmatch(str(value)))
    ).all():
        raise AdministrativeActionCorrectionError(
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
        raise AdministrativeActionCorrectionError(
            "administrative_action_id no pertenece al BOE declarado o no es "
            "un identificador materializado válido."
        )

    action_types = {member.value for member in AdministrativeActionType}
    decisions = {member.value for member in AdministrativeDecision}
    if not validated["expected_action_type"].isin(action_types).all():
        raise AdministrativeActionCorrectionError(
            "expected_action_type contiene valores fuera del contrato."
        )
    if not validated["expected_decision"].isin(decisions).all():
        raise AdministrativeActionCorrectionError(
            "expected_decision contiene valores fuera del contrato."
        )
    if not validated["expected_evidence_sha256"].map(
        lambda value: bool(_SHA256_PATTERN.fullmatch(str(value)))
    ).all():
        raise AdministrativeActionCorrectionError(
            "expected_evidence_sha256 debe ser SHA-256 hexadecimal minúsculo."
        )
    duplicate_targets = validated.duplicated(
        subset=["boe_id", "administrative_action_id"], keep=False
    )
    if duplicate_targets.any():
        raise AdministrativeActionCorrectionError(
            "El mismo target administrativo aparece en varias correcciones."
        )

    try:
        normalized_dates = validated["reviewed_on"].map(
            lambda value: date.fromisoformat(str(value)).isoformat()
        )
    except ValueError as error:
        raise AdministrativeActionCorrectionError(
            "reviewed_on debe usar una fecha ISO YYYY-MM-DD válida."
        ) from error
    validated["reviewed_on"] = normalized_dates.astype("string")
    absolute_source = validated["decision_source"].str.match(
        r"^(?:/|[A-Za-z]:[\\/])"
    )
    if absolute_source.any():
        raise AdministrativeActionCorrectionError(
            "decision_source no puede contener rutas absolutas."
        )
    return validated.reset_index(drop=True)


def corrections_identity(corrections: pd.DataFrame) -> str:
    """Build a row-order-independent semantic SHA-256 for the registry."""

    validated = validate_administrative_action_corrections(corrections)
    records = [
        {
            column: (
                int(row[column])
                if column == "correction_version"
                else str(row[column])
            )
            for column in ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS
        }
        for row in validated.to_dict(orient="records")
    ]
    records.sort(key=lambda record: record["correction_id"])
    payload = {
        "contract": "administrative_action_corrections_v1",
        "records": records,
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def load_administrative_action_corrections(
    path: Path,
) -> LoadedAdministrativeActionCorrections:
    """Load one explicit CSV registry and validate it before application."""

    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(
            f"No existe un fichero de correcciones regular: {path}"
        )
    try:
        raw = pd.read_csv(path, dtype="string", keep_default_na=False)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as error:
        raise AdministrativeActionCorrectionError(
            "No se pudo leer el CSV de correcciones."
        ) from error
    validated = validate_administrative_action_corrections(raw)
    return LoadedAdministrativeActionCorrections(
        corrections=validated,
        source_path=path.absolute(),
        logical_path=_logical_path(path),
        file_sha256=_file_sha256(path),
        semantic_identity=corrections_identity(validated),
    )


def empty_administrative_action_corrections() -> pd.DataFrame:
    """Build the typed header-only schema used by a derived empty subset."""

    dataframe = pd.DataFrame(columns=ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS)
    for column in ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS:
        if column == "correction_version":
            dataframe[column] = dataframe[column].astype("Int64")
        else:
            dataframe[column] = dataframe[column].astype("string")
    return dataframe


def _typed_applied_corrections(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the stable audit-sidecar DataFrame and its explicit dtypes."""

    dataframe = pd.DataFrame(records, columns=APPLIED_CORRECTION_COLUMNS)
    for column in APPLIED_CORRECTION_COLUMNS:
        if column == "correction_version":
            dataframe[column] = dataframe[column].astype("Int64")
        elif column == "applied":
            dataframe[column] = dataframe[column].astype("boolean")
        else:
            dataframe[column] = dataframe[column].astype("string")
    return dataframe


def _source_targets(
    current_extractions: pd.DataFrame,
) -> tuple[list[BOEProjectExtraction], dict[tuple[str, str], list[_ActionTarget]]]:
    """Index immutable source actions by BOE and materialized action ID."""

    models: list[BOEProjectExtraction] = []
    targets: dict[tuple[str, str], list[_ActionTarget]] = {}
    for row_position, row in enumerate(
        current_extractions.to_dict(orient="records")
    ):
        try:
            extraction = BOEProjectExtraction.model_validate_json(
                str(row["extraction_json"])
            )
        except (TypeError, ValueError) as error:
            raise AdministrativeActionCorrectionError(
                "current_extractions contiene extraction_json no válido."
            ) from error
        if str(row["identificador_boe"]) != extraction.boe_id:
            raise AdministrativeActionCorrectionError(
                "identificador_boe no coincide con el JSON canónico."
            )
        extraction_config_id = row["extraction_config_id"]
        if not isinstance(extraction_config_id, str) or not extraction_config_id:
            raise AdministrativeActionCorrectionError(
                "La extracción fuente no contiene extraction_config_id."
            )
        models.append(extraction)
        for event_index, event in enumerate(
            extraction.publication_events, start=1
        ):
            for action_index, action in enumerate(
                event.administrative_actions, start=1
            ):
                action_id = (
                    f"{extraction.boe_id}_event_{event_index}"
                    f"_action_{action_index}"
                )
                targets.setdefault((extraction.boe_id, action_id), []).append(
                    _ActionTarget(
                        row_position=row_position,
                        event_index=event_index,
                        action_index=action_index,
                        action=action,
                        extraction_config_id=extraction_config_id,
                    )
                )
    return models, targets


def apply_administrative_action_corrections(
    current_extractions: pd.DataFrame,
    corrections: LoadedAdministrativeActionCorrections,
    *,
    source_extraction_snapshot_id: str,
) -> AdministrativeActionCorrectionResult:
    """Apply approved exclusions to a deep copy after exact fingerprint checks."""

    if not isinstance(current_extractions, pd.DataFrame):
        raise TypeError("current_extractions debe ser un pandas.DataFrame.")
    if not current_extractions.columns.is_unique:
        raise AdministrativeActionCorrectionError(
            "current_extractions contiene columnas duplicadas."
        )
    required = {
        "identificador_boe",
        "extraction_config_id",
        "extraction_json",
    }
    missing = sorted(required - set(current_extractions.columns))
    if missing:
        raise AdministrativeActionCorrectionError(
            f"current_extractions no contiene {missing!r}."
        )
    if not isinstance(corrections, LoadedAdministrativeActionCorrections):
        raise TypeError(
            "corrections debe proceder de load_administrative_action_corrections."
        )
    if (
        not isinstance(source_extraction_snapshot_id, str)
        or not source_extraction_snapshot_id.strip()
    ):
        raise AdministrativeActionCorrectionError(
            "source_extraction_snapshot_id debe ser texto no vacío."
        )
    registry = validate_administrative_action_corrections(
        corrections.corrections
    )
    if corrections.semantic_identity != corrections_identity(registry):
        raise AdministrativeActionCorrectionError(
            "La identidad semántica del registro no coincide con su contenido."
        )

    models, target_index = _source_targets(current_extractions)
    removals: dict[tuple[int, int], set[int]] = {}
    applied_records: list[dict[str, Any]] = []
    for correction in sorted(
        registry.to_dict(orient="records"),
        key=lambda row: str(row["correction_id"]),
    ):
        key = (
            str(correction["boe_id"]),
            str(correction["administrative_action_id"]),
        )
        matches = target_index.get(key, [])
        if len(matches) != 1:
            raise AdministrativeActionCorrectionError(
                f"La corrección {correction['correction_id']!r} encontró "
                f"{len(matches)} targets; se requiere exactamente 1."
            )
        target = matches[0]
        actual_fingerprint = (
            target.action.action_type.value,
            target.action.decision.value,
            evidence_sha256(target.action.evidence),
        )
        expected_fingerprint = (
            str(correction["expected_action_type"]),
            str(correction["expected_decision"]),
            str(correction["expected_evidence_sha256"]),
        )
        if actual_fingerprint != expected_fingerprint:
            raise AdministrativeActionCorrectionError(
                f"La corrección {correction['correction_id']!r} coincide por "
                "ID pero no por fingerprint semántico."
            )
        removals.setdefault(
            (target.row_position, target.event_index), set()
        ).add(target.action_index)
        applied_records.append({
            "correction_id": str(correction["correction_id"]),
            "correction_version": int(correction["correction_version"]),
            "boe_id": str(correction["boe_id"]),
            "entity_type": str(correction["entity_type"]),
            "entity_id": str(correction["administrative_action_id"]),
            "operation": str(correction["operation"]),
            "reason_code": str(correction["reason_code"]),
            "source_action_type": actual_fingerprint[0],
            "source_decision": actual_fingerprint[1],
            "source_evidence_sha256": actual_fingerprint[2],
            "corrections_file_sha256": corrections.file_sha256,
            "corrections_identity": corrections.semantic_identity,
            "source_extraction_snapshot_id": source_extraction_snapshot_id,
            "source_extraction_config_id": target.extraction_config_id,
            "applied": True,
        })

    effective = current_extractions.copy(deep=True)
    extraction_column = effective.columns.get_loc("extraction_json")
    for row_position, extraction in enumerate(models):
        if not any(key[0] == row_position for key in removals):
            continue
        effective_events = []
        for event_index, event in enumerate(
            extraction.publication_events, start=1
        ):
            excluded_indices = removals.get((row_position, event_index), set())
            if not excluded_indices:
                effective_events.append(event.model_copy(deep=True))
                continue
            actions = [
                action.model_copy(deep=True)
                for action_index, action in enumerate(
                    event.administrative_actions, start=1
                )
                if action_index not in excluded_indices
            ]
            if not actions:
                raise AdministrativeActionCorrectionError(
                    "Una corrección dejaría un evento sin actuaciones "
                    f"administrativas: {extraction.boe_id}_event_{event_index}."
                )
            effective_events.append(event.model_copy(
                update={"administrative_actions": actions},
                deep=True,
            ))
        effective_extraction = BOEProjectExtraction.model_validate(
            extraction.model_copy(
                update={"publication_events": effective_events},
                deep=True,
            ).model_dump()
        )
        effective.iat[row_position, extraction_column] = (
            effective_extraction.model_dump_json()
        )

    return AdministrativeActionCorrectionResult(
        effective_current_extractions=effective,
        applied_corrections=_typed_applied_corrections(applied_records),
    )
