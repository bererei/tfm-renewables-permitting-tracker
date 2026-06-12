from typing import Any
from pathlib import Path
import pandas as pd


def as_list(value: Any) -> list[Any]:
    """
    Normaliza un valor para tratarlo siempre como una lista.

    Se utiliza principalmente para manejar respuestas de la API del BOE
    donde un nodo puede aparecer como un único elemento o como una lista
    de elementos.

    Parámetros
    ----------
    value : Any
        Valor a normalizar.

    Retorna
    -------
    list[Any]
        - [] si value es None.
        - value si ya es una lista.
        - [value] en cualquier otro caso.
    """
    if value is None:
        return []

    return value if isinstance(value, list) else [value]



def validate_required_columns(df: pd.DataFrame, required_cols: set[str]) -> None:
    missing_cols = required_cols - set(df.columns)

    if missing_cols:
        raise ValueError(f"Faltan columnas obligatorias: {sorted(missing_cols)}")



def save_parquet(
    df: pd.DataFrame,
    path: Path,
    *,
    index: bool = False,
) -> None:
    """
    Guarda un DataFrame en formato Parquet creando los
    directorios necesarios si no existen.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame a guardar.

    path : Path
        Ruta destino del fichero parquet.

    index : bool, default=False
        Indica si debe persistirse el índice.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(
        path,
        index=index,
    )