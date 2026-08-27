"""Pure application queries over the verified four-table Gold dataset."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

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
    "correccion_errores": "Corrección de errores",
    "declaracion_impacto_ambiental": "Declaración de impacto ambiental",
    "declaracion_utilidad_publica": "Declaración de utilidad pública",
    "evaluacion_impacto_ambiental": "Evaluación de impacto ambiental",
    "informe_determinacion_afeccion_ambiental": (
        "Informe de determinación de afección ambiental"
    ),
    "informe_impacto_ambiental": "Informe de impacto ambiental",
    "informacion_publica": "Información pública",
    "levantamiento_actas_previas_ocupacion": (
        "Levantamiento de actas previas a la ocupación"
    ),
    "modificacion_autorizacion": "Modificación de autorización",
    "otro": "Otra actuación",
    "solicitud_tramitacion": "Solicitud de tramitación",
    "solicitud_tramitacion_ambiental": "Solicitud de tramitación ambiental",
    "subsanacion_documentacion": "Subsanación de documentación",
    "terminacion_procedimiento": "Terminación del procedimiento",
}

DECISION_LABELS: Mapping[str, str] = {
    "archivado": "Archivado",
    "autorizado": "Autorizado",
    "convocado": "Convocado",
    "declarado": "Declarado",
    "denegado": "Denegado",
    "desestimado": "Desestimado",
    "desfavorable": "Desfavorable",
    "desistido": "Desistido",
    "formulado": "Formulado",
    "favorable": "Favorable",
    "modificado": "Modificado",
    "rectificado": "Rectificado",
    "requiere_evaluacion_ambiental_ordinaria": (
        "Requiere evaluación ambiental ordinaria"
    ),
    "sin_efectos_adversos_significativos": (
        "Sin efectos adversos significativos"
    ),
    "solicitado": "Solicitado",
    "sometido_informacion_publica": "Sometido a información pública",
    "subsanado": "Subsanado",
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
    "autonomous_communities",
    "provinces",
    "municipalities",
    "territorial_summary",
    "first_publication_date",
    "last_publication_date",
    "n_publications",
    "n_administrative_actions",
)
LATEST_TEMPORAL_INTERPRETATION = "latest"
HISTORICAL_TEMPORAL_INTERPRETATION = "historical"
ACTION_MATCH_ANY = "any"
ACTION_MATCH_ALL = "all"
MATCHING_ACTION_SUMMARY_COLUMNS = (
    "project_id",
    "matching_action_types",
)
_ACTION_ORDER_COLUMNS = (
    "publication_date",
    "event_index",
    "administrative_action_index",
    "administrative_action_id",
)
_LATEST_ACTION_COLUMNS = (
    "project_id",
    "action_type",
    *_ACTION_ORDER_COLUMNS,
)
_ADMINISTRATIVE_FILTER_COLUMNS = (
    *_LATEST_ACTION_COLUMNS,
    "decision",
)
TERRITORY_COUNT_COLUMNS = (
    "level",
    "code",
    "name",
    "autonomous_community_code",
    "province_code",
    "project_count",
)

_DISPLAY_TOKEN_CASE = {
    "BESS": "BESS",
    "FV": "FV",
    "HSF": "HSF",
    "KV": "kV",
    "KW": "kW",
    "LAAT": "LAAT",
    "LAT": "LAT",
    "MW": "MW",
    "MW/KV": "MW/kV",
    "MVA": "MVA",
    "PE": "PE",
    "PSFV": "PSFV",
    "SET": "SET",
}
_DISPLAY_GENERIC_WORDS = frozenset({
    "almacenamiento",
    "aérea",
    "central",
    "de",
    "del",
    "eléctrica",
    "eólica",
    "eólico",
    "fotovoltaica",
    "fotovoltaico",
    "hibridación",
    "huerta",
    "la",
    "las",
    "línea",
    "los",
    "parque",
    "planta",
    "proyecto",
    "sistema",
    "solar",
    "subestación",
    "y",
})
_ROMAN_NUMERAL_RE = re.compile(r"^[IVXLCDM]+$")


@dataclass(frozen=True)
class DashboardSelection:
    """Projects and exact BOE event rows supporting one filter selection."""

    projects: pd.DataFrame
    supporting_events: pd.DataFrame


@dataclass(frozen=True)
class DashboardMetrics:
    """The two approved primary metrics at their contractual grains."""

    projects: int
    relevant_boe_publications: int


@dataclass(frozen=True)
class ChartYearFilter:
    """Exact temporal predicates derived from one chart-year selection."""

    publication_years: tuple[int, ...]
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True)
class TimelineAction:
    """One traceable administrative action inside a publication group."""

    administrative_action_id: str
    action_type: str
    decision: str
    is_modification: bool
    evidence: str


@dataclass(frozen=True)
class PublicationTimelineGroup:
    """One BOE publication and its ordered actions for a project."""

    boe_id: str
    publication_date: pd.Timestamp
    actions: tuple[TimelineAction, ...]


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


def format_project_display_name(value: object) -> str:
    """Normalize a project name for display without changing its Gold value.

    Mixed-case official names are preserved apart from whitespace and their
    first letter. Fully uppercase names are converted conservatively: known
    generic terms become sentence case while acronyms, units, numbers and
    Roman numerals retain their contractual visual form.
    """

    if value is None or value is pd.NA:
        return ""
    text = " ".join(str(value).split())
    if not text:
        return ""
    fully_uppercase = any(character.isalpha() for character in text) and (
        text.upper() == text
    )
    rendered: list[str] = []
    for index, token in enumerate(text.split(" ")):
        canonical = _DISPLAY_TOKEN_CASE.get(token.upper())
        if canonical is not None:
            rendered.append(canonical)
        elif _ROMAN_NUMERAL_RE.fullmatch(token.upper()):
            rendered.append(token.upper())
        elif fully_uppercase and any(character.isalpha() for character in token):
            lowered = token.lower()
            if lowered in _DISPLAY_GENERIC_WORDS:
                rendered.append(lowered.capitalize() if index == 0 else lowered)
            else:
                rendered.append(lowered.capitalize())
        else:
            rendered.append(token)
    result = " ".join(rendered)
    return result[:1].upper() + result[1:]


def build_chart_year_filter(
    year: int | None,
    *,
    available_years: Iterable[int],
) -> ChartYearFilter:
    """Translate one chart selection into exact inclusive calendar predicates."""

    allowed = {int(value) for value in available_years}
    if year is None:
        return ChartYearFilter((), None, None)
    selected = int(year)
    if isinstance(year, bool) or selected not in allowed:
        raise ValueError("El año seleccionado no forma parte del corpus.")
    return ChartYearFilter(
        publication_years=(selected,),
        start_date=date(selected, 1, 1),
        end_date=date(selected, 12, 31),
    )


def extract_chart_selected_year(
    state: object,
    *,
    selection_name: str,
    available_years: Iterable[int],
) -> int | None:
    """Read one explicit Vega point selection without trusting arbitrary state."""

    selected = extract_chart_selected_values(
        state,
        selection_name=selection_name,
        fields=("publication_year",),
    )
    if selected is None:
        return None
    candidate = selected["publication_year"]
    if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
        return None
    year = int(candidate)
    if float(candidate) != year or year not in {int(value) for value in available_years}:
        return None
    return year


def extract_chart_selected_values(
    state: object,
    *,
    selection_name: str,
    fields: tuple[str, ...],
) -> dict[str, object] | None:
    """Read one bounded Vega point selection for named fields.

    Streamlit has represented a single Vega point both as a mapping and as a
    one-item list across releases. This parser accepts those public shapes and
    rejects composite or nested values rather than trusting session state.
    """

    if not fields or len(set(fields)) != len(fields):
        raise ValueError("La selección requiere campos únicos.")
    if not isinstance(state, Mapping):
        return None
    selections = state.get("selection")
    if not isinstance(selections, Mapping):
        return None
    raw = selections.get(selection_name)
    if isinstance(raw, Mapping):
        item = raw
    elif isinstance(raw, (list, tuple)) and len(raw) == 1:
        item = raw[0]
    else:
        return None
    if not isinstance(item, Mapping):
        return None
    output: dict[str, object] = {}
    for field in fields:
        candidate = item.get(field)
        if isinstance(candidate, (list, tuple)) and len(candidate) == 1:
            candidate = candidate[0]
        if candidate is None or isinstance(candidate, (Mapping, list, tuple)):
            return None
        if not isinstance(candidate, (str, int, float)) or isinstance(
            candidate, bool
        ):
            return None
        output[field] = candidate
    return output


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


def _catalog_territories(locations: pd.DataFrame) -> dict[str, str]:
    """Build compact values for each visible territorial catalogue column."""

    return {
        "autonomous_communities": _short_list(
            locations["autonomous_community"]
        ),
        "provinces": _short_list(locations["province"]),
        "municipalities": _short_list(locations.loc[
            locations["location_level"] == "municipality",
            "municipality",
        ]),
        "territorial_summary": _territorial_summary(locations),
    }


def build_project_catalog(dataset: GoldDataset) -> pd.DataFrame:
    """Return one deterministic catalogue row for every canonical project."""

    summaries = {
        project_id: _catalog_territories(group)
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
    for offset, column in enumerate(
        (
            "autonomous_communities",
            "provinces",
            "municipalities",
            "territorial_summary",
        )
    ):
        values = catalog["project_id"].astype(str).map(
            lambda project_id: summaries.get(project_id, {}).get(column, "")
        )
        catalog.insert(3 + offset, column, values.astype("string"))
    return catalog.loc[:, CATALOG_COLUMNS].sort_values(
        ["project_name", "project_id"],
        key=lambda values: values.map(normalize_text),
        kind="stable",
    ).reset_index(drop=True)


def build_catalog_interaction_context(
    dataset: GoldDataset,
    project_ids: Iterable[str],
) -> list[dict[str, object]]:
    """Return structured filter identities aligned with catalogue row order.

    Display strings may be abbreviated, so interactive filtering is derived
    directly from contractual Gold locations and never parsed back from the
    rendered catalogue.
    """

    ordered_ids = tuple(str(value) for value in project_ids)
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError("El contexto del catálogo requiere project_id únicos.")
    projects = dataset.projects.set_index("project_id", drop=False)
    missing = [
        project_id
        for project_id in ordered_ids
        if project_id not in projects.index
    ]
    if missing:
        raise ValueError(
            "El contexto del catálogo contiene project_id inexistentes: "
            f"{missing!r}."
        )
    locations = dataset.project_locations
    records: list[dict[str, object]] = []
    for project_id in ordered_ids:
        project_locations = locations[
            locations["project_id"].astype(str).eq(project_id)
        ]
        province_rows = project_locations[project_locations["province"].notna()]
        municipality_rows = project_locations[
            project_locations["location_level"].eq("municipality")
            & project_locations["municipality"].notna()
        ]
        records.append({
            "project_id": project_id,
            "technology": str(projects.loc[project_id, "technology"]),
            "autonomous_communities": _sorted_unique(
                project_locations["autonomous_community"]
            ),
            "provinces": _sorted_unique(province_rows["province"]),
            "province_communities": _sorted_unique(
                province_rows["autonomous_community"]
            ),
            "municipalities": _sorted_unique(
                municipality_rows["municipality"]
            ),
            "municipality_provinces": _sorted_unique(
                municipality_rows["province"]
            ),
            "municipality_communities": _sorted_unique(
                municipality_rows["autonomous_community"]
            ),
        })
    return records


def _selected(values: Iterable[str] | None) -> tuple[str, ...]:
    """Normalize an optional filter selection into an immutable tuple."""

    return tuple(values or ())


def _unique_selected(values: Iterable[str] | None) -> tuple[str, ...]:
    """Return selected canonical values once while preserving caller order."""

    return tuple(dict.fromkeys(_selected(values)))


def _require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    query_name: str,
) -> None:
    """Fail explicitly when a pure query lacks one of its required columns."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{query_name} requiere un DataFrame de pandas.")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(
            f"{query_name} requiere las columnas: {', '.join(missing)}."
        )


def build_latest_project_actions(project_events: pd.DataFrame) -> pd.DataFrame:
    """Return the latest published row for each project and action type.

    The selection follows publication date, event index, action index and
    administrative action ID as the final deterministic tiebreaker.
    """

    _require_columns(
        project_events,
        _LATEST_ACTION_COLUMNS,
        query_name="build_latest_project_actions",
    )
    ordered = project_events.copy().sort_values(
        list(_ACTION_ORDER_COLUMNS),
        kind="stable",
    )
    latest = ordered.drop_duplicates(
        ["project_id", "action_type"],
        keep="last",
    )
    # Esta derivación describe la última publicación conocida para cada tipo de
    # trámite del proyecto; por sí sola no es un estado jurídico consolidado.
    return latest.sort_values(
        ["project_id", "action_type", *_ACTION_ORDER_COLUMNS],
        kind="stable",
    ).reset_index(drop=True).copy()


def _validate_administrative_modes(
    *,
    temporal_interpretation: str,
    action_match: str,
) -> None:
    """Validate the two closed presentation-query modes."""

    if temporal_interpretation not in {
        LATEST_TEMPORAL_INTERPRETATION,
        HISTORICAL_TEMPORAL_INTERPRETATION,
    }:
        raise ValueError("La interpretación temporal no es válida.")
    if action_match not in {ACTION_MATCH_ANY, ACTION_MATCH_ALL}:
        raise ValueError("La coincidencia de trámites no es válida.")


def _filtered_administrative_rows(
    project_events: pd.DataFrame,
    *,
    temporal_interpretation: str,
    start_date: date | datetime | pd.Timestamp | None,
    end_date: date | datetime | pd.Timestamp | None,
    publication_years: tuple[int, ...],
    action_types: tuple[str, ...],
    decisions: tuple[str, ...],
) -> pd.DataFrame:
    """Apply all administrative predicates to one shared set of event rows."""

    _require_columns(
        project_events,
        _ADMINISTRATIVE_FILTER_COLUMNS,
        query_name="filtrado administrativo",
    )
    rows = (
        build_latest_project_actions(project_events)
        if temporal_interpretation == LATEST_TEMPORAL_INTERPRETATION
        else project_events.copy()
    )
    if start_date is not None:
        rows = rows[rows["publication_date"].ge(pd.Timestamp(start_date))]
    if end_date is not None:
        rows = rows[rows["publication_date"].le(pd.Timestamp(end_date))]
    if publication_years:
        rows = rows[rows["publication_date"].dt.year.isin(publication_years)]
    if action_types:
        rows = rows[rows["action_type"].isin(action_types)]
    if decisions:
        rows = rows[rows["decision"].isin(decisions)]
    return rows.sort_values(
        ["project_id", *_ACTION_ORDER_COLUMNS],
        kind="stable",
    ).reset_index(drop=True).copy()


def build_matching_action_summary(
    project_events: pd.DataFrame,
    *,
    temporal_interpretation: str = LATEST_TEMPORAL_INTERPRETATION,
    start_date: date | datetime | pd.Timestamp | None = None,
    end_date: date | datetime | pd.Timestamp | None = None,
    publication_years: Iterable[int] | None = None,
    action_types: Iterable[str] | None = None,
    decisions: Iterable[str] | None = None,
    action_match: str = ACTION_MATCH_ANY,
) -> pd.DataFrame:
    """Summarize matching action types for projects passing event predicates."""

    _validate_administrative_modes(
        temporal_interpretation=temporal_interpretation,
        action_match=action_match,
    )
    action_values = _unique_selected(action_types)
    decision_values = _unique_selected(decisions)
    year_values = tuple(
        dict.fromkeys(int(value) for value in (publication_years or ()))
    )
    rows = _filtered_administrative_rows(
        project_events,
        temporal_interpretation=temporal_interpretation,
        start_date=start_date,
        end_date=end_date,
        publication_years=year_values,
        action_types=action_values,
        decisions=decision_values,
    )
    if action_match == ACTION_MATCH_ALL and len(action_values) >= 2:
        required = set(action_values)
        eligible = {
            str(project_id)
            for project_id, group in rows.groupby("project_id", sort=False)
            if required <= set(group["action_type"].astype(str))
        }
        rows = rows[rows["project_id"].astype(str).isin(eligible)]
    records = [
        {
            "project_id": str(project_id),
            "matching_action_types": tuple(
                dict.fromkeys(group["action_type"].astype(str))
            ),
        }
        for project_id, group in rows.groupby("project_id", sort=False)
    ]
    return pd.DataFrame.from_records(
        records,
        columns=MATCHING_ACTION_SUMMARY_COLUMNS,
    ).sort_values("project_id", kind="stable").reset_index(drop=True).copy()


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
    publication_years: Iterable[int] | None = None,
    action_types: Iterable[str] | None = None,
    decisions: Iterable[str] | None = None,
    temporal_interpretation: str = LATEST_TEMPORAL_INTERPRETATION,
    action_match: str = ACTION_MATCH_ANY,
) -> pd.DataFrame:
    """Filter projects with OR within and AND across catalogue categories."""

    _validate_administrative_modes(
        temporal_interpretation=temporal_interpretation,
        action_match=action_match,
    )
    technology_values = _selected(technologies)
    community_values = _selected(autonomous_communities)
    province_values = _selected(provinces)
    municipality_values = _selected(municipalities)
    action_values = _unique_selected(action_types)
    decision_values = _unique_selected(decisions)
    year_values = tuple(
        dict.fromkeys(int(value) for value in (publication_years or ()))
    )
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
    administrative_filters_active = bool(
        start_date is not None
        or end_date is not None
        or year_values
        or action_values
        or decision_values
    )
    if administrative_filters_active:
        matching = build_matching_action_summary(
            dataset.project_events,
            temporal_interpretation=temporal_interpretation,
            start_date=start_date,
            end_date=end_date,
            publication_years=year_values,
            action_types=action_values,
            decisions=decision_values,
            action_match=action_match,
        )
        catalog = catalog.merge(
            matching,
            on="project_id",
            how="inner",
            sort=False,
            validate="one_to_one",
        )
    # Un proyecto puede coincidir con varias filas territoriales o de eventos,
    # pero aquí solo se filtra el catálogo maestro, que tiene una fila por
    # project_id. La copia evita modificar el dataset compartido.
    return catalog.reset_index(drop=True).copy()


def build_dashboard_selection(
    dataset: GoldDataset,
    *,
    text: str = "",
    technologies: Iterable[str] | None = None,
    autonomous_communities: Iterable[str] | None = None,
    provinces: Iterable[str] | None = None,
    municipalities: Iterable[str] | None = None,
    start_date: date | datetime | pd.Timestamp | None = None,
    end_date: date | datetime | pd.Timestamp | None = None,
    publication_years: Iterable[int] | None = None,
    action_types: Iterable[str] | None = None,
    decisions: Iterable[str] | None = None,
    temporal_interpretation: str = LATEST_TEMPORAL_INTERPRETATION,
    action_match: str = ACTION_MATCH_ANY,
) -> DashboardSelection:
    """Return eligible projects and the exact BOE rows supporting them."""

    years = tuple(
        dict.fromkeys(int(value) for value in (publication_years or ()))
    )
    actions = _unique_selected(action_types)
    decision_values = _unique_selected(decisions)
    projects = filter_projects(
        dataset,
        text=text,
        technologies=technologies,
        autonomous_communities=autonomous_communities,
        provinces=provinces,
        municipalities=municipalities,
        start_date=start_date,
        end_date=end_date,
        publication_years=years,
        action_types=actions,
        decisions=decision_values,
        temporal_interpretation=temporal_interpretation,
        action_match=action_match,
    )
    administrative_filters_active = bool(
        start_date is not None
        or end_date is not None
        or years
        or actions
        or decision_values
    )
    if administrative_filters_active:
        supporting = _filtered_administrative_rows(
            dataset.project_events,
            temporal_interpretation=temporal_interpretation,
            start_date=start_date,
            end_date=end_date,
            publication_years=years,
            action_types=actions,
            decisions=decision_values,
        )
    else:
        supporting = dataset.project_events.copy()
    project_ids = set(projects["project_id"].astype(str))
    supporting = supporting[
        supporting["project_id"].astype(str).isin(project_ids)
    ].sort_values(
        ["publication_date", "boe_id", "project_id", *_ACTION_ORDER_COLUMNS[1:]],
        kind="stable",
    ).reset_index(drop=True).copy()
    return DashboardSelection(projects=projects.copy(), supporting_events=supporting)


def summarize_dashboard_selection(
    selection: DashboardSelection,
) -> DashboardMetrics:
    """Calculate the two approved KPIs without using event-row counts."""

    return DashboardMetrics(
        projects=int(selection.projects["project_id"].nunique()),
        relevant_boe_publications=int(
            selection.supporting_events["boe_id"].nunique()
        ),
    )


def build_publication_counts(project_events: pd.DataFrame) -> pd.DataFrame:
    """Count distinct supporting BOE publications by observed publication year."""

    _require_columns(
        project_events,
        ("boe_id", "publication_date"),
        query_name="build_publication_counts",
    )
    publications = project_events.loc[
        :, ["boe_id", "publication_date"]
    ].drop_duplicates()
    conflicting = publications.groupby("boe_id")["publication_date"].nunique().gt(1)
    if conflicting.any():
        raise ValueError("Un BOE aparece con más de una fecha de publicación.")
    publications = publications.drop_duplicates("boe_id", keep="first").copy()
    if publications.empty:
        return pd.DataFrame({
            "publication_year": pd.Series(dtype="Int64"),
            "boe_publications": pd.Series(dtype="Int64"),
        })
    publications["publication_year"] = publications["publication_date"].dt.year
    counts = (
        publications.groupby("publication_year", sort=True)["boe_id"]
        .nunique()
        .rename("boe_publications")
        .reset_index()
    )
    return counts.astype({
        "publication_year": "Int64",
        "boe_publications": "Int64",
    })


def build_yearly_project_counts(project_events: pd.DataFrame) -> pd.DataFrame:
    """Count distinct projects with at least one observed publication by year."""

    _require_columns(
        project_events,
        ("project_id", "publication_date"),
        query_name="build_yearly_project_counts",
    )
    rows = project_events.loc[:, ["project_id", "publication_date"]].copy()
    if rows.empty:
        return pd.DataFrame({
            "publication_year": pd.Series(dtype="Int64"),
            "projects": pd.Series(dtype="Int64"),
        })
    rows["publication_year"] = rows["publication_date"].dt.year
    counts = (
        rows.groupby("publication_year", sort=True)["project_id"]
        .nunique()
        .rename("projects")
        .reset_index()
    )
    return counts.astype({
        "publication_year": "Int64",
        "projects": "Int64",
    })


def build_project_publication_summary(
    project_events: pd.DataFrame,
    project_location_sources: pd.DataFrame,
) -> pd.DataFrame:
    """List each BOE once with its distinct project-action count."""

    _require_columns(
        project_events,
        ("boe_id", "publication_date", "administrative_action_id"),
        query_name="build_project_publication_summary",
    )
    _require_columns(
        project_location_sources,
        ("boe_id", "publication_date"),
        query_name="build_project_publication_summary",
    )
    action_rows = project_events.loc[
        :, ["boe_id", "publication_date", "administrative_action_id"]
    ].copy()
    action_counts = (
        action_rows.groupby(["boe_id", "publication_date"], sort=False)[
            "administrative_action_id"
        ]
        .nunique()
        .rename("administrative_actions")
        .reset_index()
    )
    publication_rows = pd.concat(
        [
            action_rows.loc[:, ["boe_id", "publication_date"]],
            project_location_sources.loc[:, ["boe_id", "publication_date"]],
        ],
        ignore_index=True,
    ).drop_duplicates()
    conflicting = publication_rows.groupby("boe_id")[
        "publication_date"
    ].nunique().gt(1)
    if conflicting.any():
        raise ValueError("Un BOE aparece con más de una fecha de publicación.")
    publications = publication_rows.drop_duplicates("boe_id", keep="first")
    result = publications.merge(
        action_counts,
        on=["boe_id", "publication_date"],
        how="left",
        sort=False,
        validate="one_to_one",
    )
    result["administrative_actions"] = result[
        "administrative_actions"
    ].fillna(0).astype("Int64")
    return result.loc[
        :, ["publication_date", "boe_id", "administrative_actions"]
    ].sort_values(
        ["publication_date", "boe_id"],
        kind="stable",
    ).reset_index(drop=True).copy()


def group_project_timeline_by_publication(
    project_events: pd.DataFrame,
) -> tuple[PublicationTimelineGroup, ...]:
    """Group a project chronology newest-first without repeating BOE headers."""

    required = (
        "boe_id",
        "publication_date",
        "administrative_action_id",
        "action_type",
        "decision",
        "is_modification",
        "evidence",
        *_ACTION_ORDER_COLUMNS[1:],
    )
    _require_columns(
        project_events,
        required,
        query_name="group_project_timeline_by_publication",
    )
    ordered = project_events.sort_values(
        ["publication_date", "boe_id", *_ACTION_ORDER_COLUMNS[1:]],
        ascending=[False, True, True, True, True],
        kind="stable",
    )
    conflicting = ordered.groupby("boe_id")["publication_date"].nunique().gt(1)
    if conflicting.any():
        raise ValueError("Un BOE aparece con más de una fecha de publicación.")
    groups: list[PublicationTimelineGroup] = []
    for (publication_date, boe_id), rows in ordered.groupby(
        ["publication_date", "boe_id"],
        sort=False,
    ):
        actions = tuple(
            TimelineAction(
                administrative_action_id=str(row.administrative_action_id),
                action_type=str(row.action_type),
                decision=str(row.decision),
                is_modification=bool(row.is_modification),
                evidence=str(row.evidence),
            )
            for row in rows.itertuples(index=False)
        )
        groups.append(PublicationTimelineGroup(
            boe_id=str(boe_id),
            publication_date=pd.Timestamp(publication_date),
            actions=actions,
        ))
    return tuple(groups)


def build_administrative_situation_counts(
    project_events: pd.DataFrame,
    *,
    temporal_interpretation: str = LATEST_TEMPORAL_INTERPRETATION,
) -> pd.DataFrame:
    """Count projects by action type and observed published situation."""

    _validate_administrative_modes(
        temporal_interpretation=temporal_interpretation,
        action_match=ACTION_MATCH_ANY,
    )
    _require_columns(
        project_events,
        ("project_id", "action_type", "decision", *_ACTION_ORDER_COLUMNS),
        query_name="build_administrative_situation_counts",
    )
    if temporal_interpretation == LATEST_TEMPORAL_INTERPRETATION:
        rows = build_latest_project_actions(project_events)
    else:
        rows = project_events.copy().drop_duplicates(
            ["project_id", "action_type", "decision"]
        )
    if rows.empty:
        return pd.DataFrame({
            "action_type": pd.Series(dtype="string"),
            "decision": pd.Series(dtype="string"),
            "project_count": pd.Series(dtype="Int64"),
        })
    counts = (
        rows.groupby(["action_type", "decision"], sort=True)["project_id"]
        .nunique()
        .rename("project_count")
        .reset_index()
    )
    return counts.astype({
        "action_type": "string",
        "decision": "string",
        "project_count": "Int64",
    })


def build_territory_project_counts(
    project_locations: pd.DataFrame,
    *,
    project_ids: Iterable[str],
    level: str,
) -> pd.DataFrame:
    """Count distinct projects per administrative code at one map level."""

    level_columns = {
        "autonomous_community": (
            "ine_autonomous_community_code",
            "autonomous_community",
        ),
        "province": ("ine_province_code", "province"),
        "municipality": ("ine_municipality_code", "municipality"),
    }
    if level not in level_columns:
        raise ValueError("El nivel territorial no es válido.")
    code_column, name_column = level_columns[level]
    required = (
        "project_id",
        "location_level",
        code_column,
        name_column,
        "ine_autonomous_community_code",
        "ine_province_code",
    )
    _require_columns(
        project_locations,
        required,
        query_name="build_territory_project_counts",
    )
    selected = set(str(value) for value in project_ids)
    rows = project_locations[
        project_locations["project_id"].astype(str).isin(selected)
    ].copy()
    if level == "municipality":
        rows = rows[rows["location_level"] == "municipality"]
    rows = rows[rows[code_column].notna() & rows[name_column].notna()].copy()
    if rows.empty:
        return pd.DataFrame({
            "level": pd.Series(dtype="string"),
            "code": pd.Series(dtype="string"),
            "name": pd.Series(dtype="string"),
            "autonomous_community_code": pd.Series(dtype="string"),
            "province_code": pd.Series(dtype="string"),
            "project_count": pd.Series(dtype="Int64"),
        })
    rows["code"] = rows[code_column].astype("string")
    rows["name"] = rows[name_column].astype("string")
    for code, group in rows.groupby("code", sort=False):
        if group["name"].nunique(dropna=True) != 1:
            raise ValueError(f"El código territorial {code!r} tiene varios nombres.")
    rows["autonomous_community_code"] = rows[
        "ine_autonomous_community_code"
    ].astype("string")
    rows["province_code"] = rows["ine_province_code"].astype("string")
    if level == "autonomous_community":
        rows["autonomous_community_code"] = rows["code"]
        rows["province_code"] = pd.NA
    elif level == "province":
        rows["province_code"] = rows["code"]
    parent_columns = ["autonomous_community_code", "province_code"]
    for code, group in rows.groupby("code", sort=False):
        if any(
            group[column].nunique(dropna=True) > 1
            for column in parent_columns
        ):
            raise ValueError(
                f"El código territorial {code!r} tiene padres incoherentes."
            )
    unique = rows.drop_duplicates(["project_id", "code"])
    records = []
    for code, group in unique.groupby("code", sort=True):
        records.append({
            "level": level,
            "code": str(code),
            "name": str(group["name"].iloc[0]),
            "autonomous_community_code": group[
                "autonomous_community_code"
            ].dropna().iloc[0]
            if group["autonomous_community_code"].notna().any()
            else pd.NA,
            "province_code": group["province_code"].dropna().iloc[0]
            if group["province_code"].notna().any()
            else pd.NA,
            "project_count": int(group["project_id"].nunique()),
        })
    return pd.DataFrame.from_records(
        records,
        columns=TERRITORY_COUNT_COLUMNS,
    ).astype({
        "level": "string",
        "code": "string",
        "name": "string",
        "autonomous_community_code": "string",
        "province_code": "string",
        "project_count": "Int64",
    })


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
        "publication_years": tuple(
            sorted(
                int(value)
                for value in events["publication_date"].dt.year.unique()
            )
        ),
    }


def get_project_detail(dataset: GoldDataset, project_id: str) -> pd.Series:
    """Return the complete canonical project row for an exact project ID."""

    rows = dataset.projects[dataset.projects["project_id"] == project_id]
    if len(rows) != 1:
        raise ProjectNotFoundError(project_id)
    return rows.iloc[0].copy()


def get_project_timeline(dataset: GoldDataset, project_id: str) -> pd.DataFrame:
    """Return all project actions from newest to oldest publication."""

    get_project_detail(dataset, project_id)
    rows = dataset.project_events[
        dataset.project_events["project_id"] == project_id
    ].copy()
    # La fecha es descendente para lectura operativa. Dentro de una misma
    # publicación se conservan event_index, administrative_action_index e ID en
    # orden ascendente como desempates deterministas.
    return rows.sort_values(
        [
            "publication_date",
            "event_index",
            "administrative_action_index",
            "administrative_action_id",
        ],
        ascending=[False, True, True, True],
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
