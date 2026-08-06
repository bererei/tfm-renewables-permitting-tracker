from __future__ import annotations

from typing import Any

import pandas as pd

from renewables_permitting.extraction.flat_contract import (
    FLAT_TABLE_COLUMNS,
    FLAT_TABLE_SPECS,
    apply_flat_table_types,
)
from renewables_permitting.extraction.models import BOEProjectExtraction
from renewables_permitting.extraction.paths import (
    ADMINISTRATIVE_ACTIONS_PATH,
    ADMINISTRATIVE_ACTION_TARGETS_PATH,
    ASSOCIATED_COMPONENTS_PATH,
    ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH,
    ASSOCIATED_COMPONENT_NAMES_PATH,
    CASE_FILE_REFERENCES_PATH,
    GENERATION_ASSET_MENTIONS_PATH,
    GENERATION_ASSET_NAMES_PATH,
    GENERATION_RELATIONS_PATH,
    LOCATION_MENTIONS_PATH,
    PARTICIPANT_MENTIONS_PATH,
    PUBLICATION_EVENTS_PATH,
    TECHNICAL_MENTIONS_PATH,
)
from renewables_permitting.extraction.persistence import save_parquet_atomic


def flatten_current_extractions(
    current_extractions: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Regenera tablas planas. Solo generation_asset_mentions es agrupable."""

    rows: dict[str, list[dict[str, Any]]] = {
        table_name: [] for table_name in FLAT_TABLE_SPECS
    }

    for extraction_row in current_extractions.itertuples(index=False):
        extraction = BOEProjectExtraction.model_validate_json(
            str(extraction_row.extraction_json)
        )
        for event_index, event in enumerate(extraction.publication_events, start=1):
            event_id = f"{extraction.boe_id}_event_{event_index}"
            base = {
                "event_id": event_id,
                "identificador_boe": extraction.boe_id,
                "fecha_publicacion": pd.Timestamp(extraction.publication_date),
            }
            rows["publication_events"].append({
                **base,
                "event_index": event_index,
                "event_summary": event.event_summary,
                "n_generation_assets": len(event.generation_assets),
                "n_associated_components": len(event.associated_components),
                "n_administrative_actions": len(event.administrative_actions),
            })

            for asset_index, asset in enumerate(event.generation_assets, start=1):
                mention_id = f"{event_id}_generation_asset_{asset_index}"
                rows["generation_asset_mentions"].append({
                    **base,
                    "generation_asset_mention_id": mention_id,
                    "local_generation_asset_ref": asset.local_generation_asset_ref,
                    "generation_type": asset.generation_type.value,
                    "evidence": asset.evidence,
                })
                for name_index, name in enumerate(asset.names_raw, start=1):
                    rows["generation_asset_names"].append({
                        **base,
                        "generation_asset_mention_id": mention_id,
                        "name_index": name_index,
                        "name_raw": name,
                    })
                for technical_index, mention in enumerate(
                    asset.technical_mentions, start=1
                ):
                    rows["technical_mentions"].append({
                        **base,
                        "technical_mention_id": f"{mention_id}_technical_{technical_index}",
                        "owner_kind": "generation_asset",
                        "owner_ref": asset.local_generation_asset_ref,
                        "generation_asset_mention_id": mention_id,
                        "associated_component_id": None,
                        "attribute_type": mention.attribute_type.value,
                        "value_raw": mention.value_raw,
                        "evidence": mention.evidence,
                    })

            for component_index, component in enumerate(
                event.associated_components, start=1
            ):
                component_id = f"{event_id}_component_{component_index}"
                rows["associated_components"].append({
                    **base,
                    "associated_component_id": component_id,
                    "local_component_ref": component.local_component_ref,
                    "component_type": component.component_type.value,
                    "description_raw": component.description_raw,
                    "evidence": component.evidence,
                })
                for name_index, name in enumerate(component.names_raw, start=1):
                    rows["associated_component_names"].append({
                        **base,
                        "associated_component_id": component_id,
                        "name_index": name_index,
                        "name_raw": name,
                    })
                for link_index, generation_ref in enumerate(
                    component.related_generation_asset_refs,
                    start=1,
                ):
                    rows["associated_component_generation_links"].append({
                        **base,
                        "associated_component_id": component_id,
                        "link_index": link_index,
                        "local_generation_asset_ref": generation_ref,
                        "generation_asset_mention_id": (
                            f"{event_id}_{generation_ref}"
                        ),
                    })
                for technical_index, mention in enumerate(
                    component.technical_mentions, start=1
                ):
                    rows["technical_mentions"].append({
                        **base,
                        "technical_mention_id": f"{component_id}_technical_{technical_index}",
                        "owner_kind": "associated_component",
                        "owner_ref": component.local_component_ref,
                        "generation_asset_mention_id": None,
                        "associated_component_id": component_id,
                        "attribute_type": mention.attribute_type.value,
                        "value_raw": mention.value_raw,
                        "evidence": mention.evidence,
                    })

            for action_index, action in enumerate(
                event.administrative_actions, start=1
            ):
                action_id = f"{event_id}_action_{action_index}"
                rows["administrative_actions"].append({
                    **base,
                    "administrative_action_id": action_id,
                    "action_index": action_index,
                    "action_type": action.action_type.value,
                    "decision": action.decision.value,
                    "is_modification": action.is_modification,
                    "evidence": action.evidence,
                })
                for target_index, target_ref in enumerate(action.targets, start=1):
                    rows["administrative_action_targets"].append({
                        **base,
                        "administrative_action_id": action_id,
                        "target_index": target_index,
                        "target_ref": target_ref,
                        "target_entity_id": (
                            event_id
                            if target_ref == "event"
                            else f"{event_id}_{target_ref}"
                        ),
                        "target_kind": (
                            "event"
                            if target_ref == "event"
                            else "generation_asset"
                            if target_ref.startswith("generation_asset_")
                            else "associated_component"
                        ),
                    })

            for participant_index, participant in enumerate(
                event.participants, start=1
            ):
                participant_id = f"{event_id}_participant_{participant_index}"
                rows["participant_mentions"].append({
                    **base,
                    "participant_mention_id": participant_id,
                    "participant_name_raw": participant.participant_name_raw,
                    "participant_role": participant.participant_role.value,
                    "evidence": participant.evidence,
                })
            for location_index, location in enumerate(
                event.administrative_locations, start=1
            ):
                location_id = f"{event_id}_location_{location_index}"
                rows["location_mentions"].append({
                    **base,
                    "location_mention_id": location_id,
                    "location_name_raw": location.location_name_raw,
                    "location_level": location.location_level.value,
                    "province_hint_raw": location.province_hint_raw,
                    "autonomous_community_hint_raw": location.autonomous_community_hint_raw,
                    "evidence": location.evidence,
                })
            for relation_index, relation in enumerate(
                event.generation_relations, start=1
            ):
                rows["generation_asset_relations"].append({
                    **base,
                    "generation_asset_relation_id": f"{event_id}_relation_{relation_index}",
                    "source_generation_asset_ref": relation.source_generation_asset_ref,
                    "source_generation_asset_mention_id": (
                        f"{event_id}_{relation.source_generation_asset_ref}"
                    ),
                    "target_generation_asset_ref": relation.target_generation_asset_ref,
                    "target_generation_asset_mention_id": (
                        f"{event_id}_{relation.target_generation_asset_ref}"
                    ),
                    "relation_type": relation.relation_type.value,
                    "evidence": relation.evidence,
                })

            for reference_index, reference in enumerate(
                event.case_file_references, start=1
            ):
                rows["case_file_references"].append({
                    **base,
                    "case_file_reference_id": f"{event_id}_case_file_{reference_index}",
                    "reference_index": reference_index,
                    "case_file_reference_raw": reference,
                })

    tables = {
        table_name: pd.DataFrame(
            table_rows,
            columns=FLAT_TABLE_COLUMNS[table_name],
        )
        for table_name, table_rows in rows.items()
    }
    return apply_flat_table_types(tables)


def save_flattened_extractions(
    current_extractions: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    tables = flatten_current_extractions(current_extractions)
    paths = {
        "publication_events": PUBLICATION_EVENTS_PATH,
        "generation_asset_mentions": GENERATION_ASSET_MENTIONS_PATH,
        "generation_asset_names": GENERATION_ASSET_NAMES_PATH,
        "associated_components": ASSOCIATED_COMPONENTS_PATH,
        "associated_component_names": ASSOCIATED_COMPONENT_NAMES_PATH,
        "associated_component_generation_links": (
            ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH
        ),
        "administrative_actions": ADMINISTRATIVE_ACTIONS_PATH,
        "administrative_action_targets": ADMINISTRATIVE_ACTION_TARGETS_PATH,
        "participant_mentions": PARTICIPANT_MENTIONS_PATH,
        "location_mentions": LOCATION_MENTIONS_PATH,
        "generation_asset_relations": GENERATION_RELATIONS_PATH,
        "technical_mentions": TECHNICAL_MENTIONS_PATH,
        "case_file_references": CASE_FILE_REFERENCES_PATH,
    }
    for name, dataframe in tables.items():
        save_parquet_atomic(dataframe, paths[name])
    return tables
