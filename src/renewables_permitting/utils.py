from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
import re
import unicodedata


# ---------------------------------------------------------------------
# Nulos y conversión de valores
# ---------------------------------------------------------------------


def is_null_like(value: Any) -> bool:
    """
    Indica si un valor escalar debe tratarse como nulo.

    Reconoce `None`, `NaN`, `NaT` y `pd.NA`. Si el valor no es escalar,
    devuelve `False`.

    Examples
    --------
    >>> is_null_like(None)
    True

    >>> is_null_like(float("nan"))
    True

    >>> is_null_like("Huelva")
    False
    """
    if value is None:
        return True

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    return bool(result) if isinstance(result, bool) else False


def safe_str(value: Any) -> str:
    """
    Convierte un valor en string seguro.

    Devuelve cadena vacía para valores nulos, evitando cadenas como `"nan"` o
    `"<NA>"`.

    Examples
    --------
    >>> safe_str(None)
    ''

    >>> safe_str("BOE-A-2024-9608")
    'BOE-A-2024-9608'
    """
    if is_null_like(value):
        return ""

    return str(value)


def enum_value(value: Any) -> Any:
    """
    Extrae el `.value` de un miembro de `Enum`.

    No traduce ni infiere equivalencias. Devuelve exactamente el valor definido
    en el contrato.

    Examples
    --------
    >>> from enum import Enum
    >>>
    >>> class ProjectStatusInDocument(str, Enum):
    ...     PLANNED = "proyectado"
    ...     AUTHORIZED = "autorizado"
    ...
    >>> enum_value(ProjectStatusInDocument.PLANNED)
    'proyectado'

    >>> ProjectStatusInDocument.PLANNED.name
    'PLANNED'

    >>> ProjectStatusInDocument.PLANNED.value
    'proyectado'
    """
    if isinstance(value, Enum):
        return value.value

    return value


def to_date_or_none(value: Any) -> date | None:
    """
    Convierte un valor escalar a `datetime.date`.

    Devuelve `None` si el valor es nulo o no puede parsearse como fecha.

    Examples
    --------
    >>> to_date_or_none("2024-05-13")
    datetime.date(2024, 5, 13)

    >>> to_date_or_none("no es una fecha")
    None
    """
    if is_null_like(value):
        return None

    parsed = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(parsed):
        return None

    return parsed.date()


# ---------------------------------------------------------------------
# Colecciones
# ---------------------------------------------------------------------


def as_list(value: Any) -> list[Any]:
    """
    Convierte un valor en lista.

    Útil cuando una fuente externa puede devolver `None`, un único objeto o una
    lista de objetos.

    Examples
    --------
    >>> as_list(None)
    []

    >>> as_list("BOE-A-2024-9608")
    ['BOE-A-2024-9608']

    >>> as_list(["a", "b"])
    ['a', 'b']
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


# ---------------------------------------------------------------------
# Validación de DataFrames
# ---------------------------------------------------------------------


def validate_required_columns(
    df: pd.DataFrame,
    required_cols: set[str],
) -> None:
    """
    Valida que un DataFrame contenga todas las columnas obligatorias.

    Lanza `ValueError` si falta alguna columna.

    Examples
    --------
    >>> validate_required_columns(
    ...     df,
    ...     {"identificador", "fecha_publicacion", "titulo"},
    ... )
    """
    missing_cols = required_cols - set(df.columns)

    if missing_cols:
        raise ValueError(
            f"Faltan columnas obligatorias: {sorted(missing_cols)}"
        )


# ---------------------------------------------------------------------
# Entrada/salida
# ---------------------------------------------------------------------


def save_parquet(
    df: pd.DataFrame,
    path: Path,
    *,
    index: bool = False,
) -> None:
    """
    Guarda un DataFrame en formato Parquet.

    Crea automáticamente el directorio padre si no existe.

    Examples
    --------
    >>> save_parquet(
    ...     df=boe_candidates,
    ...     path=SILVER_DIR / "boe_candidates.parquet",
    ... )
    """
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_parquet(
        path,
        index=index,
    )


# ---------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------


def clean_text(text: str | None) -> str:
    """
    Limpia espacios conservando el contenido textual.

    No elimina tildes, mayúsculas ni signos de puntuación. Debe usarse cuando
    interesa conservar el texto documental, por ejemplo antes de enviarlo a IA.

    Examples
    --------
    >>> clean_text("Resolución\\n\\n de   6 de mayo")
    'Resolución de 6 de mayo'
    """
    if is_null_like(text):
        return ""

    text = re.sub(
        r"\s+",
        " ",
        str(text),
    )

    return text.strip()


def normalize_text(text: str | None) -> str:
    """
    Normaliza texto para búsquedas y matching determinista.

    La normalización es destructiva: convierte a minúsculas, elimina tildes y
    sustituye caracteres no alfanuméricos por espacios. No debe usarse como
    evidencia textual.

    Examples
    --------
    >>> normalize_text("Parque Eólico Badulaque, A Coruña")
    'parque eolico badulaque a coruna'

    >>> normalize_text("Desarrollos Renovables del Norte, S.L.")
    'desarrollos renovables del norte s l'
    """
    if is_null_like(text):
        return ""

    text = str(text).lower()

    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", errors="ignore")
        .decode("utf-8")
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()