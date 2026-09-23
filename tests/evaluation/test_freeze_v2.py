from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from evaluation.final_holdout_v1 import contract as v1
from evaluation.final_holdout_v2 import freeze as publication
from evaluation.final_holdout_v2.annotation import upsert_truth_row
from evaluation.final_holdout_v2.cli import main
from evaluation.final_holdout_v2.contract import (
    CONTRACT_VERSION,
    FROZEN_MANIFEST_VERSION,
    FROZEN_SELECTION,
    TABLE_SPECS,
    TRUTH_MANIFEST,
    TruthContractError,
    frozen_manifest_identity,
    load_truth,
    sha256_file,
)
from renewables_permitting.extraction.documents import build_source_document
from test_final_holdout_v2 import NON_RELEVANT_BOE, PROJECT_BOE, _write_v2_truth


def _bytes(path: Path) -> dict[str, bytes]:
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def _edit_csv(path: Path, column: str, value: str) -> None:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, column] = value
    frame.to_csv(path, index=False)


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    truth_dir = _write_v2_truth(tmp_path / "working", include_secondary=True)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = pd.DataFrame([
        {
            "identificador": boe,
            "fecha_publicacion": pd.Timestamp("2099-01-01"),
            "titulo": "Publicación sintética",
            "texto_limpio": (
                "Se otorga autorización a la Planta Sintética. "
                "25 MW de potencia instalada."
            ),
        }
        for boe in (PROJECT_BOE, NON_RELEVANT_BOE)
    ])
    source.to_parquet(source_dir / "documents.parquet", index=False)
    source_hashes = {
        row["identificador"]: build_source_document(row).source_document_sha256
        for _, row in source.iterrows()
    }
    documents = pd.read_csv(truth_dir / "documents.csv", dtype=str)
    documents["source_document_sha256"] = documents["identificador_boe"].map(source_hashes)
    documents.to_csv(truth_dir / "documents.csv", index=False)
    selection_path = tmp_path / "selection.csv"
    selection = documents[["identificador_boe", "source_document_sha256"]].copy()
    selection["source_snapshot_id"] = "d" * 64
    selection.to_csv(selection_path, index=False)
    metadata_path = truth_dir / "truth_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["holdout_artifact_identity"] = sha256_file(selection_path)
    metadata["custom_human_provenance"] = "Preserve this original note verbatim."
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return truth_dir, selection_path, source_dir


def _freeze(inputs: tuple[Path, Path, Path], output: Path):
    truth, selection, source = inputs
    return publication.freeze_truth(
        truth, output, holdout_path=selection, documents_path=source,
    )


def test_freeze_roundtrip_preserves_all_bytes_identity_and_provenance(inputs, tmp_path):
    truth, selection, source = inputs
    before = _bytes(truth)
    source_before = _bytes(source)
    working = load_truth(truth, require_complete=True)
    assert working.manifest is None
    output = tmp_path / "frozen"
    frozen = _freeze(inputs, output)
    manifest_hash = sha256_file(output / TRUTH_MANIFEST)
    reloaded = load_truth(output, require_frozen=True, expected_manifest_sha256=manifest_hash)
    assert frozen.truth_artifact_id == working.truth_artifact_id == reloaded.truth_artifact_id
    assert frozen.table_semantic_sha256 == working.table_semantic_sha256
    assert _bytes(truth) == before
    assert _bytes(source) == source_before
    assert {name: (output / name).read_bytes() for name in before} == before
    assert (output / FROZEN_SELECTION).read_bytes() == selection.read_bytes()
    assert len(_bytes(output)) == 13
    manifest = reloaded.manifest
    assert manifest["manifest_version"] == FROZEN_MANIFEST_VERSION
    assert manifest["truth_contract_version"] == CONTRACT_VERSION
    assert manifest["document_count"] == 2  # No production cardinality hardcoding.
    assert manifest["holdout_artifact_identity"] == sha256_file(selection)
    assert manifest["source_snapshot_identity"] == "d" * 64
    assert manifest["freeze_entry_point"] == "evaluation.final_holdout_v2.freeze.freeze_truth"
    assert len(manifest["freeze_tool_sha256"]) == 64
    assert manifest["created_at"].endswith("+00:00")
    assert manifest["manifest_identity_sha256"] == frozen_manifest_identity(manifest)
    assert manifest["reviewer_ids"] == ["synthetic_reviewer"]
    assert reloaded.metadata["custom_human_provenance"] == "Preserve this original note verbatim."
    assert manifest["truth_file_hashes"] == {
        name: sha256_file(output / name) for name in (*before, FROZEN_SELECTION)
    }
    assert str(tmp_path) not in json.dumps(manifest)
    assert not list(tmp_path.glob(".frozen.staging-*"))


@pytest.mark.parametrize("kind", ["empty_directory", "nonempty_directory", "file", "dangling_symlink"])
def test_existing_destination_never_changes(inputs, tmp_path, kind):
    output = tmp_path / "existing"
    if kind.endswith("directory"):
        output.mkdir()
        if kind == "nonempty_directory":
            (output / "keep.txt").write_text("Existing data")
    elif kind == "file":
        output.write_bytes(b"Existing file")
    else:
        output.symlink_to(tmp_path / "missing")
    source_before = _bytes(inputs[0])
    before = _bytes(output) if output.is_dir() else None
    with pytest.raises(FileExistsError):
        _freeze(inputs, output)
    assert _bytes(inputs[0]) == source_before
    if before is not None:
        assert _bytes(output) == before
    elif kind == "file":
        assert output.read_bytes() == b"Existing file"
    else:
        assert output.is_symlink()


def test_destination_inside_source_is_rejected_before_writing(inputs):
    before = _bytes(inputs[0])
    with pytest.raises(TruthContractError, match="inside"):
        _freeze(inputs, inputs[0] / "child" / "frozen")
    assert _bytes(inputs[0]) == before
    assert not (inputs[0] / "child").exists()


@pytest.mark.parametrize("defect", [
    "draft", "invalid_domain", "orphan", "missing_evidence", "nonliteral_evidence",
    "pending_key", "unexpected_file", "missing_metadata", "invalid_metadata", "symlink",
])
def test_invalid_truth_is_not_published_or_repaired(inputs, tmp_path, defect):
    truth = inputs[0]
    if defect == "draft":
        _edit_csv(truth / "documents.csv", "annotation_status", "draft")
    elif defect == "invalid_domain":
        _edit_csv(truth / "administrative_actions.csv", "expected_decision", "INVALID")
    elif defect == "orphan":
        _edit_csv(truth / "administrative_actions.csv", "expected_affected_generation_asset_keys_json", '["absent"]')
    elif defect == "missing_evidence":
        evidence = pd.read_csv(truth / "evidence_passages.csv")
        evidence.loc[evidence.owner_type.ne("administrative_action")].to_csv(truth / "evidence_passages.csv", index=False)
    elif defect == "nonliteral_evidence":
        _edit_csv(truth / "evidence_passages.csv", "passage_text", "Not present in the source.")
    elif defect == "pending_key":
        _edit_csv(truth / "administrative_actions.csv", "action_key", "pending")
        _edit_csv(truth / "action_targets.csv", "action_key", "pending")
        _edit_csv(truth / "evidence_passages.csv", "owner_key", "pending")
    elif defect == "unexpected_file":
        (truth / "unexpected.txt").write_text("Unexpected")
    elif defect == "missing_metadata":
        (truth / "truth_metadata.json").unlink()
    elif defect == "invalid_metadata":
        (truth / "truth_metadata.json").write_text("[]")
    else:
        target = tmp_path / "external.csv"
        (truth / "events.csv").rename(target)
        (truth / "events.csv").symlink_to(target)
    before = _bytes(truth)
    with pytest.raises(TruthContractError):
        _freeze(inputs, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
    assert not list(tmp_path.glob(".rejected.staging-*"))
    assert _bytes(truth) == before


@pytest.mark.parametrize("defect", ["hash", "membership", "duplicate", "source_snapshot", "source_text"])
def test_freeze_verifies_actual_selection_and_canonical_source(inputs, tmp_path, defect):
    truth, selection, source = inputs
    if defect == "source_text":
        frame = pd.read_parquet(source / "documents.parquet")
        frame.loc[0, "texto_limpio"] = "Changed source"
        frame.to_parquet(source / "documents.parquet", index=False)
    else:
        frame = pd.read_csv(selection)
        if defect == "membership":
            frame = frame.iloc[:1]
        elif defect == "duplicate":
            frame = pd.concat([frame, frame.iloc[:1]])
        elif defect == "source_snapshot":
            frame["source_snapshot_id"] = "f" * 64
        else:
            frame.loc[0, "source_document_sha256"] = "0" * 64
        frame.to_csv(selection, index=False)
        if defect != "hash":
            metadata_path = truth / "truth_metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["holdout_artifact_identity"] = sha256_file(selection)
            metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(TruthContractError):
        _freeze(inputs, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_empty_truth_cannot_be_frozen(inputs, tmp_path):
    for table in TABLE_SPECS:
        path = inputs[0] / f"{table}.csv"
        pd.read_csv(path).iloc[:0].to_csv(path, index=False)
    with pytest.raises(TruthContractError, match="contain documents"):
        _freeze(inputs, tmp_path / "empty")


@pytest.mark.parametrize("filename", ["documents.csv", "events.csv", "truth_metadata.json", FROZEN_SELECTION])
def test_frozen_file_byte_drift_is_rejected_even_without_semantic_change(inputs, tmp_path, filename):
    output = tmp_path / "frozen"
    _freeze(inputs, output)
    path = output / filename
    path.write_bytes(path.read_bytes() + b"\n")
    before = _bytes(output)
    with pytest.raises(TruthContractError, match="file drift"):
        load_truth(output, require_frozen=True)
    with pytest.raises(TruthContractError, match="file drift"):
        load_truth(output)
    assert _bytes(output) == before


@pytest.mark.parametrize("field,value", [
    ("status", "working"), ("manifest_version", "v1"),
    ("document_count", 48), ("truth_contract_version", "v1"),
    ("truth_artifact_id", "0" * 64), ("table_semantic_sha256", {}),
    ("holdout_artifact_identity", "0" * 64), ("source_snapshot_identity", "0" * 64),
    ("truth_file_hashes", {}), ("created_at", "2099-01-01T00:00:00+00:00"),
    ("freeze_tool_sha256", "0" * 64), ("reviewer_ids", ["someone_else"]),
])
def test_manifest_tampering_is_rejected(inputs, tmp_path, field, value):
    output = tmp_path / "frozen"
    _freeze(inputs, output)
    path = output / TRUTH_MANIFEST
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(TruthContractError):
        load_truth(output, require_frozen=True)


@pytest.mark.parametrize("content", ["{", "[]", "null", "{}"])
def test_invalid_manifest_json_is_rejected(inputs, tmp_path, content):
    output = tmp_path / "frozen"
    _freeze(inputs, output)
    (output / TRUTH_MANIFEST).write_text(content)
    with pytest.raises(TruthContractError):
        load_truth(output, require_frozen=True)


def test_external_manifest_hash_detects_resealed_publication_metadata(inputs, tmp_path):
    output = tmp_path / "frozen"
    _freeze(inputs, output)
    path = output / TRUTH_MANIFEST
    expected_hash = sha256_file(path)
    manifest = json.loads(path.read_text())
    manifest["created_at"] = "2099-01-01T00:00:00+00:00"
    manifest["manifest_identity_sha256"] = frozen_manifest_identity(manifest)
    path.write_text(json.dumps(manifest))
    with pytest.raises(TruthContractError, match="physical hash"):
        load_truth(output, require_frozen=True, expected_manifest_sha256=expected_hash)


@pytest.mark.parametrize("defect", ["extra", "missing", "symlink"])
def test_frozen_file_inventory_is_exact(inputs, tmp_path, defect):
    output = tmp_path / "frozen"
    _freeze(inputs, output)
    if defect == "extra":
        (output / "extra.txt").write_text("extra")
    elif defect == "missing":
        (output / FROZEN_SELECTION).unlink()
    else:
        (output / "events.csv").unlink()
        (output / "events.csv").symlink_to(inputs[0] / "events.csv")
    with pytest.raises(TruthContractError):
        load_truth(output, require_frozen=True)


@pytest.mark.parametrize("failure", ["copy", "manifest", "rename", "destination_appears", "source_changes"])
def test_intermediate_failure_leaves_no_publication_and_preserves_inputs(inputs, tmp_path, monkeypatch, failure):
    output = tmp_path / "frozen"
    truth = inputs[0]
    before = _bytes(truth)
    if failure == "copy":
        def fail_copy(*args, **kwargs):
            raise OSError("synthetic copy failure")
        monkeypatch.setattr(publication.shutil, "copyfile", fail_copy)
    elif failure == "manifest":
        def fail_manifest():
            raise OSError("synthetic manifest failure")
        monkeypatch.setattr(publication, "_tool_source_hash", fail_manifest)
    elif failure == "rename":
        def fail_rename(*args):
            raise OSError("synthetic publication failure")
        monkeypatch.setattr(Path, "rename", fail_rename)
    elif failure == "destination_appears":
        original = publication._require_new_destination
        calls = 0
        def destination_appears(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.mkdir()
                (path / "keep.txt").write_text("concurrent destination")
            original(path)
        monkeypatch.setattr(publication, "_require_new_destination", destination_appears)
    else:
        original = publication._tool_source_hash
        def change_source():
            _edit_csv(truth / "events.csv", "event_label", "Concurrent human change")
            return original()
        monkeypatch.setattr(publication, "_tool_source_hash", change_source)
    with pytest.raises((OSError, TruthContractError)):
        _freeze(inputs, output)
    assert not list(tmp_path.glob(".frozen.staging-*"))
    if failure == "destination_appears":
        assert _bytes(output) == {"keep.txt": b"concurrent destination"}
    else:
        assert not output.exists()
    if failure == "source_changes":
        assert b"Concurrent human change" in (truth / "events.csv").read_bytes()
    else:
        assert _bytes(truth) == before


def test_working_and_frozen_are_distinct_and_frozen_annotation_writes_fail(inputs, tmp_path):
    with pytest.raises(TruthContractError, match="frozen truth manifest"):
        load_truth(inputs[0], require_frozen=True)
    output = tmp_path / "frozen"
    truth = _freeze(inputs, output)
    before = _bytes(output)
    action = truth.tables["administrative_actions"].iloc[0].to_dict()
    action["expected_decision"] = "denegado"
    with pytest.raises(TruthContractError, match="cannot be edited"):
        upsert_truth_row(output, "administrative_actions", PROJECT_BOE, action)
    assert _bytes(output) == before
    with pytest.raises(TruthContractError, match="not working truth"):
        _freeze((output, inputs[1], inputs[2]), tmp_path / "refrozen")
    with pytest.raises(TruthContractError):
        v1.load_truth(output, require_frozen=True)


def test_identity_is_path_order_and_publication_independent_but_content_sensitive(inputs, tmp_path):
    original = load_truth(inputs[0]).truth_artifact_id
    reordered = tmp_path / "reordered"
    shutil.copytree(inputs[0], reordered)
    for table in TABLE_SPECS:
        path = reordered / f"{table}.csv"
        pd.read_csv(path, dtype=str, keep_default_na=False).iloc[::-1].to_csv(path, index=False)
    assert load_truth(reordered).truth_artifact_id == original
    first = _freeze(inputs, tmp_path / "frozen_a")
    second = _freeze((reordered, inputs[1], inputs[2]), tmp_path / "frozen_b")
    assert first.truth_artifact_id == second.truth_artifact_id == original
    assert first.manifest["truth_file_hashes"] != second.manifest["truth_file_hashes"]
    _edit_csv(reordered / "administrative_actions.csv", "expected_decision", "denegado")
    assert load_truth(reordered).truth_artifact_id != original


def test_cli_publication_and_readonly_verification(inputs, tmp_path, capsys):
    output = tmp_path / "frozen"
    assert main([
        "freeze-truth", "--truth", str(inputs[0]), "--output", str(output),
        "--holdout", str(inputs[1]), "--documents", str(inputs[2]),
    ]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["frozen_truth_intact"] is True
    assert published["evaluator_implemented"] is True
    before = _bytes(output)
    assert main([
        "validate-frozen-truth", "--truth", str(output),
        "--expected-manifest-sha256", published["manifest_sha256"],
    ]) == 0
    assert json.loads(capsys.readouterr().out) == published
    assert _bytes(output) == before
    with pytest.raises(TruthContractError):
        main(["validate-frozen-truth", "--truth", str(inputs[0])])


def test_cli_requires_explicit_inputs_and_has_no_overwrite_flag():
    with pytest.raises(SystemExit):
        main(["freeze-truth"])
