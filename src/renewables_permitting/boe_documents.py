from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import requests

from renewables_permitting.boe_candidates import (
    BOE_CANDIDATE_COLUMNS,
    CANDIDATE_POLICY_ID,
    CANDIDATE_POLICY_VERSION,
    build_doc_file_stem,
)
from renewables_permitting.boe_http import request_with_transient_retries
from renewables_permitting.utils import (
    clean_text,
    save_parquet,
    validate_required_columns,
)


DEFAULT_HTTP_TIMEOUT_SECONDS = 30.0
XML_DOWNLOAD_COLUMNS = (
    "identificador",
    "doc_file_stem",
    "fecha_publicacion",
    "source_url",
    "download_status",
    "http_status_code",
    "retrieved_at",
    "byte_count",
    "xml_sha256",
    "error_type",
    "error",
)
BOE_DOCUMENT_INPUT_COLUMNS = (
    "identificador",
    "fecha_publicacion",
    "titulo",
    "texto_limpio",
    "xml_status",
    "doc_file_stem",
    "url_html",
    "url_xml",
    "seccion_nombre",
    "departamento_nombre",
    "epigrafe_nombre",
    "summary_sha256",
    "candidate_policy_version",
    "candidate_policy_id",
    "xml_sha256",
    "texto_len",
    "parse_error",
    "source",
)
_HTTPGet = Callable[..., Any]
XMLFetchStatus = Literal[
    "downloaded",
    "missing_url",
    "http_error",
    "request_error",
    "empty_response",
    "invalid_response",
]


@dataclass(frozen=True)
class BOEXMLFetchResult:
    """Resultado explícito de obtener el XML oficial de un documento."""

    boe_id: str
    publication_date: date
    doc_file_stem: str
    source_url: str | None
    retrieved_at: datetime
    status: XMLFetchStatus
    http_status_code: int | None
    content: bytes | None
    byte_count: int
    xml_sha256: str | None
    error_type: str | None
    error: str | None


@dataclass(frozen=True)
class BOEParsedXMLDocument:
    """Identidad, título y texto canónico extraídos del XML oficial."""

    boe_id: str
    publication_date: date
    title: str
    text: str


def _xml_result(
    *,
    boe_id: str,
    publication_date: date,
    source_url: str | None,
    retrieved_at: datetime,
    status: XMLFetchStatus,
    http_status_code: int | None = None,
    content: bytes | None = None,
    error_type: str | None = None,
    error: str | None = None,
) -> BOEXMLFetchResult:
    return BOEXMLFetchResult(
        boe_id=boe_id,
        publication_date=publication_date,
        doc_file_stem=build_doc_file_stem(boe_id, publication_date),
        source_url=source_url,
        retrieved_at=retrieved_at,
        status=status,
        http_status_code=http_status_code,
        content=content,
        byte_count=len(content) if content is not None else 0,
        xml_sha256=sha256(content).hexdigest() if content is not None else None,
        error_type=error_type,
        error=error,
    )


def fetch_boe_document_xml(
    *,
    boe_id: str,
    publication_date: date,
    source_url: str | None,
    http_get: _HTTPGet | None = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    retrieved_at: datetime | None = None,
) -> BOEXMLFetchResult:
    """Obtiene XML BOE sin escribirlo y conserva estado y hash."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds debe ser mayor que cero.")
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    if not isinstance(source_url, str) or not source_url.strip():
        return _xml_result(
            boe_id=boe_id,
            publication_date=publication_date,
            source_url=None,
            retrieved_at=retrieved_at,
            status="missing_url",
            error_type="MISSING_URL",
            error="missing url_xml",
        )
    get = http_get or requests.get
    try:
        response = request_with_transient_retries(
            get,
            source_url,
            operation="xml",
            identifier=boe_id,
            request_kwargs={"timeout": timeout_seconds},
        )
    except requests.RequestException as error:
        return _xml_result(
            boe_id=boe_id,
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            status="request_error",
            error_type="REQUEST_ERROR",
            error=str(error),
        )
    http_status = int(response.status_code)
    if http_status != 200:
        return _xml_result(
            boe_id=boe_id,
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            status="http_error",
            http_status_code=http_status,
            error_type="HTTP_ERROR",
            error=f"HTTP {http_status}",
        )
    content = response.content
    if not isinstance(content, bytes) or not content.strip():
        return _xml_result(
            boe_id=boe_id,
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            status="empty_response",
            http_status_code=http_status,
            error_type="EMPTY_RESPONSE",
            error="El documento XML está vacío.",
        )
    try:
        ET.fromstring(content)
    except ET.ParseError as error:
        return _xml_result(
            boe_id=boe_id,
            publication_date=publication_date,
            source_url=source_url,
            retrieved_at=retrieved_at,
            status="invalid_response",
            http_status_code=http_status,
            error_type="INVALID_XML",
            error=str(error),
        )
    return _xml_result(
        boe_id=boe_id,
        publication_date=publication_date,
        source_url=source_url,
        retrieved_at=retrieved_at,
        status="downloaded",
        http_status_code=http_status,
        content=content,
    )


def _xml_metadata(result: BOEXMLFetchResult) -> dict[str, Any]:
    return {
        "identificador": result.boe_id,
        "fecha_publicacion": result.publication_date.isoformat(),
        "doc_file_stem": result.doc_file_stem,
        "source_url": result.source_url,
        "download_status": result.status,
        "http_status_code": result.http_status_code,
        "retrieved_at": result.retrieved_at.isoformat(),
        "byte_count": result.byte_count,
        "xml_sha256": result.xml_sha256,
        "error_type": result.error_type,
        "error": result.error,
    }


def materialize_boe_document_xml(
    result: BOEXMLFetchResult,
    *,
    output_dir: Path,
) -> Path:
    """Persiste XML y metadata por documento en un directorio explícito."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    xml_path = output_dir / f"{result.doc_file_stem}.xml"
    if result.status == "downloaded":
        if result.content is None:
            raise ValueError("Un resultado downloaded debe contener XML.")
        if xml_path.exists() and xml_path.read_bytes() != result.content:
            raise FileExistsError(
                f"Ya existe un XML incompatible: {xml_path}"
            )
        xml_path.write_bytes(result.content)
    elif xml_path.exists():
        raise FileExistsError(
            "No se reemplazará metadata de un XML existente con un resultado "
            f"{result.status}: {xml_path}"
        )
    metadata_path = output_dir / f"{result.doc_file_stem}.metadata.json"
    metadata_path.write_text(
        json.dumps(_xml_metadata(result), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def xml_download_results_dataframe(
    results: Iterable[BOEXMLFetchResult],
) -> pd.DataFrame:
    """Convierte resultados XML en un log tabular tipado y ordenado."""

    records = [_xml_metadata(result) for result in results]
    if records:
        dataframe = pd.DataFrame.from_records(records, columns=XML_DOWNLOAD_COLUMNS)
    else:
        dataframe = pd.DataFrame({
            column: pd.Series(dtype=(
                "datetime64[ns]"
                if column == "fecha_publicacion"
                else "datetime64[ns, UTC]"
                if column == "retrieved_at"
                else "Int64"
                if column in {"http_status_code", "byte_count"}
                else "string"
            ))
            for column in XML_DOWNLOAD_COLUMNS
        })
        return dataframe[list(XML_DOWNLOAD_COLUMNS)]
    dataframe["fecha_publicacion"] = pd.to_datetime(
        dataframe["fecha_publicacion"],
        errors="raise",
    )
    dataframe["retrieved_at"] = pd.to_datetime(
        dataframe["retrieved_at"],
        errors="raise",
        utc=True,
    )
    for column in ("http_status_code", "byte_count"):
        dataframe[column] = dataframe[column].astype("Int64")
    for column in XML_DOWNLOAD_COLUMNS:
        if column not in {
            "fecha_publicacion",
            "retrieved_at",
            "http_status_code",
            "byte_count",
        }:
            dataframe[column] = dataframe[column].astype("string")
    return dataframe[list(XML_DOWNLOAD_COLUMNS)].sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).reset_index(drop=True)


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", maxsplit=1)[-1].lower()


def _metadata_text(metadata: ET.Element, name: str) -> str:
    for child in metadata:
        if _local_name(child.tag) == name:
            value = clean_text("".join(child.itertext()))
            if value:
                return value
    raise ValueError(f"El XML no contiene metadatos.{name}.")


def _canonical_xml_text(root: ET.Element) -> str:
    block_tags = {
        "p", "parrafo", "titulo", "subtitulo", "epigrafe", "apartado",
        "seccion", "section", "div", "h1", "h2", "h3", "h4", "h5",
        "h6", "li", "item", "blockquote", "tr", "row", "fila", "br",
    }
    cell_tags = {"td", "th", "cell", "entry", "celda"}
    text_parts: list[str] = []

    def append_text(value: str | None) -> None:
        if value:
            normalized = re.sub(r"\s+", " ", value)
            if normalized.strip():
                text_parts.append(normalized)

    def append_line_break() -> None:
        if text_parts and text_parts[-1] != "\n":
            text_parts.append("\n")

    def walk(element: ET.Element) -> None:
        tag = _local_name(element.tag)
        if tag in block_tags:
            append_line_break()
        append_text(element.text)
        for child in element:
            walk(child)
            append_text(child.tail)
        if tag in cell_tags:
            text_parts.append(" | ")
        elif tag in block_tags:
            append_line_break()

    walk(root)
    return clean_text("".join(text_parts), preserve_line_breaks=True)


def parse_boe_document_xml(xml: bytes | str) -> BOEParsedXMLDocument:
    """Extrae identidad, título y texto conservando el orden XML legacy."""

    if not isinstance(xml, (bytes, str)) or not xml:
        raise ValueError("xml debe contener el documento oficial.")
    root = ET.fromstring(xml)
    metadata = next(
        (child for child in root if _local_name(child.tag) == "metadatos"),
        None,
    )
    if metadata is None:
        raise ValueError("El XML no contiene metadatos.")
    boe_id = _metadata_text(metadata, "identificador")
    title = _metadata_text(metadata, "titulo")
    raw_date = _metadata_text(metadata, "fecha_publicacion")
    try:
        publication_date = datetime.strptime(raw_date, "%Y%m%d").date()
    except ValueError as error:
        raise ValueError(
            "metadatos.fecha_publicacion debe usar formato AAAAMMDD."
        ) from error
    text = _canonical_xml_text(root)
    if not text:
        raise ValueError("El XML no contiene texto documental.")
    return BOEParsedXMLDocument(
        boe_id=boe_id,
        publication_date=publication_date,
        title=title,
        text=text,
    )


def empty_extractor_document_input() -> pd.DataFrame:
    """Devuelve el contrato tipado y vacío consumible por el extractor."""

    return pd.DataFrame({
        column: pd.Series(dtype=(
            "datetime64[ns]"
            if column == "fecha_publicacion"
            else "Int64"
            if column == "texto_len"
            else "string"
        ))
        for column in BOE_DOCUMENT_INPUT_COLUMNS
    })[list(BOE_DOCUMENT_INPUT_COLUMNS)]


def _document_record_base(row: Any) -> dict[str, Any]:
    return {
        "identificador": str(row.identificador),
        "fecha_publicacion": pd.Timestamp(row.fecha_publicacion),
        "titulo": row.titulo,
        "doc_file_stem": row.doc_file_stem,
        "url_html": row.url_html,
        "url_xml": row.url_xml,
        "seccion_nombre": row.seccion_nombre,
        "departamento_nombre": row.departamento_nombre,
        "epigrafe_nombre": row.epigrafe_nombre,
        "summary_sha256": row.summary_sha256,
        "candidate_policy_version": row.candidate_policy_version,
        "candidate_policy_id": row.candidate_policy_id,
        "source": "boe_xml",
    }


def build_extractor_document_input(
    candidates: pd.DataFrame,
    *,
    xml_dir: Path,
) -> pd.DataFrame:
    """Une candidatos con XML locales y produce el DataFrame del extractor."""

    if not isinstance(candidates, pd.DataFrame):
        raise TypeError("candidates debe ser un pandas.DataFrame.")
    validate_required_columns(candidates, set(BOE_CANDIDATE_COLUMNS))
    if candidates.empty:
        return empty_extractor_document_input()
    xml_dir = Path(xml_dir)
    if not xml_dir.is_dir():
        raise FileNotFoundError(f"El directorio de XML no existe: {xml_dir}")
    working = candidates.copy(deep=True)
    working["fecha_publicacion"] = pd.to_datetime(
        working["fecha_publicacion"],
        errors="raise",
    )
    records: list[dict[str, Any]] = []
    for row in working.sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).itertuples(index=False):
        expected_stem = build_doc_file_stem(
            str(row.identificador),
            row.fecha_publicacion.date(),
        )
        if row.doc_file_stem != expected_stem:
            raise ValueError(
                f"doc_file_stem incompatible para {row.identificador}."
            )
        if (
            row.candidate_policy_version != CANDIDATE_POLICY_VERSION
            or row.candidate_policy_id != CANDIDATE_POLICY_ID
        ):
            raise ValueError(
                f"Candidate policy incompatible para {row.identificador}."
            )
        base = _document_record_base(row)
        xml_path = xml_dir / f"{expected_stem}.xml"
        if not xml_path.exists():
            raise FileNotFoundError(
                f"Falta el XML oficial de {row.identificador}: {xml_path}"
            )
        xml_bytes = xml_path.read_bytes()
        xml_hash = sha256(xml_bytes).hexdigest()
        try:
            parsed = parse_boe_document_xml(xml_bytes)
        except (ET.ParseError, ValueError) as error:
            raise ValueError(
                f"No se pudo parsear el XML oficial de {row.identificador}."
            ) from error
        if (
            parsed.boe_id != row.identificador
            or parsed.publication_date != row.fecha_publicacion.date()
        ):
            raise ValueError(
                f"El XML {xml_path.name} no corresponde al candidato."
            )
        records.append({
            **base,
            "texto_limpio": parsed.text,
            "xml_status": "ok",
            "xml_sha256": xml_hash,
            "texto_len": len(parsed.text),
            "parse_error": pd.NA,
        })
    dataframe = pd.DataFrame.from_records(
        records,
        columns=BOE_DOCUMENT_INPUT_COLUMNS,
    )
    dataframe["fecha_publicacion"] = pd.to_datetime(
        dataframe["fecha_publicacion"],
        errors="raise",
    )
    dataframe["texto_len"] = dataframe["texto_len"].astype("Int64")
    for column in BOE_DOCUMENT_INPUT_COLUMNS:
        if column not in {"fecha_publicacion", "texto_len"}:
            dataframe[column] = dataframe[column].astype("string")
    return dataframe[list(BOE_DOCUMENT_INPUT_COLUMNS)].reset_index(drop=True)


def materialize_xml_download_log(
    results: Iterable[BOEXMLFetchResult],
    *,
    output_path: Path,
) -> Path:
    """Persiste el log tipado de descargas XML en una ruta explícita."""

    save_parquet(xml_download_results_dataframe(results), Path(output_path))
    return Path(output_path)


def materialize_extractor_document_input(
    documents: pd.DataFrame,
    *,
    output_path: Path,
) -> Path:
    """Persiste el input documental canónico en una ruta explícita."""

    missing = set(BOE_DOCUMENT_INPUT_COLUMNS) - set(documents.columns)
    if missing:
        raise ValueError(f"Faltan columnas documentales: {sorted(missing)}")
    ordered = documents[list(BOE_DOCUMENT_INPUT_COLUMNS)].sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).reset_index(drop=True)
    save_parquet(ordered, Path(output_path))
    return Path(output_path)
