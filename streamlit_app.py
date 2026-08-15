"""Local read-only Streamlit application over the validated Gold snapshot."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import streamlit as st

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
from renewables_permitting.app_queries import (
    ProjectNotFoundError,
    build_boe_url,
    filter_projects,
    get_filter_options,
    get_project_detail,
    get_project_location_sources,
    get_project_locations,
    get_project_timeline,
    label_action_type,
    label_decision,
    label_technology,
)
from renewables_permitting.extraction.paths import find_project_root


LOGGER = logging.getLogger(__name__)
DEFAULT_GOLD_DIR = (
    "runs/canonical-140-streamlit-base-20260814/downstream/gold"
)
DEFAULT_DOWNSTREAM_ID = (
    "7e0c9a84891ecbac66087a7af653ead436e69194653806a3697f3c8607948834"
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
    "filter_dates",
    "filter_actions",
    "filter_decisions",
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


def _render_navigation(view: str, *, data_explorer_enabled: bool) -> None:
    """Render minimal navigation without making session state authoritative."""

    st.sidebar.markdown("### Navegación")
    if st.sidebar.button(
        "Explorar proyectos",
        width="stretch",
        disabled=view == "explorar",
    ):
        _navigate("explorar")
    if st.sidebar.button(
        "Metodología",
        width="stretch",
        disabled=view == "metodologia",
    ):
        _navigate("metodologia")
    if data_explorer_enabled and st.sidebar.button(
        "Auditoría de datos",
        width="stretch",
        disabled=view == "datos",
    ):
        _navigate("datos")


def _clear_filter_state() -> None:
    """Clear only transient filter widget state."""

    for key in _FILTER_KEYS:
        st.session_state.pop(key, None)


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


def _render_filters(dataset: GoldDataset) -> dict[str, object]:
    """Render compact filters and return canonical selections for pure queries."""

    st.sidebar.markdown("### Filtros")
    st.sidebar.button(
        "Limpiar filtros",
        on_click=_clear_filter_state,
        width="stretch",
    )
    text = st.sidebar.text_input(
        "Buscar proyecto",
        key="filter_text",
        placeholder="Nombre de la planta",
    )
    base_options = get_filter_options(dataset)
    technologies = st.sidebar.multiselect(
        "Tecnología",
        base_options["technologies"],
        format_func=label_technology,
        key="filter_technologies",
    )
    communities = st.sidebar.multiselect(
        "Comunidad autónoma",
        base_options["autonomous_communities"],
        key="filter_communities",
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
    )
    minimum, maximum = _date_bounds(dataset)
    date_range = st.sidebar.date_input(
        "Fecha de publicación",
        value=(minimum.date(), maximum.date()),
        min_value=minimum.date(),
        max_value=maximum.date(),
        key="filter_dates",
    )
    action_types = st.sidebar.multiselect(
        "Actuación",
        base_options["action_types"],
        format_func=label_action_type,
        key="filter_actions",
    )
    decisions = st.sidebar.multiselect(
        "Decisión",
        base_options["decisions"],
        format_func=label_decision,
        key="filter_decisions",
    )
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range
    return {
        "text": text,
        "technologies": technologies,
        "autonomous_communities": communities,
        "provinces": provinces,
        "municipalities": municipalities,
        "start_date": start_date,
        "end_date": end_date,
        "action_types": action_types,
        "decisions": decisions,
    }


def _period_text(first: object, last: object) -> str:
    """Format a publication period compactly in Spanish date notation."""

    first_date = pd.Timestamp(first).strftime("%d/%m/%Y")
    last_date = pd.Timestamp(last).strftime("%d/%m/%Y")
    return first_date if first_date == last_date else f"{first_date} – {last_date}"


def _catalog_display(catalog: pd.DataFrame) -> pd.DataFrame:
    """Build the visual catalogue while retaining project IDs outside display."""

    display = pd.DataFrame({
        "Proyecto": catalog["project_name"],
        "Tecnología": catalog["technology"].map(label_technology),
        "Territorio": catalog["territorial_summary"],
        "Periodo publicado": [
            _period_text(first, last)
            for first, last in zip(
                catalog["first_publication_date"],
                catalog["last_publication_date"],
            )
        ],
        "Publicaciones": catalog["n_publications"],
        "Actuaciones": catalog["n_administrative_actions"],
    })
    return display


def _render_catalog_metrics(
    dataset: GoldDataset,
    filtered: pd.DataFrame,
) -> None:
    """Render project, distinct-action and distinct-publication counts."""

    project_ids = set(filtered["project_id"].astype(str))
    events = dataset.project_events[
        dataset.project_events["project_id"].astype(str).isin(project_ids)
    ]
    columns = st.columns(3)
    columns[0].metric("Proyectos mostrados", len(filtered))
    columns[1].metric(
        "Actuaciones asociadas",
        events["administrative_action_id"].nunique(),
    )
    columns[2].metric("Publicaciones asociadas", events["boe_id"].nunique())


def _render_explore(dataset: GoldDataset) -> None:
    """Render the filterable one-row-per-project master catalogue."""

    st.markdown(
        "Explora proyectos de generación identificados en publicaciones del "
        "BOE y consulta su cronología y ámbito territorial publicados."
    )
    filters = _render_filters(dataset)
    filtered = filter_projects(dataset, **filters)
    _render_catalog_metrics(dataset, filtered)
    if filtered.empty:
        st.info("No hay proyectos que coincidan con los filtros.")
        return
    selection = st.dataframe(
        _catalog_display(filtered),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
    )
    selected_rows = selection.selection.rows
    if selected_rows:
        # Streamlit devuelve la posición visual de la fila seleccionada. Se usa
        # esa posición para recuperar el project_id del resultado filtrado; el
        # índice de pantalla no se trata como una identidad persistente.
        project_id = str(filtered.iloc[selected_rows[0]]["project_id"])
        _navigate("ficha", project_id=project_id)


def _location_display_name(row: pd.Series) -> str:
    """Return the exact location name corresponding to its contractual level."""

    if row["location_level"] == "municipality":
        return str(row["municipality"])
    if row["location_level"] == "province":
        return str(row["province"])
    return str(row["autonomous_community"])


def _location_code(row: pd.Series) -> str:
    """Return the INE code corresponding to a location's contractual level."""

    if row["location_level"] == "municipality":
        return str(row["ine_municipality_code"])
    if row["location_level"] == "province":
        return str(row["ine_province_code"])
    return str(row["ine_autonomous_community_code"])


def _territory_table(rows: pd.DataFrame) -> pd.DataFrame:
    """Create a compact visual table for one contractual location level."""

    return pd.DataFrame({
        "Territorio": rows.apply(_location_display_name, axis=1),
        "Código INE": rows.apply(_location_code, axis=1),
        "Publicaciones fuente": rows["source_publication_count"],
        "Periodo territorial": [
            _period_text(first, last)
            for first, last in zip(
                rows["first_publication_date"],
                rows["last_publication_date"],
            )
        ],
    })


def _render_territory(locations: pd.DataFrame) -> None:
    """Render complete territories without fabricating parent-level rows."""

    st.header("Ámbito territorial del proyecto")
    groups = (
        ("municipality", "Municipios"),
        ("province", "Provincias"),
        ("autonomous_community", "Comunidades autónomas"),
    )
    for level, title in groups:
        rows = locations[locations["location_level"] == level]
        if rows.empty:
            continue
        st.subheader(title)
        if level == "province":
            st.caption(
                "Estas filas representan menciones contractuales resueltas solo "
                "a nivel provincial; no son duplicados derivados de municipios."
            )
        st.dataframe(
            _territory_table(rows),
            hide_index=True,
            width="stretch",
        )
    st.info(TERRITORIAL_NOTE)


def _render_timeline(timeline: pd.DataFrame) -> None:
    """Render all published actions with literal evidence and BOE provenance."""

    st.header("Cronología administrativa publicada")
    st.caption(
        "La cronología recoge actuaciones publicadas en el BOE. No constituye "
        "por sí sola una determinación jurídica consolidada del estado actual "
        "del proyecto."
    )
    for row in timeline.itertuples(index=False):
        date_text = pd.Timestamp(row.publication_date).strftime("%d/%m/%Y")
        modification = " · Modificación" if bool(row.is_modification) else ""
        st.markdown(
            f"**{date_text} · {label_action_type(row.action_type)}**  \n"
            f"{label_decision(row.decision)}{modification} · "
            f"[{row.boe_id}]({build_boe_url(row.boe_id)})"
        )
        with st.expander("Ver evidencia publicada"):
            st.write(str(row.evidence))


def _project_publications(
    timeline: pd.DataFrame,
    location_sources: pd.DataFrame,
) -> pd.DataFrame:
    """Union and deduplicate BOE publications from actions and territory lineage."""

    action_rows = timeline.loc[:, ["boe_id", "publication_date"]]
    location_rows = location_sources.loc[:, ["boe_id", "publication_date"]]
    rows = pd.concat([action_rows, location_rows], ignore_index=True)
    return rows.sort_values(
        ["publication_date", "boe_id"], kind="stable"
    ).drop_duplicates("boe_id", keep="first").reset_index(drop=True)


def _render_publications(publications: pd.DataFrame) -> None:
    """Render the distinct BOE publications contributing to the project."""

    st.header("Publicaciones implicadas")
    for row in publications.itertuples(index=False):
        date_text = pd.Timestamp(row.publication_date).strftime("%d/%m/%Y")
        st.markdown(
            f"- [{row.boe_id}]({build_boe_url(row.boe_id)}) — {date_text}"
        )


def _render_detail(dataset: GoldDataset, project_id: str | None) -> None:
    """Render one complete project independently of catalogue filter state."""

    if not project_id:
        st.warning("El proyecto solicitado no existe.")
        if st.button("Volver a explorar"):
            _navigate("explorar")
        return
    try:
        project = get_project_detail(dataset, project_id)
        timeline = get_project_timeline(dataset, project_id)
        locations = get_project_locations(dataset, project_id)
        location_sources = get_project_location_sources(dataset, project_id)
    except ProjectNotFoundError:
        st.warning("El proyecto solicitado no existe.")
        if st.button("Volver a explorar"):
            _navigate("explorar")
        return
    if st.button("← Volver a explorar"):
        _navigate("explorar")
    st.header(str(project["project_name"]))
    st.caption(f"{label_technology(project['technology'])} · {project_id}")
    summary = st.columns(4)
    summary[0].metric(
        "Primera publicación",
        pd.Timestamp(project["first_publication_date"]).strftime("%d/%m/%Y"),
    )
    summary[1].metric(
        "Última publicación",
        pd.Timestamp(project["last_publication_date"]).strftime("%d/%m/%Y"),
    )
    summary[2].metric("Publicaciones", int(project["n_publications"]))
    summary[3].metric("Actuaciones", int(project["n_administrative_actions"]))
    _render_territory(locations)
    _render_timeline(timeline)
    _render_publications(_project_publications(timeline, location_sources))


def _render_methodology(dataset: GoldDataset) -> None:
    """Render the concise methodology and validated snapshot identity."""

    st.header("Metodología")
    st.subheader("Fuente")
    st.write("Boletín Oficial del Estado.")
    st.subheader("Unidad de proyecto")
    st.write(
        "Las plantas de generación son la raíz de agrupación. Almacenamiento "
        "e infraestructuras asociadas se vinculan al proyecto cuando procede."
    )
    st.subheader("Cronología")
    st.write(
        "Se muestran actuaciones administrativas publicadas, no un estado "
        "jurídico consolidado."
    )
    st.subheader("Territorio")
    st.write(TERRITORIAL_NOTE)
    st.subheader("Correcciones humanas")
    st.write(
        "Las correcciones humanas son entradas versionadas y trazables que se "
        "aplican antes de materializar Silver y Gold."
    )
    st.subheader("Limitaciones")
    st.write(
        "Este MVP no muestra potencia, promotor, componentes asociados "
        "detallados, targets concretos ni un estado jurídico consolidado porque "
        "esos campos no forman parte de las cuatro tablas Gold consumidas."
    )
    # Estas cardinalidades se calculan desde el Gold que se acaba de cargar. No
    # se escriben cifras fijas que quedarían obsoletas al cambiar de snapshot.
    st.subheader("Versión")
    st.markdown(
        f"- core freeze: `{CORE_FREEZE_TAG}`\n"
        f"- downstream ID: `{dataset.downstream_id}`\n"
        f"- {dataset.projects['project_id'].nunique()} proyectos\n"
        "- "
        f"{dataset.project_events['administrative_action_id'].nunique()} "
        "actuaciones únicas\n"
        f"- {len(dataset.project_events)} eventos de proyecto\n"
        f"- {len(dataset.project_locations)} asociaciones territoriales"
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
        page_icon="⚡",
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
    raw_view = st.query_params.get("view", "explorar")
    allowed_views = {"explorar", "ficha", "metodologia"}
    if data_explorer_enabled:
        allowed_views.add("datos")
    view = raw_view if raw_view in allowed_views else "explorar"
    if view != raw_view:
        st.query_params.clear()
        st.query_params["view"] = "explorar"
    _render_navigation(view, data_explorer_enabled=data_explorer_enabled)
    if view == "ficha":
        _render_detail(dataset, st.query_params.get("project_id"))
    elif view == "metodologia":
        _render_methodology(dataset)
    elif view == "datos":
        _render_data_explorer(dataset)
    else:
        _render_explore(dataset)


if __name__ == "__main__":
    main()
