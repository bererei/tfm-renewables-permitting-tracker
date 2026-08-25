# Final Corpus W14 Historical Failure Review

## 1. Historical snapshot

The input was the loader-valid active extraction snapshot:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/
history-extraction-authorized-v1
```

It accounted for 56 documents with 73 unique attempts, 50 current
extractions, six blocking documentary-validation reviews and no operational
blockers. The six persisted attempts all contained a structured pre-canonical
output and had already used two model requests. This review used only those
outputs and the local source snapshot; it made no model, BOE, web or holdout
call.

The contractual identity remained unchanged throughout the offline repair:

| Identity | Value |
| --- | --- |
| Scope policy | `binary_named_generation_pre_model_guard_v4` |
| Extraction config | `4b54b89dbfe8640e` |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| Document validation version | `25` |
| Corrected deterministic code SHA-256 | `c178e23ade7cdaf0214dacca57dfe8f614fa685bb4debe96fcda9f866a237b66` |

## 2. Six blockers

| BOE | Source result | Model / canonicalization | Validator | Primary disposition |
| --- | --- | --- | --- | --- |
| `BOE-B-2022-25212` | Thirteen literal HSF rows and a granted public-utility declaration for their shared evacuation | Correct / correct | Rejected all thirteen roots | `VALIDATION BUG` |
| `BOE-B-2022-33079` | The same thirteen literal HSF rows and current prior-occupation proceedings | Correct / correct | Rejected all thirteen roots | `VALIDATION BUG` |
| `BOE-B-2023-13726` | Three literal HSF rows and public information for the public-utility request | Correct / correct | Rejected all three roots | `VALIDATION BUG` |
| `BOE-B-2023-27607` | The same three HSF rows and a granted public-utility declaration | Incorrect `not_relevant` / correctly preserved | Correctly rejected the false negative | `MODEL OUTPUT REJECTED CORRECTLY` |
| `BOE-B-2024-3731` | Three literal HSF rows and current prior-occupation proceedings | Correct / correct | Rejected all three roots | `VALIDATION BUG` |
| `BOE-B-2026-5861` | Maintenance of a watercourse that crosses Don Rodrigo II; the plant is only a geographic reference | Correct `not_relevant` / correct | Mistook the title for a plant-cycle action | `POST_MODEL_SCOPE_CONTEXT BUG` |

Every generation event in the four naming cases contains a real plant root,
a current administrative action and literal evidence. The plants are not
infrastructure, aliases, files or hallucinated names. `BOE-B-2023-27607` also
contains the three plants in the same bounded table; its persisted structured
output omitted all events and therefore could not be repaired by deterministic
canonicalization alone. `BOE-B-2026-5861` names a real plant but does not
publish an administrative action about that plant.

## 3. Root causes

Two deterministic validation families were demonstrated.

1. The existing generation-table validator recognized `DENOMINACIÓN` tables
   but not the locally bounded three-column form
   `INSTALACIÓN / PROMOTOR / EXPEDIENTE`, even when immediately introduced as
   photovoltaic production installations. It therefore lost the shared
   generation context of otherwise literal HSF names.
2. The post-model scope exceptions did not cover the narrow pattern in which
   water-authority proceedings concern maintenance and conservation of a
   watercourse segment that merely crosses a named generation plant. The
   general guard saw the plant plus public-information wording and raised a
   false-negative warning.

The first family occurs in five historical sources: the four rejected naming
cases and `BOE-B-2023-27607`. The second occurs only in
`BOE-B-2026-5861`. None was silently present among the 50 initially valid
selections. The full replay produced no new semantic change, so systemic risk
is **LOW**.

## 4. Deterministic patches and human review

`validation.py` now accepts a plant name only when it is a row in the exact
three-column table and the immediately preceding local context declares
photovoltaic electricity-production installations. Rows beginning with grid
descriptors such as `SET`, `subestación`, `LAAT`, `LAT` or `línea` remain
excluded. Generic tables remain unsupported.

The watercourse rule is post-model only. It accepts an already produced
non-relevant extraction only for maintenance and conservation of a watercourse
segment explicitly described as crossing a park, plant or central. It does not
preclassify documents and does not hide a normal prior authorization for a
named generation plant.

The incorrect persisted output for `BOE-B-2023-27607` was resolved through
the versioned review:

```text
config/manual_reviews/boe_ai/BOE-B-2023-27607.json
```

The review is tied to attempt `a2415952da72463a80b66a0fa15384f5` and source
hash `913b7f465e50a6d649e6b8a73b2405f3a9a58284a64f0e995c165d9417a694e5`.
The responsible human reviewer approved one publication event containing the
three independent generation roots, one evacuation component linked to all
three roots and one granted public-utility declaration targeted only to that
component. The component and action are not duplicated by plant. The review
passed schema, lineage, documentary and domain validation. No retry is required
for any of the six documents.

## 5. Full replay

The active cumulative recanonicalization evaluated all 56 eligible persisted
outputs, not only the blockers.

| Measure | Result |
| --- | ---: |
| Source attempts | 73 |
| Eligible pre-canonical outputs | 56 |
| Successful deterministic derivations | 55 |
| Semantically unchanged derivations | 55 |
| Semantically changed derivations | 0 |
| Validation failures recovered | 5 |
| Replay failures resolved by review | 1 |
| Unexpected changes | 0 |
| Model requests / input tokens / output tokens added | 0 / 0 / 0 |

Individual outcomes are `RESOLVED RELEVANT` for the four naming cases,
`MANUALLY VALIDATED` for `BOE-B-2023-27607`, and
`RESOLVED NON-RELEVANT` for `BOE-B-2026-5861`.

A second complete dry-run required zero new derived attempts, reused all 55
existing deterministic derivations and reported zero semantic changes or
duplicate attempt IDs.

## 6. Anchor regression

The anchor snapshot was not modified. Its contractual loader and offline replay
confirm 48 accounted/current documents, zero blockers, 40 potential roots and
48 semantically unchanged outputs. The replay still recognizes the previously
resolved `BOE-B-2026-27232` validation family, but introduces no semantic
change.

## 7. Final historical snapshot

The new atomically published and loader-valid snapshot is:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/
history-extraction-final-v2
```

Its snapshot identity is
`8301be4e929cc9a029a94b496a8f564646f3c71b3e6f3cfa736046f69aef01e3`.

| Measure | Result |
| --- | ---: |
| Documents accounted / current | 56 / 56 |
| Blocking reviews | 0 |
| Attempt rows / unique IDs / duplicates | 128 / 128 / 0 |
| Automatic / manual current selections | 55 / 1 |
| Relevant generation documents | 54 |
| Non-relevant documents | 2 |
| Generation-asset mentions | 119 |
| Publication events | 114 |
| Documents with multiple publication events | 20 |
| Documents with multiple generation assets | 24 |
| Multi-root publication events | 4 |

Compared with the preceding `history-extraction-final` snapshot, the only
semantic extraction change is the approved representation of
`BOE-B-2023-27607`; the other 55 current extractions are unchanged.

## 8. Retrieval-link validation

The 78 candidate relationships were reevaluated using the documented
production-normalized plant name/key plus technology criterion. A non-relevant
historical extraction is a false positive; a generation document without the
same extracted root remains ambiguous for later grouping.

| Disposition | Links |
| --- | ---: |
| Confirmed related | 41 |
| False positive | 2 |
| Ambiguous / needs grouping | 35 |

The only change from the pre-repair evaluation is
`BOE-B-2026-5861`, now correctly measurable as a Tier 1 false positive rather
than an ambiguous link without a current extraction. Ambiguous links are not
extraction blockers and were not forced to confirmed.

## 9. Union requirements

The anchor and history snapshots currently have zero BOE overlap and zero
attempt-ID overlap. They share the same extraction config, contract,
instructions and validation identity. Their prospective union contains 104
documents and 238 attempts.

Classification: **MINIMAL UNION TOOLING REQUIRED**. The next block needs one
contractual union operation that:

- loads and validates both complete snapshots;
- requires compatible extraction identities and source lineage;
- detects BOE overlap, deduplicates only semantically identical compatible
  histories and fails closed on any conflict;
- combines complete documents, attempts and manual-review histories through
  the existing normalizers and attempt-uniqueness checks;
- recomputes current selection and review queue;
- publishes the six extraction artifacts atomically with both parent snapshot
  identities in the manifest, then reloads the result.

No Parquet should be concatenated manually. This tooling was not implemented
in this block, and neither Silver nor downstream/Gold was run.

## 10. Final AI cost

| Scope | Real Gemini cost |
| --- | ---: |
| W14 anchor | USD 0.4782124 |
| W14 history | USD 1.1341233 |
| Final W14 total to date | **USD 1.6123357** |
| Additional cost required by these blockers | USD 0 |

Older P2 calls remain development/stabilization cost and are not included in
the final W14 corpus cost.

## 11. Next gate

The historical extraction is closed with zero blockers. The holdout remains
sealed and unexecuted. `main-04`, old `main-03` retries, union, Silver and Gold
were not executed.

```text
HISTORY CLOSED — READY FOR ANCHOR+HISTORY UNION
```
