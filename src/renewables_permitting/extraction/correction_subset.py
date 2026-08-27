from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from renewables_permitting.extraction.corrections import (
    ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS,
    LoadedAdministrativeActionCorrections,
    apply_administrative_action_corrections,
    corrections_identity,
    empty_administrative_action_corrections,
    validate_administrative_action_corrections,
)


CORRECTIONS_SUBSET_OPERATION_VERSION = "1"
CORRECTIONS_SUBSET_FILENAME = "administrative_action_corrections.csv"
CORRECTIONS_SUBSET_MANIFEST_FILENAME = "manifest.json"
_CORRECTIONS_CONTRACT = "administrative_action_corrections_v1"
_CORRECTIONS_SUBSET_ARTIFACT_TYPE = "corrections_subset"
_SHA256_CHARACTERS = frozenset("0123456789abcdef")


class AdministrativeActionCorrectionsSubsetError(ValueError):
    """A corrections subset cannot be derived or verified safely."""


@dataclass(frozen=True)
class AdministrativeActionCorrectionsSubsetPlan:
    """Validated deterministic projection of one master correction registry."""

    parent_corrections: LoadedAdministrativeActionCorrections
    selected_corrections: pd.DataFrame
    selected_correction_ids: tuple[str, ...]
    out_of_scope_correction_ids: tuple[str, ...]
    corpus_boe_count: int
    source_extraction_snapshot_id: str
    extraction_config_id: str
    deterministic_code_sha256: str
    selected_corrections_identity: str
    materialization_identity: str


@dataclass(frozen=True)
class LoadedAdministrativeActionCorrectionsSubset:
    """Round-trip validated derived registry and its lineage manifest."""

    output_dir: Path
    corrections_path: Path
    manifest_path: Path
    corrections: pd.DataFrame
    manifest: Mapping[str, Any]
    materialization_identity: str


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corrections_subset_code_sha256() -> str:
    """Fingerprint the selection logic and the fail-closed applicator."""

    module_dir = Path(__file__).parent
    return sha256(_canonical_json_bytes({
        filename: _file_sha256(module_dir / filename)
        for filename in ("correction_subset.py", "corrections.py")
    })).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= _SHA256_CHARACTERS
    )


def _validate_sha256(value: object, *, field: str) -> str:
    if not _is_sha256(value):
        raise AdministrativeActionCorrectionsSubsetError(
            f"{field} debe ser SHA-256 hexadecimal minúsculo."
        )
    return str(value)


def _typed_empty_corrections(frame: pd.DataFrame) -> pd.DataFrame:
    if not frame.columns.is_unique:
        raise AdministrativeActionCorrectionsSubsetError(
            "El subset contiene columnas duplicadas."
        )
    if tuple(frame.columns) != ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS:
        raise AdministrativeActionCorrectionsSubsetError(
            "Las columnas del subset no coinciden con el contrato de "
            "correcciones."
        )
    return empty_administrative_action_corrections()


def _validate_subset_corrections(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("corrections debe ser un pandas.DataFrame.")
    if frame.empty:
        return _typed_empty_corrections(frame)
    return validate_administrative_action_corrections(frame)


def _corrections_rows_identity(frame: pd.DataFrame) -> str:
    validated = _validate_subset_corrections(frame)
    records = [
        {
            column: (
                int(row[column])
                if column == "correction_version"
                else str(row[column])
            )
            for column in ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS
        }
        for row in validated.to_dict(orient="records")
    ]
    records.sort(key=lambda record: record["correction_id"])
    return sha256(_canonical_json_bytes({
        "contract": _CORRECTIONS_CONTRACT,
        "records": records,
    })).hexdigest()


def _out_of_scope_ids_sha256(correction_ids: Iterable[str]) -> str:
    return sha256(_canonical_json_bytes(sorted(correction_ids))).hexdigest()


def _materialization_identity(
    *,
    parent_corrections_identity: str,
    source_extraction_snapshot_id: str,
    extraction_config_id: str,
    selected_corrections_identity: str,
    deterministic_code_sha256: str,
) -> str:
    return sha256(_canonical_json_bytes({
        "operation": (
            "corrections_subset_v"
            f"{CORRECTIONS_SUBSET_OPERATION_VERSION}"
        ),
        "parent_corrections_identity": parent_corrections_identity,
        "source_extraction_snapshot_id": source_extraction_snapshot_id,
        "extraction_config_id": extraction_config_id,
        "selected_corrections_identity": selected_corrections_identity,
        "deterministic_code_sha256": deterministic_code_sha256,
    })).hexdigest()


def plan_administrative_action_corrections_subset(
    *,
    corrections: LoadedAdministrativeActionCorrections,
    current_extractions: pd.DataFrame,
    corpus_boe_ids: Iterable[str],
    source_extraction_snapshot_id: str,
    extraction_config_id: str,
    deterministic_code_sha256: str,
) -> AdministrativeActionCorrectionsSubsetPlan:
    """Select by document universe and validate every in-scope target exactly."""

    if not isinstance(corrections, LoadedAdministrativeActionCorrections):
        raise TypeError(
            "corrections debe proceder de "
            "load_administrative_action_corrections."
        )
    if not isinstance(current_extractions, pd.DataFrame):
        raise TypeError("current_extractions debe ser un pandas.DataFrame.")
    if "identificador_boe" not in current_extractions.columns:
        raise AdministrativeActionCorrectionsSubsetError(
            "current_extractions no contiene identificador_boe."
        )
    source_extraction_snapshot_id = _validate_sha256(
        source_extraction_snapshot_id,
        field="source_extraction_snapshot_id",
    )
    deterministic_code_sha256 = _validate_sha256(
        deterministic_code_sha256,
        field="deterministic_code_sha256",
    )
    if not isinstance(extraction_config_id, str) or not extraction_config_id:
        raise AdministrativeActionCorrectionsSubsetError(
            "extraction_config_id debe ser texto no vacío."
        )

    parent = validate_administrative_action_corrections(
        corrections.corrections
    )
    if corrections.semantic_identity != corrections_identity(parent):
        raise AdministrativeActionCorrectionsSubsetError(
            "La identidad semántica del master no coincide con su contenido."
        )
    if _file_sha256(corrections.source_path) != corrections.file_sha256:
        raise AdministrativeActionCorrectionsSubsetError(
            "El master cambió después de ser cargado."
        )

    universe_values = [str(value) for value in corpus_boe_ids]
    if any(not value.strip() for value in universe_values):
        raise AdministrativeActionCorrectionsSubsetError(
            "El universo documental contiene BOE vacíos."
        )
    if len(universe_values) != len(set(universe_values)):
        raise AdministrativeActionCorrectionsSubsetError(
            "El universo documental contiene BOE duplicados."
        )
    universe = set(universe_values)
    current_boe_ids = set(
        current_extractions["identificador_boe"].astype(str)
    )
    outside_current = sorted(current_boe_ids - universe)
    if outside_current:
        raise AdministrativeActionCorrectionsSubsetError(
            "current_extractions contiene BOE fuera del universo documental: "
            f"{outside_current[:20]}."
        )

    in_scope = parent["boe_id"].astype(str).isin(universe)
    selected = parent.loc[in_scope].copy(deep=True)
    selected = selected.sort_values("correction_id", kind="stable").reset_index(
        drop=True
    )
    out_of_scope = parent.loc[~in_scope, "correction_id"].astype(str)
    selected_ids = tuple(selected["correction_id"].astype(str))
    out_of_scope_ids = tuple(sorted(out_of_scope))

    if not selected.empty:
        selected_identity = corrections_identity(selected)
        selected_registry = LoadedAdministrativeActionCorrections(
            corrections=selected,
            source_path=corrections.source_path,
            logical_path=corrections.logical_path,
            file_sha256=corrections.file_sha256,
            semantic_identity=selected_identity,
        )
        apply_administrative_action_corrections(
            current_extractions,
            selected_registry,
            source_extraction_snapshot_id=source_extraction_snapshot_id,
        )
    selected_identity = _corrections_rows_identity(selected)
    identity = _materialization_identity(
        parent_corrections_identity=corrections.semantic_identity,
        source_extraction_snapshot_id=source_extraction_snapshot_id,
        extraction_config_id=extraction_config_id,
        selected_corrections_identity=selected_identity,
        deterministic_code_sha256=deterministic_code_sha256,
    )
    return AdministrativeActionCorrectionsSubsetPlan(
        parent_corrections=corrections,
        selected_corrections=selected,
        selected_correction_ids=selected_ids,
        out_of_scope_correction_ids=out_of_scope_ids,
        corpus_boe_count=len(universe),
        source_extraction_snapshot_id=source_extraction_snapshot_id,
        extraction_config_id=extraction_config_id,
        deterministic_code_sha256=deterministic_code_sha256,
        selected_corrections_identity=selected_identity,
        materialization_identity=identity,
    )


def _created_at(value: datetime | None) -> str:
    instant = datetime.now(timezone.utc) if value is None else value
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise AdministrativeActionCorrectionsSubsetError(
            "created_at debe incluir zona horaria."
        )
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _manifest_payload(
    plan: AdministrativeActionCorrectionsSubsetPlan,
    *,
    corrections_file_sha256: str,
    created_at: datetime | None,
) -> dict[str, Any]:
    return {
        "artifact_type": _CORRECTIONS_SUBSET_ARTIFACT_TYPE,
        "operation_version": CORRECTIONS_SUBSET_OPERATION_VERSION,
        "contract": _CORRECTIONS_CONTRACT,
        "materialization_identity_sha256": plan.materialization_identity,
        "created_at": _created_at(created_at),
        "deterministic_code_sha256": plan.deterministic_code_sha256,
        "parent_corrections": {
            "logical_path": plan.parent_corrections.logical_path,
            "row_count": len(plan.parent_corrections.corrections),
            "semantic_identity_sha256": (
                plan.parent_corrections.semantic_identity
            ),
            "physical_sha256": plan.parent_corrections.file_sha256,
        },
        "extraction_snapshot": {
            "snapshot_identity_sha256": (
                plan.source_extraction_snapshot_id
            ),
            "extraction_config_id": plan.extraction_config_id,
            "document_count": plan.corpus_boe_count,
        },
        "subset": {
            "selected_correction_count": len(
                plan.selected_correction_ids
            ),
            "out_of_scope_correction_count": len(
                plan.out_of_scope_correction_ids
            ),
            "selected_correction_ids": list(plan.selected_correction_ids),
            "out_of_scope_correction_ids": list(
                plan.out_of_scope_correction_ids
            ),
            "out_of_scope_correction_ids_sha256": (
                _out_of_scope_ids_sha256(
                    plan.out_of_scope_correction_ids
                )
            ),
            "selected_corrections_semantic_identity_sha256": (
                plan.selected_corrections_identity
            ),
        },
        "artifacts": {
            "administrative_action_corrections": {
                "filename": CORRECTIONS_SUBSET_FILENAME,
                "row_count": len(plan.selected_corrections),
                "columns": list(
                    ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS
                ),
                "sha256": corrections_file_sha256,
            },
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    value = dict(payload)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if json.loads(path.read_text(encoding="utf-8")) != value:
        raise AdministrativeActionCorrectionsSubsetError(
            "El manifest no supera el round-trip JSON."
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdministrativeActionCorrectionsSubsetError(
            "No se pudo leer el manifest del subset."
        ) from error
    if not isinstance(value, dict):
        raise AdministrativeActionCorrectionsSubsetError(
            "El manifest del subset debe ser un objeto JSON."
        )
    return value


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise AdministrativeActionCorrectionsSubsetError(
            f"{field} debe ser un objeto JSON."
        )
    return value


def _string_list(value: object, *, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        raise AdministrativeActionCorrectionsSubsetError(
            f"{field} debe ser una lista ordenada de IDs únicos."
        )
    return value


def load_administrative_action_corrections_subset(
    output_dir: Path,
    *,
    expected_extraction_snapshot_id: str | None = None,
    expected_extraction_config_id: str | None = None,
) -> LoadedAdministrativeActionCorrectionsSubset:
    """Load and internally validate one derived corrections subset."""

    output_dir = Path(output_dir).absolute()
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise FileNotFoundError(
            f"No existe un directorio regular de corrections-subset: {output_dir}"
        )
    corrections_path = output_dir / CORRECTIONS_SUBSET_FILENAME
    manifest_path = output_dir / CORRECTIONS_SUBSET_MANIFEST_FILENAME
    expected_files = {corrections_path, manifest_path}
    observed_files = set(output_dir.iterdir())
    if observed_files != expected_files:
        raise AdministrativeActionCorrectionsSubsetError(
            "El artefacto corrections-subset contiene ficheros inesperados."
        )
    if any(not path.is_file() or path.is_symlink() for path in expected_files):
        raise AdministrativeActionCorrectionsSubsetError(
            "Los ficheros del corrections-subset deben ser regulares."
        )

    manifest = _read_json(manifest_path)
    if manifest.get("artifact_type") != _CORRECTIONS_SUBSET_ARTIFACT_TYPE:
        raise AdministrativeActionCorrectionsSubsetError(
            "artifact_type no identifica un corrections_subset."
        )
    if manifest.get("operation_version") != CORRECTIONS_SUBSET_OPERATION_VERSION:
        raise AdministrativeActionCorrectionsSubsetError(
            "operation_version no coincide con el contrato vigente."
        )
    if manifest.get("contract") != _CORRECTIONS_CONTRACT:
        raise AdministrativeActionCorrectionsSubsetError(
            "El contrato declarado por el subset no es válido."
        )
    try:
        timestamp = datetime.fromisoformat(
            str(manifest["created_at"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError) as error:
        raise AdministrativeActionCorrectionsSubsetError(
            "created_at no es un timestamp ISO válido."
        ) from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise AdministrativeActionCorrectionsSubsetError(
            "created_at debe incluir zona horaria."
        )

    parent = _mapping(
        manifest.get("parent_corrections"),
        field="parent_corrections",
    )
    extraction = _mapping(
        manifest.get("extraction_snapshot"),
        field="extraction_snapshot",
    )
    subset = _mapping(manifest.get("subset"), field="subset")
    artifacts = _mapping(manifest.get("artifacts"), field="artifacts")
    artifact = _mapping(
        artifacts.get("administrative_action_corrections"),
        field="artifacts.administrative_action_corrections",
    )
    parent_identity = _validate_sha256(
        parent.get("semantic_identity_sha256"),
        field="parent_corrections.semantic_identity_sha256",
    )
    _validate_sha256(
        parent.get("physical_sha256"),
        field="parent_corrections.physical_sha256",
    )
    snapshot_id = _validate_sha256(
        extraction.get("snapshot_identity_sha256"),
        field="extraction_snapshot.snapshot_identity_sha256",
    )
    code_sha256 = _validate_sha256(
        manifest.get("deterministic_code_sha256"),
        field="deterministic_code_sha256",
    )
    extraction_config_id = extraction.get("extraction_config_id")
    if not isinstance(extraction_config_id, str) or not extraction_config_id:
        raise AdministrativeActionCorrectionsSubsetError(
            "extraction_snapshot.extraction_config_id no es válido."
        )
    if (
        expected_extraction_snapshot_id is not None
        and snapshot_id != expected_extraction_snapshot_id
    ):
        raise AdministrativeActionCorrectionsSubsetError(
            "El snapshot de extracción no coincide con el esperado."
        )
    if (
        expected_extraction_config_id is not None
        and extraction_config_id != expected_extraction_config_id
    ):
        raise AdministrativeActionCorrectionsSubsetError(
            "La configuración de extracción no coincide con la esperada."
        )

    try:
        raw = pd.read_csv(
            corrections_path,
            dtype="string",
            keep_default_na=False,
        )
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as error:
        raise AdministrativeActionCorrectionsSubsetError(
            "No se pudo leer el CSV derivado."
        ) from error
    corrections = _validate_subset_corrections(raw)
    selected_ids = sorted(corrections["correction_id"].astype(str))
    manifest_selected_ids = _string_list(
        subset.get("selected_correction_ids"),
        field="subset.selected_correction_ids",
    )
    out_of_scope_ids = _string_list(
        subset.get("out_of_scope_correction_ids"),
        field="subset.out_of_scope_correction_ids",
    )
    if selected_ids != manifest_selected_ids:
        raise AdministrativeActionCorrectionsSubsetError(
            "Los correction IDs del CSV no coinciden con el manifest."
        )
    if set(selected_ids) & set(out_of_scope_ids):
        raise AdministrativeActionCorrectionsSubsetError(
            "Un correction ID figura seleccionado y fuera de scope."
        )
    if subset.get("selected_correction_count") != len(selected_ids):
        raise AdministrativeActionCorrectionsSubsetError(
            "selected_correction_count no coincide con el CSV."
        )
    if subset.get("out_of_scope_correction_count") != len(out_of_scope_ids):
        raise AdministrativeActionCorrectionsSubsetError(
            "out_of_scope_correction_count no coincide con los IDs."
        )
    if parent.get("row_count") != len(selected_ids) + len(out_of_scope_ids):
        raise AdministrativeActionCorrectionsSubsetError(
            "El conteo del master no se conserva en el subset."
        )
    if subset.get("out_of_scope_correction_ids_sha256") != (
        _out_of_scope_ids_sha256(out_of_scope_ids)
    ):
        raise AdministrativeActionCorrectionsSubsetError(
            "La huella de correction IDs fuera de scope no coincide."
        )

    selected_identity = _corrections_rows_identity(corrections)
    if subset.get("selected_corrections_semantic_identity_sha256") != (
        selected_identity
    ):
        raise AdministrativeActionCorrectionsSubsetError(
            "La identidad semántica de las filas seleccionadas no coincide."
        )
    if artifact.get("filename") != CORRECTIONS_SUBSET_FILENAME:
        raise AdministrativeActionCorrectionsSubsetError(
            "El filename contractual del CSV no coincide."
        )
    if artifact.get("row_count") != len(corrections):
        raise AdministrativeActionCorrectionsSubsetError(
            "El row_count del CSV no coincide."
        )
    if artifact.get("columns") != list(ADMINISTRATIVE_ACTION_CORRECTION_COLUMNS):
        raise AdministrativeActionCorrectionsSubsetError(
            "El orden de columnas declarado no coincide."
        )
    if artifact.get("sha256") != _file_sha256(corrections_path):
        raise AdministrativeActionCorrectionsSubsetError(
            "La huella física del CSV derivado no coincide."
        )

    identity = _materialization_identity(
        parent_corrections_identity=parent_identity,
        source_extraction_snapshot_id=snapshot_id,
        extraction_config_id=extraction_config_id,
        selected_corrections_identity=selected_identity,
        deterministic_code_sha256=code_sha256,
    )
    if manifest.get("materialization_identity_sha256") != identity:
        raise AdministrativeActionCorrectionsSubsetError(
            "La identidad de materialización del subset no coincide."
        )
    return LoadedAdministrativeActionCorrectionsSubset(
        output_dir=output_dir,
        corrections_path=corrections_path,
        manifest_path=manifest_path,
        corrections=corrections,
        manifest=manifest,
        materialization_identity=identity,
    )


def materialize_administrative_action_corrections_subset(
    plan: AdministrativeActionCorrectionsSubsetPlan,
    *,
    output_dir: Path,
    created_at: datetime | None = None,
) -> LoadedAdministrativeActionCorrectionsSubset:
    """Atomically publish and round-trip one validated corrections subset."""

    if not isinstance(plan, AdministrativeActionCorrectionsSubsetPlan):
        raise TypeError(
            "plan debe proceder de "
            "plan_administrative_action_corrections_subset."
        )
    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    if _file_sha256(plan.parent_corrections.source_path) != (
        plan.parent_corrections.file_sha256
    ):
        raise AdministrativeActionCorrectionsSubsetError(
            "El master cambió después de planificar el subset."
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{output_dir.name}.staging-"
    staging_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=output_dir.parent))
    published = False
    try:
        corrections_path = staging_dir / CORRECTIONS_SUBSET_FILENAME
        plan.selected_corrections.to_csv(
            corrections_path,
            index=False,
            lineterminator="\n",
        )
        manifest = _manifest_payload(
            plan,
            corrections_file_sha256=_file_sha256(corrections_path),
            created_at=created_at,
        )
        _write_json(
            staging_dir / CORRECTIONS_SUBSET_MANIFEST_FILENAME,
            manifest,
        )
        load_administrative_action_corrections_subset(
            staging_dir,
            expected_extraction_snapshot_id=(
                plan.source_extraction_snapshot_id
            ),
            expected_extraction_config_id=plan.extraction_config_id,
        )
        if _file_sha256(plan.parent_corrections.source_path) != (
            plan.parent_corrections.file_sha256
        ):
            raise AdministrativeActionCorrectionsSubsetError(
                "El master cambió durante la materialización del subset."
            )
        if output_dir.exists() or output_dir.is_symlink():
            raise FileExistsError(f"Output already exists: {output_dir}")
        staging_dir.rename(output_dir)
        published = True
    finally:
        if not published and staging_dir.exists():
            if (
                staging_dir.parent != output_dir.parent
                or not staging_dir.name.startswith(prefix)
                or staging_dir.is_symlink()
            ):
                raise RuntimeError(
                    "Refusing to clean an unexpected staging path."
                )
            shutil.rmtree(staging_dir)

    return load_administrative_action_corrections_subset(
        output_dir,
        expected_extraction_snapshot_id=plan.source_extraction_snapshot_id,
        expected_extraction_config_id=plan.extraction_config_id,
    )
