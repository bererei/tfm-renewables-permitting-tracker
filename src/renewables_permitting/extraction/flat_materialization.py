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
        "input_row_count": input_row_count,
        "input_with_events_count": input_with_events_count,
        "input_without_events_count": input_without_events_count,
        "lineage_columns": lineage_columns,
        "lineage": lineage,
    }


def _current_context(
    current_extractions: pd.DataFrame,
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
    materialization_id: str,
) -> dict[str, Any]:
    return {
        "materialization_id": materialization_id,
        "flat_contract_version": FLAT_CONTRACT_VERSION,
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
) -> FlatMaterializationResult:
    """Valida la entrada canónica y publica una versión Silver completa.

    Los conteos proceden de los modelos Pydantic, los BOE deben ser únicos y
    la llamada presupone un único escritor para ``output_dir``.
    """

    if not isinstance(current_extractions, pd.DataFrame):
        raise TypeError("current_extractions debe ser un pandas.DataFrame.")
    if not current_extractions.columns.is_unique:
        raise ValueError("current_extractions contiene columnas duplicadas.")
    if "extraction_json" not in current_extractions.columns:
        raise ValueError(
            "current_extractions debe incluir la columna 'extraction_json'."
        )

    output_dir = Path(output_dir).absolute()
    _validate_output_available(output_dir)
    context, identity = _current_context(current_extractions)
    tables = flatten_current_extractions(current_extractions)
    return _materialize_validated_flat_tables(
        tables,
        output_dir=output_dir,
        manifest_context=context,
        input_identity=identity,
    )
