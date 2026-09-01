from __future__ import annotations

import csv
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


CONTRACT_VERSION = "final_holdout_evaluation_contract_v1"
FROZEN_PRODUCTION_COMMIT = (
    "282de815bea4e248bdcba2c655e3ee078cb58a49"
)
FROZEN_EXTRACTION_CONFIG_ID = "4b54b89dbfe8640e"
FROZEN_MODEL_PROVIDER = "gemini"
FROZEN_MODEL_NAME = "google:gemini-2.5-flash"
FROZEN_SOURCE_SNAPSHOT_ID = (
    "1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf"
)
FROZEN_INSTRUCTIONS_SHA256 = (
    "153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580"
)
FROZEN_CONTRACT_SHA256 = (
    "7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c"
)
FROZEN_UV_LOCK_SHA256 = (
    "af47371305913f4913c05a73448a8be92f44fbceb3f604b491d629cc80639229"
)

NA = "__NA__"
TRUTH_MANIFEST = "manifest.json"
TRUTH_METADATA = "truth_metadata.json"
TEMPLATES_DIR = Path(__file__).with_name("templates")
CONTRACT_DECLARATION_PATH = Path(__file__).with_name("contract.json")

APPLICABILITY = {"applicable", "not_applicable", "unknown"}
ADJUDICATION = {
    "scored_truth",
    "ambiguous_not_safely_determinable",
    "excluded_from_scoring",
}
ANNOTATION_STATUS = {"draft", "complete"}
DOCUMENT_SCOPES = {
    "not_relevant_for_generation_projects",
    "generation_project_specific",
}
TEMPORAL_STATUSES = {
    "current",
    "historical_antecedent",
    "ambiguous_not_safely_determinable",
    "not_applicable",
}
GENERATION_TYPES = {
    "fotovoltaica",
    "eolica",
    "termosolar",
    "hidroelectrica",
    "geotermica",
    "biomasa",
    "biogas",
    "otra_generacion",
}
COMPONENT_TYPES = {
    "almacenamiento",
    "sistema_evacuacion",
    "subestacion_electrica",
    "linea_electrica",
    "conexion_red",
    "otro_componente_asociado",
}
TECHNICAL_ATTRIBUTE_TYPES = {
    "potencia_instalada",
    "potencia_pico",
    "potencia_almacenamiento",
    "capacidad_almacenamiento",
    "tension",
    "numero_unidades",
    "potencia_unitaria",
    "otra",
}
POWER_ATTRIBUTE_TYPES = {
    "potencia_instalada",
    "potencia_pico",
    "potencia_almacenamiento",
    "potencia_unitaria",
}
ACTION_TYPES = {
    "solicitud_tramitacion",
    "solicitud_tramitacion_ambiental",
    "subsanacion_documentacion",
    "verificacion_requisitos_tramitacion",
    "correccion_errores",
    "informacion_publica",
    "evaluacion_impacto_ambiental",
    "declaracion_impacto_ambiental",
    "informe_impacto_ambiental",
    "informe_determinacion_afeccion_ambiental",
    "autorizacion_administrativa_previa",
    "autorizacion_administrativa_construccion",
    "autorizacion_explotacion",
    "concesion_aguas",
    "declaracion_utilidad_publica",
    "expropiacion_forzosa",
    "relacion_bienes_derechos_afectados",
    "levantamiento_actas_previas_ocupacion",
    "actas_ocupacion",
    "modificacion_autorizacion",
    "prorroga",
    "cambio_titularidad",
    "terminacion_procedimiento",
    "otro",
    "desconocido",
}
DECISIONS = {
    "solicitado",
    "subsanado",
    "requisitos_verificados",
    "rectificado",
    "sometido_informacion_publica",
    "convocado",
    "formulado",
    "favorable",
    "desfavorable",
    "sin_efectos_adversos_significativos",
    "requiere_evaluacion_ambiental_ordinaria",
    "requiere_evaluacion_ambiental_adicional",
    "no_requiere_evaluacion_ambiental_adicional",
    "autorizado",
    "declarado",
    "modificado",
    "prorrogado",
    "denegado",
    "desestimado",
    "archivado",
    "desistido",
    "inadmitido",
    "otro",
    "desconocido",
}
PARTICIPANT_ROLES = {
    "promotor",
    "copromotor",
    "titular",
    "operador",
    "solicitante",
    "cedente",
    "cesionario",
    "otro",
    "desconocido",
}
LOCATION_LEVELS = {"municipio", "provincia", "comunidad_autonoma"}
TARGET_TYPES = {"event", "generation_asset", "associated_component"}
OWNER_TYPES = {
    "generation_asset",
    "associated_component",
    "technical_mention",
    "administrative_action",
    "participant",
    "location",
}

_BOE_RE = re.compile(r"BOE-[AB]-\d{4}-\d+")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,79}")

COMMON_COLUMNS = (
    "truth_contract_version",
    "holdout_version",
    "identificador_boe",
    "source_document_sha256",
)
PROVENANCE_COLUMNS = ("reviewer_id", "reviewed_on", "annotation_notes")
ENTITY_COLUMNS = ("identificador_boe",)
ENTITY_PROVENANCE_COLUMNS = ("annotation_notes",)


@dataclass(frozen=True)
class TableSpec:
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]


def _columns(*specific: str) -> tuple[str, ...]:
    return (*COMMON_COLUMNS, *specific, *PROVENANCE_COLUMNS)


def _entity_columns(*specific: str) -> tuple[str, ...]:
    return (*ENTITY_COLUMNS, *specific, *ENTITY_PROVENANCE_COLUMNS)


TABLE_SPECS: dict[str, TableSpec] = {
    "documents": TableSpec(
        columns=_columns(
            "annotation_status",
            "scope_applicability",
            "scope_adjudication",
            "expected_document_scope",
        ),
        key_columns=("identificador_boe",),
    ),
    "events": TableSpec(
        columns=_entity_columns(
            "event_key",
            "event_label",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "event_key"),
    ),
    "generation_assets": TableSpec(
        columns=_entity_columns(
            "event_key",
            "asset_key",
            "names_json",
            "expected_generation_type",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "asset_key"),
    ),
    "associated_components": TableSpec(
        columns=_entity_columns(
            "event_key",
            "component_key",
            "names_json",
            "description_raw",
            "expected_component_type",
            "related_asset_keys_json",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "component_key"),
    ),
    "technical_mentions": TableSpec(
        columns=_entity_columns(
            "event_key",
            "owner_type",
            "owner_key",
            "technical_key",
            "expected_attribute_type",
            "expected_value_raw",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "technical_key"),
    ),
    "administrative_actions": TableSpec(
        columns=_entity_columns(
            "event_key",
            "action_key",
            "expected_action_type",
            "expected_decision",
            "expected_is_modification",
            "temporal_status",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "action_key"),
    ),
    "action_targets": TableSpec(
        columns=_entity_columns(
            "event_key",
            "action_key",
            "target_type",
            "target_truth_key",
            "applicability",
            "adjudication",
        ),
        key_columns=(
            "identificador_boe",
            "action_key",
            "target_type",
            "target_truth_key",
        ),
    ),
    "participants": TableSpec(
        columns=_entity_columns(
            "event_key",
            "participant_key",
            "participant_name_raw",
            "expected_participant_role",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "participant_key"),
    ),
    "locations": TableSpec(
        columns=_entity_columns(
            "event_key",
            "location_key",
            "location_name_raw",
            "expected_location_level",
            "applicability",
            "adjudication",
        ),
        key_columns=("identificador_boe", "location_key"),
    ),
    "evidence_passages": TableSpec(
        columns=_entity_columns(
            "owner_type",
            "owner_key",
            "passage_text",
            "applicability",
            "adjudication",
        ),
        key_columns=(
            "identificador_boe",
            "owner_type",
            "owner_key",
            "passage_text",
        ),
    ),
}


class TruthContractError(ValueError):
    """The truth artifact violates the frozen V1 contract."""


@dataclass(frozen=True)
class TruthArtifact:
    tables: Mapping[str, pd.DataFrame]
    table_semantic_sha256: Mapping[str, str]
    truth_artifact_id: str
    holdout_artifact_identity: str | None
    source_snapshot_identity: str | None
    manifest: Mapping[str, Any] | None


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype="string", keep_default_na=False)
    except (OSError, pd.errors.ParserError) as error:
        raise TruthContractError(f"Cannot read truth table {path}.") from error


def _required_nonblank(frame: pd.DataFrame, *, table: str) -> None:
    if frame.empty:
        return
    blank = frame.apply(lambda column: column.astype(str).str.strip().eq(""))
    if blank.any(axis=None):
        locations = [
            f"row={index + 2},column={column}"
            for index, row in blank.iterrows()
            for column, is_blank in row.items()
            if is_blank
        ]
        raise TruthContractError(
            f"{table} contains blank cells; use {NA!r}: {locations[:10]}."
        )


def _validate_common(frame: pd.DataFrame, *, table: str) -> None:
    _required_nonblank(frame, table=table)
    if frame.empty:
        return
    if not frame["identificador_boe"].map(
        lambda value: bool(_BOE_RE.fullmatch(str(value)))
    ).all():
        raise TruthContractError(f"{table} contains invalid BOE identifiers.")
    if table == "documents":
        if not frame["truth_contract_version"].eq(CONTRACT_VERSION).all():
            raise TruthContractError(f"{table} has an incompatible contract version.")
        if not frame["source_document_sha256"].map(
            lambda value: bool(_SHA_RE.fullmatch(str(value)))
        ).all():
            raise TruthContractError(f"{table} contains invalid source hashes.")
        try:
            frame["reviewed_on"].map(lambda value: date.fromisoformat(str(value)))
        except ValueError as error:
            raise TruthContractError(
                f"{table}.reviewed_on must use YYYY-MM-DD."
            ) from error
        if frame["reviewer_id"].eq(NA).any():
            raise TruthContractError(f"{table}.reviewer_id cannot be {NA!r}.")


def _validate_domain(
    frame: pd.DataFrame,
    column: str,
    domain: Iterable[str],
    *,
    table: str,
    allow_na: bool = False,
) -> None:
    allowed = set(domain) | ({NA} if allow_na else set())
    invalid = sorted(set(frame[column].astype(str)) - allowed)
    if invalid:
        raise TruthContractError(
            f"{table}.{column} contains values outside its closed domain: {invalid}."
        )


def _validate_keys(frame: pd.DataFrame, columns: Iterable[str], *, table: str) -> None:
    for column in columns:
        if not frame[column].map(
            lambda value: bool(_KEY_RE.fullmatch(str(value)))
        ).all():
            raise TruthContractError(f"{table}.{column} contains invalid truth keys.")


def parse_json_list(value: str, *, label: str, allow_empty: bool = True) -> list[str]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise TruthContractError(f"{label} must be a JSON array.") from error
    if (
        not isinstance(parsed, list)
        or any(not isinstance(item, str) or not item.strip() for item in parsed)
        or len(set(parsed)) != len(parsed)
        or (not allow_empty and not parsed)
    ):
        raise TruthContractError(
            f"{label} must be a unique JSON string array"
            + ("." if allow_empty else " with at least one item.")
        )
    return parsed


def _validate_json_columns(frame: pd.DataFrame, *, table: str) -> None:
    list_columns = [column for column in frame.columns if column.endswith("_json")]
    for index, row in frame.iterrows():
        for column in list_columns:
            allow_empty = column in {"related_asset_keys_json"} or (
                table == "associated_components" and column == "names_json"
            )
            parse_json_list(
                str(row[column]),
                label=f"{table}[{index + 2}].{column}",
                allow_empty=allow_empty,
            )


def _validate_applicability(frame: pd.DataFrame, *, table: str) -> None:
    if table == "documents":
        app_column = "scope_applicability"
        adj_column = "scope_adjudication"
    else:
        app_column = "applicability"
        adj_column = "adjudication"
    _validate_domain(frame, app_column, APPLICABILITY, table=table)
    _validate_domain(frame, adj_column, ADJUDICATION, table=table)
    invalid_scored = frame[adj_column].eq("scored_truth") & ~frame[app_column].eq(
        "applicable"
    )
    if invalid_scored.any():
        raise TruthContractError(
            f"{table} can use scored_truth only when applicability=applicable."
        )


def _validate_table(frame: pd.DataFrame, *, table: str, spec: TableSpec) -> None:
    if tuple(frame.columns) != spec.columns:
        raise TruthContractError(
            f"{table} columns do not match V1: expected={list(spec.columns)!r}; "
            f"found={list(frame.columns)!r}."
        )
    _validate_common(frame, table=table)
    if frame.empty:
        return
    if frame.duplicated(list(spec.key_columns), keep=False).any():
        raise TruthContractError(f"{table} contains duplicate truth keys.")
    _validate_applicability(frame, table=table)
    _validate_json_columns(frame, table=table)

    key_columns = [
        column
        for column in frame.columns
        if column.endswith("_key") and column != "target_truth_key"
    ]
    _validate_keys(frame, key_columns, table=table)

    if table == "documents":
        _validate_domain(frame, "annotation_status", ANNOTATION_STATUS, table=table)
        _validate_domain(
            frame,
            "expected_document_scope",
            DOCUMENT_SCOPES,
            table=table,
            allow_na=True,
        )
        scored = frame["scope_adjudication"].eq("scored_truth")
        if frame.loc[scored, "expected_document_scope"].eq(NA).any():
            raise TruthContractError("A scored document scope cannot be __NA__.")
    elif table == "generation_assets":
        _validate_domain(
            frame,
            "expected_generation_type",
            GENERATION_TYPES,
            table=table,
            allow_na=True,
        )
        for index, value in frame["names_json"].items():
            parse_json_list(
                str(value), label=f"{table}[{index + 2}].names_json", allow_empty=False
            )
    elif table == "associated_components":
        _validate_domain(
            frame,
            "expected_component_type",
            COMPONENT_TYPES,
            table=table,
            allow_na=True,
        )
        for index, row in frame.iterrows():
            names = parse_json_list(
                str(row["names_json"]),
                label=f"{table}[{index + 2}].names_json",
            )
            if not names and row["description_raw"] == NA:
                raise TruthContractError(
                    "A component needs at least one name or a description."
                )
    elif table == "technical_mentions":
        _validate_domain(
            frame,
            "owner_type",
            {"generation_asset", "associated_component"},
            table=table,
        )
        _validate_domain(
            frame,
            "expected_attribute_type",
            TECHNICAL_ATTRIBUTE_TYPES,
            table=table,
            allow_na=True,
        )
    elif table == "administrative_actions":
        _validate_domain(
            frame,
            "expected_action_type",
            ACTION_TYPES,
            table=table,
            allow_na=True,
        )
        _validate_domain(
            frame,
            "expected_decision",
            DECISIONS,
            table=table,
            allow_na=True,
        )
        _validate_domain(
            frame,
            "expected_is_modification",
            {"true", "false"},
            table=table,
            allow_na=True,
        )
        _validate_domain(
            frame,
            "temporal_status",
            TEMPORAL_STATUSES,
            table=table,
        )
    elif table == "action_targets":
        _validate_domain(frame, "target_type", TARGET_TYPES, table=table)
        _validate_keys(frame, ["target_truth_key"], table=table)
    elif table == "participants":
        _validate_domain(
            frame,
            "expected_participant_role",
            PARTICIPANT_ROLES,
            table=table,
            allow_na=True,
        )
    elif table == "locations":
        _validate_domain(
            frame,
            "expected_location_level",
            LOCATION_LEVELS,
            table=table,
            allow_na=True,
        )
    elif table == "evidence_passages":
        _validate_domain(frame, "owner_type", OWNER_TYPES, table=table)
        if frame["passage_text"].eq(NA).any():
            raise TruthContractError("Evidence passage text cannot be __NA__.")


def _index(frame: pd.DataFrame, *columns: str) -> set[tuple[str, ...]]:
    return {
        tuple(str(row[column]) for column in columns)
        for _, row in frame.iterrows()
    }


def _validate_foreign_keys(tables: Mapping[str, pd.DataFrame]) -> None:
    documents = tables["documents"]
    document_identity = {
        str(row["identificador_boe"]): str(row["source_document_sha256"])
        for _, row in documents.iterrows()
    }
    for table, frame in tables.items():
        if table == "documents":
            continue
        for _, row in frame.iterrows():
            boe_id = str(row["identificador_boe"])
            if boe_id not in document_identity:
                raise TruthContractError(f"{table} references an unknown document.")

    event_keys = _index(tables["events"], "identificador_boe", "event_key")
    for table in (
        "generation_assets",
        "associated_components",
        "technical_mentions",
        "administrative_actions",
        "action_targets",
        "participants",
        "locations",
    ):
        frame = tables[table]
        for _, row in frame.iterrows():
            if (str(row["identificador_boe"]), str(row["event_key"])) not in event_keys:
                raise TruthContractError(f"{table} references an unknown event.")

    asset_keys = _index(
        tables["generation_assets"], "identificador_boe", "asset_key"
    )
    component_keys = _index(
        tables["associated_components"], "identificador_boe", "component_key"
    )
    action_keys = _index(
        tables["administrative_actions"], "identificador_boe", "action_key"
    )
    asset_events = {
        (str(row["identificador_boe"]), str(row["asset_key"])): str(row["event_key"])
        for _, row in tables["generation_assets"].iterrows()
    }
    component_events = {
        (str(row["identificador_boe"]), str(row["component_key"])): str(
            row["event_key"]
        )
        for _, row in tables["associated_components"].iterrows()
    }
    action_events = {
        (str(row["identificador_boe"]), str(row["action_key"])): str(row["event_key"])
        for _, row in tables["administrative_actions"].iterrows()
    }
    entity_scored = {
        "event": {
            (str(row["identificador_boe"]), str(row["event_key"])): (
                row["applicability"] == "applicable"
                and row["adjudication"] == "scored_truth"
            )
            for _, row in tables["events"].iterrows()
        },
        "generation_asset": {
            (str(row["identificador_boe"]), str(row["asset_key"])): (
                row["applicability"] == "applicable"
                and row["adjudication"] == "scored_truth"
            )
            for _, row in tables["generation_assets"].iterrows()
        },
        "associated_component": {
            (str(row["identificador_boe"]), str(row["component_key"])): (
                row["applicability"] == "applicable"
                and row["adjudication"] == "scored_truth"
            )
            for _, row in tables["associated_components"].iterrows()
        },
        "administrative_action": {
            (str(row["identificador_boe"]), str(row["action_key"])): (
                row["applicability"] == "applicable"
                and row["adjudication"] == "scored_truth"
            )
            for _, row in tables["administrative_actions"].iterrows()
        },
    }
    owner_keys: dict[str, set[tuple[str, str]]] = {
        "generation_asset": asset_keys,
        "associated_component": component_keys,
        "technical_mention": _index(
            tables["technical_mentions"], "identificador_boe", "technical_key"
        ),
        "administrative_action": action_keys,
        "participant": _index(
            tables["participants"], "identificador_boe", "participant_key"
        ),
        "location": _index(tables["locations"], "identificador_boe", "location_key"),
    }

    for _, row in tables["technical_mentions"].iterrows():
        key = (str(row["identificador_boe"]), str(row["owner_key"]))
        expected = owner_keys[str(row["owner_type"])]
        if key not in expected:
            raise TruthContractError("A technical mention references an unknown owner.")
        owner_events = (
            asset_events
            if str(row["owner_type"]) == "generation_asset"
            else component_events
        )
        if owner_events[key] != str(row["event_key"]):
            raise TruthContractError(
                "A technical mention and its owner must belong to the same event."
            )

    for _, row in tables["associated_components"].iterrows():
        for asset_key in parse_json_list(
            str(row["related_asset_keys_json"]), label="related_asset_keys_json"
        ):
            if (str(row["identificador_boe"]), asset_key) not in asset_keys:
                raise TruthContractError("A component references an unknown asset.")
            if asset_events[(str(row["identificador_boe"]), asset_key)] != str(
                row["event_key"]
            ):
                raise TruthContractError(
                    "A component and its related asset must belong to the same event."
                )

    for _, row in tables["action_targets"].iterrows():
        boe_id = str(row["identificador_boe"])
        if (boe_id, str(row["action_key"])) not in action_keys:
            raise TruthContractError("An action target references an unknown action.")
        if action_events[(boe_id, str(row["action_key"]))] != str(row["event_key"]):
            raise TruthContractError(
                "An action target and action must belong to the same event."
            )
        target_type = str(row["target_type"])
        target_key = str(row["target_truth_key"])
        target_index = (
            event_keys
            if target_type == "event"
            else asset_keys
            if target_type == "generation_asset"
            else component_keys
        )
        if (boe_id, target_key) not in target_index:
            raise TruthContractError("An action target references an unknown entity.")
        target_event = (
            target_key
            if target_type == "event"
            else asset_events[(boe_id, target_key)]
            if target_type == "generation_asset"
            else component_events[(boe_id, target_key)]
        )
        if target_event != str(row["event_key"]):
            raise TruthContractError(
                "An action target and target entity must belong to the same event."
            )
        target_is_scored = (
            row["applicability"] == "applicable"
            and row["adjudication"] == "scored_truth"
        )
        if target_is_scored and (
            not entity_scored["administrative_action"][(boe_id, str(row["action_key"]))]
            or not entity_scored[target_type][(boe_id, target_key)]
        ):
            raise TruthContractError(
                "A scored action target requires a scored action and target entity."
            )

    for _, row in tables["evidence_passages"].iterrows():
        owner_type = str(row["owner_type"])
        owner_key = (str(row["identificador_boe"]), str(row["owner_key"]))
        if owner_key not in owner_keys[owner_type]:
            raise TruthContractError("Evidence references an unknown owner.")


def _validate_completeness(tables: Mapping[str, pd.DataFrame]) -> None:
    documents = tables["documents"]
    incomplete = documents.loc[~documents["annotation_status"].eq("complete")]
    if not incomplete.empty:
        raise TruthContractError("Truth cannot be frozen with draft documents.")

    scored_events = tables["events"].loc[
        tables["events"]["adjudication"].eq("scored_truth")
    ]
    scored_assets = tables["generation_assets"].loc[
        tables["generation_assets"]["adjudication"].eq("scored_truth")
    ]
    scored_actions = tables["administrative_actions"].loc[
        tables["administrative_actions"]["adjudication"].eq("scored_truth")
    ]
    scored_technical = tables["technical_mentions"].loc[
        tables["technical_mentions"]["adjudication"].eq("scored_truth")
    ]
    scored_evidence = tables["evidence_passages"].loc[
        tables["evidence_passages"]["adjudication"].eq("scored_truth")
        & tables["evidence_passages"]["applicability"].eq("applicable")
    ]
    for _, document in documents.iterrows():
        if document["scope_adjudication"] != "scored_truth":
            continue
        boe_id = str(document["identificador_boe"])
        events = scored_events.loc[scored_events["identificador_boe"].eq(boe_id)]
        if document["expected_document_scope"] == "generation_project_specific":
            if events.empty:
                raise TruthContractError(
                    "A project-specific document needs at least one scored event."
                )
        elif not events.empty:
            raise TruthContractError(
                "A non-relevant document cannot contain scored events."
            )
    for _, event in scored_events.iterrows():
        boe_id = str(event["identificador_boe"])
        event_key = str(event["event_key"])
        assets = scored_assets.loc[
            scored_assets["identificador_boe"].eq(boe_id)
            & scored_assets["event_key"].eq(event_key)
        ]
        actions = scored_actions.loc[
            scored_actions["identificador_boe"].eq(boe_id)
            & scored_actions["event_key"].eq(event_key)
        ]
        if assets.empty or actions.empty:
            raise TruthContractError(
                "Every scored event needs a scored generation asset and action."
            )
    evidence_owners = _index(
        scored_evidence, "identificador_boe", "owner_type", "owner_key"
    )
    for table, owner_type, key_column in (
        (scored_actions, "administrative_action", "action_key"),
        (scored_technical, "technical_mention", "technical_key"),
    ):
        for _, row in table.iterrows():
            if (
                str(row["identificador_boe"]),
                owner_type,
                str(row[key_column]),
            ) not in evidence_owners:
                raise TruthContractError(
                    f"Every scored {owner_type} needs scored entity-specific evidence."
                )


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


def load_truth(
    truth_dir: Path,
    *,
    require_complete: bool = False,
    require_frozen: bool = False,
) -> TruthArtifact:
    truth_dir = Path(truth_dir)
    tables: dict[str, pd.DataFrame] = {}
    for table, spec in TABLE_SPECS.items():
        path = truth_dir / f"{table}.csv"
        if not path.is_file():
            raise TruthContractError(f"Missing truth table: {path}.")
        frame = _read_csv(path)
        _validate_table(frame, table=table, spec=spec)
        tables[table] = frame
    _validate_foreign_keys(tables)
    if require_complete:
        _validate_completeness(tables)

    metadata_path = truth_dir / TRUTH_METADATA
    metadata: Mapping[str, Any] = {}
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TruthContractError("Invalid truth metadata JSON.") from error
        if metadata.get("truth_contract_version") != CONTRACT_VERSION:
            raise TruthContractError("Truth metadata contract version mismatch.")
        if metadata.get("predictions_exposed_during_annotation") is not False:
            raise TruthContractError(
                "Blind truth metadata must declare that predictions were not exposed."
            )
    holdout_identity = metadata.get("holdout_artifact_identity")
    source_identity = metadata.get("source_snapshot_identity")
    for label, value in (
        ("holdout_artifact_identity", holdout_identity),
        ("source_snapshot_identity", source_identity),
    ):
        if value is not None and not _SHA_RE.fullmatch(str(value)):
            raise TruthContractError(f"Invalid {label} in truth metadata.")

    table_ids, artifact_id = truth_semantic_identity(
        tables,
        holdout_artifact_identity=(None if holdout_identity is None else str(holdout_identity)),
        source_snapshot_identity=(None if source_identity is None else str(source_identity)),
    )

    manifest: Mapping[str, Any] | None = None
    manifest_path = truth_dir / TRUTH_MANIFEST
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TruthContractError("Invalid frozen truth manifest.") from error
        if (
            manifest.get("truth_contract_version") != CONTRACT_VERSION
            or manifest.get("truth_contract_declaration_sha256")
            != sha256_file(CONTRACT_DECLARATION_PATH)
            or manifest.get("truth_artifact_id") != artifact_id
            or manifest.get("table_semantic_sha256") != table_ids
            or manifest.get("status") != "frozen"
        ):
            raise TruthContractError("Frozen truth manifest identity mismatch.")
        files = manifest.get("truth_file_hashes")
        if not isinstance(files, dict):
            raise TruthContractError("Frozen truth manifest has no file hashes.")
        expected_names = {f"{table}.csv" for table in TABLE_SPECS} | {TRUTH_METADATA}
        if set(files) != expected_names:
            raise TruthContractError("Frozen truth manifest file set mismatch.")
        for filename, expected_hash in files.items():
            if sha256_file(truth_dir / filename) != expected_hash:
                raise TruthContractError(f"Frozen truth file drift: {filename}.")
    elif require_frozen:
        raise TruthContractError("Evaluation requires a frozen truth manifest.")

    return TruthArtifact(
        tables=tables,
        table_semantic_sha256=table_ids,
        truth_artifact_id=artifact_id,
        holdout_artifact_identity=(
            None if holdout_identity is None else str(holdout_identity)
        ),
        source_snapshot_identity=(None if source_identity is None else str(source_identity)),
        manifest=manifest,
    )


def _write_csv(frame: pd.DataFrame, path: Path, spec: TableSpec) -> None:
    ordered = (
        frame.sort_values(list(spec.key_columns), kind="stable")
        if not frame.empty
        else frame
    )
    ordered.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")


def freeze_truth(truth_dir: Path, output_dir: Path) -> TruthArtifact:
    truth = load_truth(truth_dir, require_complete=True)
    if truth.holdout_artifact_identity is None or truth.source_snapshot_identity is None:
        raise TruthContractError(
            "Complete truth metadata needs holdout and source snapshot identities."
        )
    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    published = False
    try:
        for table, spec in TABLE_SPECS.items():
            _write_csv(truth.tables[table], staging / f"{table}.csv", spec)
        metadata = {
            "truth_contract_version": CONTRACT_VERSION,
            "holdout_artifact_identity": truth.holdout_artifact_identity,
            "source_snapshot_identity": truth.source_snapshot_identity,
            "initialization_mode": "blind_annotation",
            "predictions_exposed_during_annotation": False,
        }
        (staging / TRUTH_METADATA).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        frozen = load_truth(staging, require_complete=True)
        file_hashes = {
            path.name: sha256_file(path)
            for path in sorted(staging.iterdir())
            if path.is_file()
        }
        documents = frozen.tables["documents"]
        reviewers = sorted(set(documents["reviewer_id"].astype(str)))
        reviewed_dates = sorted(set(documents["reviewed_on"].astype(str)))
        manifest = {
            "status": "frozen",
            "truth_contract_version": CONTRACT_VERSION,
            "truth_contract_declaration_sha256": sha256_file(
                CONTRACT_DECLARATION_PATH
            ),
            "truth_artifact_id": frozen.truth_artifact_id,
            "holdout_artifact_identity": frozen.holdout_artifact_identity,
            "source_snapshot_identity": frozen.source_snapshot_identity,
            "truth_file_hashes": file_hashes,
            "table_semantic_sha256": frozen.table_semantic_sha256,
            "document_count": len(documents),
            "reviewer_ids": reviewers,
            "reviewed_on": reviewed_dates,
            "predictions_exposed_during_annotation": False,
        }
        (staging / TRUTH_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        load_truth(staging, require_complete=True, require_frozen=True)
        staging.rename(output_dir)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)
    return load_truth(output_dir, require_complete=True, require_frozen=True)


def _documents_path(path: Path) -> Path:
    path = Path(path)
    if path.is_dir():
        path = path / "documents.parquet"
    if not path.is_file():
        raise TruthContractError(f"Source documents artifact not found: {path}.")
    return path


def initialize_truth(
    *,
    holdout_path: Path,
    documents_path: Path,
    output_dir: Path,
    holdout_version: str,
    reviewer_id: str,
    break_seal: bool,
) -> Path:
    if not break_seal:
        raise PermissionError(
            "REFUSED: init-truth reads sealed membership and source documents; "
            "repeat with explicit --break-seal only after human authorization."
        )
    if not holdout_version.strip() or not reviewer_id.strip():
        raise TruthContractError("holdout_version and reviewer_id are required.")
    print(
        "AUDIT: HOLDOUT SEAL IS BEING BROKEN FOR BLIND TRUTH INITIALIZATION; "
        "MODEL PREDICTIONS MUST REMAIN HIDDEN."
    )
    holdout_path = Path(holdout_path)
    holdout = _read_csv(holdout_path)
    required_holdout = {"identificador_boe", "source_document_sha256"}
    if not required_holdout.issubset(holdout.columns):
        raise TruthContractError("Holdout selection misses identity columns.")
    if holdout["identificador_boe"].duplicated().any():
        raise TruthContractError("Holdout selection contains duplicate documents.")
    documents = pd.read_parquet(_documents_path(documents_path))
    required_documents = {"identificador", "source_document_sha256"}
    if not required_documents.issubset(documents.columns):
        raise TruthContractError("Source documents miss identity columns.")
    selected = holdout[["identificador_boe", "source_document_sha256"]].merge(
        documents[["identificador", "source_document_sha256"]],
        left_on=["identificador_boe", "source_document_sha256"],
        right_on=["identificador", "source_document_sha256"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not selected["_merge"].eq("both").all():
        raise TruthContractError("Holdout/source identity mismatch.")

    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    reviewed_on = datetime.now(timezone.utc).date().isoformat()
    document_rows = pd.DataFrame({
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_version": holdout_version,
        "identificador_boe": selected["identificador_boe"].astype(str),
        "source_document_sha256": selected["source_document_sha256"].astype(str),
        "annotation_status": "draft",
        "scope_applicability": "unknown",
        "scope_adjudication": "excluded_from_scoring",
        "expected_document_scope": NA,
        "reviewer_id": reviewer_id,
        "reviewed_on": reviewed_on,
        "annotation_notes": "pending_blind_annotation",
    })
    _write_csv(document_rows, output_dir / "documents.csv", TABLE_SPECS["documents"])
    for table, spec in TABLE_SPECS.items():
        if table == "documents":
            continue
        pd.DataFrame(columns=spec.columns).to_csv(
            output_dir / f"{table}.csv", index=False, lineterminator="\n"
        )
    metadata = {
        "truth_contract_version": CONTRACT_VERSION,
        "holdout_artifact_identity": sha256_file(holdout_path),
        "source_snapshot_identity": FROZEN_SOURCE_SNAPSHOT_ID,
        "initialization_mode": "blind_annotation",
        "predictions_exposed_during_annotation": False,
        "seal_break_acknowledged": True,
    }
    (output_dir / TRUTH_METADATA).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    load_truth(output_dir)
    return output_dir


def copy_empty_templates(output_dir: Path) -> None:
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    shutil.copytree(TEMPLATES_DIR, output_dir)
