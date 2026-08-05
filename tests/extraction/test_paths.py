import runpy
from pathlib import Path

import pytest

from renewables_permitting.extraction.paths import (
    ADMINISTRATIVE_ACTIONS_PATH,
    ADMINISTRATIVE_ACTION_TARGETS_PATH,
    ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH,
    ASSOCIATED_COMPONENT_NAMES_PATH,
    ASSOCIATED_COMPONENTS_PATH,
    BOE_AI_EXTRACTION_ATTEMPTS_PATH,
    BOE_AI_EXTRACTIONS_PATH,
    BOE_AI_MANUAL_REVIEW_DIR,
    BOE_AI_MANUAL_REVIEWS_PATH,
    BOE_AI_QUALITY_METRICS_PATH,
    BOE_AI_REVIEW_QUEUE_PATH,
    BOE_CANDIDATES_DOCS_TEXT_PATH,
    CASE_FILE_REFERENCES_PATH,
    DATA_DIR,
    GENERATION_ASSET_MENTIONS_PATH,
    GENERATION_ASSET_NAMES_PATH,
    GENERATION_RELATIONS_PATH,
    LOCATION_MENTIONS_PATH,
    PARTICIPANT_MENTIONS_PATH,
    PROJECT_ROOT,
    PUBLICATION_EVENTS_PATH,
    SILVER_BOE_AI_DIR,
    SILVER_DIR,
    TECHNICAL_MENTIONS_PATH,
    find_project_root,
)


PATHS_BY_NAME = {
    "PROJECT_ROOT": PROJECT_ROOT,
    "DATA_DIR": DATA_DIR,
    "SILVER_DIR": SILVER_DIR,
    "SILVER_BOE_AI_DIR": SILVER_BOE_AI_DIR,
    "BOE_CANDIDATES_DOCS_TEXT_PATH": BOE_CANDIDATES_DOCS_TEXT_PATH,
    "BOE_AI_EXTRACTIONS_PATH": BOE_AI_EXTRACTIONS_PATH,
    "BOE_AI_EXTRACTION_ATTEMPTS_PATH": BOE_AI_EXTRACTION_ATTEMPTS_PATH,
    "BOE_AI_REVIEW_QUEUE_PATH": BOE_AI_REVIEW_QUEUE_PATH,
    "BOE_AI_MANUAL_REVIEWS_PATH": BOE_AI_MANUAL_REVIEWS_PATH,
    "BOE_AI_QUALITY_METRICS_PATH": BOE_AI_QUALITY_METRICS_PATH,
    "BOE_AI_MANUAL_REVIEW_DIR": BOE_AI_MANUAL_REVIEW_DIR,
    "PUBLICATION_EVENTS_PATH": PUBLICATION_EVENTS_PATH,
    "GENERATION_ASSET_MENTIONS_PATH": GENERATION_ASSET_MENTIONS_PATH,
    "GENERATION_ASSET_NAMES_PATH": GENERATION_ASSET_NAMES_PATH,
    "ASSOCIATED_COMPONENTS_PATH": ASSOCIATED_COMPONENTS_PATH,
    "ASSOCIATED_COMPONENT_NAMES_PATH": ASSOCIATED_COMPONENT_NAMES_PATH,
    "ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH": (
        ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH
    ),
    "ADMINISTRATIVE_ACTIONS_PATH": ADMINISTRATIVE_ACTIONS_PATH,
    "ADMINISTRATIVE_ACTION_TARGETS_PATH": ADMINISTRATIVE_ACTION_TARGETS_PATH,
    "PARTICIPANT_MENTIONS_PATH": PARTICIPANT_MENTIONS_PATH,
    "LOCATION_MENTIONS_PATH": LOCATION_MENTIONS_PATH,
    "GENERATION_RELATIONS_PATH": GENERATION_RELATIONS_PATH,
    "TECHNICAL_MENTIONS_PATH": TECHNICAL_MENTIONS_PATH,
    "CASE_FILE_REFERENCES_PATH": CASE_FILE_REFERENCES_PATH,
}

EXPECTED_RELATIVE_PATHS = {
    "DATA_DIR": Path("data"),
    "SILVER_DIR": Path("data/silver"),
    "SILVER_BOE_AI_DIR": Path("data/silver/boe_ai"),
    "BOE_CANDIDATES_DOCS_TEXT_PATH": Path(
        "data/silver/boe_candidates_docs_text/boe_candidates_docs_text.parquet"
    ),
    "BOE_AI_EXTRACTIONS_PATH": Path(
        "data/silver/boe_ai/boe_ai_extractions.parquet"
    ),
    "BOE_AI_EXTRACTION_ATTEMPTS_PATH": Path(
        "data/silver/boe_ai/boe_ai_extractions_attempts.parquet"
    ),
    "BOE_AI_REVIEW_QUEUE_PATH": Path(
        "data/silver/boe_ai/boe_ai_review_queue.parquet"
    ),
    "BOE_AI_MANUAL_REVIEWS_PATH": Path(
        "data/silver/boe_ai/boe_ai_manual_reviews.parquet"
    ),
    "BOE_AI_QUALITY_METRICS_PATH": Path(
        "data/silver/boe_ai/boe_ai_quality_metrics.parquet"
    ),
    "BOE_AI_MANUAL_REVIEW_DIR": Path("data/manual/boe_ai_reviews"),
    "PUBLICATION_EVENTS_PATH": Path(
        "data/silver/boe_ai/publication_events.parquet"
    ),
    "GENERATION_ASSET_MENTIONS_PATH": Path(
        "data/silver/boe_ai/generation_asset_mentions.parquet"
    ),
    "GENERATION_ASSET_NAMES_PATH": Path(
        "data/silver/boe_ai/generation_asset_names.parquet"
    ),
    "ASSOCIATED_COMPONENTS_PATH": Path(
        "data/silver/boe_ai/associated_components.parquet"
    ),
    "ASSOCIATED_COMPONENT_NAMES_PATH": Path(
        "data/silver/boe_ai/associated_component_names.parquet"
    ),
    "ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH": Path(
        "data/silver/boe_ai/associated_component_generation_links.parquet"
    ),
    "ADMINISTRATIVE_ACTIONS_PATH": Path(
        "data/silver/boe_ai/administrative_actions.parquet"
    ),
    "ADMINISTRATIVE_ACTION_TARGETS_PATH": Path(
        "data/silver/boe_ai/administrative_action_targets.parquet"
    ),
    "PARTICIPANT_MENTIONS_PATH": Path(
        "data/silver/boe_ai/participant_mentions.parquet"
    ),
    "LOCATION_MENTIONS_PATH": Path(
        "data/silver/boe_ai/location_mentions.parquet"
    ),
    "GENERATION_RELATIONS_PATH": Path(
        "data/silver/boe_ai/generation_asset_relations.parquet"
    ),
    "TECHNICAL_MENTIONS_PATH": Path(
        "data/silver/boe_ai/technical_mentions.parquet"
    ),
    "CASE_FILE_REFERENCES_PATH": Path(
        "data/silver/boe_ai/case_file_references.parquet"
    ),
}


def _snapshot_tree(root: Path) -> dict[str, tuple[bool, bytes | None]]:
    return {
        str(path.relative_to(root)): (
            path.is_dir(),
            None if path.is_dir() else path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
    }


def test_find_project_root_from_root_and_nested_directory(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    nested = project_root / "one" / "two" / "three"
    nested.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text(
        "[project]\nname = 'temporary'\n",
        encoding="utf-8",
    )

    assert find_project_root(project_root) == project_root.resolve()
    assert find_project_root(nested) == project_root.resolve()


def test_find_project_root_uses_pyproject_toml_marker(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    nested = inner / "nested"
    nested.mkdir(parents=True)
    (outer / "pyproject.toml").write_text("", encoding="utf-8")
    (inner / "pyproject.toml").write_text("", encoding="utf-8")

    assert find_project_root(nested) == inner.resolve()


def test_find_project_root_error_matches_public_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = (tmp_path / "without_project" / "nested").resolve()
    start.mkdir(parents=True)
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    expected = (
        f"No se encontró pyproject.toml desde {start}. "
        "Ejecuta el notebook dentro del repositorio del TFM."
    )
    with pytest.raises(RuntimeError) as exc_info:
        find_project_root(start)

    assert str(exc_info.value) == expected


def test_all_exported_paths_are_path_objects() -> None:
    assert all(isinstance(path, Path) for path in PATHS_BY_NAME.values())


def test_paths_are_built_from_project_root_with_exact_names() -> None:
    assert PROJECT_ROOT == find_project_root()
    for name, relative_path in EXPECTED_RELATIVE_PATHS.items():
        assert PATHS_BY_NAME[name] == PROJECT_ROOT / relative_path


def test_importing_paths_has_no_filesystem_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_root = tmp_path / "fake_project"
    nested = fake_root / "nested"
    nested.mkdir(parents=True)
    (fake_root / "pyproject.toml").write_text(
        "[project]\nname = 'unchanged'\n",
        encoding="utf-8",
    )
    existing = fake_root / "existing.txt"
    existing.write_text("contenido original", encoding="utf-8")
    before = _snapshot_tree(fake_root)
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "renewables_permitting"
        / "extraction"
        / "paths.py"
    )
    monkeypatch.chdir(nested)

    namespace = runpy.run_path(str(module_path))

    assert namespace["PROJECT_ROOT"] == fake_root.resolve()
    assert _snapshot_tree(fake_root) == before
    assert existing.read_text(encoding="utf-8") == "contenido original"


def test_all_configured_paths_are_absolute_and_inside_project_root() -> None:
    assert all(path.is_absolute() for path in PATHS_BY_NAME.values())
    assert all(
        path == PROJECT_ROOT or PROJECT_ROOT in path.parents
        for path in PATHS_BY_NAME.values()
    )
    assert DATA_DIR.parent == PROJECT_ROOT
    assert SILVER_DIR.parent == DATA_DIR
    assert SILVER_BOE_AI_DIR.parent == SILVER_DIR
