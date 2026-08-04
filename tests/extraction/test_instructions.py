import ast
import builtins
import json
import socket
from pathlib import Path

import renewables_permitting.extraction.instructions as instructions_module
from renewables_permitting.extraction.instructions import (
    AGENT_INSTRUCTIONS,
    CORE_INSTRUCTIONS,
    DECISION_EXAMPLES,
    TAXONOMY_GUIDANCE,
)


INSTRUCTION_NAMES = {
    "CORE_INSTRUCTIONS",
    "TAXONOMY_GUIDANCE",
    "DECISION_EXAMPLES",
    "AGENT_INSTRUCTIONS",
}


def _top_level_assignments(source: str) -> dict[str, ast.Assign]:
    assignments: dict[str, ast.Assign] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = node
    return assignments


def _notebook_instruction_values() -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text(encoding="utf-8")
    )
    namespace: dict[str, str] = {}
    exec(
        compile(
            "".join(notebook["cells"][5]["source"]),
            "notebook-instructions",
            "exec",
        ),
        namespace,
    )
    return {
        name: namespace[name]
        for name in INSTRUCTION_NAMES
    }


def test_instruction_values_match_notebook_literally() -> None:
    notebook_values = _notebook_instruction_values()

    assert CORE_INSTRUCTIONS == notebook_values["CORE_INSTRUCTIONS"]
    assert TAXONOMY_GUIDANCE == notebook_values["TAXONOMY_GUIDANCE"]
    assert DECISION_EXAMPLES == notebook_values["DECISION_EXAMPLES"]
    assert AGENT_INSTRUCTIONS == notebook_values["AGENT_INSTRUCTIONS"]


def test_agent_instructions_use_exact_notebook_order_and_separators() -> None:
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
        "usa not_relevant_for_generation_projects."
    )
    assert (
        AGENT_INSTRUCTIONS.index("OBJETIVO DEL TFM")
        < AGENT_INSTRUCTIONS.index("DECISIONES ADMINISTRATIVAS")
        < AGENT_INSTRUCTIONS.index("EJEMPLO 1 — CARBO")
    )


def test_instruction_assignments_match_notebook_ast() -> None:
    project_root = Path(__file__).resolve().parents[2]
    notebook = json.loads(
        (
            project_root / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
        ).read_text(encoding="utf-8")
    )
    notebook_source = "".join(notebook["cells"][5]["source"])
    module_source = Path(instructions_module.__file__).read_text(
        encoding="utf-8"
    )
    notebook_nodes = _top_level_assignments(notebook_source)
    module_nodes = _top_level_assignments(module_source)

    assert set(module_nodes) == INSTRUCTION_NAMES
    for name in INSTRUCTION_NAMES:
        assert ast.dump(module_nodes[name], include_attributes=False) == ast.dump(
            notebook_nodes[name],
            include_attributes=False,
        ), name


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
    tree = ast.parse(source)
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        for node in tree.body
    )
    assert "pydantic_ai" not in source
