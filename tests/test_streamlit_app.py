from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from test_app_data import EXPECTED_DOWNSTREAM_ID, write_gold_dataset


APP_PATH = Path(__file__).parents[1] / "streamlit_app.py"


def _configured_app(monkeypatch, tmp_path: Path) -> AppTest:
    gold_dir = write_gold_dataset(tmp_path / "gold")
    monkeypatch.setenv("RENEWABLES_GOLD_DIR", str(gold_dir))
    monkeypatch.setenv(
        "RENEWABLES_EXPECTED_DOWNSTREAM_ID",
        EXPECTED_DOWNSTREAM_ID,
    )
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
