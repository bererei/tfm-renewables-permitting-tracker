from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from renewables_permitting.utils import normalize_text_or_none


MUNICIPALITY_REFERENCE_TYPE = "ine_municipality_dimension"
MUNICIPALITY_REFERENCE_CONTRACT_VERSION = "1"
MUNICIPALITY_REFERENCE_BUILD_VERSION = "ine_municipality_build_v1"
MUNICIPALITY_DIMENSION_FILENAME = "dim_municipalities.parquet"
MUNICIPALITY_MANIFEST_FILENAME = "manifest.json"
MUNICIPALITY_LOGICAL_KEY = ("cauto", "cpro", "cmun")
MUNICIPALITY_DIMENSION_COLUMNS = (
    "cauto",
    "cpro",
    "cmun",
    "dc",
    "municipio",
    "comunidad_autonoma",
    "provincia",
    "municipio_norm",
    "provincia_norm",
    "comunidad_autonoma_norm",
    "municipio_lookup_names_norm",
    "ine_municipality_code",
    "ine_province_code",
    "ine_autonomous_community_code",
)

_CODINE_SOURCE_COLUMNS = (
    "codauto",
    "comunidad_autonoma",
    "cpro",
    "provincia",
)
_DICTIONARY_SOURCE_COLUMNS = (
    "codauto",
    "cpro",
    "cmun",
    "dc",
    "nombre",
)
_CODE_WIDTHS = {
    "cauto": 2,
    "cpro": 2,
    "cmun": 3,
    "dc": 1,
    "ine_municipality_code": 5,
    "ine_province_code": 2,
    "ine_autonomous_community_code": 2,
}
_NAME_COLUMNS = (
    "municipio",
    "comunidad_autonoma",
    "provincia",
    "municipio_norm",
    "provincia_norm",
    "comunidad_autonoma_norm",
)


@dataclass(frozen=True)
class MunicipalityDimensionComparison:
    """Resumen acotado de cambios contractuales entre dos referencias INE."""

    old_reference_id: str
    new_reference_id: str
    old_reference_sha256: str
    new_reference_sha256: str
    semantic_changed: bool
    added_codes: tuple[str, ...]
    removed_codes: tuple[str, ...]
    changed_codes: tuple[str, ...]

    @property
    def requires_downstream_rebuild(self) -> bool:
        """Indica si debe rehacerse Silver validado → INE → grouping → Gold."""

        return self.semantic_changed


@dataclass(frozen=True)
class MunicipalityReferenceMaterialization:
    """Rutas e identidad de un snapshot candidato de referencia INE."""

    output_dir: Path
    dimension_path: Path
    manifest_path: Path
    semantic_reference_id: str
    semantic_reference_sha256: str


@dataclass(frozen=True)
class LoadedMunicipalityReference:
    """Municipality snapshot reloaded after physical and semantic checks."""

    input_dir: Path
    dimension_path: Path
    manifest_path: Path
    dimension: pd.DataFrame
    semantic_reference_id: str
    semantic_reference_sha256: str
    manifest: dict[str, Any]


def _validate_source_columns(
    dataframe: pd.DataFrame,
    required: tuple[str, ...],
    *,
    source_name: str,
) -> None:
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError(f"{source_name} debe ser un pandas.DataFrame.")
    if dataframe.columns.duplicated().any():
        raise ValueError(f"{source_name} contiene columnas duplicadas.")
    missing = set(required) - set(dataframe.columns)
    if missing:
        raise ValueError(
            f"Faltan columnas en {source_name}: {sorted(missing)}"
        )


def load_ine_source_tables(
    codine_path: Path,
    dictionary_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga los dos CSV INE explícitos como tablas textuales sin inferir códigos."""

    codine_path = Path(codine_path)
    dictionary_path = Path(dictionary_path)
    codine = pd.read_csv(
        codine_path,
        encoding="utf-8-sig",
        sep=",",
        dtype="string",
    )
    dictionary = pd.read_csv(
        dictionary_path,
        encoding="utf-8-sig",
        sep=",",
        dtype="string",
    )
    _validate_source_columns(
        codine,
        _CODINE_SOURCE_COLUMNS,
        source_name="codine_table",
    )
    _validate_source_columns(
        dictionary,
        _DICTIONARY_SOURCE_COLUMNS,
        source_name="dictionary_table",
    )
    return codine, dictionary


def _normalise_code_series(
    values: pd.Series,
    *,
    width: int,
    column_name: str,
) -> pd.Series:
    normalised = (
        values.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    invalid = normalised.isna() | ~normalised.str.fullmatch(r"\d+")
    too_wide = normalised.str.len().gt(width).fillna(False)
    if invalid.any() or too_wide.any():
        examples = values.loc[invalid | too_wide].head(5).tolist()
        raise ValueError(
            f"{column_name} contiene códigos INE no válidos: {examples}"
        )
    return normalised.str.zfill(width)


def _normalise_required_names(
    values: pd.Series,
    *,
    column_name: str,
) -> pd.Series:
    names = values.astype("string").str.strip()
    invalid = names.isna() | names.eq("")
    if invalid.any():
        raise ValueError(f"{column_name} contiene nombres vacíos o nulos.")
    return names


def _normalised_name_variants(value: Any) -> list[str]:
    if value is None or value is pd.NA or bool(pd.isna(value)):
        return []
    raw = str(value).strip()
    variants = {raw}
    comma_parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(comma_parts) == 2:
        variants.add(f"{comma_parts[1]} {comma_parts[0]}")
    for current in list(variants):
        variants.update(
            part.strip() for part in current.split("/") if part.strip()
        )
    normalised = {normalize_text_or_none(item) for item in variants}
    return sorted(item for item in normalised if item is not None)


def _coerce_lookup_names(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    elif hasattr(value, "tolist"):
        converted = value.tolist()
        values = converted if isinstance(converted, list) else [converted]
    else:
        raise ValueError(
            "municipio_lookup_names_norm debe contener una colección textual."
        )
    if not values or any(not isinstance(item, str) for item in values):
        raise ValueError(
            "municipio_lookup_names_norm contiene aliases no válidos."
        )
    return sorted(set(values))


def build_municipality_dimension(
    codine_table: pd.DataFrame,
    dictionary_table: pd.DataFrame,
) -> pd.DataFrame:
    """Construye en memoria una fila canónica por municipio administrativo INE."""

    _validate_source_columns(
        codine_table,
        _CODINE_SOURCE_COLUMNS,
        source_name="codine_table",
    )
    _validate_source_columns(
        dictionary_table,
        _DICTIONARY_SOURCE_COLUMNS,
        source_name="dictionary_table",
    )
    codine = codine_table.loc[:, _CODINE_SOURCE_COLUMNS].copy(deep=True)
    dictionary = dictionary_table.loc[:, _DICTIONARY_SOURCE_COLUMNS].copy(
        deep=True
    )
    codine = codine.rename(columns={"codauto": "cauto"})
    dictionary = dictionary.rename(
        columns={"codauto": "cauto", "nombre": "municipio"}
    )

    for dataframe in (codine, dictionary):
        dataframe["cauto"] = _normalise_code_series(
            dataframe["cauto"], width=2, column_name="cauto"
        )
        dataframe["cpro"] = _normalise_code_series(
            dataframe["cpro"], width=2, column_name="cpro"
        )
    dictionary["cmun"] = _normalise_code_series(
        dictionary["cmun"], width=3, column_name="cmun"
    )
    dictionary["dc"] = _normalise_code_series(
        dictionary["dc"], width=1, column_name="dc"
    )
    codine["comunidad_autonoma"] = _normalise_required_names(
        codine["comunidad_autonoma"], column_name="comunidad_autonoma"
    )
    codine["provincia"] = _normalise_required_names(
        codine["provincia"], column_name="provincia"
    )
    dictionary["municipio"] = _normalise_required_names(
        dictionary["municipio"], column_name="municipio"
    )

    if codine["cpro"].duplicated().any():
        raise ValueError(
            "La fuente de provincias contiene un código de provincia "
            "duplicado o una jerarquía contradictoria."
        )
    if dictionary.duplicated(list(MUNICIPALITY_LOGICAL_KEY)).any():
        raise ValueError(
            "La fuente municipal contiene claves administrativas duplicadas."
        )

    dimension = dictionary.merge(
        codine,
        on=["cauto", "cpro"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if not dimension["_merge"].eq("both").all():
        missing = (
            dimension.loc[
                ~dimension["_merge"].eq("both"), ["cauto", "cpro"]
            ]
            .drop_duplicates()
            .to_dict("records")[:5]
        )
        raise ValueError(
            "Hay municipios sin provincia o comunidad asociada: "
            f"{missing}"
        )
    dimension = dimension.drop(columns="_merge")
    dimension["municipio_norm"] = dimension["municipio"].map(
        normalize_text_or_none
    ).astype("string")
    dimension["provincia_norm"] = dimension["provincia"].map(
        normalize_text_or_none
    ).astype("string")
    dimension["comunidad_autonoma_norm"] = dimension[
        "comunidad_autonoma"
    ].map(normalize_text_or_none).astype("string")
    dimension["municipio_lookup_names_norm"] = dimension["municipio"].map(
        _normalised_name_variants
    )
    dimension["ine_municipality_code"] = (
        dimension["cpro"] + dimension["cmun"]
    )
    dimension["ine_province_code"] = dimension["cpro"]
    dimension["ine_autonomous_community_code"] = dimension["cauto"]
    dimension = dimension.loc[:, MUNICIPALITY_DIMENSION_COLUMNS].sort_values(
        ["cpro", "cmun"], kind="stable"
    ).reset_index(drop=True)
    for column in MUNICIPALITY_DIMENSION_COLUMNS:
        if column != "municipio_lookup_names_norm":
            dimension[column] = dimension[column].astype("string")
    validate_municipality_dimension(dimension)
    return dimension


def _validate_exact_code(
    dimension: pd.DataFrame,
    column: str,
    width: int,
) -> pd.Series:
    values = dimension[column].astype("string")
    invalid = values.isna() | ~values.str.fullmatch(rf"\d{{{width}}}")
    if invalid.any():
        raise ValueError(
            f"{column} contiene códigos INE no válidos o sin padding."
        )
    return values


def validate_municipality_dimension(dimension: pd.DataFrame) -> None:
    """Valida schema, claves, aliases y jerarquía de una dimensión municipal."""

    if not isinstance(dimension, pd.DataFrame):
        raise TypeError("dimension debe ser un pandas.DataFrame.")
    if dimension.columns.duplicated().any():
        raise ValueError("La dimensión contiene columnas duplicadas.")
    if tuple(dimension.columns) != MUNICIPALITY_DIMENSION_COLUMNS:
        raise ValueError(
            "Las columnas de la dimensión no coinciden con el contrato: "
            f"{dimension.columns.tolist()}"
        )
    if dimension.empty:
        raise ValueError("La dimensión municipal no puede estar vacía.")

    codes = {
        column: _validate_exact_code(dimension, column, width)
        for column, width in _CODE_WIDTHS.items()
    }
    for column in _NAME_COLUMNS:
        values = dimension[column].astype("string")
        if values.isna().any() or values.str.strip().eq("").any():
            raise ValueError(
                f"La dimensión contiene nombres nulos o vacíos en {column}."
            )

    if dimension.duplicated(list(MUNICIPALITY_LOGICAL_KEY)).any():
        raise ValueError("La dimensión contiene claves municipales duplicadas.")
    if codes["ine_municipality_code"].duplicated().any():
        raise ValueError("ine_municipality_code debe ser único.")
    if not codes["ine_municipality_code"].equals(
        codes["cpro"] + codes["cmun"]
    ):
        raise ValueError("La dimensión contiene códigos municipales incoherentes.")
    if not codes["ine_province_code"].equals(codes["cpro"]):
        raise ValueError("La dimensión contiene códigos provinciales incoherentes.")
    if not codes["ine_autonomous_community_code"].equals(codes["cauto"]):
        raise ValueError("La dimensión contiene códigos autonómicos incoherentes.")

    expected_normalised = {
        "municipio_norm": dimension["municipio"].map(normalize_text_or_none),
        "provincia_norm": dimension["provincia"].map(normalize_text_or_none),
        "comunidad_autonoma_norm": dimension["comunidad_autonoma"].map(
            normalize_text_or_none
        ),
    }
    for column, expected in expected_normalised.items():
        actual = dimension[column].astype("string")
        if not actual.equals(expected.astype("string")):
            raise ValueError(f"{column} no coincide con el nombre canónico.")

    for municipality, lookup_names in zip(
        dimension["municipio"],
        dimension["municipio_lookup_names_norm"],
        strict=True,
    ):
        if _coerce_lookup_names(lookup_names) != _normalised_name_variants(
            municipality
        ):
            raise ValueError(
                "municipio_lookup_names_norm no coincide con el diccionario."
            )

    province_columns = [
        "cpro",
        "cauto",
        "provincia",
        "provincia_norm",
        "comunidad_autonoma",
        "comunidad_autonoma_norm",
    ]
    provinces = dimension[province_columns].drop_duplicates()
    if provinces["cpro"].duplicated().any():
        raise ValueError(
            "La jerarquía municipio → provincia → comunidad es contradictoria."
        )
    community_columns = [
        "cauto",
        "comunidad_autonoma",
        "comunidad_autonoma_norm",
    ]
    communities = dimension[community_columns].drop_duplicates()
    if communities["cauto"].duplicated().any():
        raise ValueError("La jerarquía de comunidades autónomas es contradictoria.")


def _semantic_records(dimension: pd.DataFrame) -> list[dict[str, Any]]:
    validate_municipality_dimension(dimension)
    ordered = dimension.sort_values(
        list(MUNICIPALITY_LOGICAL_KEY), kind="stable"
    )
    records: list[dict[str, Any]] = []
    for row in ordered.itertuples(index=False, name=None):
        record: dict[str, Any] = {}
        for column, value in zip(MUNICIPALITY_DIMENSION_COLUMNS, row, strict=True):
            record[column] = (
                _coerce_lookup_names(value)
                if column == "municipio_lookup_names_norm"
                else str(value)
            )
        records.append(record)
    return records


def compute_municipality_reference_hash(dimension: pd.DataFrame) -> str:
    """Calcula el SHA-256 del contenido administrativo contractual ordenado."""

    payload = {
        "contract_version": MUNICIPALITY_REFERENCE_CONTRACT_VERSION,
        "columns": list(MUNICIPALITY_DIMENSION_COLUMNS),
        "records": _semantic_records(dimension),
    }
    serialised = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(serialised).hexdigest()


def compute_municipality_reference_id(dimension: pd.DataFrame) -> str:
    """Devuelve el identificador corto del contenido semántico de referencia."""

    return compute_municipality_reference_hash(dimension)[:16]


def _records_by_code(dimension: pd.DataFrame) -> dict[str, tuple[Any, ...]]:
    records = {}
    for record in _semantic_records(dimension):
        code = str(record["ine_municipality_code"])
        records[code] = tuple(
            tuple(value) if isinstance(value, list) else value
            for value in record.values()
        )
    return records


def compare_municipality_dimensions(
    old: pd.DataFrame,
    new: pd.DataFrame,
) -> MunicipalityDimensionComparison:
    """Compara referencias sin ejecutar el downstream ni pedir confirmación."""

    old_records = _records_by_code(old)
    new_records = _records_by_code(new)
    old_codes = set(old_records)
    new_codes = set(new_records)
    added = tuple(sorted(new_codes - old_codes))
    removed = tuple(sorted(old_codes - new_codes))
    changed = tuple(sorted(
        code
        for code in old_codes & new_codes
        if old_records[code] != new_records[code]
    ))
    old_hash = compute_municipality_reference_hash(old)
    new_hash = compute_municipality_reference_hash(new)
    return MunicipalityDimensionComparison(
        old_reference_id=old_hash[:16],
        new_reference_id=new_hash[:16],
        old_reference_sha256=old_hash,
        new_reference_sha256=new_hash,
        semantic_changed=old_hash != new_hash,
        added_codes=added,
        removed_codes=removed,
        changed_codes=changed,
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_output_available(output_dir: Path) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(
            f"El snapshot candidato ya existe: {output_dir}"
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


def _created_at_value(value: datetime | None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at debe incluir zona horaria.")
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def materialize_municipality_dimension(
    dimension: pd.DataFrame,
    *,
    output_dir: Path,
    codine_source_path: Path,
    dictionary_source_path: Path,
    created_at: datetime | None = None,
) -> MunicipalityReferenceMaterialization:
    """Publica atómicamente un snapshot candidato validado y su manifest."""

    validate_municipality_dimension(dimension)
    output_dir = Path(output_dir).absolute()
    _validate_output_available(output_dir)
    codine_source_path = Path(codine_source_path)
    dictionary_source_path = Path(dictionary_source_path)
    codine, dictionary = load_ine_source_tables(
        codine_source_path,
        dictionary_source_path,
    )
    rebuilt = build_municipality_dimension(codine, dictionary)
    if compare_municipality_dimensions(
        dimension,
        rebuilt,
    ).semantic_changed:
        raise ValueError(
            "La dimensión no coincide semánticamente con sus fuentes INE."
        )

    canonical = dimension.sort_values(
        ["cpro", "cmun"], kind="stable"
    ).reset_index(drop=True)
    semantic_hash = compute_municipality_reference_hash(canonical)
    semantic_id = semantic_hash[:16]
    parent_dir = output_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    staging_prefix = f".{output_dir.name}.staging-"
    staging_dir = Path(tempfile.mkdtemp(
        prefix=staging_prefix,
        dir=parent_dir,
    ))
    published = False
    try:
        dimension_path = staging_dir / MUNICIPALITY_DIMENSION_FILENAME
        canonical.to_parquet(dimension_path, index=False)
        reloaded = pd.read_parquet(dimension_path)
        validate_municipality_dimension(reloaded)
        if compare_municipality_dimensions(
            canonical,
            reloaded,
        ).semantic_changed:
            raise ValueError(
                "El round trip Parquet cambió la dimensión semánticamente."
            )

        manifest = {
            "reference_type": MUNICIPALITY_REFERENCE_TYPE,
            "contract_version": MUNICIPALITY_REFERENCE_CONTRACT_VERSION,
            "build_version": MUNICIPALITY_REFERENCE_BUILD_VERSION,
            "sources": {
                "codine": {
                    "filename": codine_source_path.name,
                    "sha256": _sha256_file(codine_source_path),
                    "row_count": len(codine),
                },
                "dictionary": {
                    "filename": dictionary_source_path.name,
                    "sha256": _sha256_file(dictionary_source_path),
                    "row_count": len(dictionary),
                },
            },
            "output": {
                "filename": MUNICIPALITY_DIMENSION_FILENAME,
                "row_count": len(reloaded),
                "schema": [
                    {"name": column, "dtype": str(reloaded[column].dtype)}
                    for column in MUNICIPALITY_DIMENSION_COLUMNS
                ],
                "logical_key": list(MUNICIPALITY_LOGICAL_KEY),
                "parquet_sha256": _sha256_file(dimension_path),
            },
            "semantic_reference_id": semantic_id,
            "semantic_reference_sha256": semantic_hash,
            "created_at": _created_at_value(created_at),
        }
        manifest_path = staging_dir / MUNICIPALITY_MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("El manifest releído no coincide con el escrito.")
        expected_files = {
            MUNICIPALITY_DIMENSION_FILENAME,
            MUNICIPALITY_MANIFEST_FILENAME,
        }
        if {path.name for path in staging_dir.iterdir()} != expected_files:
            raise ValueError("El staging contiene artefactos inesperados.")

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

    return MunicipalityReferenceMaterialization(
        output_dir=output_dir,
        dimension_path=output_dir / MUNICIPALITY_DIMENSION_FILENAME,
        manifest_path=output_dir / MUNICIPALITY_MANIFEST_FILENAME,
        semantic_reference_id=semantic_id,
        semantic_reference_sha256=semantic_hash,
    )


def load_municipality_reference(
    snapshot_dir: Path,
) -> LoadedMunicipalityReference:
    """Load one versioned INE snapshot after manifest and hash validation."""

    snapshot_dir = Path(snapshot_dir).absolute()
    manifest_path = snapshot_dir / MUNICIPALITY_MANIFEST_FILENAME
    dimension_path = snapshot_dir / MUNICIPALITY_DIMENSION_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(
            f"El snapshot INE no contiene un manifest válido: {manifest_path}"
        )
    if not dimension_path.is_file() or dimension_path.is_symlink():
        raise ValueError(
            f"El snapshot INE no contiene la dimensión: {dimension_path}"
        )
    expected_files = {
        MUNICIPALITY_MANIFEST_FILENAME,
        MUNICIPALITY_DIMENSION_FILENAME,
    }
    if {path.name for path in snapshot_dir.iterdir()} != expected_files:
        raise ValueError(
            "El snapshot INE no contiene exactamente los artefactos esperados."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("No se pudo leer el manifest INE.") from error
    if not isinstance(manifest, dict):
        raise ValueError("El manifest INE no es un objeto JSON.")
    if manifest.get("reference_type") != MUNICIPALITY_REFERENCE_TYPE:
        raise ValueError("El manifest no corresponde a una referencia INE.")
    if (
        manifest.get("contract_version")
        != MUNICIPALITY_REFERENCE_CONTRACT_VERSION
    ):
        raise ValueError("La versión contractual de la referencia INE no coincide.")
    output = manifest.get("output")
    if not isinstance(output, dict):
        raise ValueError("El manifest INE no contiene metadata de output.")
    if output.get("filename") != MUNICIPALITY_DIMENSION_FILENAME:
        raise ValueError("El manifest INE declara un filename no contractual.")
    expected_physical_hash = output.get("parquet_sha256")
    if (
        not isinstance(expected_physical_hash, str)
        or len(expected_physical_hash) != 64
        or _sha256_file(dimension_path) != expected_physical_hash
    ):
        raise ValueError("El hash físico de la dimensión INE no coincide.")

    dimension = pd.read_parquet(dimension_path)
    validate_municipality_dimension(dimension)
    if output.get("row_count") != len(dimension):
        raise ValueError("El row_count de la dimensión INE no coincide.")
    actual_schema = [
        {"name": column, "dtype": str(dimension[column].dtype)}
        for column in MUNICIPALITY_DIMENSION_COLUMNS
    ]
    if output.get("schema") != actual_schema:
        raise ValueError("El schema de la dimensión INE no coincide con el manifest.")
    if output.get("logical_key") != list(MUNICIPALITY_LOGICAL_KEY):
        raise ValueError("La clave lógica INE no coincide con el contrato.")

    semantic_hash = compute_municipality_reference_hash(dimension)
    semantic_id = semantic_hash[:16]
    if manifest.get("semantic_reference_sha256") != semantic_hash:
        raise ValueError("El hash semántico de la referencia INE no coincide.")
    if manifest.get("semantic_reference_id") != semantic_id:
        raise ValueError("El semantic reference ID de INE no coincide.")
    return LoadedMunicipalityReference(
        input_dir=snapshot_dir,
        dimension_path=dimension_path,
        manifest_path=manifest_path,
        dimension=dimension,
        semantic_reference_id=semantic_id,
        semantic_reference_sha256=semantic_hash,
        manifest=manifest,
    )
