from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from test_app_data import (
    EXPECTED_DOWNSTREAM_ID,
    synthetic_gold_tables,
    write_gold_dataset,
)


APP_PATH = Path(__file__).parents[1] / "streamlit_app.py"


def _configured_app(
    monkeypatch,
    tmp_path: Path,
    *,
    enable_explorer: str | None = None,
    tables: dict[str, pd.DataFrame] | None = None,
) -> AppTest:
    gold_dir = write_gold_dataset(tmp_path / "gold", tables=tables)
    monkeypatch.setenv("RENEWABLES_GOLD_DIR", str(gold_dir))
    expected_downstream_id = EXPECTED_DOWNSTREAM_ID
    if tables is not None:
        manifest = json.loads(
            (gold_dir / "manifest.json").read_text(encoding="utf-8")
        )
        expected_downstream_id = manifest["downstream_materialization_id"]
    monkeypatch.setenv(
        "RENEWABLES_EXPECTED_DOWNSTREAM_ID",
        expected_downstream_id,
    )
    if enable_explorer is None:
        monkeypatch.delenv("RENEWABLES_ENABLE_DATA_EXPLORER", raising=False)
    else:
        monkeypatch.setenv("RENEWABLES_ENABLE_DATA_EXPLORER", enable_explorer)
    return AppTest.from_file(APP_PATH, default_timeout=10)


def test_app_starts_with_catalog_and_metrics(monkeypatch, tmp_path: Path) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    assert not app.exception
    assert app.title[0].value == "Seguimiento de proyectos energéticos en el BOE"
    assert len(app.dataframe) == 1
    assert [metric.value for metric in app.metric] == ["1", "1", "1"]


def test_app_filters_catalog_without_duplicate_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    app.sidebar.text_input[0].set_value("proyecto inexistente").run()

    assert not app.exception
    assert [metric.value for metric in app.metric] == ["0", "0", "0"]
    assert app.info[0].value == "No hay proyectos que coincidan con los filtros."


def test_app_navigates_to_project_detail_from_query_params(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    assert not app.exception
    assert any(
        "Parque Eólico Alfa" in heading.value
        for heading in [*app.title, *app.header, *app.subheader]
    )
    assert any(
        "Cronología administrativa publicada" == heading.value
        for heading in app.header
    )
    assert len(app.expander) == 1


@pytest.mark.parametrize(
    "boe_id",
    ["BOE-A-2023-10306", "BOE-B-2026-19389"],
)
def test_app_project_detail_renders_canonical_boe_link(
    monkeypatch,
    tmp_path: Path,
    boe_id: str,
) -> None:
    tables = synthetic_gold_tables()
    tables["project_events"].loc[0, "boe_id"] = boe_id
    tables["project_location_sources"].loc[0, "boe_id"] = boe_id
    app = _configured_app(monkeypatch, tmp_path, tables=tables)
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    expected_url = f"https://www.boe.es/diario_boe/txt.php?id={boe_id}"
    assert not app.exception
    assert any(expected_url in element.value for element in app.markdown)


def test_app_renders_methodology_view(monkeypatch, tmp_path: Path) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    app.query_params["view"] = "metodologia"

    app.run()

    assert not app.exception
    assert any(heading.value == "Metodología" for heading in app.header)
    assert any(
        "tfm-core-freeze-2026-08-13" in element.value
        for element in app.markdown
    )
    methodology = "\n".join(element.value for element in app.markdown)
    assert "1 proyectos" in methodology
    assert "1 actuaciones únicas" in methodology
    assert "1 eventos de proyecto" in methodology
    assert "1 asociaciones territoriales" in methodology
    assert "116 proyectos" not in methodology


def test_app_shows_safe_error_for_missing_dataset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "RENEWABLES_GOLD_DIR",
        str(tmp_path / "missing"),
    )
    monkeypatch.setenv(
        "RENEWABLES_EXPECTED_DOWNSTREAM_ID",
        EXPECTED_DOWNSTREAM_ID,
    )

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert app.error[0].value == "Dataset no disponible."
    assert str(tmp_path) not in app.error[0].value


@pytest.mark.parametrize("view", ["unknown", "ficha"])
def test_app_handles_invalid_navigation(
    monkeypatch,
    tmp_path: Path,
    view: str,
) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    app.query_params["view"] = view

    app.run()

    assert not app.exception
    if view == "unknown":
        assert len(app.dataframe) == 1
    else:
        assert app.warning[0].value == "El proyecto solicitado no existe."


def test_data_explorer_is_hidden_and_direct_navigation_is_safe_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    app.query_params["view"] = "datos"

    app.run()

    assert not app.exception
    assert all(button.label != "Auditoría de datos" for button in app.sidebar.button)
    assert all(header.value != "Auditoría de datos Gold" for header in app.header)
    assert len(app.dataframe) == 1
    assert app.query_params["view"] == ["explorar"]


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_data_explorer_accepts_only_explicit_true_values(
    monkeypatch,
    tmp_path: Path,
    value: str,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        enable_explorer=value,
    )
    app.query_params["view"] = "datos"

    app.run()

    assert not app.exception
    assert any(button.label == "Auditoría de datos" for button in app.sidebar.button)
    assert any(header.value == "Auditoría de datos Gold" for header in app.header)


@pytest.mark.parametrize("value", ["", "false", "0", "unexpected"])
def test_data_explorer_rejects_other_configuration_values(
    monkeypatch,
    tmp_path: Path,
    value: str,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        enable_explorer=value,
    )
    app.query_params["view"] = "datos"

    app.run()

    assert not app.exception
    assert all(header.value != "Auditoría de datos Gold" for header in app.header)
    assert app.query_params["view"] == ["explorar"]


def test_data_explorer_shows_content_schema_and_quality_without_write_controls(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        enable_explorer="true",
    )
    app.query_params["view"] = "datos"

    app.run()

    assert not app.exception
    assert app.selectbox[0].label == "Vista de auditoría"
    assert [tab.label for tab in app.tabs] == ["Contenido", "Esquema", "Calidad"]
    assert len(app.dataframe) >= 3
    assert all(button.label != "Descargar" for button in app.button)
    assert not app.download_button
    assert not app.file_uploader


def test_data_explorer_switches_canonical_table_and_applies_filter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        enable_explorer="true",
    )
    app.query_params["view"] = "datos"
    app.run()

    app.selectbox[0].set_value("project_events").run()
    app.multiselect[0].set_value(["project_alpha"]).run()

    assert not app.exception
    assert any("project_events" in caption.value for caption in app.caption)
    assert any(
        list(frame.value["project_id"].astype(str).unique()) == ["project_alpha"]
        for frame in app.dataframe
        if "project_id" in frame.value.columns
        and "administrative_action_id" in frame.value.columns
    )


@pytest.mark.parametrize(
    ("view_name", "expected_column"),
    [
        ("project_summary", "territorial_summary"),
        ("territorial_trace", "boe_url"),
    ],
)
def test_data_explorer_renders_derived_views(
    monkeypatch,
    tmp_path: Path,
    view_name: str,
    expected_column: str,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        enable_explorer="on",
    )
    app.query_params["view"] = "datos"
    app.run()

    app.selectbox[0].set_value(view_name).run()

    assert not app.exception
    assert len(app.tabs) == 0
    assert any(expected_column in frame.value.columns for frame in app.dataframe)
