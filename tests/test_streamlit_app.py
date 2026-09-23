from __future__ import annotations

import ast
import json
import re
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from test_app_data import (
    EXPECTED_DOWNSTREAM_ID,
    synthetic_gold_tables,
    write_gold_dataset,
)
from test_app_geometry import _write_country_context


APP_PATH = Path(__file__).parents[1] / "streamlit_app.py"


def test_production_defaults_select_corrected_gold_v2() -> None:
    module = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    defaults = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in {
            "DEFAULT_GOLD_DIR",
            "DEFAULT_DOWNSTREAM_ID",
        }:
            defaults[target.id] = ast.literal_eval(node.value)

    assert defaults == {
        "DEFAULT_GOLD_DIR": (
            "data/gold/final-w14-corpus-20220101-20260820-v2-"
            "316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86"
        ),
        "DEFAULT_DOWNSTREAM_ID": (
            "316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86"
        ),
    }


def test_versioned_default_gold_runs_without_operator_configuration(
    monkeypatch,
) -> None:
    for variable in (
        "RENEWABLES_GOLD_DIR",
        "RENEWABLES_EXPECTED_DOWNSTREAM_ID",
        "RENEWABLES_ENABLE_DATA_EXPLORER",
        "RENEWABLES_REPORT_EMAIL",
    ):
        monkeypatch.delenv(variable, raising=False)

    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    assert not app.exception
    assert not app.error
    assert [metric.label for metric in app.metric] == [
        "Proyectos",
        "Publicaciones BOE relevantes",
    ]
    assert [metric.value for metric in app.metric] == ["86", "80"]


def _write_app_geometry(
    root: Path,
    locations: pd.DataFrame,
) -> tuple[Path, str]:
    """Write a minimal contractual geometry covering a synthetic Gold fixture."""

    level_columns = {
        "autonomous_community": (
            "ine_autonomous_community_code",
            "autonomous_community",
        ),
        "province": ("ine_province_code", "province"),
        "municipality": ("ine_municipality_code", "municipality"),
    }
    features = []
    counts = {}
    for level, (code_column, name_column) in level_columns.items():
        rows = locations
        if level == "municipality":
            rows = rows[rows["location_level"].eq("municipality")]
        rows = rows[rows[code_column].notna()].drop_duplicates(code_column)
        counts[level] = len(rows)
        for index, row in enumerate(rows.itertuples(index=False), start=1):
            properties = row._asdict()
            code = str(properties[code_column])
            x = float(index)
            features.append({
                "type": "Feature",
                "id": f"{level}:{code}",
                "properties": {
                    "level": level,
                    "code": code,
                    "name": str(properties[name_column]),
                    "autonomous_community_code": str(
                        properties["ine_autonomous_community_code"]
                    ),
                    "province_code": str(properties["ine_province_code"])
                    if level != "autonomous_community"
                    else None,
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[
                        [x, 0.0],
                        [x + 0.2, 0.0],
                        [x + 0.2, 0.2],
                        [x, 0.0],
                    ]]],
                },
            })
    features.extend([
        {
            "type": "Feature",
            "id": "autonomous_community:02",
            "properties": {
                "level": "autonomous_community",
                "code": "02",
                "name": "Aragón",
                "autonomous_community_code": "02",
                "province_code": None,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[8.0, 0.0], [8.2, 0.0], [8.2, 0.2], [8.0, 0.0]]]],
            },
        },
        {
            "type": "Feature",
            "id": "province:22",
            "properties": {
                "level": "province",
                "code": "22",
                "name": "Huesca",
                "autonomous_community_code": "02",
                "province_code": "22",
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[8.0, 0.0], [8.1, 0.0], [8.1, 0.1], [8.0, 0.0]]]],
            },
        },
    ])
    counts["autonomous_community"] += 1
    counts["province"] += 1
    root.mkdir()
    artifact_names = {
        "autonomous_community": "autonomous_communities.geojson",
        "province": "provinces.geojson",
        "municipality": "project_municipalities.geojson",
    }
    artifacts = {}
    for level, filename in artifact_names.items():
        payload = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    feature
                    for feature in features
                    if feature["properties"]["level"] == level
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        (root / filename).write_bytes(payload)
        artifacts[level] = {
            "file": filename,
            "sha256": sha256(payload).hexdigest(),
        }
    manifest = {
        "contract_version": "app-administrative-geometry-v2",
        "artifacts": artifacts,
        "source": {
            "organization": "IGN/CNIG",
            "series": "Límites municipales, provinciales y autonómicos",
            "product": "Límites y Unidades Administrativas Actuales",
            "file": "LINEAS_LIMITE.ZIP",
            "publication_date": "2026-07-28",
            "sha256": "a" * 64,
        },
        "processing": {
            "version": "ign_bdlje_app_geometry_v2",
            "source_crs": {
                "peninsula_balearic_ceuta_melilla": "EPSG:4258",
                "canary_islands": "EPSG:4326",
            },
            "output_crs": "WGS84-compatible GeoJSON",
        },
        "feature_counts": counts,
        "license_attribution": "Obra derivada de BDLJE CC-BY 4.0 ign.es",
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (root / "manifest.json").write_bytes(manifest_payload)
    return root, sha256(manifest_payload).hexdigest()


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


def _basque_gold_tables() -> dict[str, pd.DataFrame]:
    """Move the synthetic solar project to one Basque municipality."""

    tables = _administrative_gold_tables()
    beta = tables["project_locations"]["project_id"].eq("project_beta")
    replacements = {
        "municipality": "Bilbao",
        "municipality_norm": "bilbao",
        "ine_municipality_code": "48020",
        "province": "Bizkaia",
        "province_norm": "bizkaia",
        "ine_province_code": "48",
        "autonomous_community": "País Vasco",
        "autonomous_community_norm": "pais vasco",
        "ine_autonomous_community_code": "16",
    }
    for column, value in replacements.items():
        tables["project_locations"].loc[beta, column] = value
    return tables


def _multi_community_gold_tables() -> dict[str, pd.DataFrame]:
    """Associate one project with two structured communities and provinces."""

    tables = _basque_gold_tables()
    beta_location = tables["project_locations"].loc[
        tables["project_locations"]["project_id"].eq("project_beta")
    ].iloc[0].to_dict()
    beta_location.update({
        "project_location_id": "location_beta_andalucia",
        "municipality": "Sevilla",
        "municipality_norm": "sevilla",
        "ine_municipality_code": "41091",
        "province": "Sevilla",
        "province_norm": "sevilla",
        "ine_province_code": "41",
        "autonomous_community": "Andalucía",
        "autonomous_community_norm": "andalucia",
        "ine_autonomous_community_code": "01",
    })
    tables["project_locations"] = pd.concat(
        [
            tables["project_locations"],
            _typed_like([beta_location], tables["project_locations"]),
        ],
        ignore_index=True,
    )
    beta_source = tables["project_location_sources"].loc[
        tables["project_location_sources"]["boe_id"].eq("BOE-A-2026-20")
    ].iloc[0].to_dict()
    beta_source.update({
        "project_location_id": "location_beta_andalucia",
        "location_mention_id": "location_mention_beta_andalucia",
    })
    tables["project_location_sources"] = pd.concat(
        [
            tables["project_location_sources"],
            _typed_like([beta_source], tables["project_location_sources"]),
        ],
        ignore_index=True,
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


def _folium_components(app: AppTest):
    return [
        element
        for element in app.get("component_instance")
        if element.proto.component_name == "streamlit_folium.st_folium"
    ]


def _folium_args(element) -> dict[str, object]:
    return json.loads(element.proto.json_args)


def _map_project_count(script: str, *, level: str, code: str) -> int:
    """Read one analytical count from the rendered Folium GeoJSON."""

    for raw_properties in re.findall(r'"properties": (\{[^{}]*\})', script):
        properties = json.loads(raw_properties)
        if properties.get("level") == level and properties.get("code") == code:
            return int(properties["project_count"])
    raise AssertionError(f"No se encontró {level}:{code} en el mapa.")


def _folium_click_payload(
    *,
    level: str,
    code: str,
    name: str,
    project_count: int = 1,
) -> dict[str, object]:
    return {
        "last_active_drawing": {
            "type": "Feature",
            "properties": {
                "level": level,
                "code": code,
                "name": name,
                "project_count": project_count,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
        }
    }


def _chart_specs(app: AppTest) -> list[dict[str, object]]:
    return [
        json.loads(element.proto.spec)
        for element in app.get("vega_lite_chart")
    ]


def _chart_selection_params(spec: object) -> list[dict[str, object]]:
    """Collect named Vega selections from unit or composed chart specs."""

    if isinstance(spec, list):
        return [
            selection
            for item in spec
            for selection in _chart_selection_params(item)
        ]
    if not isinstance(spec, dict):
        return []
    selections = [
        item
        for item in spec.get("params", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    return selections + [
        selection
        for value in spec.values()
        for selection in _chart_selection_params(value)
    ]


def _chart_with_selection(
    app: AppTest,
    selection_name: str,
) -> dict[str, object]:
    return next(
        spec
        for spec in _chart_specs(app)
        if selection_name
        in {item["name"] for item in _chart_selection_params(spec)}
    )


def _configured_app(
    monkeypatch,
    tmp_path: Path,
    *,
    enable_explorer: str | None = None,
    tables: dict[str, pd.DataFrame] | None = None,
    report_email: str | None = None,
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
    source_tables = tables or synthetic_gold_tables()
    geometry_dir, geometry_hash = _write_app_geometry(
        tmp_path / "geometry",
        source_tables["project_locations"],
    )
    monkeypatch.setenv("RENEWABLES_GEOMETRY_DIR", str(geometry_dir))
    monkeypatch.setenv(
        "RENEWABLES_EXPECTED_GEOMETRY_SHA256",
        geometry_hash,
    )
    context_dir, context_hash = _write_country_context(
        tmp_path / "country-context"
    )
    monkeypatch.setenv("RENEWABLES_COUNTRY_CONTEXT_DIR", str(context_dir))
    monkeypatch.setenv(
        "RENEWABLES_EXPECTED_COUNTRY_CONTEXT_SHA256",
        context_hash,
    )
    if report_email is None:
        monkeypatch.delenv("RENEWABLES_REPORT_EMAIL", raising=False)
    else:
        monkeypatch.setenv("RENEWABLES_REPORT_EMAIL", report_email)
    if enable_explorer is None:
        monkeypatch.delenv("RENEWABLES_ENABLE_DATA_EXPLORER", raising=False)
    else:
        monkeypatch.setenv("RENEWABLES_ENABLE_DATA_EXPLORER", enable_explorer)
    return AppTest.from_file(APP_PATH, default_timeout=10)


def test_app_starts_with_summary_and_two_primary_metrics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    assert not app.exception
    assert app.title[0].value == "Seguimiento de proyectos energéticos en el BOE"
    assert len(app.dataframe) == 1
    assert [metric.value for metric in app.metric] == ["1", "1"]
    assert [metric.label for metric in app.metric] == [
        "Proyectos",
        "Publicaciones BOE relevantes",
    ]
    assert all(metric.proto.show_border for metric in app.metric)
    assert {
        "Distribución territorial administrativa",
        "Evolución de proyectos",
        "Evolución de publicaciones BOE",
        "Última situación publicada por tipo de actuación",
    } <= {heading.value for heading in app.subheader}
    selectable_charts = [
        spec for spec in _chart_specs(app) if _chart_selection_params(spec)
    ]
    assert len(selectable_charts) == 3
    assert {
        parameter["name"]
        for chart in selectable_charts
        for parameter in _chart_selection_params(chart)
    } == {
        "project_year_selection",
        "publication_year_selection",
        "administrative_action_selection",
        "administrative_selection",
    }
    assert len(_folium_components(app)) == 1
    assert all(
        button.label != "Explorar proyectos" for button in app.sidebar.button
    )
    columns = app.get("column")
    assert [column.proto.weight for column in columns[:4]] == [0.5] * 4
    assert all(column.proto.show_border for column in columns[2:4])


def test_administrative_chart_temporal_control_reuses_and_syncs_sidebar_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    sidebar_mode = _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    )
    chart_mode = _sidebar_widget(
        app.segmented_control,
        "Interpretación temporal del gráfico",
    )

    assert sidebar_mode.value == "latest"
    assert chart_mode.value == "latest"
    assert chart_mode.options == [
        "Última decisión publicada por trámite",
        "Cualquier publicación histórica",
    ]
    assert len([
        spec
        for spec in _chart_specs(app)
        if "administrative_selection"
        in {item["name"] for item in _chart_selection_params(spec)}
    ]) == 1

    sidebar_mode.set_value("historical").run()

    assert _sidebar_widget(
        app.segmented_control,
        "Interpretación temporal del gráfico",
    ).value == "historical"
    assert any(
        heading.value
        == "Situaciones publicadas históricamente por tipo de actuación"
        for heading in app.subheader
    )
    assert len([
        spec
        for spec in _chart_specs(app)
        if "administrative_selection"
        in {item["name"] for item in _chart_selection_params(spec)}
    ]) == 1

    _sidebar_widget(
        app.segmented_control,
        "Interpretación temporal del gráfico",
    ).set_value("latest").run()

    assert _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    ).value == "latest"
    assert any(
        heading.value == "Última situación publicada por tipo de actuación"
        for heading in app.subheader
    )


def test_administrative_sidebar_controls_follow_human_approved_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()
    expected = [
        "Interpretación temporal",
        "Año de publicación",
        "Fecha publicación",
        "Trámite",
        "Situación publicada",
    ]

    rendered = [
        element.label
        for element in app.sidebar
        if getattr(element, "label", None) in expected
    ]

    assert not app.exception
    assert rendered == expected


@pytest.mark.parametrize(
    "level",
    ["autonomous_community", "province", "municipality"],
)
def test_dashboard_map_mounts_interactive_folium_at_every_level(
    monkeypatch,
    tmp_path: Path,
    level: str,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()
    map_level = next(
        element
        for element in app.segmented_control
        if element.label == "Nivel territorial"
    )
    map_level.set_value(level).run()

    components = _folium_components(app)

    assert not app.exception
    assert len(components) == 1
    args = _folium_args(components[0])
    assert args["returned_objects"] == ["last_active_drawing"]
    assert args["width"] is None
    assert "L.geoJson" in str(args["script"])
    assert "fitBounds" in str(args["script"])
    assert '"project_count": 1' in str(args["script"])
    if level != "municipality":
        assert '"project_count": 0' in str(args["script"])
    assert '"name": "Spain"' in str(args["script"])
    assert "cartocdn.com" not in str(args["script"])
    assert "openstreetmap.org" not in str(args["script"])


def test_dashboard_map_level_selector_has_three_approved_options(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    selector = _sidebar_widget(app.segmented_control, "Nivel territorial")

    assert selector.options == [
        "Comunidades y ciudades autónomas",
        "Provincias",
        "Municipios",
    ]
    assert selector.value == "autonomous_community"
    assert _sidebar_widget(app.sidebar.multiselect, "Municipio") is not None


def test_changing_map_level_preserves_other_global_filters(
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
    _sidebar_widget(app.sidebar.multiselect, "Año de publicación").set_value([
        2026
    ]).run()

    _sidebar_widget(app.segmented_control, "Nivel territorial").set_value(
        "province"
    ).run()

    assert _sidebar_widget(app.sidebar.multiselect, "Tecnología").value == [
        "fotovoltaica"
    ]
    assert _sidebar_widget(app.sidebar.multiselect, "Año de publicación").value == [
        2026
    ]


def test_catalogue_has_territories_and_a_project_mandatory_column_selector(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    catalog = _catalog_frame(app)
    selector = next(
        element
        for element in app.multiselect
        if element.label == "Columnas visibles"
    )
    assert list(catalog.columns) == [
        "Proyecto",
        "Tecnología",
        "Comunidad autónoma",
        "Provincia",
        "Municipio(s)",
        "Primera publicación observada",
        "Última publicación observada",
        "N.º BOE",
    ]
    assert "Proyecto" not in selector.options

    selector.set_value(["Provincia"]).run()

    assert list(_catalog_frame(app).columns) == ["Proyecto", "Provincia"]


def test_app_filters_catalog_without_duplicate_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    app.sidebar.text_input[0].set_value("proyecto inexistente").run()

    assert not app.exception
    assert [metric.value for metric in app.metric] == ["0", "0"]
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
    assert not any(
        "determinación jurídica" in caption.value
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
        "Fecha publicación",
    ).set_value((date(2026, 1, 1), date(2026, 1, 10))).run()

    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]


def test_publication_year_filter_composes_with_technology_and_territory(
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
    _sidebar_widget(app.sidebar.multiselect, "Año de publicación").set_value([
        2026
    ]).run()

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
    _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    ).set_value("historical").run()
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
    app.session_state["active_chart_year"] = 2026
    app.session_state["active_administrative_selection"] = (
        "autorizacion_administrativa_previa",
        "sometido_informacion_publica",
    )
    app.session_state["active_map_selection"] = {
        "level": "autonomous_community",
        "code": "01",
        "name": "Andalucía",
    }
    app.session_state["active_table_filter"] = {
        "column": "Tecnología",
        "values": ("Fotovoltaica",),
    }

    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]
    assert _sidebar_widget(
        app.sidebar.button,
        "Limpiar filtros",
    ).proto.type == "primary"

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
    assert _sidebar_widget(
        app.segmented_control,
        "Interpretación temporal del gráfico",
    ).value == "latest"
    state = app.session_state.filtered_state
    assert "active_chart_year" not in state
    assert "active_administrative_selection" not in state
    assert "active_map_selection" not in state
    assert "active_table_filter" not in state
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == []
    assert _sidebar_widget(app.sidebar.multiselect, "Provincia").value == []
    assert _sidebar_widget(app.sidebar.multiselect, "Municipio").value == []


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
        for heading in app.subheader
    )
    assert len(app.expander) == 1
    assert [metric.label for metric in app.metric] == [
        "Publicaciones BOE",
        "Actuaciones publicadas",
        "Primera publicación observada",
        "Última publicación observada",
    ]
    assert not any(
        "Situaciones publicadas más recientes" == heading.value
        for heading in [*app.header, *app.subheader]
    )
    assert len(_folium_components(app)) == 1
    assert _folium_args(_folium_components(app)[0])["returned_objects"] == []
    assert any(
        "Se autoriza el parque eólico Alfa" in element.value
        for element in app.markdown
    )
    assert not any(
        "determinación jurídica" in element.value
        for element in [*app.caption, *app.markdown]
    )


def test_project_timeline_renders_newest_publication_first(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    )
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    assert not app.exception
    timeline_headers = [
        element.value
        for element in app.markdown
        if "BOE-A-2026-10" in element.value
        or "BOE-A-2025-10" in element.value
    ]
    assert timeline_headers == [
        "#### 10/01/2026  \n"
        "[BOE-A-2026-10](https://www.boe.es/diario_boe/txt.php?id="
        "BOE-A-2026-10)",
        "#### 10/01/2025  \n"
        "[BOE-A-2025-10](https://www.boe.es/diario_boe/txt.php?id="
        "BOE-A-2025-10)",
    ]


def test_project_detail_reporting_mailto_is_configured_and_contextual(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        report_email="revision@example.org",
    )
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    assert not app.exception
    sidebar_children = list(app.sidebar)
    methodology_position = next(
        index
        for index, element in enumerate(sidebar_children)
        if element.type == "button" and element.label == "Metodología"
    )
    report_position = next(
        index
        for index, element in enumerate(sidebar_children)
        if element.type == "link_button"
        and element.label == "Reportar posible error"
    )
    assert report_position == methodology_position + 1
    assert not app.main.get("link_button")
    assert not any(
        "no está configurado" in message.value for message in app.info
    )
    assert any(
        "abre su cliente de correo" in caption.value for caption in app.caption
    )
    report = app.sidebar.get("link_button")[0].proto
    assert report.url.startswith("mailto:revision@example.org?")
    assert report.type == "secondary"
    body = parse_qs(urlsplit(report.url).query)["body"][0]
    assert "Vista: Ficha de proyecto" in body
    assert "Proyecto: Parque Eólico Alfa" in body
    assert "ID de proyecto: project_alpha" in body
    assert "BOE: BOE-A-2024-100" in body
    assert "https://www.boe.es/diario_boe/txt.php" in body
    assert "/home/" not in body
    assert "downstream" not in body


def test_summary_reporting_includes_active_global_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_basque_gold_tables(),
        report_email="revision@example.org",
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "fotovoltaica"
    ]).run()
    _sidebar_widget(app.sidebar.multiselect, "Comunidad autónoma").set_value([
        "País Vasco"
    ]).run()

    report = app.sidebar.get("link_button")[0].proto
    query = parse_qs(urlsplit(report.url).query)

    assert not app.main.get("link_button")
    assert query["subject"] == ["Posible error en datos BOE — Resumen"]
    assert "Vista: Resumen" in query["body"][0]
    assert "Tecnología: Fotovoltaica" in query["body"][0]
    assert "Comunidad autónoma: País Vasco" in query["body"][0]


def test_project_detail_groups_multi_action_publications_under_one_boe_header(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    )
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    boe_headers = [
        element.value
        for element in app.markdown
        if "BOE-A-2026-10" in element.value
    ]
    assert not app.exception
    assert len(boe_headers) == 1
    assert len(app.expander) == 3


def test_project_detail_without_territory_uses_explicit_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tables = synthetic_gold_tables()
    tables["project_locations"] = tables["project_locations"].iloc[0:0].copy()
    tables["project_location_sources"] = tables[
        "project_location_sources"
    ].iloc[0:0].copy()
    app = _configured_app(monkeypatch, tmp_path, tables=tables)
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    assert not app.exception
    assert not _folium_components(app)
    assert any(
        message.value == (
            "No consta un ámbito territorial resoluble en las publicaciones "
            "analizadas."
        )
        for message in app.info
    )


def test_active_chart_year_is_visible_and_can_be_cleared(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    app.session_state["active_chart_year"] = 2025
    app.session_state["filter_years"] = [2025]
    app.session_state["filter_dates"] = (
        date(2025, 1, 1),
        date(2025, 12, 31),
    )

    app.run()

    assert _sidebar_widget(
        app.sidebar.multiselect, "Año de publicación"
    ).value == [2025]
    assert _sidebar_widget(
        app.sidebar.date_input, "Fecha publicación"
    ).value == (date(2025, 1, 1), date(2025, 12, 31))
    assert any(
        "Año seleccionado en el gráfico: **2025**" in caption.value
        for caption in app.sidebar.caption
    )

    _sidebar_widget(
        app.sidebar.button, "Quitar año seleccionado"
    ).click().run()

    assert _sidebar_widget(
        app.sidebar.multiselect, "Año de publicación"
    ).value == []
    assert "active_chart_year" not in app.session_state.filtered_state


def test_project_detail_reporting_has_safe_unconfigured_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    assert not app.exception
    sidebar_children = list(app.sidebar)
    methodology_position = next(
        index
        for index, element in enumerate(sidebar_children)
        if element.type == "button" and element.label == "Metodología"
    )
    report_position = next(
        index
        for index, element in enumerate(sidebar_children)
        if element.type == "button"
        and element.label == "Reportar posible error"
    )
    report = _sidebar_widget(
        app.sidebar.button,
        "Reportar posible error",
    )
    assert report_position == methodology_position + 1
    assert report.disabled
    assert not app.sidebar.get("link_button")
    assert not any(
        element.label == "Reportar posible error"
        for element in app.main.get("button")
    )
    assert any(
        "Canal de reporte no configurado" in message.value
        for message in app.sidebar.caption
    )


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
    app = _configured_app(
        monkeypatch,
        tmp_path,
        report_email="revision@example.org",
    )
    app.query_params["view"] = "metodologia"

    app.run()

    assert not app.exception
    assert not app.main.get("link_button")
    assert len(app.sidebar.get("link_button")) == 1
    assert any(heading.value == "Metodología" for heading in app.header)
    assert any(
        "tfm-core-freeze-2026-08-13" in element.value
        for element in app.markdown
    )
    methodology = "\n".join(element.value for element in app.markdown)
    assert "proyectos canónicos: 1" in methodology
    assert "documentos analizados: 104" in methodology
    assert "Tier 1" in methodology
    assert "Tier 3 queda excluido" in methodology
    assert "116 proyectos" not in methodology
    visible_text = "\n".join(
        element.value
        for element in [*app.markdown, *app.caption]
    )
    assert "**BOE** — Boletín Oficial del Estado" in visible_text
    assert "**CNIG** — Centro Nacional de Información Geográfica" in visible_text
    assert "**FV** — Fotovoltaica" in visible_text
    assert "**HSF** — Huerta Solar Fotovoltaica" in visible_text
    assert "**IGN** — Instituto Geográfico Nacional" in visible_text
    assert "**INE** — Instituto Nacional de Estadística" in visible_text
    main_visible_text = "\n".join(
        str(getattr(element, "value", "")) for element in app.main
    )
    assert "Comunicación de posibles errores" not in main_visible_text
    assert "mailto:" not in main_visible_text
    assert "persiste mensajes" not in main_visible_text
    assert (
        "Interpretación de las situaciones administrativas. La aplicación "
        "muestra actuaciones y decisiones publicadas en el BOE dentro del "
        "periodo analizado. Estas publicaciones describen la evolución "
        "administrativa observada, pero no deben interpretarse por sí solas "
        "como una certificación del estado jurídico actual y definitivo del "
        "proyecto."
    ) in visible_text


def test_summary_omits_methodology_glossary_and_legal_caveat(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()

    visible_text = "\n".join(
        element.value
        for element in [*app.markdown, *app.caption]
    )
    assert "**HSF** — Huerta Solar Fotovoltaica" not in visible_text
    assert "estado jurídico actual y definitivo" not in visible_text
    assert "determinación jurídica" not in visible_text


def test_admin_chart_declares_action_and_decision_cross_filter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()

    spec = _chart_with_selection(app, "administrative_selection")
    params = {
        item["name"]: item for item in _chart_selection_params(spec)
    }
    assert params["administrative_action_selection"]["select"]["fields"] == [
        "action_type"
    ]
    assert params["administrative_selection"]["select"]["fields"] == [
        "action_type",
        "decision",
    ]
    action_view, segment_view = spec["hconcat"]
    assert action_view["title"]["text"] == "Todo"
    assert (
        action_view["encoding"]["opacity"]["condition"]["param"]
        == "administrative_action_selection"
    )
    assert segment_view["encoding"]["opacity"]["condition"]["param"] == (
        "administrative_selection"
    )


@pytest.mark.parametrize(
    ("chart_key", "selection_name"),
    [
        ("project_year_chart_0", "project_year_selection"),
        ("publication_year_chart_0", "publication_year_selection"),
    ],
)
def test_temporal_chart_click_filters_the_whole_summary(
    monkeypatch,
    tmp_path: Path,
    chart_key: str,
    selection_name: str,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "eolica"
    ]).run()
    app.session_state[chart_key] = {
        "selection": {selection_name: [{"publication_year": 2026}]}
    }

    app.run()

    assert not app.exception
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Parque Eólico Alfa"]
    assert [metric.value for metric in app.metric] == ["1", "1"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Año de publicación",
    ).value == [2026]


@pytest.mark.parametrize("temporal_mode", ["latest", "historical"])
def test_administrative_chart_click_filters_action_and_decision(
    monkeypatch,
    tmp_path: Path,
    temporal_mode: str,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    if temporal_mode == "historical":
        _sidebar_widget(
            app.segmented_control,
            "Interpretación temporal del gráfico",
        ).set_value("historical").run()
    _sidebar_widget(app.sidebar.multiselect, "Año de publicación").set_value([
        2026
    ]).run()
    epoch = int(
        app.session_state.filtered_state.get("chart_selection_epoch", 0)
    )
    app.session_state[f"administrative_chart_{epoch}"] = {
        "selection": {
            "administrative_selection": [{
                "action_type": "autorizacion_administrativa_previa",
                "decision": "autorizado",
            }]
        }
    }

    app.run()

    assert not app.exception
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Parque Eólico Alfa"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Trámite",
    ).value == ["autorizacion_administrativa_previa"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).value == ["autorizado"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Año de publicación",
    ).value == [2026]
    assert _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    ).value == temporal_mode
    assert any(
        "Autorización administrativa previa · Autorizado" in caption.value
        for caption in app.sidebar.caption
    )


@pytest.mark.parametrize("temporal_mode", ["latest", "historical"])
def test_administrative_chart_full_action_click_then_segment_switch(
    monkeypatch,
    tmp_path: Path,
    temporal_mode: str,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    if temporal_mode == "historical":
        _sidebar_widget(
            app.segmented_control,
            "Interpretación temporal del gráfico",
        ).set_value("historical").run()
    epoch = int(
        app.session_state.filtered_state.get("chart_selection_epoch", 0)
    )
    app.session_state[f"administrative_chart_{epoch}"] = {
        "selection": {
            "administrative_action_selection": [{
                "action_type": "autorizacion_administrativa_previa",
            }]
        }
    }

    app.run()

    assert not app.exception
    assert set(_catalog_frame(app)["Proyecto"]) == {
        "Parque Eólico Alfa",
        "Planta Solar Beta",
    }
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Trámite",
    ).value == ["autorizacion_administrativa_previa"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).value == []
    assert any(
        "Autorización administrativa previa · Todas las situaciones"
        in caption.value
        for caption in app.sidebar.caption
    )

    epoch = int(app.session_state.filtered_state["chart_selection_epoch"])
    app.session_state[f"administrative_chart_{epoch}"] = {
        "selection": {
            "administrative_selection": [{
                "action_type": "autorizacion_administrativa_previa",
                "decision": "autorizado",
            }]
        }
    }

    app.run()

    assert not app.exception
    assert _catalog_frame(app)["Proyecto"].tolist() == [
        "Parque Eólico Alfa"
    ]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Trámite",
    ).value == ["autorizacion_administrativa_previa"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Situación publicada",
    ).value == ["autorizado"]
    assert _sidebar_widget(
        app.sidebar.selectbox,
        "Interpretación temporal",
    ).value == temporal_mode


def test_map_click_filters_territory_and_composes_with_existing_filters(
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
    app.session_state["administrative_chart_0"] = {
        "selection": {
            "administrative_selection": [{
                "action_type": "autorizacion_administrativa_previa",
                "decision": "sometido_informacion_publica",
            }]
        }
    }
    app.run()
    app.session_state["map_chart_1"] = _folium_click_payload(
        level="autonomous_community",
        code="01",
        name="Andalucía",
    )

    app.run()

    assert not app.exception
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Tecnología",
    ).value == ["fotovoltaica"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["Andalucía"]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Trámite",
    ).value == ["autorizacion_administrativa_previa"]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]
    assert any(
        "Territorio seleccionado en el mapa: **Andalucía**" in item.value
        for item in app.sidebar.caption
    )


@pytest.mark.parametrize(
    ("level", "code", "name", "filter_label"),
    [
        ("autonomous_community", "12", "Galicia", "Comunidad autónoma"),
        ("province", "15", "A Coruña", "Provincia"),
        ("municipality", "15030", "A Coruña", "Municipio"),
    ],
)
def test_map_click_applies_equivalent_hierarchy_at_every_level(
    monkeypatch,
    tmp_path: Path,
    level: str,
    code: str,
    name: str,
    filter_label: str,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()
    _sidebar_widget(app.segmented_control, "Nivel territorial").set_value(
        level
    ).run()
    app.session_state["map_chart_0"] = _folium_click_payload(
        level=level,
        code=code,
        name=name,
    )

    app.run()

    assert not app.exception
    assert _sidebar_widget(
        app.sidebar.multiselect,
        filter_label,
    ).value == [name]
    assert [metric.value for metric in app.metric] == ["1", "1"]
    if level == "municipality":
        assert _sidebar_widget(
            app.sidebar.multiselect,
            "Provincia",
        ).value == ["A Coruña"]
        assert _sidebar_widget(
            app.sidebar.multiselect,
            "Comunidad autónoma",
        ).value == ["Galicia"]


def test_province_map_selection_composes_with_year_filter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.segmented_control, "Nivel territorial").set_value(
        "province"
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Año de publicación").set_value([
        2026
    ]).run()
    epoch = app.session_state.filtered_state.get("chart_selection_epoch", 0)
    app.session_state[f"map_chart_{epoch}"] = _folium_click_payload(
        level="province",
        code="15",
        name="A Coruña",
    )

    app.run()

    assert not app.exception
    assert _sidebar_widget(app.sidebar.multiselect, "Provincia").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Año de publicación",
    ).value == [2026]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Parque Eólico Alfa"]


def test_zero_count_province_click_is_safe_and_composes_with_technology(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.segmented_control, "Nivel territorial").set_value(
        "province"
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "fotovoltaica"
    ]).run()
    epoch = app.session_state.filtered_state.get("chart_selection_epoch", 0)
    app.session_state[f"map_chart_{epoch}"] = _folium_click_payload(
        level="province",
        code="15",
        name="A Coruña",
        project_count=0,
    )

    app.run()

    assert not app.exception
    assert _sidebar_widget(app.sidebar.multiselect, "Provincia").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(app.sidebar.multiselect, "Tecnología").value == [
        "fotovoltaica"
    ]
    assert any(
        item.value == "No hay proyectos que coincidan con los filtros."
        for item in app.info
    )
    assert len(_folium_components(app)) == 1


def test_municipality_map_retains_corpus_universe_with_zero_filtered_count(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.segmented_control, "Nivel territorial").set_value(
        "municipality"
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "fotovoltaica"
    ]).run()

    script = str(_folium_args(_folium_components(app)[0])["script"])

    assert not app.exception
    assert '"code": "15030"' in script
    assert '"code": "41091"' in script
    assert script.count('"project_count": 0') >= 1
    assert script.count('"project_count": 1') >= 1
    assert "cartocdn.com" not in script


def test_municipality_map_composes_with_year_technology_and_action_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.segmented_control, "Nivel territorial").set_value(
        "municipality"
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Tecnología").set_value([
        "eolica"
    ]).run()
    _sidebar_widget(app.sidebar.multiselect, "Año de publicación").set_value([
        2026
    ]).run()
    _sidebar_widget(app.sidebar.multiselect, "Trámite").set_value([
        "autorizacion_administrativa_previa"
    ]).run()
    epoch = app.session_state.filtered_state.get("chart_selection_epoch", 0)
    app.session_state[f"map_chart_{epoch}"] = _folium_click_payload(
        level="municipality",
        code="15030",
        name="A Coruña",
    )

    app.run()

    assert not app.exception
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Parque Eólico Alfa"]
    assert _sidebar_widget(app.sidebar.multiselect, "Municipio").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(app.sidebar.multiselect, "Provincia").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["Galicia"]
    assert [metric.value for metric in app.metric] == ["1", "1"]


def test_map_rejects_unknown_and_repeated_folium_selection_without_loop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()
    app.session_state["map_chart_0"] = _folium_click_payload(
        level="autonomous_community",
        code="99",
        name="Desconocida",
    )

    app.run()

    assert not app.exception
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == []
    assert app.session_state.filtered_state.get("chart_selection_epoch", 0) == 0

    app.session_state["active_map_selection"] = {
        "level": "autonomous_community",
        "code": "01",
        "name": "Andalucía",
    }
    app.session_state["map_chart_0"] = _folium_click_payload(
        level="autonomous_community",
        code="01",
        name="Andalucía",
    )
    app.run()

    assert not app.exception
    assert app.session_state.filtered_state.get("chart_selection_epoch", 0) == 0


def test_table_technology_cell_filters_the_whole_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[1, "Tecnología"]],
        }
    }

    app.run()

    assert not app.exception
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Tecnología",
    ).value == ["fotovoltaica"]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]
    assert [metric.value for metric in app.metric] == ["1", "1"]
    assert any(
        "Selección desde la tabla: **Tecnología · Fotovoltaica**" in item.value
        for item in app.sidebar.caption
    )


def test_table_basque_community_cell_filters_every_summary_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_basque_gold_tables(),
    ).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[1, "Comunidad autónoma"]],
        }
    }

    app.run()

    assert not app.exception
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["País Vasco"]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]
    assert [metric.value for metric in app.metric] == ["1", "1"]
    assert len(_chart_specs(app)) == 3
    map_script = str(_folium_args(_folium_components(app)[0])["script"])
    assert '"code": "16"' in map_script
    assert '"project_count": 1' in map_script


def test_basque_filter_limits_map_data_but_keeps_other_boundary_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_multi_community_gold_tables(),
    ).run()

    _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).set_value(["País Vasco"]).run()

    script = str(_folium_args(_folium_components(app)[0])["script"])
    assert not app.exception
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]
    assert _map_project_count(
        script,
        level="autonomous_community",
        code="16",
    ) == 1
    assert _map_project_count(
        script,
        level="autonomous_community",
        code="01",
    ) == 0
    assert '"code": "01"' in script


def test_table_multi_community_cell_uses_structured_or_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_multi_community_gold_tables(),
    ).run()
    assert _catalog_frame(app).loc[1, "Comunidad autónoma"] == (
        "Andalucía, País Vasco"
    )
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[1, "Comunidad autónoma"]],
        }
    }

    app.run()

    assert not app.exception
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["Andalucía", "País Vasco"]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]


def test_table_province_cell_synchronizes_parent_community(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[0, "Provincia"]],
        }
    }

    app.run()

    assert not app.exception
    assert _sidebar_widget(app.sidebar.multiselect, "Provincia").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["Galicia"]


def test_table_municipality_cell_synchronizes_full_hierarchy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[0, "Municipio(s)"]],
        }
    }

    app.run()

    assert not app.exception
    assert _sidebar_widget(app.sidebar.multiselect, "Municipio").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(app.sidebar.multiselect, "Provincia").value == [
        "A Coruña"
    ]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["Galicia"]


def test_table_cell_filter_takes_precedence_over_simultaneous_row_selection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [1],
            "columns": [],
            "cells": [[0, "Tecnología"]],
        }
    }

    app.run()

    assert not app.exception
    assert app.query_params.get("view", ["resumen"]) == ["resumen"]
    assert _sidebar_widget(app.sidebar.multiselect, "Tecnología").value == [
        "eolica"
    ]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Parque Eólico Alfa"]


def test_table_project_cell_opens_detail_directly(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[0, "Proyecto"]],
        }
    }

    app.run()

    assert not app.exception
    assert app.query_params["view"] == ["ficha"]
    assert app.query_params["project_id"] == ["project_alpha"]


def test_table_year_and_map_share_one_effective_filter_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    ).run()
    _sidebar_widget(app.sidebar.multiselect, "Año de publicación").set_value([
        2026
    ]).run()
    epoch = app.session_state.filtered_state.get("chart_selection_epoch", 0)
    app.session_state[f"map_chart_{epoch}"] = _folium_click_payload(
        level="autonomous_community",
        code="01",
        name="Andalucía",
    )
    app.run()
    epoch = app.session_state.filtered_state["chart_selection_epoch"]
    app.session_state[f"summary_catalog_{epoch}"] = {
        "selection": {
            "rows": [],
            "columns": [],
            "cells": [[0, "Tecnología"]],
        }
    }

    app.run()

    assert not app.exception
    assert _sidebar_widget(app.sidebar.multiselect, "Año de publicación").value == [
        2026
    ]
    assert _sidebar_widget(
        app.sidebar.multiselect,
        "Comunidad autónoma",
    ).value == ["Andalucía"]
    assert _sidebar_widget(app.sidebar.multiselect, "Tecnología").value == [
        "fotovoltaica"
    ]
    assert _catalog_frame(app)["Proyecto"].tolist() == ["Planta Solar Beta"]


def test_project_detail_loads_only_its_own_municipality_geometry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(
        monkeypatch,
        tmp_path,
        tables=_administrative_gold_tables(),
    )
    app.query_params["view"] = "ficha"
    app.query_params["project_id"] = "project_alpha"

    app.run()

    assert not app.exception
    args = _folium_args(_folium_components(app)[0])
    script = str(args["script"])
    assert '"code": "15030"' in script
    assert '"code": "41091"' not in script
    assert '"name": "Spain"' in script
    assert "cartocdn.com" not in script


def test_summary_catalogue_row_selection_opens_project_detail(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path).run()
    app.session_state["summary_catalog_0"] = {
        "selection": {"rows": [0], "columns": [], "cells": []}
    }

    app.run()

    assert not app.exception
    assert app.query_params["view"] == ["ficha"]
    assert app.query_params["project_id"] == ["project_alpha"]
    assert any(
        "Parque Eólico Alfa" in heading.value
        for heading in [*app.header, *app.title]
    )


def test_legacy_explore_route_returns_to_summary_catalogue(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _configured_app(monkeypatch, tmp_path)
    app.query_params["view"] = "explorar"

    app.run()

    assert not app.exception
    assert app.query_params["view"] == ["resumen"]
    assert len(app.dataframe) == 1
    assert "Proyecto" in _catalog_frame(app).columns


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
    assert app.query_params["view"] == ["resumen"]


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
    assert app.query_params["view"] == ["resumen"]


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
