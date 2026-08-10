import json
from datetime import date, datetime, timezone
from hashlib import sha256

import pandas as pd
import pytest
import requests

from renewables_permitting.boe_candidates import (
    BOE_CANDIDATE_COLUMNS,
    CANDIDATE_POLICY_ID,
    CANDIDATE_POLICY_VERSION,
)
from renewables_permitting.boe_documents import (
    BOE_DOCUMENT_INPUT_COLUMNS,
    XML_DOWNLOAD_COLUMNS,
    BOEXMLFetchResult,
    build_extractor_document_input,
    fetch_boe_document_xml,
    materialize_boe_document_xml,
    materialize_extractor_document_input,
    materialize_xml_download_log,
    parse_boe_document_xml,
    xml_download_results_dataframe,
)
from renewables_permitting.extraction.documents import build_source_document


XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<documento>
  <metadatos>
    <identificador>BOE-A-2026-1</identificador>
    <titulo>Autorizacion del parque Aurora.</titulo>
    <fecha_publicacion>20260102</fecha_publicacion>
  </metadatos>
  <texto>
    <p>Primer parrafo <b>con detalle</b> final.</p>
    <p>Segundo parrafo.</p>
    <table><tr><td>A</td><td>B</td></tr></table>
  </texto>
</documento>
"""


class _Response:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content


def _candidate() -> pd.DataFrame:
    row = {column: pd.NA for column in BOE_CANDIDATE_COLUMNS}
    row.update({
        "identificador": "BOE-A-2026-1",
        "doc_file_stem": "20260102_BOE-A-2026-1",
        "fecha_publicacion": pd.Timestamp("2026-01-02"),
        "titulo": "Autorizacion del parque Aurora.",
        "url_html": "https://www.boe.es/txt.php?id=BOE-A-2026-1",
        "url_xml": "https://www.boe.es/xml.php?id=BOE-A-2026-1",
        "source": "boe",
        "summary_sha256": "a" * 64,
        "candidate_policy_version": CANDIDATE_POLICY_VERSION,
        "candidate_policy_id": CANDIDATE_POLICY_ID,
    })
    return pd.DataFrame.from_records([row], columns=BOE_CANDIDATE_COLUMNS)


def test_xml_fetch_success_hash_and_failures_are_explicit() -> None:
    calls = []

    def get(url, *, timeout):
        calls.append((url, timeout))
        return _Response(200, XML)

    result = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://www.boe.es/xml.php?id=BOE-A-2026-1",
        http_get=get,
        timeout_seconds=8,
        retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    assert isinstance(result, BOEXMLFetchResult)
    assert result.status == "downloaded"
    assert result.content == XML
    assert result.xml_sha256 == sha256(XML).hexdigest()
    assert calls == [("https://www.boe.es/xml.php?id=BOE-A-2026-1", 8)]

    http_error = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://example.invalid/document.xml",
        http_get=lambda *args, **kwargs: _Response(500),
    )
    request_error = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://example.invalid/document.xml",
        http_get=lambda *args, **kwargs: (_ for _ in ()).throw(
            requests.ConnectionError("offline")
        ),
    )
    empty = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://example.invalid/document.xml",
        http_get=lambda *args, **kwargs: _Response(200, b""),
    )
    invalid = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://example.invalid/document.xml",
        http_get=lambda *args, **kwargs: _Response(200, b"not XML"),
    )
    assert (
        http_error.status,
        request_error.status,
        empty.status,
        invalid.status,
    ) == (
        "http_error",
        "request_error",
        "empty_response",
        "invalid_response",
    )


def test_xml_materialization_records_provenance_and_rejects_incompatible_file(
    tmp_path,
) -> None:
    result = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://www.boe.es/xml.php?id=BOE-A-2026-1",
        http_get=lambda *args, **kwargs: _Response(200, XML),
        retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    metadata_path = materialize_boe_document_xml(result, output_dir=tmp_path)
    xml_path = tmp_path / "20260102_BOE-A-2026-1.xml"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert xml_path.read_bytes() == XML
    assert metadata["xml_sha256"] == sha256(XML).hexdigest()
    assert metadata["byte_count"] == len(XML)

    xml_path.write_bytes(b"different")
    with pytest.raises(FileExistsError, match="incompatible"):
        materialize_boe_document_xml(result, output_dir=tmp_path)


def test_xml_parser_preserves_exact_order_tail_and_table_cells() -> None:
    parsed = parse_boe_document_xml(XML)

    assert parsed.boe_id == "BOE-A-2026-1"
    assert parsed.publication_date == date(2026, 1, 2)
    assert parsed.title == "Autorizacion del parque Aurora."
    assert parsed.text == (
        "BOE-A-2026-1\nAutorizacion del parque Aurora.\n20260102\n"
        "Primer parrafo con detalle final.\n"
        "Segundo parrafo.\nA | B"
    )


def test_document_dataframe_is_typed_deterministic_non_mutating_and_extractable(
    tmp_path,
) -> None:
    candidates = _candidate()
    snapshot = candidates.copy(deep=True)
    (tmp_path / "20260102_BOE-A-2026-1.xml").write_bytes(XML)

    documents = build_extractor_document_input(candidates, xml_dir=tmp_path)

    assert documents.columns.tolist() == list(BOE_DOCUMENT_INPUT_COLUMNS)
    assert documents["xml_status"].tolist() == ["ok"]
    assert documents["xml_sha256"].tolist() == [sha256(XML).hexdigest()]
    assert str(documents["identificador"].dtype) == "string"
    assert str(documents["fecha_publicacion"].dtype) == "datetime64[ns]"
    assert build_source_document(documents.iloc[0]).boe_id == "BOE-A-2026-1"
    pd.testing.assert_frame_equal(candidates, snapshot)

    empty = build_extractor_document_input(
        candidates.iloc[0:0],
        xml_dir=tmp_path / "does-not-need-to-exist",
    )
    assert empty.empty
    assert empty.columns.tolist() == list(BOE_DOCUMENT_INPUT_COLUMNS)
    assert str(empty["texto_len"].dtype) == "Int64"

    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="Falta el XML oficial"):
        build_extractor_document_input(
            candidates,
            xml_dir=missing_dir,
        )


def test_xml_download_log_typed_empty_and_input_permutation(tmp_path) -> None:
    empty = xml_download_results_dataframe([])
    assert empty.columns.tolist() == list(XML_DOWNLOAD_COLUMNS)
    assert str(empty["byte_count"].dtype) == "Int64"

    result = fetch_boe_document_xml(
        boe_id="BOE-A-2026-1",
        publication_date=date(2026, 1, 2),
        source_url="https://www.boe.es/xml.php?id=BOE-A-2026-1",
        http_get=lambda *args, **kwargs: _Response(200, XML),
        retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    log = xml_download_results_dataframe([result])
    assert log["identificador"].tolist() == ["BOE-A-2026-1"]
    assert str(log["fecha_publicacion"].dtype) == "datetime64[ns]"
    assert str(log["retrieved_at"].dtype) == "datetime64[ns, UTC]"
    assert str(log["byte_count"].dtype) == "Int64"

    candidates = pd.concat([_candidate(), _candidate()], ignore_index=True)
    candidates.loc[1, "identificador"] = "BOE-A-2026-2"
    candidates.loc[1, "doc_file_stem"] = "20260103_BOE-A-2026-2"
    candidates.loc[1, "fecha_publicacion"] = pd.Timestamp("2026-01-03")
    candidates.loc[1, "url_xml"] = "https://www.boe.es/xml.php?id=BOE-A-2026-2"
    second_xml = XML.replace(b"BOE-A-2026-1", b"BOE-A-2026-2").replace(
        b"20260102",
        b"20260103",
    )
    (tmp_path / "20260102_BOE-A-2026-1.xml").write_bytes(XML)
    (tmp_path / "20260103_BOE-A-2026-2.xml").write_bytes(second_xml)

    first = build_extractor_document_input(candidates, xml_dir=tmp_path)
    second = build_extractor_document_input(
        candidates.iloc[::-1].reset_index(drop=True),
        xml_dir=tmp_path,
    )
    pd.testing.assert_frame_equal(first, second)

    document_path = tmp_path / "silver" / "documents.parquet"
    log_path = tmp_path / "bronze" / "download_log.parquet"
    assert materialize_extractor_document_input(
        first,
        output_path=document_path,
    ) == document_path
    assert materialize_xml_download_log(
        [result],
        output_path=log_path,
    ) == log_path
    assert pd.read_parquet(document_path).columns.tolist() == list(
        BOE_DOCUMENT_INPUT_COLUMNS
    )
    assert pd.read_parquet(log_path).columns.tolist() == list(
        XML_DOWNLOAD_COLUMNS
    )
