from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import renewables_permitting.pipeline as pipeline
from renewables_permitting.boe_candidates import CANDIDATE_POLICY_ID
from renewables_permitting.boe_documents import BOEXMLFetchResult
from renewables_permitting.boe_source import BOESummaryFetchResult
from renewables_permitting.extraction.config import (
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_VALIDATION_VERSION,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
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
        "silver",
        "downstream",
        "build-reference-data",
        "refresh-reference-data",
        "run",
    ):
        assert command in output


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
    assert pd.read_parquet(result.projects_path)["project_id"].nunique() == 1
