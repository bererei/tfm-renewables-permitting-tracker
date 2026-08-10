from __future__ import annotations

import pandas as pd
import pytest

from renewables_permitting.location_resolution import (
    LOCATION_RESOLUTION_COLUMNS,
    AdministrativeUnitResolutionStatus,
    resolve_locations,
)


INPUT_COLUMNS = (
    "event_id",
    "identificador_boe",
    "fecha_publicacion",
    "location_mention_id",
    "location_name_raw",
    "location_level",
    "province_hint_raw",
    "autonomous_community_hint_raw",
    "evidence",
)


@pytest.fixture
def municipality_dimension() -> pd.DataFrame:
    rows = [
        ("03", "01", "001", "Villa Nueva", "Alfa", "Norte"),
        ("03", "01", "002", "San Pedro", "Alfa", "Norte"),
        ("04", "02", "001", "San Pedro", "Beta", "Sur"),
        ("01", "21", "006", "Alosno", "Huelva", "Andalucía"),
    ]
    dimension = pd.DataFrame(
        rows,
        columns=(
            "cauto",
            "cpro",
            "cmun",
            "municipio",
            "provincia",
            "comunidad_autonoma",
        ),
    ).astype("string")
    dimension["municipio_norm"] = (
        dimension["municipio"].str.lower().str.normalize("NFKD")
        .str.encode("ascii", errors="ignore").str.decode("utf-8")
    )
    dimension["provincia_norm"] = dimension["provincia"].str.lower()
    dimension["comunidad_autonoma_norm"] = (
        dimension["comunidad_autonoma"].str.lower().str.normalize("NFKD")
        .str.encode("ascii", errors="ignore").str.decode("utf-8")
    )
    dimension["municipio_lookup_names_norm"] = dimension[
        "municipio_norm"
    ].map(lambda value: [value])
    dimension["ine_municipality_code"] = (
        dimension["cpro"] + dimension["cmun"]
    )
    dimension["ine_province_code"] = dimension["cpro"]
    dimension["ine_autonomous_community_code"] = dimension["cauto"]
    return dimension


def _location_mentions(*rows: dict[str, object]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=INPUT_COLUMNS)
    frame["fecha_publicacion"] = pd.to_datetime(frame["fecha_publicacion"])
    for column in INPUT_COLUMNS:
        if column != "fecha_publicacion":
            frame[column] = frame[column].astype("string")
    return frame


def _mention(
    name: str,
    *,
    mention_id: str = "location_1",
    level: str = "municipio",
    province: str | None = None,
    autonomous_community: str | None = None,
) -> dict[str, object]:
    return {
        "event_id": "BOE-A-2026-1_event_1",
        "identificador_boe": "BOE-A-2026-1",
        "fecha_publicacion": "2026-08-09",
        "location_mention_id": mention_id,
        "location_name_raw": name,
        "location_level": level,
        "province_hint_raw": province,
        "autonomous_community_hint_raw": autonomous_community,
        "evidence": f"Localización administrativa: {name}.",
    }


def test_exact_municipality_resolves_complete_hierarchy(
    municipality_dimension: pd.DataFrame,
) -> None:
    resolved = resolve_locations(
        _location_mentions(_mention("Villa Nueva", province="Alfa")),
        municipality_dimension,
    ).iloc[0]

    assert resolved["municipality"] == "Villa Nueva"
    assert resolved["ine_municipality_code"] == "01001"
    assert resolved["province"] == "Alfa"
    assert resolved["ine_province_code"] == "01"
    assert resolved["autonomous_community"] == "Norte"
    assert resolved["ine_autonomous_community_code"] == "03"
    assert resolved["municipality_resolution_status"] == "resolved"
    assert resolved["province_resolution_status"] == "resolved"
    assert resolved["autonomous_community_resolution_status"] == "resolved"


def test_province_hint_disambiguates_homonymous_municipality(
    municipality_dimension: pd.DataFrame,
) -> None:
    resolved = resolve_locations(
        _location_mentions(_mention("San Pedro", province="Beta")),
        municipality_dimension,
    ).iloc[0]

    assert resolved["ine_municipality_code"] == "02001"
    assert resolved["ine_province_code"] == "02"
    assert resolved["ine_autonomous_community_code"] == "04"


def test_unknown_municipality_preserves_resolved_province_and_community(
    municipality_dimension: pd.DataFrame,
) -> None:
    resolved = resolve_locations(
        _location_mentions(_mention("Tharsis", province="Huelva")),
        municipality_dimension,
    ).iloc[0]

    assert pd.isna(resolved["municipality"])
    assert resolved["municipality_resolution_status"] == "not_found"
    assert resolved["province"] == "Huelva"
    assert resolved["ine_province_code"] == "21"
    assert resolved["province_resolution_status"] == "resolved"
    assert resolved["autonomous_community"] == "Andalucía"
    assert resolved["ine_autonomous_community_code"] == "01"
    assert resolved["autonomous_community_resolution_status"] == "resolved"


def test_unknown_province_does_not_invent_autonomous_community(
    municipality_dimension: pd.DataFrame,
) -> None:
    resolved = resolve_locations(
        _location_mentions(_mention("Lugar desconocido", province="Atlantis")),
        municipality_dimension,
    ).iloc[0]

    assert resolved["province_resolution_status"] == "not_found"
    assert pd.isna(resolved["ine_province_code"])
    assert resolved["autonomous_community_resolution_status"] != "resolved"
    assert pd.isna(resolved["ine_autonomous_community_code"])


def test_conflicting_province_hint_is_traced_without_overwriting_municipality(
    municipality_dimension: pd.DataFrame,
) -> None:
    resolved = resolve_locations(
        _location_mentions(_mention("Villa Nueva", province="Beta")),
        municipality_dimension,
    ).iloc[0]

    assert resolved["ine_municipality_code"] == "01001"
    assert resolved["province"] == "Alfa"
    assert resolved["ine_province_code"] == "01"
    assert resolved["province_resolution_status"] == "conflict"
    assert "contradice" in resolved["province_resolution_reason"]


@pytest.mark.parametrize(
    ("level", "name", "municipality_status", "province_status", "ac_status"),
    [
        ("provincia", "Huelva", "not_provided", "resolved", "resolved"),
        (
            "comunidad_autonoma",
            "Andalucía",
            "not_provided",
            "not_provided",
            "resolved",
        ),
    ],
)
def test_declared_administrative_level_is_respected(
    municipality_dimension: pd.DataFrame,
    level: str,
    name: str,
    municipality_status: str,
    province_status: str,
    ac_status: str,
) -> None:
    resolved = resolve_locations(
        _location_mentions(_mention(name, level=level)),
        municipality_dimension,
    ).iloc[0]

    assert resolved["municipality_resolution_status"] == municipality_status
    assert resolved["province_resolution_status"] == province_status
    assert resolved["autonomous_community_resolution_status"] == ac_status


def test_administrative_descriptors_do_not_prevent_exact_community_match(
    municipality_dimension: pd.DataFrame,
) -> None:
    resolved = resolve_locations(
        _location_mentions(
            _mention(
                "Comunidad Autónoma de Andalucía",
                level="comunidad_autonoma",
            )
        ),
        municipality_dimension,
    ).iloc[0]

    assert resolved["autonomous_community"] == "Andalucía"
    assert resolved["ine_autonomous_community_code"] == "01"
    assert resolved["autonomous_community_resolution_status"] == "resolved"
    assert (
        resolved["autonomous_community_resolution_matched_by"]
        == "autonomous_community_name_tokens"
    )


def test_empty_location_mentions_preserve_typed_output_contract(
    municipality_dimension: pd.DataFrame,
) -> None:
    input_frame = _location_mentions()

    resolved = resolve_locations(input_frame, municipality_dimension)

    assert resolved.empty
    assert tuple(resolved.columns) == INPUT_COLUMNS + LOCATION_RESOLUTION_COLUMNS
    assert all(
        str(resolved[column].dtype) == "string"
        for column in LOCATION_RESOLUTION_COLUMNS
    )


def test_resolution_is_deterministic_and_does_not_modify_inputs(
    municipality_dimension: pd.DataFrame,
) -> None:
    mentions = _location_mentions(
        _mention("San Pedro", province="Beta", mention_id="location_1"),
        _mention("Tharsis", province="Huelva", mention_id="location_2"),
    )
    original_mentions = mentions.copy(deep=True)
    original_dimension = municipality_dimension.copy(deep=True)

    first = resolve_locations(mentions, municipality_dimension)
    second = resolve_locations(
        mentions,
        municipality_dimension.sample(frac=1, random_state=42),
    )

    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(mentions, original_mentions)
    pd.testing.assert_frame_equal(municipality_dimension, original_dimension)


def test_status_enum_keeps_independent_administrative_states() -> None:
    assert {status.value for status in AdministrativeUnitResolutionStatus} == {
        "resolved",
        "ambiguous",
        "not_found",
        "not_provided",
        "conflict",
    }
