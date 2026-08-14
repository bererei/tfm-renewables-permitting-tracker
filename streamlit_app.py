"""Local read-only Streamlit application over the validated Gold snapshot."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from renewables_permitting.app_data import (
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


def _render_navigation(view: str) -> None:
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


def main() -> None:
    """Configure and render the single-page, three-view read-only application."""

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
    raw_view = st.query_params.get("view", "explorar")
    view = raw_view if raw_view in {"explorar", "ficha", "metodologia"} else "explorar"
    if view != raw_view:
        st.query_params.clear()
        st.query_params["view"] = "explorar"
    _render_navigation(view)
    if view == "ficha":
        _render_detail(dataset, st.query_params.get("project_id"))
    elif view == "metodologia":
        _render_methodology(dataset)
    else:
        _render_explore(dataset)


if __name__ == "__main__":
    main()
