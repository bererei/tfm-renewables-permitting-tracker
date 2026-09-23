"""Build the administrative geometry used by the Streamlit maps.

The source archive is the official IGN/CNIG ``LINEAS_LIMITE.ZIP`` product.
CCAA/city and province references are complete; only municipalities referenced
by the validated Gold snapshot are retained for project detail.
The script uses the Python standard library so rebuilding the artifact does not
add a geospatial runtime dependency to the public application.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from collections.abc import Iterator, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from renewables_permitting.app_data import load_gold_dataset
from renewables_permitting.app_geometry import (
    BDLJE_ATTRIBUTION,
    GEOMETRY_CONTRACT_VERSION,
)


SOURCE_SHA256 = "d752b1b943e6c60f46a23119d6c3d4ad0b198461c502f0a5433197d7a5e34c83"
SOURCE_PUBLICATION_DATE = "2026-07-28"
SOURCE_CRS = {
    "peninsula_balearic_ceuta_melilla": "EPSG:4258",
    "canary_islands": "EPSG:4326",
}
ARTIFACT_NAMES = {
    "autonomous_community": "autonomous_communities.geojson",
    "province": "provinces.geojson",
    "municipality": "project_municipalities.geojson",
}
PROCESSING_VERSION = "ign_bdlje_app_geometry_v2"
LEVEL_SPECS = {
    "autonomous_community": {
        "tolerance": 0.005,
        "excluded_codes": {"20"},
        "sources": (
            (
                "SHP_ETRS89",
                "recintos_autonomicas_inspire_peninbal_etrs89",
                "EPSG:4258",
            ),
            (
                "SHP_WGS84",
                "recintos_autonomicas_inspire_canarias_wgs84",
                "EPSG:4326",
            ),
        ),
    },
    "province": {
        "tolerance": 0.0025,
        "excluded_codes": {"54"},
        "sources": (
            (
                "SHP_ETRS89",
                "recintos_provinciales_inspire_peninbal_etrs89",
                "EPSG:4258",
            ),
            (
                "SHP_WGS84",
                "recintos_provinciales_inspire_canarias_wgs84",
                "EPSG:4326",
            ),
        ),
    },
    "municipality": {
        "tolerance": 0.001,
        "excluded_codes": set(),
        "sources": (
            (
                "SHP_ETRS89",
                "recintos_municipales_inspire_peninbal_etrs89",
                "EPSG:4258",
            ),
            (
                "SHP_WGS84",
                "recintos_municipales_inspire_canarias_wgs84",
                "EPSG:4326",
            ),
        ),
    },
}


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _archive_member(root: str, stem: str, suffix: str) -> str:
    return f"{root}/{stem}/{stem}.{suffix}"


def _parse_dbf(
    payload: bytes,
    *,
    selected_fields: set[str] | None = None,
    encoding: str = "utf-8",
) -> list[dict[str, str] | None]:
    """Parse selected character fields from one dBASE table."""

    if len(payload) < 33:
        raise ValueError("El DBF de IGN está truncado.")
    record_count = struct.unpack_from("<I", payload, 4)[0]
    header_length = struct.unpack_from("<H", payload, 8)[0]
    record_length = struct.unpack_from("<H", payload, 10)[0]
    if header_length < 33 or record_length < 2:
        raise ValueError("La cabecera DBF de IGN no es válida.")
    fields: list[tuple[str, str, int]] = []
    offset = 32
    while offset + 32 <= header_length and payload[offset] != 0x0D:
        descriptor = payload[offset : offset + 32]
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii")
        field_type = chr(descriptor[11])
        length = descriptor[16]
        if field_type != "C" and (
            selected_fields is None or name in selected_fields
        ):
            raise ValueError(f"Campo DBF no soportado: {name} ({field_type}).")
        fields.append((name, field_type, length))
        offset += 32
    if not fields or header_length + record_count * record_length > len(payload):
        raise ValueError("La estructura DBF de IGN no coincide con su cabecera.")
    observed = {name for name, _, _ in fields}
    if selected_fields is not None and not selected_fields <= observed:
        raise ValueError("El DBF no contiene todos los campos seleccionados.")
    records: list[dict[str, str] | None] = []
    for index in range(record_count):
        start = header_length + index * record_length
        record = payload[start : start + record_length]
        if len(record) != record_length:
            raise ValueError("El DBF de IGN contiene un registro truncado.")
        if record[:1] == b"*":
            records.append(None)
            continue
        values: dict[str, str] = {}
        cursor = 1
        for name, field_type, length in fields:
            raw = record[cursor : cursor + length]
            if selected_fields is None or name in selected_fields:
                if field_type != "C":
                    raise ValueError(
                        f"Campo DBF no soportado: {name} ({field_type})."
                    )
                values[name] = raw.decode(encoding).strip()
            cursor += length
        records.append(values)
    return records


def _iter_shp_polygons(payload: bytes) -> Iterator[list[list[tuple[float, float]]]]:
    """Yield Polygon records from a little-endian ESRI Shapefile."""

    if len(payload) < 100 or struct.unpack_from(">i", payload, 0)[0] != 9994:
        raise ValueError("La cabecera SHP de IGN no es válida.")
    declared_length = struct.unpack_from(">i", payload, 24)[0] * 2
    if declared_length != len(payload) or struct.unpack_from("<i", payload, 32)[0] != 5:
        raise ValueError("El SHP no es un Polygon contractual completo.")
    cursor = 100
    while cursor < len(payload):
        if cursor + 8 > len(payload):
            raise ValueError("El SHP contiene una cabecera de registro truncada.")
        content_length = struct.unpack_from(">i", payload, cursor + 4)[0] * 2
        content_start = cursor + 8
        content_end = content_start + content_length
        if content_end > len(payload) or content_length < 4:
            raise ValueError("El SHP contiene un registro truncado.")
        shape_type = struct.unpack_from("<i", payload, content_start)[0]
        if shape_type == 0:
            yield []
        elif shape_type == 5:
            if content_length < 44:
                raise ValueError("El SHP contiene un polígono truncado.")
            part_count, point_count = struct.unpack_from(
                "<ii", payload, content_start + 36
            )
            parts_start = content_start + 44
            points_start = parts_start + part_count * 4
            if (
                part_count < 1
                or point_count < 4
                or points_start + point_count * 16 > content_end
            ):
                raise ValueError("El SHP contiene una estructura Polygon inválida.")
            part_indices = list(struct.unpack_from(
                f"<{part_count}i", payload, parts_start
            ))
            part_indices.append(point_count)
            points = [
                struct.unpack_from("<dd", payload, points_start + index * 16)
                for index in range(point_count)
            ]
            yield [
                points[part_indices[index] : part_indices[index + 1]]
                for index in range(part_count)
            ]
        else:
            raise ValueError(f"Tipo SHP no soportado: {shape_type}.")
        cursor = content_end


def _signed_area(ring: Sequence[tuple[float, float]]) -> float:
    return sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(ring, ring[1:])
    ) / 2


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    ratio = max(
        0.0,
        min(1.0, ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)),
    )
    return math.hypot(px - (sx + ratio * dx), py - (sy + ratio * dy))


def _rdp(
    points: Sequence[tuple[float, float]],
    tolerance: float,
) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return list(points)
    distances = [
        _point_segment_distance(point, points[0], points[-1])
        for point in points[1:-1]
    ]
    if not distances or max(distances) <= tolerance:
        return [points[0], points[-1]]
    split = distances.index(max(distances)) + 1
    return _rdp(points[: split + 1], tolerance)[:-1] + _rdp(
        points[split:], tolerance
    )


def _simplify_closed_ring(
    source: Sequence[tuple[float, float]],
    tolerance: float,
) -> list[list[float]]:
    """Simplify a closed ring without collapsing its coincident endpoints."""

    points = list(source)
    if points[0] != points[-1]:
        points.append(points[0])
    unique = points[:-1]
    if len(unique) < 3:
        raise ValueError("El SHP contiene un anillo degenerado.")
    anchor_index = min(range(len(unique)), key=lambda index: unique[index])
    unique = unique[anchor_index:] + unique[:anchor_index]
    opposite = max(
        range(1, len(unique)),
        key=lambda index: (
            (unique[index][0] - unique[0][0]) ** 2
            + (unique[index][1] - unique[0][1]) ** 2
        ),
    )
    first = _rdp(unique[: opposite + 1], tolerance)
    second = _rdp(unique[opposite:] + [unique[0]], tolerance)
    simplified = first[:-1] + second
    rounded = [[round(x, 6), round(y, 6)] for x, y in simplified]
    deduplicated = [rounded[0]]
    for point in rounded[1:]:
        if point != deduplicated[-1]:
            deduplicated.append(point)
    if deduplicated[-1] != deduplicated[0]:
        deduplicated.append(deduplicated[0])
    if len(deduplicated) < 4 or abs(_signed_area([
        (point[0], point[1]) for point in deduplicated
    ])) == 0:
        return [[round(x, 6), round(y, 6)] for x, y in points]
    return deduplicated


def _point_in_ring(
    point: tuple[float, float],
    ring: Sequence[tuple[float, float]],
) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y):
            intersection = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection:
                inside = not inside
    return inside


def _to_multipolygon(
    rings: Sequence[Sequence[tuple[float, float]]],
    tolerance: float,
) -> list[list[list[list[float]]]]:
    closed = []
    for source in rings:
        ring = list(source)
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) < 4:
            raise ValueError("El SHP contiene un anillo inválido.")
        closed.append(ring)
    outers = [ring for ring in closed if _signed_area(ring) < 0]
    holes = [ring for ring in closed if _signed_area(ring) >= 0]
    if not outers:
        raise ValueError("El Polygon de IGN no contiene anillos exteriores.")
    polygons: list[list[list[list[float]]]] = [
        [_simplify_closed_ring(outer, tolerance)] for outer in outers
    ]
    for hole in holes:
        candidates = [
            index
            for index, outer in enumerate(outers)
            if _point_in_ring(hole[0], outer)
        ]
        if not candidates:
            raise ValueError("Un hueco del Polygon no tiene exterior asociado.")
        parent = min(candidates, key=lambda index: abs(_signed_area(outers[index])))
        polygons[parent].append(_simplify_closed_ring(hole, tolerance))
    return polygons


def _codes_from_natcode(natcode: str) -> tuple[str, str, str]:
    if len(natcode) != 11 or not natcode.isdigit() or not natcode.startswith("34"):
        raise ValueError(f"NATCODE de IGN no válido: {natcode!r}.")
    return natcode[2:4], natcode[4:6], natcode[6:11]


def _selected_codes(gold_dir: Path, expected_downstream_id: str) -> dict[str, set[str]]:
    dataset = load_gold_dataset(
        gold_dir,
        expected_downstream_id=expected_downstream_id,
    )
    locations = dataset.project_locations
    return {
        "autonomous_community": set(
            locations["ine_autonomous_community_code"].dropna().astype(str)
        ),
        "province": set(locations["ine_province_code"].dropna().astype(str)),
        "municipality": set(
            locations.loc[
                locations["location_level"].eq("municipality"),
                "ine_municipality_code",
            ].dropna().astype(str)
        ),
    }


def _feature(
    *,
    level: str,
    record: dict[str, str],
    rings: Sequence[Sequence[tuple[float, float]]],
    tolerance: float,
) -> dict[str, Any]:
    community_code, province_code, municipality_code = _codes_from_natcode(
        record["NATCODE"]
    )
    code = {
        "autonomous_community": community_code,
        "province": province_code,
        "municipality": municipality_code,
    }[level]
    return {
        "type": "Feature",
        "id": f"{level}:{code}",
        "properties": {
            "level": level,
            "code": code,
            "name": record["NAMEUNIT"],
            "autonomous_community_code": community_code,
            "province_code": province_code
            if level != "autonomous_community"
            else None,
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": _to_multipolygon(rings, tolerance),
        },
    }


def build_geometry(
    *,
    source_zip: Path,
    gold_dir: Path,
    expected_downstream_id: str,
    output_dir: Path,
    expected_source_sha256: str = SOURCE_SHA256,
) -> tuple[dict[str, Path], Path]:
    """Build deterministic GeoJSON and provenance manifest from official input."""

    if _sha256_file(source_zip) != expected_source_sha256:
        raise ValueError("El hash del archivo oficial IGN/CNIG no coincide.")
    selected = _selected_codes(gold_dir, expected_downstream_id)
    features_by_level: dict[str, list[dict[str, Any]]] = {
        level: [] for level in LEVEL_SPECS
    }
    with ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        for level, spec in LEVEL_SPECS.items():
            observed: set[str] = set()
            for source_root, stem, source_crs in spec["sources"]:
                required = {
                    suffix: _archive_member(source_root, stem, suffix)
                    for suffix in ("cpg", "prj", "dbf", "shp")
                }
                if not set(required.values()) <= names:
                    raise ValueError(
                        f"Faltan capas contractuales de IGN para {level}."
                    )
                if archive.read(required["cpg"]).strip().upper() != b"UTF-8":
                    raise ValueError("La codificación de la capa IGN no es UTF-8.")
                projection = archive.read(required["prj"]).decode("ascii")
                if f'AUTHORITY["EPSG","{source_crs[5:]}"]' not in projection:
                    raise ValueError(
                        f"La capa IGN no declara {source_crs} geográfico."
                    )
                records = _parse_dbf(archive.read(required["dbf"]))
                polygons = _iter_shp_polygons(archive.read(required["shp"]))
                shape_count = 0
                for shape_count, rings in enumerate(polygons, start=1):
                    record = records[shape_count - 1]
                    if record is None:
                        continue
                    community, province, municipality = _codes_from_natcode(
                        record["NATCODE"]
                    )
                    code = {
                        "autonomous_community": community,
                        "province": province,
                        "municipality": municipality,
                    }[level]
                    if code in spec["excluded_codes"]:
                        continue
                    if level == "municipality" and code not in selected[level]:
                        continue
                    if code in observed:
                        raise ValueError(
                            f"Código IGN duplicado en {level}: {code}."
                        )
                    observed.add(code)
                    features_by_level[level].append(_feature(
                        level=level,
                        record=record,
                        rings=rings,
                        tolerance=float(spec["tolerance"]),
                    ))
                if shape_count != len(records):
                    raise ValueError(
                        "Los registros SHP y DBF no tienen igual cardinalidad."
                    )
            missing = selected[level] - observed
            if missing:
                raise ValueError(
                    f"Faltan códigos IGN para {level}: {', '.join(sorted(missing))}."
                )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, str]] = {}
    artifact_paths: dict[str, Path] = {}
    for level, features in features_by_level.items():
        features.sort(key=lambda item: item["properties"]["code"])
        artifact_payload = json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        artifact_path = output_dir / ARTIFACT_NAMES[level]
        artifact_path.write_bytes(artifact_payload)
        artifact_paths[level] = artifact_path
        artifacts[level] = {
            "file": ARTIFACT_NAMES[level],
            "sha256": sha256(artifact_payload).hexdigest(),
        }
    manifest = {
        "contract_version": GEOMETRY_CONTRACT_VERSION,
        "artifacts": artifacts,
        "source": {
            "organization": "IGN/CNIG",
            "series": "Límites municipales, provinciales y autonómicos",
            "product": "Límites y Unidades Administrativas Actuales",
            "catalog_url": (
                "https://centrodedescargas.cnig.es/CentroDescargas/"
                "limites-municipales-provinciales-autonomicos"
            ),
            "file": "LINEAS_LIMITE.ZIP",
            "publication_date": SOURCE_PUBLICATION_DATE,
            "sha256": expected_source_sha256,
        },
        "processing": {
            "version": PROCESSING_VERSION,
            "source_crs": SOURCE_CRS,
            "output_crs": "WGS84-compatible GeoJSON",
            "selected_from_gold_downstream_id": expected_downstream_id,
            "simplification_tolerance_degrees": {
                level: spec["tolerance"] for level, spec in LEVEL_SPECS.items()
            },
        },
        "code_fields": {
            "autonomous_community": "code",
            "province": "code",
            "municipality": "code",
        },
        "feature_counts": {
            level: len(features_by_level[level]) for level in LEVEL_SPECS
        },
        "license_attribution": BDLJE_ATTRIBUTION,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact_paths, manifest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--gold-dir", type=Path, required=True)
    parser.add_argument("--expected-downstream-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", default=SOURCE_SHA256)
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifacts, manifest = build_geometry(
        source_zip=args.source_zip,
        gold_dir=args.gold_dir,
        expected_downstream_id=args.expected_downstream_id,
        output_dir=args.output_dir,
        expected_source_sha256=args.expected_source_sha256,
    )
    print(json.dumps({
        "artifacts": {
            level: {
                "path": str(path),
                "sha256": _sha256_file(path),
            }
            for level, path in artifacts.items()
        },
        "manifest": str(manifest),
        "manifest_sha256": _sha256_file(manifest),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
