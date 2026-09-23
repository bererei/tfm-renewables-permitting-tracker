import ast
import json
import subprocess
import sys
from inspect import Parameter, signature
from pathlib import Path

import pytest

import renewables_permitting.extraction.agent as agent_module
from renewables_permitting.extraction.agent import (
    PYDANTIC_AI_AVAILABLE,
    RunUsage,
    UsageLimits,
    build_boe_extraction_agent,
    build_ollama_model,
    validate_runtime_configuration,
)
from renewables_permitting.extraction.config import (
    AGENT_RETRIES,
    AI_MODEL_NAME,
    MODEL_SETTINGS,
)
from renewables_permitting.extraction.instructions import AGENT_INSTRUCTIONS
from renewables_permitting.extraction.models import BOEAIExtraction


POSITIVE_INTEGER_SETTINGS = [
    "AGENT_RETRIES",
    "MAX_MODEL_REQUESTS_PER_DOCUMENT",
    "TRANSIENT_RUN_ATTEMPTS",
    "CHECKPOINT_EVERY",
    "MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX",
]

POSITIVE_NUMERIC_SETTINGS = [
    "DOCUMENT_TIMEOUT_SECONDS",
    "MODEL_RUN_TIMEOUT_SECONDS",
    "TRANSIENT_RETRY_BASE_SECONDS",
]

POLICY_SETTINGS = [
    "ENTITY_MODEL_POLICY",
    "EVENT_GRANULARITY_POLICY",
    "TEMPORAL_POLICY",
    "DOCUMENTARY_MATCH_POLICY",
    "TARGET_SEMANTICS_POLICY",
    "COMPONENT_LINK_POLICY",
    "QUALITY_WORKFLOW_POLICY",
    "SCOPE_CLASSIFICATION_POLICY",
]


def test_agent_module_imports_without_global_agent() -> None:
    assert isinstance(PYDANTIC_AI_AVAILABLE, bool)
    assert not hasattr(agent_module, "agent")
    assert callable(validate_runtime_configuration)
    assert callable(build_ollama_model)
    assert callable(build_boe_extraction_agent)


def test_available_run_usage_and_usage_limits_follow_active_branch() -> None:
    usage = RunUsage()
    limits = UsageLimits(request_limit=3)

    if PYDANTIC_AI_AVAILABLE:
        assert RunUsage.__module__.startswith("pydantic_ai")
        assert UsageLimits.__module__.startswith("pydantic_ai")
    else:
        assert vars(usage) == {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    assert limits.request_limit == 3


def test_current_runtime_configuration_is_valid() -> None:
    assert agent_module.MODEL_PROVIDER == "gemini"
    assert agent_module.AI_MODEL_NAME == "google:gemini-2.5-flash"

    assert validate_runtime_configuration() is None


def test_invalid_provider_raises_exact_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "invalid")

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        "MODEL_PROVIDER debe ser 'gemini' u 'ollama': 'invalid'."
    )


@pytest.mark.parametrize("value", [1, "true", None])
def test_use_native_output_requires_bool(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    monkeypatch.setattr(agent_module, "USE_NATIVE_OUTPUT", value)

    with pytest.raises(TypeError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        f"USE_NATIVE_OUTPUT debe ser bool, no {type(value).__name__}."
    )


@pytest.mark.parametrize("setting_name", POSITIVE_INTEGER_SETTINGS)
@pytest.mark.parametrize("value", ["1", 1.5, True])
def test_positive_integer_settings_reject_non_integers_and_bool(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
    value: object,
) -> None:
    monkeypatch.setattr(agent_module, setting_name, value)

    with pytest.raises(TypeError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        f"{setting_name} debe ser un entero positivo."
    )


@pytest.mark.parametrize("setting_name", POSITIVE_INTEGER_SETTINGS)
@pytest.mark.parametrize("value", [0, -1])
def test_positive_integer_settings_reject_nonpositive_values(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
    value: int,
) -> None:
    monkeypatch.setattr(agent_module, setting_name, value)

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        f"{setting_name} debe ser mayor que cero."
    )


@pytest.mark.parametrize("value", ["0", 1.5, True])
def test_validation_retry_attempts_requires_nonnegative_integer(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS",
        value,
    )

    with pytest.raises(TypeError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS debe ser un entero no negativo."
    )


def test_validation_retry_attempts_rejects_negative_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS",
        -1,
    )

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS no puede ser negativo."
    )


def test_zero_validation_retry_attempts_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS",
        0,
    )

    assert validate_runtime_configuration() is None


@pytest.mark.parametrize("setting_name", POSITIVE_NUMERIC_SETTINGS)
@pytest.mark.parametrize("value", [0, -1.0, True, "1"])
def test_positive_numeric_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
    value: object,
) -> None:
    monkeypatch.setattr(agent_module, setting_name, value)

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        f"{setting_name} debe ser un número mayor que cero."
    )


@pytest.mark.parametrize(
    ("document_timeout", "model_timeout"),
    [(240.0, 240.0), (100.0, 101.0)],
)
def test_model_timeout_must_be_less_than_document_timeout(
    monkeypatch: pytest.MonkeyPatch,
    document_timeout: float,
    model_timeout: float,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "DOCUMENT_TIMEOUT_SECONDS",
        document_timeout,
    )
    monkeypatch.setattr(
        agent_module,
        "MODEL_RUN_TIMEOUT_SECONDS",
        model_timeout,
    )

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        "MODEL_RUN_TIMEOUT_SECONDS debe ser menor que DOCUMENT_TIMEOUT_SECONDS."
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100"])
def test_max_document_chars_requires_none_or_positive_integer(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    monkeypatch.setattr(agent_module, "MAX_DOCUMENT_CHARS", value)

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        "MAX_DOCUMENT_CHARS debe ser None o un entero mayor que cero."
    )


@pytest.mark.parametrize("value", [None, 1, 1000])
def test_valid_max_document_chars_values(
    monkeypatch: pytest.MonkeyPatch,
    value: int | None,
) -> None:
    monkeypatch.setattr(agent_module, "MAX_DOCUMENT_CHARS", value)

    assert validate_runtime_configuration() is None


@pytest.mark.parametrize("value", ["", "0", "01", "-1", "1.0"])
def test_validation_version_rejects_invalid_strings(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "DOCUMENT_VALIDATION_VERSION",
        value,
    )

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        "DOCUMENT_VALIDATION_VERSION debe ser una cadena entera positiva."
    )


@pytest.mark.parametrize("value", [None, 1])
def test_validation_version_non_string_propagates_re_type_error(
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "DOCUMENT_VALIDATION_VERSION",
        value,
    )

    with pytest.raises(TypeError):
        validate_runtime_configuration()


@pytest.mark.parametrize("setting_name", POLICY_SETTINGS)
@pytest.mark.parametrize("value", ["", "   ", None])
def test_policy_settings_require_nonempty_strings(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
    value: object,
) -> None:
    monkeypatch.setattr(agent_module, setting_name, value)

    with pytest.raises(ValueError) as exc_info:
        validate_runtime_configuration()

    assert str(exc_info.value) == (
        f"{setting_name} debe ser una cadena no vacía."
    )


def test_unvalidated_model_name_and_model_settings_remain_unvalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_module, "AI_MODEL_NAME", "")
    monkeypatch.setattr(agent_module, "MODEL_SETTINGS", object(), raising=False)

    assert validate_runtime_configuration() is None


def test_runtime_validation_does_not_depend_on_pydantic_ai_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", False)

    assert validate_runtime_configuration() is None


def test_build_ollama_model_uses_exact_default_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls: list[dict[str, object]] = []
    model_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeProvider:
        def __init__(self, **kwargs) -> None:
            provider_calls.append(kwargs)

    class FakeModel:
        def __init__(self, *args, **kwargs) -> None:
            model_calls.append((args, kwargs))

    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", True)
    monkeypatch.setattr(agent_module, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(agent_module, "OllamaModel", FakeModel)

    result = build_ollama_model("qwen3:8b")

    assert isinstance(result, FakeModel)
    assert provider_calls == [
        {"base_url": "http://localhost:11434/v1"},
    ]
    assert len(model_calls) == 1
    args, kwargs = model_calls[0]
    assert args == ("qwen3:8b",)
    assert isinstance(kwargs["provider"], FakeProvider)
    assert set(kwargs) == {"provider"}


def test_build_ollama_model_uses_custom_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    class FakeProvider:
        def __init__(self, *, base_url: str) -> None:
            calls.append(("provider", base_url))

    class FakeModel:
        def __init__(self, model_name: str, *, provider: object) -> None:
            calls.append(("model_name", model_name))
            calls.append(("provider_object", provider))

    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", True)
    monkeypatch.setattr(agent_module, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(agent_module, "OllamaModel", FakeModel)

    result = build_ollama_model(
        "custom-model",
        base_url="http://ollama.test:11434/v1",
    )

    assert isinstance(result, FakeModel)
    assert calls[0] == ("provider", "http://ollama.test:11434/v1")
    assert calls[1] == ("model_name", "custom-model")
    assert isinstance(calls[2][1], FakeProvider)


def test_build_ollama_model_unavailable_raises_exact_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", False)

    with pytest.raises(RuntimeError) as exc_info:
        build_ollama_model("qwen3:8b")

    assert str(exc_info.value) == (
        "pydantic-ai no está instalado en este entorno."
    )


def test_build_gemini_agent_with_native_output_uses_exact_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_calls: list[object] = []
    agent_calls: list[dict[str, object]] = []
    native_output = object()
    constructed_agent = object()

    def fake_native_output(output_type: object) -> object:
        native_calls.append(output_type)
        return native_output

    def fake_agent(**kwargs) -> object:
        agent_calls.append(kwargs)
        return constructed_agent

    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", True)
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(agent_module, "USE_NATIVE_OUTPUT", True)
    monkeypatch.setattr(agent_module, "NativeOutput", fake_native_output)
    monkeypatch.setattr(agent_module, "Agent", fake_agent)

    result = build_boe_extraction_agent()

    assert result is constructed_agent
    assert native_calls == [BOEAIExtraction]
    assert agent_calls == [{
        "model": AI_MODEL_NAME,
        "output_type": native_output,
        "instructions": AGENT_INSTRUCTIONS,
        "retries": AGENT_RETRIES,
    }]
    assert "model_settings" not in agent_calls[0]


def test_build_agent_without_native_output_uses_contract_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_calls: list[dict[str, object]] = []

    def forbidden_native_output(*args, **kwargs):
        raise AssertionError("NativeOutput no debe construirse")

    def fake_agent(**kwargs) -> object:
        agent_calls.append(kwargs)
        return SimpleAgent()

    class SimpleAgent:
        def run(self, *args, **kwargs):
            raise AssertionError("build_boe_extraction_agent ejecutó el agente")

    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", True)
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(agent_module, "USE_NATIVE_OUTPUT", False)
    monkeypatch.setattr(
        agent_module,
        "NativeOutput",
        forbidden_native_output,
    )
    monkeypatch.setattr(agent_module, "Agent", fake_agent)

    result = build_boe_extraction_agent()

    assert isinstance(result, SimpleAgent)
    assert agent_calls == [{
        "model": AI_MODEL_NAME,
        "output_type": BOEAIExtraction,
        "instructions": AGENT_INSTRUCTIONS,
        "retries": AGENT_RETRIES,
    }]
    assert MODEL_SETTINGS == {"temperature": 0.0}
    assert "model_settings" not in agent_calls[0]


def test_build_ollama_agent_uses_model_builder_without_running_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder_calls: list[str] = []
    agent_calls: list[dict[str, object]] = []
    model = object()
    constructed_agent = object()

    def fake_builder(model_name: str) -> object:
        builder_calls.append(model_name)
        return model

    def fake_agent(**kwargs) -> object:
        agent_calls.append(kwargs)
        return constructed_agent

    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", True)
    monkeypatch.setattr(agent_module, "MODEL_PROVIDER", "ollama")
    monkeypatch.setattr(agent_module, "USE_NATIVE_OUTPUT", False)
    monkeypatch.setattr(agent_module, "build_ollama_model", fake_builder)
    monkeypatch.setattr(agent_module, "Agent", fake_agent)

    result = build_boe_extraction_agent()

    assert result is constructed_agent
    assert builder_calls == [AI_MODEL_NAME]
    assert agent_calls[0]["model"] is model
    assert agent_calls[0]["output_type"] is BOEAIExtraction


def test_build_agent_returns_none_when_dependency_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_agent(*args, **kwargs):
        raise AssertionError("Agent no debe construirse")

    monkeypatch.setattr(agent_module, "PYDANTIC_AI_AVAILABLE", False)
    monkeypatch.setattr(agent_module, "Agent", forbidden_agent)

    assert build_boe_extraction_agent() is None


def test_isolated_import_constructs_nothing_and_does_not_access_network() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = r"""
import json
import socket

import pydantic_ai
import pydantic_ai.models.ollama
import pydantic_ai.output
import pydantic_ai.providers.ollama

def forbidden(*args, **kwargs):
    raise AssertionError("constructor o red invocados durante import")

socket.create_connection = forbidden
pydantic_ai.Agent = forbidden
pydantic_ai.models.ollama.OllamaModel = forbidden
pydantic_ai.output.NativeOutput = forbidden
pydantic_ai.providers.ollama.OllamaProvider = forbidden

import renewables_permitting.extraction.agent as module

print(json.dumps({
    "available": module.PYDANTIC_AI_AVAILABLE,
    "has_agent": hasattr(module, "agent"),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload == {
        "available": True,
        "has_agent": False,
    }


def test_isolated_missing_dependency_uses_exact_fallback() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = r"""
import importlib.abc
import json
import sys
from typing import Any

class BlockPydanticAI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "pydantic_ai" or fullname.startswith("pydantic_ai."):
            raise ModuleNotFoundError("blocked for fallback test")
        return None

sys.meta_path.insert(0, BlockPydanticAI())

import renewables_permitting.extraction.agent as module

usage = module.RunUsage()
limits = module.UsageLimits(request_limit=7)
try:
    module.build_ollama_model("qwen3:8b")
except Exception as error:
    ollama_error = [type(error).__name__, str(error)]
else:
    ollama_error = None

print(json.dumps({
    "available": module.PYDANTIC_AI_AVAILABLE,
    "agent_is_any": module.Agent is Any,
    "ollama_is_any": module.OllamaModel is Any,
    "provider_is_any": module.OllamaProvider is Any,
    "native_output": module.NativeOutput,
    "usage": vars(usage),
    "request_limit": limits.request_limit,
    "built_agent": module.build_boe_extraction_agent(),
    "ollama_error": ollama_error,
    "has_agent": hasattr(module, "agent"),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload == {
        "available": False,
        "agent_is_any": True,
        "ollama_is_any": True,
        "provider_is_any": True,
        "native_output": None,
        "usage": {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        "request_limit": 7,
        "built_agent": None,
        "ollama_error": [
            "RuntimeError",
            "pydantic-ai no está instalado en este entorno.",
        ],
        "has_agent": False,
    }


def test_agent_public_call_signatures_are_stable() -> None:
    assert tuple(signature(validate_runtime_configuration).parameters) == ()
    assert tuple(signature(build_boe_extraction_agent).parameters) == ()

    ollama_parameters = signature(build_ollama_model).parameters
    assert tuple(ollama_parameters) == ("model_name", "base_url")
    assert ollama_parameters["model_name"].kind is (
        Parameter.POSITIONAL_OR_KEYWORD
    )
    assert ollama_parameters["base_url"].kind is Parameter.KEYWORD_ONLY
    assert ollama_parameters["base_url"].default == (
        "http://localhost:11434/v1"
    )


def test_agent_module_has_no_forbidden_runner_elements_or_top_level_calls() -> None:
    # AST is intentional: this is an import-boundary rule and must be checked
    # without executing any newly added top-level expression.
    source = Path(agent_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "ModelHTTPError" not in source
    assert "run_agent_with_transient_retries" not in source
    assert "extract_documents" not in source
    assert "run_and_finalize_extractions" not in source
    assert "debug_state" not in source
    assert not any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "agent"
            for target in (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
        )
        for node in tree.body
    )
    top_level_calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
    ]
    assert top_level_calls == []
