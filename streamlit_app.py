"""Local read-only Streamlit application over the validated Gold snapshot."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from renewables_permitting.app_audit import (
    AuditDataError,
    build_project_summary,
    build_schema_summary,
    build_territorial_trace,
    filter_audit_project_events,
    filter_audit_project_location_sources,
    filter_audit_project_locations,
    filter_audit_projects,
    filter_territorial_trace,
    get_audit_table,
    observed_filter_values,
    summarize_table_quality,
)
from renewables_permitting.app_data import (
    GOLD_TABLE_SPECS,
    GoldDataset,
    GoldDatasetError,
    GoldIntegrityError,
    GoldManifestError,
    GoldSchemaError,
    GoldVersionError,
    load_gold_dataset,
)
from renewables_permitting.app_geometry import (
    BDLJE_ATTRIBUTION,
    NATURAL_EARTH_ATTRIBUTION,
    CountryContextReference,
    GeometryReference,
    GeometryReferenceError,
    attach_project_counts,
    build_folium_choropleth,
    build_folium_project_map,
    load_country_context_reference,
    load_geometry_reference,
    parse_folium_territory_selection,
    select_geometry_features,
)
from renewables_permitting.app_queries import (
    ACTION_MATCH_ALL,
    ACTION_MATCH_ANY,
    HISTORICAL_TEMPORAL_INTERPRETATION,
    LATEST_TEMPORAL_INTERPRETATION,
    ProjectNotFoundError,
    build_administrative_situation_counts,
    build_boe_url,
    build_catalog_interaction_context,
    build_chart_year_filter,
    build_dashboard_selection,
    build_project_catalog,
    build_project_publication_summary,
    build_publication_counts,
    build_territory_project_counts,
    build_yearly_project_counts,
    extract_chart_selected_values,
    extract_chart_selected_year,
    format_project_display_name,
    get_filter_options,
    get_project_detail,
    get_project_location_sources,
    get_project_locations,
    get_project_timeline,
    group_project_timeline_by_publication,
    label_action_type,
    label_decision,
    label_technology,
    summarize_dashboard_selection,
)
from renewables_permitting.app_reporting import (
    build_error_report_mailto,
    resolve_report_destination,
)
from renewables_permitting.extraction.paths import find_project_root


LOGGER = logging.getLogger(__name__)
DEFAULT_GOLD_DIR = (
    "runs/final-w14-corpus-20220101-20260820-v1/downstream/gold"
)
DEFAULT_DOWNSTREAM_ID = (
    "e3664ebb4efa0876262aed522d8c68e670c13c9ddee5f1fc0c8b76b74481b6e3"
)
DEFAULT_GEOMETRY_DIR = "app_assets/geometry/ign_bdlje_2026-07-28"
DEFAULT_GEOMETRY_SHA256 = (
    "0b93ffb56c9553d7532c891094f4b77e06d6f70423eaf8c85df677ef231f722e"
)
DEFAULT_COUNTRY_CONTEXT_DIR = "app_assets/geometry/natural_earth"
DEFAULT_COUNTRY_CONTEXT_SHA256 = (
    "59b20957215f0ced4971f101b628f5dc5f6f6ce8a3211c9c5ba2290947e279d5"
)
CORE_FREEZE_TAG = "tfm-core-freeze-2026-08-13"
TERRITORIAL_NOTE = (
    "Incluye los territorios asociados en las publicaciones a la planta de "
    "generación o a otros componentes del proyecto, como sistemas de "
    "almacenamiento o infraestructuras de evacuación. Las publicaciones no "
    "siempre permiten determinar a qué componente concreto corresponde cada "
    "territorio."
)
_FILTER_KEYS = (
    "filter_text",
    "filter_technologies",
    "filter_communities",
    "filter_provinces",
    "filter_municipalities",
    "filter_years",
    "filter_dates",
    "filter_actions",
    "filter_decisions",
    "filter_temporal_interpretation",
    "filter_action_match",
)
_EXPLORER_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_AUDIT_VIEW_LABELS = {
    "projects": "Proyectos",
    "project_events": "Eventos de proyecto",
    "project_locations": "Territorios de proyectos",
    "project_location_sources": "Fuentes territoriales",
    "project_summary": "Resumen por proyecto",
    "territorial_trace": "Trazabilidad territorial",
}
_TEMPORAL_INTERPRETATION_LABELS = {
    LATEST_TEMPORAL_INTERPRETATION: "Última decisión publicada por trámite",
    HISTORICAL_TEMPORAL_INTERPRETATION: "Cualquier publicación histórica",
}
_ACTION_MATCH_LABELS = {
    ACTION_MATCH_ANY: "Al menos uno",
    ACTION_MATCH_ALL: "Todos",
}
_MAP_LEVEL_LABELS = {
    "autonomous_community": "Comunidades y ciudades autónomas",
    "province": "Provincias",
    "municipality": "Municipios",
}
_GENERAL_MAP_LEVELS = (
    "autonomous_community",
    "province",
    "municipality",
)
_ACTIVE_CHART_YEAR_KEY = "active_chart_year"
_ACTIVE_ADMIN_SELECTION_KEY = "active_administrative_selection"
_ACTIVE_MAP_SELECTION_KEY = "active_map_selection"
_ACTIVE_TABLE_FILTER_KEY = "active_table_filter"
_CHART_EPOCH_KEY = "chart_selection_epoch"
_PROJECT_YEAR_SELECTION = "project_year_selection"
_PUBLICATION_YEAR_SELECTION = "publication_year_selection"
_ADMINISTRATIVE_SELECTION = "administrative_selection"
_ADMINISTRATIVE_ACTION_SELECTION = "administrative_action_selection"
_ADMINISTRATIVE_TEMPORAL_CONTROL_KEY = "administrative_temporal_control"
_DASHBOARD_EQUAL_COLUMN_WEIGHTS = (1, 1)
_TABLE_FILTERABLE_COLUMNS = (
    "Tecnología",
    "Comunidad autónoma",
    "Provincia",
    "Municipio(s)",
)
_CATALOG_DEFAULT_COLUMNS = (
    "Tecnología",
    "Comunidad autónoma",
    "Provincia",
    "Municipio(s)",
    "Primera publicación observada",
    "Última publicación observada",
    "N.º BOE",
)
_CATALOG_OPTIONAL_COLUMNS = (
    *_CATALOG_DEFAULT_COLUMNS,
    "N.º actuaciones",
    "Territorio resumido",
    "Trámites coincidentes",
)


# Streamlit conserva en caché el dataset ya validado para no releer los Parquet
# en cada interacción. La ruta Gold y el downstream ID identifican el snapshot;
# si cambia cualquiera de los dos, se carga y valida una versión nueva.
@st.cache_data(show_spinner="Verificando el dataset Gold…")
def _load_cached(gold_dir: str, expected_downstream_id: str) -> GoldDataset:
    """Cache a verified dataset using only serializable configuration values."""

    return load_gold_dataset(
        Path(gold_dir),
        expected_downstream_id=expected_downstream_id,
    )


def _configured_dataset() -> GoldDataset:
    """Resolve operator-only environment configuration and load Gold safely."""

    # Estas variables de entorno son configuración del operador, no valores de
    # widgets. Determinan qué directorio Gold y qué downstream ID debe cargar y
    # verificar la aplicación.
    raw_dir = os.environ.get("RENEWABLES_GOLD_DIR", DEFAULT_GOLD_DIR)
    expected_id = os.environ.get(
        "RENEWABLES_EXPECTED_DOWNSTREAM_ID",
        DEFAULT_DOWNSTREAM_ID,
    )
    configured = Path(raw_dir)
    if not configured.is_absolute():
        configured = find_project_root(Path(__file__).resolve().parent) / configured
    return _load_cached(str(configured), expected_id)


@st.cache_resource(show_spinner="Verificando la cartografía administrativa…")
def _load_geometry_cached(
    geometry_dir: str,
    expected_manifest_sha256: str,
) -> GeometryReference:
    """Cache immutable, integrity-checked administrative geometry."""

    return load_geometry_reference(
        Path(geometry_dir),
        expected_manifest_sha256=expected_manifest_sha256,
    )


def _configured_geometry() -> GeometryReference:
    """Resolve and validate the local official administrative geometry."""

    raw_dir = os.environ.get("RENEWABLES_GEOMETRY_DIR", DEFAULT_GEOMETRY_DIR)
    expected_hash = os.environ.get(
        "RENEWABLES_EXPECTED_GEOMETRY_SHA256",
        DEFAULT_GEOMETRY_SHA256,
    )
    configured = Path(raw_dir)
    if not configured.is_absolute():
        configured = find_project_root(Path(__file__).resolve().parent) / configured
    return _load_geometry_cached(str(configured), expected_hash)


@st.cache_resource(show_spinner="Verificando el contexto geográfico local…")
def _load_country_context_cached(
    context_dir: str,
    expected_manifest_sha256: str,
) -> CountryContextReference:
    """Cache immutable, integrity-checked Natural Earth context."""

    return load_country_context_reference(
        Path(context_dir),
        expected_manifest_sha256=expected_manifest_sha256,
    )


def _configured_country_context() -> CountryContextReference:
    """Resolve and validate the local, tile-free country context."""

    raw_dir = os.environ.get(
        "RENEWABLES_COUNTRY_CONTEXT_DIR",
        DEFAULT_COUNTRY_CONTEXT_DIR,
    )
    expected_hash = os.environ.get(
        "RENEWABLES_EXPECTED_COUNTRY_CONTEXT_SHA256",
        DEFAULT_COUNTRY_CONTEXT_SHA256,
    )
    configured = Path(raw_dir)
    if not configured.is_absolute():
        configured = find_project_root(Path(__file__).resolve().parent) / configured
    return _load_country_context_cached(str(configured), expected_hash)


def _report_destination() -> str | None:
    """Read the optional public report mailbox from operator configuration."""

    environment_value = os.environ.get("RENEWABLES_REPORT_EMAIL")
    secret_value = None
    if environment_value is None:
        try:
            secret_value = st.secrets.get("report_email")
        except Exception:
            # Una instalación local sin secrets es una configuración admitida;
            # el canal muestra un fallback y la aplicación sigue siendo read-only.
            secret_value = None
    return resolve_report_destination(environment_value, secret_value)


def _data_explorer_enabled() -> bool:
    """Return whether the operator explicitly enabled the local audit view."""

    # La vista contiene detalle técnico útil para auditoría y por eso no se
    # publica por defecto. Solo una variable de entorno del operador puede
    # habilitarla; no existe un widget que cambie esta decisión desde la UI.
    value = os.environ.get("RENEWABLES_ENABLE_DATA_EXPLORER", "")
    return value.strip().casefold() in _EXPLORER_TRUE_VALUES


def _load_or_stop() -> GoldDataset:
    """Render one safe Spanish error and stop before exposing technical details."""

    # El log conserva la excepción completa para el diagnóstico técnico. La
    # interfaz muestra mensajes comprensibles y no expone rutas internas,
    # detalles del contrato ni trazas a la usuaria.
    try:
        return _configured_dataset()
    except GoldVersionError:
        LOGGER.exception("La identidad o versión Gold no coincide.")
        st.error("La versión del dataset no coincide con la esperada.")
    except (GoldManifestError, GoldSchemaError):
        LOGGER.exception("El contrato Gold no tiene el formato esperado.")
        st.error("El dataset no tiene el formato esperado.")
    except GoldIntegrityError:
        LOGGER.exception("Falló la verificación de integridad Gold.")
        st.error("No se pudo verificar la integridad del dataset.")
    except GoldDatasetError:
        LOGGER.exception("El dataset Gold no está disponible.")
        st.error("Dataset no disponible.")
    except Exception:
        LOGGER.exception("Error inesperado al cargar el dataset Gold.")
        st.error("Dataset no disponible.")
    st.stop()
    raise AssertionError("st.stop() debe detener la ejecución")


def _navigate(view: str, *, project_id: str | None = None) -> None:
    """Persist navigation identity in query parameters and request a rerun."""

    # view y project_id se guardan en la URL mediante query parameters. Esto
    # permite recargar o compartir una ficha y mantiene la URL como autoridad
    # de navegación, en vez de depender solo de session_state.
    st.query_params.clear()
    st.query_params["view"] = view
    if project_id is not None:
        st.query_params["project_id"] = project_id
    st.rerun()


def _render_navigation(
    view: str,
    *,
    dataset: GoldDataset,
    project_id: str | None,
    data_explorer_enabled: bool,
) -> None:
    """Render minimal navigation without making session state authoritative."""

    st.sidebar.markdown("### Navegación")
    if st.sidebar.button(
        "Resumen",
        width="stretch",
        disabled=view == "resumen",
    ):
        _navigate("resumen")
    if st.sidebar.button(
        "Metodología",
        width="stretch",
        disabled=view == "metodologia",
    ):
        _navigate("metodologia")
    _render_report_channel(dataset, view=view, project_id=project_id)
    if data_explorer_enabled and st.sidebar.button(
        "Auditoría de datos",
        width="stretch",
        disabled=view == "datos",
    ):
        _navigate("datos")


def _clear_filter_state() -> None:
    """Clear only transient filter widget state."""

    epoch = int(st.session_state.get(_CHART_EPOCH_KEY, 0)) + 1
    for key in _FILTER_KEYS:
        st.session_state.pop(key, None)
    for key in (
        _ACTIVE_CHART_YEAR_KEY,
        _ACTIVE_ADMIN_SELECTION_KEY,
        _ACTIVE_MAP_SELECTION_KEY,
        _ACTIVE_TABLE_FILTER_KEY,
        _ADMINISTRATIVE_TEMPORAL_CONTROL_KEY,
    ):
        st.session_state.pop(key, None)
    st.session_state[_CHART_EPOCH_KEY] = epoch


def _clear_chart_year_filter(
    minimum: date,
    maximum: date,
) -> None:
    """Clear the chart-owned temporal predicates and both chart selections."""

    st.session_state["filter_years"] = []
    st.session_state["filter_dates"] = (minimum, maximum)
    st.session_state.pop(_ACTIVE_CHART_YEAR_KEY, None)
    st.session_state[_CHART_EPOCH_KEY] = (
        int(st.session_state.get(_CHART_EPOCH_KEY, 0)) + 1
    )


def _release_chart_selection() -> None:
    """Reset chart-owned visual state after an explicit widget change."""

    st.session_state.pop(_ACTIVE_CHART_YEAR_KEY, None)
    st.session_state[_CHART_EPOCH_KEY] = (
        int(st.session_state.get(_CHART_EPOCH_KEY, 0)) + 1
    )


def _release_named_selection(key: str) -> None:
    """Release one chart-owned predicate after its filter widget is edited."""

    if key not in st.session_state:
        return
    st.session_state.pop(key, None)
    st.session_state[_CHART_EPOCH_KEY] = (
        int(st.session_state.get(_CHART_EPOCH_KEY, 0)) + 1
    )


def _release_named_selections(*keys: str) -> None:
    """Release several visual origins after one canonical filter edit."""

    released = False
    for key in keys:
        if key in st.session_state:
            st.session_state.pop(key, None)
            released = True
    if released:
        st.session_state[_CHART_EPOCH_KEY] = (
            int(st.session_state.get(_CHART_EPOCH_KEY, 0)) + 1
        )


def _synchronize_temporal_interpretation(
    source_key: str,
    target_key: str,
) -> None:
    """Copy one approved temporal mode to its other visible control."""

    temporal_interpretation = st.session_state.get(source_key)
    if temporal_interpretation not in _TEMPORAL_INTERPRETATION_LABELS:
        return
    st.session_state[target_key] = temporal_interpretation
    st.session_state.pop(_ACTIVE_ADMIN_SELECTION_KEY, None)
    st.session_state[_CHART_EPOCH_KEY] = (
        int(st.session_state.get(_CHART_EPOCH_KEY, 0)) + 1
    )


def _change_chart_owned_year_filter(
    available_years: tuple[int, ...],
    minimum: date,
    maximum: date,
) -> None:
    """Keep dates coherent when a user edits a chart-owned year widget."""

    if st.session_state.get(_ACTIVE_CHART_YEAR_KEY) is None:
        return
    selected = list(st.session_state.get("filter_years", []))
    if len(selected) == 1:
        temporal = build_chart_year_filter(
            int(selected[0]),
            available_years=available_years,
        )
        st.session_state["filter_dates"] = (
            temporal.start_date,
            temporal.end_date,
        )
    else:
        st.session_state["filter_dates"] = (minimum, maximum)
    _release_chart_selection()


def _change_chart_owned_date_filter() -> None:
    """Let an explicit date edit replace, rather than conflict with, chart state."""

    if st.session_state.get(_ACTIVE_CHART_YEAR_KEY) is None:
        return
    st.session_state["filter_years"] = []
    _release_chart_selection()


def _retain_compatible_state(key: str, options: tuple[str, ...]) -> None:
    """Drop stale hierarchical selections before their widget is instantiated."""

    # Al cambiar una comunidad o provincia, una selección hija anterior puede
    # dejar de existir entre las nuevas opciones. Se elimina antes de reconstruir
    # el multiselect para evitar un estado de widget incompatible.
    current = st.session_state.get(key, [])
    compatible = [value for value in current if value in options]
    if compatible != list(current):
        st.session_state[key] = compatible


def _date_bounds(dataset: GoldDataset) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the inclusive publication-date bounds of project events."""

    dates = dataset.project_events["publication_date"]
    return pd.Timestamp(dates.min()), pd.Timestamp(dates.max())


def _apply_selected_year(
    year: int,
    *,
    available_years: tuple[int, ...],
) -> None:
    """Translate one selected chart year to the shared temporal predicates."""

    temporal = build_chart_year_filter(year, available_years=available_years)
    st.session_state["filter_years"] = list(temporal.publication_years)
    st.session_state["filter_dates"] = (
        temporal.start_date,
        temporal.end_date,
    )
    st.session_state[_ACTIVE_CHART_YEAR_KEY] = year


def _apply_selected_territory(
    dataset: GoldDataset,
    *,
    level: str,
    code: str,
    name: str,
) -> bool:
    """Apply one code-validated map point through the existing name filters."""

    code_columns = {
        "autonomous_community": "ine_autonomous_community_code",
        "province": "ine_province_code",
        "municipality": "ine_municipality_code",
    }
    code_column = code_columns.get(level)
    if code_column is None:
        return False
    rows = dataset.project_locations[
        dataset.project_locations[code_column].astype("string").eq(code)
    ]
    if rows.empty:
        return False
    row = rows.iloc[0]
    st.session_state["filter_communities"] = [
        str(row["autonomous_community"])
    ]
    if level == "autonomous_community":
        st.session_state["filter_provinces"] = []
        st.session_state["filter_municipalities"] = []
    elif level == "province":
        st.session_state["filter_provinces"] = [str(row["province"])]
        st.session_state["filter_municipalities"] = []
    else:
        st.session_state["filter_provinces"] = [str(row["province"])]
        st.session_state["filter_municipalities"] = [str(row["municipality"])]
    st.session_state[_ACTIVE_MAP_SELECTION_KEY] = {
        "level": level,
        "code": code,
        "name": name,
    }
    active_table = st.session_state.get(_ACTIVE_TABLE_FILTER_KEY)
    if isinstance(active_table, dict) and active_table.get("column") in {
        "Comunidad autónoma",
        "Provincia",
        "Municipio(s)",
    }:
        st.session_state.pop(_ACTIVE_TABLE_FILTER_KEY, None)
    return True


def _context_values(
    context: dict[str, object],
    key: str,
    *,
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate one structured catalogue value set against filter options."""

    raw = context.get(key)
    if not isinstance(raw, (list, tuple)):
        return ()
    values = tuple(dict.fromkeys(str(value) for value in raw))
    if not values or any(value not in allowed for value in values):
        return ()
    return values


def _apply_catalog_cell_filter(
    context: dict[str, object],
    *,
    column: str,
    options: dict[str, tuple[str, ...]],
) -> bool:
    """Dispatch one filterable catalogue cell to canonical session filters."""

    if column == "Tecnología":
        technology = context.get("technology")
        if (
            not isinstance(technology, str)
            or technology not in options["technologies"]
        ):
            return False
        st.session_state["filter_technologies"] = [technology]
        selected_values = (label_technology(technology),)
    elif column == "Comunidad autónoma":
        communities = _context_values(
            context,
            "autonomous_communities",
            allowed=options["autonomous_communities"],
        )
        if not communities:
            return False
        st.session_state["filter_communities"] = list(communities)
        st.session_state["filter_provinces"] = []
        st.session_state["filter_municipalities"] = []
        st.session_state.pop(_ACTIVE_MAP_SELECTION_KEY, None)
        selected_values = communities
    elif column == "Provincia":
        provinces = _context_values(
            context,
            "provinces",
            allowed=options["provinces"],
        )
        communities = _context_values(
            context,
            "province_communities",
            allowed=options["autonomous_communities"],
        )
        if not provinces or not communities:
            return False
        st.session_state["filter_communities"] = list(communities)
        st.session_state["filter_provinces"] = list(provinces)
        st.session_state["filter_municipalities"] = []
        st.session_state.pop(_ACTIVE_MAP_SELECTION_KEY, None)
        selected_values = provinces
    elif column == "Municipio(s)":
        municipalities = _context_values(
            context,
            "municipalities",
            allowed=options["municipalities"],
        )
        provinces = _context_values(
            context,
            "municipality_provinces",
            allowed=options["provinces"],
        )
        communities = _context_values(
            context,
            "municipality_communities",
            allowed=options["autonomous_communities"],
        )
        if not municipalities or not provinces or not communities:
            return False
        st.session_state["filter_communities"] = list(communities)
        st.session_state["filter_provinces"] = list(provinces)
        st.session_state["filter_municipalities"] = list(municipalities)
        st.session_state.pop(_ACTIVE_MAP_SELECTION_KEY, None)
        selected_values = municipalities
    else:
        return False
    st.session_state[_ACTIVE_TABLE_FILTER_KEY] = {
        "column": column,
        "values": selected_values,
    }
    return True


def _consume_summary_interactions(dataset: GoldDataset) -> str | None:
    """Apply completed native selections before rebuilding shared filters.

    Chart and dataframe state is read-only once instantiated. Consuming the
    previous epoch before widgets are rebuilt keeps every visual selection in
    the same AND-composed filter model and gives the next chart a clean state.
    """

    epoch = int(st.session_state.get(_CHART_EPOCH_KEY, 0))
    options = get_filter_options(dataset)
    changed = False
    for chart_name, selection_name in (
        ("project_year_chart", _PROJECT_YEAR_SELECTION),
        ("publication_year_chart", _PUBLICATION_YEAR_SELECTION),
    ):
        selected_year = extract_chart_selected_year(
            st.session_state.get(f"{chart_name}_{epoch}"),
            selection_name=selection_name,
            available_years=options["publication_years"],
        )
        if selected_year is not None:
            _apply_selected_year(
                selected_year,
                available_years=options["publication_years"],
            )
            changed = True

    administrative_segment = extract_chart_selected_values(
        st.session_state.get(f"administrative_chart_{epoch}"),
        selection_name=_ADMINISTRATIVE_SELECTION,
        fields=("action_type", "decision"),
    )
    administrative_action = extract_chart_selected_values(
        st.session_state.get(f"administrative_chart_{epoch}"),
        selection_name=_ADMINISTRATIVE_ACTION_SELECTION,
        fields=("action_type",),
    )
    if administrative_segment is not None:
        action_type = str(administrative_segment["action_type"])
        decision = str(administrative_segment["decision"])
        if (
            action_type in options["action_types"]
            and decision in options["decisions"]
        ):
            st.session_state["filter_actions"] = [action_type]
            st.session_state["filter_decisions"] = [decision]
            st.session_state[_ACTIVE_ADMIN_SELECTION_KEY] = (
                action_type,
                decision,
            )
            changed = True
    elif administrative_action is not None:
        action_type = str(administrative_action["action_type"])
        if action_type in options["action_types"]:
            st.session_state["filter_actions"] = [action_type]
            st.session_state["filter_decisions"] = []
            st.session_state[_ACTIVE_ADMIN_SELECTION_KEY] = (
                action_type,
                None,
            )
            changed = True

    map_context = st.session_state.get(f"map_context_{epoch}")
    if isinstance(map_context, dict):
        territories = map_context.get("territories")
        territory = parse_folium_territory_selection(
            st.session_state.get(f"map_chart_{epoch}"),
            expected_level=str(map_context.get("level")),
            allowed_territories=(
                territories if isinstance(territories, dict) else {}
            ),
        )
        current = st.session_state.get(_ACTIVE_MAP_SELECTION_KEY)
        selected_identity = None if territory is None else {
            "level": territory.level,
            "code": territory.code,
            "name": territory.name,
        }
        if (
            territory is not None
            and current != selected_identity
            and _apply_selected_territory(
                dataset,
                level=territory.level,
                code=territory.code,
                name=territory.name,
            )
        ):
            changed = True

    table_state = st.session_state.get(f"summary_catalog_{epoch}")
    table_context = st.session_state.get(f"summary_catalog_context_{epoch}")
    if isinstance(table_state, dict) and isinstance(table_context, list):
        raw_selection = table_state.get("selection")
        if isinstance(raw_selection, dict):
            rows = raw_selection.get("rows")
            cells = raw_selection.get("cells")
            selected_cell: tuple[int, str] | None = None
            if isinstance(cells, (list, tuple)):
                for cell in cells:
                    if (
                        isinstance(cell, (list, tuple))
                        and len(cell) == 2
                        and isinstance(cell[0], int)
                        and isinstance(cell[1], str)
                    ):
                        selected_cell = (cell[0], cell[1])
                        break
            if (
                selected_cell is not None
                and 0 <= selected_cell[0] < len(table_context)
            ):
                row_position, column = selected_cell
                context = table_context[row_position]
                if column == "Proyecto":
                    if changed:
                        st.session_state[_CHART_EPOCH_KEY] = epoch + 1
                    return str(context["project_id"])
                if (
                    column in _TABLE_FILTERABLE_COLUMNS
                    and isinstance(context, dict)
                    and _apply_catalog_cell_filter(
                        context,
                        column=column,
                        options=options,
                    )
                ):
                    changed = True
            elif (
                isinstance(rows, (list, tuple))
                and len(rows) == 1
                and isinstance(rows[0], int)
                and 0 <= rows[0] < len(table_context)
            ):
                if changed:
                    st.session_state[_CHART_EPOCH_KEY] = epoch + 1
                return str(table_context[rows[0]]["project_id"])

    if changed:
        st.session_state[_CHART_EPOCH_KEY] = epoch + 1
    return None


def _render_filters(dataset: GoldDataset) -> dict[str, object]:
    """Render compact filters and return canonical selections for pure queries."""

    st.sidebar.markdown("### Filtros")
    st.sidebar.button(
        "Limpiar filtros",
        on_click=_clear_filter_state,
        width="stretch",
        type="primary",
    )
    st.sidebar.markdown("### Proyecto")
    text = st.sidebar.text_input(
        "Buscar proyecto",
        key="filter_text",
        placeholder="Nombre de la planta",
    )
    base_options = get_filter_options(dataset)
    minimum, maximum = _date_bounds(dataset)
    technologies = st.sidebar.multiselect(
        "Tecnología",
        base_options["technologies"],
        format_func=label_technology,
        key="filter_technologies",
        on_change=_release_named_selection,
        args=(_ACTIVE_TABLE_FILTER_KEY,),
    )
    st.sidebar.markdown("### Territorio")
    communities = st.sidebar.multiselect(
        "Comunidad autónoma",
        base_options["autonomous_communities"],
        key="filter_communities",
        on_change=_release_named_selections,
        args=(_ACTIVE_MAP_SELECTION_KEY, _ACTIVE_TABLE_FILTER_KEY),
    )
    territorial_options = get_filter_options(
        dataset,
        autonomous_communities=communities,
    )
    _retain_compatible_state(
        "filter_provinces",
        territorial_options["provinces"],
    )
    provinces = st.sidebar.multiselect(
        "Provincia",
        territorial_options["provinces"],
        key="filter_provinces",
        on_change=_release_named_selections,
        args=(_ACTIVE_MAP_SELECTION_KEY, _ACTIVE_TABLE_FILTER_KEY),
    )
    territorial_options = get_filter_options(
        dataset,
        autonomous_communities=communities,
        provinces=provinces,
    )
    _retain_compatible_state(
        "filter_municipalities",
        territorial_options["municipalities"],
    )
    municipalities = st.sidebar.multiselect(
        "Municipio",
        territorial_options["municipalities"],
        key="filter_municipalities",
        on_change=_release_named_selections,
        args=(_ACTIVE_MAP_SELECTION_KEY, _ACTIVE_TABLE_FILTER_KEY),
    )
    st.sidebar.markdown("### Seguimiento administrativo")
    temporal_interpretation = st.sidebar.selectbox(
        "Interpretación temporal",
        tuple(_TEMPORAL_INTERPRETATION_LABELS),
        index=0,
        format_func=_TEMPORAL_INTERPRETATION_LABELS.get,
        help=(
            "La última decisión selecciona la publicación más reciente "
            "disponible para cada tipo de trámite. La opción histórica busca "
            "en cualquier publicación, aunque existan otras posteriores para "
            "ese mismo trámite."
        ),
        key="filter_temporal_interpretation",
        on_change=_synchronize_temporal_interpretation,
        args=(
            "filter_temporal_interpretation",
            _ADMINISTRATIVE_TEMPORAL_CONTROL_KEY,
        ),
    )
    publication_years = st.sidebar.multiselect(
        "Año de publicación",
        base_options["publication_years"],
        key="filter_years",
        on_change=_change_chart_owned_year_filter,
        args=(
            base_options["publication_years"],
            minimum.date(),
            maximum.date(),
        ),
    )
    default_dates = (minimum.date(), maximum.date())
    current_dates = st.session_state.get("filter_dates")
    if not isinstance(current_dates, (tuple, list)) or len(current_dates) != 2:
        st.session_state["filter_dates"] = default_dates
    date_range = st.sidebar.date_input(
        "Fecha publicación",
        min_value=date(minimum.year, 1, 1),
        max_value=date(maximum.year, 12, 31),
        key="filter_dates",
        on_change=_change_chart_owned_date_filter,
    )
    action_types = st.sidebar.multiselect(
        "Trámite",
        base_options["action_types"],
        format_func=label_action_type,
        key="filter_actions",
        on_change=_release_named_selection,
        args=(_ACTIVE_ADMIN_SELECTION_KEY,),
    )
    decisions = st.sidebar.multiselect(
        "Situación publicada",
        base_options["decisions"],
        format_func=label_decision,
        key="filter_decisions",
        on_change=_release_named_selection,
        args=(_ACTIVE_ADMIN_SELECTION_KEY,),
    )
    if len(action_types) >= 2:
        action_match = st.sidebar.segmented_control(
            "Coincidencia de trámites",
            tuple(_ACTION_MATCH_LABELS),
            default=ACTION_MATCH_ANY,
            required=True,
            format_func=_ACTION_MATCH_LABELS.get,
            key="filter_action_match",
            width="stretch",
        )
    else:
        st.session_state.pop("filter_action_match", None)
        action_match = ACTION_MATCH_ANY
    active_chart_year = st.session_state.get(_ACTIVE_CHART_YEAR_KEY)
    if active_chart_year is not None:
        st.sidebar.caption(
            f"Año seleccionado en el gráfico: **{int(active_chart_year)}**."
        )
        st.sidebar.button(
            "Quitar año seleccionado",
            icon=":material/filter_alt_off:",
            on_click=_clear_chart_year_filter,
            args=(minimum.date(), maximum.date()),
            width="stretch",
        )
    active_administrative = st.session_state.get(_ACTIVE_ADMIN_SELECTION_KEY)
    if isinstance(active_administrative, (tuple, list)) and len(
        active_administrative
    ) == 2:
        administrative_label = label_action_type(active_administrative[0])
        if active_administrative[1] is None:
            administrative_label += " · Todas las situaciones"
        else:
            administrative_label += (
                f" · {label_decision(active_administrative[1])}"
            )
        st.sidebar.caption(
            "Selección del gráfico administrativo: "
            f"**{administrative_label}**."
        )
    active_map = st.session_state.get(_ACTIVE_MAP_SELECTION_KEY)
    if isinstance(active_map, dict) and active_map.get("name"):
        st.sidebar.caption(
            f"Territorio seleccionado en el mapa: **{active_map['name']}**."
        )
    active_table = st.session_state.get(_ACTIVE_TABLE_FILTER_KEY)
    if isinstance(active_table, dict):
        column = active_table.get("column")
        values = active_table.get("values")
        if isinstance(column, str) and isinstance(values, (list, tuple)):
            rendered_values = ", ".join(str(value) for value in values)
            st.sidebar.caption(
                f"Selección desde la tabla: **{column} · {rendered_values}**."
            )
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range
    if start_date == minimum.date() and end_date == maximum.date():
        start_date = end_date = None
    return {
        "text": text,
        "technologies": technologies,
        "autonomous_communities": communities,
        "provinces": provinces,
        "municipalities": municipalities,
        "publication_years": publication_years,
        "start_date": start_date,
        "end_date": end_date,
        "action_types": action_types,
        "decisions": decisions,
        "temporal_interpretation": temporal_interpretation,
        "action_match": action_match,
    }


def _catalog_display(
    catalog: pd.DataFrame,
    *,
    visible_columns: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Build the visual catalogue while retaining project IDs outside display."""

    columns: dict[str, object] = {
        "Proyecto": catalog["project_name"].map(format_project_display_name),
        "Tecnología": catalog["technology"].map(label_technology),
        "Comunidad autónoma": catalog["autonomous_communities"].replace(
            "", "No consta"
        ),
        "Provincia": catalog["provinces"].replace("", "No consta"),
        "Municipio(s)": catalog["municipalities"].replace("", "No consta"),
        "Primera publicación observada": catalog[
            "first_publication_date"
        ].dt.strftime("%d/%m/%Y"),
        "Última publicación observada": catalog[
            "last_publication_date"
        ].dt.strftime("%d/%m/%Y"),
        "N.º BOE": catalog["n_publications"],
        "N.º actuaciones": catalog["n_administrative_actions"],
        "Territorio resumido": catalog["territorial_summary"].replace(
            "", "No consta"
        ),
    }
    if "matching_action_types" in catalog.columns:
        columns["Trámites coincidentes"] = catalog[
            "matching_action_types"
        ].map(_matching_action_types_text)
    display = pd.DataFrame(columns)
    if visible_columns is None:
        selected = _CATALOG_DEFAULT_COLUMNS
    else:
        selected = tuple(dict.fromkeys(visible_columns))
    allowed = [
        column
        for column in _CATALOG_OPTIONAL_COLUMNS
        if column in display.columns and column in selected
    ]
    return display.loc[:, ["Proyecto", *allowed]]


def _select_catalog_columns(*, key: str, has_matching_actions: bool) -> tuple[str, ...]:
    """Render a compact visible-column selector with Project always retained."""

    matching_seen_key = f"{key}_matching_seen"
    if has_matching_actions and not st.session_state.get(matching_seen_key, False):
        current = list(st.session_state.get(key, _CATALOG_DEFAULT_COLUMNS))
        if "Trámites coincidentes" not in current:
            st.session_state[key] = [*current, "Trámites coincidentes"]
        st.session_state[matching_seen_key] = True
    elif not has_matching_actions:
        st.session_state.pop(matching_seen_key, None)
    options = tuple(
        column
        for column in _CATALOG_OPTIONAL_COLUMNS
        if has_matching_actions or column != "Trámites coincidentes"
    )
    default = _CATALOG_DEFAULT_COLUMNS if key not in st.session_state else None
    selected = st.multiselect(
        "Columnas visibles",
        options,
        default=default,
        key=key,
        help="La columna «Proyecto» permanece siempre visible.",
    )
    st.caption("«Proyecto» es una columna obligatoria y permanece siempre visible.")
    return tuple(selected)


def _matching_action_types_text(values: object, *, limit: int = 3) -> str:
    """Format matching canonical action types without hiding omitted values."""

    labels = [label_action_type(value) for value in tuple(values)]
    if len(labels) <= limit:
        return " · ".join(labels)
    return f"{' · '.join(labels[:limit])} · y {len(labels) - limit} más"


def _render_map(
    dataset: GoldDataset,
    filtered_projects: pd.DataFrame,
) -> None:
    """Render administrative associations by official INE code."""

    st.subheader("Distribución territorial administrativa")
    st.caption(
        "Proyectos asociados a territorios administrativos según publicaciones "
        "del BOE. Seleccione un territorio para incorporarlo a los filtros."
    )
    level = st.segmented_control(
        "Nivel territorial",
        _GENERAL_MAP_LEVELS,
        default="autonomous_community",
        required=True,
        format_func=_MAP_LEVEL_LABELS.get,
        key="map_level",
        on_change=_release_named_selection,
        args=(_ACTIVE_MAP_SELECTION_KEY,),
        width="stretch",
    )
    counts = build_territory_project_counts(
        dataset.project_locations,
        project_ids=filtered_projects["project_id"],
        level=level,
    )
    try:
        geometry = _configured_geometry()
        country_context = _configured_country_context()
        context_features: list[dict[str, object]] = []
        collection, unmatched = attach_project_counts(
            geometry.features[level],
            counts,
        )
        if unmatched:
            raise GeometryReferenceError(
                "Hay códigos analíticos sin geometría administrativa."
            )
        if level == "municipality":
            province_codes = tuple(dict.fromkeys(
                str(feature["properties"]["province_code"])
                for feature in geometry.features["municipality"]
            ))
            community_codes = tuple(dict.fromkeys(
                str(feature["properties"]["autonomous_community_code"])
                for feature in geometry.features["municipality"]
            ))
            provinces, missing_provinces = select_geometry_features(
                geometry.features["province"],
                codes=province_codes,
            )
            communities, missing_communities = select_geometry_features(
                geometry.features["autonomous_community"],
                codes=community_codes,
            )
            if missing_provinces or missing_communities:
                raise GeometryReferenceError(
                    "Falta contexto padre para el mapa municipal."
                )
            context_features.extend(communities)
            context_features.extend(provinces)
    except GeometryReferenceError:
        LOGGER.exception("No se pudo verificar la cartografía administrativa.")
        st.warning("La cartografía administrativa no está disponible.")
        return
    epoch = int(st.session_state.get(_CHART_EPOCH_KEY, 0))
    st.session_state[f"map_context_{epoch}"] = {
        "level": level,
        "territories": {
            str(feature["properties"]["code"]): str(
                feature["properties"]["name"]
            )
            for feature in collection["features"]
        },
    }
    st_folium(
        build_folium_choropleth(
            collection,
            country_context=country_context.collection,
            context_features=context_features,
        ),
        key=f"map_chart_{epoch}",
        width=None,
        height=430,
        returned_objects=("last_active_drawing",),
    )
    st.caption(
        "Un proyecto puede estar asociado a varios territorios; por ello la "
        "suma del mapa puede superar el total de proyectos. "
        + (
            "En Municipios se conserva el universo de municipios presentes en "
            "el corpus, incluidos los que tengan 0 proyectos con los filtros "
            "actuales. "
            if level == "municipality"
            else ""
        )
        + f"{NATURAL_EARTH_ATTRIBUTION}. {BDLJE_ATTRIBUTION}."
    )


def _render_year_chart(
    counts: pd.DataFrame,
    *,
    title: str,
    metric_column: str,
    metric_title: str,
    chart_name: str,
    selection_name: str,
) -> None:
    """Render one selectable annual series wired to the shared filter state."""

    st.subheader(title)
    if counts.empty:
        st.info("No hay observaciones temporales que coincidan con los filtros.")
        return
    epoch = int(st.session_state.get(_CHART_EPOCH_KEY, 0))
    chart_key = f"{chart_name}_{epoch}"
    st.vega_lite_chart(
        counts,
        {
            "mark": {"type": "bar", "cornerRadiusEnd": 3},
            "params": [{
                "name": selection_name,
                "select": {
                    "type": "point",
                    "fields": ["publication_year"],
                    "toggle": False,
                    "clear": "dblclick",
                },
            }],
            "encoding": {
                "x": {
                    "field": "publication_year",
                    "type": "ordinal",
                    "title": "Año de publicación",
                },
                "y": {
                    "field": metric_column,
                    "type": "quantitative",
                    "title": metric_title,
                },
                "color": {
                    "condition": {
                        "param": selection_name,
                        "value": "#1d4ed8",
                    },
                    "value": "#93c5fd",
                    "legend": None,
                },
                "tooltip": [
                    {
                        "field": "publication_year",
                        "type": "ordinal",
                        "title": "Año",
                    },
                    {
                        "field": metric_column,
                        "type": "quantitative",
                        "title": metric_title,
                    },
                ],
            },
            "height": 300,
        },
        width="stretch",
        key=chart_key,
        on_select="rerun",
        selection_mode=selection_name,
    )


def _render_project_chart(
    events: pd.DataFrame,
) -> None:
    """Render distinct projects with an observed publication in each year."""

    _render_year_chart(
        build_yearly_project_counts(events),
        title="Evolución de proyectos",
        metric_column="projects",
        metric_title="Proyectos distintos",
        chart_name="project_year_chart",
        selection_name=_PROJECT_YEAR_SELECTION,
    )
    st.caption(
        "Proyectos distintos con al menos una publicación observada en cada año; "
        "no representa proyectos construidos ni necesariamente proyectos nuevos."
    )


def _render_publication_chart(
    events: pd.DataFrame,
) -> None:
    """Render distinct BOE publications by observed year."""

    _render_year_chart(
        build_publication_counts(events),
        title="Evolución de publicaciones BOE",
        metric_column="boe_publications",
        metric_title="Publicaciones BOE distintas",
        chart_name="publication_year_chart",
        selection_name=_PUBLICATION_YEAR_SELECTION,
    )
    st.caption("Publicaciones BOE distintas observadas en cada año.")


def _render_administrative_chart(
    events: pd.DataFrame,
    *,
    temporal_interpretation: str,
) -> None:
    """Render project counts by published action and decision."""

    if (
        st.session_state.get(_ADMINISTRATIVE_TEMPORAL_CONTROL_KEY)
        != temporal_interpretation
    ):
        st.session_state[_ADMINISTRATIVE_TEMPORAL_CONTROL_KEY] = (
            temporal_interpretation
        )
    st.segmented_control(
        "Interpretación temporal del gráfico",
        tuple(_TEMPORAL_INTERPRETATION_LABELS),
        required=True,
        format_func=_TEMPORAL_INTERPRETATION_LABELS.get,
        key=_ADMINISTRATIVE_TEMPORAL_CONTROL_KEY,
        on_change=_synchronize_temporal_interpretation,
        args=(
            _ADMINISTRATIVE_TEMPORAL_CONTROL_KEY,
            "filter_temporal_interpretation",
        ),
        width="stretch",
    )
    if temporal_interpretation == LATEST_TEMPORAL_INTERPRETATION:
        title = "Última situación publicada por tipo de actuación"
        temporal_caption = (
            "Para cada proyecto y trámite se conserva únicamente la publicación "
            "más reciente observada."
        )
    else:
        title = "Situaciones publicadas históricamente por tipo de actuación"
        temporal_caption = (
            "Cada proyecto se cuenta una vez por combinación de trámite y "
            "situación observada en cualquier publicación del corpus."
        )
    st.subheader(title)
    counts = build_administrative_situation_counts(
        events,
        temporal_interpretation=temporal_interpretation,
    )
    if counts.empty:
        st.info("No hay actuaciones que coincidan con los filtros.")
        return
    display = counts.assign(
        tramite=counts["action_type"].map(label_action_type),
        situacion=counts["decision"].map(label_decision),
    )
    display["action_total"] = display.groupby(
        "action_type", sort=False
    )["project_count"].transform("sum")
    action_sort = {
        "field": "action_total",
        "op": "max",
        "order": "descending",
    }
    st.vega_lite_chart(
        display,
        {
            "hconcat": [
                {
                    "width": 46,
                    "title": {
                        "text": "Todo",
                        "subtitle": "el trámite",
                        "fontSize": 12,
                        "subtitleFontSize": 10,
                    },
                    "transform": [{
                        "aggregate": [{
                            "op": "max",
                            "field": "action_total",
                            "as": "action_total",
                        }],
                        "groupby": ["action_type", "tramite"],
                    }],
                    "mark": {
                        "type": "point",
                        "filled": True,
                        "shape": "circle",
                        "size": 150,
                    },
                    "params": [{
                        "name": _ADMINISTRATIVE_ACTION_SELECTION,
                        "select": {
                            "type": "point",
                            "fields": ["action_type"],
                            "toggle": False,
                            "clear": "dblclick",
                        },
                    }],
                    "encoding": {
                        "y": {
                            "field": "tramite",
                            "type": "nominal",
                            "sort": action_sort,
                            "axis": None,
                        },
                        "x": {"value": 23},
                        "opacity": {
                            "condition": {
                                "param": _ADMINISTRATIVE_ACTION_SELECTION,
                                "value": 1,
                            },
                            "value": 0.45,
                        },
                        "tooltip": [{
                            "field": "tramite",
                            "type": "nominal",
                            "title": "Filtrar todo el trámite",
                        }],
                    },
                },
                {
                    "mark": {"type": "bar", "cornerRadiusEnd": 2},
                    "params": [{
                        "name": _ADMINISTRATIVE_SELECTION,
                        "select": {
                            "type": "point",
                            "fields": ["action_type", "decision"],
                            "toggle": False,
                            "clear": "dblclick",
                        },
                    }],
                    "encoding": {
                        "y": {
                            "field": "tramite",
                            "type": "nominal",
                            "title": "Trámite",
                            "sort": action_sort,
                        },
                        "x": {
                            "field": "project_count",
                            "type": "quantitative",
                            "title": "Proyectos distintos",
                        },
                        "color": {
                            "field": "situacion",
                            "type": "nominal",
                            "title": "Situación publicada",
                        },
                        "opacity": {
                            "condition": {
                                "param": _ADMINISTRATIVE_SELECTION,
                                "value": 1,
                            },
                            "value": 0.4,
                        },
                        "tooltip": [
                            {
                                "field": "tramite",
                                "type": "nominal",
                                "title": "Trámite",
                            },
                            {
                                "field": "situacion",
                                "type": "nominal",
                                "title": "Situación",
                            },
                            {
                                "field": "project_count",
                                "type": "quantitative",
                                "title": "Proyectos",
                            },
                        ],
                    },
                },
            ],
            "resolve": {"scale": {"y": "shared"}},
            "spacing": 4,
            "height": 420,
        },
        width="stretch",
        key=(
            "administrative_chart_"
            f"{int(st.session_state.get(_CHART_EPOCH_KEY, 0))}"
        ),
        on_select="rerun",
        selection_mode=(
            _ADMINISTRATIVE_ACTION_SELECTION,
            _ADMINISTRATIVE_SELECTION,
        ),
    )
    st.caption(
        f"{temporal_caption} Seleccione el punto «Todo» de una fila para "
        "filtrar todas las situaciones de ese trámite, o un segmento para "
        "aplicar simultáneamente su trámite y su situación publicada."
    )


def _render_summary(dataset: GoldDataset) -> None:
    """Render the approved two-KPI dashboard over one filter selection."""

    st.markdown(
        "Consulta la actividad administrativa publicada para los proyectos del "
        "corpus final W14. Todos los resultados y gráficos responden a los mismos "
        "filtros."
    )
    filters = _render_filters(dataset)
    selection = build_dashboard_selection(dataset, **filters)
    metrics = summarize_dashboard_selection(selection)
    project_metric, publication_metric = st.columns(
        _DASHBOARD_EQUAL_COLUMN_WEIGHTS
    )
    with project_metric:
        st.metric(
            "Proyectos",
            metrics.projects,
            icon=":material/wind_power:",
            border=True,
        )
    with publication_metric:
        st.metric(
            "Publicaciones BOE relevantes",
            metrics.relevant_boe_publications,
            icon=":material/article:",
            border=True,
        )
    if selection.projects.empty:
        st.info("No hay proyectos que coincidan con los filtros.")
    project_column, publication_column = st.columns(
        _DASHBOARD_EQUAL_COLUMN_WEIGHTS,
        border=True,
    )
    with project_column:
        _render_project_chart(selection.supporting_events)
    with publication_column:
        _render_publication_chart(selection.supporting_events)
    with st.container(border=True):
        _render_map(dataset, selection.projects)
    with st.container(border=True):
        _render_administrative_chart(
            selection.supporting_events,
            temporal_interpretation=str(filters["temporal_interpretation"]),
        )
    catalog = selection.projects.sort_values(
        ["last_publication_date", "project_name", "project_id"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    with st.container(border=True):
        st.subheader("Proyectos con actividad observada")
        visible_columns = _select_catalog_columns(
            key="summary_catalog_columns",
            has_matching_actions="matching_action_types" in catalog.columns,
        )
        st.caption(
            "Seleccione una fila o la celda Proyecto para abrir la ficha. Las "
            "celdas de Tecnología, Comunidad autónoma, Provincia y Municipio(s) "
            "filtran todo el resumen."
        )
        epoch = int(st.session_state.get(_CHART_EPOCH_KEY, 0))
        st.session_state[f"summary_catalog_context_{epoch}"] = (
            build_catalog_interaction_context(
                dataset,
                catalog["project_id"].astype(str),
            )
        )
        st.dataframe(
            _catalog_display(catalog, visible_columns=visible_columns),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode=("single-row", "single-cell"),
            key=f"summary_catalog_{epoch}",
        )


def _project_map_level(locations: pd.DataFrame) -> str | None:
    """Choose the most precise contractual level available for one project."""

    for level in ("municipality", "province", "autonomous_community"):
        if locations["location_level"].eq(level).any():
            return level
    return None


def _render_project_map(
    dataset: GoldDataset,
    project_id: str,
    locations: pd.DataFrame,
) -> None:
    """Render only the resolved territories associated with one project."""

    st.subheader("Ámbito territorial")
    level = _project_map_level(locations)
    if level is None:
        st.info(
            "No consta un ámbito territorial resoluble en las publicaciones "
            "analizadas."
        )
        return
    counts = build_territory_project_counts(
        dataset.project_locations,
        project_ids=(project_id,),
        level=level,
    )
    try:
        geometry = _configured_geometry()
        country_context = _configured_country_context()
        selected_features, unmatched = select_geometry_features(
            geometry.features[level],
            codes=tuple(counts["code"].astype(str)),
        )
        if unmatched:
            raise GeometryReferenceError(
                "Hay códigos analíticos sin geometría administrativa."
            )
        community_names = {
            str(feature["properties"]["code"]): str(
                feature["properties"]["name"]
            )
            for feature in geometry.features["autonomous_community"]
        }
        province_names = {
            str(feature["properties"]["code"]): str(
                feature["properties"]["name"]
            )
            for feature in geometry.features["province"]
        }
        community_codes: list[str] = []
        province_codes: list[str] = []
        for feature in selected_features:
            properties = feature["properties"]
            community_code = str(properties["autonomous_community_code"])
            community_codes.append(community_code)
            properties["autonomous_community_name"] = community_names[
                community_code
            ]
            if level == "municipality":
                province_code = str(properties["province_code"])
                province_codes.append(province_code)
                properties["province_name"] = province_names[province_code]
        context_features: list[dict[str, object]] = []
        if level == "municipality":
            provinces, missing_provinces = select_geometry_features(
                geometry.features["province"],
                codes=tuple(dict.fromkeys(province_codes)),
            )
            if missing_provinces:
                raise GeometryReferenceError(
                    "Falta contexto provincial para el mapa de proyecto."
                )
            context_features.extend(provinces)
        if level != "autonomous_community":
            communities, missing_communities = select_geometry_features(
                geometry.features["autonomous_community"],
                codes=tuple(dict.fromkeys(community_codes)),
            )
            if missing_communities:
                raise GeometryReferenceError(
                    "Falta contexto autonómico para el mapa de proyecto."
                )
            context_features.extend(communities)
    except GeometryReferenceError:
        LOGGER.exception("No se pudo verificar la cartografía administrativa.")
        st.warning("La cartografía administrativa no está disponible.")
        return
    if not selected_features:
        st.info(
            "No consta un ámbito territorial resoluble en las publicaciones "
            "analizadas."
        )
        return
    selected_collection = {
        "type": "FeatureCollection",
        "features": list(selected_features),
    }
    st_folium(
        build_folium_project_map(
            selected_collection,
            country_context=country_context.collection,
            context_features=context_features,
        ),
        key=f"detail_map_{project_id}",
        width=None,
        height=360,
        returned_objects=(),
    )
    territory_names = " · ".join(counts["name"].astype(str))
    st.caption(
        f"{_MAP_LEVEL_LABELS[level]} representados: {territory_names}. "
        f"{NATURAL_EARTH_ATTRIBUTION}. {BDLJE_ATTRIBUTION}."
    )
    st.info(TERRITORIAL_NOTE)


def _render_timeline(timeline: pd.DataFrame) -> None:
    """Render all actions grouped once under their BOE publication."""

    st.subheader("Cronología administrativa publicada")
    st.caption(
        "Actuaciones observadas, agrupadas una sola vez bajo cada publicación BOE."
    )
    for group in group_project_timeline_by_publication(timeline):
        date_text = group.publication_date.strftime("%d/%m/%Y")
        with st.container(border=True):
            st.markdown(
                f"#### {date_text}  \n"
                f"[{group.boe_id}]({build_boe_url(group.boe_id)})"
            )
            action_label = (
                "actuación publicada"
                if len(group.actions) == 1
                else "actuaciones publicadas"
            )
            st.caption(f"{len(group.actions)} {action_label}")
            for action in group.actions:
                modification = (
                    " · Modificación" if action.is_modification else ""
                )
                action_type = label_action_type(action.action_type)
                st.markdown(
                    f"**{action_type}**  \n"
                    f"Situación publicada: **{label_decision(action.decision)}**"
                    f"{modification}"
                )
                with st.expander(f"Evidencia publicada · {action_type}"):
                    st.write(action.evidence)


def _report_filter_context(dataset: GoldDataset) -> dict[str, object]:
    """Describe only effective public filters with human-readable labels."""

    context: dict[str, object] = {}
    text = st.session_state.get("filter_text")
    if isinstance(text, str) and text.strip():
        context["Búsqueda de proyecto"] = text.strip()
    labelers = (
        ("filter_technologies", "Tecnología", label_technology),
        ("filter_communities", "Comunidad autónoma", str),
        ("filter_provinces", "Provincia", str),
        ("filter_municipalities", "Municipio", str),
        ("filter_actions", "Trámite", label_action_type),
        ("filter_decisions", "Situación publicada", label_decision),
    )
    for key, label, formatter in labelers:
        values = st.session_state.get(key)
        if isinstance(values, (list, tuple)) and values:
            context[label] = tuple(formatter(value) for value in values)
    years = st.session_state.get("filter_years")
    if isinstance(years, (list, tuple)) and years:
        context["Año de publicación"] = tuple(str(value) for value in years)
    dates = st.session_state.get("filter_dates")
    if isinstance(dates, (list, tuple)) and len(dates) == 2:
        minimum, maximum = _date_bounds(dataset)
        try:
            selected_dates = tuple(pd.Timestamp(value).date() for value in dates)
        except (TypeError, ValueError):
            selected_dates = ()
        if selected_dates and selected_dates != (minimum.date(), maximum.date()):
            context["Fecha de publicación"] = tuple(
                value.strftime("%d/%m/%Y") for value in selected_dates
            )
    temporal = st.session_state.get("filter_temporal_interpretation")
    if temporal in _TEMPORAL_INTERPRETATION_LABELS and (
        temporal != LATEST_TEMPORAL_INTERPRETATION
    ):
        context["Interpretación temporal"] = _TEMPORAL_INTERPRETATION_LABELS[
            temporal
        ]
    action_match = st.session_state.get("filter_action_match")
    if action_match in _ACTION_MATCH_LABELS:
        context["Coincidencia de trámites"] = _ACTION_MATCH_LABELS[action_match]
    return context


def _render_report_channel(
    dataset: GoldDataset,
    *,
    view: str,
    project_id: str | None,
) -> None:
    """Render the sole bounded report control directly below navigation."""

    destination = _report_destination()
    if destination is None:
        st.sidebar.button(
            "Reportar posible error",
            icon=":material/mail:",
            type="secondary",
            disabled=True,
            width="stretch",
        )
        st.sidebar.caption(
            "Canal de reporte no configurado en esta instalación."
        )
        return
    view_context = {
        "resumen": "Resumen",
        "ficha": "Ficha de proyecto",
        "metodologia": "Metodología",
        "datos": "Auditoría de datos",
    }.get(view, "Aplicación pública")
    project_name = stable_project_id = boe_id = publication_date = None
    boe_url = first_publication_date = last_publication_date = None
    if view == "ficha" and project_id:
        try:
            project = get_project_detail(dataset, project_id)
            timeline = get_project_timeline(dataset, project_id)
        except ProjectNotFoundError:
            project = None
            timeline = pd.DataFrame()
        if project is not None and not timeline.empty:
            latest = timeline.sort_values(
                [
                    "publication_date",
                    "event_index",
                    "administrative_action_index",
                ],
                kind="stable",
            ).iloc[-1]
            project_name = format_project_display_name(project["project_name"])
            stable_project_id = project_id
            boe_id = str(latest["boe_id"])
            publication_date = pd.Timestamp(latest["publication_date"]).strftime(
                "%d/%m/%Y"
            )
            boe_url = build_boe_url(boe_id)
            first_publication_date = pd.Timestamp(
                project["first_publication_date"]
            ).strftime("%d/%m/%Y")
            last_publication_date = pd.Timestamp(
                project["last_publication_date"]
            ).strftime("%d/%m/%Y")
    mailto = build_error_report_mailto(
        destination,
        project_name=project_name,
        project_id=stable_project_id,
        boe_id=boe_id,
        publication_date=publication_date,
        boe_url=boe_url,
        first_publication_date=first_publication_date,
        last_publication_date=last_publication_date,
        view_context=view_context,
        active_filters=_report_filter_context(dataset),
    )
    st.sidebar.link_button(
        "Reportar posible error",
        mailto,
        icon=":material/mail:",
        type="secondary",
        width="stretch",
    )
    st.sidebar.caption(
        "El enlace abre su cliente de correo. La aplicación no almacena ni envía "
        "el mensaje y no modifica los datos publicados. No incluya información "
        "personal o sensible."
    )


def _render_publications(publications: pd.DataFrame) -> None:
    """Render the distinct BOE publications contributing to the project."""

    st.subheader("Publicaciones implicadas")
    display = pd.DataFrame({
        "Fecha": publications["publication_date"].dt.strftime("%d/%m/%Y"),
        "Publicación BOE": publications["boe_id"],
        "Enlace oficial": publications["boe_id"].map(build_boe_url),
        "N.º actuaciones": publications["administrative_actions"],
    })
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Enlace oficial": st.column_config.LinkColumn(
                "Enlace oficial",
                display_text="Abrir BOE",
            ),
        },
    )


def _project_description(project: pd.Series, catalog_row: pd.Series) -> str:
    """Build a short deterministic description from Gold presentation fields."""

    name = format_project_display_name(project["project_name"])
    technology = label_technology(project["technology"]).casefold()
    first = pd.Timestamp(project["first_publication_date"]).strftime("%d/%m/%Y")
    last = pd.Timestamp(project["last_publication_date"]).strftime("%d/%m/%Y")
    publications = int(project["n_publications"])
    actions = int(project["n_administrative_actions"])
    description = (
        f"Proyecto de generación {technology} identificado como «{name}», con "
        f"publicaciones observadas entre el {first} y el {last}. "
    )
    territory = str(catalog_row["territorial_summary"])
    if territory:
        description += (
            "Las publicaciones analizadas lo asocian territorialmente con "
            f"{territory}. "
        )
    publication_noun = "publicación BOE" if publications == 1 else (
        "publicaciones BOE"
    )
    action_noun = "actuación administrativa" if actions == 1 else (
        "actuaciones administrativas"
    )
    return (
        f"{description}El corpus contiene {publications} {publication_noun} y "
        f"{actions} {action_noun}."
    )


def _render_detail(dataset: GoldDataset, project_id: str | None) -> None:
    """Render one complete project independently of catalogue filter state."""

    if not project_id:
        st.warning("El proyecto solicitado no existe.")
        if st.button("Volver al resumen"):
            _navigate("resumen")
        return
    try:
        project = get_project_detail(dataset, project_id)
        timeline = get_project_timeline(dataset, project_id)
        locations = get_project_locations(dataset, project_id)
        location_sources = get_project_location_sources(dataset, project_id)
    except ProjectNotFoundError:
        st.warning("El proyecto solicitado no existe.")
        if st.button("Volver al resumen"):
            _navigate("resumen")
        return
    if st.button("← Volver al resumen"):
        _navigate("resumen")
    catalog = build_project_catalog(dataset)
    catalog_row = catalog[catalog["project_id"].eq(project_id)].iloc[0]
    st.header(format_project_display_name(project["project_name"]))
    st.caption(label_technology(project["technology"]))
    st.write(_project_description(project, catalog_row))
    with st.container(horizontal=True):
        st.metric(
            "Publicaciones BOE",
            int(project["n_publications"]),
            border=True,
        )
        st.metric(
            "Actuaciones publicadas",
            int(project["n_administrative_actions"]),
            border=True,
        )
        st.metric(
            "Primera publicación observada",
            pd.Timestamp(project["first_publication_date"]).strftime("%d/%m/%Y"),
            border=True,
        )
        st.metric(
            "Última publicación observada",
            pd.Timestamp(project["last_publication_date"]).strftime("%d/%m/%Y"),
            border=True,
        )
    action_projects = dataset.project_events.groupby(
        "administrative_action_id"
    )["project_id"].nunique()
    shared_action_count = timeline["administrative_action_id"].map(
        action_projects
    ).gt(1).sum()
    if shared_action_count:
        noun = "actuación compartida" if shared_action_count == 1 else (
            "actuaciones compartidas"
        )
        verb = "aparece" if shared_action_count == 1 else "aparecen"
        st.caption(
            f"{int(shared_action_count)} {noun} {verb} sin duplicados en "
            "esta ficha, con sus vínculos multiproyecto conservados en Gold."
        )
    with st.container(border=True):
        _render_project_map(dataset, project_id, locations)
    with st.container(border=True):
        _render_publications(
            build_project_publication_summary(timeline, location_sources)
        )
    _render_timeline(timeline)


def _render_methodology(dataset: GoldDataset) -> None:
    """Render the concise methodology and validated snapshot identity."""

    st.header("Metodología")
    st.subheader("Cobertura del corpus final")
    st.write(
        "Proyectos de generación con actividad publicada en el BOE durante la "
        "ventana ancla del 7 al 20 de agosto de 2026, con reconstrucción "
        "retrospectiva conservadora de publicaciones relacionadas observadas "
        "desde 2022."
    )
    st.write(
        "El corpus no es un censo exhaustivo del BOE ni de las instalaciones "
        "renovables españolas. La reconstrucción histórica usa candidatos Tier 1 "
        "y Tier 2 strict; el emparejamiento amplio Tier 3 queda excluido."
    )
    st.subheader("Fuente")
    st.write(
        "Boletín Oficial del Estado para publicaciones y evidencias; INE para "
        "códigos territoriales; cartografía de límites administrativos IGN/CNIG."
    )
    st.subheader("Unidad de proyecto")
    st.write(
        "Las plantas de generación son la raíz de agrupación. Almacenamiento "
        "e infraestructuras asociadas se vinculan cuando la publicación aporta "
        "evidencia suficiente. Una actuación sobre infraestructura compartida "
        "puede conservar vínculos con varios proyectos sin duplicarse como acto."
    )
    st.write(
        "El BOE no proporciona un identificador estable de proyecto. La agrupación "
        "determinista construye identidades reproducibles a partir de menciones de "
        "activos de generación; no se presenta como resolución de entidades perfecta."
    )
    st.subheader("Cronología")
    st.write(
        "Primera y última publicación significan primera y última publicación "
        "observadas dentro de este corpus."
    )
    st.write(
        "Interpretación de las situaciones administrativas. La aplicación muestra "
        "actuaciones y decisiones publicadas en el BOE dentro del periodo analizado. "
        "Estas publicaciones describen la evolución administrativa observada, pero "
        "no deben interpretarse por sí solas como una certificación del estado "
        "jurídico actual y definitivo del proyecto."
    )
    st.subheader("Territorio")
    st.write(TERRITORIAL_NOTE)
    st.write(
        "El mapa agrega asociaciones administrativas mediante códigos oficiales; "
        "no representa coordenadas ni la ubicación física exacta de la planta. "
        "La geometría procede de «Límites municipales, provinciales y autonómicos» "
        "(LILIM), fichero LINEAS_LIMITE.ZIP actualizado el 28/07/2026. "
        "El contexto de países procede de Natural Earth y se sirve localmente, "
        "sin tiles externos ni API key. "
        f"{NATURAL_EARTH_ATTRIBUTION}. {BDLJE_ATTRIBUTION}."
    )
    st.subheader("Correcciones humanas")
    st.write(
        "Las correcciones humanas son entradas versionadas y trazables que se "
        "aplican antes de materializar Silver y Gold."
    )
    st.subheader("Glosario")
    st.markdown(
        "- **BOE** — Boletín Oficial del Estado\n"
        "- **CNIG** — Centro Nacional de Información Geográfica\n"
        "- **FV** — Fotovoltaica\n"
        "- **HSF** — Huerta Solar Fotovoltaica\n"
        "- **IGN** — Instituto Geográfico Nacional\n"
        "- **INE** — Instituto Nacional de Estadística"
    )
    st.subheader("Limitaciones")
    unresolved_territory = len(
        set(dataset.projects["project_id"].astype(str))
        - set(dataset.project_locations["project_id"].astype(str))
    )
    st.write(
        "La aplicación no infiere potencia, promotor, coordenadas, componentes "
        "detallados, targets ni un estado jurídico consolidado fuera del contrato "
        f"Gold validado. {unresolved_territory} proyectos sin territorio resuelto "
        "permanecen en el "
        "catálogo y los indicadores, aunque no aporten geometría al mapa."
    )
    st.subheader("Evaluación y versión")
    st.markdown(
        "- documentos analizados: 104\n"
        "- documentos relevantes: 80\n"
        "- documentos no relevantes: 24\n"
        f"- proyectos canónicos: {dataset.projects['project_id'].nunique()}\n"
        f"- publicaciones BOE relevantes: "
        f"{dataset.project_events['boe_id'].nunique()}\n"
        f"- snapshot validado: `{dataset.downstream_id}`\n"
        f"- base metodológica: `{CORE_FREEZE_TAG}`"
    )


def _audit_multiselect(
    dataset: GoldDataset,
    table_name: str,
    column: str,
    label: str,
    *,
    key: str,
) -> list[str]:
    """Render one audit multiselect from values observed in validated Gold."""

    return st.multiselect(
        label,
        observed_filter_values(dataset, table_name, column),
        key=key,
    )


def _audit_date_range(
    frame: pd.DataFrame,
    column: str,
    label: str,
    *,
    key: str,
) -> tuple[object | None, object | None]:
    """Render an inclusive audit range when the source contains valid dates."""

    dates = frame[column].dropna()
    if dates.empty:
        st.caption("La tabla no contiene fechas para aplicar este filtro.")
        return None, None
    minimum = pd.Timestamp(dates.min()).date()
    maximum = pd.Timestamp(dates.max()).date()
    selected = st.date_input(
        label,
        value=(minimum, maximum),
        min_value=minimum,
        max_value=maximum,
        key=key,
    )
    if isinstance(selected, (tuple, list)) and len(selected) == 2:
        return selected[0], selected[1]
    return selected, selected


def _audit_projects_filters(dataset: GoldDataset) -> pd.DataFrame:
    """Render and apply row-level filters for the canonical projects table."""

    source = get_audit_table(dataset, "projects")
    text = st.text_input(
        "Buscar project_id o nombre",
        key="audit_projects_text",
    )
    technologies = _audit_multiselect(
        dataset,
        "projects",
        "technology",
        "Tecnología",
        key="audit_projects_technology",
    )
    dates = st.columns(2)
    first = pd.Timestamp(source["first_publication_date"].min()).date()
    last = pd.Timestamp(source["last_publication_date"].max()).date()
    first_from = dates[0].date_input(
        "Primera publicación desde",
        value=first,
        min_value=first,
        max_value=last,
        key="audit_projects_first",
    )
    last_to = dates[1].date_input(
        "Última publicación hasta",
        value=last,
        min_value=first,
        max_value=last,
        key="audit_projects_last",
    )
    return filter_audit_projects(
        dataset,
        text=text,
        technologies=technologies,
        first_publication_from=first_from,
        last_publication_to=last_to,
    )


def _audit_events_filters(dataset: GoldDataset) -> pd.DataFrame:
    """Render and apply row-level filters for project events."""

    project_ids = _audit_multiselect(
        dataset,
        "project_events",
        "project_id",
        "Project ID",
        key="audit_events_project",
    )
    boe_ids = _audit_multiselect(
        dataset,
        "project_events",
        "boe_id",
        "BOE ID",
        key="audit_events_boe",
    )
    action_types = _audit_multiselect(
        dataset,
        "project_events",
        "action_type",
        "Tipo de actuación",
        key="audit_events_action",
    )
    decisions = _audit_multiselect(
        dataset,
        "project_events",
        "decision",
        "Decisión",
        key="audit_events_decision",
    )
    modification = st.selectbox(
        "Modificación",
        ("all", "yes", "no"),
        format_func={"all": "Todas", "yes": "Sí", "no": "No"}.get,
        key="audit_events_modification",
    )
    start, end = _audit_date_range(
        get_audit_table(dataset, "project_events"),
        "publication_date",
        "Fecha de publicación",
        key="audit_events_dates",
    )
    return filter_audit_project_events(
        dataset,
        project_ids=project_ids,
        boe_ids=boe_ids,
        action_types=action_types,
        decisions=decisions,
        is_modification=(
            None if modification == "all" else modification == "yes"
        ),
        start_date=start,
        end_date=end,
    )


def _audit_locations_filters(dataset: GoldDataset) -> pd.DataFrame:
    """Render and apply row-level filters for canonical territories."""

    values = {
        column: _audit_multiselect(
            dataset,
            "project_locations",
            column,
            label,
            key=f"audit_locations_{column}",
        )
        for column, label in (
            ("project_id", "Project ID"),
            ("location_level", "Nivel territorial"),
            ("autonomous_community", "Comunidad autónoma"),
            ("province", "Provincia"),
            ("municipality", "Municipio"),
        )
    }
    code_options = sorted({
        value
        for column in (
            "ine_municipality_code",
            "ine_province_code",
            "ine_autonomous_community_code",
        )
        for value in observed_filter_values(dataset, "project_locations", column)
    })
    ine_codes = st.multiselect(
        "Código INE",
        code_options,
        key="audit_locations_ine_codes",
    )
    return filter_audit_project_locations(
        dataset,
        project_ids=values["project_id"],
        location_levels=values["location_level"],
        autonomous_communities=values["autonomous_community"],
        provinces=values["province"],
        municipalities=values["municipality"],
        ine_codes=ine_codes,
    )


def _audit_sources_filters(dataset: GoldDataset) -> pd.DataFrame:
    """Render and apply row-level filters for territorial provenance."""

    values = {
        column: _audit_multiselect(
            dataset,
            "project_location_sources",
            column,
            label,
            key=f"audit_sources_{column}",
        )
        for column, label in (
            ("project_location_id", "Project location ID"),
            ("location_mention_id", "Location mention ID"),
            ("event_id", "Event ID"),
            ("boe_id", "BOE ID"),
        )
    }
    start, end = _audit_date_range(
        get_audit_table(dataset, "project_location_sources"),
        "publication_date",
        "Fecha de publicación",
        key="audit_sources_dates",
    )
    return filter_audit_project_location_sources(
        dataset,
        location_ids=values["project_location_id"],
        location_mention_ids=values["location_mention_id"],
        event_ids=values["event_id"],
        boe_ids=values["boe_id"],
        start_date=start,
        end_date=end,
    )


def _filtered_audit_table(
    dataset: GoldDataset,
    table_name: str,
) -> pd.DataFrame:
    """Dispatch canonical audit filters without mixing them into callbacks."""

    filters = {
        "projects": _audit_projects_filters,
        "project_events": _audit_events_filters,
        "project_locations": _audit_locations_filters,
        "project_location_sources": _audit_sources_filters,
    }
    return filters[table_name](dataset)


def _relationship_text(table_name: str) -> str:
    """Format declared relationships for the selected canonical table."""

    relationships = GOLD_TABLE_SPECS[table_name].relationships
    if not relationships:
        return "tabla raíz"
    return "; ".join(
        f"{', '.join(item.columns)} → "
        f"{item.target_table}({', '.join(item.target_columns)})"
        for item in relationships
    )


def _render_table_quality(dataset: GoldDataset, table_name: str) -> None:
    """Render observations over a table already accepted by the Gold loader."""

    quality = summarize_table_quality(dataset, table_name)
    metrics = st.columns(3)
    metrics[0].metric("Filas", quality.row_count)
    metrics[1].metric("Columnas", quality.column_count)
    metrics[2].metric(
        "Filas con PK duplicada",
        quality.duplicate_primary_key_rows,
    )
    st.subheader("Nulos por columna")
    st.dataframe(
        pd.DataFrame(quality.null_counts, columns=["Columna", "Nulos"]),
        hide_index=True,
        width="stretch",
    )
    if quality.observed_domains:
        st.subheader("Dominios observados")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Columna": column, "Valores observados": ", ".join(values)}
                    for column, values in quality.observed_domains
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    if quality.date_ranges:
        st.subheader("Rangos de fechas")
        st.dataframe(
            pd.DataFrame(
                quality.date_ranges,
                columns=["Columna", "Mínima", "Máxima"],
            ),
            hide_index=True,
            width="stretch",
        )
    for warning in quality.warnings:
        st.warning(warning)
    if not quality.warnings:
        st.success("No se observan duplicados según la clave primaria.")


def _render_canonical_audit_table(
    dataset: GoldDataset,
    table_name: str,
) -> None:
    """Render content, dictionary and quality for one canonical Gold table."""

    spec = GOLD_TABLE_SPECS[table_name]
    source = get_audit_table(dataset, table_name)
    st.caption(f"Tabla canónica: `{spec.name}`")
    st.write(spec.description)
    st.markdown(f"**Granularidad:** {spec.granularity}")
    st.markdown(f"**Clave primaria:** `{', '.join(spec.primary_key)}`")
    st.markdown(f"**Relaciones principales:** {_relationship_text(table_name)}")
    if table_name == "project_events":
        action_projects = source.groupby("administrative_action_id")[
            "project_id"
        ].nunique()
        st.caption(
            f"{len(source)} filas, "
            f"{source['administrative_action_id'].nunique()} actuaciones "
            f"administrativas únicas y "
            f"{int(action_projects.gt(1).sum())} actuaciones multiproyecto."
        )
    content, schema, quality = st.tabs(["Contenido", "Esquema", "Calidad"])
    with content:
        filtered = _filtered_audit_table(dataset, table_name)
        st.caption(f"Filas visibles: {len(filtered)} de {len(source)}")
        if filtered.empty:
            st.info("No hay filas que coincidan con los filtros seleccionados.")
        else:
            # La auditoría conserva los IDs técnicos y utiliza una tabla de
            # consulta, no un editor, para que ninguna celda pueda modificarse.
            st.dataframe(filtered, hide_index=True, width="stretch")
    with schema:
        st.caption("Diccionario observado del snapshot Gold ya validado.")
        st.dataframe(
            build_schema_summary(dataset, table_name),
            hide_index=True,
            width="stretch",
        )
    with quality:
        st.caption(
            "Resumen descriptivo; no sustituye la validación contractual del loader."
        )
        _render_table_quality(dataset, table_name)


def _render_project_summary_audit(dataset: GoldDataset) -> None:
    """Render the existing one-row-per-project catalogue as a derived audit view."""

    st.caption("Vista derivada: no es una quinta tabla Gold canónica.")
    st.write(
        "Resume cada proyecto en una sola fila y conserva la granularidad del "
        "catálogo, sin unir actuaciones y territorios entre sí."
    )
    text = st.text_input(
        "Buscar project_id o nombre",
        key="audit_summary_text",
    )
    technologies = _audit_multiselect(
        dataset,
        "projects",
        "technology",
        "Tecnología",
        key="audit_summary_technology",
    )
    project_rows = filter_audit_projects(
        dataset,
        text=text,
        technologies=technologies,
    )
    summary = build_project_summary(dataset)
    summary = summary[
        summary["project_id"].astype(str).isin(
            set(project_rows["project_id"].astype(str))
        )
    ].reset_index(drop=True).copy()
    st.caption(f"Filas visibles: {len(summary)}")
    if summary.empty:
        st.info("No hay proyectos que coincidan con los filtros seleccionados.")
    else:
        st.dataframe(summary, hide_index=True, width="stretch")


def _render_territorial_trace_audit(dataset: GoldDataset) -> None:
    """Render one row per territorial source with project and BOE context."""

    st.caption("Vista derivada: no sustituye las tablas Gold canónicas.")
    st.write(
        "Permite seguir proyecto → territorio → mención → evento → BOE → fecha."
    )
    full_trace = build_territorial_trace(dataset)
    project_ids = st.multiselect(
        "Project ID",
        sorted(full_trace["project_id"].astype(str).unique()),
        key="audit_trace_project",
    )
    location_levels = st.multiselect(
        "Nivel territorial",
        sorted(full_trace["location_level"].astype(str).unique()),
        key="audit_trace_level",
    )
    boe_ids = st.multiselect(
        "BOE ID",
        sorted(full_trace["boe_id"].astype(str).unique()),
        key="audit_trace_boe",
    )
    # La vista conserva una fila por fuente territorial. No une las actuaciones
    # de project_events, porque esa relación multiplicaría filas sin aportar
    # nueva trazabilidad sobre el territorio.
    trace = filter_territorial_trace(
        dataset,
        project_ids=project_ids,
        location_levels=location_levels,
        boe_ids=boe_ids,
    )
    st.caption(f"Filas visibles: {len(trace)} de {len(full_trace)}")
    if trace.empty:
        st.info("No hay trazas territoriales que coincidan con los filtros.")
    else:
        st.dataframe(trace, hide_index=True, width="stretch")


def _render_data_explorer(dataset: GoldDataset) -> None:
    """Render the configuration-gated, read-only Gold audit view."""

    st.header("Auditoría de datos Gold")
    st.write(
        "Esta vista permite inspeccionar las tablas validadas que alimentan la "
        "aplicación. Es una herramienta de consulta: no modifica los datos."
    )
    st.info(
        "Gold está compuesto por varias tablas relacionadas. No existe una "
        "única tabla plana que conserve correctamente todas las granularidades."
    )
    st.caption(f"Downstream ID auditado: `{dataset.downstream_id}`")
    selected_view = st.selectbox(
        "Vista de auditoría",
        tuple(_AUDIT_VIEW_LABELS),
        format_func=_AUDIT_VIEW_LABELS.get,
        key="audit_view",
    )
    try:
        if selected_view in GOLD_TABLE_SPECS:
            _render_canonical_audit_table(dataset, selected_view)
        elif selected_view == "project_summary":
            _render_project_summary_audit(dataset)
        else:
            _render_territorial_trace_audit(dataset)
    except AuditDataError:
        LOGGER.exception("No se pudo preparar la vista de auditoría Gold.")
        st.error("No se pudo mostrar la vista de auditoría seleccionada.")


def main() -> None:
    """Configure and render the single-page read-only application."""

    st.set_page_config(
        page_title="Seguimiento de proyectos energéticos en el BOE",
        page_icon=":material/wind_power:",
        layout="wide",
    )
    st.title("Seguimiento de proyectos energéticos en el BOE")
    st.caption(
        "Cronología y ámbito territorial publicados para proyectos de "
        "generación eléctrica."
    )
    dataset = _load_or_stop()
    # En cada rerun se leen view y project_id desde los query parameters, que son
    # la autoridad de navegación. session_state se reserva para el estado
    # transitorio de los widgets y no decide qué vista está abierta.
    data_explorer_enabled = _data_explorer_enabled()
    raw_view = st.query_params.get("view", "resumen")
    allowed_views = {"resumen", "ficha", "metodologia"}
    if data_explorer_enabled:
        allowed_views.add("datos")
    view = raw_view if raw_view in allowed_views else "resumen"
    if view != raw_view:
        st.query_params.clear()
        st.query_params["view"] = "resumen"
    project_id = st.query_params.get("project_id") if view == "ficha" else None
    if view == "resumen":
        selected_project_id = _consume_summary_interactions(dataset)
        if selected_project_id is not None:
            _navigate("ficha", project_id=selected_project_id)
    _render_navigation(
        view,
        dataset=dataset,
        project_id=project_id,
        data_explorer_enabled=data_explorer_enabled,
    )
    if view == "ficha":
        _render_detail(dataset, project_id)
    elif view == "metodologia":
        _render_methodology(dataset)
    elif view == "datos":
        _render_data_explorer(dataset)
    elif view == "resumen":
        _render_summary(dataset)


if __name__ == "__main__":
    main()
