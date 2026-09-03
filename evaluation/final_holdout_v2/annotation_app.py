from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

# Streamlit launches file entrypoints with their script directory on sys.path.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

import pandas as pd
import streamlit as st

from evaluation.final_holdout_v1.annotation import (
    EntityChoice,
    aliases_for_edit,
    build_official_boe_url,
    derive_entity_reference,
    entity_choices,
    serialize_aliases,
    serialize_key_selection,
    validate_evidence_literal,
)
from evaluation.final_holdout_v2.annotation import (
    action_evidence_rows,
    build_ai_qa_review_package,
    configured_paths,
    delete_truth_row,
    load_annotation_workspace,
    mark_document_complete,
    next_key_for_table,
    secondary_evidence_rows,
    serialize_affected_assets,
    update_document_scope,
    upsert_truth_row,
    validate_document,
)
from evaluation.final_holdout_v2.contract import (
    ACTION_TYPES,
    ADJUDICATION,
    APPLICABILITY,
    COMPONENT_TYPES,
    DECISIONS,
    DOCUMENT_SCOPES,
    GENERATION_TYPES,
    LOCATION_LEVELS,
    NA,
    PARTICIPANT_ROLES,
    TABLE_SPECS,
    TECHNICAL_ATTRIBUTE_TYPES,
    TEMPORAL_STATUSES,
    TruthArtifact,
    TruthContractError,
)
from evaluation.final_holdout_v2.terminology import (
    canonical_path,
    entity_label,
    field_label,
    table_key_field,
    table_entity,
    widget_label,
)


SECONDARY_TABLES = (
    "associated_components",
    "technical_mentions",
    "action_targets",
    "participants",
    "evidence_passages",
)
ACTION_SUMMARY_FIELDS = (
    "expected_action_type",
    "expected_decision",
    "expected_is_modification",
    "temporal_status",
    "expected_affected_generation_asset_keys_json",
)


st.set_page_config(
    page_title="Anotación humana ciega V2",
    page_icon=":material/fact_check:",
    layout="wide",
)


def _domain_options(
    domain: Sequence[str] | set[str], *, allow_na: bool = False
) -> list[str]:
    options = sorted(str(value) for value in domain)
    if allow_na:
        options.append(NA)
    return options


def _index_or_none(options: Sequence[str], value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return list(options).index(str(value))
    except ValueError:
        return None


def _select_domain(
    table: str,
    field: str,
    domain: Sequence[str] | set[str],
    *,
    local_key: str | None,
    current: object | None,
    key: str,
    allow_na: bool = False,
    row: Mapping[str, object] | None = None,
) -> str | None:
    entity = table_entity(table)
    options = _domain_options(domain, allow_na=allow_na)
    return st.selectbox(
        _field_widget_label(table, field, local_key=local_key, row=row),
        options,
        index=_index_or_none(options, current),
        placeholder="Selecciona una opción del contrato",
        key=key,
    )


def _field_widget_label(
    table: str,
    field: str,
    *,
    local_key: str | None,
    row: Mapping[str, object] | None = None,
) -> str:
    entity = table_entity(table)
    if entity == "evidence_passage":
        path = (
            "evidence_passage/<owner_entity>/<owner_key>"
            if row is None
            else canonical_path(
                entity,
                owner_entity=str(row["owner_type"]),
                local_key=str(row["owner_key"]),
            )
        )
        return f"{field_label(entity, field)} · {path}"
    return widget_label(entity, field, local_key=local_key)


def _required(value: object | None, label: str) -> str:
    if value is None:
        raise TruthContractError(f"Selecciona {label}.")
    return str(value)


def _explicit_text(value: object) -> str:
    return str(value).strip() or NA


def _notes_for_edit(value: object | None) -> str:
    return "" if value is None or str(value) == NA else str(value)


def _common_fields(
    table: str,
    local_key: str,
    row: Mapping[str, object] | None,
    *,
    key_prefix: str,
) -> tuple[str | None, str | None, str]:
    applicability = _select_domain(
        table,
        "applicability",
        APPLICABILITY,
        local_key=local_key,
        current=None if row is None else row["applicability"],
        key=f"{key_prefix}_applicability",
        row=row,
    )
    adjudication = _select_domain(
        table,
        "adjudication",
        ADJUDICATION,
        local_key=local_key,
        current=None if row is None else row["adjudication"],
        key=f"{key_prefix}_adjudication",
        row=row,
    )
    notes = st.text_area(
        _field_widget_label(
            table, "annotation_notes", local_key=local_key, row=row
        ),
        value=_notes_for_edit(None if row is None else row["annotation_notes"]),
        key=f"{key_prefix}_notes",
    )
    return applicability, adjudication, notes


def _frame_for_boe(truth: TruthArtifact, table: str, boe_id: str) -> pd.DataFrame:
    frame = truth.tables[table]
    return frame.loc[frame["identificador_boe"].astype(str).eq(boe_id)].copy()


def _row_options(frame: pd.DataFrame, table: str) -> tuple[list[str], dict[str, int]]:
    keys = [
        column
        for column in TABLE_SPECS[table].key_columns
        if column != "identificador_boe"
    ]
    labels: list[str] = []
    positions: dict[str, int] = {}
    for position, (_, row) in enumerate(frame.iterrows()):
        label = " · ".join(f"{column}={row[column]}" for column in keys)
        labels.append(label)
        positions[label] = position
    return labels, positions


def _original_key(table: str, row: Mapping[str, object]) -> dict[str, str]:
    return {
        column: str(row[column])
        for column in TABLE_SPECS[table].key_columns
        if column != "identificador_boe"
    }


def _display_rows(
    frame: pd.DataFrame,
    *,
    empty_message: str = "Todavía no hay filas para este BOE.",
) -> None:
    if frame.empty:
        st.info(empty_message)
        return
    visible = frame.drop(columns=["identificador_boe"]).copy()
    for column in (
        "names_json",
        "related_asset_keys_json",
        "expected_affected_generation_asset_keys_json",
    ):
        if column in visible.columns:
            visible[column] = visible[column].map(
                lambda value: "\n".join(json.loads(str(value)))
            )
    st.dataframe(visible, hide_index=True, height="content")


def _event_select(
    truth: TruthArtifact,
    boe_id: str,
    *,
    current: str | None,
    key: str,
    entity: str,
    local_key: str,
) -> str | None:
    events = _frame_for_boe(truth, "events", boe_id)
    values = events["event_key"].astype(str).tolist()
    labels = {
        str(row["event_key"]): f"{row['event_key']} · {row['event_label']}"
        for _, row in events.iterrows()
    }
    return st.selectbox(
        widget_label(entity, "event_key", local_key=local_key),
        values,
        index=_index_or_none(values, current),
        format_func=lambda value: labels[value],
        placeholder="Selecciona un evento existente",
        key=key,
    )


def _asset_options(
    truth: TruthArtifact, boe_id: str
) -> tuple[list[str], dict[str, str]]:
    assets = _frame_for_boe(truth, "generation_assets", boe_id)
    values = assets["asset_key"].astype(str).tolist()
    labels = {
        str(row["asset_key"]): (
            f"{row['event_key']} · {row['asset_key']} · {row['names_json']}"
        )
        for _, row in assets.iterrows()
    }
    return values, labels


def _choice_select(
    label: str,
    choices: Sequence[EntityChoice],
    *,
    current_type: str | None,
    current_key: str | None,
    key: str,
) -> str | None:
    values = [choice.value for choice in choices]
    labels = {choice.value: choice.label for choice in choices}
    current = (
        None
        if current_type is None or current_key is None
        else f"{current_type}:{current_key}"
    )
    return st.selectbox(
        label,
        values,
        index=_index_or_none(values, current),
        format_func=lambda value: labels[value],
        placeholder="Selecciona una entidad humana existente",
        key=key,
    )


def _save_notice(message: str) -> None:
    st.session_state["v2_annotation_notice"] = message
    st.rerun()


def _navigate_to(boe_id: str) -> None:
    st.session_state["v2_current_boe"] = boe_id
    st.session_state["v2_direct_boe"] = boe_id


def _render_delete(
    truth_dir: Path,
    table: str,
    boe_id: str,
    frame: pd.DataFrame,
    source_text: str,
    *,
    key_suffix: str = "all",
) -> None:
    labels, positions = _row_options(frame, table)
    selected = st.selectbox(
        "Fila que se eliminará",
        labels,
        key=f"v2_delete_{table}_{boe_id}_{key_suffix}",
    )
    row = frame.iloc[positions[selected]].to_dict()
    with st.form(f"v2_delete_form_{table}_{boe_id}_{key_suffix}"):
        confirmed = st.checkbox("Confirmo la eliminación de esta fila")
        submitted = st.form_submit_button(
            "Eliminar fila", icon=":material/delete:"
        )
    if submitted:
        if not confirmed:
            st.error("Confirma explícitamente la eliminación.")
            return
        try:
            delete_truth_row(
                truth_dir,
                table,
                boe_id,
                _original_key(table, row),
                source_text=source_text,
            )
        except (OSError, ValueError, TruthContractError) as error:
            st.error(str(error))
        else:
            _save_notice("Fila eliminada.")


def _render_entity_form(
    truth_dir: Path,
    truth: TruthArtifact,
    table: str,
    boe_id: str,
    frame: pd.DataFrame,
    mode: str,
    source_text: str,
    *,
    action_evidence_only: bool = False,
    evidence_owner_key: str | None = None,
) -> None:
    row: dict[str, object] | None = None
    if mode == "Editar":
        labels, positions = _row_options(frame, table)
        selected = st.selectbox(
            "Fila que se editará",
            labels,
            key=(
                f"v2_edit_{table}_{boe_id}_{action_evidence_only}_"
                f"{evidence_owner_key or 'all'}"
            ),
        )
        row = frame.iloc[positions[selected]].to_dict()

    generated = (
        next_key_for_table(truth, table, boe_id)
        if mode == "Añadir" and table in KEYED_TABLES
        else None
    )
    local_key = generated or _local_key_for_form(table, row)
    if generated is not None:
        st.caption(f"Clave local generada al guardar: `{generated}`")
    elif local_key:
        st.caption(f"Clave local: `{local_key}`")

    entity = table_entity(table)
    key_prefix = (
        f"v2_{mode}_{table}_{boe_id}_{action_evidence_only}_"
        f"{evidence_owner_key or 'all'}"
    )
    with st.form(f"v2_form_{key_prefix}", enter_to_submit=False):
        values: dict[str, object] = {}
        if table == "events":
            values["event_key"] = local_key
            values["event_label"] = st.text_input(
                widget_label(entity, "event_label", local_key=local_key),
                value="" if row is None else str(row["event_label"]),
            )
        elif table == "generation_assets":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
                entity=entity,
                local_key=local_key,
            )
            values["asset_key"] = local_key
            values["aliases"] = st.text_area(
                widget_label(entity, "names_json", local_key=local_key),
                value="" if row is None else aliases_for_edit(str(row["names_json"])),
                help="Introduce un alias literal por línea; la aplicación serializa la lista.",
            )
            values["expected_generation_type"] = _select_domain(
                table,
                "expected_generation_type",
                GENERATION_TYPES,
                local_key=local_key,
                current=None if row is None else row["expected_generation_type"],
                key=f"{key_prefix}_generation_type",
                allow_na=True,
            )
        elif table == "administrative_actions":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
                entity=entity,
                local_key=local_key,
            )
            values["action_key"] = local_key
            values["expected_action_type"] = _select_domain(
                table,
                "expected_action_type",
                ACTION_TYPES,
                local_key=local_key,
                current=None if row is None else row["expected_action_type"],
                key=f"{key_prefix}_action_type",
                allow_na=True,
            )
            values["expected_decision"] = _select_domain(
                table,
                "expected_decision",
                DECISIONS,
                local_key=local_key,
                current=None if row is None else row["expected_decision"],
                key=f"{key_prefix}_decision",
                allow_na=True,
            )
            values["expected_is_modification"] = _select_domain(
                table,
                "expected_is_modification",
                {"true", "false"},
                local_key=local_key,
                current=None if row is None else row["expected_is_modification"],
                key=f"{key_prefix}_modification",
                allow_na=True,
            )
            values["temporal_status"] = _select_domain(
                table,
                "temporal_status",
                TEMPORAL_STATUSES,
                local_key=local_key,
                current=None if row is None else row["temporal_status"],
                key=f"{key_prefix}_temporal_status",
            )
            asset_values, asset_labels = _asset_options(truth, boe_id)
            current_assets = (
                []
                if row is None
                else json.loads(
                    str(row["expected_affected_generation_asset_keys_json"])
                )
            )
            values["affected_assets"] = st.multiselect(
                widget_label(
                    entity,
                    "expected_affected_generation_asset_keys_json",
                    local_key=local_key,
                ),
                asset_values,
                default=current_assets,
                format_func=lambda value: asset_labels[value],
                help=(
                    "Selecciona explícitamente todos los activos afectados; "
                    "la aplicación serializa el contrato y no infiere el único activo."
                ),
            )
        elif table == "locations":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
                entity=entity,
                local_key=local_key,
            )
            values["location_key"] = local_key
            values["location_name_raw"] = st.text_input(
                widget_label(entity, "location_name_raw", local_key=local_key),
                value="" if row is None else str(row["location_name_raw"]),
            )
            values["expected_location_level"] = _select_domain(
                table,
                "expected_location_level",
                LOCATION_LEVELS,
                local_key=local_key,
                current=None if row is None else row["expected_location_level"],
                key=f"{key_prefix}_location_level",
                allow_na=True,
            )
        elif table == "associated_components":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
                entity=entity,
                local_key=local_key,
            )
            values["component_key"] = local_key
            values["aliases"] = st.text_area(
                widget_label(entity, "names_json", local_key=local_key),
                value="" if row is None else aliases_for_edit(str(row["names_json"])),
                help="Un nombre literal por línea; la aplicación serializa la lista.",
            )
            values["description_raw"] = st.text_area(
                widget_label(entity, "description_raw", local_key=local_key),
                value=(
                    ""
                    if row is None or str(row["description_raw"]) == NA
                    else str(row["description_raw"])
                ),
            )
            values["expected_component_type"] = _select_domain(
                table,
                "expected_component_type",
                COMPONENT_TYPES,
                local_key=local_key,
                current=None if row is None else row["expected_component_type"],
                key=f"{key_prefix}_component_type",
                allow_na=True,
            )
            asset_values, asset_labels = _asset_options(truth, boe_id)
            values["related_assets"] = st.multiselect(
                widget_label(entity, "related_asset_keys_json", local_key=local_key),
                asset_values,
                default=(
                    []
                    if row is None
                    else json.loads(str(row["related_asset_keys_json"]))
                ),
                format_func=lambda value: asset_labels[value],
            )
        elif table == "technical_mentions":
            owners = entity_choices(truth, boe_id, purpose="technical_owner")
            values["owner"] = _choice_select(
                widget_label(entity, "owner_key", local_key=local_key),
                owners,
                current_type=None if row is None else str(row["owner_type"]),
                current_key=None if row is None else str(row["owner_key"]),
                key=f"{key_prefix}_owner",
            )
            values["technical_key"] = local_key
            values["expected_attribute_type"] = _select_domain(
                table,
                "expected_attribute_type",
                TECHNICAL_ATTRIBUTE_TYPES,
                local_key=local_key,
                current=None if row is None else row["expected_attribute_type"],
                key=f"{key_prefix}_attribute_type",
                allow_na=True,
            )
            values["expected_value_raw"] = st.text_input(
                widget_label(entity, "expected_value_raw", local_key=local_key),
                value="" if row is None else str(row["expected_value_raw"]),
            )
        elif table == "participants":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
                entity=entity,
                local_key=local_key,
            )
            values["participant_key"] = local_key
            values["participant_name_raw"] = st.text_input(
                widget_label(entity, "participant_name_raw", local_key=local_key),
                value="" if row is None else str(row["participant_name_raw"]),
            )
            values["expected_participant_role"] = _select_domain(
                table,
                "expected_participant_role",
                PARTICIPANT_ROLES,
                local_key=local_key,
                current=None if row is None else row["expected_participant_role"],
                key=f"{key_prefix}_participant_role",
                allow_na=True,
            )
        elif table == "action_targets":
            actions = _frame_for_boe(truth, "administrative_actions", boe_id)
            action_values = actions["action_key"].astype(str).tolist()
            values["action_key"] = st.selectbox(
                "Actuación · action_target/<action_key>.target",
                action_values,
                index=_index_or_none(
                    action_values, None if row is None else row["action_key"]
                ),
                key=f"{key_prefix}_action",
            )
            targets = entity_choices(truth, boe_id, purpose="action_target")
            values["target"] = _choice_select(
                "Objetivo exacto · action_target/<action_key>.target",
                targets,
                current_type=None if row is None else str(row["target_type"]),
                current_key=None if row is None else str(row["target_truth_key"]),
                key=f"{key_prefix}_target",
            )
        elif table == "evidence_passages":
            owners = entity_choices(truth, boe_id, purpose="evidence_owner")
            if evidence_owner_key is not None:
                owners = tuple(
                    choice
                    for choice in owners
                    if choice.owner_type == "administrative_action"
                    and choice.owner_key == evidence_owner_key
                )
                if len(owners) != 1:
                    raise TruthContractError(
                        "La actuación seleccionada ya no existe en la verdad V2."
                    )
                values["owner"] = owners[0].value
                current_path = canonical_path(
                    "evidence_passage",
                    owner_entity="administrative_action",
                    local_key=evidence_owner_key,
                )
                st.caption(f"Entidad respaldada · `{current_path}`")
            else:
                owners = tuple(
                    choice
                    for choice in owners
                    if (choice.owner_type == "administrative_action")
                    == action_evidence_only
                )
                values["owner"] = _choice_select(
                    "Entidad respaldada · evidence_passage/<owner_entity>/<owner_key>",
                    owners,
                    current_type=None if row is None else str(row["owner_type"]),
                    current_key=None if row is None else str(row["owner_key"]),
                    key=f"{key_prefix}_owner",
                )
                current_path = (
                    "evidence_passage/<owner_entity>/<owner_key>"
                    if row is None
                    else canonical_path(
                        "evidence_passage",
                        owner_entity=str(row["owner_type"]),
                        local_key=str(row["owner_key"]),
                    )
                )
            values["passage_text"] = st.text_area(
                f"Pasaje continuo literal · {current_path}",
                value="" if row is None else str(row["passage_text"]),
                height=160,
            )
        else:
            raise AssertionError(f"Tabla V2 no gestionada: {table}")

        common_local_key = local_key or (
            str(row["owner_key"]) if row is not None and table == "evidence_passages" else "pending"
        )
        applicability, adjudication, notes = _common_fields(
            table,
            common_local_key,
            row,
            key_prefix=key_prefix,
        )
        submitted = st.form_submit_button(
            "Guardar fila", icon=":material/save:"
        )

    if not submitted:
        return
    try:
        entity_row: dict[str, str] = {
            "identificador_boe": boe_id,
            "applicability": _required(applicability, "la aplicabilidad"),
            "adjudication": _required(adjudication, "la adjudicación"),
            "annotation_notes": _explicit_text(notes),
        }
        if table == "events":
            entity_row.update(
                event_key=str(values["event_key"]),
                event_label=_explicit_text(values["event_label"]),
            )
        elif table == "generation_assets":
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                asset_key=str(values["asset_key"]),
                names_json=serialize_aliases(str(values["aliases"])),
                expected_generation_type=_required(
                    values["expected_generation_type"], "el tipo de generación"
                ),
            )
        elif table == "administrative_actions":
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                action_key=str(values["action_key"]),
                expected_action_type=_required(
                    values["expected_action_type"], "el tipo de actuación"
                ),
                expected_decision=_required(values["expected_decision"], "la decisión"),
                expected_is_modification=_required(
                    values["expected_is_modification"], "si es modificación"
                ),
                temporal_status=_required(
                    values["temporal_status"], "la temporalidad"
                ),
                expected_affected_generation_asset_keys_json=serialize_affected_assets(
                    values["affected_assets"]
                ),
            )
        elif table == "locations":
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                location_key=str(values["location_key"]),
                location_name_raw=_explicit_text(values["location_name_raw"]),
                expected_location_level=_required(
                    values["expected_location_level"], "el nivel administrativo"
                ),
            )
        elif table == "associated_components":
            aliases = [
                value.strip()
                for value in str(values["aliases"]).splitlines()
                if value.strip()
            ]
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                component_key=str(values["component_key"]),
                names_json=serialize_key_selection(aliases),
                description_raw=_explicit_text(values["description_raw"]),
                expected_component_type=_required(
                    values["expected_component_type"], "el tipo de componente"
                ),
                related_asset_keys_json=serialize_key_selection(
                    values["related_assets"]
                ),
            )
        elif table == "technical_mentions":
            owners = entity_choices(truth, boe_id, purpose="technical_owner")
            owner_type, owner_key = derive_entity_reference(
                _required(values["owner"], "la entidad propietaria"), owners
            )
            owner = next(choice for choice in owners if choice.value == values["owner"])
            entity_row.update(
                event_key=str(owner.event_key),
                owner_type=owner_type,
                owner_key=owner_key,
                technical_key=str(values["technical_key"]),
                expected_attribute_type=_required(
                    values["expected_attribute_type"], "el tipo de atributo"
                ),
                expected_value_raw=_explicit_text(values["expected_value_raw"]),
            )
        elif table == "participants":
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                participant_key=str(values["participant_key"]),
                participant_name_raw=_explicit_text(values["participant_name_raw"]),
                expected_participant_role=_required(
                    values["expected_participant_role"], "el rol"
                ),
            )
        elif table == "action_targets":
            action_key = _required(values["action_key"], "la actuación")
            action = _frame_for_boe(truth, "administrative_actions", boe_id).loc[
                lambda frame: frame["action_key"].astype(str).eq(action_key)
            ].iloc[0]
            targets = entity_choices(truth, boe_id, purpose="action_target")
            target_type, target_key = derive_entity_reference(
                _required(values["target"], "el objetivo"), targets
            )
            entity_row.update(
                event_key=str(action["event_key"]),
                action_key=action_key,
                target_type=target_type,
                target_truth_key=target_key,
            )
        elif table == "evidence_passages":
            owners = entity_choices(truth, boe_id, purpose="evidence_owner")
            owner_type, owner_key = derive_entity_reference(
                _required(values["owner"], "la entidad respaldada"), owners
            )
            if action_evidence_only != (owner_type == "administrative_action"):
                raise TruthContractError("Selecciona una entidad de la sección correcta.")
            entity_row.update(
                owner_type=owner_type,
                owner_key=owner_key,
                passage_text=validate_evidence_literal(
                    str(values["passage_text"]), source_text
                ),
            )
        upsert_truth_row(
            truth_dir,
            table,
            boe_id,
            entity_row,
            original_key=None if row is None else _original_key(table, row),
            source_text=source_text,
        )
    except (IndexError, OSError, ValueError, TruthContractError) as error:
        st.error(str(error))
    else:
        _save_notice("Fila guardada y validada.")


KEYED_TABLES = {
    "events",
    "generation_assets",
    "associated_components",
    "technical_mentions",
    "administrative_actions",
    "participants",
    "locations",
}


def _local_key_for_form(
    table: str, row: Mapping[str, object] | None
) -> str:
    if row is None:
        return "pending"
    key_field = table_key_field(table)
    if key_field is None:
        return "pending"
    return str(row[key_field])


def _render_table_editor(
    truth_dir: Path,
    truth: TruthArtifact,
    table: str,
    boe_id: str,
    source_text: str,
    *,
    action_evidence_only: bool = False,
    evidence_owner_key: str | None = None,
    empty_message: str = "Todavía no hay filas para este BOE.",
) -> None:
    if table == "evidence_passages":
        frame = (
            action_evidence_rows(
                truth,
                boe_id,
                action_key=evidence_owner_key,
            )
            if action_evidence_only
            else secondary_evidence_rows(truth, boe_id)
        )
    else:
        frame = _frame_for_boe(truth, table, boe_id)
    editor_scope = evidence_owner_key or (
        "primary" if action_evidence_only else "all"
    )
    _display_rows(frame, empty_message=empty_message)
    modes = ["Añadir"] if frame.empty else ["Editar", "Añadir", "Eliminar"]
    mode = st.segmented_control(
        "Operación",
        modes,
        default=modes[0],
        key=f"v2_mode_{table}_{boe_id}_{editor_scope}",
    )
    if mode == "Eliminar":
        _render_delete(
            truth_dir,
            table,
            boe_id,
            frame,
            source_text,
            key_suffix=editor_scope,
        )
    else:
        _render_entity_form(
            truth_dir,
            truth,
            table,
            boe_id,
            frame,
            str(mode),
            source_text,
            action_evidence_only=action_evidence_only,
            evidence_owner_key=evidence_owner_key,
        )


def _render_action_summary(action: Mapping[str, object]) -> None:
    action_key = str(action["action_key"])
    st.markdown(f"**Actuación administrativa · `{action_key}`**")
    st.caption(
        f"`{canonical_path('administrative_action', local_key=action_key)}`"
    )
    for field in ACTION_SUMMARY_FIELDS:
        value = str(action[field])
        if field == "expected_affected_generation_asset_keys_json":
            affected = json.loads(value)
            value = ", ".join(affected) if affected else "Sin atribución resuelta"
        path = canonical_path(
            "administrative_action",
            local_key=action_key,
            field=field,
        )
        st.markdown(f"**{field_label('administrative_action', field)}** · `{path}`")
        st.write(value)


def _render_action_evidence_workflow(
    truth_dir: Path,
    truth: TruthArtifact,
    boe_id: str,
    source_text: str,
) -> None:
    actions = _frame_for_boe(truth, "administrative_actions", boe_id)
    if actions.empty:
        st.info(
            "No hay actuaciones administrativas. Añade primero una actuación "
            "para poder registrar su evidencia."
        )
        return
    actions = actions.sort_values("action_key", kind="stable")
    for _, action in actions.iterrows():
        action_key = str(action["action_key"])
        evidence_path = canonical_path(
            "evidence_passage",
            owner_entity="administrative_action",
            local_key=action_key,
        )
        with st.container(border=True):
            _render_action_summary(action)
            st.markdown(f"**Evidencias de `{action_key}`**")
            st.caption(f"`{evidence_path}`")
            _render_table_editor(
                truth_dir,
                truth,
                "evidence_passages",
                boe_id,
                source_text,
                action_evidence_only=True,
                evidence_owner_key=action_key,
                empty_message=(
                    f"Todavía no hay evidencia para {action_key}. Añade al menos "
                    "un pasaje literal continuo para completar la actuación."
                ),
            )


def _render_scope(
    truth_dir: Path,
    truth: TruthArtifact,
    boe_id: str,
    source_text: str,
) -> None:
    document = _frame_for_boe(truth, "documents", boe_id).iloc[0]
    with st.form(f"v2_scope_{boe_id}"):
        applicability = _select_domain(
            "documents",
            "scope_applicability",
            APPLICABILITY,
            local_key=None,
            current=document["scope_applicability"],
            key=f"v2_scope_applicability_{boe_id}",
        )
        adjudication = _select_domain(
            "documents",
            "scope_adjudication",
            ADJUDICATION,
            local_key=None,
            current=document["scope_adjudication"],
            key=f"v2_scope_adjudication_{boe_id}",
        )
        scope = _select_domain(
            "documents",
            "expected_document_scope",
            DOCUMENT_SCOPES,
            local_key=None,
            current=document["expected_document_scope"],
            key=f"v2_scope_value_{boe_id}",
            allow_na=True,
        )
        notes = st.text_area(
            widget_label("document", "annotation_notes"),
            value=_notes_for_edit(document["annotation_notes"]),
        )
        submitted = st.form_submit_button(
            "Guardar alcance", icon=":material/save:"
        )
    if submitted:
        try:
            update_document_scope(
                truth_dir,
                boe_id,
                scope_applicability=_required(applicability, "la aplicabilidad"),
                scope_adjudication=_required(adjudication, "la adjudicación"),
                expected_document_scope=_required(scope, "el alcance"),
                annotation_notes=notes,
                source_text=source_text,
            )
        except (OSError, ValueError, TruthContractError) as error:
            st.error(str(error))
        else:
            _save_notice("Alcance V2 guardado.")


def _render_completion(
    truth_dir: Path,
    boe_id: str,
    source_text: str,
) -> None:
    st.caption(
        "Solo cuentan alcance, eventos, activos, actuaciones, atribución efectiva, "
        "localizaciones y evidencia de actuaciones. Lo opcional nunca es requisito."
    )
    with st.container(horizontal=True):
        if st.button(
            "Validar documento V2",
            icon=":material/rule:",
            key=f"v2_validate_{boe_id}",
        ):
            try:
                validate_document(truth_dir, boe_id, source_text=source_text)
            except (OSError, ValueError, TruthContractError) as error:
                st.error(str(error))
            else:
                st.success("El documento satisface la completitud primaria V2.")
        if st.button(
            "Marcar como complete",
            icon=":material/task_alt:",
            type="primary",
            key=f"v2_complete_{boe_id}",
        ):
            try:
                mark_document_complete(truth_dir, boe_id, source_text=source_text)
            except (OSError, ValueError, TruthContractError) as error:
                st.error(str(error))
            else:
                _save_notice("Documento revalidado y marcado como complete en V2.")


truth_dir, source_dir = configured_paths()

st.title("Anotación humana ciega V2")
st.caption(
    "Contrato reducido previo al modelo: la interfaz no sugiere ni infiere entidades."
)

try:
    workspace = load_annotation_workspace(truth_dir, source_dir)
except (OSError, ValueError, TruthContractError) as error:
    st.error(f"No se pudo cargar el workspace V2: {error}")
    st.stop()

documents = workspace.truth.tables["documents"]
complete_count = int(documents["annotation_status"].astype(str).eq("complete").sum())
total_count = len(documents)

with st.sidebar:
    st.subheader("Navegación")
    st.progress(
        complete_count / total_count,
        text=f"{complete_count} complete / {total_count}",
    )
    status_filter = st.segmented_control(
        "Estado",
        ["Todos", "Draft", "Complete"],
        default="Todos",
        key="v2_status_filter",
    )
    filtered = documents
    if status_filter != "Todos":
        filtered = filtered.loc[
            filtered["annotation_status"].astype(str).eq(str(status_filter).lower())
        ]
    boe_options = filtered["identificador_boe"].astype(str).tolist()
    if not boe_options:
        st.warning("No hay documentos con este filtro.")
        st.stop()
    current = st.session_state.get("v2_current_boe")
    if current not in boe_options:
        current = boe_options[0]
    if st.session_state.get("v2_direct_boe") not in boe_options:
        st.session_state["v2_direct_boe"] = current
    selected_boe = st.selectbox("BOE", boe_options, key="v2_direct_boe")
    st.session_state["v2_current_boe"] = selected_boe
    selected_index = boe_options.index(selected_boe)
    with st.container(horizontal=True):
        st.button(
            "Anterior",
            icon=":material/arrow_back:",
            disabled=selected_index == 0,
            on_click=_navigate_to,
            args=(boe_options[max(selected_index - 1, 0)],),
        )
        st.button(
            "Siguiente",
            icon=":material/arrow_forward:",
            disabled=selected_index == len(boe_options) - 1,
            on_click=_navigate_to,
            args=(boe_options[min(selected_index + 1, len(boe_options) - 1)],),
        )
    st.divider()
    st.caption(f"Truth V2: `{workspace.truth_dir}`")
    st.caption(f"Source: `{workspace.source_path}`")

if notice := st.session_state.pop("v2_annotation_notice", None):
    st.success(str(notice))

source_row = workspace.source_documents.loc[
    workspace.source_documents["identificador"].astype(str).eq(selected_boe)
].iloc[0]
document_row = documents.loc[
    documents["identificador_boe"].astype(str).eq(selected_boe)
].iloc[0]
publication_date = (
    "No disponible"
    if pd.isna(source_row["fecha_publicacion"])
    else pd.Timestamp(source_row["fecha_publicacion"]).date().isoformat()
)
source_text = f"{source_row['titulo']}\n{source_row['texto_limpio']}"
is_exportable = str(document_row["annotation_status"]) == "complete"
review_package = (
    build_ai_qa_review_package(
        workspace.truth,
        selected_boe,
        title=str(source_row["titulo"]),
        publication_date=(
            None if publication_date == "No disponible" else publication_date
        ),
        source_text=str(source_row["texto_limpio"]),
    )
    if is_exportable
    else b""
)

st.subheader(str(source_row["titulo"]))
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(
        f"{selected_boe} · publicación {publication_date} · "
        f"estado {document_row['annotation_status']}"
    )
    st.link_button(
        "Abrir documento en BOE",
        build_official_boe_url(selected_boe),
        icon=":material/open_in_new:",
        help="El clic abre la fuente oficial; la aplicación no realiza la petición.",
    )
    st.download_button(
        "Descargar paquete para revisión IA",
        data=review_package,
        file_name=f"{selected_boe}_human_annotation_v2_review.md",
        mime="text/markdown",
        icon=":material/download:",
        disabled=not is_exportable,
        on_click="ignore",
    )
if not is_exportable:
    st.caption("Completa y valida primero la anotación humana V2.")

source_column, annotation_column = st.columns([1.05, 1], gap="large")
with source_column:
    st.text_area(
        "Texto completo de la fuente local",
        value=str(source_row["texto_limpio"]),
        height=760,
        disabled=True,
        key=f"v2_source_{selected_boe}",
    )
with annotation_column:
    st.subheader("1. Documento")
    _render_scope(workspace.truth_dir, workspace.truth, selected_boe, source_text)

    st.subheader("2. Eventos / proyectos publicados")
    _render_table_editor(
        workspace.truth_dir,
        workspace.truth,
        "events",
        selected_boe,
        source_text,
    )

    st.subheader("3. Activos de generación")
    event_rows = _frame_for_boe(workspace.truth, "events", selected_boe)
    if event_rows.empty:
        st.info(
            "No hay eventos. Añade primero un evento para poder registrar "
            "activos de generación."
        )
    else:
        _render_table_editor(
            workspace.truth_dir,
            workspace.truth,
            "generation_assets",
            selected_boe,
            source_text,
        )

    st.subheader("4. Actuaciones administrativas")
    asset_rows = _frame_for_boe(
        workspace.truth, "generation_assets", selected_boe
    )
    if asset_rows.empty:
        st.info(
            "No hay activos de generación. Añade primero un activo para poder "
            "registrar una actuación y seleccionar sus activos afectados."
        )
    else:
        _render_table_editor(
            workspace.truth_dir,
            workspace.truth,
            "administrative_actions",
            selected_boe,
            source_text,
        )

    st.subheader("5. Evidencias de actuaciones administrativas")
    st.caption(
        "Cada actuación primaria debe tener al menos un pasaje literal continuo "
        "del BOE que respalde esa actuación. Las evidencias de otros tipos de "
        "entidad son opcionales/diagnósticas en V2."
    )
    _render_action_evidence_workflow(
        workspace.truth_dir,
        workspace.truth,
        selected_boe,
        source_text,
    )

    st.subheader("6. Localizaciones")
    if event_rows.empty:
        st.info(
            "No hay eventos. Añade primero un evento para poder registrar "
            "localizaciones administrativas."
        )
    else:
        _render_table_editor(
            workspace.truth_dir,
            workspace.truth,
            "locations",
            selected_boe,
            source_text,
        )

    st.subheader("7. Validación y estado de anotación")
    _render_completion(workspace.truth_dir, selected_boe, source_text)

    with st.expander("8. Opcional / diagnóstico", expanded=False):
        st.caption(
            "Estos campos no son necesarios para completar el ground truth V2 "
            "y no forman parte del núcleo de métricas primarias."
        )
        secondary_table = st.selectbox(
            "Dimensión secundaria",
            SECONDARY_TABLES,
            format_func=lambda table: (
                "Evidencias de otras entidades"
                if table == "evidence_passages"
                else entity_label(table_entity(table))
            ),
            key=f"v2_secondary_table_{selected_boe}",
        )
        _render_table_editor(
            workspace.truth_dir,
            workspace.truth,
            secondary_table,
            selected_boe,
            source_text,
            action_evidence_only=False,
        )
