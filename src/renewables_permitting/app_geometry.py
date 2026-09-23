"""Verified local administrative geometry used only by the public map."""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import folium
import pandas as pd
from branca.colormap import LinearColormap


GEOMETRY_CONTRACT_VERSION = "app-administrative-geometry-v2"
COUNTRY_CONTEXT_CONTRACT_VERSION = "app-country-context-v1"
GEOMETRY_LEVELS = (
    "autonomous_community",
    "province",
    "municipality",
)
BDLJE_ATTRIBUTION = "Obra derivada de BDLJE CC-BY 4.0 ign.es"
NATURAL_EARTH_ATTRIBUTION = "Contexto geográfico: Natural Earth"
NATURAL_EARTH_REQUIRED_COUNTRIES = frozenset({
    "Algeria",
    "France",
    "Morocco",
    "Portugal",
    "Spain",
})
SPAIN_CONTEXT_BOUNDS = ((24.0, -20.5), (48.5, 12.5))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CODE_PATTERNS = {
    "autonomous_community": re.compile(r"^\d{2}$"),
    "province": re.compile(r"^\d{2}$"),
    "municipality": re.compile(r"^\d{5}$"),
}


class GeometryReferenceError(RuntimeError):
    """The application geometry is missing, unsafe or internally inconsistent."""


@dataclass(frozen=True)
class GeometryReference:
    """Validated reference features grouped by administrative level."""

    features: Mapping[str, tuple[dict[str, Any], ...]]
    manifest: Mapping[str, Any]
    manifest_sha256: str
    artifact_sha256s: Mapping[str, str]
    root: Path


@dataclass(frozen=True)
class CountryContextReference:
    """Validated local country context kept separate from IGN geometry."""

    collection: Mapping[str, Any]
    manifest: Mapping[str, Any]
    manifest_sha256: str
    artifact_sha256: str
    root: Path


@dataclass(frozen=True)
class TerritorySelection:
    """One validated administrative feature selected in the Folium map."""

    level: str
    code: str
    name: str


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GeometryReferenceError(
            f"El {label} de geometría no contiene JSON válido."
        ) from error


def _safe_artifact_path(root: Path, filename: object) -> Path:
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise GeometryReferenceError("La ruta del artefacto geométrico no es segura.")
    try:
        resolved_root = root.resolve(strict=True)
        artifact = (root / filename).resolve(strict=True)
        artifact.relative_to(resolved_root)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise GeometryReferenceError(
            "No se encontró un artefacto geométrico seguro."
        ) from error
    if not artifact.is_file() or artifact.is_symlink():
        raise GeometryReferenceError(
            "El artefacto geométrico no es un fichero regular."
        )
    return artifact


def _validate_ring(ring: object) -> None:
    if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
        raise GeometryReferenceError("Una geometría contiene un anillo no cerrado.")
    for point in ring:
        if not isinstance(point, list) or len(point) != 2:
            raise GeometryReferenceError(
                "Una geometría contiene coordenadas inválidas."
            )
        longitude, latitude = point
        if (
            isinstance(longitude, bool)
            or isinstance(latitude, bool)
            or not isinstance(longitude, (int, float))
            or not isinstance(latitude, (int, float))
            or not math.isfinite(float(longitude))
            or not math.isfinite(float(latitude))
            or not -180 <= float(longitude) <= 180
            or not -90 <= float(latitude) <= 90
        ):
            raise GeometryReferenceError(
                "Una geometría contiene coordenadas inválidas."
            )


def _validate_geometry(geometry: object) -> None:
    if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
        raise GeometryReferenceError("El artefacto debe contener polígonos múltiples.")
    polygons = geometry.get("coordinates")
    if not isinstance(polygons, list) or not polygons:
        raise GeometryReferenceError("Una geometría administrativa está vacía.")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise GeometryReferenceError("Una geometría administrativa está vacía.")
        for ring in polygon:
            _validate_ring(ring)


def _validate_source_manifest(manifest: Mapping[str, Any]) -> None:
    source = manifest.get("source")
    processing = manifest.get("processing")
    counts = manifest.get("feature_counts")
    artifacts = manifest.get("artifacts")
    if not isinstance(source, dict) or not isinstance(processing, dict):
        raise GeometryReferenceError(
            "El manifest no declara la procedencia geométrica."
        )
    if (
        source.get("organization") != "IGN/CNIG"
        or source.get("series")
        != "Límites municipales, provinciales y autonómicos"
        or source.get("product") != "Límites y Unidades Administrativas Actuales"
        or source.get("file") != "LINEAS_LIMITE.ZIP"
        or source.get("publication_date") != "2026-07-28"
        or not isinstance(source.get("sha256"), str)
        or _SHA256_RE.fullmatch(str(source["sha256"])) is None
        or processing.get("version") != "ign_bdlje_app_geometry_v2"
        or processing.get("source_crs")
        != {
            "peninsula_balearic_ceuta_melilla": "EPSG:4258",
            "canary_islands": "EPSG:4326",
        }
        or processing.get("output_crs") != "WGS84-compatible GeoJSON"
        or manifest.get("license_attribution") != BDLJE_ATTRIBUTION
        or not isinstance(counts, dict)
        or set(counts) != set(GEOMETRY_LEVELS)
        or not isinstance(artifacts, dict)
        or set(artifacts) != set(GEOMETRY_LEVELS)
    ):
        raise GeometryReferenceError("La procedencia geométrica no es contractual.")
    filenames: set[str] = set()
    for level in GEOMETRY_LEVELS:
        specification = artifacts[level]
        if (
            not isinstance(specification, dict)
            or set(specification) != {"file", "sha256"}
            or not isinstance(specification["file"], str)
            or Path(specification["file"]).name != specification["file"]
            or not isinstance(specification["sha256"], str)
            or _SHA256_RE.fullmatch(specification["sha256"]) is None
            or specification["file"] in filenames
        ):
            raise GeometryReferenceError(
                "El manifest no declara artefactos geométricos contractuales."
            )
        filenames.add(specification["file"])


def load_geometry_reference(
    root: Path,
    *,
    expected_manifest_sha256: str,
) -> GeometryReference:
    """Load all versioned GeoJSON assets after contract and integrity checks."""

    directory = Path(root)
    if not directory.is_dir() or directory.is_symlink():
        raise GeometryReferenceError("La referencia geométrica no está disponible.")
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise GeometryReferenceError("Falta el manifest de geometría.")
    if (
        not isinstance(expected_manifest_sha256, str)
        or _SHA256_RE.fullmatch(expected_manifest_sha256) is None
        or _sha256_file(manifest_path) != expected_manifest_sha256
    ):
        raise GeometryReferenceError(
            "La identidad del manifest geométrico no coincide."
        )
    manifest = _read_json(manifest_path, label="manifest")
    if not isinstance(manifest, dict):
        raise GeometryReferenceError("El manifest de geometría no es un objeto JSON.")
    if manifest.get("contract_version") != GEOMETRY_CONTRACT_VERSION:
        raise GeometryReferenceError("La versión del contrato geométrico no coincide.")
    _validate_source_manifest(manifest)
    grouped: dict[str, list[dict[str, Any]]] = {
        level: [] for level in GEOMETRY_LEVELS
    }
    observed_codes: dict[str, set[str]] = {
        level: set() for level in GEOMETRY_LEVELS
    }
    artifact_sha256s: dict[str, str] = {}
    for expected_level in GEOMETRY_LEVELS:
        specification = manifest["artifacts"][expected_level]
        artifact = _safe_artifact_path(directory, specification["file"])
        declared_hash = str(specification["sha256"])
        if _sha256_file(artifact) != declared_hash:
            raise GeometryReferenceError(
                "El hash de integridad geométrica no coincide."
            )
        artifact_sha256s[expected_level] = declared_hash
        collection = _read_json(artifact, label=f"artefacto {expected_level}")
        if (
            not isinstance(collection, dict)
            or collection.get("type") != "FeatureCollection"
            or not isinstance(collection.get("features"), list)
        ):
            raise GeometryReferenceError("El artefacto no es una colección GeoJSON.")
        for feature in collection["features"]:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise GeometryReferenceError(
                    "El artefacto contiene una feature inválida."
                )
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                raise GeometryReferenceError(
                    "Una feature no contiene propiedades válidas."
                )
            level = properties.get("level")
            code = properties.get("code")
            name = properties.get("name")
            if (
                level != expected_level
                or not isinstance(code, str)
                or _CODE_PATTERNS[expected_level].fullmatch(code) is None
                or not isinstance(name, str)
                or not name.strip()
                or feature.get("id") != f"{level}:{code}"
                or code in observed_codes[expected_level]
            ):
                raise GeometryReferenceError(
                    "Una feature tiene código o identidad inválidos."
                )
            _validate_geometry(feature.get("geometry"))
            observed_codes[expected_level].add(code)
            grouped[expected_level].append(deepcopy(feature))
    for feature in grouped["province"]:
        parent = feature["properties"].get("autonomous_community_code")
        if parent not in observed_codes["autonomous_community"]:
            raise GeometryReferenceError("Una provincia no tiene CCAA padre válida.")
    province_parents = {
        feature["properties"]["code"]: feature["properties"][
            "autonomous_community_code"
        ]
        for feature in grouped["province"]
    }
    for feature in grouped["municipality"]:
        properties = feature["properties"]
        province = properties.get("province_code")
        community = properties.get("autonomous_community_code")
        if province not in province_parents or province_parents[province] != community:
            raise GeometryReferenceError("Un municipio no tiene padres coherentes.")
    expected_counts = manifest["feature_counts"]
    if any(
        expected_counts[level] != len(grouped[level]) for level in GEOMETRY_LEVELS
    ):
        raise GeometryReferenceError("Los conteos geométricos no coinciden.")
    frozen_features = MappingProxyType({
        level: tuple(sorted(
            grouped[level],
            key=lambda item: item["properties"]["code"],
        ))
        for level in GEOMETRY_LEVELS
    })
    return GeometryReference(
        features=frozen_features,
        manifest=MappingProxyType(deepcopy(manifest)),
        manifest_sha256=expected_manifest_sha256,
        artifact_sha256s=MappingProxyType(artifact_sha256s.copy()),
        root=directory.resolve(),
    )


def _validated_country_context(
    collection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and copy non-interactive Natural Earth country features."""

    if (
        collection.get("type") != "FeatureCollection"
        or not isinstance(collection.get("features"), list)
        or not collection["features"]
    ):
        raise GeometryReferenceError(
            "El contexto geográfico no es una colección GeoJSON válida."
        )
    features: list[dict[str, Any]] = []
    observed_names: set[str] = set()
    for raw_feature in collection["features"]:
        if (
            not isinstance(raw_feature, dict)
            or raw_feature.get("type") != "Feature"
            or not isinstance(raw_feature.get("properties"), dict)
        ):
            raise GeometryReferenceError(
                "El contexto geográfico contiene una feature inválida."
            )
        feature = deepcopy(raw_feature)
        properties = feature["properties"]
        if set(properties) != {"iso_a3", "name"}:
            raise GeometryReferenceError(
                "El contexto geográfico contiene propiedades no contractuales."
            )
        name = properties["name"]
        iso_a3 = properties["iso_a3"]
        if (
            not isinstance(name, str)
            or not name.strip()
            or name in observed_names
            or not isinstance(iso_a3, str)
            or not iso_a3.strip()
        ):
            raise GeometryReferenceError(
                "El contexto geográfico contiene identidades de país inválidas."
            )
        _validate_geometry(feature.get("geometry"))
        observed_names.add(name)
        features.append(feature)
    missing = NATURAL_EARTH_REQUIRED_COUNTRIES - observed_names
    if missing:
        raise GeometryReferenceError(
            "El contexto geográfico no cubre los países mínimos requeridos."
        )
    return {
        "type": "FeatureCollection",
        "features": sorted(features, key=lambda item: item["properties"]["name"]),
    }


def load_country_context_reference(
    root: Path,
    *,
    expected_manifest_sha256: str,
) -> CountryContextReference:
    """Load versioned Natural Earth context after provenance and hash checks."""

    directory = Path(root)
    if not directory.is_dir() or directory.is_symlink():
        raise GeometryReferenceError("El contexto geográfico no está disponible.")
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise GeometryReferenceError("Falta el manifest del contexto geográfico.")
    if (
        not isinstance(expected_manifest_sha256, str)
        or _SHA256_RE.fullmatch(expected_manifest_sha256) is None
        or _sha256_file(manifest_path) != expected_manifest_sha256
    ):
        raise GeometryReferenceError(
            "La identidad del manifest de contexto no coincide."
        )
    manifest = _read_json(manifest_path, label="manifest de contexto")
    if not isinstance(manifest, dict):
        raise GeometryReferenceError(
            "El manifest de contexto no es un objeto JSON."
        )
    source = manifest.get("source")
    processing = manifest.get("processing")
    artifact_spec = manifest.get("artifact")
    if (
        manifest.get("contract_version") != COUNTRY_CONTEXT_CONTRACT_VERSION
        or not isinstance(source, dict)
        or source.get("organization") != "Natural Earth"
        or source.get("dataset") != "naturalearth_lowres"
        or source.get("scale") != "1:110m"
        or source.get("source_crs") != "EPSG:4326"
        or source.get("license") != "Public domain"
        or not isinstance(source.get("sha256"), str)
        or _SHA256_RE.fullmatch(str(source["sha256"])) is None
        or not isinstance(processing, dict)
        or processing.get("version") != "natural_earth_country_context_v1"
        or processing.get("output_crs") != "EPSG:4326"
        or not isinstance(artifact_spec, dict)
        or set(artifact_spec) != {"file", "sha256"}
        or manifest.get("license_attribution") != NATURAL_EARTH_ATTRIBUTION
        or not isinstance(manifest.get("feature_count"), int)
        or isinstance(manifest.get("feature_count"), bool)
        or manifest["feature_count"] < 1
    ):
        raise GeometryReferenceError(
            "La procedencia del contexto geográfico no es contractual."
        )
    artifact = _safe_artifact_path(directory, artifact_spec["file"])
    declared_hash = artifact_spec["sha256"]
    if (
        not isinstance(declared_hash, str)
        or _SHA256_RE.fullmatch(declared_hash) is None
        or _sha256_file(artifact) != declared_hash
    ):
        raise GeometryReferenceError(
            "El hash del contexto geográfico no coincide."
        )
    raw_collection = _read_json(artifact, label="artefacto de contexto")
    if not isinstance(raw_collection, dict):
        raise GeometryReferenceError(
            "El artefacto de contexto no es un objeto JSON."
        )
    collection = _validated_country_context(raw_collection)
    if len(collection["features"]) != manifest["feature_count"]:
        raise GeometryReferenceError(
            "El conteo del contexto geográfico no coincide."
        )
    return CountryContextReference(
        collection=MappingProxyType(collection),
        manifest=MappingProxyType(deepcopy(manifest)),
        manifest_sha256=expected_manifest_sha256,
        artifact_sha256=declared_hash,
        root=directory.resolve(),
    )


def attach_project_counts(
    features: Sequence[Mapping[str, Any]],
    counts: pd.DataFrame,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Join analytical counts to geometry strictly by administrative code."""

    required = {"code", "project_count"}
    if not isinstance(counts, pd.DataFrame) or not required <= set(counts.columns):
        raise ValueError("La agregación territorial no contiene sus columnas.")
    if counts["code"].isna().any() or counts["code"].astype(str).duplicated().any():
        raise ValueError("La agregación territorial contiene códigos duplicados.")
    values = {
        str(row.code): int(row.project_count)
        for row in counts.loc[:, ["code", "project_count"]].itertuples(index=False)
    }
    feature_codes = {
        str(feature["properties"]["code"]) for feature in features
    }
    output: list[dict[str, Any]] = []
    for source in features:
        feature = deepcopy(dict(source))
        code = str(feature["properties"]["code"])
        feature["properties"]["project_count"] = values.get(code, 0)
        output.append(feature)
    unmatched = tuple(sorted(set(values) - feature_codes))
    return {"type": "FeatureCollection", "features": output}, unmatched


def select_geometry_features(
    features: Sequence[Mapping[str, Any]],
    *,
    codes: Sequence[str],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Select an ordered geometry subset by stable code without mutating input."""

    selected_codes = tuple(dict.fromkeys(str(code) for code in codes))
    requested = set(selected_codes)
    by_code: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise ValueError("Una feature geométrica no contiene propiedades.")
        code = properties.get("code")
        if not isinstance(code, str) or code in by_code:
            raise ValueError("Las features geométricas no tienen códigos únicos.")
        by_code[code] = feature
    selected = tuple(
        deepcopy(dict(by_code[code])) for code in selected_codes if code in by_code
    )
    return selected, tuple(sorted(requested - set(by_code)))


def _validated_map_collection(
    collection: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[tuple[float, float], tuple[float, float]], int]:
    """Copy a counted collection and derive its Leaflet bounds."""

    if collection.get("type") != "FeatureCollection":
        raise ValueError("El mapa requiere una colección GeoJSON.")
    raw_features = collection.get("features")
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError("El mapa requiere features GeoJSON.")
    features: list[dict[str, Any]] = []
    positions: list[tuple[float, float]] = []
    maximum = 0

    def collect_positions(value: object) -> None:
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in value
            )
        ):
            longitude, latitude = (float(value[0]), float(value[1]))
            if not math.isfinite(longitude) or not math.isfinite(latitude):
                raise ValueError("El mapa contiene coordenadas no finitas.")
            positions.append((longitude, latitude))
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                collect_positions(item)

    for raw_feature in raw_features:
        if (
            not isinstance(raw_feature, dict)
            or raw_feature.get("type") != "Feature"
            or not isinstance(raw_feature.get("properties"), dict)
        ):
            raise ValueError("El mapa contiene una feature no válida.")
        feature = deepcopy(raw_feature)
        properties = feature["properties"]
        level = properties.get("level")
        code = properties.get("code")
        name = properties.get("name")
        count = properties.get("project_count")
        if (
            level not in GEOMETRY_LEVELS
            or not isinstance(code, str)
            or _CODE_PATTERNS[str(level)].fullmatch(code) is None
            or not isinstance(name, str)
            or not name.strip()
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise ValueError("El mapa contiene propiedades territoriales inválidas.")
        try:
            _validate_geometry(feature.get("geometry"))
        except GeometryReferenceError as error:
            raise ValueError("El mapa contiene una geometría no válida.") from error
        collect_positions(feature["geometry"]["coordinates"])
        maximum = max(maximum, count)
        features.append(feature)
    if not positions:
        raise ValueError("El mapa requiere coordenadas GeoJSON.")
    minimum_longitude = min(position[0] for position in positions)
    maximum_longitude = max(position[0] for position in positions)
    minimum_latitude = min(position[1] for position in positions)
    maximum_latitude = max(position[1] for position in positions)
    if (
        minimum_longitude == maximum_longitude
        or minimum_latitude == maximum_latitude
    ):
        raise ValueError("El mapa requiere una extensión geográfica no vacía.")
    return (
        {"type": "FeatureCollection", "features": features},
        (
            (minimum_latitude, minimum_longitude),
            (maximum_latitude, maximum_longitude),
        ),
        maximum,
    )


def _base_map(*, location: Sequence[float], zoom_start: int) -> folium.Map:
    """Build a tile-free Leaflet canvas for local vector layers."""

    return folium.Map(
        location=list(location),
        tiles=None,
        zoom_start=zoom_start,
        control_scale=True,
        attribution_control=False,
    )


def _add_country_context(
    map_view: folium.Map,
    country_context: Mapping[str, Any],
) -> None:
    """Draw local Natural Earth countries below every analytical layer."""

    try:
        copied = _validated_country_context(country_context)
    except GeometryReferenceError as error:
        raise ValueError("El mapa requiere contexto geográfico válido.") from error
    folium.GeoJson(
        copied,
        name="Contexto geográfico (Natural Earth)",
        style_function=lambda _: {
            "color": "#94a3b8",
            "weight": 0.7,
            "fillColor": "#f8fafc",
            "fillOpacity": 0.72,
        },
        interactive=False,
    ).add_to(map_view)


def _add_administrative_context(
    map_view: folium.Map,
    context_features: Sequence[Mapping[str, Any]],
) -> None:
    """Draw non-selectable parent boundaries below a precise local layer."""

    if not context_features:
        return
    context_collection = {
        "type": "FeatureCollection",
        "features": [deepcopy(dict(feature)) for feature in context_features],
    }
    for feature in context_collection["features"]:
        feature["properties"]["project_count"] = 0
    validated_context, _, _ = _validated_map_collection(context_collection)
    folium.GeoJson(
        validated_context,
        name="Contexto administrativo",
        style_function=lambda _: {
            "color": "#64748b",
            "weight": 0.8,
            "fillOpacity": 0,
        },
        interactive=False,
    ).add_to(map_view)


def build_folium_choropleth(
    collection: Mapping[str, Any],
    *,
    country_context: Mapping[str, Any],
    context_features: Sequence[Mapping[str, Any]] = (),
) -> folium.Map:
    """Build the complete analytical map over local vector context."""

    copied, _, maximum = _validated_map_collection(collection)
    colors = ("#eff6ff", "#bfdbfe", "#60a5fa", "#1d4ed8")
    scale = LinearColormap(
        colors=colors,
        vmin=0,
        vmax=max(1, maximum),
        caption="Proyectos distintos",
    )

    def style_function(feature: Mapping[str, Any]) -> dict[str, object]:
        count = int(feature["properties"]["project_count"])
        return {
            "color": "#334155",
            "weight": 1,
            "fillColor": "#e5e7eb" if count == 0 else scale(count),
            "fillOpacity": 0.5 if count == 0 else 0.75,
        }

    map_view = _base_map(
        location=(
            (SPAIN_CONTEXT_BOUNDS[0][0] + SPAIN_CONTEXT_BOUNDS[1][0]) / 2,
            (SPAIN_CONTEXT_BOUNDS[0][1] + SPAIN_CONTEXT_BOUNDS[1][1]) / 2,
        ),
        zoom_start=4,
    )
    _add_country_context(map_view, country_context)
    _add_administrative_context(map_view, context_features)
    folium.GeoJson(
        copied,
        name="Territorios administrativos",
        style_function=style_function,
        highlight_function=lambda _: {
            "color": "#0f172a",
            "weight": 2,
            "fillOpacity": 0.9,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=("name", "project_count"),
            aliases=("Territorio", "N.º de proyectos"),
            localize=True,
            sticky=True,
        ),
        zoom_on_click=False,
    ).add_to(map_view)
    scale.add_to(map_view)
    map_view.fit_bounds(
        [list(bound) for bound in SPAIN_CONTEXT_BOUNDS],
        padding=(8, 8),
        max_zoom=5,
    )
    return map_view


def build_folium_project_map(
    collection: Mapping[str, Any],
    *,
    country_context: Mapping[str, Any],
    context_features: Sequence[Mapping[str, Any]] = (),
) -> folium.Map:
    """Build one project map fitted only to its selected local territories."""

    counted = deepcopy(dict(collection))
    raw_features = counted.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("El mapa de proyecto requiere features GeoJSON.")
    for feature in raw_features:
        if isinstance(feature, dict) and isinstance(feature.get("properties"), dict):
            feature["properties"]["project_count"] = 1
    copied, bounds, _ = _validated_map_collection(counted)
    southwest, northeast = bounds
    levels = {
        str(feature["properties"]["level"]) for feature in copied["features"]
    }
    if len(levels) != 1:
        raise ValueError("El mapa de proyecto requiere un único nivel territorial.")
    level = next(iter(levels))
    map_view = _base_map(
        location=(
            (southwest[0] + northeast[0]) / 2,
            (southwest[1] + northeast[1]) / 2,
        ),
        zoom_start=7,
    )
    _add_country_context(map_view, country_context)
    _add_administrative_context(map_view, context_features)
    tooltip_fields = ["name"]
    tooltip_aliases = [{
        "municipality": "Municipio",
        "province": "Provincia",
        "autonomous_community": "Comunidad o ciudad autónoma",
    }[level]]
    properties = copied["features"][0]["properties"]
    for field, alias in (
        ("province_name", "Provincia"),
        ("autonomous_community_name", "Comunidad o ciudad autónoma"),
    ):
        if field in properties:
            tooltip_fields.append(field)
            tooltip_aliases.append(alias)
    folium.GeoJson(
        copied,
        name="Ámbito publicado del proyecto",
        style_function=lambda _: {
            "color": "#1e3a8a",
            "weight": 2,
            "fillColor": "#2563eb",
            "fillOpacity": 0.58,
        },
        highlight_function=lambda _: {
            "color": "#0f172a",
            "weight": 3,
            "fillOpacity": 0.75,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tuple(tooltip_fields),
            aliases=tuple(tooltip_aliases),
            localize=True,
            sticky=True,
        ),
        zoom_on_click=False,
    ).add_to(map_view)
    map_view.fit_bounds(
        [list(southwest), list(northeast)],
        padding=(28, 28),
        max_zoom=11,
    )
    return map_view


def parse_folium_territory_selection(
    payload: object,
    *,
    expected_level: str,
    allowed_territories: Mapping[str, str],
) -> TerritorySelection | None:
    """Validate the GeoJSON feature returned by ``st_folium`` fail-safe."""

    if expected_level not in GEOMETRY_LEVELS or not isinstance(payload, Mapping):
        return None
    feature = payload.get("last_active_drawing")
    if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
        return None
    properties = feature.get("properties")
    if not isinstance(properties, Mapping):
        return None
    level = properties.get("level")
    code = properties.get("code")
    name = properties.get("name")
    count = properties.get("project_count")
    if (
        level != expected_level
        or not isinstance(code, str)
        or _CODE_PATTERNS[expected_level].fullmatch(code) is None
        or not isinstance(name, str)
        or not name.strip()
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or allowed_territories.get(code) != name
    ):
        return None
    try:
        _validate_geometry(feature.get("geometry"))
    except GeometryReferenceError:
        return None
    return TerritorySelection(level=level, code=code, name=name)
