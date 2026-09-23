import pandas as pd
import pytest

from renewables_permitting.boe_candidates import (
    BOE_CANDIDATE_COLUMNS,
    CANDIDATE_POLICY_ID,
    CANDIDATE_POLICY_VERSION,
    build_doc_file_stem,
    materialize_energy_candidates,
    select_energy_candidates,
)
from renewables_permitting.boe_source import BOE_ITEM_COLUMNS


def _items() -> pd.DataFrame:
    base = {column: pd.NA for column in BOE_ITEM_COLUMNS}
    records = []
    for boe_id, title, publication_date in (
        (
            "BOE-A-2026-2",
            "Resolución sobre el nombramiento de una profesora universitaria.",
            "2026-01-03",
        ),
        (
            "BOE-A-2026-1",
            "AUTORIZACIÓN del PARQUE-EÓLICO Aurora.",
            "2026-01-02",
        ),
    ):
        records.append({
            **base,
            "identificador": boe_id,
            "fecha_publicacion": pd.Timestamp(publication_date),
            "titulo": title,
            "url_xml": f"https://www.boe.es/xml.php?id={boe_id}",
            "url_html": f"https://www.boe.es/diario_boe/txt.php?id={boe_id}",
            "source": "boe",
            "summary_sha256": "a" * 64,
        })
    return pd.DataFrame.from_records(records, columns=BOE_ITEM_COLUMNS)


def test_candidate_policy_is_title_only_normalized_versioned_and_deterministic() -> None:
    items = _items()
    snapshot = items.copy(deep=True)

    candidates = select_energy_candidates(items)
    repeated = select_energy_candidates(items.iloc[::-1].reset_index(drop=True))

    assert candidates["identificador"].tolist() == ["BOE-A-2026-1"]
    assert candidates["titulo_norm"].tolist() == [
        "autorizacion del parque eolico aurora"
    ]
    assert candidates["candidate_policy_version"].tolist() == [
        CANDIDATE_POLICY_VERSION
    ]
    assert candidates["candidate_policy_id"].tolist() == [
        CANDIDATE_POLICY_ID
    ]
    assert repeated["identificador"].tolist() == ["BOE-A-2026-1"]
    assert CANDIDATE_POLICY_ID == "79289feae5d557be"
    pd.testing.assert_frame_equal(items, snapshot)


def test_department_and_epigraph_alone_do_not_select_candidate() -> None:
    items = _items().iloc[[0]].copy()
    items.loc[:, "departamento_nombre"] = "Ministerio de Energía"
    items.loc[:, "epigrafe_nombre"] = "Energía eléctrica"

    assert select_energy_candidates(items).empty


def test_doc_file_stem_uses_document_identity_and_empty_contract_is_typed() -> None:
    assert build_doc_file_stem(
        "BOE-A-2026-1",
        pd.Timestamp("2026-01-02").date(),
    ) == "20260102_BOE-A-2026-1"
    with pytest.raises(ValueError, match="boe_id"):
        build_doc_file_stem("../unsafe", pd.Timestamp("2026-01-02").date())

    empty = select_energy_candidates(
        pd.DataFrame(columns=BOE_ITEM_COLUMNS)
    )
    assert empty.columns.tolist() == list(BOE_CANDIDATE_COLUMNS)
    assert str(empty["identificador"].dtype) == "string"
    assert str(empty["fecha_publicacion"].dtype) == "datetime64[ns]"


def test_candidate_materialization_uses_only_explicit_path(tmp_path) -> None:
    candidates = select_energy_candidates(_items())
    output_path = tmp_path / "chosen" / "candidates.parquet"

    returned = materialize_energy_candidates(
        candidates,
        output_path=output_path,
    )
    restored = pd.read_parquet(returned)

    assert returned == output_path
    assert restored.columns.tolist() == list(BOE_CANDIDATE_COLUMNS)
    assert restored["identificador"].tolist() == ["BOE-A-2026-1"]
