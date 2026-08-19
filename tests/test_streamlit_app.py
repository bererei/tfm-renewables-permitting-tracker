from __future__ import annotations

import json
from datetime import date
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


def _typed_like(
    rows: list[dict[str, object]],
    template: pd.DataFrame,
) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=template.columns)
    for column, dtype in template.dtypes.items():
        if str(dtype) == "datetime64[ns]":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def _administrative_gold_tables() -> dict[str, pd.DataFrame]:
    tables = synthetic_gold_tables()
    alpha_project = tables["projects"].iloc[0].to_dict()
    beta_project = dict(alpha_project)
    alpha_project.update({
        "project_name": "Parque Eólico Alfa",
        "technology": "eolica",
        "first_publication_date": "2025-01-10",
        "last_publication_date": "2026-01-10",
        "n_publications": 2,
        "n_administrative_actions": 3,
    })
    beta_project.update({
        "project_id": "project_beta",
        "project_name": "Planta Solar Beta",
        "technology": "fotovoltaica",
        "province_codes": "41",
        "provinces": "Sevilla",
        "municipality_codes": "41091",
        "municipalities": "Sevilla",
        "first_publication_date": "2026-01-10",
        "last_publication_date": "2026-01-10",
        "n_publications": 1,
        "n_administrative_actions": 2,
    })
    tables["projects"] = _typed_like(
        [alpha_project, beta_project],
        tables["projects"],
    )

    base_event = tables["project_events"].iloc[0].to_dict()

    def event(
        project_id: str,
        event_id: str,
        action_id: str,
        boe_id: str,
        publication_date: str,
        action_type: str,
        decision: str,
        action_index: int,
    ) -> dict[str, object]:
        row = dict(base_event)
        row.update({
            "project_id": project_id,
            "event_id": event_id,
            "administrative_action_id": action_id,
            "boe_id": boe_id,
            "publication_date": publication_date,
            "event_index": 1,
            "administrative_action_index": action_index,
            "action_type": action_type,
            "decision": decision,
            "evidence": f"Evidencia publicada de {action_id}.",
        })
        return row

    tables["project_events"] = _typed_like(
        [
            event(
                "project_alpha",
                "event_alpha_old",
                "action_alpha_aap_old",
                "BOE-A-2025-10",
                "2025-01-10",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                1,
            ),
            event(
                "project_alpha",
                "event_alpha_current",
                "action_alpha_aap_current",
                "BOE-A-2026-10",
                "2026-01-10",
                "autorizacion_administrativa_previa",
                "autorizado",
                1,
            ),
            event(
                "project_alpha",
                "event_alpha_current",
                "action_alpha_aac",
                "BOE-A-2026-10",
                "2026-01-10",
                "autorizacion_administrativa_construccion",
                "sometido_informacion_publica",
                2,
            ),
            event(
                "project_beta",
                "event_beta",
                "action_beta_aap",
                "BOE-A-2026-20",
                "2026-01-10",
                "autorizacion_administrativa_previa",
                "sometido_informacion_publica",
                1,
            ),
            event(
                "project_beta",
                "event_beta",
                "action_beta_aac",
                "BOE-A-2026-20",
                "2026-01-10",
                "autorizacion_administrativa_construccion",
                "sometido_informacion_publica",
                2,
            ),
        ],
        tables["project_events"],
    )

    alpha_location = tables["project_locations"].iloc[0].to_dict()
    beta_location = dict(alpha_location)
    beta_location.update({
        "project_location_id": "location_beta",
        "project_id": "project_beta",
        "municipality": "Sevilla",
        "municipality_norm": "sevilla",
        "ine_municipality_code": "41091",
        "province": "Sevilla",
        "province_norm": "sevilla",
        "ine_province_code": "41",
        "autonomous_community": "Andalucía",
        "autonomous_community_norm": "andalucia",
        "ine_autonomous_community_code": "01",
        "first_publication_date": "2026-01-10",
        "last_publication_date": "2026-01-10",
    })
    tables["project_locations"] = _typed_like(
        [alpha_location, beta_location],
        tables["project_locations"],
    )

    alpha_source = tables["project_location_sources"].iloc[0].to_dict()
    beta_source = dict(alpha_source)
    alpha_source.update({
        "event_id": "event_alpha_current",
        "boe_id": "BOE-A-2026-10",
        "publication_date": "2026-01-10",
    })
    beta_source.update({
        "project_location_id": "location_beta",
        "location_mention_id": "location_mention_beta",
        "event_id": "event_beta",
        "boe_id": "BOE-A-2026-20",
        "publication_date": "2026-01-10",
    })
    tables["project_location_sources"] = _typed_like(
        [alpha_source, beta_source],
        tables["project_location_sources"],
    )
    return tables


def _sidebar_widget(elements, label: str):
    return next(element for element in elements if element.label == label)


def _catalog_frame(app: AppTest) -> pd.DataFrame:
    return next(
        frame.value
        for frame in app.dataframe
        if "Proyecto" in frame.value.columns
    )


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


def test_administrative_filters_default_to_latest_and_show_matching_actions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()

    interpretation = _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    )
    assert interpretation.value == "latest"
    assert "publicación más reciente" in interpretation.help
    assert any(
        "no constituye por sí sola una determinación jurídica" in caption.value
        for caption in app.sidebar.caption
    )
    _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).set_value(["sometido_informacion_publica"]).run()

    catalog = _catalog_frame(app)
    assert set(catalog["Proyecto"]) == {
        "Parque Eólico Alfa",
        "Planta Solar Beta",
    }
    assert "Trámites coincidentes" in catalog.columns
    assert catalog["Trámites coincidentes"].str.len().gt(0).all()

    _sidebar_widget(app.sidebar.multiselect, "Trámite").set_value([
        "autorizacion_administrativa_previa"
    ]).run()

    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]
    assert not any(
        element.label == "Coincidencia de trámites"
        for element in app.sidebar.segmented_control
    )


def test_historical_mode_and_date_range_use_the_same_action_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    ).set_value("historical").run()
    _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).set_value(["sometido_informacion_publica"]).run()
    _sidebar_widget(app.sidebar.multiselect, "Trámite").set_value([
        "autorizacion_administrativa_previa"
    ]).run()

    assert set(_catalog_frame(app)["Proyecto"]) == {
        "Parque Eólico Alfa",
        "Planta Solar Beta",
    }

    _sidebar_widget(
        app.sidebar.date_input,
        "Fecha de publicación",
    ).set_value((date(2026, 1, 1), date(2026, 1, 10))).run()

    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]


def test_multiple_action_types_offer_any_and_all_semantics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).set_value(["sometido_informacion_publica"]).run()
    _sidebar_widget(app.sidebar.multiselect, "Trámite").set_value([
        "autorizacion_administrativa_previa",
        "autorizacion_administrativa_construccion",
    ]).run()

    action_match = _sidebar_widget(
        app.sidebar.segmented_control,
        "Coincidencia de trámites",
    )
    assert action_match.value == "any"
    assert set(_catalog_frame(app)["Proyecto"]) == {
        "Parque Eólico Alfa",
        "Planta Solar Beta",
    }
    assert _catalog_frame(app)["Trámites coincidentes"].str.contains(
        "Autorización administrativa"
    ).all()

    action_match.set_value("all").run()

    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]


def test_combined_filters_empty_state_and_clear_restore_defaults(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "fotovoltaica"
    ]).run()
    _sidebar_widget(app.sidebar.multiselect, "Comunidad autónoma").set_value([
        "Andalucía"
    ]).run()
    _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).set_value(["sometido_informacion_publica"]).run()
    _sidebar_widget(app.sidebar.multiselect, "Trámite").set_value([
        "autorizacion_administrativa_previa",
        "autorizacion_administrativa_construccion",
    ]).run()
    _sidebar_widget(
        app.sidebar.segmented_control,
        "Coincidencia de trámites",
    ).set_value("all").run()

    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]

    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "eolica"
    ]).run()
    assert app.info[0].value == "No hay proyectos que coincidan con los filtros."

    _sidebar_widget(app.sidebar.button, "Limpiar filtros").click().run()

    assert set(_catalog_frame(app)["Proyecto"]) == {
        "Parque Eólico Alfa",
        "Planta Solar Beta",
    }
    assert "Trámites coincidentes" not in _catalog_frame(app).columns
    assert _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    ).value == "latest"


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
