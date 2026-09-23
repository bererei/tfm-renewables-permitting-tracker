import runpy
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.extraction.persistence import save_parquet_atomic


def _dataframe() -> pd.DataFrame:
    dataframe = pd.DataFrame(
        {
            "integer_value": pd.Series([1, 2], dtype="int64"),
            "float_value": pd.Series([1.5, 2.5], dtype="float64"),
            "boolean_value": pd.Series([True, False], dtype="bool"),
            "text_value": pd.Series(["uno", "dos"], dtype="object"),
            "date_value": pd.to_datetime(
                [datetime(2024, 1, 2), datetime(2025, 3, 4)]
            ),
        }
    )
    dataframe.index = pd.Index([10, 20], name="source_index")
    return dataframe


def _snapshot_tree(root: Path) -> dict[str, tuple[bool, bytes | None]]:
    return {
        str(path.relative_to(root)): (
            path.is_dir(),
            None if path.is_dir() else path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
    }


def test_save_parquet_atomic_writes_reads_and_preserves_types(
    tmp_path: Path,
) -> None:
    dataframe = _dataframe()
    dataframe_before = dataframe.copy(deep=True)
    output_path = tmp_path / "nested" / "table.parquet"
    temporary_path = output_path.with_suffix(".parquet.tmp")

    save_parquet_atomic(dataframe, output_path)

    assert output_path.parent.is_dir()
    assert output_path.is_file()
    assert not temporary_path.exists()
    stored = pd.read_parquet(output_path)
    expected = dataframe.reset_index(drop=True)
    pd.testing.assert_frame_equal(stored, expected)
    assert stored.dtypes.to_dict() == expected.dtypes.to_dict()
    assert isinstance(stored.index, pd.RangeIndex)
    pd.testing.assert_frame_equal(dataframe, dataframe_before)


def test_save_parquet_atomic_replaces_existing_file(tmp_path: Path) -> None:
    output_path = tmp_path / "table.parquet"
    output_path.write_bytes(b"contenido anterior")
    replacement = pd.DataFrame({"value": [3, 4]})

    save_parquet_atomic(replacement, output_path)

    pd.testing.assert_frame_equal(
        pd.read_parquet(output_path),
        replacement,
    )
    assert not output_path.with_suffix(".parquet.tmp").exists()


def test_save_parquet_atomic_propagates_error_without_final_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = _dataframe()
    dataframe_before = dataframe.copy(deep=True)
    output_path = tmp_path / "nested" / "table.parquet"
    original_error = RuntimeError("fallo original de escritura")

    def fail_to_parquet(
        self: pd.DataFrame,
        path: Path,
        *,
        index: bool,
    ) -> None:
        assert self is dataframe
        assert path == output_path.with_suffix(".parquet.tmp")
        assert index is False
        raise original_error

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_to_parquet)

    with pytest.raises(RuntimeError) as exc_info:
        save_parquet_atomic(dataframe, output_path)

    assert exc_info.value is original_error
    assert output_path.parent.is_dir()
    assert not output_path.exists()
    assert not output_path.with_suffix(".parquet.tmp").exists()
    pd.testing.assert_frame_equal(dataframe, dataframe_before)


def test_failed_write_does_not_replace_existing_final_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = _dataframe()
    output_path = tmp_path / "table.parquet"
    original_content = b"archivo final anterior"
    output_path.write_bytes(original_content)

    def fail_to_parquet(
        self: pd.DataFrame,
        path: Path,
        *,
        index: bool,
    ) -> None:
        raise OSError("sin espacio")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_to_parquet)

    with pytest.raises(OSError, match="sin espacio"):
        save_parquet_atomic(dataframe, output_path)

    assert output_path.read_bytes() == original_content


def test_importing_persistence_has_no_filesystem_side_effects(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.txt"
    existing.write_text("contenido original", encoding="utf-8")
    before = _snapshot_tree(tmp_path)
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "renewables_permitting"
        / "extraction"
        / "persistence.py"
    )

    namespace = runpy.run_path(str(module_path))

    assert namespace["save_parquet_atomic"].__name__ == "save_parquet_atomic"
    assert _snapshot_tree(tmp_path) == before
    assert existing.read_text(encoding="utf-8") == "contenido original"


def test_atomic_replace_error_is_propagated_after_temporary_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = _dataframe()
    output_path = tmp_path / "table.parquet"
    temporary_path = output_path.with_suffix(".parquet.tmp")
    original_error = OSError("fallo al promover el archivo temporal")

    def fake_to_parquet(
        self: pd.DataFrame,
        path: Path,
        *,
        index: bool,
    ) -> None:
        assert self is dataframe
        assert path == temporary_path
        assert index is False
        path.write_bytes(b"parquet temporal completo")

    def fail_replace(self: Path, target: Path) -> None:
        assert self == temporary_path
        assert target == output_path
        raise original_error

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)
    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError) as exc_info:
        save_parquet_atomic(dataframe, output_path)

    assert exc_info.value is original_error
    assert temporary_path.read_bytes() == b"parquet temporal completo"
    assert not output_path.exists()
