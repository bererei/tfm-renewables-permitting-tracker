from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import folium
import pandas as pd
import pytest
from branca.colormap import LinearColormap
from folium.features import GeoJson, GeoJsonTooltip
from folium.map import FitBounds

from renewables_permitting.app_geometry import (
    NATURAL_EARTH_ATTRIBUTION,
    GeometryReferenceError,
    attach_project_counts,
    build_folium_choropleth,
    build_folium_project_map,
    load_country_context_reference,
    load_geometry_reference,
    parse_folium_territory_selection,
    select_geometry_features,
)


def _country_context_collection() -> dict[str, object]:
    countries = (
        ("Algeria", "DZA", 2.0, 29.0),
        ("France", "FRA", 1.0, 44.0),
        ("Morocco", "MAR", -8.0, 30.0),
        ("Portugal", "PRT", -9.0, 38.0),
        ("Spain", "ESP", -4.0, 38.0),
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"iso_a3": iso_a3, "name": name},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[
                        [longitude, latitude],
                        [longitude + 0.5, latitude],
                        [longitude + 0.5, latitude + 0.5],
                        [longitude, latitude],
                    ]]],
                },
            }
            for name, iso_a3, longitude, latitude in countries
        ],
    }


def _write_country_context(root: Path) -> tuple[Path, str]:
    root.mkdir()
    collection = _country_context_collection()
    artifact_payload = json.dumps(
        collection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (root / "countries_context.geojson").write_bytes(artifact_payload)
    manifest = {
        "contract_version": "app-country-context-v1",
        "artifact": {
            "file": "countries_context.geojson",
            "sha256": sha256(artifact_payload).hexdigest(),
        },
        "feature_count": 5,
        "license_attribution": NATURAL_EARTH_ATTRIBUTION,
        "source": {
            "organization": "Natural Earth",
            "dataset": "naturalearth_lowres",
            "scale": "1:110m",
            "source_crs": "EPSG:4326",
            "sha256": "b" * 64,
            "license": "Public domain",
        },
        "processing": {
            "version": "natural_earth_country_context_v1",
            "output_crs": "EPSG:4326",
        },
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (root / "manifest.json").write_bytes(manifest_payload)
    return root, sha256(manifest_payload).hexdigest()


def _write_geometry_reference(root: Path) -> tuple[Path, str]:
    root.mkdir()
    features = [
        {
            "type": "Feature",
            "id": "autonomous_community:01",
            "properties": {
                "level": "autonomous_community",
                "code": "01",
                "name": "Andalucía",
                "autonomous_community_code": "01",
                "province_code": None,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]],
            },
        },
        {
            "type": "Feature",
            "id": "province:41",
            "properties": {
                "level": "province",
                "code": "41",
                "name": "Sevilla",
                "autonomous_community_code": "01",
                "province_code": "41",
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.0]]]],
            },
        },
        {
            "type": "Feature",
            "id": "municipality:41091",
            "properties": {
                "level": "municipality",
                "code": "41091",
                "name": "Sevilla",
                "autonomous_community_code": "01",
                "province_code": "41",
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0.0, 0.0], [0.25, 0.0], [0.25, 0.25], [0.0, 0.0]]]],
            },
        },
    ]
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
            "simplification_tolerance_degrees": {
                "autonomous_community": 0.005,
                "province": 0.0025,
                "municipality": 0.001,
            },
        },
        "code_fields": {
            "autonomous_community": "code",
            "province": "code",
            "municipality": "code",
        },
        "feature_counts": {
            "autonomous_community": 1,
            "province": 1,
            "municipality": 1,
        },
        "license_attribution": "Obra derivada de BDLJE CC-BY 4.0 ign.es",
    }
    manifest_payload = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (root / "manifest.json").write_bytes(manifest_payload)
    return root, sha256(manifest_payload).hexdigest()


def test_geometry_loader_verifies_hash_levels_and_code_relationships(
    tmp_path: Path,
) -> None:
    root, manifest_digest = _write_geometry_reference(tmp_path / "geometry")

    reference = load_geometry_reference(
        root,
        expected_manifest_sha256=manifest_digest,
    )

    assert reference.manifest_sha256 == manifest_digest
    assert [
        feature["properties"]["code"]
        for feature in reference.features["municipality"]
    ] == ["41091"]


def test_geometry_loader_rejects_tampered_artifact(tmp_path: Path) -> None:
    root, manifest_digest = _write_geometry_reference(tmp_path / "geometry")
    (root / "provinces.geojson").write_text("{}", encoding="utf-8")

    with pytest.raises(GeometryReferenceError, match="hash|integridad"):
        load_geometry_reference(
            root,
            expected_manifest_sha256=manifest_digest,
        )


def test_country_context_loader_verifies_provenance_countries_and_hash(
    tmp_path: Path,
) -> None:
    root, manifest_digest = _write_country_context(tmp_path / "countries")

    reference = load_country_context_reference(
        root,
        expected_manifest_sha256=manifest_digest,
    )

    assert reference.manifest_sha256 == manifest_digest
    assert reference.manifest["source"]["license"] == "Public domain"
    assert {
        feature["properties"]["name"]
        for feature in reference.collection["features"]
    } == {"Algeria", "France", "Morocco", "Portugal", "Spain"}


def test_geometry_join_uses_codes_and_reports_unmatched() -> None:
    features = ({
        "type": "Feature",
        "id": "province:41",
        "properties": {
            "level": "province",
            "code": "41",
            "name": "Nombre oficial distinto",
            "autonomous_community_code": "01",
            "province_code": "41",
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
        },
    },)
    counts = pd.DataFrame({
        "level": ["province", "province"],
        "code": ["41", "99"],
        "name": ["Sevilla", "No existe"],
        "autonomous_community_code": ["01", "01"],
        "province_code": ["41", "99"],
        "project_count": [3, 1],
    })

    collection, unmatched = attach_project_counts(features, counts)

    assert collection["features"][0]["properties"]["project_count"] == 3
    assert collection["features"][0]["properties"]["name"] == (
        "Nombre oficial distinto"
    )
    assert unmatched == ("99",)


def test_geometry_join_is_left_join_and_retains_zero_count_units() -> None:
    features = tuple(
        {
            "type": "Feature",
            "id": f"province:{code}",
            "properties": {
                "level": "province",
                "code": code,
                "name": name,
                "autonomous_community_code": "01",
                "province_code": code,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
        }
        for code, name in (("41", "Sevilla"), ("04", "Almería"))
    )
    counts = pd.DataFrame({"code": ["41"], "project_count": [3]})

    collection, unmatched = attach_project_counts(features, counts)

    assert unmatched == ()
    assert [
        (feature["properties"]["code"], feature["properties"]["project_count"])
        for feature in collection["features"]
    ] == [("41", 3), ("04", 0)]


def test_folium_builder_uses_only_local_vector_context_and_analytical_geojson() -> None:
    features = ({
        "type": "Feature",
        "id": "province:41",
        "properties": {
            "level": "province",
            "code": "41",
            "name": "Sevilla",
            "project_count": 3,
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
        },
    },)
    collection = {"type": "FeatureCollection", "features": list(features)}

    map_view = build_folium_choropleth(
        collection,
        country_context=_country_context_collection(),
    )

    assert isinstance(map_view, folium.Map)
    assert map_view.options["attribution_control"] is False
    assert not any(
        isinstance(child, folium.raster_layers.TileLayer)
        for child in map_view._children.values()
    )
    geojson_layers = [
        child for child in map_view._children.values() if isinstance(child, GeoJson)
    ]
    assert len(geojson_layers) == 2
    country_context = next(
        layer
        for layer in geojson_layers
        if "project_count" not in layer.data["features"][0]["properties"]
    )
    geojson = next(
        layer
        for layer in geojson_layers
        if "project_count" in layer.data["features"][0]["properties"]
    )
    assert country_context.options["interactive"] is False
    assert {
        feature["properties"]["name"]
        for feature in country_context.data["features"]
    } >= {"Spain", "Portugal", "France", "Morocco"}
    assert geojson.data["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert geojson.data["features"][0]["properties"] == {
        "level": "province",
        "code": "41",
        "name": "Sevilla",
        "project_count": 3,
    }
    assert any(
        isinstance(child, FitBounds) for child in map_view._children.values()
    )
    legend = next(
        child
        for child in map_view._children.values()
        if isinstance(child, LinearColormap)
    )
    assert legend.caption == "Proyectos distintos"
    fit = next(
        child
        for child in map_view._children.values()
        if isinstance(child, FitBounds)
    )
    assert fit.bounds == [[24.0, -20.5], [48.5, 12.5]]
    tooltip = next(
        child
        for child in geojson._children.values()
        if isinstance(child, GeoJsonTooltip)
    )
    assert tooltip.fields == ("name", "project_count")
    assert tooltip.aliases == ("Territorio", "N.º de proyectos")
    html = map_view.get_root().render()
    assert "Sevilla" in html
    assert '"code": "41"' in html
    assert "cartocdn.com" not in html
    assert "openstreetmap.org" not in html
    assert "mapbox" not in html.lower()
    assert "google" not in html.lower()
    assert "esri" not in html.lower()


def test_folium_builder_uses_neutral_style_for_zero_count() -> None:
    collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "province:26",
            "properties": {
                "level": "province",
                "code": "26",
                "name": "La Rioja",
                "project_count": 0,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
        }],
    }

    map_view = build_folium_choropleth(
        collection,
        country_context=_country_context_collection(),
    )
    geojson = next(
        child
        for child in map_view._children.values()
        if isinstance(child, GeoJson)
        and "project_count" in child.data["features"][0]["properties"]
    )

    style = geojson.style_function(geojson.data["features"][0])
    assert style["fillColor"] == "#e5e7eb"
    assert style["fillOpacity"] > 0


@pytest.mark.parametrize(
    ("level", "code", "name"),
    [
        ("autonomous_community", "01", "Andalucía"),
        ("province", "41", "Sevilla"),
        ("municipality", "41091", "Sevilla"),
    ],
)
def test_folium_selection_uses_stable_feature_identity(
    level: str,
    code: str,
    name: str,
) -> None:
    payload = {
        "last_active_drawing": {
            "type": "Feature",
            "properties": {
                "level": level,
                "code": code,
                "name": name,
                "project_count": 2,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
        }
    }

    selection = parse_folium_territory_selection(
        payload,
        expected_level=level,
        allowed_territories={code: name},
    )

    assert selection is not None
    assert selection.level == level
    assert selection.code == code
    assert selection.name == name


@pytest.mark.parametrize(
    "payload,expected_level,allowed",
    [
        ({}, "province", {"41": "Sevilla"}),
        (
            {
                "last_active_drawing": {
                    "type": "Feature",
                    "properties": {
                        "level": "municipality",
                        "code": "41091",
                        "name": "Sevilla",
                        "project_count": 1,
                    },
                }
            },
            "province",
            {"41": "Sevilla"},
        ),
        (
            {
                "last_active_drawing": {
                    "type": "Feature",
                    "properties": {
                        "level": "province",
                        "code": "99",
                        "name": "Desconocida",
                        "project_count": 1,
                    },
                }
            },
            "province",
            {"41": "Sevilla"},
        ),
    ],
)
def test_folium_selection_rejects_invalid_or_unselectable_payloads(
    payload: object,
    expected_level: str,
    allowed: dict[str, str],
) -> None:
    assert parse_folium_territory_selection(
        payload,
        expected_level=expected_level,
        allowed_territories=allowed,
    ) is None


def test_folium_selection_accepts_zero_count_for_a_known_territory() -> None:
    payload = {
        "last_active_drawing": {
            "type": "Feature",
            "properties": {
                "level": "province",
                "code": "41",
                "name": "Sevilla",
                "project_count": 0,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            },
        }
    }

    selection = parse_folium_territory_selection(
        payload,
        expected_level="province",
        allowed_territories={"41": "Sevilla"},
    )

    assert selection is not None
    assert selection.code == "41"


@pytest.mark.parametrize(
    ("level", "expected_count"),
    [
        ("autonomous_community", 19),
        ("province", 52),
        ("municipality", 95),
    ],
)
def test_versioned_geometry_builds_every_default_folium_level(
    level: str,
    expected_count: int,
) -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "app_assets"
        / "geometry"
        / "ign_bdlje_2026-07-28"
    )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest_digest = sha256((root / "manifest.json").read_bytes()).hexdigest()
    reference = load_geometry_reference(
        root,
        expected_manifest_sha256=manifest_digest,
    )
    counts = pd.DataFrame({
        "code": [
            str(feature["properties"]["code"])
            for feature in reference.features[level]
        ],
        "project_count": [1] * expected_count,
    })
    collection, unmatched = attach_project_counts(
        reference.features[level],
        counts,
    )

    map_view = build_folium_choropleth(
        collection,
        country_context=_country_context_collection(),
    )
    geojson = next(
        child
        for child in map_view._children.values()
        if isinstance(child, GeoJson)
        and "project_count" in child.data["features"][0]["properties"]
    )

    assert unmatched == ()
    assert len(geojson.data["features"]) == expected_count


def _feature_bounds(feature: dict[str, object]) -> tuple[float, float, float, float]:
    positions: list[tuple[float, float]] = []

    def collect(value: object) -> None:
        if (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, (int, float)) for item in value)
        ):
            positions.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    geometry = feature["geometry"]
    assert isinstance(geometry, dict)
    collect(geometry["coordinates"])
    longitudes = [position[0] for position in positions]
    latitudes = [position[1] for position in positions]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def test_versioned_geometry_contains_complete_units_and_real_city_bounds() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "app_assets"
        / "geometry"
        / "ign_bdlje_2026-07-28"
    )
    reference = load_geometry_reference(
        root,
        expected_manifest_sha256=sha256(
            (root / "manifest.json").read_bytes()
        ).hexdigest(),
    )
    communities = {
        feature["properties"]["code"]: feature
        for feature in reference.features["autonomous_community"]
    }
    provinces = {
        feature["properties"]["code"]: feature
        for feature in reference.features["province"]
    }

    assert set(communities) == {f"{code:02d}" for code in range(1, 20)}
    assert set(provinces) == {f"{code:02d}" for code in range(1, 53)}
    assert communities["18"]["properties"]["name"] == "Ciudad Autónoma de Ceuta"
    assert communities["19"]["properties"]["name"] == "Ciudad Autónoma de Melilla"
    ceuta_bounds = _feature_bounds(communities["18"])
    melilla_bounds = _feature_bounds(communities["19"])
    assert -6.0 < ceuta_bounds[0] < -5.0 and 35.0 < ceuta_bounds[1] < 36.5
    assert -3.5 < melilla_bounds[0] < -2.5 and 35.0 < melilla_bounds[1] < 36.5


def test_versioned_country_context_is_local_complete_and_public_domain() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "app_assets"
        / "geometry"
        / "natural_earth"
    )
    reference = load_country_context_reference(
        root,
        expected_manifest_sha256=sha256(
            (root / "manifest.json").read_bytes()
        ).hexdigest(),
    )
    names = {
        feature["properties"]["name"]
        for feature in reference.collection["features"]
    }

    assert len(names) == 177
    assert names >= {"Spain", "Portugal", "France", "Morocco", "Algeria"}
    assert reference.manifest["source"]["scale"] == "1:110m"
    assert reference.manifest["source"]["license"] == "Public domain"


def test_project_map_receives_only_selected_municipalities_with_parent_context(
) -> None:
    features = tuple(
        {
            "type": "Feature",
            "id": f"municipality:{code}",
            "properties": {
                "level": "municipality",
                "code": code,
                "name": name,
                "autonomous_community_code": "01",
                "province_code": "41",
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[x, 0], [x + 0.2, 0], [x + 0.2, 0.2], [x, 0]]]],
            },
        }
        for x, code, name in (
            (0.0, "41001", "Alanís"),
            (1.0, "41091", "Sevilla"),
            (2.0, "41092", "Tocina"),
        )
    )

    selected, missing = select_geometry_features(features, codes=("41001", "41092"))

    assert missing == ()
    assert [feature["properties"]["code"] for feature in selected] == [
        "41001",
        "41092",
    ]
    map_view = build_folium_project_map(
        {"type": "FeatureCollection", "features": list(selected)},
        country_context=_country_context_collection(),
    )
    assert not any(
        isinstance(child, folium.raster_layers.TileLayer)
        for child in map_view._children.values()
    )
    rendered = next(
        child
        for child in map_view._children.values()
        if isinstance(child, GeoJson)
        and "level" in child.data["features"][0]["properties"]
    )
    assert [
        feature["properties"]["name"] for feature in rendered.data["features"]
    ] == ["Alanís", "Tocina"]
