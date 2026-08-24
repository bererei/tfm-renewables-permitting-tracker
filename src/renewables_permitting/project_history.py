"""Deterministic Tier 1 + Tier 2 strict retrieval of project history."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from renewables_permitting.extraction.flatten import flatten_current_extractions
from renewables_permitting.location_resolution import resolve_locations
from renewables_permitting.project_grouping import (
    _normalize_generation_name,
    group_projects,
)
from renewables_permitting.utils import normalize_text


PROJECT_HISTORY_POLICY_VERSION = "project_history_retrieval_v1"
ANCHOR_CANDIDATE_ID_VERSION = "anchor_project_candidate_v1"
PROJECT_HISTORY_CONTRACT_VERSION = "1"

ANCHOR_PROJECT_CANDIDATE_COLUMNS = (
    "anchor_project_candidate_id",
    "anchor_boe_ids_json",
    "anchor_publication_dates_json",
    "anchor_event_ids_json",
    "anchor_generation_asset_mention_ids_json",
    "anchor_source_document_sha256_json",
    "aliases_json",
    "normalized_name_keys_json",
    "distinctive_tokens_json",
    "generation_types_json",
    "locations_json",
)
PROJECT_HISTORY_CANDIDATE_COLUMNS = (
    "anchor_project_candidate_id",
    "historical_boe_id",
    "publication_date",
    "source_document_sha256",
    "match_tier",
    "match_reason",
    "match_evidence",
    "retrieval_policy_version",
)
HISTORICAL_SCOPE_COLUMNS = (
    "identificador_boe",
    "publication_date",
    "source_document_sha256",
)

GENERIC_TOKENS = frozenset({
    "solar", "solares", "eolico", "eolica", "eolicos", "eolicas",
    "fotovoltaico", "fotovoltaica", "fotovoltaicos", "fotovoltaicas",
    "parque", "parques", "planta", "plantas", "proyecto", "proyectos",
    "central", "centrales", "instalacion", "instalaciones", "generacion",
    "fase", "modulo", "modulos", "fv", "pfv", "psfv", "pe", "peol",
    "de", "del", "la", "las", "el", "los", "y", "en",
})

TECHNOLOGY_MARKERS: Mapping[str, tuple[str, ...]] = {
    "fotovoltaica": ("fotovolta", " planta solar ", " psfv ", " pfv ", " fv "),
    "eolica": ("eolic", " aerogenerador", " parque eolico ", " pe "),
    "hidroelectrica": ("hidroelect", " central hidraul", " aprovechamiento hidraul"),
    "termosolar": ("termosolar", "solar termoelect"),
    "biomasa": ("biomasa",),
    "biogas": ("biogas",),
    "cogeneracion": ("cogeneracion",),
    "otra": (),
}


@dataclass(frozen=True)
class ProjectSignature:
    """Audited retrieval signals for one lineage-based anchor root."""

    anchor_project_candidate_id: str
    aliases: tuple[str, ...]
    normalized_name_keys: tuple[str, ...]
    locations: tuple[str, ...]
    generation_types: tuple[str, ...]


@dataclass(frozen=True)
class ProjectHistoryBuild:
    """In-memory contractual result before publication."""

    anchor_project_candidates: pd.DataFrame
    project_history_candidates: pd.DataFrame
    historical_scope: pd.DataFrame
    holdout_overlap_count: int
    source_conflict_count: int


@dataclass(frozen=True)
class ProjectHistoryMaterialization:
    """Verified paths and identities of a history materialization."""

    output_dir: Path
    manifest_path: Path
    anchor_project_candidates_path: Path
    project_history_candidates_path: Path
    historical_scope_path: Path
    manifest: Mapping[str, Any]
    anchor_project_candidates: pd.DataFrame
    project_history_candidates: pd.DataFrame
    historical_scope: pd.DataFrame


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    )


def _json_list(values: Sequence[Any]) -> str:
    return _canonical_json(list(values))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scope_table_fingerprint(frame: pd.DataFrame) -> str:
    """Use the established extraction-scope semantic fingerprint."""

    ordered = frame.sort_values("identificador_boe", kind="stable")
    lines = [
        "|".join("" if pd.isna(value) else str(value) for value in row)
        for row in ordered.itertuples(index=False, name=None)
    ]
    return sha256("".join(f"{line}\n" for line in lines).encode()).hexdigest()


def _phrase_mask(texts: pd.Series, phrase: str) -> pd.Series:
    return texts.str.contains(f" {phrase} ", regex=False, na=False)


def _usable_alias(alias: str) -> bool:
    tokens = [token for token in alias.split() if token not in GENERIC_TOKENS]
    return any(token.isalpha() and len(token) >= 4 for token in tokens)


def _core_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token for token in value.split()
        if token not in GENERIC_TOKENS and len(token) >= 2
    )


def _technology_mask(texts: pd.Series, types: Sequence[str]) -> pd.Series:
    result = pd.Series(False, index=texts.index)
    for generation_type in types:
        for marker in TECHNOLOGY_MARKERS.get(generation_type, ()):
            result |= texts.str.contains(marker, regex=False, na=False)
    return result


def _geography_mask(texts: pd.Series, locations: Sequence[str]) -> pd.Series:
    result = pd.Series(False, index=texts.index)
    for location in locations:
        result |= _phrase_mask(texts, location)
    return result


def _typed_anchor(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=ANCHOR_PROJECT_CANDIDATE_COLUMNS)
    for column in ANCHOR_PROJECT_CANDIDATE_COLUMNS:
        frame[column] = frame[column].astype("string")
    return frame


def _typed_links(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=PROJECT_HISTORY_CANDIDATE_COLUMNS)
    for column in PROJECT_HISTORY_CANDIDATE_COLUMNS:
        if column == "publication_date":
            frame[column] = pd.to_datetime(frame[column])
        else:
            frame[column] = frame[column].astype("string")
    return frame


def _typed_scope(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=HISTORICAL_SCOPE_COLUMNS)
    frame["identificador_boe"] = frame["identificador_boe"].astype("string")
    frame["publication_date"] = pd.to_datetime(frame["publication_date"])
    frame["source_document_sha256"] = frame[
        "source_document_sha256"
    ].astype("string")
    return frame


def build_anchor_project_candidates(
    current_extractions: pd.DataFrame,
    municipality_dimension: pd.DataFrame,
    *,
    anchor_snapshot_id: str,
) -> tuple[pd.DataFrame, tuple[ProjectSignature, ...]]:
    """Derive anchor roots with IDs based only on stable extraction lineage."""

    source_hash_by_boe = dict(zip(
        current_extractions["identificador_boe"].astype(str),
        current_extractions["source_document_sha256"].astype(str),
        strict=True,
    ))
    flat = flatten_current_extractions(current_extractions)
    resolved = resolve_locations(flat["location_mentions"], municipality_dimension)
    grouping = group_projects(
        flat["generation_asset_mentions"], flat["generation_asset_names"], resolved
    )
    assets = flat["generation_asset_mentions"].merge(
        grouping, on="generation_asset_mention_id", how="inner"
    )
    names = flat["generation_asset_names"]
    names_by_mention = {
        str(mention): list(rows["name_raw"].astype(str))
        for mention, rows in names.groupby("generation_asset_mention_id", sort=True)
    }
    location_by_event: dict[str, set[str]] = defaultdict(set)
    for row in resolved.itertuples(index=False):
        for column in ("municipality", "province", "autonomous_community"):
            value = getattr(row, column)
            if pd.notna(value):
                normalized = normalize_text(str(value))
                if len(normalized) >= 4:
                    location_by_event[str(row.event_id)].add(normalized)

    records: list[dict[str, Any]] = []
    signatures: list[ProjectSignature] = []
    for _, rows in assets.groupby("project_id", sort=True):
        aliases: set[str] = set()
        keys: set[str] = set()
        locations: set[str] = set()
        boes: set[str] = set()
        dates: set[str] = set()
        event_ids: set[str] = set()
        mention_ids: set[str] = set()
        source_hashes: set[str] = set()
        generation_types: set[str] = set()
        for row in rows.itertuples(index=False):
            mention_id = str(row.generation_asset_mention_id)
            observed_names = names_by_mention[mention_id]
            aliases.update(normalize_text(name) for name in observed_names)
            keys.update(_normalize_generation_name(name) for name in observed_names)
            locations.update(location_by_event.get(str(row.event_id), set()))
            boes.add(str(row.identificador_boe))
            dates.add(pd.Timestamp(row.fecha_publicacion).date().isoformat())
            event_ids.add(str(row.event_id))
            mention_ids.add(mention_id)
            source_hashes.add(source_hash_by_boe[str(row.identificador_boe)])
            generation_types.add(str(row.generation_type))
        lineage = {
            "version": ANCHOR_CANDIDATE_ID_VERSION,
            "anchor_snapshot_id": anchor_snapshot_id,
            "generation_asset_mention_ids": sorted(mention_ids),
        }
        candidate_id = "anchor_candidate_" + sha256(
            _canonical_json(lineage).encode()
        ).hexdigest()[:32]
        candidate_tokens = sorted({
            token
            for value in keys | aliases
            for token in _core_tokens(value)
        })
        records.append({
            "anchor_project_candidate_id": candidate_id,
            "anchor_boe_ids_json": _json_list(sorted(boes)),
            "anchor_publication_dates_json": _json_list(sorted(dates)),
            "anchor_event_ids_json": _json_list(sorted(event_ids)),
            "anchor_generation_asset_mention_ids_json": _json_list(sorted(mention_ids)),
            "anchor_source_document_sha256_json": _json_list(sorted(source_hashes)),
            "aliases_json": _json_list(sorted(aliases)),
            "normalized_name_keys_json": _json_list(sorted(keys)),
            "distinctive_tokens_json": _json_list(candidate_tokens),
            "generation_types_json": _json_list(sorted(generation_types)),
            "locations_json": _json_list(sorted(locations)),
        })
        signatures.append(ProjectSignature(
            anchor_project_candidate_id=candidate_id,
            aliases=tuple(sorted(aliases)),
            normalized_name_keys=tuple(sorted(keys)),
            locations=tuple(sorted(locations)),
            generation_types=tuple(sorted(generation_types)),
        ))
    return (
        _typed_anchor(records).sort_values(
            "anchor_project_candidate_id", kind="stable"
        ).reset_index(drop=True),
        tuple(sorted(signatures, key=lambda value: value.anchor_project_candidate_id)),
    )


def retrieve_project_history_candidates(
    signatures: Sequence[ProjectSignature],
    history_documents: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the exactly recovered audited Tier 1 + Tier 2 strict policy."""

    required = {
        "identificador", "fecha_publicacion", "titulo", "texto_limpio",
        "source_document_sha256",
    }
    missing = required - set(history_documents.columns)
    if missing:
        raise ValueError(f"Historical documents miss columns: {sorted(missing)}")
    history = history_documents.copy(deep=True).reset_index(drop=True)
    history["search_text"] = " " + (
        history["titulo"].astype(str) + "\n" + history["texto_limpio"].astype(str)
    ).map(normalize_text) + " "
    threshold = max(10, math.ceil(len(history) * 0.0005))
    texts = history["search_text"]
    token_frequency: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    for signature in signatures:
        tier1 = pd.Series(False, index=history.index)
        tier1_reasons: dict[int, str] = {}
        for alias in signature.aliases:
            if not _usable_alias(alias):
                continue
            mask = _phrase_mask(texts, alias)
            frequency = int(mask.sum())
            if 0 < frequency <= threshold:
                tier1 |= mask
                for index in history.index[mask]:
                    tier1_reasons.setdefault(int(index), f"exact_alias:{alias}")
        for index in history.index[tier1]:
            row = history.loc[index]
            reason = tier1_reasons[int(index)]
            records.append({
                "anchor_project_candidate_id": signature.anchor_project_candidate_id,
                "historical_boe_id": str(row.identificador),
                "publication_date": pd.Timestamp(row.fecha_publicacion),
                "source_document_sha256": str(row.source_document_sha256),
                "match_tier": "tier_1_exact_alias",
                "match_reason": reason,
                "match_evidence": reason.removeprefix("exact_alias:"),
                "retrieval_policy_version": PROJECT_HISTORY_POLICY_VERSION,
            })

        tier2 = pd.Series(False, index=history.index)
        tier2_reasons: dict[int, str] = {}
        corroboration = _technology_mask(
            texts, signature.generation_types
        ) | _geography_mask(texts, signature.locations)
        names = sorted(set(signature.normalized_name_keys) | set(signature.aliases))
        for candidate_name in names:
            tokens = _core_tokens(candidate_name)
            if not tokens:
                continue
            rare_alpha: list[str] = []
            for token in tokens:
                if token not in token_frequency:
                    token_frequency[token] = int(_phrase_mask(texts, token).sum())
                if (
                    token.isalpha() and len(token) >= 5
                    and token_frequency[token] <= threshold
                ):
                    rare_alpha.append(token)
            eligible = bool(rare_alpha) and (
                len(tokens) >= 2
                or (
                    len(tokens) == 1 and len(tokens[0]) >= 7
                    and token_frequency[tokens[0]] <= 3
                )
            )
            if not eligible:
                continue
            match = pd.Series(True, index=history.index)
            for token in tokens:
                match &= _phrase_mask(texts, token)
            match &= corroboration
            match &= ~tier1
            tier2 |= match
            reason = "strict_tokens:" + "+".join(tokens)
            for index in history.index[match]:
                tier2_reasons.setdefault(int(index), reason)
        for index in history.index[tier2]:
            row = history.loc[index]
            reason = tier2_reasons[int(index)]
            records.append({
                "anchor_project_candidate_id": signature.anchor_project_candidate_id,
                "historical_boe_id": str(row.identificador),
                "publication_date": pd.Timestamp(row.fecha_publicacion),
                "source_document_sha256": str(row.source_document_sha256),
                "match_tier": "tier_2_strict",
                "match_reason": reason,
                "match_evidence": reason.removeprefix("strict_tokens:"),
                "retrieval_policy_version": PROJECT_HISTORY_POLICY_VERSION,
            })
    result = _typed_links(records)
    if result.empty:
        return result
    tier_order = result["match_tier"].map({
        "tier_1_exact_alias": 1, "tier_2_strict": 2,
    })
    result = result.assign(_tier_order=tier_order).sort_values(
        ["_tier_order", "anchor_project_candidate_id", "publication_date", "historical_boe_id"],
        kind="stable",
    ).drop_duplicates(
        ["anchor_project_candidate_id", "historical_boe_id"], keep="first"
    ).drop(columns="_tier_order").reset_index(drop=True)
    return _typed_links(result.to_dict("records"))


def _validate_scope_lineage(
    scope: pd.DataFrame,
    source_by_id: pd.DataFrame,
    *,
    label: str,
) -> set[str]:
    required = {"identificador_boe", "source_document_sha256"}
    missing = required - set(scope.columns)
    if missing:
        raise ValueError(f"{label} misses columns: {sorted(missing)}")
    identifiers = scope["identificador_boe"].astype("string")
    if identifiers.isna().any() or identifiers.duplicated().any():
        raise ValueError(f"{label} contains invalid BOE identifiers.")
    absent = sorted(set(identifiers.astype(str)) - set(source_by_id.index.astype(str)))
    if absent:
        raise ValueError(f"{label} contains BOEs absent from source: {absent[:20]}")
    for row in scope.itertuples(index=False):
        actual = str(source_by_id.loc[str(row.identificador_boe), "source_document_sha256"])
        if actual != str(row.source_document_sha256):
            raise ValueError(f"Source drift in {label}: {row.identificador_boe}")
    return set(identifiers.astype(str))


def select_historical_search_universe(
    source_documents: pd.DataFrame,
    *,
    p2_main_boe_ids: set[str],
    holdout_boe_ids: set[str],
    history_start: date,
    history_end: date,
) -> pd.DataFrame:
    """Apply the audited date/P2 boundary and exclude holdout before matching."""

    source = source_documents.copy(deep=True)
    dates = pd.to_datetime(source["fecha_publicacion"])
    eligible = (
        dates.between(pd.Timestamp(history_start), pd.Timestamp(history_end), inclusive="both")
        & ((dates < pd.Timestamp("2024-01-01")) | source["identificador"].isin(p2_main_boe_ids))
        & ~source["identificador"].isin(holdout_boe_ids)
    )
    return source.loc[eligible].sort_values("identificador", kind="stable").reset_index(drop=True)


def build_project_history(
    *,
    source_documents: pd.DataFrame,
    anchor_current_extractions: pd.DataFrame,
    municipality_dimension: pd.DataFrame,
    anchor_scope: pd.DataFrame,
    p2_main_scope: pd.DataFrame,
    holdout_scope: pd.DataFrame,
    anchor_snapshot_id: str,
    history_start: date,
    history_end: date,
) -> ProjectHistoryBuild:
    """Build one fail-closed W14 history result without I/O or model calls."""

    if history_end < history_start:
        raise ValueError("History end precedes history start.")
    source = source_documents.copy(deep=True)
    source["fecha_publicacion"] = pd.to_datetime(source["fecha_publicacion"])
    if source["identificador"].astype("string").duplicated().any():
        raise ValueError("Source contains duplicate BOE identifiers.")
    source_by_id = source.set_index("identificador", drop=False)
    anchor_ids = _validate_scope_lineage(anchor_scope, source_by_id, label="anchor scope")
    main_ids = _validate_scope_lineage(p2_main_scope, source_by_id, label="P2 main scope")
    holdout_ids = _validate_scope_lineage(holdout_scope, source_by_id, label="holdout")
    current_ids = set(anchor_current_extractions["identificador_boe"].astype(str))
    if current_ids != anchor_ids:
        raise ValueError("Anchor extraction documents do not match anchor scope.")
    for row in anchor_current_extractions.itertuples(index=False):
        actual = str(source_by_id.loc[str(row.identificador_boe), "source_document_sha256"])
        if actual != str(row.source_document_sha256):
            raise ValueError(f"Source drift in anchor extraction: {row.identificador_boe}")

    anchor_candidates, signatures = build_anchor_project_candidates(
        anchor_current_extractions, municipality_dimension,
        anchor_snapshot_id=anchor_snapshot_id,
    )
    history = select_historical_search_universe(
        source,
        p2_main_boe_ids=main_ids,
        holdout_boe_ids=holdout_ids,
        history_start=history_start,
        history_end=history_end,
    )
    links = retrieve_project_history_candidates(signatures, history)
    holdout_overlap_count = int(links["historical_boe_id"].isin(holdout_ids).sum())
    if holdout_overlap_count:
        raise AssertionError("Holdout was inspected by historical retrieval.")
    scope = _typed_scope([
        {
            "identificador_boe": row.historical_boe_id,
            "publication_date": pd.Timestamp(row.publication_date),
            "source_document_sha256": row.source_document_sha256,
        }
        for row in links.sort_values("historical_boe_id", kind="stable")
        .drop_duplicates("historical_boe_id").itertuples(index=False)
    ])
    return ProjectHistoryBuild(
        anchor_project_candidates=anchor_candidates,
        project_history_candidates=links,
        historical_scope=scope,
        holdout_overlap_count=holdout_overlap_count,
        source_conflict_count=0,
    )


def _semantic_frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            result[column] = result[column].dt.strftime("%Y-%m-%d")
    return result.where(result.notna(), None).to_dict("records")


def project_history_materialization_identity(
    build: ProjectHistoryBuild,
    *,
    source_snapshot_id: str,
    anchor_snapshot_id: str,
    anchor_scope_fingerprint: str,
    ine_reference_sha256: str,
    history_start: date,
    history_end: date,
    code_sha256: str,
) -> str:
    payload = {
        "contract_version": PROJECT_HISTORY_CONTRACT_VERSION,
        "retrieval_policy_version": PROJECT_HISTORY_POLICY_VERSION,
        "source_snapshot_id": source_snapshot_id,
        "anchor_snapshot_id": anchor_snapshot_id,
        "anchor_scope_fingerprint": anchor_scope_fingerprint,
        "ine_reference_sha256": ine_reference_sha256,
        "history_start": history_start.isoformat(),
        "history_end": history_end.isoformat(),
        "code_sha256": code_sha256,
        "anchor_project_candidates": _semantic_frame_records(build.anchor_project_candidates),
        "project_history_candidates": _semantic_frame_records(build.project_history_candidates),
        "historical_scope_fingerprint": scope_table_fingerprint(build.historical_scope),
    }
    return sha256(_canonical_json(payload).encode()).hexdigest()


def _validate_build(build: ProjectHistoryBuild) -> None:
    if tuple(build.anchor_project_candidates.columns) != ANCHOR_PROJECT_CANDIDATE_COLUMNS:
        raise ValueError("Anchor project candidate schema is invalid.")
    if tuple(build.project_history_candidates.columns) != PROJECT_HISTORY_CANDIDATE_COLUMNS:
        raise ValueError("Project history candidate schema is invalid.")
    if tuple(build.historical_scope.columns) != HISTORICAL_SCOPE_COLUMNS:
        raise ValueError("Historical scope schema is invalid.")
    links = build.project_history_candidates
    if links.duplicated(["anchor_project_candidate_id", "historical_boe_id"]).any():
        raise ValueError("Project-history links are duplicated.")
    roots = set(build.anchor_project_candidates["anchor_project_candidate_id"].astype(str))
    if not set(links["anchor_project_candidate_id"].astype(str)).issubset(roots):
        raise ValueError("Project-history links reference an unknown anchor root.")
    scope_ids = set(build.historical_scope["identificador_boe"].astype(str))
    if scope_ids != set(links["historical_boe_id"].astype(str)):
        raise ValueError("Historical scope is not the exact BOE deduplication of links.")
    if build.historical_scope["identificador_boe"].duplicated().any():
        raise ValueError("Historical scope contains duplicate BOEs.")


def materialize_project_history(
    build: ProjectHistoryBuild,
    *,
    output_dir: Path,
    source_snapshot_id: str,
    anchor_snapshot_id: str,
    anchor_scope_fingerprint: str,
    ine_reference_sha256: str,
    p2_main_scope_fingerprint: str,
    holdout_scope_fingerprint: str,
    history_start: date,
    history_end: date,
    code_sha256: str,
    created_at: datetime | None = None,
) -> ProjectHistoryMaterialization:
    """Atomically publish and reload a deterministic history materialization."""

    _validate_build(build)
    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    prefix = f".{output_dir.name}.staging-"
    staging = Path(tempfile.mkdtemp(prefix=prefix, dir=output_dir.parent))
    try:
        anchor_path = staging / "anchor_project_candidates.parquet"
        links_path = staging / "project_history_candidates.parquet"
        scope_path = staging / "historical_scope.csv"
        build.anchor_project_candidates.to_parquet(anchor_path, index=False)
        build.project_history_candidates.to_parquet(links_path, index=False)
        scope_csv = build.historical_scope.copy()
        scope_csv["publication_date"] = scope_csv["publication_date"].dt.strftime("%Y-%m-%d")
        scope_csv.to_csv(scope_path, index=False)
        materialization_id = project_history_materialization_identity(
            build,
            source_snapshot_id=source_snapshot_id,
            anchor_snapshot_id=anchor_snapshot_id,
            anchor_scope_fingerprint=anchor_scope_fingerprint,
            ine_reference_sha256=ine_reference_sha256,
            history_start=history_start,
            history_end=history_end,
            code_sha256=code_sha256,
        )
        tier_counts = build.project_history_candidates["match_tier"].value_counts()
        multi_project = int(
            build.project_history_candidates.groupby("historical_boe_id")[
                "anchor_project_candidate_id"
            ].nunique().gt(1).sum()
        ) if not build.project_history_candidates.empty else 0
        manifest = {
            "stage": "project_history",
            "stage_version": "1",
            "contract_version": PROJECT_HISTORY_CONTRACT_VERSION,
            "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
            "retrieval_policy_version": PROJECT_HISTORY_POLICY_VERSION,
            "tier_1_enabled": True,
            "tier_2_strict_enabled": True,
            "tier_3_enabled": False,
            "source_snapshot_id": source_snapshot_id,
            "anchor_extraction_snapshot_id": anchor_snapshot_id,
            "anchor_scope_fingerprint": anchor_scope_fingerprint,
            "ine_reference_sha256": ine_reference_sha256,
            "p2_main_scope_fingerprint": p2_main_scope_fingerprint,
            "holdout_scope_fingerprint": holdout_scope_fingerprint,
            "history_start": history_start.isoformat(),
            "history_end": history_end.isoformat(),
            "code_sha256": code_sha256,
            "scope_fingerprint": scope_table_fingerprint(build.historical_scope),
            "materialization_identity_sha256": materialization_id,
            "counts": {
                "anchor_roots": len(build.anchor_project_candidates),
                "tier_1_links": int(tier_counts.get("tier_1_exact_alias", 0)),
                "tier_2_strict_links": int(tier_counts.get("tier_2_strict", 0)),
                "candidate_links": len(build.project_history_candidates),
                "unique_historical_boe": len(build.historical_scope),
                "multi_project_historical_boe": multi_project,
                "holdout_overlaps": build.holdout_overlap_count,
                "source_conflicts": build.source_conflict_count,
            },
            "artifacts": {
                "anchor_project_candidates": {
                    "filename": anchor_path.name,
                    "row_count": len(build.anchor_project_candidates),
                    "sha256": _sha256_file(anchor_path),
                },
                "project_history_candidates": {
                    "filename": links_path.name,
                    "row_count": len(build.project_history_candidates),
                    "sha256": _sha256_file(links_path),
                },
                "historical_scope": {
                    "filename": scope_path.name, "row_count": len(build.historical_scope),
                    "sha256": _sha256_file(scope_path),
                },
            },
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, output_dir)
    except Exception:
        if (
            staging.exists()
            and staging.parent == output_dir.parent
            and staging.name.startswith(prefix)
        ):
            shutil.rmtree(staging)
        raise
    return load_project_history_materialization(output_dir)


def load_project_history_materialization(path: Path) -> ProjectHistoryMaterialization:
    """Load a history output after exact artifact, schema and identity checks."""

    path = Path(path).absolute()
    expected_files = {
        "manifest.json", "anchor_project_candidates.parquet",
        "project_history_candidates.parquet", "historical_scope.csv",
    }
    if not path.is_dir() or {item.name for item in path.iterdir()} != expected_files:
        raise ValueError("Project history output has unexpected artifacts.")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("stage") != "project_history"
        or manifest.get("contract_version") != PROJECT_HISTORY_CONTRACT_VERSION
        or manifest.get("retrieval_policy_version") != PROJECT_HISTORY_POLICY_VERSION
        or manifest.get("tier_3_enabled") is not False
    ):
        raise ValueError("Project history manifest is incompatible.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "anchor_project_candidates", "project_history_candidates", "historical_scope"
    }:
        raise ValueError("Project history artifact metadata is incomplete.")
    for name, entry in artifacts.items():
        if not isinstance(entry, Mapping):
            raise ValueError(f"Project history artifact metadata is invalid: {name}")
        artifact = path / str(entry.get("filename"))
        if not artifact.is_file() or _sha256_file(artifact) != entry.get("sha256"):
            raise ValueError(f"Project history artifact hash mismatch: {name}")
    anchor = _typed_anchor(
        pd.read_parquet(path / "anchor_project_candidates.parquet")
        .to_dict("records")
    )
    links = _typed_links(
        pd.read_parquet(path / "project_history_candidates.parquet")
        .to_dict("records")
    )
    scope = _typed_scope(
        pd.read_csv(path / "historical_scope.csv", dtype="string")
        .to_dict("records")
    )
    build = ProjectHistoryBuild(
        anchor,
        links,
        scope,
        int(manifest["counts"]["holdout_overlaps"]),
        int(manifest["counts"]["source_conflicts"]),
    )
    _validate_build(build)
    counts = manifest.get("counts")
    tier_counts = links["match_tier"].value_counts()
    expected_counts = {
        "anchor_roots": len(anchor),
        "tier_1_links": int(tier_counts.get("tier_1_exact_alias", 0)),
        "tier_2_strict_links": int(tier_counts.get("tier_2_strict", 0)),
        "candidate_links": len(links),
        "unique_historical_boe": len(scope),
        "multi_project_historical_boe": int(
            links.groupby("historical_boe_id")["anchor_project_candidate_id"]
            .nunique().gt(1).sum()
        ) if not links.empty else 0,
        "holdout_overlaps": build.holdout_overlap_count,
        "source_conflicts": build.source_conflict_count,
    }
    if counts != expected_counts:
        raise ValueError("Project history manifest counts are inconsistent.")
    for name, frame in (
        ("anchor_project_candidates", anchor),
        ("project_history_candidates", links),
        ("historical_scope", scope),
    ):
        if artifacts[name].get("row_count") != len(frame):
            raise ValueError(f"Project history artifact row count mismatch: {name}")
    if manifest.get("scope_fingerprint") != scope_table_fingerprint(scope):
        raise ValueError("Historical scope fingerprint mismatch.")
    expected_identity = project_history_materialization_identity(
        build,
        source_snapshot_id=str(manifest["source_snapshot_id"]),
        anchor_snapshot_id=str(manifest["anchor_extraction_snapshot_id"]),
        anchor_scope_fingerprint=str(manifest["anchor_scope_fingerprint"]),
        ine_reference_sha256=str(manifest["ine_reference_sha256"]),
        history_start=date.fromisoformat(str(manifest["history_start"])),
        history_end=date.fromisoformat(str(manifest["history_end"])),
        code_sha256=str(manifest["code_sha256"]),
    )
    if manifest.get("materialization_identity_sha256") != expected_identity:
        raise ValueError("Project history materialization identity mismatch.")
    return ProjectHistoryMaterialization(
        output_dir=path,
        manifest_path=path / "manifest.json",
        anchor_project_candidates_path=path / "anchor_project_candidates.parquet",
        project_history_candidates_path=path / "project_history_candidates.parquet",
        historical_scope_path=path / "historical_scope.csv",
        manifest=manifest,
        anchor_project_candidates=anchor,
        project_history_candidates=links,
        historical_scope=scope,
    )
