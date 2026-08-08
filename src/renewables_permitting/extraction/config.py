from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Literal

from renewables_permitting.extraction.instructions import AGENT_INSTRUCTIONS
from renewables_permitting.extraction.models import BOEAIExtraction


ModelProvider = Literal["gemini", "ollama"]

MODEL_PROVIDER: ModelProvider = "gemini"
# MODEL_PROVIDER: ModelProvider = "ollama"
AI_MODEL_NAME = "google:gemini-2.5-flash"
AGENT_RETRIES = 3
USE_NATIVE_OUTPUT = True
MODEL_SETTINGS: dict[str, Any] = {"temperature": 0.0}

if MODEL_PROVIDER == "ollama":
    AI_MODEL_NAME = "qwen3:8b"
    AGENT_RETRIES = 4

DOCUMENT_TIMEOUT_SECONDS = 600.0
MODEL_RUN_TIMEOUT_SECONDS = 240.0
MAX_MODEL_REQUESTS_PER_DOCUMENT = 6
DOCUMENT_VALIDATION_RETRY_ATTEMPTS = 1
TRANSIENT_RUN_ATTEMPTS = 2
TRANSIENT_RETRY_BASE_SECONDS = 2.0
CHECKPOINT_EVERY = 5

DOCUMENT_VALIDATION_VERSION = "25"
_CANONICALIZATION_POLICY = (
    "termination_object_filter_environmental_terminal_whitelist_"
    "lexical_authorization_grants_v2"
)
ENTITY_MODEL_POLICY = "generation_roots_components_event_targets_v3"
EVENT_GRANULARITY_POLICY = "canonical_split_independent_generation_projects_v3"
TEMPORAL_POLICY = "current_publication_object_only_v2"
DOCUMENTARY_MATCH_POLICY = "generation_titles_and_exact_source_spans_v5"
TARGET_SEMANTICS_POLICY = "contextual_entity_targets_v2"
COMPONENT_LINK_POLICY = "contextual_links_not_same_quote_required_v1"
QUALITY_WORKFLOW_POLICY = "auto_review_manual_precedence_v2"
SCOPE_CLASSIFICATION_POLICY = "binary_named_generation_pre_model_guard_v3"


def _stable_json_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


CONTRACT_SCHEMA_SHA256 = _stable_json_hash(BOEAIExtraction.model_json_schema())
INSTRUCTIONS_SHA256 = sha256(AGENT_INSTRUCTIONS.encode("utf-8")).hexdigest()
EXTRACTION_CONFIG = {
    "model_provider": MODEL_PROVIDER,
    "model_name": AI_MODEL_NAME,
    "agent_retries": AGENT_RETRIES,
    "use_native_output": USE_NATIVE_OUTPUT,
    "model_settings": MODEL_SETTINGS,
    "document_validation_version": DOCUMENT_VALIDATION_VERSION,
    "model_run_timeout_seconds": MODEL_RUN_TIMEOUT_SECONDS,
    "canonicalization_policy": _CANONICALIZATION_POLICY,
    "entity_model_policy": ENTITY_MODEL_POLICY,
    "event_granularity_policy": EVENT_GRANULARITY_POLICY,
    "temporal_policy": TEMPORAL_POLICY,
    "documentary_match_policy": DOCUMENTARY_MATCH_POLICY,
    "target_semantics_policy": TARGET_SEMANTICS_POLICY,
    "component_link_policy": COMPONENT_LINK_POLICY,
    "quality_workflow_policy": QUALITY_WORKFLOW_POLICY,
    "scope_classification_policy": SCOPE_CLASSIFICATION_POLICY,
    "contract_schema_sha256": CONTRACT_SCHEMA_SHA256,
    "instructions_sha256": INSTRUCTIONS_SHA256,
}
EXTRACTION_CONFIG_ID = _stable_json_hash(EXTRACTION_CONFIG)[:16]
