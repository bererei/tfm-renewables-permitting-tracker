from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from renewables_permitting.app_reporting import (
    build_error_report_mailto,
    resolve_report_destination,
    validate_report_destination,
)


def test_mailto_escapes_context_and_leaves_description_space() -> None:
    url = build_error_report_mailto(
        "reports@example.org",
        project_name="FV Sol & Viento",
        boe_id="BOE-A-2026-12345",
        publication_date="2026-08-20",
        boe_url=(
            "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-12345"
        ),
        view_context="Ficha de proyecto",
        active_filters={
            "Tecnología": ("Fotovoltaica",),
            "Comunidad autónoma": ("País Vasco",),
        },
    )

    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    body = query["body"][0]
    assert parsed.scheme == "mailto"
    assert parsed.path == "reports@example.org"
    assert "FV Sol & Viento" in body
    assert "BOE-A-2026-12345" in body
    assert "2026-08-20" in body
    assert "Tipo de problema:" in body
    assert "[ ] Actuación administrativa" in body
    assert "Descripción del posible error:" in body
    assert "Tecnología: Fotovoltaica" in body
    assert "Comunidad autónoma: País Vasco" in body
    assert "https://www.boe.es/diario_boe/txt.php" in body
    assert "la aplicación pública no modifica directamente los datos" in body


def test_mailto_excludes_hashes_paths_and_raw_payloads() -> None:
    url = build_error_report_mailto(
        "reports@example.org",
        project_name="Proyecto seguro",
        project_id="project_safe",
        boe_id="BOE-A-2026-12345",
        publication_date="2026-08-20",
        view_context="Ficha de proyecto",
    )

    assert "/home/" not in url
    assert "downstream_id" not in url
    assert "raw" not in url.casefold()
    assert "project_0123456789abcdef0123456789abcdef" not in url


def test_mailto_project_context_keeps_stable_functional_lineage() -> None:
    url = build_error_report_mailto(
        "reports@example.org",
        project_name="Parque Eólico Alfa",
        project_id="project_alpha",
        boe_id="BOE-A-2026-12345",
        publication_date="20/08/2026",
        first_publication_date="10/01/2024",
        last_publication_date="20/08/2026",
        view_context="Ficha de proyecto",
    )

    query = parse_qs(urlsplit(url).query)
    body = query["body"][0]
    assert query["subject"] == [
        "Posible error en datos BOE — Parque Eólico Alfa"
    ]
    assert "ID de proyecto: project_alpha" in body
    assert "Primera publicación observada: 10/01/2024" in body
    assert "Última publicación observada: 20/08/2026" in body


@pytest.mark.parametrize(
    "value",
    ["", "not-an-email", "a@example.org?subject=inject", "a@example.org\nBcc:x"],
)
def test_report_destination_rejects_missing_or_unsafe_values(value: str) -> None:
    assert validate_report_destination(value) is None


def test_report_destination_accepts_a_plain_mailbox() -> None:
    assert validate_report_destination("reports@example.org") == "reports@example.org"


def test_report_destination_uses_environment_then_secret_fallback() -> None:
    assert resolve_report_destination(
        "environment@example.org",
        "secret@example.org",
    ) == "environment@example.org"
    assert resolve_report_destination(
        None,
        "secret@example.org",
    ) == "secret@example.org"
    assert resolve_report_destination(None, None) is None


def test_invalid_explicit_environment_destination_fails_closed() -> None:
    assert resolve_report_destination(
        "not-an-email",
        "secret@example.org",
    ) is None
