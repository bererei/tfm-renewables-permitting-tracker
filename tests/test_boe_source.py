import json
import logging
import time
from datetime import date, datetime, timezone
from hashlib import sha256

import pandas as pd
import pytest
import requests

from renewables_permitting.boe_source import (
    BOE_ITEM_COLUMNS,
    BOESummaryFetchResult,
    fetch_boe_summaries,
    fetch_boe_summary,
    inclusive_date_range,
    materialize_boe_items,
    materialize_boe_summary,
    parse_boe_summary,
)


class _Response:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _summary_payload() -> dict:
    def item(boe_id: str, title: str) -> dict:
        return {
            "identificador": boe_id,
            "control": "2026/1",
            "titulo": title,
            "url_html": f"https://www.boe.es/diario_boe/txt.php?id={boe_id}",
            "url_xml": f"https://www.boe.es/xml.php?id={boe_id}",
        }

    return {
        "status": {"code": "200", "text": "ok"},
        "data": {"sumario": {
            "metadatos": {"fecha_publicacion": "20260102"},
            "diario": {"numero": "2", "seccion": [{
                "codigo": "3",
                "nombre": "III. Otras disposiciones",
                "departamento": {
                    "codigo": "9575",
                    "nombre": "MINISTERIO PARA LA TRANSICIÓN ECOLÓGICA",
                    "epigrafe": {
                        "nombre": "Energía eléctrica",
                        "item": item(
                            "BOE-A-2026-101",
                            "Autorización del parque eólico Aurora.",
                        ),
                    },
                    "texto": {"epigrafe": {
                        "nombre": "Evaluación ambiental",
                        "item": item(
                            "BOE-A-2026-100",
                            "Declaración de impacto ambiental de Aurora.",
                        ),
                    }},
                },
            }]},
        }},
    }


def test_inclusive_date_range_and_invalid_range() -> None:
    assert inclusive_date_range(
        date(2026, 1, 1),
        date(2026, 1, 3),
    ) == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    assert inclusive_date_range(
        date(2025, 12, 31),
        date(2026, 1, 1),
    ) == [date(2025, 12, 31), date(2026, 1, 1)]
    with pytest.raises(ValueError, match="start_date"):
        inclusive_date_range(date(2026, 1, 2), date(2026, 1, 1))


def test_summary_fetch_success_range_and_no_publication_are_explicit() -> None:
    payload = _summary_payload()
    calls: list[tuple[str, float]] = []

    def get(url, *, headers, timeout):
        calls.append((url, timeout))
        return _Response(200, payload)

    result = fetch_boe_summary(
        date(2026, 1, 2),
        http_get=get,
        timeout_seconds=12.5,
        retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    assert isinstance(result, BOESummaryFetchResult)
    assert result.status == "success"
    assert result.payload == payload
    assert result.item_count == 2
    assert calls == [(
        "https://www.boe.es/datosabiertos/api/boe/sumario/20260102",
        12.5,
    )]

    no_publication = fetch_boe_summary(
        date(2026, 1, 4),
        http_get=lambda *args, **kwargs: _Response(404),
    )
    assert no_publication.status == "no_publication"
    assert no_publication.payload is None

    boe_no_publication = fetch_boe_summary(
        date(2026, 1, 5),
        http_get=lambda *args, **kwargs: _Response(
            200,
            {"status": {"code": "404", "text": "No disponible"}},
        ),
    )
    assert boe_no_publication.status == "no_publication"
    assert boe_no_publication.error_type == "BOE_404"

    results = fetch_boe_summaries(
        date(2026, 1, 2),
        date(2026, 1, 3),
        http_get=get,
    )
    assert [result.publication_date for result in results] == [
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]


def test_summary_retries_transient_request_and_preserves_result(
    monkeypatch,
    caplog,
) -> None:
    retrieved_at = datetime(2026, 1, 3, tzinfo=timezone.utc)
    outcomes = iter([
        requests.ConnectionError("temporary connection reset"),
        _Response(200, _summary_payload()),
    ])
    calls = 0
    sleeps: list[float] = []

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(time, "sleep", sleeps.append)
    with caplog.at_level(logging.WARNING):
        retried = fetch_boe_summary(
            date(2026, 1, 2),
            http_get=get,
            retrieved_at=retrieved_at,
        )
    first_try = fetch_boe_summary(
        date(2026, 1, 2),
        http_get=lambda *args, **kwargs: _Response(200, _summary_payload()),
        retrieved_at=retrieved_at,
    )

    assert retried == first_try
    assert calls == 2
    assert sleeps == [1.0]
    assert "operation=summary" in caplog.text
    assert "identifier=2026-01-02" in caplog.text
    assert "attempt=1/4" in caplog.text
    assert "delay_seconds=1" in caplog.text


@pytest.mark.parametrize("transient_status", [408, 429, 500, 502, 503, 504])
def test_summary_retries_transient_http_status(
    transient_status: int,
    monkeypatch,
) -> None:
    responses = iter([
        _Response(transient_status),
        _Response(200, _summary_payload()),
    ])
    calls = 0
    sleeps: list[float] = []

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(time, "sleep", sleeps.append)
    result = fetch_boe_summary(date(2026, 1, 2), http_get=get)

    assert result.status == "success"
    assert calls == 2
    assert sleeps == [1.0]


def test_summary_retry_exhaustion_uses_bounded_backoff(monkeypatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise requests.Timeout("temporary timeout")

    monkeypatch.setattr(time, "sleep", sleeps.append)
    result = fetch_boe_summary(date(2026, 1, 2), http_get=get)

    assert result.status == "failed"
    assert result.error_type == "REQUEST_ERROR"
    assert calls == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_summary_404_is_not_retried(monkeypatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Response(404)

    monkeypatch.setattr(time, "sleep", sleeps.append)
    result = fetch_boe_summary(date(2026, 1, 2), http_get=get)

    assert result.status == "no_publication"
    assert result.error_type == "HTTP_404"
    assert calls == 1
    assert sleeps == []


def test_non_transient_request_exception_is_not_retried(monkeypatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise requests.exceptions.InvalidURL("invalid source URL")

    monkeypatch.setattr(time, "sleep", sleeps.append)
    result = fetch_boe_summary(date(2026, 1, 2), http_get=get)

    assert result.status == "failed"
    assert result.error_type == "REQUEST_ERROR"
    assert calls == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("get", "error_type"),
    [
        (lambda *args, **kwargs: _Response(400), "HTTP_ERROR"),
        (
            lambda *args, **kwargs: _Response(200, ValueError("bad json")),
            "INVALID_JSON",
        ),
    ],
)
def test_summary_failures_are_not_masked_as_no_publication(
    get,
    error_type: str,
) -> None:
    result = fetch_boe_summary(date(2026, 1, 2), http_get=get)

    assert result.status == "failed"
    assert result.error_type == error_type
    assert result.status != "no_publication"


def test_summary_materialization_hashes_exact_persisted_payload(tmp_path) -> None:
    result = fetch_boe_summary(
        date(2026, 1, 2),
        http_get=lambda *args, **kwargs: _Response(200, _summary_payload()),
        retrieved_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    metadata_path = materialize_boe_summary(result, output_dir=tmp_path)
    summary_path = tmp_path / "20260102" / "sumario.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata_path == tmp_path / "20260102" / "metadata.json"
    assert metadata["summary_sha256"] == sha256(
        summary_path.read_bytes()
    ).hexdigest()
    assert metadata["records_downloaded"] == 2
    assert metadata["source"] == result.source_url


def test_parse_real_summary_shape_supports_observed_nested_text_epigraph() -> None:
    payload = _summary_payload()

    items = parse_boe_summary(payload)

    assert items.columns.tolist() == list(BOE_ITEM_COLUMNS)
    assert items["identificador"].tolist() == [
        "BOE-A-2026-100",
        "BOE-A-2026-101",
    ]
    assert items["item_location"].tolist() == [
        "departamento.texto.epigrafe.item",
        "departamento.epigrafe.item",
    ]
    assert str(items["identificador"].dtype) == "string"
    assert str(items["fecha_publicacion"].dtype) == "datetime64[ns]"
    assert items["summary_sha256"].str.fullmatch(r"[0-9a-f]{64}").all()


def test_boe_items_materialization_uses_only_explicit_path(tmp_path) -> None:
    items = parse_boe_summary(_summary_payload())
    output_path = tmp_path / "normalized" / "boe_items.parquet"

    returned = materialize_boe_items(items, output_path=output_path)
    restored = pd.read_parquet(returned)

    assert returned == output_path
    assert restored.columns.tolist() == list(BOE_ITEM_COLUMNS)
    assert restored["identificador"].tolist() == items["identificador"].tolist()


def test_parse_summary_rejects_malformed_and_returns_typed_empty() -> None:
    with pytest.raises(ValueError, match="data.sumario"):
        parse_boe_summary({"status": {"code": "200"}})

    payload = _summary_payload()
    payload["data"]["sumario"]["diario"] = None
    empty = parse_boe_summary(payload)

    assert empty.empty
    assert empty.columns.tolist() == list(BOE_ITEM_COLUMNS)
    assert str(empty["identificador"].dtype) == "string"
    assert str(empty["fecha_publicacion"].dtype) == "datetime64[ns]"

    payload = _summary_payload()
    department = payload["data"]["sumario"]["diario"]["seccion"][0][
        "departamento"
    ]
    department["epigrafe"] = None
    department["texto"] = {"unexpected": {
        "item": {
            "identificador": "BOE-A-2026-999",
            "titulo": "Publicación inesperada.",
            "url_xml": "https://www.boe.es/xml.php?id=BOE-A-2026-999",
        }
    }}
    with pytest.raises(ValueError, match="estructura BOE no soportada"):
        parse_boe_summary(payload)
