from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from renewables_permitting.extraction.config import (
    AGENT_RETRIES,
    AI_MODEL_NAME,
    CHECKPOINT_EVERY,
    COMPONENT_LINK_POLICY,
    DOCUMENT_TIMEOUT_SECONDS,
    DOCUMENT_VALIDATION_RETRY_ATTEMPTS,
    DOCUMENT_VALIDATION_VERSION,
    DOCUMENTARY_MATCH_POLICY,
    ENTITY_MODEL_POLICY,
    EVENT_GRANULARITY_POLICY,
    MAX_MODEL_REQUESTS_PER_DOCUMENT,
    MODEL_PROVIDER,
    MODEL_RUN_TIMEOUT_SECONDS,
    QUALITY_WORKFLOW_POLICY,
    SCOPE_CLASSIFICATION_POLICY,
    TARGET_SEMANTICS_POLICY,
    TEMPORAL_POLICY,
    TRANSIENT_RETRY_BASE_SECONDS,
    TRANSIENT_RUN_ATTEMPTS,
    USE_NATIVE_OUTPUT,
)
from renewables_permitting.extraction.documents import (
    MAX_DOCUMENT_CHARS,
    MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX,
)
from renewables_permitting.extraction.instructions import AGENT_INSTRUCTIONS
from renewables_permitting.extraction.models import BOEAIExtraction


# Pydantic AI se importa de forma opcional para que el contrato y las pruebas
# deterministas puedan ejecutarse también en entornos sin acceso al modelo.
try:
    from pydantic_ai import Agent
    from pydantic_ai.models.ollama import OllamaModel
    from pydantic_ai.output import NativeOutput
    from pydantic_ai.providers.ollama import OllamaProvider
    from pydantic_ai.usage import RunUsage, UsageLimits
    PYDANTIC_AI_AVAILABLE = True
except ModuleNotFoundError:
    Agent = Any
    OllamaModel = Any
    NativeOutput = None
    OllamaProvider = Any
    PYDANTIC_AI_AVAILABLE = False

    @dataclass
    class RunUsage:  # fallback exclusivo para pruebas deterministas
        requests: int = 0
        input_tokens: int = 0
        output_tokens: int = 0
        total_tokens: int = 0

    class UsageLimits:
        def __init__(self, request_limit: int) -> None:
            self.request_limit = request_limit


def validate_runtime_configuration() -> None:
    """Valida únicamente invariantes operativas, sin acoplar pruebas a una versión concreta."""
    if MODEL_PROVIDER not in {"gemini", "ollama"}:
        raise ValueError(
            "MODEL_PROVIDER debe ser 'gemini' u 'ollama': "
            f"{MODEL_PROVIDER!r}."
        )

    boolean_settings = {
        "USE_NATIVE_OUTPUT": USE_NATIVE_OUTPUT,
    }
    for setting_name, setting_value in boolean_settings.items():
        if not isinstance(setting_value, bool):
            raise TypeError(
                f"{setting_name} debe ser bool, no {type(setting_value).__name__}."
            )

    positive_integer_settings = {
        "AGENT_RETRIES": AGENT_RETRIES,
        "MAX_MODEL_REQUESTS_PER_DOCUMENT": MAX_MODEL_REQUESTS_PER_DOCUMENT,
        "TRANSIENT_RUN_ATTEMPTS": TRANSIENT_RUN_ATTEMPTS,
        "CHECKPOINT_EVERY": CHECKPOINT_EVERY,
        "MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX": (
            MIN_SUBSTANTIVE_TEXT_CHARS_BEFORE_ANNEX
        ),
    }
    for setting_name, setting_value in positive_integer_settings.items():
        if not isinstance(setting_value, int) or isinstance(setting_value, bool):
            raise TypeError(f"{setting_name} debe ser un entero positivo.")
        if setting_value <= 0:
            raise ValueError(f"{setting_name} debe ser mayor que cero.")

    nonnegative_integer_settings = {
        "DOCUMENT_VALIDATION_RETRY_ATTEMPTS": (
            DOCUMENT_VALIDATION_RETRY_ATTEMPTS
        ),
    }
    for setting_name, setting_value in nonnegative_integer_settings.items():
        if not isinstance(setting_value, int) or isinstance(setting_value, bool):
            raise TypeError(f"{setting_name} debe ser un entero no negativo.")
        if setting_value < 0:
            raise ValueError(f"{setting_name} no puede ser negativo.")

    positive_numeric_settings = {
        "DOCUMENT_TIMEOUT_SECONDS": DOCUMENT_TIMEOUT_SECONDS,
        "MODEL_RUN_TIMEOUT_SECONDS": MODEL_RUN_TIMEOUT_SECONDS,
        "TRANSIENT_RETRY_BASE_SECONDS": TRANSIENT_RETRY_BASE_SECONDS,
    }
    for setting_name, setting_value in positive_numeric_settings.items():
        if (
            not isinstance(setting_value, (int, float))
            or isinstance(setting_value, bool)
            or setting_value <= 0
        ):
            raise ValueError(f"{setting_name} debe ser un número mayor que cero.")

    if MODEL_RUN_TIMEOUT_SECONDS >= DOCUMENT_TIMEOUT_SECONDS:
        raise ValueError(
            "MODEL_RUN_TIMEOUT_SECONDS debe ser menor que DOCUMENT_TIMEOUT_SECONDS."
        )

    if MAX_DOCUMENT_CHARS is not None:
        if (
            not isinstance(MAX_DOCUMENT_CHARS, int)
            or isinstance(MAX_DOCUMENT_CHARS, bool)
            or MAX_DOCUMENT_CHARS <= 0
        ):
            raise ValueError(
                "MAX_DOCUMENT_CHARS debe ser None o un entero mayor que cero."
            )

    if not re.fullmatch(r"[1-9]\d*", DOCUMENT_VALIDATION_VERSION):
        raise ValueError(
            "DOCUMENT_VALIDATION_VERSION debe ser una cadena entera positiva."
        )

    for policy_name, policy_value in {
        "ENTITY_MODEL_POLICY": ENTITY_MODEL_POLICY,
        "EVENT_GRANULARITY_POLICY": EVENT_GRANULARITY_POLICY,
        "TEMPORAL_POLICY": TEMPORAL_POLICY,
        "DOCUMENTARY_MATCH_POLICY": DOCUMENTARY_MATCH_POLICY,
        "TARGET_SEMANTICS_POLICY": TARGET_SEMANTICS_POLICY,
        "COMPONENT_LINK_POLICY": COMPONENT_LINK_POLICY,
        "QUALITY_WORKFLOW_POLICY": QUALITY_WORKFLOW_POLICY,
        "SCOPE_CLASSIFICATION_POLICY": SCOPE_CLASSIFICATION_POLICY,
    }.items():
        if not isinstance(policy_value, str) or not policy_value.strip():
            raise ValueError(f"{policy_name} debe ser una cadena no vacía.")


def build_ollama_model(
    model_name: str,
    *,
    base_url: str = "http://localhost:11434/v1",
):
    if not PYDANTIC_AI_AVAILABLE:
        raise RuntimeError("pydantic-ai no está instalado en este entorno.")
    return OllamaModel(
        model_name,
        provider=OllamaProvider(base_url=base_url),
    )


def build_boe_extraction_agent():
    if not PYDANTIC_AI_AVAILABLE:
        return None
    model = (
        AI_MODEL_NAME
        if MODEL_PROVIDER == "gemini"
        else build_ollama_model(AI_MODEL_NAME)
    )
    output_type = (
        NativeOutput(BOEAIExtraction)
        if USE_NATIVE_OUTPUT
        else BOEAIExtraction
    )
    return Agent(
        model=model,
        output_type=output_type,
        instructions=AGENT_INSTRUCTIONS,
        retries=AGENT_RETRIES,
    )
