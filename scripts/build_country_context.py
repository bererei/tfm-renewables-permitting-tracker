"""Build the local Natural Earth country context used by Streamlit maps.

The input is the already available GeoPandas ``naturalearth_lowres`` dataset
copied into Pyogrio's test fixtures. It is a Natural Earth 1:110m country
dataset in EPSG:4326. The output remains separate from IGN administrative
geometry and is used only as a non-interactive orientation layer.
"""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from build_app_geometry import _iter_shp_polygons, _parse_dbf, _to_multipolygon
from renewables_permitting.app_geometry import (
    COUNTRY_CONTEXT_CONTRACT_VERSION,
    NATURAL_EARTH_ATTRIBUTION,
    NATURAL_EARTH_REQUIRED_COUNTRIES,
)


SOURCE_STEM = "naturalearth_lowres"
SOURCE_SUFFIXES = (".cpg", ".dbf", ".prj", ".shp", ".shx")
SOURCE_SHA256 = "ddfa7af6ff87ac6bfe7b216913462069244aa140fe2a30de61576cfde58a8c53"
ARTIFACT_NAME = "countries_context.geojson"
PROCESSING_VERSION = "natural_earth_country_context_v1"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_files(source_dir: Path) -> tuple[Path, ...]:
    files = tuple(source_dir / f"{SOURCE_STEM}{suffix}" for suffix in SOURCE_SUFFIXES)
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError("Falta algún fichero local de Natural Earth.")
    return files


def _source_fingerprint(files: tuple[Path, ...]) -> str:
    """Hash ordered source filenames and their physical SHA-256 digests."""

    digest = sha256()
    for path in sorted(files, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_country_context(
    *,
    source_dir: Path,
    output_dir: Path,
    expected_source_sha256: str = SOURCE_SHA256,
) -> tuple[Path, Path]:
    """Build deterministic, tile-free country context and its provenance manifest."""

    files = _source_files(source_dir)
    if _source_fingerprint(files) != expected_source_sha256:
        raise ValueError("La identidad de la fuente local Natural Earth no coincide.")
    projection = (source_dir / f"{SOURCE_STEM}.prj").read_text(encoding="ascii")
    if 'GEOGCS["GCS_WGS_1984"' not in projection:
        raise ValueError("Natural Earth no declara el CRS WGS84 esperado.")
    encoding = (
        source_dir / f"{SOURCE_STEM}.cpg"
    ).read_text(encoding="ascii").strip()
    if encoding.upper() != "ISO-8859-1":
        raise ValueError("Natural Earth no declara la codificación esperada.")
    records = _parse_dbf(
        (source_dir / f"{SOURCE_STEM}.dbf").read_bytes(),
        selected_fields={"iso_a3", "name"},
        encoding=encoding,
    )
    polygons = list(_iter_shp_polygons(
        (source_dir / f"{SOURCE_STEM}.shp").read_bytes()
    ))
    if len(records) != len(polygons):
        raise ValueError("Natural Earth no conserva la cardinalidad SHP/DBF.")
    features: list[dict[str, Any]] = []
    for record, rings in zip(records, polygons):
        if record is None or not rings:
            raise ValueError("Natural Earth contiene una feature eliminada o vacía.")
        name = record["name"]
        iso_a3 = record["iso_a3"]
        if not name or not iso_a3:
            raise ValueError("Natural Earth contiene una identidad de país vacía.")
        features.append({
            "type": "Feature",
            "properties": {"iso_a3": iso_a3, "name": name},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": _to_multipolygon(rings, tolerance=0.0),
            },
        })
    features.sort(key=lambda item: item["properties"]["name"])
    names = {str(feature["properties"]["name"]) for feature in features}
    if missing := NATURAL_EARTH_REQUIRED_COUNTRIES - names:
        raise ValueError(
            "Natural Earth no cubre el contexto mínimo: " + ", ".join(sorted(missing))
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_payload = json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    artifact_path = output_dir / ARTIFACT_NAME
    artifact_path.write_bytes(artifact_payload)
    manifest = {
        "contract_version": COUNTRY_CONTEXT_CONTRACT_VERSION,
        "artifact": {
            "file": ARTIFACT_NAME,
            "sha256": sha256(artifact_payload).hexdigest(),
        },
        "feature_count": len(features),
        "license_attribution": NATURAL_EARTH_ATTRIBUTION,
        "source": {
            "organization": "Natural Earth",
            "dataset": SOURCE_STEM,
            "scale": "1:110m",
            "version": "not declared by local fixture",
            "publication_date": None,
            "distribution": "GeoPandas naturalearth_lowres copied by Pyogrio",
            "source_crs": "EPSG:4326",
            "sha256": expected_source_sha256,
            "files": {
                path.name: _sha256_file(path)
                for path in sorted(files, key=lambda item: item.name)
            },
            "license": "Public domain",
            "website": "https://www.naturalearthdata.com/",
        },
        "processing": {
            "version": PROCESSING_VERSION,
            "output_crs": "EPSG:4326",
            "derivation": (
                "All source countries retained; Polygon records promoted to "
                "MultiPolygon; coordinates and natural positions unchanged."
            ),
            "properties": ["iso_a3", "name"],
            "feature_order": "name",
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact_path, manifest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", default=SOURCE_SHA256)
    return parser


def main() -> int:
    args = _parser().parse_args()
    artifact, manifest = build_country_context(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        expected_source_sha256=args.expected_source_sha256,
    )
    print(json.dumps({
        "artifact": {"path": str(artifact), "sha256": _sha256_file(artifact)},
        "manifest": str(manifest),
        "manifest_sha256": _sha256_file(manifest),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
