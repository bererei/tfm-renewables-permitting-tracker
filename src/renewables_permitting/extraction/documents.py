from __future__ import annotations

import re
from datetime import date
from hashlib import sha256
from typing import Any

import pandas as pd

from renewables_permitting.extraction.models import (
    BOE_ID_ADAPTER,
    BOESourceDocument,
    PreparedDocumentPrompt,
    SelectedDocumentText,
)


MAX_DOCUMENT_CHARS: int | None = None
MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX = 1_000
_AFFECTED_ASSETS_ANNEX_HEADING_RE = re.compile(
    r"(?im)^[ \t]*(?:ANEXO(?:\s+[A-Z0-9IVX.-]+)?\s*[:.-]?\s*)?"
    r"RELACI[ÓO]N(?:\s+CONCRETA\s+E\s+INDIVIDUALIZADA)?"
    r"\s+DE\s+BIENES\s+Y\s+DERECHOS\s+AFECTADOS.*$"
)

DOCUMENT_PROMPT_TEMPLATE = r"""
Analiza exclusivamente la publicación delimitada a continuación.
No reproduzcas boe_id ni publication_date en BOEAIExtraction.

BOE_ID: {boe_id}
FECHA_PUBLICACION: {publication_date}
TITULO: {title}
ESTRATEGIA_TEXTO: {input_selection_strategy}

<BOE_DOCUMENT>
{document_text}
</BOE_DOCUMENT>
""".strip()


def _required_text(
    value: Any,
    *,
    field_name: str,
    strip_value: bool = True,
) -> str:
    if value is None or value is pd.NA or bool(pd.isna(value)):
        raise ValueError(f"{field_name} no puede ser nulo.")
    text = str(value)
    text = text.strip() if strip_value else text
    if not text.strip():
        raise ValueError(f"{field_name} no puede estar vacío.")
    return text


def _required_date(value: Any, *, field_name: str) -> date:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{field_name} no contiene una fecha válida.")
    return parsed.date()


def _source_document_hash(
    *,
    boe_id: str,
    publication_date: date,
    title: str,
    text: str,
) -> str:
    value = "\n".join([boe_id, publication_date.isoformat(), title, text])
    return sha256(value.encode("utf-8")).hexdigest()


def build_source_document(row: pd.Series) -> BOESourceDocument:
    boe_id = BOE_ID_ADAPTER.validate_python(
        _required_text(row["identificador"], field_name="identificador")
    )
    publication_date = _required_date(
        row["fecha_publicacion"],
        field_name="fecha_publicacion",
    )
    title = _required_text(row["titulo"], field_name="titulo")
    text = _required_text(
        row["texto_limpio"],
        field_name="texto_limpio",
        strip_value=False,
    )
    return BOESourceDocument(
        boe_id=boe_id,
        publication_date=publication_date,
        title=title,
        text=text,
        source_document_sha256=_source_document_hash(
            boe_id=boe_id,
            publication_date=publication_date,
            title=title,
            text=text,
        ),
    )


def select_document_text(text: str) -> SelectedDocumentText:
    if not text.strip():
        raise ValueError("El texto documental no puede estar vacío.")

    selected = text
    strategy = "full_text"
    marker: str | None = None
    for match in _AFFECTED_ASSETS_ANNEX_HEADING_RE.finditer(text):
        if match.start() < MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX:
            continue
        candidate = text[: match.start()].rstrip()
        if candidate:
            selected = candidate
            strategy = "before_affected_assets_annex"
            marker = match.group(0).strip()
            break

    if MAX_DOCUMENT_CHARS is not None and len(selected) > MAX_DOCUMENT_CHARS:
        raise ValueError(
            f"El documento contiene {len(selected):,} caracteres y supera "
            f"MAX_DOCUMENT_CHARS={MAX_DOCUMENT_CHARS:,}; no se truncará."
        )

    return SelectedDocumentText(
        text=selected,
        strategy=strategy,
        marker=marker,
        excluded_chars=len(text) - len(selected),
        text_sha256=sha256(selected.encode("utf-8")).hexdigest(),
    )


def build_document_prompt(document: BOESourceDocument) -> PreparedDocumentPrompt:
    selected = select_document_text(document.text)
    prompt = DOCUMENT_PROMPT_TEMPLATE.format(
        boe_id=document.boe_id,
        publication_date=document.publication_date.isoformat(),
        title=document.title,
        input_selection_strategy=selected.strategy,
        document_text=selected.text,
    )
    return PreparedDocumentPrompt(
        prompt=prompt,
        input_text_chars=len(selected.text),
        input_text_sha256=selected.text_sha256,
        input_selection_strategy=selected.strategy,
        input_selection_marker=selected.marker,
        input_excluded_chars=selected.excluded_chars,
    )
