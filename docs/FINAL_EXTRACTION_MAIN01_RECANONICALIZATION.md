# Final Extraction main-01 Recanonicalization

## 1. Blocker

The original `recanonicalize` path accepted only the approved historical
identity `67a0bd9d0759a322`. It called the historical loader unconditionally,
so active identity `4b54b89dbfe8640e` failed as incompatible. It also required
one automatic current extraction per document, no manual reviews and zero
blocking review rows. Therefore it could not replay the real incomplete
`main-01` snapshot.

Retrying only the seven failures was unsafe. Offline comparison demonstrated
that current deterministic code also changes three previously successful
outputs. A retry-only snapshot would consequently mix two deterministic
implementations under one apparent extraction identity.

## 2. Materialization design

The CLI retains the historical replacement path and adds a bounded active
cumulative mode when source and target both use the installed extraction
identity. The cumulative path:

1. verifies the source snapshot, active config, instructions, contract,
   validation version, policies, documents and optional scope;
2. validates optional versioned reviews against the original attempts;
3. replays every root persisted structured output, without a BOE allow-list;
4. appends a deterministic derived attempt for each successful replay while
   retaining every original attempt unchanged;
5. applies normal manual-review precedence;
6. preserves errors without structured output in the blocking queue; and
7. validates the staged snapshot through the contractual loader before an
   atomic rename to a new output.

The operation rejects corrupt payloads, incomplete lineage, source/config/
policy mismatch, duplicate attempt IDs, unknown review attempts, duplicate or
same-time conflicting reviews, unresolved semantic failures and existing
output paths. It contains no agent construction or provider-call path.

## 3. Identity/provenance

`EXTRACTION_CONFIG_ID` remains `4b54b89dbfe8640e`. The instructions SHA remains
`153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580`
and the contract SHA remains
`7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c`.

Before this change, config and canonicalization-policy metadata did not
distinguish the corrected implementation from the one that produced the
original snapshot. The new manifest records recanonicalization materialization
version `2` and SHA-256
`0593bfa34e5b11ff31c6dbd1f2b55bd94dbb0a62e3d9d379fa58a3372503d97f`
over the exact `canonicalization.py`, `recanonicalization.py` and
`validation.py` bytes. That fingerprint participates in derived attempt IDs
and `snapshot_identity_sha256`, without changing historical IDs or the
extraction contract.

The new snapshot identity is
`36244d4490fe8c01afbd761ecaf8a220bb3f3e17fadcf5371685d142458132ae`.

## 4. Full offline replay

The active source contained 250 original model attempts. Of these, 248 had a
persisted precanonical and canonical structured output. All 248 were inspected:

| Measure | Count |
| --- | ---: |
| Successful deterministic derivations | 247 |
| Semantically unchanged | 242 |
| Semantically changed | 5 |
| Replay validation failures resolved by human review | 1 |
| Unexpected change families | 0 |

The 247 derived attempts record zero requests and zero input, output and total
tokens. The cumulative snapshot retains the original usage totals: 286
requests, 2,391,308 input tokens, 776,142 output/thinking tokens and 3,167,450
total tokens. The original `attempts.parquet` physical SHA remains
`7d6bdf3c2beba698dea14cdc249f433a6b8c707cc9eb8b804664e41fcea83bd5`.

## 5. Changed outputs

| BOE | Deterministic change | Old summary | New summary | Expected family |
| --- | --- | --- | --- | --- |
| `BOE-B-2024-14806` | utility-public recognition | generic public-information action plus requested DUP | one specific DUP action submitted to public information | yes |
| `BOE-B-2024-27588` | continuous evidence | composite DUP evidence | continuous title passage for the same three submitted actions | yes |
| `BOE-B-2024-41345` | utility-public recognition | generic public-information action plus requested DUP | one specific DUP action submitted to public information | yes |
| `BOE-B-2025-39508` | continuous evidence | composite DUP evidence | continuous title passage for the same DUP action | yes |
| `BOE-B-2026-4032` | rectification canonicalization | five actions, including a duplicate modification request | four deterministic actions before the human temporal decision | yes |

No difference appeared outside the audited rectification/public-information
and utility-public recognition families. The hybrid-photovoltaic and bounded
generation-table fixes recovered failures without changing their stored
canonical payloads.

## 6. Semantic case recovery

| BOE | Offline outcome |
| --- | --- |
| `BOE-A-2026-14482` | valid hybrid photovoltaic generation context; recovered |
| `BOE-B-2024-29516` | nine independent installations retained; recovered |
| `BOE-B-2025-39508` | specific DUP action retained without a generic duplicate; recovered |
| `BOE-B-2026-4032` | deterministic replay valid, then human rectification-only selection applied |
| `BOE-B-2024-46241` | documentary validation still rejects the non-generation asset; human rejection applied |

## 7. Human dispositions

The existing JSON review contract records both inputs under
`config/manual_reviews/boe_ai/` with reviewer `human_tfm_review`, a real UTC
timestamp and lineage to the original source attempt.

- `BOE-B-2024-46241` is `rejected` with reason
  `out_of_scope_non_generation_geothermal_research_permit`. It has no current
  extraction.
- `BOE-B-2026-4032` is `manually_validated`. Its current event contains only
  `correccion_errores / rectificado / target=event`; none of the antecedent
  authorization, public-information or public-utility requests is redated.

## 8. Operational errors

Exactly two errors remain blocking and no retry was executed:

| BOE | Error | Status |
| --- | --- | --- |
| `BOE-A-2025-19878` | `ReadError` | operational retry pending |
| `BOE-B-2024-30150` | `TimeoutError` | operational retry pending |

## 9. New snapshot

The original snapshot remains immutable at:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01
```

The new loader-validated snapshot is:

```text
runs/final-tfm-p2-20240101-20260820-v1/
extraction-main-01-recanonicalized
```

It contains 250 documents, 497 attempts (250 original plus 247 derived), two
manual reviews, 247 current extractions and two blocking operational review
rows. Its manifest links the original manifest and attempts hashes, code
fingerprint, review identity and all artifacts.

## 10. Retry dry-run

An `extract --dry-run` against the new snapshot selected only
`BOE-A-2025-19878` and `BOE-B-2024-30150`: 248 documents were reusable, two
were pending and two new model calls would be required. Because
`--execute-model` was absent, planned and executed model calls were zero.
`BOE-B-2024-46241`, `BOE-B-2026-4032` and the other recovered semantic cases
were not selected.

The focused regression set for recanonicalization, pipeline, canonicalization,
document validation, reviews, attempts and finalization passed **474 tests**.
The complete offline suite then passed **1,118 tests** with no warnings.

## 11. Main-02 gate

`main-01` is now materially ready for a separate human decision on the two
operational retries. Gemini remains **NOT AUTHORIZED**, both retries remain
**NOT EXECUTED**, and `main-02` remains **NOT AUTHORIZED** until the retries are
resolved and `main-01` receives final human closure.
