from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.app_data import (
    GoldDataset,
    GoldDatasetError,
    GoldIntegrityError,
    GoldManifestError,
    GoldVersionError,
    load_gold_dataset,
)
from renewables_permitting.downstream import (
    DOWNSTREAM_BUILD_VERSION,
    GOLD_MATERIALIZATION_CONTRACT_VERSION,
    compute_downstream_materialization_id,
)
from renewables_permitting.project_locations import (
    project_locations_semantic_hash,
)


SILVER_MATERIALIZATION_ID = "1" * 64
EXTRACTION_CONFIG_ID = "a1" * 8
INE_REFERENCE_SHA256 = "2" * 64
INE_REFERENCE_ID = INE_REFERENCE_SHA256[:16]
RESOLVED_LOCATIONS_ID = "3" * 64
PROJECT_GROUPING_ID = "4" * 64

TABLE_KEYS = {
    "projects": ("project_id",),
    "project_events": ("project_id", "administrative_action_id"),
    "project_locations": ("project_location_id",),
    "project_location_sources": (
        "project_location_id",
        "location_mention_id",
    ),
}


def _typed_frame(
    rows: list[dict[str, object]],
    dtypes: dict[str, str],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(dtypes))
    for column, dtype in dtypes.items():
        if dtype == "datetime64[ns]":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def synthetic_gold_tables() -> dict[str, pd.DataFrame]:
    """Return a minimal valid four-table Gold dataset for unit tests."""

    projects = _typed_frame(
        [{
            "project_id": "project_alpha",
            "project_name": "Parque Eólico Alfa",
            "technology": "eolica",
            "province_codes": "15",
            "provinces": "A Coruña",
            "municipality_codes": "15030",
            "municipalities": "A Coruña",
            "first_publication_date": "2024-01-10",
            "last_publication_date": "2024-01-10",
            "n_publications": 1,
            "n_administrative_actions": 1,
        }],
        {
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
    )
    project_events = _typed_frame(
        [{
            "project_id": "project_alpha",
            "event_id": "event_alpha",
            "administrative_action_id": "action_alpha",
            "boe_id": "BOE-A-2024-100",
            "publication_date": "2024-01-10",
            "event_index": 1,
            "administrative_action_index": 1,
            "action_type": "autorizacion_administrativa_previa",
            "decision": "autorizado",
            "is_modification": False,
            "evidence": "Se autoriza el parque eólico Alfa.",
        }],
        {
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
    )
    project_locations = _typed_frame(
        [{
            "project_location_id": "location_alpha",
            "project_id": "project_alpha",
            "location_level": "municipality",
            "municipality": "A Coruña",
            "municipality_norm": "a coruna",
            "ine_municipality_code": "15030",
            "province": "A Coruña",
            "province_norm": "a coruna",
            "ine_province_code": "15",
            "autonomous_community": "Galicia",
            "autonomous_community_norm": "galicia",
            "ine_autonomous_community_code": "12",
            "source_location_mention_count": 1,
            "source_publication_count": 1,
            "first_publication_date": "2024-01-10",
            "last_publication_date": "2024-01-10",
        }],
        {
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
    )
    project_location_sources = _typed_frame(
        [{
            "project_location_id": "location_alpha",
            "location_mention_id": "location_mention_alpha",
            "event_id": "event_alpha",
            "boe_id": "BOE-A-2024-100",
            "publication_date": "2024-01-10",
        }],
        {
            "project_location_id": "string",
            "location_mention_id": "string",
            "event_id": "string",
            "boe_id": "string",
            "publication_date": "datetime64[ns]",
        },
    )
    return {
        "projects": projects,
        "project_events": project_events,
        "project_locations": project_locations,
        "project_location_sources": project_location_sources,
    }


def _json_scalar(value: object) -> object:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _semantic_hash(frame: pd.DataFrame, key: tuple[str, ...]) -> str:
    ordered = frame.sort_values(list(key), kind="stable").reset_index(drop=True)
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


def _artifact_semantic_hashes(
    tables: dict[str, pd.DataFrame],
) -> dict[str, str]:
    return {
        "resolved_locations": RESOLVED_LOCATIONS_ID,
        "project_grouping": PROJECT_GROUPING_ID,
        **{
            name: _semantic_hash(frame, TABLE_KEYS[name])
            for name, frame in tables.items()
        },
    }


EXPECTED_DOWNSTREAM_ID = compute_downstream_materialization_id(
    silver_materialization_id=SILVER_MATERIALIZATION_ID,
    extraction_config_id=EXTRACTION_CONFIG_ID,
    ine_reference_sha256=INE_REFERENCE_SHA256,
    artifact_semantic_sha256=_artifact_semantic_hashes(
        synthetic_gold_tables()
    ),
)


def write_gold_dataset(
    gold_dir: Path,
    *,
    tables: dict[str, pd.DataFrame] | None = None,
    declared_downstream_id: str | None = None,
) -> Path:
    """Materialize one synthetic Gold fixture and its production-shaped manifest."""

    gold_dir.mkdir(parents=True, exist_ok=True)
    frames = tables or synthetic_gold_tables()
    metadata: dict[str, dict[str, object]] = {}
    reloaded_frames: dict[str, pd.DataFrame] = {}
    for name, frame in frames.items():
        path = gold_dir / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        reloaded = pd.read_parquet(path)
        reloaded_frames[name] = reloaded
        metadata[name] = {
            "filename": path.name,
            "row_count": len(reloaded),
            "schema": [
                {"name": column, "dtype": str(reloaded[column].dtype)}
                for column in reloaded.columns
            ],
            "primary_key": list(TABLE_KEYS[name]),
            "semantic_sha256": _semantic_hash(reloaded, TABLE_KEYS[name]),
            "parquet_sha256": sha256(path.read_bytes()).hexdigest(),
        }
    recomputed_downstream_id = compute_downstream_materialization_id(
        silver_materialization_id=SILVER_MATERIALIZATION_ID,
        extraction_config_id=EXTRACTION_CONFIG_ID,
        ine_reference_sha256=INE_REFERENCE_SHA256,
        artifact_semantic_sha256={
            "resolved_locations": RESOLVED_LOCATIONS_ID,
            "project_grouping": PROJECT_GROUPING_ID,
            **{
                name: str(table_metadata["semantic_sha256"])
                for name, table_metadata in metadata.items()
            },
        },
    )
    manifest = {
        "build_version": DOWNSTREAM_BUILD_VERSION,
        "contract_version": GOLD_MATERIALIZATION_CONTRACT_VERSION,
        "created_at": "2026-08-14T10:00:00Z",
        "downstream_materialization_id": (
            declared_downstream_id or recomputed_downstream_id
        ),
        "silver_materialization_id": SILVER_MATERIALIZATION_ID,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "ine_reference_id": INE_REFERENCE_ID,
        "ine_reference_sha256": INE_REFERENCE_SHA256,
        "resolved_locations_id": RESOLVED_LOCATIONS_ID,
        "project_grouping_id": PROJECT_GROUPING_ID,
        "project_locations_semantic_sha256": project_locations_semantic_hash(
            reloaded_frames["project_locations"],
            reloaded_frames["project_location_sources"],
        ),
        "tables": metadata,
    }
    (gold_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return gold_dir


def _rewrite_manifest(gold_dir: Path, mutate) -> None:
    path = gold_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_load_gold_dataset_reads_four_valid_tables(tmp_path: Path) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")

    dataset = load_gold_dataset(
        gold_dir,
        expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
    )

    assert isinstance(dataset, GoldDataset)
    assert dataset.downstream_id == EXPECTED_DOWNSTREAM_ID
    assert len(dataset.projects) == 1
    assert len(dataset.project_events) == 1
    assert len(dataset.project_locations) == 1
    assert len(dataset.project_location_sources) == 1
    with pytest.raises(FrozenInstanceError):
        dataset.downstream_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("prepare", "error"),
    [
        (lambda path: path, GoldDatasetError),
        (lambda path: (path.mkdir(), path)[1], GoldManifestError),
    ],
    ids=["missing-directory", "missing-manifest"],
)
def test_load_gold_dataset_rejects_missing_inputs(
    tmp_path: Path,
    prepare,
    error: type[Exception],
) -> None:
    gold_dir = prepare(tmp_path / "gold")

    with pytest.raises(error):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_invalid_json(tmp_path: Path) -> None:
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    (gold_dir / "manifest.json").write_text("{invalid", encoding="utf-8")

    with pytest.raises(GoldManifestError):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_internally_inconsistent_downstream_id(
    tmp_path: Path,
) -> None:
    gold_dir = write_gold_dataset(
        tmp_path / "gold",
        declared_downstream_id="0" * 64,
    )

    with pytest.raises(GoldIntegrityError, match="identidad"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_unexpected_valid_downstream_id(
    tmp_path: Path,
) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")

    with pytest.raises(GoldVersionError, match="versión"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id="0" * 64,
        )


def test_load_gold_dataset_rejects_coordinated_semantic_change_with_stale_id(
    tmp_path: Path,
) -> None:
    tables = synthetic_gold_tables()
    tables["projects"] = tables["projects"].copy()
    tables["projects"].loc[0, "project_name"] = "Parque Eólico Alfa Modificado"
    gold_dir = write_gold_dataset(
        tmp_path / "gold",
        tables=tables,
        declared_downstream_id=EXPECTED_DOWNSTREAM_ID,
    )

    with pytest.raises(GoldIntegrityError, match="identidad"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_missing_table(tmp_path: Path) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    (gold_dir / "project_events.parquet").unlink()

    with pytest.raises(GoldIntegrityError):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_unexpected_table(tmp_path: Path) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    synthetic_gold_tables()["projects"].to_parquet(
        gold_dir / "unexpected.parquet",
        index=False,
    )

    with pytest.raises(GoldManifestError, match="cuatro tablas"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_filename_outside_gold_dir(
    tmp_path: Path,
) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    _rewrite_manifest(
        gold_dir,
        lambda value: value["tables"]["projects"].update(
            filename="../projects.parquet"
        ),
    )

    with pytest.raises(GoldManifestError, match="filename"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_wrong_physical_hash(tmp_path: Path) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    _rewrite_manifest(
        gold_dir,
        lambda value: value["tables"]["projects"].update(
            parquet_sha256="0" * 64
        ),
    )

    with pytest.raises(GoldIntegrityError, match="hash"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_wrong_row_count(tmp_path: Path) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    _rewrite_manifest(
        gold_dir,
        lambda value: value["tables"]["projects"].update(row_count=2),
    )

    with pytest.raises(GoldIntegrityError, match="cardinalidad"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


@pytest.mark.parametrize("fault", ["columns", "dtype"])
def test_load_gold_dataset_rejects_wrong_schema(
    tmp_path: Path,
    fault: str,
) -> None:
    tables = synthetic_gold_tables()
    if fault == "columns":
        tables["projects"] = tables["projects"].rename(
            columns={"project_name": "wrong_name"}
        )
    else:
        tables["projects"]["n_publications"] = (
            tables["projects"]["n_publications"].astype("int64")
        )
    gold_dir = write_gold_dataset(tmp_path / "gold", tables=tables)

    with pytest.raises(GoldIntegrityError, match="esquema"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_duplicate_primary_key(tmp_path: Path) -> None:
    tables = synthetic_gold_tables()
    tables["projects"] = pd.concat(
        [tables["projects"], tables["projects"]],
        ignore_index=True,
    )
    gold_dir = write_gold_dataset(tmp_path / "gold", tables=tables)

    with pytest.raises(GoldIntegrityError, match="clave primaria"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_rejects_orphan_foreign_key(tmp_path: Path) -> None:
    tables = synthetic_gold_tables()
    tables["project_events"] = tables["project_events"].copy()
    tables["project_events"].loc[0, "project_id"] = "project_missing"
    gold_dir = write_gold_dataset(tmp_path / "gold", tables=tables)

    with pytest.raises(GoldIntegrityError, match="huérfan"):
        load_gold_dataset(
            gold_dir,
            expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
        )


def test_load_gold_dataset_does_not_modify_source_artifacts(tmp_path: Path) -> None:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    before = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in gold_dir.iterdir()
    }

    load_gold_dataset(
        gold_dir,
        expected_downstream_id=EXPECTED_DOWNSTREAM_ID,
    )

    after = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in gold_dir.iterdir()
    }
    assert after == before
