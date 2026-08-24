from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

import renewables_permitting.pipeline as pipeline
from renewables_permitting.boe_candidates import CANDIDATE_POLICY_ID
from renewables_permitting.boe_documents import BOEXMLFetchResult
from renewables_permitting.boe_source import BOESummaryFetchResult
from renewables_permitting.extraction.config import (
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    SCOPE_CLASSIFICATION_POLICY,
)
from renewables_permitting.extraction.corrections import (
    ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
    evidence_sha256,
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
    append_ai_extraction_attempts,
    normalise_ai_extraction_attempts_log,
)
from renewables_permitting.extraction.runner import (
    build_error_record,
    build_success_record,
)
from renewables_permitting.extraction.agent import RunUsage
from renewables_permitting.extraction.documents import build_source_document
from renewables_permitting.ine_reference import (
    build_municipality_dimension,
    materialize_municipality_dimension,
)


NOW = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<documento>
  <metadatos>
    <identificador>BOE-A-2026-101</identificador>
    <titulo>Autorizacion de la planta fotovoltaica Aurora Solar.</titulo>
    <fecha_publicacion>20260102</fecha_publicacion>
  </metadatos>
  <texto><p>Se autoriza la planta fotovoltaica Aurora Solar.</p></texto>
</documento>
"""


def _summary_payload() -> dict:
    return {
        "status": {"code": "200", "text": "ok"},
        "data": {"sumario": {
            "metadatos": {"fecha_publicacion": "20260102"},
            "diario": {"numero": "2", "seccion": {
                "codigo": "3",
                "nombre": "III. Otras disposiciones",
                "departamento": {
                    "codigo": "9575",
                    "nombre": "MINISTERIO",
                    "epigrafe": {
                        "nombre": "Energía eléctrica",
                        "item": {
                            "identificador": "BOE-A-2026-101",
                            "titulo": (
                                "Autorización de la planta fotovoltaica "
                                "Aurora Solar."
                            ),
                            "url_html": "https://example.test/html",
                            "url_xml": "https://example.test/xml",
                        },
                    },
                },
            }},
        }},
    }


def _documents(*, count: int = 1) -> pd.DataFrame:
    rows = []
    for index in range(1, count + 1):
        boe_id = f"BOE-A-2026-{100 + index}"
        evidence = f"Se autoriza la planta fotovoltaica Aurora {index}."
        rows.append({
            "identificador": boe_id,
            "fecha_publicacion": pd.Timestamp(2026, 1, index + 1),
            "titulo": evidence,
            "texto_limpio": evidence,
            "xml_status": "ok",
        })
    return pd.DataFrame(rows)


def _write_documents(tmp_path: Path, *, count: int = 1) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "documents.parquet"
    _documents(count=count).to_parquet(path, index=False)
    return path


def _project_extraction(row: pd.Series) -> BOEProjectExtraction:
    evidence = str(row["texto_limpio"])
    index = str(row["identificador"]).rsplit("-", maxsplit=1)[-1]
    return BOEProjectExtraction(
        classification_status=ClassificationStatus.CLASSIFIED,
        document_scope=DocumentScope.GENERATION_PROJECT_SPECIFIC,
        classification_reason="Documento específico de generación.",
        publication_events=[PublicationEvent(
            generation_assets=[GenerationAssetMention(
                local_generation_asset_ref="generation_asset_1",
                names_raw=[f"Aurora {int(index) - 100}"],
                generation_type=GenerationType.PHOTOVOLTAIC,
                evidence=evidence,
            )],
            administrative_actions=[AdministrativeAction(
                action_type=(
                    AdministrativeActionType.PRIOR_ADMINISTRATIVE_AUTHORIZATION
                ),
                decision=AdministrativeDecision.AUTHORIZED,
                targets=["event"],
                evidence=evidence,
            )],
            event_summary="Autorización publicada.",
        )],
        extraction_notes=None,
        boe_id=str(row["identificador"]),
        publication_date=pd.Timestamp(row["fecha_publicacion"]).date(),
    )


def _success_attempts(documents: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in pipeline.prepare_documents(documents).iterrows():
        document = build_source_document(row)
        records.append(build_success_record(
            document=document,
            prepared=None,
            extraction=_project_extraction(row),
            duration_seconds=0.1,
            usage=RunUsage(),
            adjustments=[],
        ))
    return normalise_ai_extraction_attempts_log(pd.DataFrame(records))


def _error_attempt(documents: pd.DataFrame) -> pd.DataFrame:
    row = pipeline.prepare_documents(documents).iloc[0]
    document = build_source_document(row)
    record = build_error_record(
        document=document,
        prepared=None,
        error=RuntimeError("synthetic model failure"),
        processing_stage="agent_run",
        duration_seconds=0.1,
        usage=RunUsage(),
        extraction=None,
        adjustments=[],
    )
    return normalise_ai_extraction_attempts_log(pd.DataFrame([record]))


def _write_attempts(tmp_path: Path, attempts: pd.DataFrame) -> Path:
    path = tmp_path / "attempts.parquet"
    attempts.to_parquet(path, index=False)
    return path


def _reference_sources(tmp_path: Path, *, extra: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    codine = pd.DataFrame([{
        "codauto": "1",
        "comunidad_autonoma": "Andalucía",
        "cpro": "21",
        "provincia": "Huelva",
    }]).astype("string")
    rows = [{
        "codauto": "1",
        "cpro": "21",
        "cmun": "6",
        "dc": "0",
        "nombre": "Alosno",
    }]
    if extra:
        rows.append({
            "codauto": "1",
            "cpro": "21",
            "cmun": "7",
            "dc": "8",
            "nombre": "Aracena",
        })
    dictionary = pd.DataFrame(rows).astype("string")
    codine_path = tmp_path / ("codine-extra.csv" if extra else "codine.csv")
    dictionary_path = tmp_path / (
        "dictionary-extra.csv" if extra else "dictionary.csv"
    )
    codine.to_csv(codine_path, index=False, encoding="utf-8-sig")
    dictionary.to_csv(dictionary_path, index=False, encoding="utf-8-sig")
    return codine_path, dictionary_path, codine, dictionary


def _materialize_reference(tmp_path: Path) -> Path:
    codine_path, dictionary_path, codine, dictionary = _reference_sources(
        tmp_path
    )
    result = materialize_municipality_dimension(
        build_municipality_dimension(codine, dictionary),
        output_dir=tmp_path / "ine-current",
        codine_source_path=codine_path,
        dictionary_source_path=dictionary_path,
        created_at=NOW,
    )
    return result.output_dir


def test_cli_help_lists_the_minimal_command_surface() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "renewables_permitting.pipeline", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    output = completed.stdout
    for command in (
        "source",
        "extract",
        "extraction-subset",
        "history",
        "recanonicalize",
        "silver",
        "downstream",
        "build-reference-data",
        "refresh-reference-data",
        "run",
    ):
        assert command in output


def test_history_cli_has_no_model_execution_flag() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "renewables_permitting.pipeline",
            "history",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--execute-model" not in completed.stdout
    assert "--history-start" in completed.stdout
    assert "--history-end" in completed.stdout


def test_silver_help_exposes_explicit_corrections_option() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "renewables_permitting.pipeline",
            "silver",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--corrections" in completed.stdout


def test_extract_help_exposes_only_explicit_error_retry_selection() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "renewables_permitting.pipeline",
            "extract",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--retry-error-boe" in completed.stdout
    assert "--retry-all-errors" not in completed.stdout


def test_extract_cli_dry_run_plans_only_the_selected_error_retry(
    tmp_path,
    capsys,
) -> None:
    documents = _documents()
    output = tmp_path / "planned-retry"

    code = pipeline.main([
        "extract",
        "--documents", str(_write_documents(tmp_path / "input")),
        "--attempts", str(_write_attempts(
            tmp_path,
            _error_attempt(documents),
        )),
        "--output-dir", str(output),
        "--retry-error-boe", "BOE-A-2026-101",
        "--execute-model",
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
        "--dry-run",
    ])

    assert code == 0
    assert "explicit error retries: 1" in capsys.readouterr().out
    assert not output.exists()


def test_source_subcommand_uses_existing_apis_without_network(
    tmp_path,
    monkeypatch,
) -> None:
    summary = BOESummaryFetchResult(
        publication_date=date(2026, 1, 2),
        source_url="https://example.test/summary",
        retrieved_at=NOW,
        status="success",
        http_status=200,
        boe_status_code="200",
        payload=_summary_payload(),
        item_count=1,
        summary_sha256=None,
        error_type=None,
        error=None,
    )
    xml = BOEXMLFetchResult(
        boe_id="BOE-A-2026-101",
        publication_date=date(2026, 1, 2),
        doc_file_stem="20260102_BOE-A-2026-101",
        source_url="https://example.test/xml",
        retrieved_at=NOW,
        status="downloaded",
        http_status_code=200,
        content=XML,
        byte_count=len(XML),
        xml_sha256=pipeline.sha256(XML).hexdigest(),
        error_type=None,
        error=None,
    )
    monkeypatch.setattr(pipeline, "fetch_boe_summaries", lambda *args: [summary])
    monkeypatch.setattr(
        pipeline,
        "fetch_boe_document_xml",
        lambda **kwargs: xml,
    )

    output_dir = tmp_path / "source"
    code = pipeline.main([
        "source",
        "--start-date", "2026-01-02",
        "--end-date", "2026-01-02",
        "--output-dir", str(output_dir),
    ])

    assert code == 0
    documents = pd.read_parquet(output_dir / "documents.parquet")
    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert documents["identificador"].tolist() == ["BOE-A-2026-101"]
    assert manifest["candidate_policy_id"] == CANDIDATE_POLICY_ID
    assert manifest["counts"]["documents"] == 1
    assert manifest["summaries"][0]["source_url"] == summary.source_url
    assert manifest["xml_documents"][0]["xml_sha256"] == xml.xml_sha256


def test_source_stage_xml_failure_does_not_publish_partial_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    summary = BOESummaryFetchResult(
        publication_date=date(2026, 1, 2),
        source_url="https://example.test/summary",
        retrieved_at=NOW,
        status="success",
        http_status=200,
        boe_status_code="200",
        payload=_summary_payload(),
        item_count=1,
        summary_sha256=None,
        error_type=None,
        error=None,
    )
    real_fetch_xml = pipeline.fetch_boe_document_xml
    calls = 0
    sleeps: list[float] = []

    def exhausted_xml(**kwargs):
        def get(*args, **request_kwargs):
            nonlocal calls
            calls += 1
            raise requests.ConnectionError("temporary network failure")

        return real_fetch_xml(**kwargs, http_get=get)

    monkeypatch.setattr(
        pipeline,
        "fetch_boe_summaries",
        lambda *args: [summary],
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_boe_document_xml",
        exhausted_xml,
    )
    monkeypatch.setattr(time, "sleep", sleeps.append)
    output_dir = tmp_path / "source"

    with pytest.raises(pipeline.PipelineError, match="request_error"):
        pipeline.run_source_stage(
            start_date=date(2026, 1, 2),
            end_date=date(2026, 1, 2),
            output_dir=output_dir,
        )

    assert not output_dir.exists()
    assert calls == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_model_is_denied_by_default_before_writes_or_agent_construction(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _write_documents(tmp_path)
    output_dir = tmp_path / "extraction"
    calls = 0

    def forbidden_agent():
        nonlocal calls
        calls += 1
        raise AssertionError("agent must not be constructed")

    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", forbidden_agent)
    with pytest.raises(pipeline.ModelPermissionRequired, match="1 documents"):
        pipeline.run_extraction_stage(
            documents=documents,
            output_dir=output_dir,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=False,
        )

    assert calls == 0
    assert not output_dir.exists()


def test_canonical_documents_reject_missing_xml_status() -> None:
    documents = _documents()
    documents.loc[0, "xml_status"] = pd.NA

    with pytest.raises(ValueError, match="XML/text"):
        pipeline.prepare_documents(documents)


def test_explicit_missing_attempts_path_cannot_trigger_model_reexecution(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _write_documents(tmp_path)
    calls = 0

    def forbidden_agent():
        nonlocal calls
        calls += 1
        raise AssertionError("a missing resume input must fail first")

    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", forbidden_agent)
    with pytest.raises(FileNotFoundError, match="Attempt input"):
        pipeline.run_extraction_stage(
            documents=documents,
            attempts=tmp_path / "missing-attempts.parquet",
            output_dir=tmp_path / "extraction",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert calls == 0
    assert not (tmp_path / "extraction").exists()


def test_execute_model_is_explicit_and_invokes_adapter_once(
    tmp_path,
    monkeypatch,
) -> None:
    documents_path = _write_documents(tmp_path)
    fake_agent = object()
    constructed = 0
    executed = 0

    def build_agent():
        nonlocal constructed
        constructed += 1
        return fake_agent

    async def extract(run_df, *, agent, attempts_path, checkpoint_every):
        nonlocal executed
        executed += 1
        assert agent is fake_agent
        append_ai_extraction_attempts(_success_attempts(run_df), attempts_path)
        return []

    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", build_agent)
    monkeypatch.setattr(pipeline, "extract_documents", extract)

    result = pipeline.run_extraction_stage(
        documents=documents_path,
        output_dir=tmp_path / "extraction",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=True,
    )

    assert constructed == 1
    assert executed == 1
    assert result.model_calls_planned == 1
    assert result.blocking_review_count == 0
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["scope_classification_policy"] == (
        SCOPE_CLASSIFICATION_POLICY
    )


def test_compatible_attempt_is_reused_without_model_call(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    documents_path = _write_documents(tmp_path)
    attempts_path = _write_attempts(tmp_path, _success_attempts(documents))
    monkeypatch.setattr(
        pipeline,
        "extract_documents",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("model must not run")
        ),
    )

    result = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        output_dir=tmp_path / "reused",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=False,
    )

    assert result.compatible_existing_count == 1
    assert result.model_calls_planned == 0
    assert result.blocking_review_count == 0


def test_cumulative_scopes_reuse_completed_batch_without_duplicate_calls(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents(count=10)
    documents_path = _write_documents(tmp_path / "input", count=10)
    first_scope = tmp_path / "scope-01.csv"
    second_scope = tmp_path / "scope-02.csv"
    documents.iloc[:5][["identificador"]].rename(
        columns={"identificador": "identificador_boe"}
    ).to_csv(first_scope, index=False)
    documents.iloc[5:][["identificador"]].rename(
        columns={"identificador": "identificador_boe"}
    ).to_csv(second_scope, index=False)
    calls: list[list[str]] = []

    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", object)

    async def fake_extract(run_df, *, agent, attempts_path, checkpoint_every):
        calls.append(run_df["identificador"].astype(str).tolist())
        append_ai_extraction_attempts(
            _success_attempts(run_df), attempts_path
        )
        return []

    monkeypatch.setattr(pipeline, "extract_documents", fake_extract)
    first = pipeline.run_extraction_stage(
        documents=documents_path,
        scope_paths=[first_scope],
        output_dir=tmp_path / "batch-01",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=True,
    )
    second = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=first.output_dir,
        scope_paths=[first_scope, second_scope],
        output_dir=tmp_path / "batch-02",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=True,
    )

    assert calls == [
        documents.iloc[:5]["identificador"].tolist(),
        documents.iloc[5:]["identificador"].tolist(),
    ]
    assert second.compatible_existing_count == 5
    assert second.pending_document_count == 5
    assert second.model_calls_planned == 5
    assert second.blocking_review_count == 0


def test_explicit_error_retry_preserves_history_and_leaves_other_error_pending(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents(count=2)
    first_error = _error_attempt(documents.iloc[[0]])
    second_error = _error_attempt(documents.iloc[[1]])
    attempts = pd.concat([first_error, second_error], ignore_index=True)
    attempts_path = _write_attempts(tmp_path, attempts)
    calls: list[list[str]] = []
    fake_agent = object()

    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: fake_agent,
    )

    async def fake_extract(run_df, *, agent, attempts_path, checkpoint_every):
        assert agent is fake_agent
        calls.append(run_df["identificador"].astype(str).tolist())
        new_attempts = _success_attempts(run_df)
        append_ai_extraction_attempts(new_attempts, attempts_path)
        return new_attempts.to_dict(orient="records")

    monkeypatch.setattr(pipeline, "extract_documents", fake_extract)
    result = pipeline.run_extraction_stage(
        documents=_write_documents(tmp_path / "input", count=2),
        attempts=attempts_path,
        retry_error_boe_ids=["BOE-A-2026-101"],
        output_dir=tmp_path / "retried",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=True,
    )

    persisted_attempts = pd.read_parquet(result.attempts_path)
    current = pd.read_parquet(result.current_extractions_path)
    queue = pd.read_parquet(result.review_queue_path)
    assert calls == [["BOE-A-2026-101"]]
    assert len(persisted_attempts) == 3
    assert set(attempts["attempt_id"]).issubset(
        set(persisted_attempts["attempt_id"])
    )
    assert persisted_attempts.loc[
        persisted_attempts["identificador_boe"].eq("BOE-A-2026-101"),
        "extraction_status",
    ].tolist() == ["error", "ok"]
    assert current["identificador_boe"].tolist() == ["BOE-A-2026-101"]
    assert queue["identificador_boe"].tolist() == ["BOE-A-2026-102"]
    assert queue["source_attempt_id"].tolist() == [
        second_error.iloc[0]["attempt_id"]
    ]
    assert result.model_calls_planned == 1
    assert result.blocking_review_count == 1


def test_error_attempt_is_not_retried_without_explicit_selection(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    attempts = _error_attempt(documents)
    monkeypatch.setattr(
        pipeline,
        "extract_documents",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("an unselected error must not execute")
        ),
    )

    result = pipeline.run_extraction_stage(
        documents=_write_documents(tmp_path / "input"),
        attempts=_write_attempts(tmp_path, attempts),
        output_dir=tmp_path / "unchanged-error",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=True,
    )

    persisted = pd.read_parquet(result.attempts_path)
    assert persisted["attempt_id"].tolist() == attempts["attempt_id"].tolist()
    assert result.model_calls_planned == 0
    assert result.blocking_review_count == 1


def test_success_attempt_cannot_be_selected_for_error_retry(tmp_path) -> None:
    documents = _documents()

    with pytest.raises(pipeline.PipelineError, match="latest unresolved error"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, _success_attempts(documents)),
            retry_error_boe_ids=["BOE-A-2026-101"],
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_error_retry_rejects_boe_outside_the_extraction_scope(tmp_path) -> None:
    documents = _documents()

    with pytest.raises(pipeline.PipelineError, match="outside the extraction scope"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, _error_attempt(documents)),
            retry_error_boe_ids=["BOE-A-2026-999"],
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


@pytest.mark.parametrize(
    ("identity_column", "replacement"),
    [
        ("extraction_config_id", "stale-config"),
        ("contract_schema_sha256", "0" * 64),
        ("instructions_sha256", "1" * 64),
    ],
)
def test_error_retry_rejects_incompatible_identity_before_model(
    tmp_path,
    monkeypatch,
    identity_column: str,
    replacement: str,
) -> None:
    attempts = _error_attempt(_documents())
    attempts[identity_column] = replacement
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(
            AssertionError("identity mismatch must fail before the agent")
        ),
    )

    with pytest.raises(pipeline.PipelineError, match="configuration"):
        pipeline.run_extraction_stage(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, attempts),
            retry_error_boe_ids=["BOE-A-2026-101"],
            output_dir=tmp_path / "output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert not (tmp_path / "output").exists()


def test_error_retry_rejects_source_mismatch_before_model(
    tmp_path,
    monkeypatch,
) -> None:
    attempts = _error_attempt(_documents())
    attempts["source_document_sha256"] = "0" * 64
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(
            AssertionError("source mismatch must fail before the agent")
        ),
    )

    with pytest.raises(pipeline.PipelineError, match="source hash"):
        pipeline.run_extraction_stage(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, attempts),
            retry_error_boe_ids=["BOE-A-2026-101"],
            output_dir=tmp_path / "output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert not (tmp_path / "output").exists()


def test_error_retry_rejects_corrupt_structured_attempt(tmp_path) -> None:
    attempts = _error_attempt(_documents())
    attempts.loc[0, "extraction_json"] = "{not-valid-json"

    with pytest.raises(pipeline.PipelineError, match="invalid extraction JSON"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, attempts),
            retry_error_boe_ids=["BOE-A-2026-101"],
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_error_retry_rejects_duplicate_historical_attempt_id(tmp_path) -> None:
    attempt = _error_attempt(_documents())
    attempts = pd.concat([attempt, attempt], ignore_index=True)

    with pytest.raises(pipeline.PipelineError, match="duplicate attempt_id"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, attempts),
            retry_error_boe_ids=["BOE-A-2026-101"],
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_error_retry_rejects_duplicate_new_attempt_id_without_publishing(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    historical = _error_attempt(documents)
    historical_id = str(historical.iloc[0]["attempt_id"])
    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", object)

    async def duplicate_extract(
        run_df, *, agent, attempts_path, checkpoint_every
    ):
        new_attempts = _success_attempts(run_df)
        new_attempts.loc[:, "attempt_id"] = historical_id
        append_ai_extraction_attempts(new_attempts, attempts_path)
        return new_attempts.to_dict(orient="records")

    monkeypatch.setattr(pipeline, "extract_documents", duplicate_extract)
    with pytest.raises(pipeline.PipelineError, match="duplicate new attempt_id"):
        pipeline.run_extraction_stage(
            documents=_write_documents(tmp_path / "input"),
            attempts=_write_attempts(tmp_path, historical),
            retry_error_boe_ids=["BOE-A-2026-101"],
            output_dir=tmp_path / "output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert not (tmp_path / "output").exists()


def test_resume_rejects_old_config_before_constructing_agent(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    attempts = _success_attempts(documents)
    attempts["extraction_config_id"] = "8158661f76a31c87"
    attempts_path = _write_attempts(tmp_path, attempts)
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(
            AssertionError("incompatible attempts must fail before the agent")
        ),
    )

    with pytest.raises(pipeline.PipelineError, match="configuration"):
        pipeline.run_extraction_stage(
            documents=_write_documents(tmp_path / "input"),
            attempts=attempts_path,
            output_dir=tmp_path / "output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert not (tmp_path / "output").exists()


def test_resume_rejects_source_drift_before_constructing_agent(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    attempts = _success_attempts(documents)
    attempts["source_document_sha256"] = "0" * 64
    attempts_path = _write_attempts(tmp_path, attempts)
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(
            AssertionError("stale attempts must fail before the agent")
        ),
    )

    with pytest.raises(pipeline.PipelineError, match="source hash"):
        pipeline.run_extraction_stage(
            documents=_write_documents(tmp_path / "input"),
            attempts=attempts_path,
            output_dir=tmp_path / "output",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert not (tmp_path / "output").exists()


def test_resume_rejects_duplicate_attempt_identity(tmp_path) -> None:
    documents = _documents()
    attempt = _success_attempts(documents)
    attempts = pd.concat([attempt, attempt], ignore_index=True)
    attempts_path = _write_attempts(tmp_path, attempts)

    with pytest.raises(pipeline.PipelineError, match="duplicate attempt_id"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input"),
            attempts=attempts_path,
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_resume_rejects_corrupt_success_attempt(tmp_path) -> None:
    documents = _documents()
    attempts = _success_attempts(documents)
    attempts.loc[0, "extraction_json"] = "{not-valid-json"
    attempts_path = _write_attempts(tmp_path, attempts)

    with pytest.raises(pipeline.PipelineError, match="invalid extraction JSON"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input"),
            attempts=attempts_path,
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )


def test_interrupted_unpublished_batch_is_not_automatically_discovered(
    tmp_path,
    monkeypatch,
) -> None:
    documents_path = _write_documents(tmp_path / "input", count=10)
    monkeypatch.setattr(pipeline, "build_boe_extraction_agent", object)

    async def interrupt_after_three(
        run_df, *, agent, attempts_path, checkpoint_every
    ):
        append_ai_extraction_attempts(
            _success_attempts(run_df.iloc[:3]), attempts_path
        )
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "extract_documents", interrupt_after_three)
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_extraction_stage(
            documents=documents_path,
            output_dir=tmp_path / "interrupted",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=True,
        )

    assert not (tmp_path / "interrupted").exists()
    assert not list(tmp_path.glob(".interrupted.staging-*"))
    plan = pipeline.build_extraction_plan(
        documents=documents_path,
        execute_model=False,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert plan.pending_document_count == 10
    assert plan.model_required_count == 10


def test_review_gate_blocks_silver_and_run_downstream(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    documents_path = _write_documents(tmp_path)
    attempts_path = _write_attempts(tmp_path, _error_attempt(documents))
    result = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        output_dir=tmp_path / "review-extraction",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=False,
    )
    assert result.blocking_review_count == 1
    assert result.review_queue_path.exists()

    monkeypatch.setattr(
        pipeline,
        "run_downstream",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("downstream must not run")
        ),
    )
    with pytest.raises(pipeline.ReviewRequired):
        pipeline.run_silver_stage(
            extraction_snapshot=result.output_dir,
            output_dir=tmp_path / "silver",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "silver").exists()


def test_resume_with_manual_review_reuses_attempt_and_materializes_silver(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    prepared = pipeline.prepare_documents(documents)
    attempts = _error_attempt(documents)
    attempts_path = _write_attempts(tmp_path, attempts)
    source_hash = prepared.iloc[0]["source_document_sha256"]
    manual = pd.DataFrame([{
        "manual_review_id": pd.NA,
        "identificador_boe": "BOE-A-2026-101",
        "source_document_sha256": source_hash,
        "source_attempt_id": attempts.iloc[0]["attempt_id"],
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "review_status": "manually_validated",
        "corrected_extraction_json": _project_extraction(
            prepared.iloc[0]
        ).model_dump_json(),
        "reviewer": "human_reviewer_1",
        "review_notes": "Validated for pipeline resume.",
        "reviewed_at_utc": NOW,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }])
    manual_path = tmp_path / "manual.parquet"
    manual.to_parquet(manual_path, index=False)
    documents_path = _write_documents(tmp_path / "input")
    monkeypatch.setattr(
        pipeline,
        "extract_documents",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("resume must not repeat model calls")
        ),
    )

    extraction = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        manual_reviews=manual_path,
        output_dir=tmp_path / "resumed",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=False,
    )
    silver = pipeline.run_silver_stage(
        extraction_snapshot=extraction.output_dir,
        output_dir=tmp_path / "silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert extraction.blocking_review_count == 0
    assert silver.output_dir.exists()


def test_silver_cli_applies_explicit_versioned_corrections(
    tmp_path: Path,
) -> None:
    documents = _documents()
    prepared = pipeline.prepare_documents(documents)
    row = prepared.iloc[0]
    extraction = _project_extraction(row)
    historical_evidence = "Se convocó información pública anteriormente."
    event = extraction.publication_events[0].model_copy(
        update={
            "administrative_actions": [
                *extraction.publication_events[0].administrative_actions,
                AdministrativeAction(
                    action_type=AdministrativeActionType.PUBLIC_INFORMATION,
                    decision=AdministrativeDecision.ANNOUNCED,
                    targets=["event"],
                    evidence=historical_evidence,
                ),
            ]
        },
        deep=True,
    )
    extraction = extraction.model_copy(
        update={"publication_events": [event]}, deep=True
    )
    document = build_source_document(row)
    attempts = normalise_ai_extraction_attempts_log(pd.DataFrame([
        build_success_record(
            document=document,
            prepared=None,
            extraction=extraction,
            duration_seconds=0.1,
            usage=RunUsage(),
            adjustments=[],
        )
    ]))
    extraction_stage = pipeline.run_extraction_stage(
        documents=_write_documents(tmp_path / "input"),
        attempts=_write_attempts(tmp_path, attempts),
        output_dir=tmp_path / "extraction",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    correction = pd.DataFrame([{
        "correction_id": "pipeline-historical-action-v1",
        "correction_version": 1,
        "status": "approved",
        "boe_id": "BOE-A-2026-101",
        "entity_type": "administrative_action",
        "operation": "exclude",
        "administrative_action_id": "BOE-A-2026-101_event_1_action_2",
        "expected_action_type": "informacion_publica",
        "expected_decision": "convocado",
        "expected_evidence_sha256": evidence_sha256(historical_evidence),
        "reason_code": "historical_antecedent_misattributed",
        "reason": "El trámite pertenece a un antecedente histórico.",
        "decision_source": "synthetic-human-review:v1",
        "reviewed_on": "2026-08-13",
        "reviewer": "human_tfm_review",
    }], columns=ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS)
    correction_path = tmp_path / "corrections.csv"
    correction.to_csv(correction_path, index=False)
    output_dir = tmp_path / "silver-corrected"

    code = pipeline.main([
        "silver",
        "--extraction-snapshot", str(extraction_stage.output_dir),
        "--output-dir", str(output_dir),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
        "--corrections", str(correction_path),
    ])

    assert code == 0
    loaded = pipeline.load_flat_materialization(
        output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert len(loaded.tables["administrative_actions"]) == 1
    assert (output_dir / "applied_corrections.parquet").is_file()
    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["corrections"]["applied_count"] == 1
    assert manifest["corrections"]["source_extraction_config_id"] == (
        EXTRACTION_CONFIG_ID
    )


def test_stale_expected_config_fails_before_any_stage_output(tmp_path) -> None:
    documents = _write_documents(tmp_path)
    with pytest.raises(pipeline.PipelineError, match="configuration"):
        pipeline.run_extraction_stage(
            documents=documents,
            output_dir=tmp_path / "stale",
            expected_extraction_config_id="stale",
            execute_model=False,
        )
    assert not (tmp_path / "stale").exists()


def test_silver_rejects_stale_extraction_snapshot_before_materialization(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    extraction = pipeline.run_extraction_stage(
        documents=_write_documents(tmp_path),
        attempts=_write_attempts(tmp_path, _success_attempts(documents)),
        output_dir=tmp_path / "extraction",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    manifest_path = extraction.manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extraction_config_id"] = "stale-config"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        pipeline,
        "materialize_current_extractions",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("stale lineage must fail before Silver")
        ),
    )

    with pytest.raises(pipeline.PipelineError, match="incompatible"):
        pipeline.run_silver_stage(
            extraction_snapshot=extraction.output_dir,
            output_dir=tmp_path / "silver",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )

    assert not (tmp_path / "silver").exists()


def test_downstream_subcommand_is_a_thin_noninteractive_wrapper(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []

    def downstream(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(materialization_id="downstream-id")

    monkeypatch.setattr(pipeline, "run_downstream", downstream)
    monkeypatch.setattr(
        pipeline,
        "input",
        lambda *args: (_ for _ in ()).throw(AssertionError("no prompt")),
        raising=False,
    )
    code = pipeline.main([
        "downstream",
        "--silver-snapshot", str(tmp_path / "silver"),
        "--municipality-reference", str(tmp_path / "ine"),
        "--output-dir", str(tmp_path / "downstream"),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    assert code == 0
    assert len(calls) == 1
    assert calls[0] == {
        "silver_snapshot": tmp_path / "silver",
        "municipality_reference": tmp_path / "ine",
        "output_dir": tmp_path / "downstream",
        "expected_extraction_config_id": EXTRACTION_CONFIG_ID,
    }


def test_downstream_validation_failure_has_concise_cli_error(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "run_downstream",
        lambda **kwargs: (_ for _ in ()).throw(
            pipeline.DownstreamError("synthetic stale Silver")
        ),
    )

    code = pipeline.main([
        "downstream",
        "--silver-snapshot", str(tmp_path / "silver"),
        "--municipality-reference", str(tmp_path / "ine"),
        "--output-dir", str(tmp_path / "downstream"),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    assert code == pipeline.EXIT_FAILURE
    assert "synthetic stale Silver" in capsys.readouterr().err


def test_build_reference_materializes_without_downstream(
    tmp_path,
    monkeypatch,
) -> None:
    codine, dictionary, *_ = _reference_sources(tmp_path)
    monkeypatch.setattr(
        pipeline,
        "run_downstream",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("build reference must not run downstream")
        ),
    )

    code = pipeline.main([
        "build-reference-data",
        "--codine", str(codine),
        "--dictionary", str(dictionary),
        "--output-dir", str(tmp_path / "candidate"),
    ])

    assert code == 0
    assert (tmp_path / "candidate" / "manifest.json").exists()


def _patch_valid_silver(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "load_flat_materialization",
        lambda *args, **kwargs: SimpleNamespace(
            materialization_id="silver-id",
            extraction_config_id=EXTRACTION_CONFIG_ID,
        ),
    )


def test_refresh_unchanged_skips_prompt_and_downstream(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    current = _materialize_reference(tmp_path)
    codine, dictionary, *_ = _reference_sources(tmp_path / "new")
    _patch_valid_silver(monkeypatch)
    monkeypatch.setattr(
        "builtins.input",
        lambda *args: (_ for _ in ()).throw(AssertionError("no prompt")),
    )
    monkeypatch.setattr(
        pipeline,
        "run_downstream",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("no rebuild")),
    )

    code = pipeline.main([
        "refresh-reference-data",
        "--codine", str(codine),
        "--dictionary", str(dictionary),
        "--current-reference", str(current),
        "--candidate-reference-output", str(tmp_path / "candidate"),
        "--silver-snapshot", str(tmp_path / "silver"),
        "--downstream-output", str(tmp_path / "downstream"),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    assert code == 0
    output = capsys.readouterr().out
    assert "No semantic INE changes." in output
    assert "Downstream rebuild not required." in output
    assert not (tmp_path / "candidate").exists()


@pytest.mark.parametrize(
    ("response", "expect_prompt"),
    [("n", True), (EOFError(), True)],
)
def test_refresh_changed_decline_or_eof_is_safe(
    tmp_path,
    monkeypatch,
    response,
    expect_prompt,
) -> None:
    current = _materialize_reference(tmp_path)
    codine, dictionary, *_ = _reference_sources(tmp_path / "changed", extra=True)
    _patch_valid_silver(monkeypatch)
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr("builtins.input", answer)
    calls = []
    monkeypatch.setattr(pipeline, "run_downstream", lambda **kwargs: calls.append(kwargs))

    code = pipeline.main([
        "refresh-reference-data",
        "--codine", str(codine),
        "--dictionary", str(dictionary),
        "--current-reference", str(current),
        "--candidate-reference-output", str(tmp_path / "candidate"),
        "--silver-snapshot", str(tmp_path / "silver"),
        "--downstream-output", str(tmp_path / "downstream"),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    assert code == 0
    assert bool(prompts) is expect_prompt
    assert prompts == ["Continue? [y/N] "]
    assert calls == []
    assert not (tmp_path / "candidate").exists()


@pytest.mark.parametrize(("confirmation", "answer"), [(False, "y"), (True, None)])
def test_refresh_changed_explicit_confirmation_runs_downstream_once(
    tmp_path,
    monkeypatch,
    capsys,
    confirmation,
    answer,
) -> None:
    current = _materialize_reference(tmp_path)
    codine, dictionary, *_ = _reference_sources(tmp_path / "changed", extra=True)
    _patch_valid_silver(monkeypatch)
    if confirmation:
        monkeypatch.setattr(
            "builtins.input",
            lambda *args: (_ for _ in ()).throw(AssertionError("--yes prompts")),
        )
    else:
        monkeypatch.setattr("builtins.input", lambda prompt: answer)
    calls = []

    def downstream(**kwargs):
        loaded = pipeline.load_municipality_reference(
            kwargs["municipality_reference"]
        )
        assert loaded.input_dir == tmp_path / "candidate"
        calls.append(kwargs)
        return SimpleNamespace(materialization_id="downstream-id")

    monkeypatch.setattr(pipeline, "run_downstream", downstream)
    arguments = [
        "refresh-reference-data",
        "--codine", str(codine),
        "--dictionary", str(dictionary),
        "--current-reference", str(current),
        "--candidate-reference-output", str(tmp_path / "candidate"),
        "--silver-snapshot", str(tmp_path / "silver"),
        "--downstream-output", str(tmp_path / "downstream"),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ]
    if confirmation:
        arguments.append("--yes")

    assert pipeline.main(arguments) == 0
    output = capsys.readouterr().out
    assert "full historical Silver snapshot" in output
    assert "will NOT call the AI model or regenerate Silver" in output
    assert len(calls) == 1
    assert calls[0]["municipality_reference"] == tmp_path / "candidate"


def test_run_from_documents_dry_run_has_no_source_model_or_writes(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    documents = _write_documents(tmp_path)
    reference = _materialize_reference(tmp_path / "reference")
    monkeypatch.setattr(
        pipeline,
        "run_source_stage",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("no source")),
    )
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("no agent")),
    )
    run_root = tmp_path / "runs"

    code = pipeline.main([
        "run",
        "--documents", str(documents),
        "--runs-dir", str(run_root),
        "--run-id", "freeze-test",
        "--municipality-reference", str(reference),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
        "--execute-model",
        "--dry-run",
    ])

    assert code == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert not run_root.exists()


def test_full_source_run_dry_run_has_no_network_model_or_writes(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    reference = _materialize_reference(tmp_path / "reference")
    monkeypatch.setattr(
        pipeline,
        "run_source_stage",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("no BOE")),
    )
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("no model")),
    )
    monkeypatch.setattr(
        pipeline,
        "run_downstream",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("no downstream")),
    )
    runs_dir = tmp_path / "runs"

    code = pipeline.main([
        "run",
        "--start-date", "2026-01-01",
        "--end-date", "2026-01-02",
        "--runs-dir", str(runs_dir),
        "--run-id", "source-dry",
        "--municipality-reference", str(reference),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
        "--execute-model",
        "--dry-run",
    ])

    assert code == 0
    assert "document counts unavailable without BOE access" in capsys.readouterr().out
    assert not runs_dir.exists()


def test_run_denies_pending_model_work_without_explicit_permission(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    documents = _write_documents(tmp_path)
    reference = _materialize_reference(tmp_path / "reference")
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("no agent")),
    )
    monkeypatch.setattr(
        pipeline,
        "extract_documents",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("no extraction")
        ),
    )
    runs_dir = tmp_path / "runs"

    code = pipeline.main([
        "run",
        "--documents", str(documents),
        "--runs-dir", str(runs_dir),
        "--run-id", "denied",
        "--municipality-reference", str(reference),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    captured = capsys.readouterr()
    assert code == pipeline.EXIT_MODEL_PERMISSION_REQUIRED
    assert (
        "1 documents require model execution" in captured.err
        and "--execute-model" in captured.err
    )
    assert not runs_dir.exists()


def test_run_review_gate_stops_before_silver_and_downstream(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    documents_path = _write_documents(tmp_path)
    attempts_path = _write_attempts(tmp_path, _error_attempt(documents))
    reference = _materialize_reference(tmp_path / "reference")
    monkeypatch.setattr(
        pipeline,
        "run_silver_stage",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("review must stop before Silver")
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "run_downstream",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("review must stop before downstream")
        ),
    )
    runs_dir = tmp_path / "runs"

    code = pipeline.main([
        "run",
        "--documents", str(documents_path),
        "--attempts", str(attempts_path),
        "--runs-dir", str(runs_dir),
        "--run-id", "review-stop",
        "--municipality-reference", str(reference),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    run_root = runs_dir / "review-stop"
    assert code == pipeline.EXIT_REVIEW_REQUIRED
    assert (run_root / "extraction" / "review_queue.parquet").exists()
    assert not (run_root / "silver").exists()
    assert not (run_root / "downstream").exists()
    assert not (run_root / "run_manifest.json").exists()


def test_run_from_existing_documents_reuses_attempts_end_to_end(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    documents_path = _write_documents(tmp_path)
    attempts_path = _write_attempts(tmp_path, _success_attempts(documents))
    reference_path = _materialize_reference(tmp_path / "reference")
    reference = pipeline.load_municipality_reference(reference_path)
    monkeypatch.setattr(
        pipeline,
        "run_source_stage",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("no source")),
    )
    monkeypatch.setattr(
        pipeline,
        "build_boe_extraction_agent",
        lambda: (_ for _ in ()).throw(AssertionError("no agent")),
    )
    monkeypatch.setattr(
        pipeline,
        "extract_documents",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("compatible attempts must be reused")
        ),
    )
    runs_dir = tmp_path / "runs"

    code = pipeline.main([
        "run",
        "--documents", str(documents_path),
        "--attempts", str(attempts_path),
        "--runs-dir", str(runs_dir),
        "--run-id", "existing-documents",
        "--municipality-reference", str(reference_path),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    run_root = runs_dir / "existing-documents"
    assert code == 0
    assert not (run_root / "source").exists()
    for stage in ("extraction", "silver", "downstream"):
        assert (run_root / stage).is_dir()
    silver = pipeline.load_flat_materialization(
        run_root / "silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    manifest = json.loads(
        (run_root / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_mode"] == "existing_documents"
    assert manifest["silver_materialization_id"] == silver.materialization_id
    assert manifest["ine_reference_id"] == reference.semantic_reference_id
    assert manifest["downstream_materialization_id"]


def test_multiple_scopes_are_deterministic_and_report_overlap(
    tmp_path,
    capsys,
) -> None:
    documents = pipeline.prepare_documents(_documents(count=3))
    first = tmp_path / "first.csv"
    second = tmp_path / "second.parquet"
    pd.DataFrame({"identificador": [
        "BOE-A-2026-102", "BOE-A-2026-101"
    ]}).to_csv(first, index=False)
    pd.DataFrame({"identificador_boe": [
        "BOE-A-2026-102", "BOE-A-2026-103"
    ]}).to_parquet(second, index=False)

    scoped, summary = pipeline.apply_document_scopes(
        documents,
        [first, second],
    )

    assert summary.input_sizes == (2, 2)
    assert summary.overlap_count == 1
    assert summary.final_unique_count == 3
    assert scoped["identificador"].tolist() == [
        "BOE-A-2026-101", "BOE-A-2026-102", "BOE-A-2026-103"
    ]

    pipeline.run_extraction_stage(
        documents=_write_documents(tmp_path / "input", count=3),
        scope_paths=[first, second],
        output_dir=tmp_path / "planned",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=True,
        dry_run=True,
    )
    output = capsys.readouterr().out
    assert f"scope: path={first} size=2" in output
    assert f"scope: path={second} size=2" in output
    assert "scope overlap: 1" in output
    assert "scope final unique BOE count: 3" in output
    assert not (tmp_path / "planned").exists()


def test_scope_rejects_duplicate_boe_ids_within_one_input(tmp_path) -> None:
    documents = pipeline.prepare_documents(_documents(count=2))
    duplicate_scope = tmp_path / "duplicates.csv"
    pd.DataFrame({
        "identificador_boe": ["BOE-A-2026-101", "BOE-A-2026-101"]
    }).to_csv(duplicate_scope, index=False)

    with pytest.raises(ValueError, match="duplicate BOE identifiers"):
        pipeline.apply_document_scopes(documents, [duplicate_scope])


def test_existing_output_is_never_overwritten(tmp_path) -> None:
    documents = _write_documents(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        pipeline.run_extraction_stage(
            documents=documents,
            output_dir=output,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
            execute_model=False,
            dry_run=True,
        )
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_real_contracts_flow_documents_to_silver_to_downstream(
    tmp_path,
    monkeypatch,
) -> None:
    documents = _documents()
    documents_path = _write_documents(tmp_path)
    attempts = _write_attempts(tmp_path, _success_attempts(documents))
    extraction = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=attempts,
        output_dir=tmp_path / "extraction",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=False,
    )
    silver = pipeline.run_silver_stage(
        extraction_snapshot=extraction.output_dir,
        output_dir=tmp_path / "silver",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    reference = _materialize_reference(tmp_path / "reference")

    result = pipeline.run_downstream(
        silver_snapshot=silver.output_dir,
        municipality_reference=reference,
        output_dir=tmp_path / "downstream",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        created_at=NOW,
    )

    assert result.projects_path.exists()
    assert result.project_events_path.exists()
    assert result.project_locations_path.exists()
    assert result.project_location_sources_path.exists()
    assert pd.read_parquet(result.projects_path)["project_id"].nunique() == 1


def _write_scope(
    path: Path,
    boe_ids: list[str],
    *,
    documents: pd.DataFrame | None = None,
) -> Path:
    frame = pd.DataFrame({"identificador_boe": boe_ids})
    if documents is not None:
        prepared = pipeline.prepare_documents(documents).set_index(
            "identificador"
        )
        frame["source_document_sha256"] = [
            prepared.loc[boe_id, "source_document_sha256"]
            for boe_id in boe_ids
        ]
    frame.to_csv(path, index=False)
    return path


def _publish_parent_snapshot(
    tmp_path: Path,
    *,
    documents: pd.DataFrame,
    attempts: pd.DataFrame,
    manual_reviews: pd.DataFrame | None = None,
) -> Path:
    documents_path = tmp_path / "documents.parquet"
    attempts_path = tmp_path / "attempts.parquet"
    documents.to_parquet(documents_path, index=False)
    attempts.to_parquet(attempts_path, index=False)
    manual_path = None
    if manual_reviews is not None:
        manual_path = tmp_path / "manual-reviews.parquet"
        manual_reviews.to_parquet(manual_path, index=False)
    result = pipeline.run_extraction_stage(
        documents=documents_path,
        attempts=attempts_path,
        manual_reviews=manual_path,
        output_dir=tmp_path / "parent",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        execute_model=False,
    )
    return result.output_dir


def _manual_review(
    document: pd.Series,
    attempt: pd.Series,
    *,
    status: str,
    reviewed_at: datetime,
) -> dict[str, object]:
    return {
        "manual_review_id": pd.NA,
        "identificador_boe": str(document["identificador"]),
        "source_document_sha256": str(document["source_document_sha256"]),
        "source_attempt_id": str(attempt["attempt_id"]),
        "extraction_config_id": EXTRACTION_CONFIG_ID,
        "review_status": status,
        "corrected_extraction_json": (
            _project_extraction(document).model_dump_json()
            if status == "manually_validated"
            else pd.NA
        ),
        "reviewer": "human_reviewer_1",
        "review_notes": f"Contract test decision: {status}.",
        "reviewed_at_utc": reviewed_at,
        "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    }


def _rewrite_manifest_artifact(
    snapshot: Path,
    artifact: str,
    *,
    row_count: int,
) -> None:
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = snapshot / manifest["artifacts"][artifact]["filename"]
    manifest["artifacts"][artifact]["row_count"] = row_count
    manifest["artifacts"][artifact]["sha256"] = hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
    if artifact == "attempts":
        manifest["counts"]["attempts"] = row_count
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def test_extraction_subset_preserves_selected_history_and_parent(
    tmp_path: Path,
) -> None:
    documents = pipeline.prepare_documents(_documents(count=3))
    attempts = _success_attempts(documents)
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=attempts,
        manual_reviews=pd.DataFrame([_manual_review(
            documents.iloc[1],
            attempts.iloc[1],
            status="manually_validated",
            reviewed_at=NOW,
        )]),
    )
    scope = _write_scope(
        tmp_path / "scope.csv",
        ["BOE-A-2026-101", "BOE-A-2026-103"],
        documents=documents,
    )
    parent_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in parent.iterdir()
    }

    result = pipeline.materialize_extraction_subset(
        input_extraction=parent,
        scope_paths=[scope],
        output_dir=tmp_path / "subset",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    loaded_parent = pipeline.load_extraction_snapshot(
        parent,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    loaded_subset = pipeline.load_extraction_snapshot(
        result.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    expected_ids = {"BOE-A-2026-101", "BOE-A-2026-103"}
    assert set(loaded_subset.documents["identificador"].astype(str)) == expected_ids
    assert set(loaded_subset.attempts["identificador_boe"].astype(str)) == expected_ids
    assert loaded_subset.manual_reviews.empty
    expected_current = loaded_parent.current_extractions.loc[
        loaded_parent.current_extractions["identificador_boe"]
        .astype(str)
        .isin(expected_ids)
    ].reset_index(drop=True)
    parent_only_columns = [
        column
        for column in expected_current.columns
        if column not in loaded_subset.current_extractions.columns
    ]
    assert expected_current[parent_only_columns].isna().all().all()
    assert pipeline._frame_equal(
        loaded_subset.current_extractions,
        expected_current.loc[
            :, loaded_subset.current_extractions.columns
        ],
        sort_by=("identificador_boe", "attempt_id"),
    )
    assert parent_hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in parent.iterdir()
    }
    assert result.scope_boe_count == 2
    assert result.selected_document_count == 2
    assert loaded_subset.manifest["snapshot_type"] == "extraction_subset"
    assert loaded_subset.manifest["stage_version"] == "1"
    assert loaded_subset.manifest["parent"]["snapshot_identity_sha256"] == (
        pipeline._extraction_snapshot_identity(loaded_parent)
    )
    assert loaded_subset.manifest["subset"]["scope_boe_count"] == 2
    assert loaded_subset.manifest["snapshot_identity_sha256"] != (
        pipeline._extraction_snapshot_identity(loaded_parent)
    )
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        loaded_subset.manifest["deterministic_code_sha256"],
    )


def test_extraction_subset_preserves_multiple_attempts_and_is_idempotent(
    tmp_path: Path,
) -> None:
    documents = _documents(count=2)
    first = documents.iloc[[0]]
    failed = _error_attempt(first)
    failed.loc[:, "attempt_id"] = "attempt-failed"
    failed.loc[:, "extracted_at"] = NOW - timedelta(minutes=2)
    succeeded = _success_attempts(first)
    succeeded.loc[:, "attempt_id"] = "attempt-success"
    succeeded.loc[:, "extracted_at"] = NOW - timedelta(minutes=1)
    derived = succeeded.copy(deep=True)
    derived.loc[:, "attempt_id"] = "attempt-derived"
    derived.loc[:, "attempt_origin"] = "recanonicalized"
    derived.loc[:, "source_attempt_id"] = "attempt-success"
    derived.loc[:, "extracted_at"] = NOW
    attempts = normalise_ai_extraction_attempts_log(pd.concat(
        [failed, succeeded, derived, _success_attempts(documents.iloc[[1]])],
        ignore_index=True,
    ))
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=attempts,
    )
    scope = _write_scope(
        tmp_path / "scope.csv",
        ["BOE-A-2026-101"],
        documents=documents,
    )

    first_subset = pipeline.materialize_extraction_subset(
        input_extraction=parent,
        scope_paths=[scope],
        output_dir=tmp_path / "subset-1",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    second_subset = pipeline.materialize_extraction_subset(
        input_extraction=first_subset.output_dir,
        scope_paths=[scope],
        output_dir=tmp_path / "subset-2",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    first_loaded = pipeline.load_extraction_snapshot(
        first_subset.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    second_loaded = pipeline.load_extraction_snapshot(
        second_subset.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert first_loaded.attempts["attempt_id"].tolist() == [
        "attempt-failed", "attempt-success", "attempt-derived"
    ]
    pd.testing.assert_frame_equal(first_loaded.attempts, second_loaded.attempts)
    pd.testing.assert_frame_equal(
        first_loaded.current_extractions,
        second_loaded.current_extractions,
    )
    assert first_loaded.attempts["attempt_id"].is_unique
    assert first_loaded.manifest["snapshot_identity_sha256"] == (
        second_loaded.manifest["snapshot_identity_sha256"]
    )


def test_extraction_subset_preserves_manual_decisions_and_excludes_other_reviews(
    tmp_path: Path,
) -> None:
    documents = pipeline.prepare_documents(_documents(count=3))
    attempts = _success_attempts(documents)
    attempts_by_boe = {
        str(row["identificador_boe"]): row
        for _, row in attempts.iterrows()
    }
    reviews = pd.DataFrame([
        _manual_review(
            row,
            attempts_by_boe[str(row["identificador"])],
            status=status,
            reviewed_at=NOW + timedelta(seconds=index),
        )
        for index, (row, status) in enumerate(zip(
            (documents.iloc[0], documents.iloc[1], documents.iloc[2]),
            ("rejected", "manually_validated", "rejected"),
            strict=True,
        ))
    ])
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=attempts,
        manual_reviews=reviews,
    )
    scope = _write_scope(
        tmp_path / "scope.csv",
        ["BOE-A-2026-101", "BOE-A-2026-102"],
        documents=documents,
    )

    result = pipeline.materialize_extraction_subset(
        input_extraction=parent,
        scope_paths=[scope],
        output_dir=tmp_path / "subset",
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    subset = pipeline.load_extraction_snapshot(
        result.output_dir,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )

    assert set(subset.manual_reviews["identificador_boe"].astype(str)) == {
        "BOE-A-2026-101", "BOE-A-2026-102"
    }
    assert set(subset.manual_reviews["review_status"].astype(str)) == {
        "rejected", "manually_validated"
    }
    assert subset.current_extractions["identificador_boe"].tolist() == [
        "BOE-A-2026-102"
    ]
    assert subset.current_extractions["selection_source"].tolist() == [
        "manually_validated"
    ]
    assert subset.review_queue.empty


def test_extraction_subset_rejects_dangling_review_before_publication(
    tmp_path: Path,
) -> None:
    documents = pipeline.prepare_documents(_documents())
    attempts = _success_attempts(documents)
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=attempts,
        manual_reviews=pd.DataFrame([_manual_review(
            documents.iloc[0],
            attempts.iloc[0],
            status="rejected",
            reviewed_at=NOW,
        )]),
    )
    manual_path = parent / "manual_reviews.parquet"
    manual = pd.read_parquet(manual_path)
    manual.loc[:, "source_attempt_id"] = "missing-attempt"
    manual.to_parquet(manual_path, index=False)
    _rewrite_manifest_artifact(parent, "manual_reviews", row_count=1)
    scope = _write_scope(tmp_path / "scope.csv", ["BOE-A-2026-101"])

    with pytest.raises(ValueError, match="source_attempt_id.*no existe"):
        pipeline.materialize_extraction_subset(
            input_extraction=parent,
            scope_paths=[scope],
            output_dir=tmp_path / "subset",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "subset").exists()


def test_extraction_subset_rejects_duplicate_parent_attempt_id(
    tmp_path: Path,
) -> None:
    documents = _documents()
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=_success_attempts(documents),
    )
    attempt_path = parent / "attempts.parquet"
    attempts = pd.read_parquet(attempt_path)
    pd.concat([attempts, attempts], ignore_index=True).to_parquet(
        attempt_path,
        index=False,
    )
    _rewrite_manifest_artifact(parent, "attempts", row_count=2)
    scope = _write_scope(tmp_path / "scope.csv", ["BOE-A-2026-101"])

    with pytest.raises(pipeline.PipelineError, match="duplicate attempt_id"):
        pipeline.materialize_extraction_subset(
            input_extraction=parent,
            scope_paths=[scope],
            output_dir=tmp_path / "subset",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    assert not (tmp_path / "subset").exists()


def test_extraction_subset_rejects_config_or_scope_source_mismatch(
    tmp_path: Path,
) -> None:
    documents = _documents()
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=_success_attempts(documents),
    )
    bad_scope = tmp_path / "bad-scope.csv"
    pd.DataFrame([{
        "identificador_boe": "BOE-A-2026-101",
        "source_document_sha256": "0" * 64,
    }]).to_csv(bad_scope, index=False)

    with pytest.raises(pipeline.PipelineError, match="scope source hash"):
        pipeline.materialize_extraction_subset(
            input_extraction=parent,
            scope_paths=[bad_scope],
            output_dir=tmp_path / "bad-source",
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
    with pytest.raises(pipeline.PipelineError, match="configuration mismatch"):
        pipeline.materialize_extraction_subset(
            input_extraction=parent,
            scope_paths=[bad_scope],
            output_dir=tmp_path / "bad-config",
            expected_extraction_config_id="stale-config",
        )
    assert not (tmp_path / "bad-source").exists()
    assert not (tmp_path / "bad-config").exists()


def test_extraction_subset_supports_empty_reuse_and_cli(
    tmp_path: Path,
) -> None:
    documents = _documents()
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=_success_attempts(documents),
    )
    scope = _write_scope(tmp_path / "scope.csv", ["BOE-A-2026-999"])
    output = tmp_path / "empty-subset"

    code = pipeline.main([
        "extraction-subset",
        "--input-extraction", str(parent),
        "--scope", str(scope),
        "--output-dir", str(output),
        "--expected-extraction-config-id", EXTRACTION_CONFIG_ID,
    ])

    assert code == 0
    loaded = pipeline.load_extraction_snapshot(
        output,
        expected_extraction_config_id=EXTRACTION_CONFIG_ID,
    )
    assert loaded.documents.empty
    assert loaded.attempts.empty
    assert loaded.current_extractions.empty
    assert loaded.review_queue.empty


def test_extract_still_rejects_attempts_outside_scope(tmp_path: Path) -> None:
    documents = _documents(count=2)
    parent = _publish_parent_snapshot(
        tmp_path,
        documents=documents,
        attempts=_success_attempts(documents),
    )
    scope = _write_scope(tmp_path / "scope.csv", ["BOE-A-2026-101"])

    with pytest.raises(pipeline.PipelineError, match="outside the cumulative scope"):
        pipeline.build_extraction_plan(
            documents=_write_documents(tmp_path / "input", count=2),
            attempts=parent,
            scope_paths=[scope],
            execute_model=False,
            expected_extraction_config_id=EXTRACTION_CONFIG_ID,
        )
