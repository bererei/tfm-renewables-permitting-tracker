"""Verified, read-only loading boundary for the Streamlit Gold dataset."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from renewables_permitting.downstream import (
    DOWNSTREAM_BUILD_VERSION,
    GOLD_MATERIALIZATION_CONTRACT_VERSION,
    compute_downstream_materialization_id,
)
from renewables_permitting.gold import PROJECT_EVENTS_COLUMNS, PROJECTS_COLUMNS
from renewables_permitting.project_locations import (
    PROJECT_LOCATION_SOURCES_COLUMNS,
    PROJECT_LOCATIONS_COLUMNS,
    project_locations_semantic_hash,
)


_TABLE_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "projects": PROJECTS_COLUMNS,
    "project_events": PROJECT_EVENTS_COLUMNS,
    "project_locations": PROJECT_LOCATIONS_COLUMNS,
    "project_location_sources": PROJECT_LOCATION_SOURCES_COLUMNS,
}
_TABLE_DTYPES: Mapping[str, Mapping[str, str]] = {
    "projects": {
        "project_id": "string",
        "project_name": "string",
        "technology": "string",
        "province_codes": "string",
        "provinces": "string",
        "municipality_codes": "string",
        "municipalities": "string",
        "first_publication_date": "datetime64[ns]",
        "last_publication_date": "datetime64[ns]",
        "n_publications": "Int64",
        "n_administrative_actions": "Int64",
    },
    "project_events": {
        "project_id": "string",
        "event_id": "string",
        "administrative_action_id": "string",
        "boe_id": "string",
        "publication_date": "datetime64[ns]",
        "event_index": "Int64",
        "administrative_action_index": "Int64",
        "action_type": "string",
        "decision": "string",
        "is_modification": "boolean",
        "evidence": "string",
    },
    "project_locations": {
        "project_location_id": "string",
        "project_id": "string",
        "location_level": "string",
        "municipality": "string",
        "municipality_norm": "string",
        "ine_municipality_code": "string",
        "province": "string",
        "province_norm": "string",
        "ine_province_code": "string",
        "autonomous_community": "string",
        "autonomous_community_norm": "string",
        "ine_autonomous_community_code": "string",
        "source_location_mention_count": "Int64",
        "source_publication_count": "Int64",
        "first_publication_date": "datetime64[ns]",
        "last_publication_date": "datetime64[ns]",
    },
    "project_location_sources": {
        "project_location_id": "string",
        "location_mention_id": "string",
        "event_id": "string",
        "boe_id": "string",
        "publication_date": "datetime64[ns]",
    },
}
_TABLE_PRIMARY_KEYS: Mapping[str, tuple[str, ...]] = {
    "projects": ("project_id",),
    "project_events": ("project_id", "administrative_action_id"),
    "project_locations": ("project_location_id",),
    "project_location_sources": (
        "project_location_id",
        "location_mention_id",
    ),
}
_TABLE_FILENAMES: Mapping[str, str] = {
    name: f"{name}.parquet" for name in _TABLE_COLUMNS
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GoldDatasetError(RuntimeError):
    """A Gold dataset cannot be loaded safely for the application."""


class GoldManifestError(GoldDatasetError):
    """The Gold manifest is missing, malformed or contractually incompatible."""


class GoldVersionError(GoldManifestError):
    """The Gold snapshot identity or version differs from the configured one."""


class GoldIntegrityError(GoldDatasetError):
    """A Gold artifact does not match the integrity declared by its manifest."""


class GoldSchemaError(GoldIntegrityError):
    """A Gold table does not have its expected application-facing schema."""


@dataclass(frozen=True)
class GoldDataset:
    """Validated Gold inputs consumed as read-only values by application queries.

    The dataclass prevents attribute reassignment. Query functions always return
    copies and must treat the contained DataFrames as immutable source values.
    """

    projects: pd.DataFrame
    project_events: pd.DataFrame
    project_locations: pd.DataFrame
    project_location_sources: pd.DataFrame
    manifest: Mapping[str, Any]
    gold_dir: Path
    downstream_id: str


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without modifying it."""

    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_scalar(value: Any) -> Any:
    """Convert pandas values to the canonical JSON representation used by Gold."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _semantic_sha256(frame: pd.DataFrame, primary_key: tuple[str, ...]) -> str:
    """Reproduce the deterministic table semantic hash from downstream."""

    ordered = frame.sort_values(list(primary_key), kind="stable").reset_index(
        drop=True
    )
    payload = {
        "columns": list(ordered.columns),
        "rows": [
            [_json_scalar(value) for value in row]
            for row in ordered.itertuples(index=False, name=None)
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _schema(frame: pd.DataFrame) -> list[dict[str, str]]:
    """Describe a DataFrame using the schema representation in the manifest."""

    return [
        {"name": column, "dtype": str(frame[column].dtype)}
        for column in frame.columns
    ]


def _freeze_json(value: Any) -> Any:
    """Detach parsed JSON values from local mutable parsing state."""

    if isinstance(value, dict):
        return {key: _freeze_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _read_manifest(gold_dir: Path) -> dict[str, Any]:
    """Read and minimally shape-check a Gold manifest."""

    manifest_path = gold_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise GoldManifestError("Falta el manifest del dataset Gold.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoldManifestError("El manifest Gold no contiene JSON válido.") from error
    if not isinstance(manifest, dict):
        raise GoldManifestError("El manifest Gold no es un objeto JSON.")
    return manifest


def _validate_manifest(
    manifest: Mapping[str, Any],
) -> Mapping[str, Mapping[str, Any]]:
    """Validate snapshot identity, contract versions and table declarations."""

    if (
        manifest.get("contract_version")
        != GOLD_MATERIALIZATION_CONTRACT_VERSION
        or manifest.get("build_version") != DOWNSTREAM_BUILD_VERSION
    ):
        raise GoldVersionError("La versión del dataset no coincide con la esperada.")
    for field_name in (
        "downstream_materialization_id",
        "silver_materialization_id",
        "ine_reference_sha256",
        "resolved_locations_id",
        "project_grouping_id",
    ):
        value = manifest.get(field_name)
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise GoldManifestError(
                f"El campo contractual {field_name!r} no es válido."
            )
    extraction_config_id = manifest.get("extraction_config_id")
    if (
        not isinstance(extraction_config_id, str)
        or not extraction_config_id.strip()
    ):
        raise GoldManifestError(
            "El manifest Gold no declara una configuración de extracción válida."
        )
    ine_reference_id = manifest.get("ine_reference_id")
    if (
        not isinstance(ine_reference_id, str)
        or ine_reference_id != str(manifest["ine_reference_sha256"])[:16]
    ):
        raise GoldManifestError(
            "La identidad de la referencia INE no es válida."
        )
    tables = manifest.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(_TABLE_COLUMNS):
        raise GoldManifestError("Gold debe declarar exactamente sus cuatro tablas.")
    for name, metadata in tables.items():
        if not isinstance(metadata, dict):
            raise GoldManifestError(
                f"La declaración de la tabla {name!r} no es válida."
            )
        if metadata.get("filename") != _TABLE_FILENAMES[name]:
            raise GoldManifestError(
                f"El filename declarado para {name!r} no es válido."
            )
        if metadata.get("primary_key") != list(_TABLE_PRIMARY_KEYS[name]):
            raise GoldManifestError(
                f"La clave primaria declarada para {name!r} no es válida."
            )
    return tables


def _validated_table_path(
    gold_dir: Path,
    *,
    table_name: str,
    filename: str,
) -> Path:
    """Resolve a table path and reject path traversal or external symlinks."""

    root = gold_dir.resolve(strict=True)
    candidate = gold_dir / filename
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise GoldIntegrityError(
            f"No se encontró un artefacto válido para {table_name!r}."
        ) from error
    if not resolved.is_file():
        raise GoldIntegrityError(
            f"No se encontró un artefacto válido para {table_name!r}."
        )
    return resolved


def _load_and_validate_table(
    gold_dir: Path,
    *,
    table_name: str,
    metadata: Mapping[str, Any],
) -> pd.DataFrame:
    """Load one table only after its path, hash and manifest metadata are valid."""

    path = _validated_table_path(
        gold_dir,
        table_name=table_name,
        filename=str(metadata["filename"]),
    )
    expected_hash = metadata.get("parquet_sha256")
    if not isinstance(expected_hash, str) or _sha256_file(path) != expected_hash:
        raise GoldIntegrityError(
            f"El hash físico de {table_name!r} no coincide con el manifest."
        )
    try:
        frame = pd.read_parquet(path)
    except Exception as error:
        raise GoldIntegrityError(
            f"No se pudo leer de forma segura la tabla {table_name!r}."
        ) from error
    if metadata.get("row_count") != len(frame):
        raise GoldIntegrityError(
            f"La cardinalidad de {table_name!r} no coincide con el manifest."
        )
    expected_columns = _TABLE_COLUMNS[table_name]
    expected_schema = [
        {"name": column, "dtype": _TABLE_DTYPES[table_name][column]}
        for column in expected_columns
    ]
    if (
        tuple(frame.columns) != expected_columns
        or _schema(frame) != expected_schema
        or metadata.get("schema") != expected_schema
    ):
        raise GoldSchemaError(
            f"El esquema de {table_name!r} no coincide con el contrato."
        )
    primary_key = _TABLE_PRIMARY_KEYS[table_name]
    expected_semantic_hash = metadata.get("semantic_sha256")
    if (
        not isinstance(expected_semantic_hash, str)
        or _semantic_sha256(frame, primary_key) != expected_semantic_hash
    ):
        raise GoldIntegrityError(
            f"El hash semántico de {table_name!r} no coincide con el manifest."
        )
    return frame


def _validate_primary_keys(tables: Mapping[str, pd.DataFrame]) -> None:
    """Reject null or duplicate values in every declared Gold primary key."""

    for name, key in _TABLE_PRIMARY_KEYS.items():
        values = tables[name].loc[:, list(key)]
        if values.isna().any().any() or values.duplicated().any():
            raise GoldIntegrityError(
                f"La clave primaria de {name!r} contiene nulos o duplicados."
            )


def _as_text_set(series: pd.Series) -> set[str]:
    """Return non-null string values as a set for relational checks."""

    return set(series.dropna().astype(str))


def _validate_foreign_keys(tables: Mapping[str, pd.DataFrame]) -> None:
    """Validate project, location and publication-event relationships."""

    projects = tables["projects"]
    events = tables["project_events"]
    locations = tables["project_locations"]
    sources = tables["project_location_sources"]
    project_ids = _as_text_set(projects["project_id"])
    if _as_text_set(events["project_id"]) - project_ids:
        raise GoldIntegrityError("project_events contiene project_id huérfanos.")
    if _as_text_set(locations["project_id"]) - project_ids:
        raise GoldIntegrityError("project_locations contiene project_id huérfanos.")
    location_ids = _as_text_set(locations["project_location_id"])
    source_location_ids = _as_text_set(sources["project_location_id"])
    if source_location_ids - location_ids:
        raise GoldIntegrityError(
            "project_location_sources contiene localizaciones huérfanas."
        )
    if location_ids - source_location_ids:
        raise GoldIntegrityError("project_locations contiene filas sin fuente.")
    event_ids = _as_text_set(events["event_id"])
    if _as_text_set(sources["event_id"]) - event_ids:
        raise GoldIntegrityError(
            "project_location_sources contiene eventos huérfanos."
        )
    event_publications = set(
        events.loc[:, ["event_id", "boe_id", "publication_date"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    source_publications = set(
        sources.loc[:, ["event_id", "boe_id", "publication_date"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    if source_publications - event_publications:
        raise GoldIntegrityError(
            "project_location_sources contiene publicaciones huérfanas."
        )


def load_gold_dataset(
    gold_dir: Path,
    *,
    expected_downstream_id: str,
) -> GoldDataset:
    """Load and fully verify the four-table Gold snapshot used by the app.

    The function is pure with respect to repository state: it only reads the
    configured directory, does not cache, and never rewrites its artifacts.
    """

    directory = Path(gold_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise GoldDatasetError("El directorio del dataset Gold no está disponible.")
    manifest = _read_manifest(directory)
    metadata = _validate_manifest(manifest)
    expected_parquets = set(_TABLE_FILENAMES.values())
    actual_parquets = {path.name for path in directory.glob("*.parquet")}
    if expected_parquets - actual_parquets:
        raise GoldIntegrityError("Falta una tabla contractual del dataset Gold.")
    if actual_parquets - expected_parquets:
        raise GoldManifestError("Gold debe contener exactamente sus cuatro tablas.")
    tables = {
        name: _load_and_validate_table(
            directory,
            table_name=name,
            metadata=metadata[name],
        )
        for name in _TABLE_COLUMNS
    }
    _validate_primary_keys(tables)
    _validate_foreign_keys(tables)
    expected_bundle_hash = manifest.get("project_locations_semantic_sha256")
    actual_bundle_hash = project_locations_semantic_hash(
        tables["project_locations"],
        tables["project_location_sources"],
    )
    if (
        not isinstance(expected_bundle_hash, str)
        or actual_bundle_hash != expected_bundle_hash
    ):
        raise GoldIntegrityError(
            "El hash semántico conjunto de localizaciones no coincide."
        )
    recomputed_downstream_id = compute_downstream_materialization_id(
        silver_materialization_id=str(manifest["silver_materialization_id"]),
        extraction_config_id=str(manifest["extraction_config_id"]),
        ine_reference_sha256=str(manifest["ine_reference_sha256"]),
        artifact_semantic_sha256={
            "resolved_locations": str(manifest["resolved_locations_id"]),
            "project_grouping": str(manifest["project_grouping_id"]),
            **{
                name: str(metadata[name]["semantic_sha256"])
                for name in _TABLE_COLUMNS
            },
        },
    )
    if recomputed_downstream_id != manifest["downstream_materialization_id"]:
        raise GoldIntegrityError(
            "La identidad contractual del dataset no coincide con su contenido."
        )
    if recomputed_downstream_id != expected_downstream_id:
        raise GoldVersionError(
            "La versión del dataset no coincide con la esperada."
        )
    return GoldDataset(
        projects=tables["projects"],
        project_events=tables["project_events"],
        project_locations=tables["project_locations"],
        project_location_sources=tables["project_location_sources"],
        manifest=_freeze_json(manifest),
        gold_dir=directory.resolve(),
        downstream_id=recomputed_downstream_id,
    )
