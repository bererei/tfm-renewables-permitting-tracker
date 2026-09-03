from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from evaluation.final_holdout_v1 import contract as v1


CONTRACT_VERSION = "final_holdout_evaluation_contract_v2"
MIGRATION_VERSION = "v1_truth_to_v2_v1"
FROZEN_PRODUCTION_COMMIT = v1.FROZEN_PRODUCTION_COMMIT
NA = v1.NA
TRUTH_MANIFEST = v1.TRUTH_MANIFEST
TRUTH_METADATA = v1.TRUTH_METADATA
TEMPLATES_DIR = Path(__file__).with_name("templates")
CONTRACT_DECLARATION_PATH = Path(__file__).with_name("contract.json")

APPLICABILITY = v1.APPLICABILITY
ADJUDICATION = v1.ADJUDICATION
ANNOTATION_STATUS = v1.ANNOTATION_STATUS
DOCUMENT_SCOPES = v1.DOCUMENT_SCOPES
TEMPORAL_STATUSES = v1.TEMPORAL_STATUSES
GENERATION_TYPES = v1.GENERATION_TYPES
COMPONENT_TYPES = v1.COMPONENT_TYPES
TECHNICAL_ATTRIBUTE_TYPES = v1.TECHNICAL_ATTRIBUTE_TYPES
ACTION_TYPES = v1.ACTION_TYPES
DECISIONS = v1.DECISIONS
PARTICIPANT_ROLES = v1.PARTICIPANT_ROLES
LOCATION_LEVELS = v1.LOCATION_LEVELS
TARGET_TYPES = v1.TARGET_TYPES
OWNER_TYPES = v1.OWNER_TYPES
TruthContractError = v1.TruthContractError
TableSpec = v1.TableSpec

_AFFECTED_ASSETS_COLUMN = "expected_affected_generation_asset_keys_json"
_DETERMINATE_TEMPORAL_STATUSES = {
    "current",
    "historical_antecedent",
    "ambiguous_not_safely_determinable",
}

TABLE_SPECS: dict[str, TableSpec] = dict(v1.TABLE_SPECS)
_v1_action_columns = v1.TABLE_SPECS["administrative_actions"].columns
_temporal_index = _v1_action_columns.index("temporal_status") + 1
TABLE_SPECS["administrative_actions"] = TableSpec(
    columns=(
        *_v1_action_columns[:_temporal_index],
        _AFFECTED_ASSETS_COLUMN,
        *_v1_action_columns[_temporal_index:],
    ),
    key_columns=v1.TABLE_SPECS["administrative_actions"].key_columns,
)

PRIMARY_ENTITY_TABLES = (
    "events",
    "generation_assets",
    "administrative_actions",
    "locations",
)
SECONDARY_TABLES = (
    "associated_components",
    "technical_mentions",
    "action_targets",
    "participants",
)


@dataclass(frozen=True)
class TruthArtifact:
    tables: Mapping[str, pd.DataFrame]
    table_semantic_sha256: Mapping[str, str]
    truth_artifact_id: str
    holdout_artifact_identity: str | None
    source_snapshot_identity: str | None
    metadata: Mapping[str, Any]
    manifest: Mapping[str, Any] | None


def sha256_file(path: Path) -> str:
    return v1.sha256_file(Path(path))


def canonical_json_bytes(value: Any) -> bytes:
    return v1.canonical_json_bytes(value)


def parse_json_list(value: str, *, label: str, allow_empty: bool = True) -> list[str]:
    return v1.parse_json_list(value, label=label, allow_empty=allow_empty)


def _scored(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[
        frame["applicability"].eq("applicable")
        & frame["adjudication"].eq("scored_truth")
    ]


def _adapt_for_v1_validation(frame: pd.DataFrame, table: str) -> pd.DataFrame:
    adapted = frame.copy()
    if table == "documents":
        adapted.loc[:, "truth_contract_version"] = v1.CONTRACT_VERSION
    elif table == "administrative_actions":
        adapted = adapted.drop(columns=[_AFFECTED_ASSETS_COLUMN])
    return adapted


def _validate_table(frame: pd.DataFrame, *, table: str, spec: TableSpec) -> None:
    if tuple(frame.columns) != spec.columns:
        raise TruthContractError(
            f"{table} columns do not match V2: expected={list(spec.columns)!r}; "
            f"found={list(frame.columns)!r}."
        )
    if table == "documents" and not frame.empty:
        if not frame["truth_contract_version"].eq(CONTRACT_VERSION).all():
            raise TruthContractError(f"{table} has an incompatible V2 contract version.")
    v1._validate_table(
        _adapt_for_v1_validation(frame, table),
        table=table,
        spec=v1.TABLE_SPECS[table],
    )
    if table == "administrative_actions":
        for index, value in frame[_AFFECTED_ASSETS_COLUMN].items():
            parse_json_list(
                str(value),
                label=f"{table}[{index + 2}].{_AFFECTED_ASSETS_COLUMN}",
                allow_empty=True,
            )


def _validate_v2_foreign_keys(tables: Mapping[str, pd.DataFrame]) -> None:
    v1._validate_foreign_keys(tables)
    assets = tables["generation_assets"]
    asset_event = {
        (str(row["identificador_boe"]), str(row["asset_key"])): str(row["event_key"])
        for _, row in assets.iterrows()
    }
    scored_assets = {
        (str(row["identificador_boe"]), str(row["asset_key"]))
        for _, row in _scored(assets).iterrows()
    }
    scored_events = {
        (str(row["identificador_boe"]), str(row["event_key"]))
        for _, row in _scored(tables["events"]).iterrows()
    }

    for table in ("generation_assets", "administrative_actions", "locations"):
        for _, row in _scored(tables[table]).iterrows():
            event = (str(row["identificador_boe"]), str(row["event_key"]))
            if event not in scored_events:
                raise TruthContractError(
                    f"A scored {table} row requires a scored event."
                )

    for _, action in tables["administrative_actions"].iterrows():
        boe_id = str(action["identificador_boe"])
        event_key = str(action["event_key"])
        affected = parse_json_list(
            str(action[_AFFECTED_ASSETS_COLUMN]),
            label=_AFFECTED_ASSETS_COLUMN,
            allow_empty=True,
        )
        for asset_key in affected:
            key = (boe_id, asset_key)
            if key not in asset_event:
                raise TruthContractError(
                    "An administrative action references an unknown affected asset."
                )
            if asset_event[key] != event_key:
                raise TruthContractError(
                    "An action and its affected assets must belong to the same event."
                )
            action_is_scored = (
                action["applicability"] == "applicable"
                and action["adjudication"] == "scored_truth"
            )
            if action_is_scored and key not in scored_assets:
                raise TruthContractError(
                    "A scored action requires scored affected generation assets."
                )

    scored_actions = {
        (str(row["identificador_boe"]), str(row["action_key"]))
        for _, row in _scored(tables["administrative_actions"]).iterrows()
    }
    evidence = _scored(tables["evidence_passages"])
    for _, row in evidence.loc[
        evidence["owner_type"].eq("administrative_action")
    ].iterrows():
        if (str(row["identificador_boe"]), str(row["owner_key"])) not in scored_actions:
            raise TruthContractError(
                "Scored administrative-action evidence requires a scored action."
            )


def _document_primary_rows(
    tables: Mapping[str, pd.DataFrame], boe_id: str
) -> dict[str, pd.DataFrame]:
    selected: dict[str, pd.DataFrame] = {}
    for table in PRIMARY_ENTITY_TABLES:
        scored = _scored(tables[table])
        selected[table] = scored.loc[
            scored["identificador_boe"].astype(str).eq(boe_id)
        ]
    action_evidence = _scored(tables["evidence_passages"])
    selected["action_evidence"] = action_evidence.loc[
        action_evidence["identificador_boe"].astype(str).eq(boe_id)
        & action_evidence["owner_type"].eq("administrative_action")
    ]
    return selected


def validate_document_completeness(
    tables: Mapping[str, pd.DataFrame], boe_id: str
) -> None:
    documents = tables["documents"]
    matches = documents.loc[documents["identificador_boe"].astype(str).eq(boe_id)]
    if len(matches) != 1:
        raise TruthContractError(f"Unknown truth document: {boe_id}")
    document = matches.iloc[0]
    if (
        document["scope_applicability"] != "applicable"
        or document["scope_adjudication"] != "scored_truth"
        or document["expected_document_scope"] == NA
    ):
        raise TruthContractError("A complete V2 document requires scored scope.")

    primary = _document_primary_rows(tables, boe_id)
    if document["expected_document_scope"] == "not_relevant_for_generation_projects":
        if any(not frame.empty for frame in primary.values()):
            raise TruthContractError(
                "A complete non-relevant document cannot contain primary scored entities."
            )
        return

    events = primary["events"]
    if events.empty:
        raise TruthContractError(
            "A project-specific V2 document needs at least one scored event."
        )
    assets = primary["generation_assets"]
    actions = primary["administrative_actions"]
    action_evidence = {
        str(row["owner_key"])
        for _, row in primary["action_evidence"].iterrows()
    }
    for _, event in events.iterrows():
        event_key = str(event["event_key"])
        if assets.loc[assets["event_key"].astype(str).eq(event_key)].empty:
            raise TruthContractError(
                "Every scored V2 event needs a scored generation asset."
            )
        if actions.loc[actions["event_key"].astype(str).eq(event_key)].empty:
            raise TruthContractError(
                "Every scored V2 event needs a scored administrative action."
            )

    for _, action in actions.iterrows():
        for column in (
            "expected_action_type",
            "expected_decision",
            "expected_is_modification",
        ):
            if str(action[column]) == NA:
                raise TruthContractError(
                    f"Every scored V2 action needs {column}."
                )
        if str(action["temporal_status"]) not in _DETERMINATE_TEMPORAL_STATUSES:
            raise TruthContractError(
                "Every scored V2 action needs current, historical or explicit ambiguity."
            )
        affected = parse_json_list(
            str(action[_AFFECTED_ASSETS_COLUMN]),
            label=_AFFECTED_ASSETS_COLUMN,
            allow_empty=True,
        )
        if not affected:
            raise TruthContractError(
                "Every scored V2 action needs explicit affected-generation-asset attribution."
            )
        if str(action["action_key"]) not in action_evidence:
            raise TruthContractError(
                "Every scored V2 action needs scored action-specific evidence."
            )


def _validate_complete_documents(tables: Mapping[str, pd.DataFrame]) -> None:
    complete = tables["documents"].loc[
        tables["documents"]["annotation_status"].eq("complete")
    ]
    for boe_id in complete["identificador_boe"].astype(str):
        validate_document_completeness(tables, boe_id)


def _canonical_rows(frame: pd.DataFrame, spec: TableSpec) -> list[dict[str, str]]:
    if frame.empty:
        return []
    ordered = frame.sort_values(list(spec.key_columns), kind="stable")
    return [
        {column: str(row[column]) for column in spec.columns}
        for _, row in ordered.iterrows()
    ]


def truth_semantic_identity(
    tables: Mapping[str, pd.DataFrame],
    *,
    holdout_artifact_identity: str | None,
    source_snapshot_identity: str | None,
) -> tuple[dict[str, str], str]:
    table_ids = {
        table: sha256(canonical_json_bytes(_canonical_rows(tables[table], spec))).hexdigest()
        for table, spec in TABLE_SPECS.items()
    }
    identity = sha256(canonical_json_bytes({
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_artifact_identity": holdout_artifact_identity,
        "source_snapshot_identity": source_snapshot_identity,
        "table_semantic_sha256": table_ids,
    })).hexdigest()
    return table_ids, identity


def _read_metadata(truth_dir: Path) -> Mapping[str, Any]:
    path = truth_dir / TRUTH_METADATA
    if not path.is_file():
        return {}
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TruthContractError("Invalid V2 truth metadata JSON.") from error
    if metadata.get("truth_contract_version") != CONTRACT_VERSION:
        raise TruthContractError("V2 truth metadata contract version mismatch.")
    if metadata.get("predictions_exposed_during_annotation") is not False:
        raise TruthContractError(
            "Blind V2 truth metadata must declare that predictions were not exposed."
        )
    for label in ("holdout_artifact_identity", "source_snapshot_identity"):
        value = metadata.get(label)
        if value is not None and not v1._SHA_RE.fullmatch(str(value)):
            raise TruthContractError(f"Invalid {label} in V2 truth metadata.")
    if metadata.get("initialization_mode") == "migrated_v1_blind_human_truth":
        migration = metadata.get("migration")
        if not isinstance(migration, dict):
            raise TruthContractError("Migrated V2 truth needs migration provenance.")
        if (
            migration.get("source_truth_contract_version") != v1.CONTRACT_VERSION
            or migration.get("migration_version") != MIGRATION_VERSION
            or not v1._SHA_RE.fullmatch(
                str(migration.get("source_truth_artifact_id", ""))
            )
            or migration.get("predictions_used") is not False
        ):
            raise TruthContractError("Invalid V1-to-V2 migration provenance.")
    return metadata


def load_truth(
    truth_dir: Path,
    *,
    require_complete: bool = False,
) -> TruthArtifact:
    truth_dir = Path(truth_dir)
    tables: dict[str, pd.DataFrame] = {}
    for table, spec in TABLE_SPECS.items():
        path = truth_dir / f"{table}.csv"
        if not path.is_file():
            raise TruthContractError(f"Missing V2 truth table: {path}.")
        frame = v1._read_csv(path)
        _validate_table(frame, table=table, spec=spec)
        tables[table] = frame
    _validate_v2_foreign_keys(tables)
    _validate_complete_documents(tables)
    if require_complete:
        drafts = tables["documents"].loc[
            ~tables["documents"]["annotation_status"].eq("complete")
        ]
        if not drafts.empty:
            raise TruthContractError("V2 truth cannot be complete with draft documents.")

    metadata = _read_metadata(truth_dir)
    holdout_identity = metadata.get("holdout_artifact_identity")
    source_identity = metadata.get("source_snapshot_identity")
    table_ids, artifact_id = truth_semantic_identity(
        tables,
        holdout_artifact_identity=(
            None if holdout_identity is None else str(holdout_identity)
        ),
        source_snapshot_identity=(
            None if source_identity is None else str(source_identity)
        ),
    )
    if (truth_dir / TRUTH_MANIFEST).exists():
        raise TruthContractError(
            "V2-A does not implement frozen truth manifests; freeze belongs to V2-B."
        )
    return TruthArtifact(
        tables=tables,
        table_semantic_sha256=table_ids,
        truth_artifact_id=artifact_id,
        holdout_artifact_identity=(
            None if holdout_identity is None else str(holdout_identity)
        ),
        source_snapshot_identity=(
            None if source_identity is None else str(source_identity)
        ),
        metadata=metadata,
        manifest=None,
    )


def _write_csv(frame: pd.DataFrame, path: Path, spec: TableSpec) -> None:
    ordered = (
        frame.sort_values(list(spec.key_columns), kind="stable")
        if not frame.empty
        else frame
    )
    ordered.to_csv(
        path,
        index=False,
        columns=list(spec.columns),
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )


def _is_scored_row(row: pd.Series) -> bool:
    return row["applicability"] == "applicable" and row["adjudication"] == "scored_truth"


def _derive_affected_assets(
    v1_truth: v1.TruthArtifact,
    action: pd.Series,
) -> tuple[list[str], bool]:
    if not _is_scored_row(action):
        return [], True
    boe_id = str(action["identificador_boe"])
    event_key = str(action["event_key"])
    action_key = str(action["action_key"])
    targets = v1_truth.tables["action_targets"]
    targets = targets.loc[
        targets["identificador_boe"].astype(str).eq(boe_id)
        & targets["action_key"].astype(str).eq(action_key)
    ]
    if targets.empty or any(not _is_scored_row(row) for _, row in targets.iterrows()):
        return [], False

    assets = v1_truth.tables["generation_assets"]
    event_assets = assets.loc[
        assets["identificador_boe"].astype(str).eq(boe_id)
        & assets["event_key"].astype(str).eq(event_key)
    ]
    components = v1_truth.tables["associated_components"]
    affected: set[str] = set()
    for _, target in targets.iterrows():
        target_type = str(target["target_type"])
        target_key = str(target["target_truth_key"])
        if target_type == "generation_asset":
            selected = event_assets.loc[
                event_assets["asset_key"].astype(str).eq(target_key)
            ]
            if len(selected) != 1 or not _is_scored_row(selected.iloc[0]):
                return [], False
            affected.add(target_key)
        elif target_type == "event":
            if target_key != event_key or event_assets.empty:
                return [], False
            if any(not _is_scored_row(row) for _, row in event_assets.iterrows()):
                return [], False
            affected.update(event_assets["asset_key"].astype(str))
        elif target_type == "associated_component":
            selected = components.loc[
                components["identificador_boe"].astype(str).eq(boe_id)
                & components["component_key"].astype(str).eq(target_key)
            ]
            if len(selected) != 1 or not _is_scored_row(selected.iloc[0]):
                return [], False
            related = parse_json_list(
                str(selected.iloc[0]["related_asset_keys_json"]),
                label="related_asset_keys_json",
                allow_empty=True,
            )
            if not related:
                return [], False
            related_rows = event_assets.loc[
                event_assets["asset_key"].astype(str).isin(related)
            ]
            if len(related_rows) != len(related) or any(
                not _is_scored_row(row) for _, row in related_rows.iterrows()
            ):
                return [], False
            affected.update(related)
        else:
            return [], False
    return sorted(affected), bool(affected)


def migrate_v1_truth(source_dir: Path, output_dir: Path) -> Path:
    """Copy validated human V1 truth into a new V2 workspace without mutation."""

    source_dir = Path(source_dir).resolve()
    requested_output = Path(output_dir).absolute()
    if requested_output.exists() or requested_output.is_symlink():
        raise FileExistsError(f"Output already exists: {requested_output}")
    output_dir = requested_output.resolve()
    if output_dir.is_relative_to(source_dir):
        raise TruthContractError(
            "V2 migration output cannot be inside the immutable V1 workspace."
        )
    source_truth = v1.load_truth(source_dir)
    source_metadata_path = source_dir / TRUTH_METADATA
    source_metadata = (
        json.loads(source_metadata_path.read_text(encoding="utf-8"))
        if source_metadata_path.is_file()
        else {}
    )

    tables = {table: frame.copy() for table, frame in source_truth.tables.items()}
    documents = tables["documents"]
    documents.loc[:, "truth_contract_version"] = CONTRACT_VERSION
    original_status = documents["annotation_status"].copy()
    documents.loc[:, "annotation_status"] = "draft"

    actions = tables["administrative_actions"].copy()
    derived_values: list[str] = []
    unresolved: list[str] = []
    for _, action in actions.iterrows():
        affected, safely_derived = _derive_affected_assets(source_truth, action)
        derived_values.append(
            json.dumps(affected, ensure_ascii=False, separators=(",", ":"))
        )
        if _is_scored_row(action) and not safely_derived:
            unresolved.append(
                f"{action['identificador_boe']}|{action['action_key']}"
            )
    actions.insert(_temporal_index, _AFFECTED_ASSETS_COLUMN, derived_values)
    tables["administrative_actions"] = actions

    for index, document in documents.iterrows():
        if (
            original_status.loc[index] != "complete"
            or document["expected_document_scope"]
            != "not_relevant_for_generation_projects"
            or document["scope_applicability"] != "applicable"
            or document["scope_adjudication"] != "scored_truth"
        ):
            continue
        boe_id = str(document["identificador_boe"])
        if all(frame.empty for frame in _document_primary_rows(tables, boe_id).values()):
            documents.loc[index, "annotation_status"] = "complete"

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{output_dir.name}.migration-staging-",
        dir=output_dir.parent,
    ))
    published = False
    try:
        for table, spec in TABLE_SPECS.items():
            _write_csv(tables[table], staging / f"{table}.csv", spec)
        metadata = {
            "truth_contract_version": CONTRACT_VERSION,
            "holdout_artifact_identity": source_truth.holdout_artifact_identity,
            "source_snapshot_identity": source_truth.source_snapshot_identity,
            "initialization_mode": "migrated_v1_blind_human_truth",
            "predictions_exposed_during_annotation": False,
            "migration": {
                "migration_version": MIGRATION_VERSION,
                "source_truth_contract_version": v1.CONTRACT_VERSION,
                "source_truth_artifact_id": source_truth.truth_artifact_id,
                "predictions_used": False,
                "unresolved_affected_asset_actions": sorted(unresolved),
            },
        }
        if "seal_break_acknowledged" in source_metadata:
            metadata["seal_break_acknowledged"] = bool(
                source_metadata["seal_break_acknowledged"]
            )
        (staging / TRUTH_METADATA).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        load_truth(staging)
        os.replace(staging, output_dir)
        published = True
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
    return output_dir


def copy_empty_templates(output_dir: Path) -> None:
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    shutil.copytree(TEMPLATES_DIR, output_dir)
