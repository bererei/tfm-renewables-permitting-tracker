from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.corrections import (
    AdministrativeActionCorrectionError,
    apply_administrative_action_corrections,
    corrections_identity,
    evidence_sha256,
    load_administrative_action_corrections,
    validate_administrative_action_corrections,
)
from renewables_permitting.extraction.flatten import (
    flatten_current_extractions,
)
from renewables_permitting.extraction.flat_materialization import (
    load_flat_materialization,
    materialize_current_extractions,
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


REGISTRY_PATH = Path(
    "config/corrections/administrative_action_corrections.csv"
)

EVIDENCE = {
    "BOE-A-2024-16662_event_1_action_1": (
        "Resolución de 10 de julio de 2024, de la Dirección General de "
        "Política Energética y Minas, por la que se desestima la solicitud "
        "de El Refugio Fotovoltaico, SLU, de autorización administrativa "
        "previa del parque fotovoltaico El Refugio, de 116,55 MW de potencia "
        "instalada, y de su infraestructura de evacuación, en las "
        "provincias de Toledo y Madrid."
    ),
    "BOE-A-2024-16662_event_1_action_2": (
        "La Dirección General de Calidad y Evaluación Ambiental emite, con "
        "fecha 7 de marzo de 2024, resolución por la que formula declaración "
        "de impacto ambiental desfavorable para el parque solar fotovoltaico "
        "El Refugio y su infraestructura de evacuación asociada"
    ),
    "BOE-A-2024-16662_event_1_action_3": (
        "Con fecha de 22 de marzo de 2024 se notifica el trámite de audiencia "
        "sobre la propuesta de resolución por la que se desestima la solicitud "
        "de autorización administrativa previa del proyecto."
    ),
    "BOE-A-2024-9608_event_1_action_1": (
        "solicitud de inicio de tramitación de procedimiento de determinación "
        "de afección ambiental del proyecto «Instalación solar FV La Puebla "
        "1 [...] promovido por Jinko Greenfield Spain 3, SL"
    ),
    "BOE-A-2024-9608_event_1_action_2": (
        "se procede a requerir la subsanación con fecha 9 de noviembre de "
        "2023, documentación que es remitida por el promotor el 8 de enero 2024."
    ),
    "BOE-A-2024-9608_event_1_action_3": (
        "Resolución de 6 de mayo de 2024, de la Dirección General de Calidad "
        "y Evaluación Ambiental, por la que se formula informe de determinación "
        'de afección ambiental del proyecto "Instalación solar FV La Puebla '
        '1, de 100 MW de potencia instalada, en la provincia de Huelva".'
    ),
    "BOE-A-2025-26110_event_1_action_1": (
        "Resolución de 17 de noviembre de 2025, de la Dirección General de "
        "Política Energética y Minas, por la que se otorga a Jinko Greenfield "
        "Spain 3, SL, la autorización administrativa previa para la instalación "
        "fotovoltaica «FV La Puebla 1», de 59,52 MW de potencia instalada, y su "
        "infraestructura de evacuación, en Puebla de Guzmán (Huelva)."
    ),
    "BOE-A-2025-26110_event_1_action_2": (
        "habiendo sido formulada declaración de impacto ambiental favorable, "
        "concretada mediante Resolución de 16 de septiembre de 2025 de la "
        "Dirección General de Calidad y Evaluación Ambiental del Ministerio "
        "para la Transición Ecológica y el Reto Demográfico (en adelante, DIA "
        "o declaración de impacto ambiental)"
    ),
}


def _action(
    action_type: AdministrativeActionType,
    decision: AdministrativeDecision,
    evidence_key: str,
) -> AdministrativeAction:
    return AdministrativeAction(
        action_type=action_type,
        decision=decision,
        targets=["generation_asset_1"],
        evidence=EVIDENCE[evidence_key],
    )


def _extraction(
    boe_id: str,
    actions: list[AdministrativeAction],
) -> BOEProjectExtraction:
    evidence = f"Proyecto de generación publicado en {boe_id}."
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Documento específico de generación.",
        publication_events=[PublicationEvent(
            generation_assets=[GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=[f"Planta {boe_id}"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                evidence=evidence,
            )],
            administrative_actions=actions,
            event_summary="Actuaciones publicadas.",
        )],
        extraction_notes=None,
        boe_id=boe_id,
        publication_date=date(2026, 8, 13),
    )


def _known_current_extractions() -> pd.DataFrame:
    extractions = [
        _extraction("BOE-A-2024-16662", [
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.DESESTIMADO,
                "BOE-A-2024-16662_event_1_action_1",
            ),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
                AdministrativeDecision.UNFAVORABLE,
                "BOE-A-2024-16662_event_1_action_2",
            ),
            _action(
                AdministrativeActionType.PUBLIC_INFORMATION,
                AdministrativeDecision.ANNOUNCED,
                "BOE-A-2024-16662_event_1_action_3",
            ),
        ]),
        _extraction("BOE-A-2024-9608", [
            _action(
                AdministrativeActionType.ENVIRONMENTAL_APPLICATION_SUBMISSION,
                AdministrativeDecision.REQUESTED,
                "BOE-A-2024-9608_event_1_action_1",
            ),
            _action(
                AdministrativeActionType.DOCUMENTATION_CORRECTION,
                AdministrativeDecision.CORRECTED,
                "BOE-A-2024-9608_event_1_action_2",
            ),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_AFFECTATION_DETERMINATION_REPORT,
                AdministrativeDecision.FORMULATED,
                "BOE-A-2024-9608_event_1_action_3",
            ),
        ]),
        _extraction("BOE-A-2025-26110", [
            _action(
                AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
                AdministrativeDecision.AUTHORIZED,
                "BOE-A-2025-26110_event_1_action_1",
            ),
            _action(
                AdministrativeActionType.ENVIRONMENTAL_IMPACT_STATEMENT,
                AdministrativeDecision.FAVORABLE,
                "BOE-A-2025-26110_event_1_action_2",
            ),
        ]),
    ]
    return pd.DataFrame([
        {
            "identificador_boe": extraction.boe_id,
            "extraction_config_id": EXTRACTION_CONFIG_ID,
            "extraction_json": extraction.model_dump_json(),
            "attempt_id": f"attempt-{index}",
        }
        for index, extraction in enumerate(extractions, start=1)
    ])


def _materializable_known_current() -> pd.DataFrame:
    current = _known_current_extractions()
    current["source_document_sha256"] = ["a" * 64, "b" * 64, "c" * 64]
    current["contract_schema_sha256"] = CONTRACT_SCHEMA_SHA256
    current["instructions_sha256"] = INSTRUCTIONS_SHA256
    current["model_provider"] = MODEL_PROVIDER
    current["model_name"] = AI_MODEL_NAME
    current["document_validation_version"] = DOCUMENT_VALIDATION_VERSION
    current["selection_source"] = "auto_validated"
    return current


def _loaded_registry():
    return load_administrative_action_corrections(REGISTRY_PATH)


def _write_registry_variant(
    tmp_path: Path,
    corrections: pd.DataFrame,
):
    path = tmp_path / "corrections-variant.csv"
    corrections.to_csv(path, index=False)
    return load_administrative_action_corrections(path)


def test_versioned_registry_loads_exactly_five_approved_corrections() -> None:
    loaded = _loaded_registry()

    assert len(loaded.corrections) == 5
    assert loaded.corrections["status"].unique().tolist() == ["approved"]
    assert loaded.corrections["operation"].unique().tolist() == ["exclude"]
    assert len(loaded.file_sha256) == 64
    assert loaded.semantic_identity == corrections_identity(loaded.corrections)


def test_evidence_hash_uses_minimal_stable_unicode_and_line_normalization() -> None:
    assert evidence_sha256("  resolución\r\nfinal  ") == evidence_sha256(
        "resolución\nfinal"
    )
    assert evidence_sha256("Resolución, final.") != evidence_sha256(
        "Resolución final"
    )


def test_duplicate_correction_id_is_rejected() -> None:
    corrections = _loaded_registry().corrections.copy(deep=True)
    corrections.loc[1, "correction_id"] = corrections.loc[0, "correction_id"]

    with pytest.raises(AdministrativeActionCorrectionError, match="duplicad"):
        validate_administrative_action_corrections(corrections)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_registry_requires_exact_columns(change: str) -> None:
    corrections = _loaded_registry().corrections.copy(deep=True)
    if change == "missing":
        corrections = corrections.drop(columns=["reviewer"])
    else:
        corrections["unexpected"] = "value"

    with pytest.raises(AdministrativeActionCorrectionError, match="columnas"):
        validate_administrative_action_corrections(corrections)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("correction_version", 0),
        ("correction_id", "Unstable ID"),
        ("expected_evidence_sha256", "A" * 64),
    ],
)
def test_invalid_version_id_or_evidence_hash_is_rejected(
    column: str,
    value: object,
) -> None:
    corrections = _loaded_registry().corrections.copy(deep=True)
    corrections.loc[0, column] = value

    with pytest.raises(AdministrativeActionCorrectionError):
        validate_administrative_action_corrections(corrections)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("operation", "replace"),
        ("status", "pending"),
        ("entity_type", "location"),
    ],
)
def test_invalid_domain_is_rejected(column: str, value: str) -> None:
    corrections = _loaded_registry().corrections.copy(deep=True)
    corrections.loc[0, column] = value

    with pytest.raises(AdministrativeActionCorrectionError, match=column):
        validate_administrative_action_corrections(corrections)


def test_known_corrections_match_exactly_and_do_not_mutate_source() -> None:
    current = _known_current_extractions()
    snapshot = current.copy(deep=True)

    result = apply_administrative_action_corrections(
        current,
        _loaded_registry(),
        source_extraction_snapshot_id="source-snapshot-v1",
    )

    pd.testing.assert_frame_equal(current, snapshot)
    assert len(result.applied_corrections) == 5
    assert result.applied_corrections["applied"].all()
    assert list(result.applied_corrections["correction_id"]) == sorted(
        result.applied_corrections["correction_id"]
    )


def test_known_exclusions_preserve_idaa_aap_and_unrelated_entities() -> None:
    current = _known_current_extractions()
    before = flatten_current_extractions(current)
    result = apply_administrative_action_corrections(
        current,
        _loaded_registry(),
        source_extraction_snapshot_id="source-snapshot-v1",
    )
    after = flatten_current_extractions(result.effective_current_extractions)

    observed = {
        boe_id: list(zip(group["action_type"], group["decision"], strict=True))
        for boe_id, group in after["administrative_actions"].groupby(
            "identificador_boe", sort=True
        )
    }
    assert observed == {
        "BOE-A-2024-16662": [
            ("autorizacion_administrativa_previa", "desestimado")
        ],
        "BOE-A-2024-9608": [
            ("informe_determinacion_afeccion_ambiental", "formulado")
        ],
        "BOE-A-2025-26110": [
            ("autorizacion_administrativa_previa", "autorizado")
        ],
    }
    assert len(before["administrative_actions"]) == 8
    assert len(after["administrative_actions"]) == 3
    assert len(before["administrative_action_targets"]) == 8
    assert len(after["administrative_action_targets"]) == 3
    pd.testing.assert_frame_equal(
        before["publication_events"].drop(columns=["n_administrative_actions"]),
        after["publication_events"].drop(columns=["n_administrative_actions"]),
    )
    for table_name in (
        "generation_asset_mentions",
        "generation_asset_names",
        "associated_components",
        "participant_mentions",
        "location_mentions",
        "generation_asset_relations",
        "technical_mentions",
        "case_file_references",
    ):
        pd.testing.assert_frame_equal(before[table_name], after[table_name])


def test_missing_target_fails_closed(tmp_path: Path) -> None:
    corrections = _loaded_registry().corrections.iloc[[0]].copy(deep=True)
    corrections.loc[:, "administrative_action_id"] = (
        "BOE-A-2024-16662_event_9_action_9"
    )
    loaded = _write_registry_variant(tmp_path, corrections)

    with pytest.raises(AdministrativeActionCorrectionError, match="0 targets"):
        apply_administrative_action_corrections(
            _known_current_extractions(),
            loaded,
            source_extraction_snapshot_id="source-snapshot-v1",
        )


def test_duplicated_source_target_fails_closed_as_ambiguous(
    tmp_path: Path,
) -> None:
    current = _known_current_extractions()
    current = pd.concat([current, current.iloc[[0]]], ignore_index=True)
    corrections = _loaded_registry().corrections.iloc[[0]].copy(deep=True)
    loaded = _write_registry_variant(tmp_path, corrections)

    with pytest.raises(AdministrativeActionCorrectionError, match="2 targets"):
        apply_administrative_action_corrections(
            current,
            loaded,
            source_extraction_snapshot_id="source-snapshot-v1",
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("expected_action_type", "informacion_publica"),
        ("expected_decision", "convocado"),
        ("expected_evidence_sha256", "f" * 64),
    ],
)
def test_semantic_fingerprint_mismatch_fails_closed(
    tmp_path: Path,
    column: str,
    value: str,
) -> None:
    corrections = _loaded_registry().corrections.iloc[[0]].copy(deep=True)
    corrections.loc[:, column] = value
    loaded = _write_registry_variant(tmp_path, corrections)

    with pytest.raises(
        AdministrativeActionCorrectionError,
        match="fingerprint",
    ):
        apply_administrative_action_corrections(
            _known_current_extractions(),
            loaded,
            source_extraction_snapshot_id="source-snapshot-v1",
        )


def test_registry_row_order_does_not_change_identity_or_effective_output(
    tmp_path: Path,
) -> None:
    loaded = _loaded_registry()
    shuffled_frame = loaded.corrections.sample(
        frac=1, random_state=23
    ).reset_index(drop=True)
    shuffled = _write_registry_variant(tmp_path, shuffled_frame)
    current = _known_current_extractions()

    first = apply_administrative_action_corrections(
        current,
        loaded,
        source_extraction_snapshot_id="source-snapshot-v1",
    )
    second = apply_administrative_action_corrections(
        current,
        shuffled,
        source_extraction_snapshot_id="source-snapshot-v1",
    )

    assert loaded.semantic_identity == shuffled.semantic_identity
    pd.testing.assert_frame_equal(
        first.effective_current_extractions,
        second.effective_current_extractions,
    )
    pd.testing.assert_frame_equal(
        first.applied_corrections.drop(columns=["corrections_file_sha256"]),
        second.applied_corrections.drop(columns=["corrections_file_sha256"]),
    )


def test_corrected_silver_writes_verified_sidecar_manifest_and_new_identity(
    tmp_path: Path,
) -> None:
    current = _materializable_known_current()
    baseline = materialize_current_extractions(
        current,
        output_dir=tmp_path / "baseline",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    corrected = materialize_current_extractions(
        current,
        output_dir=tmp_path / "corrected",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        corrections=_loaded_registry(),
        source_extraction_snapshot_id="source-snapshot-v1",
    )

    assert baseline.materialization_id != corrected.materialization_id
    assert baseline.applied_corrections_path is None
    assert corrected.applied_corrections_path == (
        corrected.output_dir / "applied_corrections.parquet"
    )
    sidecar = pd.read_parquet(corrected.applied_corrections_path)
    assert len(sidecar) == 5
    assert sidecar["applied"].all()
    manifest = pd.read_json(corrected.manifest_path, typ="series")
    correction_manifest = manifest["corrections"]
    assert correction_manifest["applied"] is True
    assert correction_manifest["approved_count"] == 5
    assert correction_manifest["applied_count"] == 5
    assert correction_manifest["logical_path"] == REGISTRY_PATH.as_posix()
    assert correction_manifest["identity"] == _loaded_registry().semantic_identity
    assert correction_manifest["source_extraction_config_id"] == (
        EXTRACTION_CONFIG_ID
    )
    loaded = load_flat_materialization(
        corrected.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert loaded.materialization_id == corrected.materialization_id
    actions = loaded.tables["administrative_actions"]
    targets = loaded.tables["administrative_action_targets"]
    assert len(actions) == 3
    assert len(targets) == 3


def test_no_corrections_keeps_tables_and_legacy_identity_without_sidecar(
    tmp_path: Path,
) -> None:
    current = _materializable_known_current()
    first = materialize_current_extractions(
        current,
        output_dir=tmp_path / "first",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    second = materialize_current_extractions(
        current,
        output_dir=tmp_path / "second",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        corrections=None,
    )

    assert first.materialization_id == second.materialization_id
    assert first.applied_corrections_path is None
    assert second.applied_corrections_path is None
    for table_name, expected in flatten_current_extractions(current).items():
        pd.testing.assert_frame_equal(
            pd.read_parquet(second.table_paths[table_name]), expected
        )


def test_correction_failure_does_not_publish_partial_silver(tmp_path: Path) -> None:
    loaded = _loaded_registry()
    invalid = loaded.corrections.copy(deep=True)
    invalid.loc[0, "expected_evidence_sha256"] = "f" * 64
    invalid_loaded = _write_registry_variant(tmp_path, invalid)
    output_dir = tmp_path / "must-not-exist"

    with pytest.raises(AdministrativeActionCorrectionError, match="fingerprint"):
        materialize_current_extractions(
            _materializable_known_current(),
            output_dir=output_dir,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            corrections=invalid_loaded,
            source_extraction_snapshot_id="source-snapshot-v1",
        )

    assert not output_dir.exists()
    assert list(tmp_path.glob(".must-not-exist.staging-*")) == []


def test_correction_row_order_keeps_silver_identity(tmp_path: Path) -> None:
    current = _materializable_known_current()
    loaded = _loaded_registry()
    shuffled_path = tmp_path / "shuffled-corrections.csv"
    loaded.corrections.sample(frac=1, random_state=9).to_csv(
        shuffled_path, index=False
    )
    shuffled = load_administrative_action_corrections(shuffled_path)

    assert loaded.file_sha256 != shuffled.file_sha256
    assert loaded.semantic_identity == shuffled.semantic_identity

    first = materialize_current_extractions(
        current,
        output_dir=tmp_path / "first",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        corrections=loaded,
        source_extraction_snapshot_id="source-snapshot-v1",
    )
    second = materialize_current_extractions(
        current,
        output_dir=tmp_path / "second",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        corrections=shuffled,
        source_extraction_snapshot_id="source-snapshot-v1",
    )

    assert first.materialization_id == second.materialization_id
    first_tables = load_flat_materialization(
        first.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    ).tables
    second_tables = load_flat_materialization(
        second.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    ).tables
    for table_name in first_tables:
        pd.testing.assert_frame_equal(
            first_tables[table_name], second_tables[table_name]
        )
