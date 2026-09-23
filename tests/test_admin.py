import json
import shutil
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from renewables_permitting import admin
from renewables_permitting.extraction.config import (
    AI_MODEL_NAME,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MODEL_PROVIDER,
)
from renewables_permitting.extraction.corrections import (
    evidence_sha256,
    historical_action_exclusion_correction_id,
    load_administrative_action_corrections,
)
from renewables_permitting.extraction.documents import build_source_document
from renewables_permitting.extraction.historical_antecedent_reviews import (
    historical_antecedent_review_id,
    load_historical_antecedent_reviews,
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
from renewables_permitting.extraction.review import (
    _load_manual_review_files_for_boe_ids,
    normalise_ai_extraction_attempts_log,
)
from renewables_permitting.pipeline import run_extraction_stage


@dataclass(frozen=True)
class AdminEnvironment:
    """Paths and immutable source JSONs for one local admin test universe."""

    snapshot: Path
    corrections: Path
    current_reviews: Path
    manual_reviews: Path
    source_json_by_boe: dict[str, str]


def _action(
    action_type: AdministrativeActionType,
    decision: AdministrativeDecision,
    evidence: str,
) -> AdministrativeAction:
    """Build one event-level administrative action fixture."""

    return AdministrativeAction(
        action_type=action_type,
        decision=decision,
        targets=["event"],
        evidence=evidence,
    )


def _historical_example(
    boe_id: str,
    name: str,
    *,
    two_findings: bool,
) -> tuple[dict[str, object], BOEProjectExtraction]:
    """Build one detector-positive source and canonical extraction."""

    title = (
        "Resolución por la que se otorga autorización administrativa previa "
        f"a la planta solar fotovoltaica {name}."
    )
    request = (
        "el promotor solicitó el 1 de enero de 2025 autorización "
        f"administrativa previa para {name}"
    )
    public_information = (
        "la petición fue sometida el 2 de febrero de 2025 a información "
        f"pública para {name}"
    )
    actions = [
        _action(
            AdministrativeActionType.APPLICATION_SUBMISSION,
            AdministrativeDecision.REQUESTED,
            request,
        )
    ]
    if two_findings:
        actions.append(_action(
            AdministrativeActionType.PUBLIC_INFORMATION,
            AdministrativeDecision.SUBMITTED_TO_PUBLIC_INFORMATION,
            public_information,
        ))
    actions.append(_action(
        AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION,
        AdministrativeDecision.AUTHORIZED,
        title,
    ))
    extraction = BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Proyecto de generación identificado.",
        publication_events=[PublicationEvent(
            generation_assets=[GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=[name],
                generation_type=GenerationType.PHOTOVOLTAIC,
                evidence=name,
            )],
            administrative_actions=actions,
            event_summary=f"Autorización de {name}.",
        )],
        boe_id=boe_id,
        publication_date=date(2026, 1, 1),
    )
    historical_passages = f"{request}."
    if two_findings:
        historical_passages += f" {public_information}."
    text = (
        f"{title} Antecedentes de hecho. {historical_passages} "
        "Fundamentos de Derecho. Esta Dirección General resuelve: "
        f"Otorgar autorización administrativa previa a {name}."
    )
    return ({
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp("2026-01-01"),
        "titulo": title,
        "xml_status": "ok",
        "texto_limpio": text,
    }, extraction)


def _generic_example() -> tuple[dict[str, object], BOEProjectExtraction]:
    """Build one valid uncertain extraction routed to generic review."""

    boe_id = "BOE-A-2026-91003"
    title = "Anuncio relativo a la planta solar fotovoltaica Gamma."
    extraction = BOEProjectExtraction(
        classification_status=ClassificationStatus.UNCERTAIN,
        document_scope=None,
        classification_reason=(
            "La publicación no permite confirmar el alcance administrativo."
        ),
        publication_events=[],
        boe_id=boe_id,
        publication_date=date(2026, 1, 3),
    )
    return ({
        "identificador": boe_id,
        "fecha_publicacion": pd.Timestamp("2026-01-03"),
        "titulo": title,
        "xml_status": "ok",
        "texto_limpio": (
            f"{title} Se publica información sobre Gamma sin suficiente "
            "detalle para resolver su alcance."
        ),
    }, extraction)


def _attempt_record(
    row: dict[str, object],
    extraction: BOEProjectExtraction,
    *,
    position: int,
) -> tuple[dict[str, object], dict[str, object]]:
    """Add source identity and build one compatible persisted attempt."""

    source = dict(row)
    document = build_source_document(pd.Series(source))
    source["source_document_sha256"] = document.source_document_sha256
    attempt = {
        "attempt_id": f"admin-attempt-{position}",
        "identificador_boe": extraction.boe_id,
        "fecha_publicacion": pd.Timestamp(extraction.publication_date),
        "titulo": document.title,
        "source_document_sha256": document.source_document_sha256,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "instructions_sha256": INSTRUCTIONS_SHA256,
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "classification_status": extraction.classification_status.value,
        "document_scope": (
            extraction.document_scope.value
            if extraction.document_scope is not None
            else pd.NA
        ),
        "classification_reason": extraction.classification_reason,
        "extraction_json": extraction.model_dump_json(),
        "extracted_at": pd.Timestamp("2026-08-29T10:00:00Z"),
        "extraction_status": "ok",
        "processing_stage": "completed",
        "document_validation_status": "passed",
    }
    return source, attempt


@pytest.fixture()
def admin_environment(tmp_path: Path) -> AdminEnvironment:
    """Materialize one validated mixed review snapshot entirely offline."""

    examples = [
        _historical_example(
            "BOE-A-2026-91001", "Alpha", two_findings=True
        ),
        _historical_example(
            "BOE-A-2026-91002", "Beta", two_findings=False
        ),
        _generic_example(),
    ]
    sources: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    source_json_by_boe: dict[str, str] = {}
    for position, (row, extraction) in enumerate(examples, start=1):
        source, attempt = _attempt_record(
            row, extraction, position=position
        )
        sources.append(source)
        attempts.append(attempt)
        source_json_by_boe[extraction.boe_id] = extraction.model_dump_json()

    documents_path = tmp_path / "documents.parquet"
    attempts_path = tmp_path / "attempts.parquet"
    snapshot = tmp_path / "extraction"
    pd.DataFrame(sources).to_parquet(documents_path, index=False)
    normalise_ai_extraction_attempts_log(
        pd.DataFrame(attempts)
    ).to_parquet(attempts_path, index=False)
    run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        output_dir=snapshot,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    corrections = tmp_path / "administrative_action_corrections.csv"
    current_reviews = tmp_path / "historical_antecedent_reviews.csv"
    shutil.copyfile(admin.CORRECTIONS_PATH, corrections)
    shutil.copyfile(admin.CURRENT_REVIEWS_PATH, current_reviews)
    return AdminEnvironment(
        snapshot=snapshot,
        corrections=corrections,
        current_reviews=current_reviews,
        manual_reviews=tmp_path / "manual_reviews",
        source_json_by_boe=source_json_by_boe,
    )


def _context(environment: AdminEnvironment) -> admin.AdminContext:
    """Load one fixture context through the production validated loader."""

    return admin.load_admin_context(
        environment.snapshot,
        corrections_path=environment.corrections,
        current_reviews_path=environment.current_reviews,
    )


def _common_cli_args(environment: AdminEnvironment) -> list[str]:
    """Return shared explicit test registry and snapshot arguments."""

    return [
        "--extraction-snapshot",
        str(environment.snapshot),
        "--corrections",
        str(environment.corrections),
        "--current-reviews",
        str(environment.current_reviews),
    ]


@pytest.mark.parametrize(
    "command",
    [
        None,
        "list",
        "show",
        "current",
        "antecedent",
        "validate-extraction",
        "reject-extraction",
        "list-decisions",
    ],
)
def test_cli_help_for_module_and_every_command(
    command: str | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every approved command exposes argparse help."""

    argv = ["--help"] if command is None else [command, "--help"]
    with pytest.raises(SystemExit) as raised:
        admin.main(argv)
    assert raised.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_cli_rejects_invalid_command_and_missing_required_arguments() -> None:
    """Argparse fails closed for invalid or incomplete invocations."""

    with pytest.raises(SystemExit) as invalid:
        admin.main(["unsupported"])
    assert invalid.value.code == 2
    with pytest.raises(SystemExit) as missing:
        admin.main(["show"])
    assert missing.value.code == 2


def test_list_is_deterministic_and_expands_historical_findings(
    admin_environment: AdminEnvironment,
) -> None:
    """List expands action findings and keeps stable BOE/action ordering."""

    context = _context(admin_environment)
    first = admin.build_review_cases(context)
    second = admin.build_review_cases(context)

    assert first == second
    assert [(case.boe_id, case.index) for case in first] == [
        ("BOE-A-2026-91001", 1),
        ("BOE-A-2026-91001", 2),
        ("BOE-A-2026-91002", 1),
        ("BOE-A-2026-91003", 1),
    ]
    assert [case.reason_code for case in first[-1:]] == [
        "classification_uncertain"
    ]
    assert "BOE-A-2026-91001_event_1_action_1" in admin.format_case_list(
        first
    )


def test_list_filters_and_empty_queue_message(
    admin_environment: AdminEnvironment,
) -> None:
    """BOE/reason filters are exact and empty output is explicit."""

    context = _context(admin_environment)
    cases = admin.build_review_cases(
        context,
        reason_code="classification_uncertain",
    )
    assert [case.boe_id for case in cases] == ["BOE-A-2026-91003"]
    assert admin.format_case_list(admin.build_review_cases(
        context, boe_id="BOE-A-2026-99999"
    )) == "No pending review cases."


def test_show_preserves_evidence_sections_and_signals(
    admin_environment: AdminEnvironment,
) -> None:
    """Historical detail contains literal evidence and detector diagnostics."""

    case = admin.select_review_case(
        _context(admin_environment),
        boe_id="BOE-A-2026-91001",
        index=1,
    )
    detail = admin.format_case_detail(case)
    assert case.finding is not None
    assert case.finding.evidence in detail
    assert "section=antecedentes_de_hecho" in detail
    assert "Temporal signals:" in detail
    assert "Contextual signals:" in detail
    assert "Source passage:" in detail


def test_show_requires_index_only_when_multiple_findings_exist(
    admin_environment: AdminEnvironment,
) -> None:
    """A singleton can omit index while a multi-finding BOE cannot."""

    context = _context(admin_environment)
    assert admin.select_review_case(
        context, boe_id="BOE-A-2026-91002"
    ).index == 1
    with pytest.raises(admin.AdminCLIError, match="indica --index"):
        admin.select_review_case(context, boe_id="BOE-A-2026-91001")


def test_generic_show_is_structured_and_non_editable(
    admin_environment: AdminEnvironment,
) -> None:
    """Generic display summarizes the exact proposal without input controls."""

    case = admin.select_review_case(
        _context(admin_environment), boe_id="BOE-A-2026-91003"
    )
    detail = admin.format_case_detail(case)
    assert "Classification: uncertain" in detail
    assert "Publication events: 0" in detail
    assert "Classification reason:" in detail


def test_current_dry_run_validates_without_mutation(
    admin_environment: AdminEnvironment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CURRENT dry-run derives metadata but leaves the registry untouched."""

    before = admin_environment.current_reviews.read_bytes()
    result = admin.main([
        "current",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "La actuación pertenece a la resolución actual.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-current",
        "--dry-run",
    ])
    assert result == 0
    assert admin_environment.current_reviews.read_bytes() == before
    assert "DRY RUN" in capsys.readouterr().out


def test_current_write_derives_contract_metadata_and_preserves_source(
    admin_environment: AdminEnvironment,
) -> None:
    """CURRENT writes one validated row without changing extraction data."""

    current_path = admin_environment.snapshot / "current_extractions.parquet"
    source_before = current_path.read_bytes()
    result = admin.main([
        "current",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "La actuación es actual.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-current-write",
        "--yes",
    ])
    assert result == 0
    loaded = load_historical_antecedent_reviews(
        admin_environment.current_reviews
    )
    assert len(loaded.reviews) == 1
    row = loaded.reviews.iloc[0].to_dict()
    assert row["outcome"] == "current"
    assert row["boe_id"] == "BOE-A-2026-91002"
    assert row["source_document_sha256"]
    assert row["expected_evidence_sha256"]
    assert len(historical_antecedent_review_id(row)) == 24
    assert current_path.read_bytes() == source_before
    assert json.loads(admin_environment.source_json_by_boe[
        "BOE-A-2026-91002"
    ]) == json.loads(pd.read_parquet(current_path).loc[
        lambda frame: frame["identificador_boe"].eq("BOE-A-2026-91002"),
        "extraction_json",
    ].iloc[0])


def test_current_duplicate_is_rejected_without_write(
    admin_environment: AdminEnvironment,
) -> None:
    """A second CURRENT attempt sees no pending exact finding."""

    args = [
        "current",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "La actuación es actual.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-current-duplicate",
        "--yes",
    ]
    assert admin.main(args) == 0
    before = admin_environment.current_reviews.read_bytes()
    assert admin.main(args) == 2
    assert admin_environment.current_reviews.read_bytes() == before


def test_current_atomic_failure_preserves_original(
    admin_environment: AdminEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed atomic replace leaves the original CURRENT bytes intact."""

    context = _context(admin_environment)
    case = admin.select_review_case(
        context, boe_id="BOE-A-2026-91002"
    )
    candidate = admin.prepare_current_decision(
        context,
        case,
        reason="La actuación es actual.",
        reviewer="operator",
        decision_source="human-review:test-atomic",
        reviewed_on=date(2026, 8, 29),
    )
    before = admin_environment.current_reviews.read_bytes()
    monkeypatch.setattr(
        admin.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("atomic failure")),
    )
    with pytest.raises(OSError, match="atomic failure"):
        admin.persist_current_decision(candidate)
    assert admin_environment.current_reviews.read_bytes() == before
    assert not list(admin_environment.current_reviews.parent.glob(
        ".historical_antecedent_reviews.csv.*.tmp"
    ))


def test_current_append_preserves_existing_approved_row(
    admin_environment: AdminEnvironment,
) -> None:
    """A second distinct CURRENT decision preserves the first semantically."""

    common = _common_cli_args(admin_environment)
    assert admin.main([
        "current", *common,
        "--boe-id", "BOE-A-2026-91001", "--index", "1",
        "--reason", "Primera actual.", "--reviewer", "operator",
        "--decision-source", "human-review:preserve-first", "--yes",
    ]) == 0
    first = load_historical_antecedent_reviews(
        admin_environment.current_reviews
    ).reviews.iloc[0].to_dict()
    assert admin.main([
        "current", *common,
        "--boe-id", "BOE-A-2026-91002",
        "--reason", "Segunda actual.", "--reviewer", "operator",
        "--decision-source", "human-review:preserve-second", "--yes",
    ]) == 0
    loaded = load_historical_antecedent_reviews(
        admin_environment.current_reviews
    ).reviews
    assert len(loaded) == 2
    assert loaded.iloc[0].to_dict() == first


def test_antecedent_dry_run_and_write_are_exact_and_deterministic(
    admin_environment: AdminEnvironment,
) -> None:
    """ANTECEDENT validates target/fingerprint and persists deterministic ID."""

    context = _context(admin_environment)
    case = admin.select_review_case(
        context, boe_id="BOE-A-2026-91002"
    )
    assert case.finding is not None
    candidate = admin.prepare_antecedent_decision(
        context,
        case,
        reason="Es un trámite anterior.",
        reviewer="operator",
        decision_source="human-review:test-antecedent",
        reviewed_on=date(2026, 8, 29),
    )
    expected_id = historical_action_exclusion_correction_id(
        boe_id=case.finding.boe_id,
        administrative_action_id=case.finding.administrative_action_id,
        expected_action_type=case.finding.action_type,
        expected_decision=case.finding.decision,
        expected_evidence_sha256=case.finding.evidence_sha256,
    )
    assert candidate.correction_id == expected_id
    assert candidate.row["expected_evidence_sha256"] == evidence_sha256(
        case.finding.evidence
    )
    before = admin_environment.corrections.read_bytes()
    dry_run = admin.main([
        "antecedent",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "Es un trámite anterior.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-antecedent",
        "--dry-run",
    ])
    assert dry_run == 0
    assert admin_environment.corrections.read_bytes() == before

    write = admin.main([
        "antecedent",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "Es un trámite anterior.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-antecedent",
        "--yes",
    ])
    assert write == 0
    loaded = load_administrative_action_corrections(
        admin_environment.corrections
    )
    assert loaded.corrections.iloc[-1]["correction_id"] == expected_id
    assert len(loaded.corrections) == 17


def test_antecedent_duplicate_and_current_conflict_fail_closed(
    admin_environment: AdminEnvironment,
) -> None:
    """Resolved or contradictory historical decisions cannot be added."""

    antecedent_args = [
        "antecedent",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "Es anterior.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-conflict",
        "--yes",
    ]
    assert admin.main(antecedent_args) == 0
    corrections_before = admin_environment.corrections.read_bytes()
    current_before = admin_environment.current_reviews.read_bytes()
    assert admin.main(antecedent_args) == 2
    assert admin.main([
        "current",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91002",
        "--reason",
        "Es actual.",
        "--reviewer",
        "operator",
        "--decision-source",
        "human-review:test-conflict",
        "--yes",
    ]) == 2
    assert admin_environment.corrections.read_bytes() == corrections_before
    assert admin_environment.current_reviews.read_bytes() == current_before


def test_antecedent_conflict_with_existing_current_fails_closed(
    admin_environment: AdminEnvironment,
) -> None:
    """The inverse CURRENT-to-ANTECEDENT conflict is also rejected."""

    common = _common_cli_args(admin_environment)
    assert admin.main([
        "current", *common,
        "--boe-id", "BOE-A-2026-91002",
        "--reason", "Es actual.", "--reviewer", "operator",
        "--decision-source", "human-review:inverse-conflict", "--yes",
    ]) == 0
    corrections_before = admin_environment.corrections.read_bytes()
    assert admin.main([
        "antecedent", *common,
        "--boe-id", "BOE-A-2026-91002",
        "--reason", "Es anterior.", "--reviewer", "operator",
        "--decision-source", "human-review:inverse-conflict", "--yes",
    ]) == 2
    assert admin_environment.corrections.read_bytes() == corrections_before


def test_antecedent_atomic_failure_preserves_original(
    admin_environment: AdminEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed correction replace leaves every approved row untouched."""

    context = _context(admin_environment)
    case = admin.select_review_case(
        context, boe_id="BOE-A-2026-91002"
    )
    candidate = admin.prepare_antecedent_decision(
        context,
        case,
        reason="Es anterior.",
        reviewer="operator",
        decision_source="human-review:antecedent-atomic",
        reviewed_on=date(2026, 8, 29),
    )
    before = admin_environment.corrections.read_bytes()
    monkeypatch.setattr(
        admin.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("atomic failure")),
    )
    with pytest.raises(OSError, match="atomic failure"):
        admin.persist_antecedent_decision(candidate)
    assert admin_environment.corrections.read_bytes() == before
    assert not list(admin_environment.corrections.parent.glob(
        ".administrative_action_corrections.csv.*.tmp"
    ))


def test_stale_finding_and_concurrent_registry_change_are_rejected(
    admin_environment: AdminEnvironment,
) -> None:
    """Expected finding identity and physical registry hash both fail closed."""

    context = _context(admin_environment)
    case = admin.select_review_case(
        context, boe_id="BOE-A-2026-91002"
    )
    assert case.finding is not None
    stale = replace(case.finding, evidence_sha256="0" * 64)
    with pytest.raises(admin.AdminCLIError, match="finding cambió"):
        admin._select_exact_finding_case(context, stale)

    candidate = admin.prepare_current_decision(
        context,
        case,
        reason="Es actual.",
        reviewer="operator",
        decision_source="human-review:test-stale",
        reviewed_on=date(2026, 8, 29),
    )
    admin_environment.current_reviews.write_text(
        admin_environment.current_reviews.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(admin.AdminCLIError, match="cambió"):
        admin.persist_current_decision(candidate)


def test_malformed_registry_fails_before_any_decision_write(
    admin_environment: AdminEnvironment,
) -> None:
    """Malformed current or correction contracts abort context loading."""

    corrections_before = admin_environment.corrections.read_bytes()
    admin_environment.current_reviews.write_text(
        "wrong,columns\nvalue,value\n", encoding="utf-8"
    )
    assert admin.main([
        "list",
        *_common_cli_args(admin_environment),
    ]) == 2
    assert admin_environment.corrections.read_bytes() == corrections_before


def test_validate_exact_proposal_dry_run_and_write(
    admin_environment: AdminEnvironment,
) -> None:
    """Generic approval writes only the queue's exact validated proposal."""

    args = [
        "validate-extraction",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91003",
        "--reviewer",
        "operator",
        "--notes",
        "La clasificación propuesta ha sido revisada.",
        "--manual-review-dir",
        str(admin_environment.manual_reviews),
    ]
    assert admin.main([*args, "--dry-run"]) == 0
    assert not admin_environment.manual_reviews.exists()
    assert admin.main([*args, "--yes"]) == 0

    context = _context(admin_environment)
    loaded = _load_manual_review_files_for_boe_ids(
        context.snapshot.documents,
        context.snapshot.attempts,
        review_dir=admin_environment.manual_reviews,
        boe_ids=context.snapshot.documents["identificador"].astype(str),
    )
    assert loaded["review_status"].tolist() == ["manually_validated"]
    stored = json.loads((
        admin_environment.manual_reviews / "BOE-A-2026-91003.json"
    ).read_text(encoding="utf-8"))
    assert stored["corrected_extraction"] == json.loads(
        admin_environment.source_json_by_boe["BOE-A-2026-91003"]
    )


def test_reject_extraction_and_decisive_overwrite_rejection(
    admin_environment: AdminEnvironment,
) -> None:
    """A whole-extraction rejection persists once and cannot be overwritten."""

    args = [
        "reject-extraction",
        *_common_cli_args(admin_environment),
        "--boe-id",
        "BOE-A-2026-91003",
        "--reviewer",
        "operator",
        "--notes",
        "La extracción completa debe rechazarse.",
        "--manual-review-dir",
        str(admin_environment.manual_reviews),
        "--yes",
    ]
    assert admin.main(args) == 0
    target = admin_environment.manual_reviews / "BOE-A-2026-91003.json"
    before = target.read_bytes()
    assert json.loads(before)["corrected_extraction"] is None
    assert admin.main(args) == 2
    assert target.read_bytes() == before


def test_generic_review_rejects_missing_proposal_historical_and_unattempted(
    admin_environment: AdminEnvironment,
) -> None:
    """Unsupported generic cases fail before staging any JSON."""

    context = _context(admin_environment)
    generic = admin.select_review_case(
        context, boe_id="BOE-A-2026-91003"
    )
    with pytest.raises(admin.AdminCLIError, match="proposed_extraction"):
        admin.prepare_manual_decision(
            context,
            replace(generic, proposed_extraction_json=None),
            review_status="manually_validated",
            reviewer="operator",
            notes="Missing proposal.",
            review_dir=admin_environment.manual_reviews,
        )
    historical = admin.select_review_case(
        context, boe_id="BOE-A-2026-91002"
    )
    with pytest.raises(admin.AdminCLIError, match="CURRENT o ANTECEDENT"):
        admin.prepare_manual_decision(
            context,
            historical,
            review_status="rejected",
            reviewer="operator",
            notes="Wrong contract.",
            review_dir=admin_environment.manual_reviews,
        )
    unattempted = replace(
        generic,
        reason_code="source_not_attempted",
        source_attempt_id=None,
    )
    with pytest.raises(admin.AdminCLIError, match="primero un intento"):
        admin.prepare_manual_decision(
            context,
            unattempted,
            review_status="rejected",
            reviewer="operator",
            notes="No attempt.",
            review_dir=admin_environment.manual_reviews,
        )
    assert not admin_environment.manual_reviews.exists()


def test_manual_review_atomic_failure_preserves_existing_pending_file(
    admin_environment: AdminEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JSON replace failure preserves an existing pending review bytewise."""

    context = _context(admin_environment)
    case = admin.select_review_case(
        context, boe_id="BOE-A-2026-91003"
    )
    admin_environment.manual_reviews.mkdir()
    target = admin_environment.manual_reviews / "BOE-A-2026-91003.json"
    target.write_text(json.dumps({
        "identificador_boe": case.boe_id,
        "source_document_sha256": case.source_document_sha256,
        "source_attempt_id": case.source_attempt_id,
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "review_status": "pending",
        "reviewer": None,
        "review_notes": None,
        "reviewed_at_utc": None,
        "corrected_extraction": json.loads(case.proposed_extraction_json),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidate = admin.prepare_manual_decision(
        context,
        case,
        review_status="manually_validated",
        reviewer="operator",
        notes="Reviewed.",
        review_dir=admin_environment.manual_reviews,
        reviewed_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    before = target.read_bytes()
    monkeypatch.setattr(
        admin.os,
        "replace",
        lambda *_: (_ for _ in ()).throw(OSError("atomic failure")),
    )
    with pytest.raises(OSError, match="atomic failure"):
        admin.persist_manual_decision(context, candidate)
    assert target.read_bytes() == before
    assert not list(tmp for tmp in target.parent.parent.iterdir() if (
        tmp.name.startswith(".boe-ai-reviews-")
    ))


def test_list_decisions_shows_all_three_validated_decision_types(
    admin_environment: AdminEnvironment,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The audit view reports CURRENT, ANTECEDENT and generic decisions."""

    common = _common_cli_args(admin_environment)
    assert admin.main([
        "current", *common,
        "--boe-id", "BOE-A-2026-91001", "--index", "1",
        "--reason", "Actual.", "--reviewer", "operator",
        "--decision-source", "human-review:list-decisions", "--yes",
    ]) == 0
    assert admin.main([
        "antecedent", *common,
        "--boe-id", "BOE-A-2026-91002",
        "--reason", "Anterior.", "--reviewer", "operator",
        "--decision-source", "human-review:list-decisions", "--yes",
    ]) == 0
    assert admin.main([
        "reject-extraction", *common,
        "--boe-id", "BOE-A-2026-91003", "--reviewer", "operator",
        "--notes", "Rechazada.",
        "--manual-review-dir", str(admin_environment.manual_reviews),
        "--yes",
    ]) == 0
    capsys.readouterr()

    result = admin.main([
        "list-decisions",
        "--extraction-snapshot", str(admin_environment.snapshot),
        "--corrections", str(admin_environment.corrections),
        "--current-reviews", str(admin_environment.current_reviews),
        "--manual-review-dir", str(admin_environment.manual_reviews),
    ])
    output = capsys.readouterr().out
    assert result == 0
    assert "CURRENT validations:" in output
    assert "ANTECEDENT corrections:" in output
    assert "Generic extraction reviews:" in output
    assert "BOE-A-2026-91001" in output
    assert "BOE-A-2026-91002" in output
    assert "BOE-A-2026-91003" in output


def test_cli_never_mutates_snapshot_silver_or_gold_paths(
    admin_environment: AdminEnvironment,
) -> None:
    """Decision registration changes only the explicitly selected registry."""

    artifact_hashes = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in admin_environment.snapshot.iterdir()
        if path.is_file()
    }
    assert admin.main([
        "current",
        *_common_cli_args(admin_environment),
        "--boe-id", "BOE-A-2026-91002",
        "--reason", "Actual.",
        "--reviewer", "operator",
        "--decision-source", "human-review:safety",
        "--yes",
    ]) == 0
    assert artifact_hashes == {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in admin_environment.snapshot.iterdir()
        if path.is_file()
    }
    assert not (admin_environment.snapshot.parent / "silver").exists()
    assert not (admin_environment.snapshot.parent / "gold").exists()
