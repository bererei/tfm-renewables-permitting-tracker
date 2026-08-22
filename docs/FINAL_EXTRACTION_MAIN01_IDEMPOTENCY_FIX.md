# Final Extraction main-01 Idempotency Fix

## 1. Defect

The first final rematerialization at
`runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01-final`
contained 748 attempt rows but only 501 unique `attempt_id` values. There were
247 duplicated IDs affecting 494 rows. The snapshot is retained as historical
evidence but is not contractual input or output.

All 247 pairs were inspected systematically. Each pair had the same BOE,
parent attempt, document hash, extraction identity, deterministic provenance,
status, canonical payload and other stable fields. Only `extracted_at` and
`recanonicalized_at` differed. The defect is classified as **DUPLICATE
DERIVATION EQUIVALENT**; no semantic collision was found.

## 2. Root cause

Materialization version 2 already gives a deterministic derived attempt a
stable ID calculated from its parent attempt ID, source document SHA-256,
target extraction config, deterministic code SHA-256 and materialization
version. That identity algorithm was correct and remains unchanged.

Active cumulative recanonicalization rebuilt every eligible root output with a
new execution timestamp and appended all rebuilt rows to the source history.
It did not first reconcile stable derived IDs already present in the source.
The snapshot loader recomputed selections and manifests but did not enforce
`attempt_id` uniqueness, so the duplicated history passed its final staged
load.

## 3. Idempotency invariant

For the same root attempts, documents, extraction identity, deterministic code
and reviews:

```text
recanonicalize(X) -> Y
recanonicalize(Y) -> semantically Y
```

An already persisted compatible derivation is now reused as a complete
historical row. Its original timestamps are preserved. A new row is appended
only when its stable deterministic ID is absent.

Compatibility compares every stable attempt field. Execution timestamps and
the immediate execution-container label do not define derivation identity. If
the same deterministic ID has a different stable field, recanonicalization
fails closed and reports the ID plus a bounded field sample; it never chooses
one row or applies blind deduplication.

## 4. Loader/publication safeguards

A central uniqueness check now rejects duplicated `attempt_id` values with at
most five sample IDs. It is applied when validating resume attempts, loading a
contractual extraction snapshot, before extraction publication, while planning
active recanonicalization and before recanonicalization publication.

The publication gate runs before selection and before staging is atomically
renamed. Consequently, even an internal caller that constructs duplicate rows
cannot publish an extraction snapshot.

After the change, the contractual loader rejects the retained invalid snapshot
with `PipelineError: Extraction snapshot attempts contains duplicate
attempt_id values`.

## 5. Tests

Four core regression tests were written RED first and initially all failed. A
fifth regression records successful retry preservation. Together they cover:

- two consecutive active cumulative recanonicalizations;
- reuse of equivalent derived attempts with preserved timestamps, reviews and
  usage;
- preservation of an explicit successful retry exactly once across subsequent
  recanonicalizations;
- fail-closed handling of a semantic collision under an existing ID;
- loader rejection of duplicated IDs; and
- rejection before atomic publication when duplicate rows are constructed.

The recanonicalization file passes 22 tests. The broader focal set for
recanonicalization, pipeline, attempts, reviews and runner finalization passes
259 tests. The complete offline suite passes **1,123 tests** in 109.74 seconds.

## 6. Invalid historical snapshot

The following snapshot remains untouched:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01-final
```

It has 748 rows, 501 unique IDs, 247 duplicated IDs and 494 duplicated rows.
The patched loader rejects it. It was not repaired, deduplicated, deleted or
used as input for the valid final materialization.

## 7. Correct input snapshot

The correct cumulative input was:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01-retry-01
```

Its loader-validated history has 499 rows and 499 unique IDs. It contains all
497 prior rows plus exactly one successful retry attempt for each authorized
BOE: `BOE-A-2025-19878` and `BOE-B-2024-30150`. It has 249 current extractions,
one human rejection and no blocking review rows.

## 8. Offline rematerialization

The dry-run used source v2, the versioned `main-01` scope, config
`4b54b89dbfe8640e`, the inherited versioned reviews and materialization version
2. It reported:

| Measure | Count |
| --- | ---: |
| Input attempt rows | 499 |
| Compatible derived attempts reused | 247 |
| New derived attempts required | 2 |
| Output attempt rows | 501 |
| Output unique attempt IDs | 501 |
| Duplicate attempt IDs | 0 |
| Model calls | 0 |

The two new derived attempts correspond only to the two successful operational
retries. Both record zero derived model usage.

## 9. Final snapshot

The new loader-validated snapshot is:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01-final-v2
```

It contains 250 documents, 501 unique attempt rows, 249 current extractions,
one rejection and zero blocking reviews. `BOE-A-2025-19878` is successful;
`BOE-B-2024-30150` is a valid non-relevant result; `BOE-B-2024-46241` remains
rejected without a current extraction; and `BOE-B-2026-4032` remains the
rectification-only manual selection without redated antecedents. The recovered
results for `BOE-A-2026-14482`, `BOE-B-2024-29516` and `BOE-B-2025-39508`
remain valid.

Config `4b54b89dbfe8640e`, instructions SHA
`153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580`,
contract SHA
`7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c`
and deterministic code SHA
`0593bfa34e5b11ff31c6dbd1f2b55bd94dbb0a62e3d9d379fa58a3372503d97f`
remain unchanged. Rematerialization added zero requests and zero input/output
tokens.

## 10. Second-pass idempotency proof

A second dry-run used `extraction-main-01-final-v2` as input and a nonexistent
output path. It reported 501 input rows, 249 compatible derivations reused,
zero new derivations, zero semantic changes, 501 output rows, 501 unique IDs,
zero duplicates and zero model calls. No second snapshot was created.

## 11. Main-02 gate

`main-01` is contractually closed and ready for human review. `main-02` remains
**NOT AUTHORIZED**. The holdout remains **NOT EXECUTED**. This block made zero
BOE, Gemini, other model or web calls; it did not repeat either operational
retry.
