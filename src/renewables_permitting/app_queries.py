"""Pure application queries over the verified four-table Gold dataset."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

import pandas as pd

from renewables_permitting.app_data import GoldDataset
from renewables_permitting.utils import normalize_text


LOGGER = logging.getLogger(__name__)
_BOE_ID_RE = re.compile(r"^BOE-[A-Z]-\d{4}-\d+$")

TECHNOLOGY_LABELS: Mapping[str, str] = {
    "eolica": "Eólica",
    "fotovoltaica": "Fotovoltaica",
    "hidroelectrica": "Hidroeléctrica",
    "otra_generacion": "Otra generación",
    "termosolar": "Termosolar",
}

ACTION_TYPE_LABELS: Mapping[str, str] = {
    "autorizacion_administrativa_construccion": (
        "Autorización administrativa de construcción"
    ),
    "autorizacion_administrativa_previa": (
        "Autorización administrativa previa"
    ),
    "concesion_aguas": "Concesión de aguas",
    "declaracion_impacto_ambiental": "Declaración de impacto ambiental",
    "declaracion_utilidad_publica": "Declaración de utilidad pública",
    "evaluacion_impacto_ambiental": "Evaluación de impacto ambiental",
    "informe_determinacion_afeccion_ambiental": (
        "Informe de determinación de afección ambiental"
    ),
    "informe_impacto_ambiental": "Informe de impacto ambiental",
    "levantamiento_actas_previas_ocupacion": (
        "Levantamiento de actas previas a la ocupación"
    ),
    "otro": "Otra actuación",
    "terminacion_procedimiento": "Terminación del procedimiento",
}

DECISION_LABELS: Mapping[str, str] = {
    "archivado": "Archivado",
    "autorizado": "Autorizado",
    "convocado": "Convocado",
    "declarado": "Declarado",
    "desestimado": "Desestimado",
    "desfavorable": "Desfavorable",
    "desistido": "Desistido",
    "formulado": "Formulado",
    "requiere_evaluacion_ambiental_ordinaria": (
        "Requiere evaluación ambiental ordinaria"
    ),
    "sin_efectos_adversos_significativos": (
        "Sin efectos adversos significativos"
    ),
    "sometido_informacion_publica": "Sometido a información pública",
}

LOCATION_LEVEL_LABELS: Mapping[str, str] = {
    "municipality": "Municipio",
    "province": "Provincia",
    "autonomous_community": "Comunidad autónoma",
}

CATALOG_COLUMNS = (
    "project_id",
    "project_name",
    "technology",
    "territorial_summary",
    "first_publication_date",
    "last_publication_date",
    "n_publications",
    "n_administrative_actions",
)


class ProjectNotFoundError(LookupError):
    """A requested canonical project ID does not exist in the loaded Gold."""


def _humanize_unknown(value: str, *, domain: str) -> str:
    """Humanize a future domain code while retaining it in technical logs."""

    # Los códigos canónicos se conservan en Gold y las etiquetas solo cambian su
    # presentación. Si aparece un código futuro, se registra y se humaniza en
    # vez de ocultarlo o hacer fallar toda la interfaz.
    LOGGER.warning("Valor desconocido en el dominio %s: %s", domain, value)
    return value.replace("_", " ").strip().capitalize()


def _label(value: object, mapping: Mapping[str, str], *, domain: str) -> str:
    """Return an explicit domain label or a safe fallback for future values."""

    canonical = str(value)
    return mapping.get(canonical) or _humanize_unknown(canonical, domain=domain)


def label_technology(value: object) -> str:
    """Return the Spanish display label for a canonical technology code."""

    return _label(value, TECHNOLOGY_LABELS, domain="technology")


def label_action_type(value: object) -> str:
    """Return the Spanish display label for a canonical action type."""

    return _label(value, ACTION_TYPE_LABELS, domain="action_type")


def label_decision(value: object) -> str:
    """Return the Spanish display label for a canonical administrative decision."""

    return _label(value, DECISION_LABELS, domain="decision")


def label_location_level(value: object) -> str:
    """Return the Spanish display label for a canonical location level."""

    return _label(value, LOCATION_LEVEL_LABELS, domain="location_level")


def _sorted_unique(values: Iterable[object]) -> tuple[str, ...]:
    """Return non-null textual values once in deterministic display order."""

    unique = {
        str(value)
        for value in values
        if value is not None and not bool(pd.isna(value)) and str(value).strip()
    }
    return tuple(sorted(unique, key=lambda value: (normalize_text(value), value)))


def _short_list(values: Iterable[object], *, limit: int = 3) -> str:
    """Format a deterministic short list without hiding the omitted count."""

    ordered = _sorted_unique(values)
    if len(ordered) <= limit:
        return ", ".join(ordered)
    return f"{', '.join(ordered[:limit])} y {len(ordered) - limit} más"


def _territorial_summary(locations: pd.DataFrame) -> str:
    """Build a municipality-first concise summary from contractual locations."""

    municipalities = locations.loc[
        locations["location_level"] == "municipality", "municipality"
    ]
    if municipalities.notna().any():
        return _short_list(municipalities)
    provinces = locations.loc[
        locations["location_level"] == "province", "province"
    ]
    if provinces.notna().any():
        return _short_list(provinces)
    communities = locations.loc[
        locations["location_level"] == "autonomous_community",
        "autonomous_community",
    ]
    return _short_list(communities)


def build_project_catalog(dataset: GoldDataset) -> pd.DataFrame:
    """Return one deterministic catalogue row for every canonical project."""

    summaries = {
        project_id: _territorial_summary(group)
        for project_id, group in dataset.project_locations.groupby(
            "project_id", sort=False
        )
    }
    catalog = dataset.projects.loc[:, [
        "project_id",
        "project_name",
        "technology",
        "first_publication_date",
        "last_publication_date",
        "n_publications",
        "n_administrative_actions",
    ]].copy()
    catalog.insert(
        3,
        "territorial_summary",
        catalog["project_id"].astype(str).map(summaries).fillna(""),
    )
    return catalog.loc[:, CATALOG_COLUMNS].sort_values(
        ["project_name", "project_id"],
        key=lambda values: values.map(normalize_text),
        kind="stable",
    ).reset_index(drop=True)


def _selected(values: Iterable[str] | None) -> tuple[str, ...]:
    """Normalize an optional filter selection into an immutable tuple."""

    return tuple(values or ())


def _territorial_project_ids(
    locations: pd.DataFrame,
    *,
    autonomous_communities: tuple[str, ...],
    provinces: tuple[str, ...],
    municipalities: tuple[str, ...],
) -> set[str] | None:
    """Intersect project sets for active hierarchical territorial filters."""

    # isin combina con OR los valores de una categoría: por ejemplo, una de dos
    # provincias. Los conjuntos de cada nivel activo se intersectan después,
    # aplicando AND entre comunidad, provincia y municipio.
    active_sets: list[set[str]] = []
    if autonomous_communities:
        rows = locations[
            locations["autonomous_community"].isin(autonomous_communities)
        ]
        active_sets.append(set(rows["project_id"].astype(str)))
    if provinces:
        rows = locations[locations["province"].isin(provinces)]
        active_sets.append(set(rows["project_id"].astype(str)))
    if municipalities:
        # Solo una fila publicada a nivel municipality puede satisfacer este
        # filtro. Una mención province-only o autonomous-community-only no se
        # convierte artificialmente en un municipio más preciso.
        rows = locations[
            (locations["location_level"] == "municipality")
            & locations["municipality"].isin(municipalities)
        ]
        active_sets.append(set(rows["project_id"].astype(str)))
    if not active_sets:
        return None
    return set.intersection(*active_sets)


def _event_project_ids(
    events: pd.DataFrame,
    *,
    start_date: date | datetime | pd.Timestamp | None,
    end_date: date | datetime | pd.Timestamp | None,
    action_types: tuple[str, ...],
    decisions: tuple[str, ...],
) -> set[str] | None:
    """Filter the same event rows by date, action and decision before projection."""

    if start_date is None and end_date is None and not action_types and not decisions:
        return None
    # Los filtros se aplican sucesivamente al mismo conjunto de filas de
    # project_events. Así, fecha, actuación y decisión deben coincidir en una
    # misma fila, no en eventos diferentes del mismo proyecto.
    rows = events.copy()
    if start_date is not None:
        rows = rows[rows["publication_date"].ge(pd.Timestamp(start_date))]
    if end_date is not None:
        rows = rows[rows["publication_date"].le(pd.Timestamp(end_date))]
    if action_types:
        rows = rows[rows["action_type"].isin(action_types)]
    if decisions:
        rows = rows[rows["decision"].isin(decisions)]
    return set(rows["project_id"].astype(str))


def filter_projects(
    dataset: GoldDataset,
    *,
    text: str = "",
    technologies: Iterable[str] | None = None,
    autonomous_communities: Iterable[str] | None = None,
    provinces: Iterable[str] | None = None,
    municipalities: Iterable[str] | None = None,
    start_date: date | datetime | pd.Timestamp | None = None,
    end_date: date | datetime | pd.Timestamp | None = None,
    action_types: Iterable[str] | None = None,
    decisions: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Filter the project catalogue using OR within and AND across categories."""

    technology_values = _selected(technologies)
    community_values = _selected(autonomous_communities)
    province_values = _selected(provinces)
    municipality_values = _selected(municipalities)
    action_values = _selected(action_types)
    decision_values = _selected(decisions)
    catalog = build_project_catalog(dataset)
    if normalize_text(text):
        needle = normalize_text(text)
        catalog = catalog[
            catalog["project_name"].map(normalize_text).str.contains(
                needle,
                regex=False,
            )
        ]
    if technology_values:
        catalog = catalog[catalog["technology"].isin(technology_values)]
    territorial_ids = _territorial_project_ids(
        dataset.project_locations,
        autonomous_communities=community_values,
        provinces=province_values,
        municipalities=municipality_values,
    )
    if territorial_ids is not None:
        catalog = catalog[catalog["project_id"].astype(str).isin(territorial_ids)]
    event_ids = _event_project_ids(
        dataset.project_events,
        start_date=start_date,
        end_date=end_date,
        action_types=action_values,
        decisions=decision_values,
    )
    if event_ids is not None:
        catalog = catalog[catalog["project_id"].astype(str).isin(event_ids)]
    # Un proyecto puede coincidir con varias filas territoriales o de eventos,
    # pero aquí solo se filtra el catálogo maestro, que tiene una fila por
    # project_id. La copia evita modificar el dataset compartido.
    return catalog.reset_index(drop=True).copy()


def get_filter_options(
    dataset: GoldDataset,
    *,
    autonomous_communities: Iterable[str] | None = None,
    provinces: Iterable[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return deterministic filter values with territorial hierarchy applied."""

    locations = dataset.project_locations.copy()
    communities = _sorted_unique(locations["autonomous_community"])
    selected_communities = _selected(autonomous_communities)
    if selected_communities:
        locations = locations[
            locations["autonomous_community"].isin(selected_communities)
        ]
    province_options = _sorted_unique(locations["province"])
    selected_provinces = _selected(provinces)
    if selected_provinces:
        locations = locations[locations["province"].isin(selected_provinces)]
    # Las opciones siguen la jerarquía elegida por la usuaria y los municipios
    # salen solo de filas municipality. Las menciones menos precisas siguen
    # disponibles en provincia o comunidad, sin inventar un nivel inferior.
    municipalities = _sorted_unique(locations.loc[
        locations["location_level"] == "municipality", "municipality"
    ])
    events = dataset.project_events
    return {
        "technologies": _sorted_unique(dataset.projects["technology"]),
        "autonomous_communities": communities,
        "provinces": province_options,
        "municipalities": municipalities,
        "action_types": _sorted_unique(events["action_type"]),
        "decisions": _sorted_unique(events["decision"]),
    }


def get_project_detail(dataset: GoldDataset, project_id: str) -> pd.Series:
    """Return the complete canonical project row for an exact project ID."""

    rows = dataset.projects[dataset.projects["project_id"] == project_id]
    if len(rows) != 1:
        raise ProjectNotFoundError(project_id)
    return rows.iloc[0].copy()


def get_project_timeline(dataset: GoldDataset, project_id: str) -> pd.DataFrame:
    """Return all administrative actions for a project in contractual order."""

    get_project_detail(dataset, project_id)
    rows = dataset.project_events[
        dataset.project_events["project_id"] == project_id
    ].copy()
    # La cronología se ordena por publication_date, event_index y
    # administrative_action_index. administrative_action_id actúa como último
    # desempate para obtener siempre el mismo orden.
    return rows.sort_values(
        [
            "publication_date",
            "event_index",
            "administrative_action_index",
            "administrative_action_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def get_project_locations(dataset: GoldDataset, project_id: str) -> pd.DataFrame:
    """Return every contractual territory associated with one project."""

    get_project_detail(dataset, project_id)
    rows = dataset.project_locations[
        dataset.project_locations["project_id"] == project_id
    ].copy()
    level_order = {
        "municipality": 0,
        "province": 1,
        "autonomous_community": 2,
    }
    rows["_level_order"] = rows["location_level"].map(level_order).fillna(3)
    rows["_display_name"] = (
        rows["municipality"]
        .fillna(rows["province"])
        .fillna(rows["autonomous_community"])
        .fillna("")
    )
    rows = rows.sort_values(
        ["_level_order", "_display_name", "project_location_id"],
        key=lambda values: (
            values.map(normalize_text)
            if values.name == "_display_name"
            else values
        ),
        kind="stable",
    )
    return rows.drop(columns=["_level_order", "_display_name"]).reset_index(
        drop=True
    )


def get_project_location_sources(
    dataset: GoldDataset,
    project_id: str,
) -> pd.DataFrame:
    """Return exact BOE provenance rows for all locations of one project."""

    locations = get_project_locations(dataset, project_id)
    location_ids = set(locations["project_location_id"].astype(str))
    rows = dataset.project_location_sources[
        dataset.project_location_sources["project_location_id"]
        .astype(str)
        .isin(location_ids)
    ].copy()
    return rows.sort_values(
        ["publication_date", "boe_id", "project_location_id", "location_mention_id"],
        kind="stable",
    ).reset_index(drop=True)


def build_boe_url(boe_id: str) -> str:
    """Build a BOE public text URL after validating the contractual identifier."""

    if not isinstance(boe_id, str) or not _BOE_ID_RE.fullmatch(boe_id):
        raise ValueError("El identificador BOE no tiene el formato esperado.")
    return f"https://www.boe.es/diario_boe/txt.php?id={boe_id}"
