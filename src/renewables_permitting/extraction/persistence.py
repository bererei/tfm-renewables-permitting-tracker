from __future__ import annotations

from pathlib import Path

import pandas as pd


def save_parquet_atomic(dataframe: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    dataframe.to_parquet(temporary, index=False)
    temporary.replace(output_path)
