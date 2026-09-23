from __future__ import annotations

import json
import re
from datetime import date
from hashlib import sha256
from pathlib import Path

import pandas as pd

from renewables_permitting.boe_source import BOE_ITEM_COLUMNS
from renewables_permitting.utils import normalize_text, save_parquet


CANDIDATE_POLICY_VERSION = "title_keywords_v1"
TITLE_KEYWORDS = (
    "almacenamiento",
    "autorizacion administrativa de construccion",
    "autorizacion administrativa previa",
    "bateria",
    "declaracion de impacto ambiental",
    "energia electrica",
    "energia solar",
    "instalacion solar",
    "eolic",
    "evacuacion",
    "fotovoltaic",
    "hibridacion",
    "impacto ambiental",
    "afeccion ambiental",
    "informacion publica",
    "infraestructura de evacuacion",
    "linea de evacuacion",
    "linea electrica",
    "parque eolico",
    "planta fotovoltaica",
    "planta solar",
    "plantas solares",
    "repotenciacion",
    "solar termica",
    "subestacion",
    "utilidad publica",
)
_POLICY_PAYLOAD = {
    "version": CANDIDATE_POLICY_VERSION,
    "normalization": "lower_nfkd_ascii_non_alphanumeric_spaces_v1",
    "title_keywords": list(TITLE_KEYWORDS),
    "effective_fields": ["titulo"],
}
CANDIDATE_POLICY_ID = sha256(json.dumps(
    _POLICY_PAYLOAD,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")).hexdigest()[:16]
BOE_CANDIDATE_COLUMNS = (
    "identificador",
    "doc_file_stem",
    *(column for column in BOE_ITEM_COLUMNS if column != "identificador"),
    "candidate_policy_version",
    "candidate_policy_id",
)
_BOE_ID_RE = re.compile(r"^BOE-[A-Z]-\d{4}-\d+$")
_TITLE_PATTERN = "|".join(re.escape(keyword) for keyword in TITLE_KEYWORDS)


def build_doc_file_stem(boe_id: str, publication_date: date) -> str:
    """Construye el nombre estable ``YYYYMMDD_BOE-ID`` de un documento."""

    if not isinstance(boe_id, str) or not _BOE_ID_RE.fullmatch(boe_id):
        raise ValueError("boe_id no tiene un formato documental BOE válido.")
    return f"{publication_date:%Y%m%d}_{boe_id}"


def empty_energy_candidates() -> pd.DataFrame:
    """Devuelve el contrato tipado y vacío de candidatos energéticos."""

    data = {
        column: pd.Series(dtype=(
            "datetime64[ns]" if column == "fecha_publicacion" else "string"
        ))
        for column in BOE_CANDIDATE_COLUMNS
    }
    return pd.DataFrame(data, columns=BOE_CANDIDATE_COLUMNS)


def select_energy_candidates(items: pd.DataFrame) -> pd.DataFrame:
    """Selecciona por keywords del título normalizado, como el notebook 03."""

    if not isinstance(items, pd.DataFrame):
        raise TypeError("items debe ser un pandas.DataFrame.")
    missing = set(BOE_ITEM_COLUMNS) - set(items.columns)
    if missing:
        raise ValueError(f"Faltan columnas BOE: {sorted(missing)}")
    if items.empty:
        return empty_energy_candidates()
    working = items.copy(deep=True)
    working["fecha_publicacion"] = pd.to_datetime(
        working["fecha_publicacion"],
        errors="raise",
    )
    working["titulo_norm"] = working["titulo"].map(normalize_text).astype(
        "string"
    )
    mask = working["titulo_norm"].str.contains(
        _TITLE_PATTERN,
        regex=True,
        na=False,
    )
    selected = working.loc[mask].copy()
    if selected.empty:
        return empty_energy_candidates()
    selected["doc_file_stem"] = [
        build_doc_file_stem(str(row.identificador), row.fecha_publicacion.date())
        for row in selected.itertuples(index=False)
    ]
    selected["candidate_policy_version"] = CANDIDATE_POLICY_VERSION
    selected["candidate_policy_id"] = CANDIDATE_POLICY_ID
    for column in BOE_CANDIDATE_COLUMNS:
        if column != "fecha_publicacion":
            selected[column] = selected[column].astype("string")
    return selected[list(BOE_CANDIDATE_COLUMNS)].sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).reset_index(drop=True)


def materialize_energy_candidates(
    candidates: pd.DataFrame,
    *,
    output_path: Path,
) -> Path:
    """Persiste candidatos energéticos en una ruta Parquet explícita."""

    missing = set(BOE_CANDIDATE_COLUMNS) - set(candidates.columns)
    if missing:
        raise ValueError(f"Faltan columnas de candidatos: {sorted(missing)}")
    ordered = candidates[list(BOE_CANDIDATE_COLUMNS)].sort_values(
        ["fecha_publicacion", "identificador"],
        kind="stable",
    ).reset_index(drop=True)
    save_parquet(ordered, Path(output_path))
    return Path(output_path)
