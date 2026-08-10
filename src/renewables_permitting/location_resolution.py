from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from renewables_permitting.text_matching import text_tokens
from renewables_permitting.utils import (
    is_null_like,
    normalize_text_or_none,
    validate_required_columns,
)


class AdministrativeUnitResolutionStatus(str, Enum):
    """Resultado independiente de resolver una unidad administrativa."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    NOT_PROVIDED = "not_provided"
    CONFLICT = "conflict"


class LocationResolutionStatus(str, Enum):
    """Completitud agregada de los tres niveles administrativos."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    NOT_PROVIDED = "not_provided"
    CONFLICT = "conflict"


LOCATION_RESOLUTION_COLUMNS = (
    "municipality",
    "municipality_norm",
    "ine_municipality_code",
    "municipality_resolution_status",
    "municipality_resolution_matched_by",
    "municipality_resolution_reason",
    "province",
    "province_norm",
    "ine_province_code",
    "province_resolution_status",
    "province_resolution_matched_by",
    "province_resolution_reason",
    "autonomous_community",
    "autonomous_community_norm",
    "ine_autonomous_community_code",
    "autonomous_community_resolution_status",
    "autonomous_community_resolution_matched_by",
    "autonomous_community_resolution_reason",
    "location_resolution_status",
    "location_resolution_level",
)


_INPUT_COLUMNS = {
    "event_id",
    "identificador_boe",
    "fecha_publicacion",
    "location_mention_id",
    "location_name_raw",
    "location_level",
    "province_hint_raw",
    "autonomous_community_hint_raw",
    "evidence",
}

_DIMENSION_COLUMNS = {
    "cauto",
    "cpro",
    "cmun",
    "municipio",
    "municipio_norm",
    "municipio_lookup_names_norm",
    "provincia",
    "provincia_norm",
    "comunidad_autonoma",
    "comunidad_autonoma_norm",
    "ine_municipality_code",
    "ine_province_code",
    "ine_autonomous_community_code",
}

_LEVEL_MUNICIPALITY = "municipio"
_LEVEL_PROVINCE = "provincia"
_LEVEL_AUTONOMOUS_COMMUNITY = "comunidad_autonoma"
_VALID_LEVELS = {
    _LEVEL_MUNICIPALITY,
    _LEVEL_PROVINCE,
    _LEVEL_AUTONOMOUS_COMMUNITY,
}

_ADMINISTRATIVE_NAME_STOP_TOKENS = {
    "autonoma",
    "autonomo",
    "comunidad",
    "comunitat",
    "de",
    "del",
    "e",
    "el",
    "la",
    "las",
    "los",
    "principado",
    "region",
    "y",
}

_PROVINCE_ALIASES_BY_CODE = {
    "01": {"alava", "araba"},
    "03": {"alicante", "alacant"},
    "07": {"illes balears", "islas baleares", "baleares"},
    "12": {"castellon", "castello"},
    "15": {"a coruna", "la coruna", "coruna"},
    "17": {"girona", "gerona"},
    "20": {"gipuzkoa", "guipuzcoa"},
    "26": {"la rioja", "rioja"},
    "35": {"las palmas", "palmas"},
    "46": {"valencia"},
    "48": {"bizkaia", "vizcaya"},
}

_AUTONOMOUS_COMMUNITY_ALIASES_BY_CODE = {
    "03": {"asturias", "principado de asturias"},
    "04": {"illes balears", "islas baleares", "baleares"},
    "09": {"cataluna", "catalunya"},
    "10": {"comunitat valenciana", "comunidad valenciana"},
    "13": {"madrid", "comunidad de madrid"},
    "14": {"murcia", "region de murcia"},
    "15": {"navarra", "comunidad foral de navarra"},
    "16": {"pais vasco", "euskadi"},
    "17": {"la rioja", "rioja"},
}


@dataclass(frozen=True)
class _LookupResult:
    status: AdministrativeUnitResolutionStatus
    row: pd.Series | None
    matched_by: str | None
    reason: str


def _coerce_lookup_names(value: Any) -> list[Any]:
    if is_null_like(value):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if hasattr(value, "tolist"):
        converted = value.tolist()
        return converted if isinstance(converted, list) else [converted]
    return [value]


def _normalized_variants(value: Any, aliases: set[str] | None = None) -> list[str]:
    if is_null_like(value):
        return []
    raw = str(value).strip()
    variants = {raw, *(aliases or set())}
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) == 2:
        variants.add(f"{parts[1]} {parts[0]}")
    for current in list(variants):
        variants.update(part.strip() for part in current.split("/") if part.strip())
    normalized = {normalize_text_or_none(item) for item in variants}
    return sorted(item for item in normalized if item is not None)


def _lookup_names_contain(value: Any, query_norm: str) -> bool:
    return query_norm in {
        normalized
        for item in _coerce_lookup_names(value)
        if (normalized := normalize_text_or_none(item)) is not None
    }


def _lookup_names_token_match(value: Any, query: Any) -> bool:
    query_tokens = text_tokens(
        query,
        stop_tokens=_ADMINISTRATIVE_NAME_STOP_TOKENS,
    )
    if not query_tokens:
        return False
    return any(
        query_tokens
        == text_tokens(
            candidate,
            stop_tokens=_ADMINISTRATIVE_NAME_STOP_TOKENS,
        )
        for candidate in _coerce_lookup_names(value)
    )


def _validate_input(location_mentions: pd.DataFrame) -> None:
    if location_mentions.columns.duplicated().any():
        duplicates = location_mentions.columns[
            location_mentions.columns.duplicated(keep=False)
        ].tolist()
        raise ValueError(f"location_mentions contiene columnas duplicadas: {duplicates}")
    validate_required_columns(location_mentions, _INPUT_COLUMNS)
    if location_mentions["location_mention_id"].isna().any():
        raise ValueError("location_mention_id no puede contener nulos.")
    if location_mentions["location_mention_id"].duplicated().any():
        raise ValueError("location_mention_id debe ser único.")
    invalid_levels = set(
        location_mentions["location_level"].dropna().astype(str)
    ) - _VALID_LEVELS
    if invalid_levels or location_mentions["location_level"].isna().any():
        raise ValueError(
            "location_level contiene valores no válidos: "
            f"{sorted(invalid_levels)}"
        )


def _prepare_dimension(municipality_dimension: pd.DataFrame) -> pd.DataFrame:
    if municipality_dimension.columns.duplicated().any():
        raise ValueError("La dimensión INE contiene columnas duplicadas.")
    validate_required_columns(municipality_dimension, _DIMENSION_COLUMNS)
    dimension = municipality_dimension.copy(deep=True)
    code_widths = {
        "cauto": 2,
        "cpro": 2,
        "cmun": 3,
        "ine_municipality_code": 5,
        "ine_province_code": 2,
        "ine_autonomous_community_code": 2,
    }
    for column, width in code_widths.items():
        values = dimension[column].astype("string").str.strip()
        invalid = values.isna() | ~values.str.fullmatch(r"\d+")
        if invalid.any() or values.str.len().gt(width).any():
            raise ValueError(f"{column} contiene códigos INE no válidos.")
        dimension[column] = values.str.zfill(width)

    expected_municipality_code = dimension["cpro"] + dimension["cmun"]
    inconsistent = (
        dimension["ine_municipality_code"] != expected_municipality_code
    ) | (dimension["ine_province_code"] != dimension["cpro"]) | (
        dimension["ine_autonomous_community_code"] != dimension["cauto"]
    )
    if inconsistent.any():
        raise ValueError("La dimensión INE contiene códigos jerárquicos incoherentes.")
    if dimension.duplicated(["cauto", "cpro", "cmun"]).any():
        raise ValueError("La dimensión INE contiene municipios duplicados.")
    if dimension["ine_municipality_code"].duplicated().any():
        raise ValueError("ine_municipality_code debe ser único.")

    structural = [
        "municipio",
        "provincia",
        "comunidad_autonoma",
        "municipio_norm",
        "provincia_norm",
        "comunidad_autonoma_norm",
    ]
    if dimension[structural].isna().any().any():
        raise ValueError("La dimensión INE contiene nombres estructurales nulos.")

    return dimension.sort_values(
        ["ine_autonomous_community_code", "ine_province_code", "ine_municipality_code"],
        kind="stable",
    ).reset_index(drop=True)


def _province_dimension(dimension: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "cauto",
        "cpro",
        "provincia",
        "provincia_norm",
        "comunidad_autonoma",
        "comunidad_autonoma_norm",
        "ine_province_code",
        "ine_autonomous_community_code",
    ]
    provinces = dimension[columns].drop_duplicates().sort_values(
        "ine_province_code", kind="stable"
    )
    if provinces["ine_province_code"].duplicated().any():
        raise ValueError("Un código de provincia identifica varias jerarquías INE.")
    provinces = provinces.reset_index(drop=True)
    provinces["lookup_names_norm"] = provinces.apply(
        lambda row: _normalized_variants(
            row["provincia"],
            _PROVINCE_ALIASES_BY_CODE.get(row["ine_province_code"], set()),
        ),
        axis=1,
    )
    return provinces


def _autonomous_community_dimension(dimension: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "cauto",
        "comunidad_autonoma",
        "comunidad_autonoma_norm",
        "ine_autonomous_community_code",
    ]
    communities = dimension[columns].drop_duplicates().sort_values(
        "ine_autonomous_community_code", kind="stable"
    )
    if communities["ine_autonomous_community_code"].duplicated().any():
        raise ValueError("Un código autonómico identifica varias unidades INE.")
    communities = communities.reset_index(drop=True)
    communities["lookup_names_norm"] = communities.apply(
        lambda row: _normalized_variants(
            row["comunidad_autonoma"],
            _AUTONOMOUS_COMMUNITY_ALIASES_BY_CODE.get(
                row["ine_autonomous_community_code"], set()
            ),
        ),
        axis=1,
    )
    return communities


def _empty_lookup(unit: str, provided: bool) -> _LookupResult:
    if provided:
        return _LookupResult(
            AdministrativeUnitResolutionStatus.NOT_FOUND,
            None,
            "not_found",
            f"No se encontró una coincidencia de {unit} en la dimensión INE.",
        )
    return _LookupResult(
        AdministrativeUnitResolutionStatus.NOT_PROVIDED,
        None,
        None,
        f"No se proporcionó {unit}.",
    )


def _build_lookup(
    matches: pd.DataFrame,
    *,
    unit: str,
    matched_by: str,
    unique_code: str,
) -> _LookupResult:
    matches = matches.drop_duplicates(unique_code).sort_values(
        unique_code, kind="stable"
    )
    if len(matches) == 1:
        return _LookupResult(
            AdministrativeUnitResolutionStatus.RESOLVED,
            matches.iloc[0],
            matched_by,
            f"Coincidencia de {unit} resuelta por nombre o alias normalizado.",
        )
    return _LookupResult(
        AdministrativeUnitResolutionStatus.AMBIGUOUS,
        None,
        f"{matched_by}_ambiguous",
        f"La mención coincide con varias unidades de {unit}.",
    )


def _resolve_province(query: Any, provinces: pd.DataFrame) -> _LookupResult:
    query_norm = normalize_text_or_none(query)
    if query_norm is None:
        return _empty_lookup("una provincia", False)
    matches = provinces.loc[
        provinces["lookup_names_norm"].map(
            lambda names: _lookup_names_contain(names, query_norm)
        )
    ]
    matched_by = "province_name"
    if matches.empty:
        matches = provinces.loc[
            provinces["lookup_names_norm"].map(
                lambda names: _lookup_names_token_match(names, query)
            )
        ]
        matched_by = "province_name_tokens"
    if matches.empty:
        return _empty_lookup("provincia", True)
    return _build_lookup(
        matches,
        unit="provincia",
        matched_by=matched_by,
        unique_code="ine_province_code",
    )


def _resolve_autonomous_community(
    query: Any,
    communities: pd.DataFrame,
) -> _LookupResult:
    query_norm = normalize_text_or_none(query)
    if query_norm is None:
        return _empty_lookup("una comunidad autónoma", False)
    matches = communities.loc[
        communities["lookup_names_norm"].map(
            lambda names: _lookup_names_contain(names, query_norm)
        )
    ]
    matched_by = "autonomous_community_name"
    if matches.empty:
        matches = communities.loc[
            communities["lookup_names_norm"].map(
                lambda names: _lookup_names_token_match(names, query)
            )
        ]
        matched_by = "autonomous_community_name_tokens"
    if matches.empty:
        return _empty_lookup("comunidad autónoma", True)
    return _build_lookup(
        matches,
        unit="comunidad autónoma",
        matched_by=matched_by,
        unique_code="ine_autonomous_community_code",
    )


def _resolve_municipality(
    query: Any,
    dimension: pd.DataFrame,
    *,
    province_code: str | None,
    autonomous_community_code: str | None,
) -> _LookupResult:
    query_norm = normalize_text_or_none(query)
    if query_norm is None:
        return _empty_lookup("un municipio", False)
    matches = dimension.loc[
        dimension["municipio_lookup_names_norm"].map(
            lambda names: _lookup_names_contain(names, query_norm)
        )
    ]
    if matches.empty:
        return _empty_lookup("municipio", True)

    criteria: list[str] = []
    constrained = matches
    if province_code is not None:
        constrained = constrained.loc[
            constrained["ine_province_code"] == province_code
        ]
        criteria.append("province")
    if autonomous_community_code is not None:
        constrained = constrained.loc[
            constrained["ine_autonomous_community_code"]
            == autonomous_community_code
        ]
        criteria.append("autonomous_community")
    if constrained.empty:
        constrained = matches
        criteria = []

    suffix = "_and_" + "_and_".join(criteria) if criteria else ""
    return _build_lookup(
        constrained,
        unit="municipio",
        matched_by=f"municipality_name{suffix}",
        unique_code="ine_municipality_code",
    )


def _not_provided(unit: str, level: str) -> _LookupResult:
    return _LookupResult(
        AdministrativeUnitResolutionStatus.NOT_PROVIDED,
        None,
        f"location_level_{level}",
        f"La mención declarada como {level} no contiene {unit}.",
    )


def _reconcile(
    lookup: _LookupResult,
    canonical: pd.Series,
    *,
    unit: str,
    code_column: str,
    source: str,
) -> _LookupResult:
    source_reference = {
        "municipality": "el municipio",
        "province": "la provincia",
    }[source]
    source_origin = {
        "municipality": "del municipio",
        "province": "de la provincia",
    }[source]
    if lookup.status == AdministrativeUnitResolutionStatus.RESOLVED:
        assert lookup.row is not None
        if lookup.row[code_column] != canonical[code_column]:
            return _LookupResult(
                AdministrativeUnitResolutionStatus.CONFLICT,
                canonical,
                f"conflict_with_{source}",
                f"La {unit} disponible contradice la determinada por "
                f"{source_reference}; "
                "se conserva la jerarquía de la unidad más específica.",
            )
        return _LookupResult(
            AdministrativeUnitResolutionStatus.RESOLVED,
            canonical,
            f"{lookup.matched_by}_validated_by_{source}",
            f"La {unit} disponible coincide con la determinada por "
            f"{source_reference}.",
        )
    return _LookupResult(
        AdministrativeUnitResolutionStatus.RESOLVED,
        canonical,
        f"derived_from_{source}",
        f"{unit.capitalize()} derivada {source_origin}.",
    )


def _aggregate_status(
    municipality: _LookupResult,
    province: _LookupResult,
    autonomous_community: _LookupResult,
) -> LocationResolutionStatus:
    statuses = (
        municipality.status,
        province.status,
        autonomous_community.status,
    )
    if AdministrativeUnitResolutionStatus.CONFLICT in statuses:
        return LocationResolutionStatus.CONFLICT
    if AdministrativeUnitResolutionStatus.AMBIGUOUS in statuses:
        return LocationResolutionStatus.AMBIGUOUS
    resolved_count = statuses.count(AdministrativeUnitResolutionStatus.RESOLVED)
    if resolved_count == 3:
        return LocationResolutionStatus.RESOLVED
    if resolved_count:
        return LocationResolutionStatus.PARTIALLY_RESOLVED
    if AdministrativeUnitResolutionStatus.NOT_FOUND in statuses:
        return LocationResolutionStatus.NOT_FOUND
    return LocationResolutionStatus.NOT_PROVIDED


def _resolved_level(
    municipality: _LookupResult,
    province: _LookupResult,
    autonomous_community: _LookupResult,
) -> str | None:
    if municipality.status == AdministrativeUnitResolutionStatus.RESOLVED:
        return "municipality"
    if province.status == AdministrativeUnitResolutionStatus.RESOLVED:
        return "province"
    if autonomous_community.status == AdministrativeUnitResolutionStatus.RESOLVED:
        return "autonomous_community"
    return None


def _add_unit_metadata(
    record: dict[str, Any],
    prefix: str,
    result: _LookupResult,
) -> None:
    record[f"{prefix}_resolution_status"] = result.status.value
    record[f"{prefix}_resolution_matched_by"] = result.matched_by
    record[f"{prefix}_resolution_reason"] = result.reason


def _resolve_row(
    row: pd.Series,
    dimension: pd.DataFrame,
    provinces: pd.DataFrame,
    communities: pd.DataFrame,
) -> dict[str, Any]:
    level = str(row["location_level"])
    record = {column: None for column in LOCATION_RESOLUTION_COLUMNS}

    if level == _LEVEL_AUTONOMOUS_COMMUNITY:
        municipality = _not_provided("un municipio", level)
        province = _not_provided("una provincia", level)
        autonomous_community = _resolve_autonomous_community(
            row["location_name_raw"], communities
        )
    elif level == _LEVEL_PROVINCE:
        municipality = _not_provided("un municipio", level)
        province = _resolve_province(row["location_name_raw"], provinces)
        autonomous_community = _resolve_autonomous_community(
            row["autonomous_community_hint_raw"], communities
        )
        if province.status == AdministrativeUnitResolutionStatus.RESOLVED:
            assert province.row is not None
            autonomous_community = _reconcile(
                autonomous_community,
                province.row,
                unit="comunidad autónoma",
                code_column="ine_autonomous_community_code",
                source="province",
            )
    else:
        province = _resolve_province(row["province_hint_raw"], provinces)
        autonomous_community = _resolve_autonomous_community(
            row["autonomous_community_hint_raw"], communities
        )
        province_code = (
            str(province.row["ine_province_code"])
            if province.status == AdministrativeUnitResolutionStatus.RESOLVED
            and province.row is not None
            else None
        )
        autonomous_community_code = (
            str(autonomous_community.row["ine_autonomous_community_code"])
            if autonomous_community.status
            == AdministrativeUnitResolutionStatus.RESOLVED
            and autonomous_community.row is not None
            else None
        )
        municipality = _resolve_municipality(
            row["location_name_raw"],
            dimension,
            province_code=province_code,
            autonomous_community_code=autonomous_community_code,
        )
        if municipality.status == AdministrativeUnitResolutionStatus.RESOLVED:
            assert municipality.row is not None
            province = _reconcile(
                province,
                municipality.row,
                unit="provincia",
                code_column="ine_province_code",
                source="municipality",
            )
            autonomous_community = _reconcile(
                autonomous_community,
                municipality.row,
                unit="comunidad autónoma",
                code_column="ine_autonomous_community_code",
                source="municipality",
            )
        elif province.status == AdministrativeUnitResolutionStatus.RESOLVED:
            assert province.row is not None
            autonomous_community = _reconcile(
                autonomous_community,
                province.row,
                unit="comunidad autónoma",
                code_column="ine_autonomous_community_code",
                source="province",
            )

    if municipality.row is not None:
        record.update(
            municipality=municipality.row["municipio"],
            municipality_norm=municipality.row["municipio_norm"],
            ine_municipality_code=municipality.row["ine_municipality_code"],
        )
    if province.row is not None:
        record.update(
            province=province.row["provincia"],
            province_norm=province.row["provincia_norm"],
            ine_province_code=province.row["ine_province_code"],
        )
    if autonomous_community.row is not None:
        record.update(
            autonomous_community=autonomous_community.row["comunidad_autonoma"],
            autonomous_community_norm=autonomous_community.row[
                "comunidad_autonoma_norm"
            ],
            ine_autonomous_community_code=autonomous_community.row[
                "ine_autonomous_community_code"
            ],
        )

    _add_unit_metadata(record, "municipality", municipality)
    _add_unit_metadata(record, "province", province)
    _add_unit_metadata(record, "autonomous_community", autonomous_community)
    record["location_resolution_status"] = _aggregate_status(
        municipality, province, autonomous_community
    ).value
    record["location_resolution_level"] = _resolved_level(
        municipality, province, autonomous_community
    )
    return record


def resolve_locations(
    location_mentions: pd.DataFrame,
    municipality_dimension: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve menciones territoriales contra una dimensión municipal INE.

    La función es pura: no modifica los DataFrames recibidos, no escribe
    ficheros y conserva todas las filas e identificadores de entrada. Municipio,
    provincia y comunidad autónoma mantienen estados independientes; una
    provincia explícita puede resolverse aunque falle el municipio.
    """

    _validate_input(location_mentions)
    dimension = _prepare_dimension(municipality_dimension)
    provinces = _province_dimension(dimension)
    communities = _autonomous_community_dimension(dimension)

    input_columns = [
        column
        for column in location_mentions.columns
        if column not in LOCATION_RESOLUTION_COLUMNS
    ]
    base = location_mentions.loc[:, input_columns].copy(deep=True)
    records = [
        _resolve_row(row, dimension, provinces, communities)
        for _, row in location_mentions.iterrows()
    ]
    resolved = pd.DataFrame(
        records,
        index=location_mentions.index,
        columns=LOCATION_RESOLUTION_COLUMNS,
    )
    for column in LOCATION_RESOLUTION_COLUMNS:
        resolved[column] = resolved[column].astype("string")
    return pd.concat([base, resolved], axis=1)
