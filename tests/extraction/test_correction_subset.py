from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.extraction.config import EXTRACTION_CONFIG_ID
from renewables_permitting.extraction.correction_subset import (
    AdministrativeActionCorrectionsSubsetError,
    load_administrative_action_corrections_subset,
    materialize_administrative_action_corrections_subset,
    plan_administrative_action_corrections_subset,
)
from renewables_permitting.extraction.corrections import (
    ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
    AdministrativeActionCorrectionError,
    evidence_sha256,
    load_administrative_action_corrections,
)
from renewables_permitting.extraction.models import (
    AdministrativeAction,
    AdministrativeActionType,
    AdministrativeDecision,
    BOEProjectExtraction,
    ClassificationStatus,
    DocumentScope,
    GenerationAssetMention,
    GenerationType,
    PublicationEvent,
)


SNAPSHOT_ID = "a" * 64
CODE_SHA256 = "b" * 64


def _action(evidence: str) -> AdministrativeAction:
    return AdministrativeAction(
        action_type=AdministrativeActionType.PUBLIC_INFORMATION,
        decision=AdministrativeDecision.ANNOUNCED,
        targets=["generation_asset_1"],
        evidence=evidence,
    )


def _current_extractions(
    action_counts: dict[str, int],
) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    for boe_id, action_count in action_counts.items():
        actions = [
            _action(f"Actuación {index} publicada en {boe_id}.")
            for index in range(1, action_count + 1)
        ]
        extraction = BOEProjectExtraction(
            classification_status=ClassificationStatus.CLASSIFIED,
            document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
            classification_reason="Documento específico de generación.",
            publication_events=[PublicationEvent(
                generation_assets=[GenerationAssetMention(
                    local_generation_asset_ref="generation_asset_1",
                    names_raw=[f"Planta {boe_id}"],
                    generation_type=GenerationType.PHOTOVOLTAIC,
                    evidence=f"Proyecto publicado en {boe_id}.",
                )],
                administrative_actions=actions,
                event_summary="Actuaciones publicadas.",
            )],
            extraction_notes=None,
            boe_id=boe_id,
            publication_date=date(2026, 8, 26),
        )
        records.append({
            "identificador_boe": boe_id,
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "extraction_json": extraction.model_dump_json(),
        })
    return pd.DataFrame(records)


def _correction(
    boe_id: str,
    action_index: int,
    *,
    correction_id: str | None = None,
) -> dict[str, object]:
    evidence = f"Actuación {action_index} publicada en {boe_id}."
    return {
        "correction_id": correction_id or (
            f"historical-action-exclusion-{boe_id.lower()}-{action_index}"
        ),
        "correction_version": 1,
        "status": "approved",
        "boe_id": boe_id,
        "entity_type": "administrative_action",
        "operation": "exclude",
        "administrative_action_id": (
            f"{boe_id}_event_1_action_{action_index}"
        ),
        "expected_action_type": "informacion_publica",
        "expected_decision": "convocado",
        "expected_evidence_sha256": evidence_sha256(evidence),
        "reason_code": "historical_antecedent_misattributed",
        "reason": "Es un antecedente histórico.",
        "decision_source": "human_decision:test",
        "reviewed_on": "2026-08-26",
        "reviewer": "human_tfm_review",
    }


def _write_master(
    tmp_path: Path,
    rows: list[dict[str, object]],
) -> Path:
    path = tmp_path / "master.csv"
    pd.DataFrame(
        rows,
        columns=ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
    ).to_csv(path, index=False)
    return path


def _plan(
    master_path: Path,
    current: pd.DataFrame,
    corpus_boe_ids: list[str],
):
    return plan_administrative_action_corrections_subset(
        corrections=load_administrative_action_corrections(master_path),
        current_extractions=current,
        corpus_boe_ids=corpus_boe_ids,
        source_extraction_snapshot_id=SNAPSHOT_ID,
        extraction_config_id=EXTRACTION_CONFIG_ID,
        deterministic_code_sha256=CODE_SHA256,
    )


def test_subset_selects_only_valid_corrections_in_document_universe(
    tmp_path: Path,
) -> None:
    master_path = _write_master(tmp_path, [
        _correction("BOE-A-2026-101", 1),
        _correction("BOE-A-2026-202", 1),
    ])
    before = master_path.read_bytes()

    plan = _plan(
        master_path,
        _current_extractions({"BOE-A-2026-101": 2}),
        ["BOE-A-2026-101"],
    )

    assert plan.selected_correction_ids == (
        "historical-action-exclusion-boe-a-2026-101-1",
    )
    assert plan.out_of_scope_correction_ids == (
        "historical-action-exclusion-boe-a-2026-202-1",
    )
    assert len(plan.selected_corrections) == 1
    assert plan.selected_corrections.iloc[0].to_dict() == (
        plan.parent_corrections.corrections.iloc[0].to_dict()
    )
    derived = materialize_administrative_action_corrections_subset(
        plan,
        output_dir=tmp_path / "derived",
    )
    silver_input = load_administrative_action_corrections(
        derived.corrections_path
    )
    assert len(silver_input.corrections) == 1
    assert silver_input.corrections.iloc[0].to_dict() == (
        plan.parent_corrections.corrections.iloc[0].to_dict()
    )
    assert master_path.read_bytes() == before


def test_subset_supports_empty_selected_registry_and_round_trip(
    tmp_path: Path,
) -> None:
    master_path = _write_master(tmp_path, [
        _correction("BOE-A-2026-101", 1),
        _correction("BOE-A-2026-202", 1),
    ])
    plan = _plan(
        master_path,
        _current_extractions({"BOE-A-2026-303": 2}),
        ["BOE-A-2026-303"],
    )

    first = materialize_administrative_action_corrections_subset(
        plan,
        output_dir=tmp_path / "first",
        created_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    second = materialize_administrative_action_corrections_subset(
        plan,
        output_dir=tmp_path / "second",
        created_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    loaded = load_administrative_action_corrections_subset(
        first.output_dir,
        expected_extraction_snapshot_id=SNAPSHOT_ID,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert loaded.corrections.empty
    assert tuple(loaded.corrections.columns) == (
        ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS
    )
    assert loaded.manifest["subset"]["selected_correction_count"] == 0
    assert loaded.manifest["subset"]["out_of_scope_correction_count"] == 2
    assert first.materialization_identity == second.materialization_identity
    assert first.corrections_path.read_bytes() == second.corrections_path.read_bytes()
    with pytest.raises(AdministrativeActionCorrectionError, match="vacío"):
        load_administrative_action_corrections(first.corrections_path)


def test_subset_fails_closed_for_missing_target_in_scope(tmp_path: Path) -> None:
    row = _correction("BOE-A-2026-101", 1)
    row["administrative_action_id"] = "BOE-A-2026-101_event_1_action_99"
    master_path = _write_master(tmp_path, [row])

    with pytest.raises(AdministrativeActionCorrectionError, match="0 targets"):
        _plan(
            master_path,
            _current_extractions({"BOE-A-2026-101": 2}),
            ["BOE-A-2026-101"],
        )


def test_subset_fails_closed_for_multiple_targets_in_scope(
    tmp_path: Path,
) -> None:
    master_path = _write_master(
        tmp_path,
        [_correction("BOE-A-2026-101", 1)],
    )
    current = _current_extractions({"BOE-A-2026-101": 2})
    duplicated = pd.concat([current, current], ignore_index=True)

    with pytest.raises(AdministrativeActionCorrectionError, match="2 targets"):
        _plan(master_path, duplicated, ["BOE-A-2026-101"])


def test_subset_fails_closed_for_in_scope_fingerprint_mismatch(
    tmp_path: Path,
) -> None:
    row = _correction("BOE-A-2026-101", 1)
    row["expected_evidence_sha256"] = "f" * 64
    master_path = _write_master(tmp_path, [row])

    with pytest.raises(AdministrativeActionCorrectionError, match="fingerprint"):
        _plan(
            master_path,
            _current_extractions({"BOE-A-2026-101": 2}),
            ["BOE-A-2026-101"],
        )


def test_subset_does_not_validate_fingerprint_outside_document_universe(
    tmp_path: Path,
) -> None:
    row = _correction("BOE-A-2026-101", 1)
    row["expected_evidence_sha256"] = "f" * 64
    master_path = _write_master(tmp_path, [row])

    plan = _plan(
        master_path,
        _current_extractions({"BOE-A-2026-202": 2}),
        ["BOE-A-2026-202"],
    )

    assert plan.selected_corrections.empty
    assert plan.out_of_scope_correction_ids == (
        "historical-action-exclusion-boe-a-2026-101-1",
    )


def test_subset_rejects_invalid_master_before_selection(tmp_path: Path) -> None:
    rows = [
        _correction("BOE-A-2026-101", 1),
        _correction("BOE-A-2026-202", 1),
    ]
    rows[1]["correction_id"] = rows[0]["correction_id"]
    duplicate_path = _write_master(tmp_path, rows)

    with pytest.raises(AdministrativeActionCorrectionError, match="duplicados"):
        load_administrative_action_corrections(duplicate_path)

    invalid = pd.DataFrame(
        [_correction("BOE-A-2026-101", 1)],
        columns=ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
    ).drop(columns=["reason"])
    invalid_path = tmp_path / "invalid.csv"
    invalid.to_csv(invalid_path, index=False)
    with pytest.raises(AdministrativeActionCorrectionError, match="columnas"):
        load_administrative_action_corrections(invalid_path)


def test_subset_future_master_selects_eleven_and_excludes_five(
    tmp_path: Path,
) -> None:
    selected_boe = "BOE-A-2026-111"
    selected = [
        _correction(selected_boe, index)
        for index in range(1, 12)
    ]
    out_of_scope = [
        _correction(
            f"BOE-A-2025-{200 + index}",
            1,
            correction_id=f"historical-action-exclusion-old-{index}",
        )
        for index in range(1, 6)
    ]
    master_path = _write_master(tmp_path, [*out_of_scope, *selected])

    first = _plan(
        master_path,
        _current_extractions({selected_boe: 12}),
        [selected_boe],
    )
    second = _plan(
        master_path,
        _current_extractions({selected_boe: 12}),
        [selected_boe],
    )

    assert len(first.parent_corrections.corrections) == 16
    assert len(first.selected_corrections) == 11
    assert len(first.out_of_scope_correction_ids) == 5
    assert first.materialization_identity == second.materialization_identity


def test_subset_failed_validation_does_not_publish_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master_path = _write_master(
        tmp_path,
        [_correction("BOE-A-2026-101", 1)],
    )
    plan = _plan(
        master_path,
        _current_extractions({"BOE-A-2026-202": 2}),
        ["BOE-A-2026-202"],
    )
    output = tmp_path / "must-not-exist"

    def fail_round_trip(*args, **kwargs):
        raise AdministrativeActionCorrectionsSubsetError("synthetic failure")

    monkeypatch.setattr(
        "renewables_permitting.extraction.correction_subset."
        "load_administrative_action_corrections_subset",
        fail_round_trip,
    )
    with pytest.raises(
        AdministrativeActionCorrectionsSubsetError,
        match="synthetic failure",
    ):
        materialize_administrative_action_corrections_subset(
            plan,
            output_dir=output,
        )

    assert not output.exists()
    assert list(tmp_path.glob(".must-not-exist.staging-*")) == []
