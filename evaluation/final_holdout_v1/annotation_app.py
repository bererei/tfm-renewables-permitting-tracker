from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

# Streamlit executes a file entrypoint with the script directory on sys.path.
# Add this repository root so the evaluation namespace remains importable when
# launched through the documented root-relative command.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

import pandas as pd
import streamlit as st

from evaluation.final_holdout_v1.annotation import (
    EntityChoice,
    aliases_for_edit,
    build_ai_qa_review_package,
    build_official_boe_url,
    configured_paths,
    delete_truth_row,
    derive_entity_reference,
    entity_choices,
    load_annotation_workspace,
    mark_document_complete,
    next_key_for_table,
    serialize_aliases,
    serialize_key_selection,
    update_document_scope,
    upsert_truth_row,
    validate_document,
    validate_evidence_literal,
)
from evaluation.final_holdout_v1.contract import (
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


TABLE_LABELS = {
    "events": "Eventos",
    "generation_assets": "Activos de generación",
    "associated_components": "Componentes asociados",
    "technical_mentions": "Menciones técnicas",
    "administrative_actions": "Actuaciones administrativas",
    "action_targets": "Objetivos de actuaciones",
    "participants": "Participantes",
    "locations": "Localizaciones",
    "evidence_passages": "Pasajes de evidencia",
}


st.set_page_config(
    page_title="Anotación humana ciega",
    page_icon=":material/fact_check:",
    layout="wide",
)


def _domain_options(domain: Sequence[str] | set[str], *, allow_na: bool = False) -> list[str]:
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
    label: str,
    domain: Sequence[str] | set[str],
    *,
    current: object | None,
    key: str,
    allow_na: bool = False,
) -> str | None:
    options = _domain_options(domain, allow_na=allow_na)
    return st.selectbox(
        label,
        options,
        index=_index_or_none(options, current),
        placeholder="Selecciona una opción del contrato",
        key=key,
    )


def _required(value: str | None, label: str) -> str:
    if value is None:
        raise TruthContractError(f"Selecciona {label}.")
    return str(value)


def _explicit_text(value: str) -> str:
    return str(value).strip() or NA


def _notes_for_edit(value: object | None) -> str:
    return "" if value is None or str(value) == NA else str(value)


def _common_fields(
    row: Mapping[str, object] | None,
    *,
    key_prefix: str,
) -> tuple[str | None, str | None, str]:
    applicability = _select_domain(
        "Aplicabilidad",
        APPLICABILITY,
        current=None if row is None else row["applicability"],
        key=f"{key_prefix}_applicability",
    )
    adjudication = _select_domain(
        "Adjudicación",
        ADJUDICATION,
        current=None if row is None else row["adjudication"],
        key=f"{key_prefix}_adjudication",
    )
    notes = st.text_area(
        "Notas de anotación",
        value=_notes_for_edit(None if row is None else row["annotation_notes"]),
        key=f"{key_prefix}_notes",
    )
    return applicability, adjudication, notes


def _entity_row_options(frame: pd.DataFrame, table: str) -> tuple[list[str], dict[str, int]]:
    key_columns = [
        column
        for column in TABLE_SPECS[table].key_columns
        if column != "identificador_boe"
    ]
    labels: list[str] = []
    positions: dict[str, int] = {}
    for index, (_, row) in enumerate(frame.iterrows()):
        label = " · ".join(f"{column}={row[column]}" for column in key_columns)
        labels.append(label)
        positions[label] = index
    return labels, positions


def _original_key(table: str, row: Mapping[str, object]) -> dict[str, str]:
    return {
        column: str(row[column])
        for column in TABLE_SPECS[table].key_columns
        if column != "identificador_boe"
    }


def _display_rows(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("Todavía no hay filas para este BOE.")
        return
    visible = frame.drop(columns=["identificador_boe"]).copy()
    for column in ("names_json", "related_asset_keys_json"):
        if column in visible.columns:
            visible[column] = visible[column].map(
                lambda value: "\n".join(json.loads(str(value)))
            )
    st.dataframe(visible, hide_index=True, height="content")


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
        placeholder="Selecciona una entidad existente",
        key=key,
    )


def _event_select(
    truth: TruthArtifact,
    boe_id: str,
    *,
    current: str | None,
    key: str,
) -> str | None:
    events = truth.tables["events"]
    events = events.loc[events["identificador_boe"].astype(str).eq(boe_id)]
    values = events["event_key"].astype(str).tolist()
    labels = {
        str(row["event_key"]): f"{row['event_key']} · {row['event_label']}"
        for _, row in events.iterrows()
    }
    return st.selectbox(
        "Evento",
        values,
        index=_index_or_none(values, current),
        format_func=lambda value: labels[value],
        placeholder="Selecciona un evento existente",
        key=key,
    )


def _action_select(
    truth: TruthArtifact,
    boe_id: str,
    *,
    current: str | None,
    key: str,
) -> str | None:
    actions = truth.tables["administrative_actions"]
    actions = actions.loc[actions["identificador_boe"].astype(str).eq(boe_id)]
    values = actions["action_key"].astype(str).tolist()
    labels = {
        str(row["action_key"]): (
            f"{row['event_key']} · {row['action_key']} · {row['expected_action_type']}"
        )
        for _, row in actions.iterrows()
    }
    return st.selectbox(
        "Actuación",
        values,
        index=_index_or_none(values, current),
        format_func=lambda value: labels[value],
        placeholder="Selecciona una actuación existente",
        key=key,
    )


def _asset_options(truth: TruthArtifact, boe_id: str) -> tuple[list[str], dict[str, str]]:
    assets = truth.tables["generation_assets"]
    assets = assets.loc[assets["identificador_boe"].astype(str).eq(boe_id)]
    values = assets["asset_key"].astype(str).tolist()
    labels = {
        str(row["asset_key"]): f"{row['event_key']} · {row['asset_key']} · {row['names_json']}"
        for _, row in assets.iterrows()
    }
    return values, labels


def _save_notice(message: str) -> None:
    st.session_state["annotation_notice"] = message
    st.rerun()


def _navigate_to(boe_id: str) -> None:
    st.session_state["current_annotation_boe"] = boe_id
    st.session_state["direct_boe_selection"] = boe_id


def _render_delete(
    truth_dir: Path,
    truth: TruthArtifact,
    table: str,
    boe_id: str,
    frame: pd.DataFrame,
    source_text: str,
) -> None:
    labels, positions = _entity_row_options(frame, table)
    selected = st.selectbox("Fila que se eliminará", labels, key=f"delete_{table}_{boe_id}")
    selected_row = frame.iloc[positions[selected]].to_dict()
    with st.form(f"delete_form_{table}_{boe_id}"):
        confirmed = st.checkbox("Confirmo la eliminación de esta fila")
        submitted = st.form_submit_button(
            "Eliminar fila", icon=":material/delete:", type="primary"
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
                _original_key(table, selected_row),
                source_text=source_text,
            )
        except (OSError, ValueError, TruthContractError) as error:
            st.error(str(error))
        else:
            _save_notice(f"Fila eliminada de {TABLE_LABELS[table]}.")


def _render_entity_form(
    truth_dir: Path,
    truth: TruthArtifact,
    table: str,
    boe_id: str,
    frame: pd.DataFrame,
    mode: str,
    source_text: str,
) -> None:
    row: dict[str, object] | None = None
    if mode == "Editar":
        labels, positions = _entity_row_options(frame, table)
        selected = st.selectbox(
            "Fila que se editará", labels, key=f"edit_{table}_{boe_id}"
        )
        row = frame.iloc[positions[selected]].to_dict()

    key_prefix = f"{mode}_{table}_{boe_id}"
    generated_key = (
        next_key_for_table(truth, table, boe_id)
        if mode == "Añadir" and table in {
            "events",
            "generation_assets",
            "associated_components",
            "technical_mentions",
            "administrative_actions",
            "participants",
            "locations",
        }
        else None
    )
    if generated_key is not None:
        st.caption(f"Clave local generada al guardar: `{generated_key}`")

    with st.form(f"entity_form_{key_prefix}", enter_to_submit=False):
        values: dict[str, object] = {}
        if table == "events":
            values["event_key"] = generated_key or str(row["event_key"])
            values["event_label"] = st.text_input(
                "Etiqueta humana del evento",
                value="" if row is None else str(row["event_label"]),
            )

        elif table == "generation_assets":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
            )
            values["asset_key"] = generated_key or str(row["asset_key"])
            values["aliases"] = st.text_area(
                "Alias literales, uno por línea",
                value="" if row is None else aliases_for_edit(str(row["names_json"])),
            )
            values["expected_generation_type"] = _select_domain(
                "Tipo de generación",
                GENERATION_TYPES,
                current=None if row is None else row["expected_generation_type"],
                allow_na=True,
                key=f"{key_prefix}_generation_type",
            )

        elif table == "associated_components":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
            )
            values["component_key"] = generated_key or str(row["component_key"])
            values["aliases"] = st.text_area(
                "Nombres literales, uno por línea (opcional)",
                value="" if row is None else aliases_for_edit(str(row["names_json"])),
            )
            values["description_raw"] = st.text_area(
                "Descripción literal (obligatoria si no hay nombre)",
                value=(
                    ""
                    if row is None or str(row["description_raw"]) == NA
                    else str(row["description_raw"])
                ),
            )
            values["expected_component_type"] = _select_domain(
                "Tipo de componente",
                COMPONENT_TYPES,
                current=None if row is None else row["expected_component_type"],
                allow_na=True,
                key=f"{key_prefix}_component_type",
            )
            asset_values, asset_labels = _asset_options(truth, boe_id)
            current_assets = (
                [] if row is None else json.loads(str(row["related_asset_keys_json"]))
            )
            values["related_assets"] = st.multiselect(
                "Activos de generación relacionados",
                asset_values,
                default=current_assets,
                format_func=lambda value: asset_labels[value],
            )

        elif table == "technical_mentions":
            owners = entity_choices(truth, boe_id, purpose="technical_owner")
            values["owner"] = _choice_select(
                "Entidad propietaria",
                owners,
                current_type=None if row is None else str(row["owner_type"]),
                current_key=None if row is None else str(row["owner_key"]),
                key=f"{key_prefix}_owner",
            )
            values["technical_key"] = generated_key or str(row["technical_key"])
            values["expected_attribute_type"] = _select_domain(
                "Tipo de atributo técnico",
                TECHNICAL_ATTRIBUTE_TYPES,
                current=None if row is None else row["expected_attribute_type"],
                allow_na=True,
                key=f"{key_prefix}_attribute_type",
            )
            values["expected_value_raw"] = st.text_input(
                "Valor literal",
                value="" if row is None else str(row["expected_value_raw"]),
            )

        elif table == "administrative_actions":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
            )
            values["action_key"] = generated_key or str(row["action_key"])
            values["expected_action_type"] = _select_domain(
                "Tipo de actuación",
                ACTION_TYPES,
                current=None if row is None else row["expected_action_type"],
                allow_na=True,
                key=f"{key_prefix}_action_type",
            )
            values["expected_decision"] = _select_domain(
                "Decisión",
                DECISIONS,
                current=None if row is None else row["expected_decision"],
                allow_na=True,
                key=f"{key_prefix}_decision",
            )
            values["expected_is_modification"] = _select_domain(
                "¿Es modificación?",
                {"true", "false"},
                current=None if row is None else row["expected_is_modification"],
                allow_na=True,
                key=f"{key_prefix}_modification",
            )
            values["temporal_status"] = _select_domain(
                "Estado temporal",
                TEMPORAL_STATUSES,
                current=None if row is None else row["temporal_status"],
                key=f"{key_prefix}_temporal_status",
            )

        elif table == "action_targets":
            values["action_key"] = _action_select(
                truth,
                boe_id,
                current=None if row is None else str(row["action_key"]),
                key=f"{key_prefix}_action",
            )
            targets = entity_choices(truth, boe_id, purpose="action_target")
            values["target"] = _choice_select(
                "Entidad objetivo",
                targets,
                current_type=None if row is None else str(row["target_type"]),
                current_key=None if row is None else str(row["target_truth_key"]),
                key=f"{key_prefix}_target",
            )

        elif table == "participants":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
            )
            values["participant_key"] = generated_key or str(row["participant_key"])
            values["participant_name_raw"] = st.text_input(
                "Nombre literal del participante",
                value="" if row is None else str(row["participant_name_raw"]),
            )
            values["expected_participant_role"] = _select_domain(
                "Rol",
                PARTICIPANT_ROLES,
                current=None if row is None else row["expected_participant_role"],
                allow_na=True,
                key=f"{key_prefix}_participant_role",
            )

        elif table == "locations":
            values["event_key"] = _event_select(
                truth,
                boe_id,
                current=None if row is None else str(row["event_key"]),
                key=f"{key_prefix}_event",
            )
            values["location_key"] = generated_key or str(row["location_key"])
            values["location_name_raw"] = st.text_input(
                "Localización literal",
                value="" if row is None else str(row["location_name_raw"]),
            )
            values["expected_location_level"] = _select_domain(
                "Nivel territorial",
                LOCATION_LEVELS,
                current=None if row is None else row["expected_location_level"],
                allow_na=True,
                key=f"{key_prefix}_location_level",
            )

        elif table == "evidence_passages":
            owners = entity_choices(truth, boe_id, purpose="evidence_owner")
            values["owner"] = _choice_select(
                "Entidad respaldada",
                owners,
                current_type=None if row is None else str(row["owner_type"]),
                current_key=None if row is None else str(row["owner_key"]),
                key=f"{key_prefix}_evidence_owner",
            )
            values["passage_text"] = st.text_area(
                "Pasaje continuo copiado literalmente",
                value="" if row is None else str(row["passage_text"]),
                height=160,
            )

        applicability, adjudication, notes = _common_fields(row, key_prefix=key_prefix)
        submitted = st.form_submit_button(
            "Guardar fila", icon=":material/save:", type="primary"
        )

    if not submitted:
        return
    try:
        entity_row: dict[str, str] = {
            "identificador_boe": boe_id,
            "annotation_notes": _explicit_text(notes),
            "applicability": _required(applicability, "la aplicabilidad"),
            "adjudication": _required(adjudication, "la adjudicación"),
        }
        if table == "events":
            entity_row.update(
                event_key=str(values["event_key"]),
                event_label=_explicit_text(str(values["event_label"])),
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
        elif table == "associated_components":
            alias_lines = [
                line.strip()
                for line in str(values["aliases"]).splitlines()
                if line.strip()
            ]
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                component_key=str(values["component_key"]),
                names_json=serialize_key_selection(alias_lines),
                description_raw=_explicit_text(str(values["description_raw"])),
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
                expected_value_raw=_explicit_text(str(values["expected_value_raw"])),
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
                    values["temporal_status"], "el estado temporal"
                ),
            )
        elif table == "action_targets":
            action_key = _required(values["action_key"], "la actuación")
            actions = truth.tables["administrative_actions"]
            action = actions.loc[
                actions["identificador_boe"].astype(str).eq(boe_id)
                & actions["action_key"].astype(str).eq(action_key)
            ].iloc[0]
            targets = entity_choices(truth, boe_id, purpose="action_target")
            target_type, target_key = derive_entity_reference(
                _required(values["target"], "la entidad objetivo"), targets
            )
            entity_row.update(
                event_key=str(action["event_key"]),
                action_key=action_key,
                target_type=target_type,
                target_truth_key=target_key,
            )
        elif table == "participants":
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                participant_key=str(values["participant_key"]),
                participant_name_raw=_explicit_text(
                    str(values["participant_name_raw"])
                ),
                expected_participant_role=_required(
                    values["expected_participant_role"], "el rol"
                ),
            )
        elif table == "locations":
            entity_row.update(
                event_key=_required(values["event_key"], "el evento"),
                location_key=str(values["location_key"]),
                location_name_raw=_explicit_text(str(values["location_name_raw"])),
                expected_location_level=_required(
                    values["expected_location_level"], "el nivel territorial"
                ),
            )
        elif table == "evidence_passages":
            owners = entity_choices(truth, boe_id, purpose="evidence_owner")
            owner_type, owner_key = derive_entity_reference(
                _required(values["owner"], "la entidad respaldada"), owners
            )
            entity_row.update(
                owner_type=owner_type,
                owner_key=owner_key,
                passage_text=validate_evidence_literal(
                    str(values["passage_text"]), source_text
                ),
            )
        else:
            raise AssertionError(f"Tabla no gestionada: {table}")

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
        _save_notice(f"Fila guardada en {TABLE_LABELS[table]}.")


def _render_entity_editor(
    truth_dir: Path,
    truth: TruthArtifact,
    boe_id: str,
    source_text: str,
) -> None:
    st.subheader("Entidades anotadas")
    table = st.selectbox(
        "Tabla de verdad",
        list(TABLE_LABELS),
        format_func=lambda value: TABLE_LABELS[value],
        key=f"annotation_table_{boe_id}",
    )
    frame = truth.tables[table]
    frame = frame.loc[frame["identificador_boe"].astype(str).eq(boe_id)].copy()
    _display_rows(frame)

    modes = ["Añadir"] if frame.empty else ["Añadir", "Editar", "Eliminar"]
    mode = st.segmented_control(
        "Operación",
        modes,
        default=modes[0],
        key=f"annotation_mode_{table}_{boe_id}",
    )
    if mode == "Eliminar":
        _render_delete(truth_dir, truth, table, boe_id, frame, source_text)
    else:
        _render_entity_form(
            truth_dir,
            truth,
            table,
            boe_id,
            frame,
            str(mode),
            source_text,
        )


def _render_scope_editor(
    truth_dir: Path,
    truth: TruthArtifact,
    boe_id: str,
    source_text: str,
) -> None:
    document = truth.tables["documents"].loc[
        truth.tables["documents"]["identificador_boe"].astype(str).eq(boe_id)
    ].iloc[0]
    st.subheader("Alcance documental")
    with st.form(f"document_scope_{boe_id}"):
        applicability = _select_domain(
            "scope_applicability",
            APPLICABILITY,
            current=document["scope_applicability"],
            key=f"scope_applicability_{boe_id}",
        )
        adjudication = _select_domain(
            "scope_adjudication",
            ADJUDICATION,
            current=document["scope_adjudication"],
            key=f"scope_adjudication_{boe_id}",
        )
        expected_scope = _select_domain(
            "expected_document_scope",
            DOCUMENT_SCOPES,
            current=document["expected_document_scope"],
            allow_na=True,
            key=f"expected_document_scope_{boe_id}",
        )
        notes = st.text_area(
            "annotation_notes",
            value=_notes_for_edit(document["annotation_notes"]),
        )
        submitted = st.form_submit_button(
            "Guardar alcance", icon=":material/save:", type="primary"
        )
    if submitted:
        try:
            update_document_scope(
                truth_dir,
                boe_id,
                scope_applicability=_required(applicability, "scope_applicability"),
                scope_adjudication=_required(adjudication, "scope_adjudication"),
                expected_document_scope=_required(
                    expected_scope, "expected_document_scope"
                ),
                annotation_notes=notes,
                source_text=source_text,
            )
        except (OSError, ValueError, TruthContractError) as error:
            st.error(str(error))
        else:
            _save_notice("Alcance documental guardado.")

    with st.container(horizontal=True):
        if st.button(
            "Validar documento",
            icon=":material/rule:",
            key=f"validate_document_{boe_id}",
        ):
            try:
                validate_document(truth_dir, boe_id, source_text=source_text)
            except (OSError, ValueError, TruthContractError) as error:
                st.error(str(error))
            else:
                st.success("El documento satisface las restricciones de completitud.")
        if st.button(
            "Marcar como complete",
            icon=":material/task_alt:",
            type="primary",
            key=f"mark_complete_{boe_id}",
        ):
            try:
                mark_document_complete(
                    truth_dir,
                    boe_id,
                    source_text=source_text,
                )
            except (OSError, ValueError, TruthContractError) as error:
                st.error(str(error))
            else:
                _save_notice("Documento validado y marcado como complete.")


truth_dir, source_dir = configured_paths()

st.title("Anotación humana ciega")
st.caption(
    "Primera pasada exclusivamente humana: la interfaz no sugiere ni infiere entidades."
)

try:
    workspace = load_annotation_workspace(truth_dir, source_dir)
except (OSError, ValueError, TruthContractError) as error:
    st.error(f"No se pudo cargar el workspace de anotación: {error}")
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
        key="annotation_status_filter",
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
    current = st.session_state.get("current_annotation_boe")
    if current not in boe_options:
        current = boe_options[0]
    if st.session_state.get("direct_boe_selection") not in boe_options:
        st.session_state["direct_boe_selection"] = current
    selected_boe = st.selectbox(
        "BOE",
        boe_options,
        key="direct_boe_selection",
    )
    st.session_state["current_annotation_boe"] = selected_boe
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
    st.caption(f"Truth: `{workspace.truth_dir}`")
    st.caption(f"Source: `{workspace.source_path}`")

if notice := st.session_state.pop("annotation_notice", None):
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
official_boe_url = build_official_boe_url(selected_boe)
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
        official_boe_url,
        icon=":material/open_in_new:",
        help=(
            "Abre la publicación oficial en una pestaña nueva; el texto local "
            "sigue siendo la fuente usada por la anotación."
        ),
    )
    st.download_button(
        "Descargar paquete para revisión IA",
        data=review_package,
        file_name=f"{selected_boe}_human_annotation_review.md",
        mime="text/markdown",
        icon=":material/download:",
        disabled=not is_exportable,
        on_click="ignore",
    )
if not is_exportable:
    st.caption("Completa y valida primero la anotación humana.")

source_column, annotation_column = st.columns([1.15, 1], gap="large")
with source_column:
    st.text_area(
        "Texto completo de la fuente",
        value=str(source_row["texto_limpio"]),
        height=720,
        disabled=True,
        key=f"source_text_{selected_boe}",
    )
with annotation_column:
    scope_tab, entities_tab = st.tabs(["Alcance", "Entidades"])
    with scope_tab:
        _render_scope_editor(
            workspace.truth_dir,
            workspace.truth,
            selected_boe,
            source_text,
        )
    with entities_tab:
        _render_entity_editor(
            workspace.truth_dir,
            workspace.truth,
            selected_boe,
            source_text,
        )
