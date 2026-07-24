from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_V25_1_PATH = (
    PROJECT_ROOT / "notebooks" / "07_extraccion_ia_v25_1.ipynb"
)
NOTEBOOK_V25_2_PATH = (
    PROJECT_ROOT / "notebooks" / "07_extraccion_ia_v25_2.ipynb"
)
EXTRACTION_PACKAGE_PATH = (
    PROJECT_ROOT / "src" / "renewables_permitting" / "extraction"
)

V25_1_SIZE = 439_538
V25_1_MTIME_NS = 1_784_787_417_466_152_511
V25_1_SHA256 = (
    "f0bb34b614d574084fb3e2c32dd4331cc3b33e0f2ecacfb17188898039303218"
)

MIGRATED_MODULES = {
    "renewables_permitting.extraction.models": "models.py",
    "renewables_permitting.extraction.documents": "documents.py",
    "renewables_permitting.extraction.canonicalization": "canonicalization.py",
    "renewables_permitting.extraction.validation": "validation.py",
    "renewables_permitting.extraction.instructions": "instructions.py",
    "renewables_permitting.extraction.config": "config.py",
    "renewables_permitting.extraction.agent": "agent.py",
    "renewables_permitting.extraction.review": "review.py",
    "renewables_permitting.extraction.flatten": "flatten.py",
    "renewables_permitting.extraction.runner": "runner.py",
    "renewables_permitting.extraction.paths": "paths.py",
    "renewables_permitting.extraction.persistence": "persistence.py",
}

PILOT_FUNCTIONS = {
    "load_pilot_scope_labels",
    "_pilot_topic_group",
    "build_stratified_pilot_sample",
    "load_or_build_pilot_sample",
    "evaluate_pilot",
}

DANGEROUS_FLAGS = {
    "RUN_STRATIFIED_PILOT",
    "RESET_PILOT_OUTPUTS",
    "REBUILD_PILOT_SAMPLE",
    "RUN_PRODUCTION_EXTRACTION",
    "RESET_PRODUCTION_OUTPUTS",
    "RESET_QUALITY_METRICS",
    "REFRESH_REVIEW_WORKFLOW",
    "REGENERATE_FLAT_TABLES",
}


def _load_notebook(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _code_trees(notebook: dict[str, Any]) -> list[ast.Module]:
    return [
        ast.parse("".join(cell["source"]))
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {
        target.id
        for target in targets
        if isinstance(target, ast.Name)
    }


def _direct_product_names(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names.update(_assignment_names(node))
    return names


def _notebook_defined_names(trees: list[ast.Module]) -> set[str]:
    names: set[str] = set()
    for tree in trees:
        for node in tree.body:
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                names.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                names.update(_assignment_names(node))
    return names


def _notebook_imports(
    trees: list[ast.Module],
) -> dict[str, set[str]]:
    imports: dict[str, set[str]] = {}
    for tree in trees:
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            imports.setdefault(node.module, set()).update(
                alias.name for alias in node.names
            )
    return imports


def _literal_assignments(trees: list[ast.Module]) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    for tree in trees:
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            names = _assignment_names(node)
            value = node.value
            for name in names:
                try:
                    assignments[name] = ast.literal_eval(value)
                except (ValueError, TypeError):
                    pass
    return assignments


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        if (
            node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "agent"
        ):
            return "agent.run"
        return node.func.attr
    return None


def _guard_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    parent = getattr(node, "_parent", None)
    while parent is not None:
        if isinstance(parent, ast.If):
            names.update(
                child.id
                for child in ast.walk(parent.test)
                if isinstance(child, ast.Name)
            )
        parent = getattr(parent, "_parent", None)
    return names


def test_v25_2_is_valid_json_and_preserves_essential_metadata() -> None:
    source = _load_notebook(NOTEBOOK_V25_1_PATH)
    target = _load_notebook(NOTEBOOK_V25_2_PATH)

    assert target["nbformat"] == source["nbformat"]
    assert target["nbformat_minor"] == source["nbformat_minor"]
    assert target["metadata"] == source["metadata"]
    assert target["metadata"]["kernelspec"] == source["metadata"]["kernelspec"]
    assert target["metadata"]["language_info"] == source["metadata"]["language_info"]
    assert len(target["cells"]) == len(source["cells"]) == 24


def test_all_code_outputs_and_execution_counts_are_cleared() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    code_cells = [
        cell for cell in notebook["cells"] if cell["cell_type"] == "code"
    ]

    assert code_cells
    assert all(cell["execution_count"] is None for cell in code_cells)
    assert all(cell["outputs"] == [] for cell in code_cells)


def test_all_migrated_modules_and_elements_are_imported_explicitly() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    trees = _code_trees(notebook)
    imports = _notebook_imports(trees)

    assert set(MIGRATED_MODULES) <= imports.keys()
    assert "renewables_permitting.utils" in imports
    for module, filename in MIGRATED_MODULES.items():
        product_names = _direct_product_names(EXTRACTION_PACKAGE_PATH / filename)
        assert product_names <= imports[module]
        assert "*" not in imports[module]

    assert {
        "Agent",
        "PYDANTIC_AI_AVAILABLE",
        "RunUsage",
        "UsageLimits",
    } <= imports["renewables_permitting.extraction.agent"]


def test_notebook_does_not_redefine_any_migrated_product_element() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    trees = _code_trees(notebook)
    notebook_names = _notebook_defined_names(trees)
    migrated_names = set().union(
        *(
            _direct_product_names(EXTRACTION_PACKAGE_PATH / filename)
            for filename in MIGRATED_MODULES.values()
        )
    )
    migrated_names.update(
        {
            "PYDANTIC_AI_AVAILABLE",
            "RunUsage",
            "UsageLimits",
        }
    )

    assert notebook_names.isdisjoint(migrated_names)
    assert PILOT_FUNCTIONS <= notebook_names


def test_configuration_is_imported_without_local_reassignment() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    trees = _code_trees(notebook)
    assigned_names = _notebook_defined_names(trees)
    config_names = _direct_product_names(EXTRACTION_PACKAGE_PATH / "config.py")
    imports = _notebook_imports(trees)

    assert config_names <= imports["renewables_permitting.extraction.config"]
    assert assigned_names.isdisjoint(config_names)


def test_model_and_agent_construction_remain_explicit_orchestration() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    trees = _code_trees(notebook)
    orchestration_tree = trees[3]

    calls = [
        node
        for node in orchestration_tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert [_call_name(node.value) for node in calls] == [
        "validate_runtime_configuration"
    ]

    assignments = {
        next(iter(_assignment_names(node))): node.value
        for node in orchestration_tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and len(_assignment_names(node)) == 1
    }
    ai_model = assignments["AI_MODEL"]
    assert isinstance(ai_model, ast.IfExp)
    assert ast.unparse(ai_model.test) == "MODEL_PROVIDER == 'gemini'"
    assert ast.unparse(ai_model.body) == "AI_MODEL_NAME"
    assert ast.unparse(ai_model.orelse) == "build_ollama_model(AI_MODEL_NAME)"
    assert ast.unparse(assignments["agent"]) == "build_boe_extraction_agent()"


def test_only_the_five_pilot_functions_remain_defined() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    definitions = {
        node.name
        for tree in _code_trees(notebook)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }

    assert definitions == PILOT_FUNCTIONS


def test_pilot_and_production_blocks_are_preserved_with_safe_flags() -> None:
    source = _load_notebook(NOTEBOOK_V25_1_PATH)
    target = _load_notebook(NOTEBOOK_V25_2_PATH)
    source_pilot = "".join(source["cells"][21]["source"])
    target_pilot = "".join(target["cells"][21]["source"])

    assert target_pilot == source_pilot.replace(
        "RUN_STRATIFIED_PILOT = True",
        "RUN_STRATIFIED_PILOT = False",
        1,
    )
    assert target["cells"][23]["source"] == source["cells"][23]["source"]

    assignments = _literal_assignments(_code_trees(target))
    assert DANGEROUS_FLAGS <= assignments.keys()
    assert all(assignments[name] is False for name in DANGEROUS_FLAGS)
    assert assignments["RAISE_ON_PILOT_FAILURE"] is True


def test_no_artificial_if_true_or_unguarded_operational_calls() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    trees = _code_trees(notebook)
    protected_calls: dict[str, list[set[str]]] = {
        "run_and_finalize_extractions": [],
        "save_flattened_extractions": [],
        "unlink": [],
    }

    for tree in trees:
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child._parent = parent  # type: ignore[attr-defined]
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                assert not (
                    isinstance(node.test, ast.Constant)
                    and node.test.value is True
                )
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node)
            assert call_name != "agent.run"
            if call_name in protected_calls:
                protected_calls[call_name].append(_guard_names(node))

    assert len(protected_calls["run_and_finalize_extractions"]) == 2
    assert len(protected_calls["save_flattened_extractions"]) == 1
    assert len(protected_calls["unlink"]) == 3
    assert all(
        guards & DANGEROUS_FLAGS
        for occurrences in protected_calls.values()
        for guards in occurrences
    )


def test_embedded_regressions_are_replaced_by_a_markdown_note() -> None:
    notebook = _load_notebook(NOTEBOOK_V25_2_PATH)
    code_source = "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    markdown_source = "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "markdown"
    )

    assert "_run_regression_tests" not in code_source
    assert "_test_document" not in code_source
    assert "_test_extraction" not in code_source
    assert "tests/extraction" in markdown_source
    assert "pytest" in markdown_source


def test_v25_1_reference_file_is_unchanged() -> None:
    stat = NOTEBOOK_V25_1_PATH.stat()

    assert stat.st_size == V25_1_SIZE
    assert stat.st_mtime_ns == V25_1_MTIME_NS
    assert hashlib.sha256(NOTEBOOK_V25_1_PATH.read_bytes()).hexdigest() == (
        V25_1_SHA256
    )
