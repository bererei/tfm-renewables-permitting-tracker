import ast
import builtins
from hashlib import sha256
import socket
from pathlib import Path

import renewables_permitting.extraction.instructions as instructions_module
from renewables_permitting.extraction.instructions import (
    AGENT_INSTRUCTIONS,
    CORE_INSTRUCTIONS,
    DECISION_EXAMPLES,
    TAXONOMY_GUIDANCE,
)


def test_instruction_section_hashes_match_validated_snapshots() -> None:
    values = {
        "CORE_INSTRUCTIONS": CORE_INSTRUCTIONS,
        "TAXONOMY_GUIDANCE": TAXONOMY_GUIDANCE,
        "DECISION_EXAMPLES": DECISION_EXAMPLES,
        "AGENT_INSTRUCTIONS": AGENT_INSTRUCTIONS,
    }
    expected_hashes = {
        "CORE_INSTRUCTIONS": (
            "b87be37b9a26466b12a5bbffaa3ea1e24a95a84fc14e39569726e9a9432218df"
        ),
        "TAXONOMY_GUIDANCE": (
            "58cd07a3e6903158e214bffd01b372d73e3235fd7da2cc8d73b1a64fd714d64d"
        ),
        "DECISION_EXAMPLES": (
            "64b13944ad4fc5b41c02f34f0186344033e3a8ae4a8c3ba4dd1d9cb59857a140"
        ),
        "AGENT_INSTRUCTIONS": (
            "b48240832d1b274af0435cea42cc6d305d2aec83b5a3395a1d5ce1529eff0607"
        ),
    }

    assert {
        name: sha256(value.encode("utf-8")).hexdigest()
        for name, value in values.items()
    } == expected_hashes


def test_agent_instructions_use_exact_section_order_and_separators() -> None:
    expected = "\n\n".join([
        CORE_INSTRUCTIONS.strip(),
        TAXONOMY_GUIDANCE.strip(),
        DECISION_EXAMPLES.strip(),
    ])

    assert AGENT_INSTRUCTIONS == expected
    assert AGENT_INSTRUCTIONS.startswith(
        "Eres un extractor canónico de publicaciones"
    )
    assert AGENT_INSTRUCTIONS.endswith(
        "decision=formulado."
    )
    assert (
        AGENT_INSTRUCTIONS.index("OBJETIVO DEL TFM")
        < AGENT_INSTRUCTIONS.index("DECISIONES ADMINISTRATIVAS")
        < AGENT_INSTRUCTIONS.index("EJEMPLO 1 — CARBO")
    )


def test_instruction_sections_are_nonempty_and_included_once() -> None:
    sections = [CORE_INSTRUCTIONS, TAXONOMY_GUIDANCE, DECISION_EXAMPLES]
    normalized_sections = [section.strip() for section in sections]

    assert all(normalized_sections)
    assert all(
        AGENT_INSTRUCTIONS.count(section) == 1
        for section in normalized_sections
    )


def test_environmental_decision_guidance_prioritizes_specific_outcomes() -> None:
    guidance = " ".join(TAXONOMY_GUIDANCE.split())
    examples = " ".join(DECISION_EXAMPLES.split())

    assert "resultado más específico" in guidance
    assert "formulado es solo el fallback" in guidance
    assert "No infieras una decisión terminal" in guidance
    assert all(
        value in guidance
        for value in (
            "declaracion_impacto_ambiental",
            "informe_impacto_ambiental",
            "informe_determinacion_afeccion_ambiental",
            "desfavorable",
            "sin_efectos_adversos_significativos",
            "requiere_evaluacion_ambiental_ordinaria",
            "requiere_evaluacion_ambiental_adicional",
            "no_requiere_evaluacion_ambiental_adicional",
        )
    )
    assert "Título: «se formula" in examples
    assert (
        "Cuerpo: «La declaración de impacto ambiental es desfavorable»"
        in examples
    )
    assert "decision=desfavorable" in examples
    assert "decision=formulado" in examples


def test_executing_instructions_has_no_io_network_or_agent_side_effects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Path(instructions_module.__file__).read_text(encoding="utf-8")
    compiled = compile(source, "isolated-instructions", "exec")
    before = list(tmp_path.rglob("*"))

    def forbidden_open(*args, **kwargs):
        raise AssertionError("instructions.py intentó acceder a un archivo")

    def forbidden_network(*args, **kwargs):
        raise AssertionError("instructions.py intentó acceder a la red")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    namespace: dict[str, object] = {}

    exec(compiled, namespace)

    assert list(tmp_path.rglob("*")) == before
    assert namespace["AGENT_INSTRUCTIONS"] == AGENT_INSTRUCTIONS
    assert "agent" not in namespace
    assert "Agent" not in namespace
    # AST is intentional: instructions.py is a data-only architectural layer
    # and importing another module would expand its side-effect boundary.
    tree = ast.parse(source)
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        for node in tree.body
    )
    assert "pydantic_ai" not in source
