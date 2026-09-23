"""Safe construction of the public, non-persistent error-report mailto."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import quote, urlencode


_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def validate_report_destination(value: object) -> str | None:
    """Return a plain mailbox or ``None`` for missing/unsafe configuration."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > 254
        or _CONTROL_RE.search(candidate)
        or _EMAIL_RE.fullmatch(candidate) is None
    ):
        return None
    return candidate


def resolve_report_destination(
    environment_value: object,
    secret_value: object,
) -> str | None:
    """Resolve the mailbox with explicit environment-over-secret precedence.

    An explicitly present but invalid environment value fails closed instead of
    silently changing the operator-selected destination.
    """

    if environment_value is not None:
        return validate_report_destination(environment_value)
    return validate_report_destination(secret_value)


def _context_value(value: object | None, *, limit: int) -> str | None:
    """Normalize bounded Gold display context without accepting controls."""

    if value is None:
        return None
    text = str(value).strip()
    if not text or _CONTROL_RE.search(text):
        return None
    return text[:limit]


def _filter_lines(active_filters: Mapping[str, object] | None) -> list[str]:
    """Render bounded, display-only filter values without internal keys."""

    if not active_filters:
        return ["Filtros activos: ninguno"]
    lines = ["Filtros activos:"]
    for raw_label, raw_values in list(active_filters.items())[:12]:
        label = _context_value(raw_label, limit=60)
        if label is None:
            continue
        if isinstance(raw_values, str) or not isinstance(raw_values, Sequence):
            values = (raw_values,)
        else:
            values = raw_values
        normalized = [
            value
            for value in (
                _context_value(item, limit=100) for item in list(values)[:11]
            )
            if value is not None
        ]
        if not normalized:
            continue
        if len(normalized) > 10:
            rendered = f"{', '.join(normalized[:10])} y más"
        else:
            rendered = ", ".join(normalized)
        lines.append(f"- {label}: {rendered}")
    return lines if len(lines) > 1 else ["Filtros activos: ninguno"]


def build_error_report_mailto(
    destination: str,
    *,
    project_name: object | None = None,
    project_id: object | None = None,
    boe_id: object | None = None,
    publication_date: object | None = None,
    boe_url: object | None = None,
    first_publication_date: object | None = None,
    last_publication_date: object | None = None,
    view_context: object = "Aplicación pública",
    active_filters: Mapping[str, object] | None = None,
) -> str:
    """Build a bounded report email without paths, hashes or raw payloads."""

    mailbox = validate_report_destination(destination)
    if mailbox is None:
        raise ValueError("El destino de reportes no es una dirección válida.")
    project = _context_value(project_name, limit=240)
    stable_project_id = _context_value(project_id, limit=100)
    boe = _context_value(boe_id, limit=40)
    publication = _context_value(publication_date, limit=20)
    public_boe_url = _context_value(boe_url, limit=180)
    first_publication = _context_value(first_publication_date, limit=20)
    last_publication = _context_value(last_publication_date, limit=20)
    context = _context_value(view_context, limit=80) or "Aplicación pública"
    lines = [
        f"Vista: {context}",
    ]
    if project is not None:
        lines.append(f"Proyecto: {project}")
    if stable_project_id is not None:
        lines.append(f"ID de proyecto: {stable_project_id}")
    if boe is not None:
        lines.append(f"BOE: {boe}")
    if publication is not None:
        lines.append(f"Fecha del BOE: {publication}")
    if public_boe_url is not None:
        lines.append(f"Enlace BOE: {public_boe_url}")
    if first_publication is not None:
        lines.append(f"Primera publicación observada: {first_publication}")
    if last_publication is not None:
        lines.append(f"Última publicación observada: {last_publication}")
    lines.extend(_filter_lines(active_filters))
    lines.extend([
        "",
        "Tipo de problema:",
        "[ ] Nombre/dato del proyecto",
        "[ ] Publicación BOE",
        "[ ] Actuación administrativa",
        "[ ] Territorio",
        "[ ] Agrupación de proyectos",
        "[ ] Otro",
        "",
        "Descripción del posible error:",
        "",
        (
            "La corrección, si procede, se aplicará mediante el proceso de "
            "revisión y regeneración de datos; la aplicación pública no "
            "modifica directamente los datos."
        ),
        "",
        "Por favor, no incluya datos personales ni información sensible.",
    ])
    subject_context = project or context
    query = urlencode(
        {
            "subject": f"Posible error en datos BOE — {subject_context}",
            "body": "\n".join(lines),
        },
        quote_via=quote,
    )
    return f"mailto:{quote(mailbox, safe='@+._-')}?{query}"
