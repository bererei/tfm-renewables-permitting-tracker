from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import requests

from renewables_permitting.utils import normalize_text, save_parquet


BOE_SUMMARY_BASE_URL = "https://www.boe.es/datosabiertos/api/boe/sumario"
DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
BOE_ITEM_COLUMNS = (
    "identificador",
    "fecha_publicacion",
    "titulo",
    "url_html",
    "url_xml",
    "control",
    "diario_numero",
    "seccion_codigo",
    "seccion_nombre",
    "departamento_codigo",
    "departamento_nombre",
    "epigrafe_nombre",
    "item_location",
    "source",
    "summary_sha256",
    "seccion_nombre_norm",
    "departamento_nombre_norm",
    "epigrafe_nombre_norm",
    "titulo_norm",
)
_STRING_ITEM_COLUMNS = tuple(
    column for column in BOE_ITEM_COLUMNS
    if column != "fecha_publicacion"
)
_HTTPGet = Callable[..., Any]
SummaryFetchStatus = Literal["success", "no_publication", "failed"]


@dataclass(frozen=True)
class BOESummaryFetchResult:
    """Resultado explícito de obtener un sumario diario oficial."""

    publication_date: date
    source_url: str
    retrieved_at: datetime
    status: SummaryFetchStatus
    http_status: int | None
    boe_status_code: str | None
    payload: dict[str, Any] | None
    item_count: int
    summary_sha256: str | None
    error_type: str | None
    error: str | None


def inclusive_date_range(start_date: date, end_date: date) -> list[date]:
    """Devuelve todas las fechas del rango, incluidos ambos extremos."""

    if start_date > end_date:
        raise ValueError("start_date no puede ser posterior a end_date.")
    day_count = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(day_count + 1)]


def _summary_url(publication_date: date) -> str:
    return f"{BOE_SUMMARY_BASE_URL}/{publication_date:%Y%m%d}"


def _summary_payload_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _summary_payload_sha256(payload: dict[str, Any]) -> str:
    return sha256(_summary_payload_bytes(payload)).hexdigest()


def _count_item_nodes(value: Any) -> int:
    if isinstance(value, dict):
        count = 0
        for key, child in value.items():
            if key == "item":
                if child is None:
                    continue
                count += len(child) if isinstance(child, list) else 1
            else:
                count += _count_item_nodes(child)
        return count
    if isinstance(value, list):
        return sum(_count_item_nodes(child) for child in value)
    return 0


def _failed_summary_result(
    *,
    publication_date: date,
    source_url: str,
    retrieved_at: datetime,
    http_status: int | None,
    boe_status_code: str | None,
    error_type: str,
    error: str,
) -> BOESummaryFetchResult:
    return BOESummaryFetchResult(
        publication_date=publication_date,
        source_url=source_url,
        retrieved_at=retrieved_at,
        status="failed",
        http_status=http_status,
        boe_status_code=boe_status_code,
        payload=None,
        item_count=0,
        summary_sha256=None,
        error_type=error_type,
        error=error,
    )


def fetch_boe_summary(
    publication_date: date,
    *,
    http_get: _HTTPGet | None = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    retrieved_at: datetime | None = None,
) -> BOESummaryFetchResult:
    """Obtiene un sumario BOE distinguiendo éxito, ausencia y fallo."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds debe ser mayor que cero.")
    source_url = _summary_url(publication_date)
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    get = http_get or requests.get
    try:
        response = get(
            source_url,
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
        )
    except requests.RequestException as error:
        return _failed_summary_result(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            http_status=None,
            boe_status_code=None,
            error_type="REQUEST_ERROR",
            error=str(error),
        )

    http_status = int(response.status_code)
    if http_status == 404:
        return BOESummaryFetchResult(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            status="no_publication",
            http_status=404,
            boe_status_code=None,
            payload=None,
            item_count=0,
            summary_sha256=None,
            error_type="HTTP_404",
            error="No BOE publication for this date",
        )
    if http_status != 200:
        return _failed_summary_result(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            http_status=http_status,
            boe_status_code=None,
            error_type="HTTP_ERROR",
            error=f"HTTP {http_status}",
        )
    try:
        payload = response.json()
    except ValueError as error:
        return _failed_summary_result(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            http_status=http_status,
            boe_status_code=None,
            error_type="INVALID_JSON",
            error=str(error),
        )
    if not isinstance(payload, dict):
        return _failed_summary_result(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            http_status=http_status,
            boe_status_code=None,
            error_type="INVALID_JSON",
            error="La respuesta JSON no es un objeto.",
        )
    boe_status_code = str(payload.get("status", {}).get("code", ""))
    if boe_status_code == "404":
        return BOESummaryFetchResult(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            status="no_publication",
            http_status=http_status,
            boe_status_code=boe_status_code,
            payload=None,
            item_count=0,
            summary_sha256=None,
            error_type="BOE_404",
            error=str(
                payload.get("status", {}).get(
                    "text",
                    "No BOE publication for this date",
                )
            ),
        )
    if boe_status_code != "200":
        return _failed_summary_result(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            http_status=http_status,
            boe_status_code=boe_status_code or None,
            error_type="BOE_STATUS_ERROR",
            error=str(payload.get("status", {}).get("text", "BOE status error")),
        )
    sumario = payload.get("data", {}).get("sumario")
    if not isinstance(sumario, dict):
        return _failed_summary_result(
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            http_status=http_status,
            boe_status_code=boe_status_code,
            error_type="UNEXPECTED_PAYLOAD",
            error="La respuesta no contiene data.sumario.",
        )
    payload_hash = _summary_payload_sha256(payload)
    return BOESummaryFetchResult(
        publication_date=publication_date,
        source_url=source_url,
        retrieved_at=retrieved_at,
        status="success",
        http_status=http_status,
        boe_status_code=boe_status_code,
        payload=payload,
        item_count=_count_item_nodes(sumario),
        summary_sha256=payload_hash,
        error_type=None,
        error=None,
    )


def fetch_boe_summaries(
    start_date: date,
    end_date: date,
    *,
    http_get: _HTTPGet | None = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> list[BOESummaryFetchResult]:
    """Obtiene de forma secuencial un rango inclusivo de sumarios BOE."""

    return [
        fetch_boe_summary(
            publication_date,
            http_get=http_get,
            timeout_seconds=timeout_seconds,
        )
        for publication_date in inclusive_date_range(start_date, end_date)
    ]


def materialize_boe_summary(
    result: BOESummaryFetchResult,
    *,
    output_dir: Path,
) -> Path:
    """Persiste un resultado diario bajo ``output_dir/YYYYMMDD``."""

    day_dir = Path(output_dir) / result.publication_date.strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    summary_hash = result.summary_sha256
    summary_path = day_dir / "sumario.json"
    if result.status == "success":
        if result.payload is None:
            raise ValueError("Un resultado success debe contener payload.")
        payload_bytes = _summary_payload_bytes(result.payload)
        summary_hash = sha256(payload_bytes).hexdigest()
        if summary_path.exists() and summary_path.read_bytes() != payload_bytes:
            raise FileExistsError(
                f"Ya existe un sumario incompatible: {summary_path}"
            )
        summary_path.write_bytes(payload_bytes)
    elif summary_path.exists():
        raise FileExistsError(
            "No se reemplazará un sumario existente con un resultado "
            f"{result.status}: {summary_path}"
        )
    metadata = {
        "date": result.publication_date.isoformat(),
        "source": result.source_url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "status": result.status,
        "http_status": result.http_status,
        "boe_status_code": result.boe_status_code,
        "records_downloaded": result.item_count,
        "summary_sha256": summary_hash,
        "error_type": result.error_type,
        "error": result.error,
    }
    metadata_path = day_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def _objects(value: Any, *, path: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    if not all(isinstance(item, dict) for item in values):
        raise ValueError(f"{path} debe contener objetos BOE.")
    return values


def _required_text(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} debe contener texto no vacío.")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _item_row(
    item: dict[str, Any],
    *,
    publication_date: pd.Timestamp,
    summary_hash: str,
    diario_numero: Any,
    seccion: dict[str, Any],
    departamento: dict[str, Any],
    epigrafe_nombre: Any,
    item_location: str,
) -> dict[str, Any]:
    boe_id = _required_text(item.get("identificador"), path="item.identificador")
    title = _required_text(item.get("titulo"), path=f"{boe_id}.titulo")
    url_xml = _required_text(item.get("url_xml"), path=f"{boe_id}.url_xml")
    seccion_nombre = _optional_text(seccion.get("nombre"))
    departamento_nombre = _optional_text(departamento.get("nombre"))
    epigrafe = _optional_text(epigrafe_nombre)
    return {
        "identificador": boe_id,
        "fecha_publicacion": publication_date,
        "titulo": title,
        "url_html": _optional_text(item.get("url_html")),
        "url_xml": url_xml,
        "control": _optional_text(item.get("control")),
        "diario_numero": _optional_text(diario_numero),
        "seccion_codigo": _optional_text(seccion.get("codigo")),
        "seccion_nombre": seccion_nombre,
        "departamento_codigo": _optional_text(departamento.get("codigo")),
        "departamento_nombre": departamento_nombre,
        "epigrafe_nombre": epigrafe,
        "item_location": item_location,
        "source": "boe",
        "summary_sha256": summary_hash,
        "seccion_nombre_norm": normalize_text(seccion_nombre),
        "departamento_nombre_norm": normalize_text(departamento_nombre),
        "epigrafe_nombre_norm": normalize_text(epigrafe),
        "titulo_norm": normalize_text(title),
    }


def _department_item_rows(
    departamento: dict[str, Any],
    *,
    prefix: str,
    publication_date: pd.Timestamp,
    summary_hash: str,
    diario_numero: Any,
    seccion: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    common = {
        "publication_date": publication_date,
        "summary_hash": summary_hash,
        "diario_numero": diario_numero,
        "seccion": seccion,
        "departamento": departamento,
    }
    for epigrafe in _objects(
        departamento.get("epigrafe"),
        path=f"{prefix}.epigrafe",
    ):
        for item in _objects(
            epigrafe.get("item"),
            path=f"{prefix}.epigrafe.item",
        ):
            yield _item_row(
                item,
                epigrafe_nombre=epigrafe.get("nombre"),
                item_location=f"{prefix}.epigrafe.item",
                **common,
            )
    for item in _objects(departamento.get("item"), path=f"{prefix}.item"):
        yield _item_row(
            item,
            epigrafe_nombre=None,
            item_location=f"{prefix}.item",
            **common,
        )
    texto = departamento.get("texto")
    if texto is None:
        return
    if not isinstance(texto, dict):
        raise ValueError(f"{prefix}.texto debe ser un objeto BOE.")
    for item in _objects(texto.get("item"), path=f"{prefix}.texto.item"):
        yield _item_row(
            item,
            epigrafe_nombre=None,
            item_location=f"{prefix}.texto.item",
            **common,
        )
    for epigrafe in _objects(
        texto.get("epigrafe"),
        path=f"{prefix}.texto.epigrafe",
    ):
        for item in _objects(
            epigrafe.get("item"),
            path=f"{prefix}.texto.epigrafe.item",
        ):
            yield _item_row(
                item,
                epigrafe_nombre=epigrafe.get("nombre"),
                item_location=f"{prefix}.texto.epigrafe.item",
                **common,
            )


def empty_boe_items() -> pd.DataFrame:
    """Devuelve el contrato tipado y vacío de items BOE normalizados."""

    data = {
        column: pd.Series(dtype=(
            "datetime64[ns]" if column == "fecha_publicacion" else "string"
        ))
        for column in BOE_ITEM_COLUMNS
    }
    return pd.DataFrame(data, columns=BOE_ITEM_COLUMNS)


def _apply_item_types(dataframe: pd.DataFrame) -> pd.DataFrame:
    typed = dataframe.copy()
    for column in _STRING_ITEM_COLUMNS:
        typed[column] = typed[column].astype("string")
    typed["fecha_publicacion"] = pd.to_datetime(
        typed["fecha_publicacion"],
        errors="raise",
    )
    return typed[list(BOE_ITEM_COLUMNS)]


def parse_boe_summary(payload: dict[str, Any]) -> pd.DataFrame:
    """Convierte un sumario BOE válido en items normalizados y tipados."""

    if not isinstance(payload, dict):
        raise TypeError("payload debe ser un diccionario.")
    try:
        sumario = payload["data"]["sumario"]
    except (KeyError, TypeError) as error:
        raise ValueError("La respuesta no contiene data.sumario.") from error
    if not isinstance(sumario, dict):
        raise ValueError("data.sumario debe ser un objeto.")
    metadata = sumario.get("metadatos")
    if not isinstance(metadata, dict):
        raise ValueError("data.sumario.metadatos debe ser un objeto.")
    raw_date = metadata.get("fecha_publicacion")
    try:
        publication_date = pd.to_datetime(
            _required_text(raw_date, path="fecha_publicacion"),
            format="%Y%m%d",
            errors="raise",
        )
    except (TypeError, ValueError) as error:
        raise ValueError("fecha_publicacion debe usar formato AAAAMMDD.") from error

    summary_hash = _summary_payload_sha256(payload)
    rows: list[dict[str, Any]] = []
    for diario in _objects(sumario.get("diario"), path="sumario.diario"):
        for seccion in _objects(diario.get("seccion"), path="diario.seccion"):
            departments = [
                (department, "departamento")
                for department in _objects(
                    seccion.get("departamento"),
                    path="seccion.departamento",
                )
            ]
            section_text = seccion.get("texto")
            if section_text is not None:
                if not isinstance(section_text, dict):
                    raise ValueError("seccion.texto debe ser un objeto BOE.")
                departments.extend(
                    (department, "seccion.texto.departamento")
                    for department in _objects(
                        section_text.get("departamento"),
                        path="seccion.texto.departamento",
                    )
                )
            for departamento, prefix in departments:
                rows.extend(_department_item_rows(
                    departamento,
                    prefix=prefix,
                    publication_date=publication_date,
                    summary_hash=summary_hash,
                    diario_numero=diario.get("numero"),
                    seccion=seccion,
                ))
    if not rows:
        if _count_item_nodes(sumario):
            raise ValueError(
                "El sumario contiene publicaciones en una estructura BOE "
                "no soportada."
            )
        return empty_boe_items()
    expected_items = _count_item_nodes(sumario)
    if len(rows) != expected_items:
        raise ValueError(
            "El sumario contiene publicaciones en una estructura BOE no "
            f"soportada: parseadas={len(rows)}, observadas={expected_items}."
        )
    result = _apply_item_types(
        pd.DataFrame.from_records(rows, columns=BOE_ITEM_COLUMNS)
    )
    duplicated = result["identificador"].duplicated(keep=False)
    if duplicated.any():
        sample = sorted(result.loc[duplicated, "identificador"].tolist())[:5]
        raise ValueError(f"El sumario contiene identificadores duplicados: {sample}")
    return result.sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).reset_index(drop=True)


def materialize_boe_items(items: pd.DataFrame, *, output_path: Path) -> Path:
    """Persiste items BOE tipados en una ruta Parquet explícita."""

    missing = set(BOE_ITEM_COLUMNS) - set(items.columns)
    if missing:
        raise ValueError(f"Faltan columnas BOE: {sorted(missing)}")
    ordered = _apply_item_types(items).sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).reset_index(drop=True)
    save_parquet(ordered, Path(output_path))
    return Path(output_path)
