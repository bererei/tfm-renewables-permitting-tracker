import ast
import builtins
import socket
from hashlib import sha256
from pathlib import Path
from typing import get_args, get_type_hints

import renewables_permitting.extraction.config as config_module
import renewables_permitting.extraction.review as review_module
from renewables_permitting.extraction.config import (
    AGENT_RETRIES,
    AI_MODEL_NAME,
    CHECKPOINT_EVERY,
    COMPONENT_LINK_POLICY,
    CONTRACT_SCHEMA_SHA256,
    DOCUMENT_TIMEOUT_SECONDS,
    DOCUMENT_VALIDATION_RETRY_ATTEMPTS,
    DOCUMENT_VALIDATION_VERSION,
    DOCUMENTARY_MATCH_POLICY,
    ENTITY_MODEL_POLICY,
    EVENT_GRANULARITY_POLICY,
    EXTRACTION_CONFIG,
    EXTRACTION_CONFIG_ID,
    INSTRUCTIONS_SHA256,
    MAX_MODEL_REQUESTS_PER_DOCUMENT,
    MODEL_PROVIDER,
    MODEL_RUN_TIMEOUT_SECONDS,
    MODEL_SETTINGS,
    QUALITY_WORKFLOW_POLICY,
    SCOPE_CLASSIFICATION_POLICY,
    TARGET_SEMANTICS_POLICY,
    TEMPORAL_POLICY,
    TRANSIENT_RETRY_BASE_SECONDS,
    TRANSIENT_RUN_ATTEMPTS,
    USE_NATIVE_OUTPUT,
    ModelProvider,
    _stable_json_hash,
)
from renewables_permitting.extraction.instructions import AGENT_INSTRUCTIONS
from renewables_permitting.extraction.models import BOEAIExtraction


EXPECTED_CONTRACT_SCHEMA_SHA256 = (
    "7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c"
)
EXPECTED_INSTRUCTIONS_SHA256 = (
    "b48240832d1b274af0435cea42cc6d305d2aec83b5a3395a1d5ce1529eff0607"
)
EXPECTED_EXTRACTION_CONFIG_ID = "00303cf56466f39d"
PRE_LIMITED_REOPEN_CONTRACT_SCHEMA_SHA256 = (
    "455028c7de0ada067264cd695b4e7dab9de377b31105e141321313d61c3ff283"
)
PRE_LIMITED_REOPEN_EXTRACTION_CONFIG_ID = "67a0bd9d0759a322"


def _top_level_nodes(source: str) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            nodes[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node
    return nodes


def test_model_provider_and_all_configuration_values_are_exact() -> None:
    assert get_args(ModelProvider) == ("gemini", "ollama")
    assert MODEL_PROVIDER == "gemini"
    assert AI_MODEL_NAME == "google:gemini-2.5-flash"
    assert AGENT_RETRIES == 3
    assert USE_NATIVE_OUTPUT is True
    assert MODEL_SETTINGS == {"temperature": 0.0}
    assert DOCUMENT_TIMEOUT_SECONDS == 600.0
    assert MODEL_RUN_TIMEOUT_SECONDS == 240.0
    assert MAX_MODEL_REQUESTS_PER_DOCUMENT == 6
    assert DOCUMENT_VALIDATION_RETRY_ATTEMPTS == 1
    assert TRANSIENT_RUN_ATTEMPTS == 2
    assert TRANSIENT_RETRY_BASE_SECONDS == 2.0
    assert CHECKPOINT_EVERY == 5
    assert DOCUMENT_VALIDATION_VERSION == "25"
    assert config_module._CANONICALIZATION_POLICY == (
        "termination_object_filter_environmental_terminal_whitelist_"
        "lexical_authorization_decisions_v3_"
        "explicit_relation_validation_conservative_grouping_v1"
    )
    assert ENTITY_MODEL_POLICY == (
        "generation_roots_components_event_targets_v3"
    )
    assert EVENT_GRANULARITY_POLICY == (
        "canonical_split_independent_generation_projects_v3"
    )
    assert TEMPORAL_POLICY == "current_publication_object_only_v2"
    assert DOCUMENTARY_MATCH_POLICY == (
        "generation_titles_and_exact_source_spans_v5"
    )
    assert TARGET_SEMANTICS_POLICY == "contextual_entity_targets_v2"
    assert COMPONENT_LINK_POLICY == (
        "contextual_links_not_same_quote_required_v1"
    )
    assert QUALITY_WORKFLOW_POLICY == "auto_review_manual_precedence_v2"
    assert SCOPE_CLASSIFICATION_POLICY == (
        "binary_named_generation_pre_model_guard_v3"
    )


def test_model_provider_keeps_public_type_annotation() -> None:
    assert get_type_hints(config_module)["MODEL_PROVIDER"] == ModelProvider


def test_extraction_config_structure_order_and_values_are_exact() -> None:
    assert list(EXTRACTION_CONFIG) == [
        "model_provider",
        "model_name",
        "agent_retries",
        "use_native_output",
        "model_settings",
        "document_validation_version",
        "model_run_timeout_seconds",
        "canonicalization_policy",
        "entity_model_policy",
        "event_granularity_policy",
        "temporal_policy",
        "documentary_match_policy",
        "target_semantics_policy",
        "component_link_policy",
        "quality_workflow_policy",
        "scope_classification_policy",
        "contract_schema_sha256",
        "instructions_sha256",
    ]
    assert EXTRACTION_CONFIG == {
        "model_provider": MODEL_PROVIDER,
        "model_name": AI_MODEL_NAME,
        "agent_retries": AGENT_RETRIES,
        "use_native_output": USE_NATIVE_OUTPUT,
        "model_settings": MODEL_SETTINGS,
        "document_validation_version": DOCUMENT_VALIDATION_VERSION,
        "model_run_timeout_seconds": MODEL_RUN_TIMEOUT_SECONDS,
        "canonicalization_policy": config_module._CANONICALIZATION_POLICY,
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


def test_reproducible_hashes_are_dynamic_and_match_validated_snapshots() -> None:
    expected_schema_hash = _stable_json_hash(
        BOEAIExtraction.model_json_schema()
    )
    expected_instructions_hash = sha256(
        AGENT_INSTRUCTIONS.encode("utf-8")
    ).hexdigest()
    expected_config_id = _stable_json_hash(EXTRACTION_CONFIG)[:16]

    assert CONTRACT_SCHEMA_SHA256 == expected_schema_hash
    assert INSTRUCTIONS_SHA256 == expected_instructions_hash
    assert EXTRACTION_CONFIG_ID == expected_config_id
    assert CONTRACT_SCHEMA_SHA256 == EXPECTED_CONTRACT_SCHEMA_SHA256
    assert INSTRUCTIONS_SHA256 == EXPECTED_INSTRUCTIONS_SHA256
    assert EXTRACTION_CONFIG_ID == EXPECTED_EXTRACTION_CONFIG_ID


def test_relevant_configuration_change_produces_different_hash() -> None:
    changed = {
        **EXTRACTION_CONFIG,
        "model_name": "changed-model",
    }

    assert _stable_json_hash(changed)[:16] != EXTRACTION_CONFIG_ID


def test_canonicalization_policy_change_produces_different_config_id() -> None:
    changed = {
        **EXTRACTION_CONFIG,
        "canonicalization_policy": "changed-canonicalization-policy",
    }

    assert (
        EXTRACTION_CONFIG["canonicalization_policy"]
        == config_module._CANONICALIZATION_POLICY
    )
    assert _stable_json_hash(changed)[:16] != EXTRACTION_CONFIG_ID


def test_limited_freeze_reopen_changes_contract_and_productive_identity() -> None:
    assert CONTRACT_SCHEMA_SHA256 != PRE_LIMITED_REOPEN_CONTRACT_SCHEMA_SHA256
    assert EXTRACTION_CONFIG_ID != PRE_LIMITED_REOPEN_EXTRACTION_CONFIG_ID


def test_stable_json_hash_is_order_independent_and_value_sensitive() -> None:
    first = {"b": 2, "a": "á"}
    reordered = {"a": "á", "b": 2}
    changed = {"a": "á", "b": 3}

    assert _stable_json_hash(first) == _stable_json_hash(reordered)
    assert _stable_json_hash(first) != _stable_json_hash(changed)


def test_provider_defaults_are_internally_consistent() -> None:
    expected_defaults = {
        "gemini": ("google:gemini-2.5-flash", 3),
        "ollama": ("qwen3:8b", 4),
    }

    assert (AI_MODEL_NAME, AGENT_RETRIES) == expected_defaults[MODEL_PROVIDER]


def test_config_execution_has_no_io_network_agent_or_runner_side_effects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Path(config_module.__file__).read_text(encoding="utf-8")
    compiled = compile(source, "isolated-config", "exec")
    before = list(tmp_path.rglob("*"))

    def forbidden_open(*args, **kwargs):
        raise AssertionError("config.py intentó acceder a un archivo")

    def forbidden_network(*args, **kwargs):
        raise AssertionError("config.py intentó acceder a la red")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    namespace = {"__name__": "isolated_config"}

    exec(compiled, namespace)

    assert list(tmp_path.rglob("*")) == before
    assert namespace["EXTRACTION_CONFIG_ID"] == EXTRACTION_CONFIG_ID
    assert "agent" not in namespace
    assert "Agent" not in namespace
    assert "pydantic_ai" not in source
    assert "runner" not in source
    assert "os.environ" not in source
    assert "getenv" not in source


def test_review_uses_canonical_config_objects_without_local_assignments() -> None:
    # AST is intentional: ownership of lineage configuration is an explicit
    # architectural rule; review.py may consume but never redefine it.
    review_source = Path(review_module.__file__).read_text(encoding="utf-8")
    review_nodes = _top_level_nodes(review_source)
    names = {
        "DOCUMENT_VALIDATION_VERSION",
        "EXTRACTION_CONFIG_ID",
        "CONTRACT_SCHEMA_SHA256",
        "INSTRUCTIONS_SHA256",
        "MODEL_PROVIDER",
        "AI_MODEL_NAME",
    }
    config_import = next(
        node
        for node in ast.parse(review_source).body
        if isinstance(node, ast.ImportFrom)
        and node.module == "renewables_permitting.extraction.config"
    )

    assert names.isdisjoint(review_nodes)
    assert {alias.name for alias in config_import.names} == names
    for name in names:
        assert getattr(review_module, name) is getattr(config_module, name)
