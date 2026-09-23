from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

import pandas as pd
import pytest

from renewables_permitting.ine_reference import (
    MUNICIPALITY_DIMENSION_COLUMNS,
    MUNICIPALITY_LOGICAL_KEY,
    MUNICIPALITY_REFERENCE_CONTRACT_VERSION,
    build_municipality_dimension,
    compare_municipality_dimensions,
    compute_municipality_reference_hash,
    compute_municipality_reference_id,
    load_ine_source_tables,
    materialize_municipality_dimension,
    validate_municipality_dimension,
)
from renewables_permitting.location_resolution import resolve_locations


def _source_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    codine = pd.DataFrame(
        [
            ("1", "Andalucía", "21", "Huelva"),
            ("1", "Andalucía", "29", "Málaga"),
            ("16", "País Vasco", "1", "Araba/Álava"),
        ],
        columns=("codauto", "comunidad_autonoma", "cpro", "provincia"),
    ).astype("string")
    dictionary = pd.DataFrame(
        [
            ("1", "21", "6", "0", "Alosno"),
            ("1", "21", "24", "5", "El Cerro de Andévalo"),
            ("1", "29", "1", "1", "Alameda"),
            ("16", "1", "51", "3", "Agurain/Salvatierra"),
        ],
        columns=("codauto", "cpro", "cmun", "dc", "nombre"),
    ).astype("string")
    return codine, dictionary


def _write_sources(tmp_path):
    codine, dictionary = _source_tables()
    codine_path = tmp_path / "province-reference.csv"
    dictionary_path = tmp_path / "municipality-reference.csv"
    codine.to_csv(codine_path, index=False, encoding="utf-8-sig")
    dictionary.to_csv(dictionary_path, index=False, encoding="utf-8-sig")
    return codine_path, dictionary_path


def _location_mentions() -> pd.DataFrame:
    frame = pd.DataFrame([{
        "event_id": "BOE-A-2026-1_event_1",
        "identificador_boe": "BOE-A-2026-1",
        "fecha_publicacion": "2026-08-10",
        "location_mention_id": "location_1",
        "location_name_raw": "Tharsis",
        "location_level": "municipio",
        "province_hint_raw": "Huelva",
        "autonomous_community_hint_raw": None,
        "evidence": "Término municipal de Tharsis, en Huelva.",
    }])
    frame["fecha_publicacion"] = pd.to_datetime(frame["fecha_publicacion"])
    for column in frame.columns:
        if column != "fecha_publicacion":
            frame[column] = frame[column].astype("string")
    return frame


def test_build_dimension_preserves_contract_padding_aliases_and_inputs() -> None:
    codine, dictionary = _source_tables()
    codine_snapshot = codine.copy(deep=True)
    dictionary_snapshot = dictionary.copy(deep=True)

    dimension = build_municipality_dimension(codine, dictionary)

    assert dimension.columns.tolist() == list(MUNICIPALITY_DIMENSION_COLUMNS)
    assert dimension["ine_municipality_code"].tolist() == [
        "01051", "21006", "21024", "29001",
    ]
    assert dimension.loc[0, "cauto"] == "16"
    assert dimension.loc[0, "cpro"] == "01"
    assert dimension.loc[0, "cmun"] == "051"
    assert dimension.loc[0, "dc"] == "3"
    assert dimension.loc[0, "municipio_lookup_names_norm"] == [
        "agurain", "agurain salvatierra", "salvatierra",
    ]
    assert all(
        str(dimension[column].dtype) == "string"
        for column in MUNICIPALITY_DIMENSION_COLUMNS
        if column != "municipio_lookup_names_norm"
    )
    assert str(dimension["municipio_lookup_names_norm"].dtype) == "object"
    pd.testing.assert_frame_equal(codine, codine_snapshot)
    pd.testing.assert_frame_equal(dictionary, dictionary_snapshot)


def test_build_rejects_duplicate_key_and_inconsistent_hierarchy() -> None:
    codine, dictionary = _source_tables()
    duplicate = pd.concat([dictionary, dictionary.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicad"):
        build_municipality_dimension(codine, duplicate)

    conflicting_province = pd.concat([
        codine,
        pd.DataFrame([{
            "codauto": "2",
            "comunidad_autonoma": "Aragón",
            "cpro": "21",
            "provincia": "Provincia conflictiva",
        }]).astype("string"),
    ], ignore_index=True)
    with pytest.raises(ValueError, match="provincia"):
        build_municipality_dimension(conflicting_province, dictionary)

    unmatched = dictionary.copy()
    unmatched.loc[0, "codauto"] = "2"
    with pytest.raises(ValueError, match="sin provincia"):
        build_municipality_dimension(codine, unmatched)


def test_validation_rejects_conflicting_names_and_empty_dimension() -> None:
    dimension = build_municipality_dimension(*_source_tables())
    conflicting = dimension.copy(deep=True)
    conflicting.loc[
        conflicting["ine_municipality_code"].eq("21024"), "provincia"
    ] = "Otra provincia"
    conflicting.loc[
        conflicting["ine_municipality_code"].eq("21024"), "provincia_norm"
    ] = "otra provincia"
    with pytest.raises(ValueError, match="jerarquía"):
        validate_municipality_dimension(conflicting)

    with pytest.raises(ValueError, match="vacía"):
        validate_municipality_dimension(dimension.iloc[0:0])


def test_input_order_does_not_change_dimension_or_semantic_identity() -> None:
    codine, dictionary = _source_tables()
    first = build_municipality_dimension(codine, dictionary)
    second = build_municipality_dimension(
        codine.sample(frac=1, random_state=7).reset_index(drop=True),
        dictionary.sample(frac=1, random_state=11).reset_index(drop=True),
    )

    pd.testing.assert_frame_equal(first, second)
    assert compute_municipality_reference_id(first) == (
        compute_municipality_reference_id(second)
    )
    assert compute_municipality_reference_hash(first) == (
        compute_municipality_reference_hash(second)
    )


def test_comparison_ignores_order_and_reports_added_removed_changed_codes() -> None:
    codine, dictionary = _source_tables()
    current = build_municipality_dimension(codine, dictionary)
    reordered = current.sample(frac=1, random_state=3).reset_index(drop=True)

    unchanged = compare_municipality_dimensions(current, reordered)
    assert unchanged.semantic_changed is False
    assert unchanged.requires_downstream_rebuild is False
    assert unchanged.old_reference_sha256 == unchanged.new_reference_sha256
    assert unchanged.added_codes == ()
    assert unchanged.removed_codes == ()
    assert unchanged.changed_codes == ()

    added_dictionary = pd.concat([
        dictionary,
        pd.DataFrame([{
            "codauto": "1",
            "cpro": "29",
            "cmun": "2",
            "dc": "6",
            "nombre": "Alcaucín",
        }]).astype("string"),
    ], ignore_index=True)
    added = build_municipality_dimension(codine, added_dictionary)
    added_comparison = compare_municipality_dimensions(current, added)
    assert added_comparison.semantic_changed is True
    assert added_comparison.requires_downstream_rebuild is True
    assert added_comparison.added_codes == ("29002",)

    removed = current.loc[
        ~current["ine_municipality_code"].eq("21024")
    ].reset_index(drop=True)
    removed_comparison = compare_municipality_dimensions(current, removed)
    assert removed_comparison.removed_codes == ("21024",)

    renamed_dictionary = dictionary.copy()
    renamed_dictionary.loc[
        renamed_dictionary["cmun"].eq("6"), "nombre"
    ] = "Alosno Nuevo"
    changed = build_municipality_dimension(codine, renamed_dictionary)
    changed_comparison = compare_municipality_dimensions(current, changed)
    assert changed_comparison.changed_codes == ("21006",)


def test_materialization_manifest_round_trip_and_safe_publication(tmp_path) -> None:
    codine_path, dictionary_path = _write_sources(tmp_path)
    codine, dictionary = load_ine_source_tables(
        codine_path,
        dictionary_path,
    )
    dimension = build_municipality_dimension(codine, dictionary)
    output_dir = tmp_path / "candidate-reference"

    result = materialize_municipality_dimension(
        dimension,
        output_dir=output_dir,
        codine_source_path=codine_path,
        dictionary_source_path=dictionary_path,
        created_at=datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    restored = pd.read_parquet(result.dimension_path)

    assert result.output_dir == output_dir
    assert manifest["reference_type"] == "ine_municipality_dimension"
    assert manifest["contract_version"] == (
        MUNICIPALITY_REFERENCE_CONTRACT_VERSION
    )
    assert manifest["semantic_reference_id"] == (
        compute_municipality_reference_id(dimension)
    )
    assert manifest["semantic_reference_sha256"] == (
        compute_municipality_reference_hash(dimension)
    )
    assert manifest["sources"]["codine"]["filename"] == codine_path.name
    assert manifest["sources"]["codine"]["sha256"] == sha256(
        codine_path.read_bytes()
    ).hexdigest()
    assert manifest["sources"]["dictionary"]["sha256"] == sha256(
        dictionary_path.read_bytes()
    ).hexdigest()
    assert manifest["sources"]["dictionary"]["row_count"] == len(dictionary)
    assert manifest["output"]["row_count"] == len(dimension)
    assert manifest["output"]["logical_key"] == list(
        MUNICIPALITY_LOGICAL_KEY
    )
    assert manifest["output"]["parquet_sha256"] == sha256(
        result.dimension_path.read_bytes()
    ).hexdigest()
    assert compare_municipality_dimensions(
        dimension,
        restored,
    ).semantic_changed is False
    validate_municipality_dimension(restored)

    parquet_before = result.dimension_path.read_bytes()
    with pytest.raises(FileExistsError, match="ya existe"):
        materialize_municipality_dimension(
            dimension,
            output_dir=output_dir,
            codine_source_path=codine_path,
            dictionary_source_path=dictionary_path,
        )
    assert result.dimension_path.read_bytes() == parquet_before


def test_failed_materialization_does_not_publish_partial_snapshot(tmp_path) -> None:
    codine_path, dictionary_path = _write_sources(tmp_path)
    codine, dictionary = load_ine_source_tables(
        codine_path,
        dictionary_path,
    )
    incomplete = build_municipality_dimension(codine, dictionary).iloc[:-1]
    output_dir = tmp_path / "must-not-exist"

    with pytest.raises(ValueError, match="fuentes"):
        materialize_municipality_dimension(
            incomplete,
            output_dir=output_dir,
            codine_source_path=codine_path,
            dictionary_source_path=dictionary_path,
        )

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".must-not-exist.staging-*"))


def test_built_dimension_is_directly_compatible_with_location_resolver() -> None:
    dimension = build_municipality_dimension(*_source_tables())

    resolved = resolve_locations(_location_mentions(), dimension).iloc[0]

    assert pd.isna(resolved["municipality"])
    assert resolved["municipality_resolution_status"] == "not_found"
    assert resolved["province"] == "Huelva"
    assert resolved["ine_province_code"] == "21"
    assert resolved["autonomous_community"] == "Andalucía"
    assert resolved["ine_autonomous_community_code"] == "01"
