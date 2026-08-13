from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.flat_contract import (
    FLAT_CONTRACT_VERSION,
    FLAT_TABLE_SPECS,
    FlatTableSpec,
)
from renewables_permitting.extraction.flat_validation import (
    validate_flat_tables,
)
from renewables_permitting.extraction.flatten import (
    flatten_current_extractions,
)
from renewables_permitting.extraction.models import BOEProjectExtraction


_MANIFEST_FILENAME = "manifest.json"
_LINEAGE_COLUMNS = (
    "identificador_boe",
    "attempt_id",
    "source_document_sha256",
    "extraction_config_id",
    "selection_source",
    "manual_review_id",
    "source_attempt_id",
)
_ERROR_SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class FlatMaterializationResult:
    """Describe una versión Silver publicada correctamente."""

    output_dir: Path
    manifest_path: Path
    table_paths: Mapping[str, Path]
    row_counts: Mapping[str, int]
    materialization_id: str


@dataclass(frozen=True)
class LoadedFlatMaterialization:
    """Silver snapshot reloaded only after full manifest verification."""

    input_dir: Path
    manifest_path: Path
    tables: Mapping[str, pd.DataFrame]
    materialization_id: str
    extraction_config_id: str
    manifest: Mapping[str, Any]


class FlatMaterializationError(RuntimeError):
    """Indica que una materialización no superó su verificación."""


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
    if bool(pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _sorted_contract_table(
    dataframe: pd.DataFrame,
    table_spec: FlatTableSpec,
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.reset_index(drop=True).copy()
    return dataframe.sort_values(
        list(table_spec.primary_key),
        kind="stable",
    ).reset_index(drop=True)


def _semantic_table_sha256(
    dataframe: pd.DataFrame,
    table_spec: FlatTableSpec,
) -> str:
    ordered = _sorted_contract_table(dataframe, table_spec)
    rows = [
        [_json_scalar(value) for value in row]
        for row in ordered.itertuples(index=False, name=None)
    ]
    payload = {
        "columns": list(table_spec.column_names),
        "rows": rows,
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _semantic_table_hashes(
    tables: Mapping[str, pd.DataFrame],
) -> dict[str, str]:
    return {
        table_name: _semantic_table_sha256(
            tables[table_name],
            table_spec,
        )
        for table_name, table_spec in FLAT_TABLE_SPECS.items()
    }


def _semantic_tables_equal(
    original: Mapping[str, pd.DataFrame],
    reloaded: Mapping[str, pd.DataFrame],
) -> None:
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        expected = _sorted_contract_table(
            original[table_name],
            table_spec,
        )
        actual = _sorted_contract_table(
            reloaded[table_name],
            table_spec,
        )
        try:
            pd.testing.assert_frame_equal(
                actual,
                expected,
                check_dtype=True,
                check_exact=True,
                check_like=False,
            )
        except AssertionError as error:
            raise FlatMaterializationError(
                f"La tabla releída {table_name!r} no es "
                "semánticamente equivalente a la original."
            ) from error


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _arrow_schema_payload(schema: pa.Schema) -> list[dict[str, Any]]:
    return [
        {
            "name": field.name,
            "type": str(field.type),
            "nullable": field.nullable,
        }
        for field in schema
    ]


def _write_contract_parquet(
    dataframe: pd.DataFrame,
    path: Path,
    table_spec: FlatTableSpec,
) -> None:
    arrow_table = pa.Table.from_pandas(
        dataframe,
        schema=table_spec.arrow_schema,
        preserve_index=False,
        safe=True,
    )
    pq.write_table(arrow_table, path)


def _read_contract_parquet(
    path: Path,
    table_spec: FlatTableSpec,
) -> pd.DataFrame:
    arrow_table = pq.read_table(path)
    if not arrow_table.schema.equals(
        table_spec.arrow_schema,
        check_metadata=False,
    ):
        raise FlatMaterializationError(
            f"El esquema Arrow de {table_spec.name!r} no coincide con "
            "el contrato."
        )
    return arrow_table.to_pandas()


def _normalise_lineage_records(
    records: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    if records is None:
        return [], []
    if not isinstance(records, (list, tuple)):
        raise TypeError("manifest_context['lineage'] debe ser una secuencia.")

    normalised: list[dict[str, Any]] = []
    available_columns: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError(
                "Cada registro de linaje debe ser un mapping."
            )
        selected: dict[str, Any] = {}
        for column in _LINEAGE_COLUMNS:
            if column not in record:
                continue
            selected[column] = _json_scalar(record[column])
            available_columns.add(column)
        normalised.append(selected)

    normalised.sort(key=lambda record: _canonical_json_bytes(record))
    columns = [
        column for column in _LINEAGE_COLUMNS
        if column in available_columns
    ]
    return columns, normalised


def _context_count(
    context: Mapping[str, Any],
    name: str,
) -> int:
    if name not in context:
        raise FlatMaterializationError(
            f"manifest_context debe incluir el conteo documental {name!r}."
        )
    value = context[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlatMaterializationError(
            f"manifest_context[{name!r}] debe ser un entero >= 0."
        )
    return value


def _normalise_manifest_context(
    manifest_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if manifest_context is None:
        raise FlatMaterializationError(
            "materialize_flat_tables requiere manifest_context con los tres "
            "conteos documentales exactos."
        )
    if not isinstance(manifest_context, Mapping):
        raise FlatMaterializationError(
            "manifest_context debe ser un mapping con conteos documentales."
        )
    context = manifest_context

    input_row_count = _context_count(
        context,
        "input_row_count",
    )
    input_with_events_count = _context_count(
        context,
        "input_with_events_count",
    )
    input_without_events_count = _context_count(
        context,
        "input_without_events_count",
    )
    if input_with_events_count + input_without_events_count != input_row_count:
        raise FlatMaterializationError(
            "Los conteos de entrada con y sin eventos no suman "
            "input_row_count."
        )

    lineage_columns, lineage = _normalise_lineage_records(
        context.get("lineage")
    )
    if "lineage" in context and len(lineage) != input_row_count:
        raise FlatMaterializationError(
            "La cardinalidad del linaje debe coincidir con "
            f"input_row_count: linaje={len(lineage)}; "
            f"entradas={input_row_count}."
        )
    return {
        "extraction_config_id": context.get("extraction_config_id"),
        "input_row_count": input_row_count,
        "input_with_events_count": input_with_events_count,
        "input_without_events_count": input_without_events_count,
        "lineage_columns": lineage_columns,
        "lineage": lineage,
    }


def _is_missing_text(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        return False
    return not isinstance(value, str) or not value.strip()


def _provenance_sample_boe_ids(
    current_extractions: pd.DataFrame,
    mask: pd.Series,
) -> list[str]:
    if "identificador_boe" not in current_extractions.columns:
        return ["<missing-identificador_boe>"]
    return sorted({
        str(value)
        for value in current_extractions.loc[mask, "identificador_boe"]
        if not _is_missing_text(value)
    })[:_ERROR_SAMPLE_LIMIT]


def _validate_current_extractions_provenance(
    current_extractions: pd.DataFrame,
    *,
    expected_extraction_config_id: str,
) -> None:
    """Bloquea Selected/Current incompatible antes de crear staging Silver."""

    if _is_missing_text(expected_extraction_config_id):
        raise ValueError(
            "expected_extraction_config_id debe ser texto no vacío."
        )
    if current_extractions.empty:
        return
    required_columns = (
        "identificador_boe",
        "attempt_id",
        "source_document_sha256",
        "extraction_config_id",
        "contract_schema_sha256",
        "instructions_sha256",
        "model_provider",
        "model_name",
        "document_validation_version",
        "selection_source",
        "extraction_json",
    )
    missing_columns = [
        column for column in required_columns
        if column not in current_extractions.columns
    ]
    if missing_columns:
        raise FlatMaterializationError(
            "current_extractions no contiene el linaje obligatorio: "
            f"columnas_faltantes={missing_columns!r}."
        )
    config_missing = current_extractions["extraction_config_id"].map(
        _is_missing_text
    )
    config_mismatch = ~current_extractions[
        "extraction_config_id"
    ].eq(expected_extraction_config_id).fillna(False)
    if config_mismatch.any():
        found_configs = sorted({
            str(value)
            for value in current_extractions.loc[
                ~config_missing,
                "extraction_config_id",
            ]
        })
        raise FlatMaterializationError(
            "Configuración de extracción incompatible antes de Silver: "
            f"expected={expected_extraction_config_id!r}; "
            f"found={found_configs!r}; "
            f"falta={int(config_missing.sum())}; "
            "sample_boe_ids="
            f"{_provenance_sample_boe_ids(current_extractions, config_mismatch)!r}."
        )

    expected_values = {
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }
    for column, expected in expected_values.items():
        mismatch = ~current_extractions[column].eq(expected).fillna(False)
        if mismatch.any():
            found = sorted({
                str(value)
                for value in current_extractions.loc[
                    ~current_extractions[column].map(_is_missing_text),
                    column,
                ]
            })
            raise FlatMaterializationError(
                f"Linaje incompatible en {column!r}: expected={expected!r}; "
                f"found={found!r}; sample_boe_ids="
                f"{_provenance_sample_boe_ids(current_extractions, mismatch)!r}."
            )

    for column in (
        "identificador_boe",
        "attempt_id",
        "source_document_sha256",
        "extraction_json",
    ):
        missing = current_extractions[column].map(_is_missing_text)
        if missing.any():
            raise FlatMaterializationError(
                f"Falta el campo de procedencia obligatorio {column!r}; "
                "sample_boe_ids="
                f"{_provenance_sample_boe_ids(current_extractions, missing)!r}."
            )

    selection = current_extractions["selection_source"]
    invalid_selection = ~selection.isin(
        ["auto_validated", "manually_validated"]
    ).fillna(False)
    if invalid_selection.any():
        raise FlatMaterializationError(
            "selection_source debe ser auto_validated o manually_validated; "
            "sample_boe_ids="
            f"{_provenance_sample_boe_ids(current_extractions, invalid_selection)!r}."
        )

    manual = selection.eq("manually_validated").fillna(False)
    automatic = ~manual
    deterministic_origin = (
        current_extractions["attempt_origin"].astype("string").isin(
            ["deterministic", "deterministic_reissued"]
        )
        if "attempt_origin" in current_extractions.columns
        else pd.Series(False, index=current_extractions.index)
    )
    model_backed = automatic & ~deterministic_origin
    for column, expected in (
        ("model_provider", MODEL_PROVIDER),
        ("model_name", AI_MODEL_NAME),
    ):
        mismatch = model_backed & ~current_extractions[column].eq(
            expected
        ).fillna(False)
        if mismatch.any():
            raise FlatMaterializationError(
                f"Linaje automático incompatible en {column!r}; "
                f"expected={expected!r}; sample_boe_ids="
                f"{_provenance_sample_boe_ids(current_extractions, mismatch)!r}."
            )

    if manual.any():
        for column, expected in (
            ("model_provider", "manual"),
            ("model_name", "human_review"),
        ):
            mismatch = manual & ~current_extractions[column].eq(
                expected
            ).fillna(False)
            if mismatch.any():
                raise FlatMaterializationError(
                    f"Linaje manual incompatible en {column!r}; "
                    f"expected={expected!r}; sample_boe_ids="
                    f"{_provenance_sample_boe_ids(current_extractions, mismatch)!r}."
                )
        for column in ("manual_review_id", "source_attempt_id"):
            if column not in current_extractions.columns:
                raise FlatMaterializationError(
                    "El linaje manual requiere la columna "
                    f"{column!r}."
                )
            missing = manual & current_extractions[column].map(
                _is_missing_text
            )
            if missing.any():
                raise FlatMaterializationError(
                    f"El linaje manual requiere {column!r}; sample_boe_ids="
                    f"{_provenance_sample_boe_ids(current_extractions, missing)!r}."
                )


def _current_context(
    current_extractions: pd.DataFrame,
    *,
    extraction_config_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    models: list[BOEProjectExtraction] = []
    identity: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    lineage_columns = [
        column for column in _LINEAGE_COLUMNS
        if column in current_extractions.columns
    ]
    canonical_boe_ids: list[str] = []
    inconsistent_boe_ids: list[tuple[str, Any]] = []

    for row in current_extractions.to_dict(orient="records"):
        extraction = BOEProjectExtraction.model_validate_json(
            str(row["extraction_json"])
        )
        models.append(extraction)
        canonical_boe_ids.append(extraction.boe_id)
        if "identificador_boe" in row:
            row_boe_id = row["identificador_boe"]
            if (
                not isinstance(row_boe_id, str)
                or row_boe_id != extraction.boe_id
            ):
                inconsistent_boe_ids.append(
                    (extraction.boe_id, row_boe_id)
                )
        lineage_record = {
            column: row[column]
            for column in lineage_columns
        }
        lineage.append(lineage_record)
        canonical_extraction = extraction.model_dump(mode="json")
        identity.append({
            **{
                column: _json_scalar(row[column])
                for column in lineage_columns
                if column != "identificador_boe"
            },
            "identificador_boe": extraction.boe_id,
            "canonical_extraction_sha256": sha256(
                _canonical_json_bytes(canonical_extraction)
            ).hexdigest(),
        })

    if inconsistent_boe_ids:
        sample = sorted(
            inconsistent_boe_ids,
            key=lambda item: (item[0], repr(item[1])),
        )[:_ERROR_SAMPLE_LIMIT]
        raise FlatMaterializationError(
            "identificador_boe no coincide con el BOE canónico del JSON o "
            f"es nulo; muestra={sample!r}."
        )

    boe_counts: dict[str, int] = {}
    for boe_id in canonical_boe_ids:
        boe_counts[boe_id] = boe_counts.get(boe_id, 0) + 1
    duplicated_boe_ids = sorted(
        boe_id for boe_id, count in boe_counts.items() if count > 1
    )
    if duplicated_boe_ids:
        raise FlatMaterializationError(
            "current_extractions contiene BOE canónicos duplicados; "
            f"muestra={duplicated_boe_ids[:_ERROR_SAMPLE_LIMIT]!r}."
        )

    identity.sort(key=lambda record: _canonical_json_bytes(record))
    with_events = sum(
        bool(extraction.publication_events)
        for extraction in models
    )
    return (
        {
            "extraction_config_id": extraction_config_id,
            "input_row_count": len(models),
            "input_with_events_count": with_events,
            "input_without_events_count": len(models) - with_events,
            "lineage": lineage,
        },
        identity,
    )


def _materialization_id(
    tables: Mapping[str, pd.DataFrame],
    *,
    identity: list[dict[str, Any]],
    context: Mapping[str, Any],
) -> str:
    payload = {
        "flat_contract_version": FLAT_CONTRACT_VERSION,
        "extraction_config_id": context["extraction_config_id"],
        "input_identity": identity,
        "input_counts": {
            "input_row_count": context["input_row_count"],
            "input_with_events_count": context["input_with_events_count"],
            "input_without_events_count": context[
                "input_without_events_count"
            ],
        },
        "semantic_table_sha256": _semantic_table_hashes(tables),
    }
    return sha256(_canonical_json_bytes(payload)).hexdigest()


def _table_manifest_entries(
    staging_dir: Path,
    tables: Mapping[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        entries.append({
            "table_name": table_name,
            "filename": table_spec.filename,
            "row_count": len(tables[table_name]),
            "columns": list(table_spec.column_names),
            "primary_key": list(table_spec.primary_key),
            "arrow_schema": _arrow_schema_payload(
                table_spec.arrow_schema
            ),
            "sha256": _sha256_file(staging_dir / table_spec.filename),
        })
    return entries


def _manifest_payload(
    staging_dir: Path,
    tables: Mapping[str, pd.DataFrame],
    *,
    context: Mapping[str, Any],
    input_identity: list[dict[str, Any]],
    materialization_id: str,
) -> dict[str, Any]:
    return {
        "materialization_id": materialization_id,
        "flat_contract_version": FLAT_CONTRACT_VERSION,
        "extraction_config_id": context["extraction_config_id"],
        "created_at_utc": (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "input_row_count": context["input_row_count"],
        "input_with_events_count": context["input_with_events_count"],
        "input_without_events_count": context["input_without_events_count"],
        "materialized_event_count": len(tables["publication_events"]),
        "table_count": len(FLAT_TABLE_SPECS),
        "lineage": {
            "columns": context["lineage_columns"],
            "records": context["lineage"],
        },
        "input_identity": input_identity,
        "tables": _table_manifest_entries(staging_dir, tables),
    }


def _validate_output_available(output_dir: Path) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(
            f"El directorio de materialización ya existe: {output_dir}"
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
        raise RuntimeError("Se rechazó limpiar un staging con nombre inesperado.")
    if staging_dir.is_symlink():
        raise RuntimeError("Se rechazó limpiar un staging convertido en enlace.")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)


def _verify_expected_files(
    staging_dir: Path,
    *,
    include_manifest: bool,
) -> None:
    expected = {
        table_spec.filename
        for table_spec in FLAT_TABLE_SPECS.values()
    }
    if include_manifest:
        expected.add(_MANIFEST_FILENAME)
    actual = {path.name for path in staging_dir.iterdir()}
    if actual != expected or any(
        not (staging_dir / filename).is_file()
        for filename in expected
    ):
        raise FlatMaterializationError(
            "El staging no contiene exactamente los artefactos esperados: "
            f"esperados={sorted(expected)}; encontrados={sorted(actual)}."
        )


def _reload_and_verify_tables(
    staging_dir: Path,
    original_tables: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    reloaded: dict[str, pd.DataFrame] = {}
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        dataframe = _read_contract_parquet(
            staging_dir / table_spec.filename,
            table_spec,
        )
        if tuple(dataframe.columns) != table_spec.column_names:
            raise FlatMaterializationError(
                f"Las columnas releídas de {table_name!r} no coinciden."
            )
        if len(dataframe) != len(original_tables[table_name]):
            raise FlatMaterializationError(
                f"El número de filas releído de {table_name!r} no coincide."
            )
        reloaded[table_name] = dataframe

    validate_flat_tables(reloaded)
    _semantic_tables_equal(original_tables, reloaded)
    return reloaded


def _materialize_validated_flat_tables(
    tables: Mapping[str, pd.DataFrame],
    *,
    output_dir: Path,
    manifest_context: Mapping[str, Any] | None,
    input_identity: list[dict[str, Any]] | None = None,
) -> FlatMaterializationResult:
    output_dir = Path(output_dir).absolute()
    _validate_output_available(output_dir)
    context = _normalise_manifest_context(manifest_context)
    identity = input_identity or list(context["lineage"])
    materialization_id = _materialization_id(
        tables,
        identity=identity,
        context=context,
    )

    parent_dir = output_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    staging_prefix = f".{output_dir.name}.staging-"
    staging_dir = Path(tempfile.mkdtemp(
        prefix=staging_prefix,
        dir=parent_dir,
    ))
    published = False
    try:
        for table_name, table_spec in FLAT_TABLE_SPECS.items():
            _write_contract_parquet(
                _sorted_contract_table(
                    tables[table_name],
                    table_spec,
                ),
                staging_dir / table_spec.filename,
                table_spec,
            )
        _verify_expected_files(staging_dir, include_manifest=False)
        _reload_and_verify_tables(staging_dir, tables)

        manifest = _manifest_payload(
            staging_dir,
            tables,
            context=context,
            input_identity=identity,
            materialization_id=materialization_id,
        )
        manifest_path = staging_dir / _MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        reloaded_manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if reloaded_manifest != manifest:
            raise FlatMaterializationError(
                "El manifiesto releído no coincide con el escrito."
            )
        _verify_expected_files(staging_dir, include_manifest=True)

        _validate_output_available(output_dir)
        staging_dir.rename(output_dir)
        published = True
    finally:
        if not published:
            _cleanup_staging(
                staging_dir,
                parent_dir=parent_dir,
                staging_prefix=staging_prefix,
            )

    table_paths = MappingProxyType({
        table_name: output_dir / table_spec.filename
        for table_name, table_spec in FLAT_TABLE_SPECS.items()
    })
    row_counts = MappingProxyType({
        table_name: len(tables[table_name])
        for table_name in FLAT_TABLE_SPECS
    })
    return FlatMaterializationResult(
        output_dir=output_dir,
        manifest_path=output_dir / _MANIFEST_FILENAME,
        table_paths=table_paths,
        row_counts=row_counts,
        materialization_id=materialization_id,
    )


def materialize_flat_tables(
    tables: Mapping[str, pd.DataFrame],
    *,
    output_dir: Path,
    manifest_context: Mapping[str, Any] | None = None,
) -> FlatMaterializationResult:
    """Publica tablas válidas con conteos documentales explícitos.

    La llamada presupone un único escritor para ``output_dir`` y rechaza un
    destino que ya exista, pero no ofrece exclusión frente a otros escritores
    concurrentes.
    """

    output_dir = Path(output_dir).absolute()
    _validate_output_available(output_dir)
    validate_flat_tables(tables)
    return _materialize_validated_flat_tables(
        tables,
        output_dir=output_dir,
        manifest_context=manifest_context,
    )


def materialize_current_extractions(
    current_extractions: pd.DataFrame,
    *,
    output_dir: Path,
    expected_extraction_config_id: str,
) -> FlatMaterializationResult:
    """Valida la entrada canónica y publica una versión Silver completa.

    El linaje debe coincidir con ``expected_extraction_config_id`` antes del
    flattening. Los conteos proceden de los modelos Pydantic, los BOE deben
    ser únicos y la llamada presupone un único escritor para ``output_dir``.
    """

    if not isinstance(current_extractions, pd.DataFrame):
        raise TypeError("current_extractions debe ser un pandas.DataFrame.")
    if not current_extractions.columns.is_unique:
        raise ValueError("current_extractions contiene columnas duplicadas.")
    if "extraction_json" not in current_extractions.columns:
        raise ValueError(
            "current_extractions debe incluir la columna 'extraction_json'."
        )
    _validate_current_extractions_provenance(
        current_extractions,
        expected_extraction_config_id=expected_extraction_config_id,
    )

    output_dir = Path(output_dir).absolute()
    _validate_output_available(output_dir)
    context, identity = _current_context(
        current_extractions,
        extraction_config_id=expected_extraction_config_id,
    )
    tables = flatten_current_extractions(current_extractions)
    return _materialize_validated_flat_tables(
        tables,
        output_dir=output_dir,
        manifest_context=context,
        input_identity=identity,
    )


def _manifest_sha256(value: Any, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FlatMaterializationError(
            f"El manifest Silver contiene {field_name!r} no válido."
        )
    return value


def load_flat_materialization(
    snapshot_dir: Path,
    *,
    expected_extraction_config_id: str,
) -> LoadedFlatMaterialization:
    """Load and verify one complete 13-table Silver materialization.

    The manifest, physical hashes, Arrow schemas, relational contract,
    extraction configuration and deterministic materialization identity are
    verified before any table is returned.
    """

    if _is_missing_text(expected_extraction_config_id):
        raise ValueError(
            "expected_extraction_config_id debe ser texto no vacío."
        )
    snapshot_dir = Path(snapshot_dir).absolute()
    manifest_path = snapshot_dir / _MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FlatMaterializationError(
            f"El snapshot Silver no contiene un manifest válido: {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FlatMaterializationError(
            "No se pudo leer el manifest Silver."
        ) from error
    if not isinstance(manifest, dict):
        raise FlatMaterializationError("El manifest Silver no es un objeto JSON.")
    if manifest.get("flat_contract_version") != FLAT_CONTRACT_VERSION:
        raise FlatMaterializationError(
            "Versión de contrato Silver incompatible: "
            f"{manifest.get('flat_contract_version')!r}."
        )
    extraction_config_id = manifest.get("extraction_config_id")
    if not isinstance(extraction_config_id, str) or not extraction_config_id:
        raise FlatMaterializationError(
            "El manifest Silver no contiene extraction_config_id."
        )
    if extraction_config_id != expected_extraction_config_id:
        raise FlatMaterializationError(
            "El manifest Silver contiene una extraction config incompatible: "
            f"expected={expected_extraction_config_id!r}; "
            f"found={extraction_config_id!r}."
        )
    materialization_id = _manifest_sha256(
        manifest.get("materialization_id"),
        field_name="materialization_id",
    )

    entries = manifest.get("tables")
    if (
        manifest.get("table_count") != len(FLAT_TABLE_SPECS)
        or not isinstance(entries, list)
        or len(entries) != len(FLAT_TABLE_SPECS)
    ):
        raise FlatMaterializationError(
            "El manifest Silver no declara exactamente las 13 tablas."
        )
    entries_by_name: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise FlatMaterializationError(
                "El manifest Silver contiene una entrada de tabla inválida."
            )
        table_name = entry.get("table_name")
        if not isinstance(table_name, str) or table_name in entries_by_name:
            raise FlatMaterializationError(
                "El manifest Silver contiene nombres de tabla inválidos o duplicados."
            )
        entries_by_name[table_name] = entry
    if set(entries_by_name) != set(FLAT_TABLE_SPECS):
        raise FlatMaterializationError(
            "Las tablas del manifest Silver no coinciden con el contrato."
        )

    expected_files = {
        _MANIFEST_FILENAME,
        *(spec.filename for spec in FLAT_TABLE_SPECS.values()),
    }
    if not snapshot_dir.is_dir() or {
        path.name for path in snapshot_dir.iterdir()
    } != expected_files:
        raise FlatMaterializationError(
            "El snapshot Silver no contiene exactamente los artefactos esperados."
        )

    tables: dict[str, pd.DataFrame] = {}
    for table_name, table_spec in FLAT_TABLE_SPECS.items():
        entry = entries_by_name[table_name]
        if (
            entry.get("filename") != table_spec.filename
            or entry.get("columns") != list(table_spec.column_names)
            or entry.get("primary_key") != list(table_spec.primary_key)
            or entry.get("arrow_schema")
            != _arrow_schema_payload(table_spec.arrow_schema)
        ):
            raise FlatMaterializationError(
                f"El manifest Silver contradice el contrato de {table_name!r}."
            )
        table_path = snapshot_dir / table_spec.filename
        if not table_path.is_file() or table_path.is_symlink():
            raise FlatMaterializationError(
                f"Falta el Parquet Silver {table_spec.filename!r}."
            )
        expected_hash = _manifest_sha256(
            entry.get("sha256"),
            field_name=f"tables[{table_name}].sha256",
        )
        if _sha256_file(table_path) != expected_hash:
            raise FlatMaterializationError(
                f"El hash físico de la tabla Silver {table_name!r} no coincide."
            )
        dataframe = _read_contract_parquet(table_path, table_spec)
        row_count = entry.get("row_count")
        if isinstance(row_count, bool) or row_count != len(dataframe):
            raise FlatMaterializationError(
                f"El row_count de {table_name!r} no coincide con el Parquet."
            )
        tables[table_name] = dataframe
    validate_flat_tables(tables)
    if manifest.get("materialized_event_count") != len(
        tables["publication_events"]
    ):
        raise FlatMaterializationError(
            "El conteo de eventos del manifest Silver no coincide."
        )

    lineage = manifest.get("lineage")
    if not isinstance(lineage, Mapping):
        raise FlatMaterializationError("El manifest Silver no contiene linaje.")
    context = _normalise_manifest_context({
        "extraction_config_id": extraction_config_id,
        "input_row_count": manifest.get("input_row_count"),
        "input_with_events_count": manifest.get("input_with_events_count"),
        "input_without_events_count": manifest.get("input_without_events_count"),
        "lineage": lineage.get("records"),
    })
    if lineage.get("columns") != context["lineage_columns"]:
        raise FlatMaterializationError(
            "Las columnas de linaje del manifest Silver no coinciden."
        )
    input_identity = manifest.get("input_identity")
    if not isinstance(input_identity, list) or any(
        not isinstance(record, Mapping) for record in input_identity
    ):
        raise FlatMaterializationError(
            "El manifest Silver no contiene input_identity verificable."
        )
    recomputed_id = _materialization_id(
        tables,
        identity=[dict(record) for record in input_identity],
        context=context,
    )
    if recomputed_id != materialization_id:
        raise FlatMaterializationError(
            "El materialization_id Silver no coincide con tablas e identidad."
        )

    return LoadedFlatMaterialization(
        input_dir=snapshot_dir,
        manifest_path=manifest_path,
        tables=MappingProxyType(tables),
        materialization_id=materialization_id,
        extraction_config_id=extraction_config_id,
        manifest=MappingProxyType(manifest),
    )
