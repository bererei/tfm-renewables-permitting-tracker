from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.project_history import (
    PROJECT_HISTORY_POLICY_VERSION,
    ProjectHistoryBuild,
    ProjectSignature,
    build_project_history,
    load_project_history_materialization,
    materialize_project_history,
    project_history_materialization_identity,
    retrieve_project_history_candidates,
    select_historical_search_universe,
)


def _document(
    boe_id: str,
    text: str,
    *,
    publication_date: str = "2023-01-02",
) -> dict[str, object]:
    return {
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp(publication_date),
        "titulo": text,
        "texto_limpio": text,
        "source_document_sha256": (boe_id.encode().hex() + "0" * 64)[:64],
    }


def _signature(
    candidate_id: str = "anchor_candidate_a",
    *,
    aliases: tuple[str, ...] = ("parque eolico ejemplo",),
    keys: tuple[str, ...] = ("ejemplo",),
    locations: tuple[str, ...] = (),
    generation_types: tuple[str, ...] = ("eolica",),
) -> ProjectSignature:
    return ProjectSignature(
        anchor_project_candidate_id=candidate_id,
        aliases=aliases,
        normalized_name_keys=keys,
        locations=locations,
        generation_types=generation_types,
    )


def _retrieve(
    documents: list[dict[str, object]],
    *signatures: ProjectSignature,
) -> pd.DataFrame:
    return retrieve_project_history_candidates(
        signatures or (_signature(),), pd.DataFrame(documents)
    )


def test_tier_1_matches_exact_normalized_name_and_explicit_alias() -> None:
    links = _retrieve([
        _document("BOE-A-2023-1", "Se autoriza el Parque Eólico Ejemplo."),
        _document("BOE-A-2023-2", "Se autoriza PE Ejemplo Norte."),
    ], _signature(aliases=("parque eolico ejemplo", "pe ejemplo norte")))

    assert len(links) == 2
    assert set(links["match_tier"]) == {"tier_1_exact_alias"}
    assert set(links["retrieval_policy_version"]) == {
        PROJECT_HISTORY_POLICY_VERSION
    }


def test_generic_tokens_alone_do_not_match() -> None:
    links = _retrieve(
        [_document("BOE-A-2023-1", "Información sobre energía solar.")],
        _signature(
            aliases=("solar norte",),
            keys=("solar norte",),
            generation_types=("fotovoltaica",),
        ),
    )
    assert links.empty


@pytest.mark.parametrize(
    ("text", "locations", "generation_types", "expected"),
    [
        ("Monte tramita Azul como instalación fotovoltaica.", (), ("fotovoltaica",), True),
        ("Monte tramita Azul sin más datos.", (), ("fotovoltaica",), False),
        ("Monte tramita Azul como parque eólico.", (), ("fotovoltaica",), False),
        ("Monte tramita Azul en Alosno.", ("alosno",), ("fotovoltaica",), True),
    ],
)
def test_tier_2_strict_requires_audited_corroboration(
    text: str,
    locations: tuple[str, ...],
    generation_types: tuple[str, ...],
    expected: bool,
) -> None:
    links = _retrieve(
        [_document("BOE-A-2023-1", text)],
        _signature(
            aliases=("monte azul",),
            keys=("monte azul",),
            locations=locations,
            generation_types=generation_types,
        ),
    )
    assert (len(links) == 1) is expected
    if expected:
        assert links.iloc[0]["match_tier"] == "tier_2_strict"


def test_multi_project_boe_preserves_links_but_duplicate_evidence_does_not() -> None:
    document = _document(
        "BOE-A-2023-1",
        "Monte y Azul son fotovoltaicos; Valle y Claro son eólicos.",
    )
    first = _signature(
        "anchor_candidate_a",
        aliases=("monte azul", "monte azul"),
        keys=("monte azul",),
        generation_types=("fotovoltaica",),
    )
    second = _signature(
        "anchor_candidate_b",
        aliases=("valle claro",),
        keys=("valle claro",),
        generation_types=("eolica",),
    )
    links = _retrieve([document], first, second)
    assert len(links) == 2
    assert links["historical_boe_id"].nunique() == 1
    assert not links.duplicated(
        ["anchor_project_candidate_id", "historical_boe_id"]
    ).any()


def test_tier_3_style_match_is_not_implemented() -> None:
    links = _retrieve(
        [_document("BOE-A-2023-1", "Monte aparece y después Azul aparece.")],
        _signature(aliases=("monte azul",), keys=("monte azul",)),
    )
    assert links.empty


def test_versioned_longitudinal_regression_recovers_five_of_five() -> None:
    documents = [
        _document("BOE-A-2023-10306", "Parque Eólico Badulaque."),
        _document("BOE-A-2023-2598", "Parque Eólico Badulaque."),
        _document("BOE-B-2023-19082", "Parque Eólico Badulaque."),
        _document("BOE-A-2023-2595", "Planta Volateo Solar."),
        _document("BOE-A-2024-9608", "Instalación solar FV La Puebla 1."),
    ]
    signatures = (
        _signature("badulaque", aliases=("parque eolico badulaque",)),
        _signature(
            "volateo", aliases=("volateo solar",),
            generation_types=("fotovoltaica",),
        ),
        _signature(
            "la_puebla", aliases=("la puebla 1",),
            generation_types=("fotovoltaica",),
        ),
    )
    links = _retrieve(documents, *signatures)
    assert len(links) == 5
    assert set(links["match_tier"]) == {"tier_1_exact_alias"}


def test_search_universe_enforces_bounds_p2_boundary_and_holdout_before_text() -> None:
    documents = pd.DataFrame([
        _document("before", "secret", publication_date="2021-12-31"),
        _document("old", "eligible", publication_date="2023-01-01"),
        _document("p2-main", "eligible", publication_date="2025-01-01"),
        _document("not-main", "excluded", publication_date="2025-01-01"),
        _document("holdout", "must not be matched", publication_date="2025-01-01"),
        _document("anchor", "excluded", publication_date="2026-08-07"),
    ])
    source = select_historical_search_universe(
        documents,
        p2_main_boe_ids={"p2-main", "holdout"},
        holdout_boe_ids={"holdout"},
        history_start=date(2022, 1, 1),
        history_end=date(2026, 8, 6),
    )
    assert source["identificador"].tolist() == ["old", "p2-main"]


def test_source_drift_fails_closed_before_retrieval() -> None:
    source = pd.DataFrame([_document("anchor", "Anchor", publication_date="2026-08-07")])
    current = pd.DataFrame({
        "identificador_boe": pd.Series(["anchor"], dtype="string"),
        "source_document_sha256": pd.Series(
            [source.iloc[0]["source_document_sha256"]], dtype="string"
        ),
    })
    anchor_scope = pd.DataFrame({
        "identificador_boe": ["anchor"],
        "source_document_sha256": ["f" * 64],
    })
    empty_scope = pd.DataFrame({
        "identificador_boe": pd.Series(dtype="string"),
        "source_document_sha256": pd.Series(dtype="string"),
    })

    with pytest.raises(ValueError, match="Source drift.*anchor scope"):
        build_project_history(
            source_documents=source,
            anchor_current_extractions=current,
            municipality_dimension=pd.DataFrame(),
            anchor_scope=anchor_scope,
            p2_main_scope=empty_scope,
            holdout_scope=empty_scope,
            anchor_snapshot_id="a" * 64,
            history_start=date(2022, 1, 1),
            history_end=date(2026, 8, 6),
        )


def _empty_build() -> ProjectHistoryBuild:
    from renewables_permitting.project_history import (
        ANCHOR_PROJECT_CANDIDATE_COLUMNS,
        HISTORICAL_SCOPE_COLUMNS,
        PROJECT_HISTORY_CANDIDATE_COLUMNS,
    )

    anchor = pd.DataFrame({
        column: pd.Series(dtype="string")
        for column in ANCHOR_PROJECT_CANDIDATE_COLUMNS
    })
    links = pd.DataFrame({
        column: pd.Series(dtype="datetime64[ns]" if column == "publication_date" else "string")
        for column in PROJECT_HISTORY_CANDIDATE_COLUMNS
    })
    scope = pd.DataFrame({
        "identificador_boe": pd.Series(dtype="string"),
        "publication_date": pd.Series(dtype="datetime64[ns]"),
        "source_document_sha256": pd.Series(dtype="string"),
    }).loc[:, HISTORICAL_SCOPE_COLUMNS]
    return ProjectHistoryBuild(anchor, links, scope, 0, 0)


def test_materialization_identity_is_timestamp_independent_and_loader_validates(
    tmp_path: Path,
) -> None:
    build = _empty_build()
    arguments = dict(
        source_snapshot_id="s" * 64,
        anchor_snapshot_id="a" * 64,
        anchor_scope_fingerprint="b" * 64,
        ine_reference_sha256="i" * 64,
        p2_main_scope_fingerprint="p" * 64,
        holdout_scope_fingerprint="h" * 64,
        history_start=date(2022, 1, 1),
        history_end=date(2026, 8, 6),
        code_sha256="c" * 64,
    )
    first = materialize_project_history(
        build, output_dir=tmp_path / "one",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), **arguments,
    )
    second = materialize_project_history(
        build, output_dir=tmp_path / "two",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), **arguments,
    )
    assert first.manifest["materialization_identity_sha256"] == second.manifest[
        "materialization_identity_sha256"
    ]
    assert load_project_history_materialization(first.output_dir).historical_scope.empty
    assert project_history_materialization_identity(
        build,
        source_snapshot_id=arguments["source_snapshot_id"],
        anchor_snapshot_id=arguments["anchor_snapshot_id"],
        anchor_scope_fingerprint=arguments["anchor_scope_fingerprint"],
        ine_reference_sha256=arguments["ine_reference_sha256"],
        history_start=arguments["history_start"],
        history_end=arguments["history_end"],
        code_sha256=arguments["code_sha256"],
    ) == first.manifest["materialization_identity_sha256"]
