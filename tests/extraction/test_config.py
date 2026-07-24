import ast
import builtins
import json
import socket
from hashlib import sha256
from pathlib import Path
from typing import get_args

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
    "455028c7de0ada067264cd695b4e7dab9de377b31105e141321313d61c3ff283"
)
EXPECTED_INSTRUCTIONS_SHA256 = (
    "4d9b67eba25460e912d7bee361def17272b0d9335738e6306b5a7c45de24561d"
)
EXPECTED_EXTRACTION_CONFIG_ID = "db2bc8c3564ce062"

CONFIG_NODE_NAMES = {
    "ModelProvider",
    "MODEL_PROVIDER",
    "AI_MODEL_NAME",
    "AGENT_RETRIES",
    "USE_NATIVE_OUTPUT",
    "MODEL_SETTINGS",
    "DOCUMENT_TIMEOUT_SECONDS",
    "MODEL_RUN_TIMEOUT_SECONDS",
    "MAX_MODEL_REQUESTS_PER_DOCUMENT",
    "DOCUMENT_VALIDATION_RETRY_ATTEMPTS",
    "TRANSIENT_RUN_ATTEMPTS",
    "TRANSIENT_RETRY_BASE_SECONDS",
    "CHECKPOINT_EVERY",
    "DOCUMENT_VALIDATION_VERSION",
    "ENTITY_MODEL_POLICY",
    "EVENT_GRANULARITY_POLICY",
    "TEMPORAL_POLICY",
    "DOCUMENTARY_MATCH_POLICY",
    "TARGET_SEMANTICS_POLICY",
    "COMPONENT_LINK_POLICY",
    "QUALITY_WORKFLOW_POLICY",
    "SCOPE_CLASSIFICATION_POLICY",
    "_stable_json_hash",
    "CONTRACT_SCHEMA_SHA256",
    "INSTRUCTIONS_SHA256",
    "EXTRACTION_CONFIG",
    "EXTRACTION_CONFIG_ID",
}


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


def test_model_provider_keeps_original_annotation() -> None:
    source = Path(config_module.__file__).read_text(encoding="utf-8")
    node = _top_level_nodes(source)["MODEL_PROVIDER"]

    assert isinstance(node, ast.AnnAssign)
    assert ast.unparse(node.annotation) == "ModelProvider"


def test_extraction_config_structure_order_and_values_are_exact() -> None:
    assert list(EXTRACTION_CONFIG) == [
        "model_provider",
        "model_name",
        "agent_retries",
        "use_native_output",
        "model_settings",
        "document_validation_version",
        "model_run_timeout_seconds",
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


def test_reproducible_hashes_are_dynamic_and_match_v25_1() -> None:
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


def test_hash_assignments_are_computed_not_literal_snapshots() -> None:
    source = Path(config_module.__file__).read_text(encoding="utf-8")
    nodes = _top_level_nodes(source)

    assert isinstance(nodes["CONTRACT_SCHEMA_SHA256"], ast.Assign)
    assert isinstance(
        nodes["CONTRACT_SCHEMA_SHA256"].value,
        ast.Call,
    )
    assert isinstance(nodes["INSTRUCTIONS_SHA256"], ast.Assign)
    assert isinstance(nodes["INSTRUCTIONS_SHA256"].value, ast.Call)
    assert isinstance(nodes["EXTRACTION_CONFIG_ID"], ast.Assign)
    assert isinstance(nodes["EXTRACTION_CONFIG_ID"].value, ast.Subscript)


def test_config_nodes_and_provider_branch_match_notebook_ast() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text(encoding="utf-8")
    )
    notebook_source = "".join(notebook["cells"][7]["source"])
    module_source = Path(config_module.__file__).read_text(encoding="utf-8")
    notebook_nodes = _top_level_nodes(notebook_source)
    module_nodes = _top_level_nodes(module_source)

    assert CONFIG_NODE_NAMES <= notebook_nodes.keys()
    assert CONFIG_NODE_NAMES <= module_nodes.keys()
    for name in CONFIG_NODE_NAMES:
        assert ast.dump(module_nodes[name], include_attributes=False) == ast.dump(
            notebook_nodes[name],
            include_attributes=False,
        ), name

    notebook_branch = next(
        node
        for node in ast.parse(notebook_source).body
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "MODEL_PROVIDER == 'ollama'"
    )
    module_branch = next(
        node
        for node in ast.parse(module_source).body
        if isinstance(node, ast.If)
    )
    assert ast.dump(
        module_branch,
        include_attributes=False,
    ) == ast.dump(
        notebook_branch,
        include_attributes=False,
    )


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
