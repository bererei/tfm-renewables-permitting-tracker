from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from renewables_permitting.extraction.flat_materialization import (
    load_flat_materialization,
)
from renewables_permitting.gold import (
    PROJECT_EVENTS_COLUMNS,
    PROJECTS_COLUMNS,
    build_gold_tables,
)
from renewables_permitting.ine_reference import (
    load_municipality_reference,
)
from renewables_permitting.location_resolution import (
    LOCATION_RESOLUTION_COLUMNS,
    resolve_locations,
)
from renewables_permitting.project_grouping import (
    PROJECT_GROUPING_COLUMNS,
    group_projects,
)
from renewables_permitting.project_locations import (
    PROJECT_LOCATION_SOURCES_COLUMNS,
    PROJECT_LOCATIONS_COLUMNS,
    PROJECT_LOCATIONS_CONTRACT_VERSION,
    project_locations_semantic_hash,
)


DOWNSTREAM_CONTRACT_VERSION = "2"
DOWNSTREAM_BUILD_VERSION = "deterministic_downstream_v2"
GOLD_MATERIALIZATION_CONTRACT_VERSION = "2"

_RESOLVED_LOCATIONS_FILENAME = "resolved_locations.parquet"
_PROJECT_GROUPING_FILENAME = "project_grouping.parquet"
_DOWNSTREAM_MANIFEST_FILENAME = "downstream_manifest.json"
_GOLD_DIRECTORY = "gold"
_GOLD_MANIFEST_FILENAME = "manifest.json"
_PROJECTS_FILENAME = "projects.parquet"
_PROJECT_EVENTS_FILENAME = "project_events.parquet"
_PROJECT_LOCATIONS_FILENAME = "project_locations.parquet"
_PROJECT_LOCATION_SOURCES_FILENAME = "project_location_sources.parquet"


@dataclass(frozen=True)
class DownstreamResult:
    """Paths and deterministic identity of one published downstream snapshot."""

    output_dir: Path
    resolved_locations_path: Path
    project_grouping_path: Path
    projects_path: Path
    project_events_path: Path
    project_locations_path: Path
    project_location_sources_path: Path
    downstream_manifest_path: Path
    gold_manifest_path: Path
    materialization_id: str
    silver_materialization_id: str
    ine_reference_id: str


class DownstreamError(RuntimeError):
    """A downstream input, derivation or publication failed validation."""


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _schema(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [
        {"name": column, "dtype": str(frame[column].dtype)}
        for column in frame.columns
    ]


def _ordered(frame: pd.DataFrame, primary_key: tuple[str, ...]) -> pd.DataFrame:
    if frame.empty:
        return frame.reset_index(drop=True).copy()
    return frame.sort_values(list(primary_key), kind="stable").reset_index(
        drop=True
    )


def _semantic_sha256(
    frame: pd.DataFrame,
    *,
    primary_key: tuple[str, ...],
) -> str:
    ordered = _ordered(frame, primary_key)
    rows = [
        [_json_scalar(value) for value in row]
        for row in ordered.itertuples(index=False, name=None)
    ]
    return sha256(_canonical_json_bytes({
        "columns": list(ordered.columns),
        "rows": rows,
    })).hexdigest()


def _created_at_value(value: datetime | None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at debe incluir zona horaria.")
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_output_available(output_dir: Path) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(
            f"El directorio downstream ya existe: {output_dir}"
        )


def _cleanup_staging(
    staging_dir: Path,
    *,
    parent_dir: Path,
    staging_prefix: str,
) -> None:
    if staging_dir.parent != parent_dir:
        raise RuntimeError("Se rechazó limpiar un staging fuera del destino.")
    if not staging_dir.name.startswith(staging_prefix):
        raise RuntimeError("Se rechazó limpiar un staging inesperado.")
    if staging_dir.is_symlink():
        raise RuntimeError("Se rechazó limpiar un staging convertido en enlace.")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)


def _validate_resolved_locations(
    resolved: pd.DataFrame,
    location_mentions: pd.DataFrame,
) -> None:
    expected_columns = (
        *tuple(location_mentions.columns),
        *LOCATION_RESOLUTION_COLUMNS,
    )
    if tuple(resolved.columns) != expected_columns:
        raise ValueError("resolved_locations no conserva el esquema esperado.")
    if len(resolved) != len(location_mentions):
        raise ValueError("resolved_locations no conserva la cardinalidad Silver.")
    ids = resolved["location_mention_id"]
    if ids.isna().any() or ids.duplicated().any():
        raise ValueError("resolved_locations contiene IDs nulos o duplicados.")
    if set(ids.astype(str)) != set(
        location_mentions["location_mention_id"].astype(str)
    ):
        raise ValueError("resolved_locations no conserva los IDs Silver.")


def _validate_project_grouping(
    grouping: pd.DataFrame,
    generation_asset_mentions: pd.DataFrame,
) -> None:
    if tuple(grouping.columns) != PROJECT_GROUPING_COLUMNS:
        raise ValueError("project_grouping no conserva su contrato de columnas.")
    ids = grouping["generation_asset_mention_id"]
    if ids.isna().any() or ids.duplicated().any():
        raise ValueError("project_grouping contiene IDs nulos o duplicados.")
    if set(ids.astype(str)) != set(
        generation_asset_mentions["generation_asset_mention_id"].astype(str)
    ):
        raise ValueError("project_grouping no cubre exactamente los assets Silver.")


def _validate_gold_tables(tables: Mapping[str, pd.DataFrame]) -> None:
    expected_tables = {
        "projects",
        "project_events",
        "project_locations",
        "project_location_sources",
    }
    if set(tables) != expected_tables:
        raise ValueError("Gold debe contener exactamente sus cuatro tablas.")
    projects = tables["projects"]
    project_events = tables["project_events"]
    project_locations = tables["project_locations"]
    project_location_sources = tables["project_location_sources"]
    if tuple(projects.columns) != PROJECTS_COLUMNS:
        raise ValueError("projects no conserva su contrato de columnas.")
    if tuple(project_events.columns) != PROJECT_EVENTS_COLUMNS:
        raise ValueError("project_events no conserva su contrato de columnas.")
    if tuple(project_locations.columns) != PROJECT_LOCATIONS_COLUMNS:
        raise ValueError("project_locations no conserva su contrato de columnas.")
    if tuple(project_location_sources.columns) != (
        PROJECT_LOCATION_SOURCES_COLUMNS
    ):
        raise ValueError(
            "project_location_sources no conserva su contrato de columnas."
        )
    if projects["project_id"].isna().any() or projects[
        "project_id"
    ].duplicated().any():
        raise ValueError("projects contiene una PK nula o duplicada.")
    event_pk = ["project_id", "administrative_action_id"]
    if project_events[event_pk].isna().any().any() or project_events.duplicated(
        event_pk
    ).any():
        raise ValueError("project_events contiene una PK nula o duplicada.")
    if set(project_events["project_id"].astype(str)) - set(
        projects["project_id"].astype(str)
    ):
        raise ValueError("project_events contiene project_id huérfanos.")
    if project_locations["project_location_id"].isna().any() or (
        project_locations["project_location_id"].duplicated().any()
    ):
        raise ValueError("project_locations contiene una PK nula o duplicada.")
    source_pk = ["project_location_id", "location_mention_id"]
    if project_location_sources[source_pk].isna().any().any() or (
        project_location_sources.duplicated(source_pk).any()
    ):
        raise ValueError(
            "project_location_sources contiene una PK nula o duplicada."
        )
    if set(project_locations["project_id"].astype(str)) - set(
        projects["project_id"].astype(str)
    ):
        raise ValueError("project_locations contiene project_id huérfanos.")
    location_ids = set(project_locations["project_location_id"].astype(str))
    source_location_ids = set(
        project_location_sources["project_location_id"].astype(str)
    )
    if source_location_ids - location_ids:
        raise ValueError(
            "project_location_sources contiene project_location_id huérfanos."
        )
    if location_ids - source_location_ids:
        raise ValueError("project_locations contiene filas sin fuente.")


def _write_verified_parquet(
    frame: pd.DataFrame,
    path: Path,
    *,
    primary_key: tuple[str, ...],
) -> dict[str, Any]:
    ordered = _ordered(frame, primary_key)
    ordered.to_parquet(path, index=False)
    reloaded = pd.read_parquet(path)
    try:
        pd.testing.assert_frame_equal(
            reloaded,
            ordered,
            check_dtype=True,
            check_exact=True,
        )
    except AssertionError as error:
        raise ValueError(
            f"El round trip Parquet cambió {path.name!r}."
        ) from error
    return {
        "filename": path.name,
        "row_count": len(reloaded),
        "schema": _schema(reloaded),
        "primary_key": list(primary_key),
        "semantic_sha256": _semantic_sha256(
            reloaded,
            primary_key=primary_key,
        ),
        "parquet_sha256": _sha256_file(path),
    }


def _write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    serializable = dict(payload)
    path.write_text(
        json.dumps(
            serializable,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    if json.loads(path.read_text(encoding="utf-8")) != serializable:
        raise ValueError(f"El manifest {path.name!r} no supera el round trip.")


def _downstream_materialization_id(
    *,
    silver_materialization_id: str,
    extraction_config_id: str,
    ine_reference_sha256: str,
    artifacts: Mapping[str, Mapping[str, Any]],
) -> str:
    payload = {
        "contract_version": DOWNSTREAM_CONTRACT_VERSION,
        "build_version": DOWNSTREAM_BUILD_VERSION,
        "gold_contract_version": GOLD_MATERIALIZATION_CONTRACT_VERSION,
        "silver_materialization_id": silver_materialization_id,
        "extraction_config_id": extraction_config_id,
        "ine_reference_sha256": ine_reference_sha256,
        "artifact_semantic_sha256": {
            name: metadata["semantic_sha256"]
            for name, metadata in sorted(artifacts.items())
        },
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def run_downstream(
    *,
    silver_snapshot: Path,
    municipality_reference: Path,
    output_dir: Path,
    expected_extraction_config_id: str,
    created_at: datetime | None = None,
) -> DownstreamResult:
    """Build and atomically publish all deterministic outputs after Silver.

    The input boundary is one manifest-verified 13-table Silver snapshot plus
    one manifest-verified municipality reference snapshot. The function runs
    the existing location resolver, project grouping and Gold builders over
    the complete Silver history, validates every derived table and publishes a
    run-scoped snapshot. The caller is responsible for obtaining any required
    confirmation before calling this non-interactive API.
    """

    output_dir = Path(output_dir).absolute()
    _validate_output_available(output_dir)
    try:
        silver = load_flat_materialization(
            silver_snapshot,
            expected_extraction_config_id=expected_extraction_config_id,
        )
    except Exception as error:
        raise DownstreamError(f"Silver validation failed: {error}") from error
    try:
        ine = load_municipality_reference(municipality_reference)
    except Exception as error:
        raise DownstreamError(f"INE validation failed: {error}") from error

    tables = silver.tables
    try:
        resolved_locations = resolve_locations(
            tables["location_mentions"],
            ine.dimension,
        )
        _validate_resolved_locations(
            resolved_locations,
            tables["location_mentions"],
        )
    except Exception as error:
        raise DownstreamError(f"Location resolution failed: {error}") from error
    try:
        project_grouping = group_projects(
            tables["generation_asset_mentions"],
            tables["generation_asset_names"],
            resolved_locations,
        )
        _validate_project_grouping(
            project_grouping,
            tables["generation_asset_mentions"],
        )
    except Exception as error:
        raise DownstreamError(f"Project grouping failed: {error}") from error
    try:
        gold_tables = build_gold_tables(
            publication_events=tables["publication_events"],
            generation_asset_mentions=tables["generation_asset_mentions"],
            generation_asset_names=tables["generation_asset_names"],
            administrative_actions=tables["administrative_actions"],
            administrative_action_targets=tables[
                "administrative_action_targets"
            ],
            associated_component_generation_links=tables[
                "associated_component_generation_links"
            ],
            project_grouping=project_grouping,
            resolved_locations=resolved_locations,
        )
        _validate_gold_tables(gold_tables)
    except Exception as error:
        raise DownstreamError(f"Gold build failed: {error}") from error

    created_at_value = _created_at_value(created_at)
    parent_dir = output_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    staging_prefix = f".{output_dir.name}.staging-"
    staging_dir = Path(tempfile.mkdtemp(
        prefix=staging_prefix,
        dir=parent_dir,
    ))
    published = False
    try:
        gold_dir = staging_dir / _GOLD_DIRECTORY
        gold_dir.mkdir()
        artifact_metadata = {
            "resolved_locations": _write_verified_parquet(
                resolved_locations,
                staging_dir / _RESOLVED_LOCATIONS_FILENAME,
                primary_key=("location_mention_id",),
            ),
            "project_grouping": _write_verified_parquet(
                project_grouping,
                staging_dir / _PROJECT_GROUPING_FILENAME,
                primary_key=("generation_asset_mention_id",),
            ),
            "projects": _write_verified_parquet(
                gold_tables["projects"],
                gold_dir / _PROJECTS_FILENAME,
                primary_key=("project_id",),
            ),
            "project_events": _write_verified_parquet(
                gold_tables["project_events"],
                gold_dir / _PROJECT_EVENTS_FILENAME,
                primary_key=("project_id", "administrative_action_id"),
            ),
            "project_locations": _write_verified_parquet(
                gold_tables["project_locations"],
                gold_dir / _PROJECT_LOCATIONS_FILENAME,
                primary_key=("project_location_id",),
            ),
            "project_location_sources": _write_verified_parquet(
                gold_tables["project_location_sources"],
                gold_dir / _PROJECT_LOCATION_SOURCES_FILENAME,
                primary_key=("project_location_id", "location_mention_id"),
            ),
        }
        artifact_metadata["resolved_locations"]["lineage"] = {
            "silver_materialization_id": silver.materialization_id,
            "extraction_config_id": silver.extraction_config_id,
            "ine_reference_id": ine.semantic_reference_id,
        }
        artifact_metadata["project_grouping"]["lineage"] = {
            "silver_materialization_id": silver.materialization_id,
            "extraction_config_id": silver.extraction_config_id,
            "ine_reference_id": ine.semantic_reference_id,
            "resolved_locations_id": artifact_metadata[
                "resolved_locations"
            ]["semantic_sha256"],
        }
        location_sources = [
            "projects",
            "publication_events",
            "generation_asset_mentions",
            "project_grouping",
            "resolved_locations",
        ]
        artifact_metadata["project_locations"]["sources"] = location_sources
        artifact_metadata["project_locations"]["contract_version"] = (
            PROJECT_LOCATIONS_CONTRACT_VERSION
        )
        artifact_metadata["project_locations"]["lineage"] = {
            "silver_materialization_id": silver.materialization_id,
            "extraction_config_id": silver.extraction_config_id,
            "ine_reference_id": ine.semantic_reference_id,
            "resolved_locations_id": artifact_metadata[
                "resolved_locations"
            ]["semantic_sha256"],
            "project_grouping_id": artifact_metadata[
                "project_grouping"
            ]["semantic_sha256"],
        }
        artifact_metadata["project_location_sources"]["sources"] = [
            "project_locations",
            "resolved_locations",
            "publication_events",
        ]
        artifact_metadata["project_location_sources"]["contract_version"] = (
            PROJECT_LOCATIONS_CONTRACT_VERSION
        )
        artifact_metadata["project_location_sources"]["lineage"] = dict(
            artifact_metadata["project_locations"]["lineage"]
        )
        project_location_sources = gold_tables["project_location_sources"]
        resolved_source_mentions = project_location_sources[
            "location_mention_id"
        ].nunique()
        project_locations_audit = {
            "source_location_mentions": len(resolved_locations),
            "resolved_source_location_mentions": resolved_source_mentions,
            "unresolved_source_location_mentions_omitted": (
                len(resolved_locations) - resolved_source_mentions
            ),
            "multiproject_source_expansions": (
                len(project_location_sources) - resolved_source_mentions
            ),
        }
        project_locations_bundle_hash = project_locations_semantic_hash(
            gold_tables["project_locations"],
            project_location_sources,
        )
        materialization_id = _downstream_materialization_id(
            silver_materialization_id=silver.materialization_id,
            extraction_config_id=silver.extraction_config_id,
            ine_reference_sha256=ine.semantic_reference_sha256,
            artifacts=artifact_metadata,
        )
        gold_manifest = {
            "contract_version": GOLD_MATERIALIZATION_CONTRACT_VERSION,
            "build_version": DOWNSTREAM_BUILD_VERSION,
            "created_at": created_at_value,
            "downstream_materialization_id": materialization_id,
            "silver_materialization_id": silver.materialization_id,
            "extraction_config_id": silver.extraction_config_id,
            "ine_reference_id": ine.semantic_reference_id,
            "ine_reference_sha256": ine.semantic_reference_sha256,
            "resolved_locations_id": artifact_metadata[
                "resolved_locations"
            ]["semantic_sha256"],
            "project_grouping_id": artifact_metadata[
                "project_grouping"
            ]["semantic_sha256"],
            "project_locations_semantic_sha256": (
                project_locations_bundle_hash
            ),
            "project_locations_audit": project_locations_audit,
            "tables": {
                "projects": artifact_metadata["projects"],
                "project_events": artifact_metadata["project_events"],
                "project_locations": artifact_metadata[
                    "project_locations"
                ],
                "project_location_sources": artifact_metadata[
                    "project_location_sources"
                ],
            },
        }
        _write_manifest(gold_dir / _GOLD_MANIFEST_FILENAME, gold_manifest)
        downstream_manifest = {
            "contract_version": DOWNSTREAM_CONTRACT_VERSION,
            "build_version": DOWNSTREAM_BUILD_VERSION,
            "materialization_id": materialization_id,
            "created_at": created_at_value,
            "silver": {
                "materialization_id": silver.materialization_id,
                "extraction_config_id": silver.extraction_config_id,
            },
            "ine_reference": {
                "semantic_reference_id": ine.semantic_reference_id,
                "semantic_reference_sha256": ine.semantic_reference_sha256,
            },
            "artifacts": {
                "resolved_locations": artifact_metadata[
                    "resolved_locations"
                ],
                "project_grouping": artifact_metadata["project_grouping"],
            },
            "gold": {
                "directory": _GOLD_DIRECTORY,
                "manifest": _GOLD_MANIFEST_FILENAME,
                "materialization_id": materialization_id,
            },
        }
        _write_manifest(
            staging_dir / _DOWNSTREAM_MANIFEST_FILENAME,
            downstream_manifest,
        )
        expected_root = {
            _RESOLVED_LOCATIONS_FILENAME,
            _PROJECT_GROUPING_FILENAME,
            _DOWNSTREAM_MANIFEST_FILENAME,
            _GOLD_DIRECTORY,
        }
        expected_gold = {
            _PROJECTS_FILENAME,
            _PROJECT_EVENTS_FILENAME,
            _PROJECT_LOCATIONS_FILENAME,
            _PROJECT_LOCATION_SOURCES_FILENAME,
            _GOLD_MANIFEST_FILENAME,
        }
        if {path.name for path in staging_dir.iterdir()} != expected_root:
            raise ValueError("El staging downstream contiene artefactos inesperados.")
        if {path.name for path in gold_dir.iterdir()} != expected_gold:
            raise ValueError("El staging Gold contiene artefactos inesperados.")

        _validate_output_available(output_dir)
        staging_dir.rename(output_dir)
        published = True
    except Exception as error:
        raise DownstreamError(
            f"Downstream materialization failed: {error}"
        ) from error
    finally:
        if not published:
            _cleanup_staging(
                staging_dir,
                parent_dir=parent_dir,
                staging_prefix=staging_prefix,
            )

    return DownstreamResult(
        output_dir=output_dir,
        resolved_locations_path=output_dir / _RESOLVED_LOCATIONS_FILENAME,
        project_grouping_path=output_dir / _PROJECT_GROUPING_FILENAME,
        projects_path=output_dir / _GOLD_DIRECTORY / _PROJECTS_FILENAME,
        project_events_path=(
            output_dir / _GOLD_DIRECTORY / _PROJECT_EVENTS_FILENAME
        ),
        project_locations_path=(
            output_dir / _GOLD_DIRECTORY / _PROJECT_LOCATIONS_FILENAME
        ),
        project_location_sources_path=(
            output_dir
            / _GOLD_DIRECTORY
            / _PROJECT_LOCATION_SOURCES_FILENAME
        ),
        downstream_manifest_path=(
            output_dir / _DOWNSTREAM_MANIFEST_FILENAME
        ),
        gold_manifest_path=(
            output_dir / _GOLD_DIRECTORY / _GOLD_MANIFEST_FILENAME
        ),
        materialization_id=materialization_id,
        silver_materialization_id=silver.materialization_id,
        ine_reference_id=ine.semantic_reference_id,
    )
