# Final Corpus W14 Backfill Implementation

## 1. Purpose

This block productizes the audited conservative historical retrieval for the
closed W14 anchor. It generates project-to-BOE candidate links and a
document-deduplicated extraction scope offline. It does not authorize or run
Gemini, BOE access, Silver, downstream, Gold, holdout, P2 `main-04`, or the two
pending `main-03` retries.

## 2. Retrieval policy

`project_history_retrieval_v1` is the exactly recovered audit policy. The
search range is 2022-01-01 through 2026-08-06 inclusive. Before 2024 the
audited universe is the full canonical source; from 2024 onward it is limited
to the versioned P2 `main-*` model scopes. Holdout identifiers are excluded
before search text is built. The implementation reconstructed the reference
counts without hardcoding them.

## 3. Anchor roots

The verified anchor extraction identity is
`e7b7a5408f1420cf37ef4037502942fdd4e59536fa320b2ca16a4225e284623a`.
Its 48 current selections contain 40 generation roots and zero blockers.
Production flattening, INE resolution and conservative grouping derive the
root memberships.

## 4. Signatures

Each root signature contains only observed normalized names and literal
aliases, distinctive non-generic tokens, generation technology and resolved
territories. Promoter and power are not required. The intermediate
`anchor_project_candidate_id` hashes the anchor snapshot identity and sorted
`generation_asset_mention_id` lineage; it is not a Gold `project_id` and can
be traced to anchor BOE, event, mention and source hash.

## 5. Tier 1

Tier 1 requires an exact normalized phrase for an observed usable alias. An
alias must retain an alphabetic non-generic token of at least four characters,
and the phrase frequency must not exceed the audited corpus threshold
`max(10, ceil(N × 0.0005))`. Every link stores `exact_alias:<alias>`.

## 6. Tier 2 strict

Tier 2 requires every non-generic name token as an exact token, at least one
rare alphabetic token under the audited thresholds, and corroboration by an
audited technology marker or an exact resolved territory. It excludes links
already recovered by Tier 1 and records `strict_tokens:<tokens>`.

## 7. Tier 3 exclusion

No fuzzy, embedding, generic-token, infrastructure-only or Tier 3 fallback is
implemented. The manifest records `tier_3_enabled: false`, and regression
tests reject broad uncorroborated matches.

## 8. Candidate links

The materialization contains 78 root-to-document links: 71 Tier 1 and seven
Tier 2 strict. Every row preserves the anchor candidate ID, historical BOE,
publication date, source SHA-256, tier, compact reason/evidence and policy
version. Eleven historical BOEs link to more than one root.

## 9. Deduplication

All root-to-BOE relations remain in `project_history_candidates.parquet`, but
`historical_scope.csv` contains each historical BOE exactly once. The result
is 56 unique extraction documents; extraction is never duplicated per root.

## 10. Holdout protection

The versioned holdout registry is validated by identifier and source hash
without matching its text. It is removed from the search universe before text
normalization. The real materialization has zero overlaps, zero exclusions
after matching and zero source conflicts.

## 11. Identity and manifest

The source identity is
`1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf`;
the anchor scope fingerprint is
`ed07c25e74aaff29c19e28362f70dfa973f40a0aa74b189d0077539b5fe1c2c2`.
The scope fingerprint is
`1214c694bf72c1e6325a9e174d9e588c8329f5bc99f0e5f55148d7c81c178b1f`,
and the history materialization identity is
`192c68491b394890ef3986d583760f0f30c797e5aaf62f9849ce062ffeb1ee4d`.
The identity excludes timestamps and includes source, anchor, period, policy,
code and semantic tables. The loader checks the exact file set, hashes, row
counts, schemas, relations, scope fingerprint and recomputed identity.

## 12. CLI

`python -m renewables_permitting.pipeline history` accepts explicit source,
anchor extraction/scope, P2 main scopes, INE reference, dates, holdout, output
and extraction config identity. It has no `--execute-model` flag and no import
or call path to an agent. The exact invocation is in `docs/USER_GUIDE.md`.

## 13. Tests

Focal tests cover exact aliases, generic false positives, strict positive and
negative corroboration, wrong technology, territory, multi-project BOEs,
duplicate links, date/P2 boundaries, pre-match holdout exclusion, source
drift, absence of Tier 3, deterministic identity, loader validation, CLI model
incapability and the exposed 5/5 longitudinal regression.

## 14. W14 materialization

The validated output is
`runs/final-w14-anchor-pilot-20260807-20260820-v1/history-final/`. It contains only
`manifest.json`, `anchor_project_candidates.parquet`,
`project_history_candidates.parquet` and `historical_scope.csv`. Observed
counts are 40 roots, 71/7 tier links, 78 total links, 56 BOEs, 11 multi-root
BOEs, zero holdout and zero conflicts.

## 15. Reuse

The widest compatible paid parent is
`runs/final-tfm-p2-20240101-20260820-v1/extraction-main-03-recanonicalized-v2`.
Production `extraction-subset` created
`runs/final-w14-anchor-pilot-20260807-20260820-v1/history-reuse-input-final/` with
nine documents, 26 unique attempts, no reviews, no out-of-scope history and
zero blockers. Its identity is
`b9bc4cba36da26781063cfa2691d3ea9a235d734070129c68242aa8e91703415`.

## 16. Historical extract dry-run

The real dry-run used source v2, the 56-row scope and the reuse subset. It
reported nine compatible existing documents, 47 pending model documents,
zero deterministic pending, zero explicit retries and zero model calls
planned. No extraction output was created. A future run would require a new
output path and explicit human authorization before adding `--execute-model`.

## 17. Cost

The 42 newly paid W14 anchor documents used 50 requests, 461,833 input tokens,
135,865 output/thinking tokens, 610.069 seconds and USD 0.4782124. Applying
the observed mean per-document rate to 47 fresh historical documents gives
55.952 expected requests, 11.378 provider minutes and USD 0.5351424. Applying
the worst observed W14 document rate independently gives a conservative 61.595
provider minutes and USD 2.5688038. These are planning projections, not usage
authorization or limits.

## 18. Downstream integration

Classification: **MINIMAL UNION/MATERIALIZATION TOOLING REQUIRED**. Silver
accepts one loader-validated extraction snapshot. Existing
`extraction-subset` safely projects one parent but does not union the closed
anchor snapshot with a future historical snapshot. No Parquet concatenation
or new merge was implemented here. A small separately reviewed cumulative
snapshot operation is required before Silver; this is not a large redesign.

## 19. Daily update applicability

Classification: **REQUIRES SMALL FOLLOW-UP**. The lineage, deterministic
matching, BOE deduplication and extraction reuse mechanisms apply to new daily
anchors. The current CLI deliberately validates the final P2 main-scope
collection; a future daily operation needs a versioned current eligibility
scope contract rather than reusing that final-run-specific boundary.

## 20. Human authorization gate

Historical extraction remains **NOT AUTHORIZED**. The human gate must review
the 56-document scope, 47-call/cost projection, absence of holdout and source
conflicts, and the downstream minimal-union requirement. `main-04`, the two
`main-03` retries and holdout remain outside this block.
