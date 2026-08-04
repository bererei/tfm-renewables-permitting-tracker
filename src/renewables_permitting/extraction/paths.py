from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Localiza la raíz del proyecto buscando pyproject.toml."""

    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(
        f"No se encontró pyproject.toml desde {start}. "
        "Ejecuta el notebook dentro del repositorio del TFM."
    )


PROJECT_ROOT = find_project_root()


DATA_DIR = PROJECT_ROOT / "data"


SILVER_DIR = DATA_DIR / "silver"


SILVER_BOE_AI_DIR = SILVER_DIR / "boe_ai"


BOE_CANDIDATES_DOCS_TEXT_PATH = (
    SILVER_DIR
    / "boe_candidates_docs_text"
    / "boe_candidates_docs_text.parquet"
)


BOE_AI_EXTRACTIONS_PATH = SILVER_BOE_AI_DIR / "boe_ai_extractions.parquet"


BOE_AI_EXTRACTION_ATTEMPTS_PATH = (
    SILVER_BOE_AI_DIR / "boe_ai_extractions_attempts.parquet"
)


BOE_AI_REVIEW_QUEUE_PATH = SILVER_BOE_AI_DIR / "boe_ai_review_queue.parquet"


BOE_AI_MANUAL_REVIEWS_PATH = SILVER_BOE_AI_DIR / "boe_ai_manual_reviews.parquet"


BOE_AI_QUALITY_METRICS_PATH = SILVER_BOE_AI_DIR / "boe_ai_quality_metrics.parquet"


BOE_AI_MANUAL_REVIEW_DIR = DATA_DIR / "manual" / "boe_ai_reviews"


PUBLICATION_EVENTS_PATH = SILVER_BOE_AI_DIR / "publication_events.parquet"


GENERATION_ASSET_MENTIONS_PATH = (
    SILVER_BOE_AI_DIR / "generation_asset_mentions.parquet"
)


GENERATION_ASSET_NAMES_PATH = (
    SILVER_BOE_AI_DIR / "generation_asset_names.parquet"
)


ASSOCIATED_COMPONENTS_PATH = (
    SILVER_BOE_AI_DIR / "associated_components.parquet"
)


ASSOCIATED_COMPONENT_NAMES_PATH = (
    SILVER_BOE_AI_DIR / "associated_component_names.parquet"
)


ASSOCIATED_COMPONENT_GENERATION_LINKS_PATH = (
    SILVER_BOE_AI_DIR / "associated_component_generation_links.parquet"
)


ADMINISTRATIVE_ACTIONS_PATH = (
    SILVER_BOE_AI_DIR / "administrative_actions.parquet"
)


ADMINISTRATIVE_ACTION_TARGETS_PATH = (
    SILVER_BOE_AI_DIR / "administrative_action_targets.parquet"
)


PARTICIPANT_MENTIONS_PATH = (
    SILVER_BOE_AI_DIR / "participant_mentions.parquet"
)


LOCATION_MENTIONS_PATH = SILVER_BOE_AI_DIR / "location_mentions.parquet"


GENERATION_RELATIONS_PATH = (
    SILVER_BOE_AI_DIR / "generation_asset_relations.parquet"
)


TECHNICAL_MENTIONS_PATH = SILVER_BOE_AI_DIR / "technical_mentions.parquet"


CASE_FILE_REFERENCES_PATH = (
    SILVER_BOE_AI_DIR / "case_file_references.parquet"
)
