# Final Corpus W14 Anchor Completion

## 1. Decision

The W14 non-holdout anchor is complete. Its final loader-valid snapshot is:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/extraction-final
```

It contains 48 accounted documents, 48 current extractions, zero blocking
reviews and 110 unique attempt IDs. The final decision is:

```text
PIVOT CONFIRMED — IMPLEMENT W14 BACKFILL
```

This work did not execute Gemini, BOE, another model, historical extraction,
`main-04`, either pending `main-03` retry, the holdout, Silver or Gold. It did
not implement the historical backfill.

## 2. Blocking document and evidence

The only pilot blocker was `BOE-B-2026-27232`. The persisted attempt contains
a complete structured output with zero events and classifies the document as
`not_relevant_for_generation_projects`.

The title calls the object an electrical-generation installation but names it
as `Sustitución de LAMT 25kV ... para conversion a D/C`. The body states the
purpose more precisely:

> Sustitución de tramo LAMT para convertirla en doble circuito y nuevo tramo de LSMT.

The publication contains a current prior-occupation action, but that action
concerns standalone distribution/grid infrastructure. It does not name an
electricity-generation plant. Therefore:

| Question | Finding |
| --- | --- |
| Source describes a generation project | NO |
| Source names a generation plant | NO |
| Source publishes a current administrative action | YES, for grid infrastructure |
| Model output represents the document correctly | YES |
| Validator was correct | NO |
| Disposition | `VALIDATION BUG` |

## 3. Root cause and deterministic correction

The post-model non-project guard already covered the audited
`grid-line-replacement` family when a title used the form `sustitución de tramo
de LAMT`. It did not recognize either the opening quotation mark after
`denominada` or the shorter form `sustitución de LAMT` used by this BOE.
Consequently, the general scope guard mistook generation vocabulary surrounding
the grid object for a named generation plant and rejected a correct non-relevant
model output.

The correction is deliberately narrow and BOE-independent. The existing
post-model expression now accepts an optional opening quotation mark and an
optional `tramo de` before `LAMT`, `LMT` or `línea`. It remains active only when
validating a model output that already says the document is non-relevant. It
does not preclassify documents and does not hide the positive contrast of an
explicitly named photovoltaic, wind or other generation plant.

The affected identity remains:

| Identity | Value / impact |
| --- | --- |
| Scope policy | `binary_named_generation_pre_model_guard_v4`, unchanged |
| Extraction config | `4b54b89dbfe8640e`, unchanged |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c`, unchanged |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580`, unchanged |
| Deterministic replay code SHA-256 | `099233062fe79e7e81144130224251484b32a21071bb082a682037260f050bbd` |

## 4. Exposure and risk

The sealed holdout was excluded before inspecting titles. The exact corrected
family occurs four times in the 4,989 non-holdout P2 model documents: three
already processed cases and one unprocessed case. Two of the processed cases
use `sustitución de tramo de LAMT`; the W14 blocker uses the quoted shorter
form. The unprocessed exposure uses the quoted `tramo de LAMT` form.

This is a known, bounded grid-infrastructure family. Systemic risk is **LOW**:
the expression requires the full generation-wrapper plus a named line
replacement and has positive named-generation contrasts.

## 5. Tests and replay

The new regression first failed with the expected `Posible falso negativo de
alcance`. After the patch:

```text
tests/extraction/test_validation.py                         52 passed
validator + recanonicalization focal suite                 74 passed
full repository suite                                   1,161 passed
```

The active cumulative dry-run and materialization replayed all eligible W14
structured outputs, not only the blocker:

| Replay measure | Result |
| --- | ---: |
| Source attempts | 62 |
| Eligible structured outputs | 48 |
| Successfully replayed | 48 |
| Semantically unchanged | 48 |
| Semantically changed | 0 |
| Semantic failures recovered | 1 |
| Unexpected changes | 0 |
| New deterministic attempts | 48 |
| Final attempts / unique IDs | 110 / 110 |
| Model requests added | 0 |

The model JSON for `BOE-B-2026-27232` did not need correction. Only its
deterministic validation outcome changed from blocking to valid non-relevant.
The focal offline replay outcome is **RESOLVED NON-RELEVANT**.

## 6. Final W14 anchor cohort

The final snapshot identity is:

```text
e7b7a5408f1420cf37ef4037502942fdd4e59536fa320b2ca16a4225e284623a
```

Production flattening, INE resolution and project grouping were executed only
in memory for analysis. No Silver or Gold snapshot was written.

| W14 anchor measure | Result |
| --- | ---: |
| Accounted / current / blocking | 48 / 48 / 0 |
| Generation documents | 26 |
| Non-relevant documents | 22 |
| Multi-project documents | 5 |
| Generation-project mentions | 40 |
| Potential generation roots | 40 |
| Roots in more than one anchor BOE | 0 |
| Technology distribution | 30 photovoltaic / 10 wind |
| Resolved provinces / autonomous communities | 14 / 8 |

The blocker adds one valid non-relevant selection. Relative to the pilot it
adds zero project mentions and zero roots, removes none and changes no
project-bearing output. The `W14_ANCHOR_COHORT` therefore remains at 40
potential roots.

## 7. Conservative historical recalculation

The final anchor was searched offline from 2022-01-01 through 2026-08-06 using
the established Tier 1 plus strict Tier 2 policy. Tier 3 remained excluded and
no fresh historical document was inspected manually.

| Historical measure | Result |
| --- | ---: |
| Tier 1 project-to-BOE links | 71 |
| Strict Tier 2 links | 7 |
| Total links | 78 |
| Unique historical BOE | 56 |
| Compatible reusable extractions | 9 |
| Fresh model documents | 47 |
| Projects with candidate history | 29 |
| Projects spanning at least 2 years | 25 |
| Projects spanning at least 3 years | 9 |
| Projects spanning at least 4 years | 4 |
| Earliest candidate year | 2022 |
| Median / maximum candidate span | 355 / 1,682 days |

These are candidate relationships, not confirmed complete legal lifecycles.
One BOE linked to several roots is still one document-level extraction.

## 8. Cost and final gate

The paid pilot covered 42 fresh anchor documents and cost USD 0.4782124 with
0.1695 provider hours. Applying its observed document-level rate to the 47
fresh historical candidates gives:

| Strategy measure | Projection |
| --- | ---: |
| Pilot plus future historical model documents | 89 |
| Future historical cost | USD 0.5351424 |
| Total W14 plus backfill cost | USD 1.0133548 |
| Future historical provider time | 0.1896 h |
| Total provider time | 0.3591 h |

The project yield, territorial and technological breadth, 29 projects with
candidate history and 47-document future model requirement justify the bounded
implementation effort. P2 remains a fallback only; `main-04` remains paused,
the two `main-03` retries remain unauthorized and the holdout remains sealed.

The next block may implement the versioned Tier 1 plus strict Tier 2 candidate
contract, lineage, document-level deduplication, validation, dry-run and safe
continuation. It does not yet authorize any historical Gemini call.

```text
PIVOT CONFIRMED — IMPLEMENT W14 BACKFILL
```
