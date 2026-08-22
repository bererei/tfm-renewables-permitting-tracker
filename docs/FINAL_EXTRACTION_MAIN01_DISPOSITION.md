# Final Extraction main-01 Disposition

## 1. Scope and status

This REQUIRED, offline review closes the two pending semantic decisions for
`main-01` and prepares—but does not authorize—the two operational retries. It
uses HEAD `25ddc8826b89ebf19f41ec5a68162836572b53c8` and the immutable snapshot:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01
```

The snapshot passes the contractual loader and still contains 250 documents,
250 attempts, 243 current extractions, no manual reviews and seven blocking
review rows. No Gemini or BOE call was made, no retry was executed and no
artifact under `runs/` was changed.

Disposition status: **HUMAN CASES RESOLVED — FINAL CUMULATIVE
RECANONICALIZATION BLOCKED**.

## 2. BOE-B-2024-46241

**SOURCE DESCRIBES GENERATION PROJECT: NO.**

The source is a correction to the admission of the mining-law research permit
`CIBELES CENTRO-SUR` for geothermal resources. The operative correction changes
the affected mining-grid count from 121 to 110. The referenced public
information concerns the restoration plan. The source does not identify a
named electricity-generation plant, authorize a generation installation or
establish one as the object of the publication.

The persisted model output treats `CIBELES CENTRO-SUR` as a generation asset.
With the current correction precedence applied, documentary validation rejects
that asset because the source does not name it as a generation plant. This is
the intended domain safeguard, not a remaining parser defect.

Decision:

```text
ACCEPT_VALIDATOR_REJECTION
reason = out_of_scope_non_generation_geothermal_research_permit
```

The existing contractual closure mechanism is a versioned manual review tied
to attempt `cde570883d314230af0ff882e4eb070b`, with `review_status=rejected`, a
real reviewer, notes recording the reason above and a real UTC review time.
`corrected_extraction` is not required for `rejected`. The normal manual-review
loader validates source hash, attempt, extraction config and document
validation identity; the selection and queue rules then account for the
document as rejected and remove it from the blocking queue. No new reason code
or correction-registry entry is needed.

## 3. BOE-B-2026-4032

The current publication states that the earlier BOE announcement is being
rectified. Its substantive operative change is to include parcel ownership
already represented in the published affected-rights list and parcels omitted
from the earlier BOE by error.

The title repeats the earlier procedure: public information for requested
modifications of the prior administrative authorization, construction
authorization and declaration of public utility. Those requests identify the
announcement being corrected; the body does not issue a new authorization,
open a new independent public-information procedure or make a new public-
utility decision.

Decision:

```text
APPROVE RECTIFICATION-ONLY CURRENT EVENT
```

The current publication event must therefore contain only:

```text
correccion_errores / rectificado / target=event
```

The referenced public-information, authorization-modification and public-
utility requests are antecedents and must not acquire the rectification's 2026
publication date. The persisted structured output contains sufficient plant,
event and correction evidence. After current canonicalization, removing the
antecedent actions produces a document-valid extraction in memory.

Because the deterministic canonicalizer deliberately does not infer this
temporal human judgment, closure requires a versioned `manually_validated`
review tied to attempt `ae5811ffa7ce49c9bf454d7c49f31f34`. Its corrected
extraction retains the event and plant but only the rectification action above.
No new Gemini call is required.

## 4. Other semantic blocker cases

The current source, persisted precanonical output and production code were
replayed offline again:

| BOE | Result | Model calls |
| --- | --- | ---: |
| `BOE-A-2026-14482` | PASS; explicit hybrid photovoltaic generation context is accepted | 0 |
| `BOE-B-2024-29516` | PASS; all nine independent generation rows retain bounded table context | 0 |
| `BOE-B-2025-39508` | PASS; the specific public-utility action validates without a redundant generic action | 0 |

The five-case replay yields four valid extractions plus the accepted domain
rejection above. None of the five semantic cases requires Gemini.

An in-memory validation of the five manual dispositions—four
`manually_validated` outputs and the one rejection—produced 247 current
extractions and left only these queue rows:

```text
BOE-A-2025-19878
BOE-B-2024-30150
```

This proves the review statuses and corrected payloads are contract-valid; it
is not the recommended final provenance for the three purely deterministic
repairs. No review file or extraction snapshot was written by that diagnostic.

## 5. Operational retry candidates and dry-run

Only the following two BOEs are retry candidates:

| BOE | Historical error | Historical attempt ID |
| --- | --- | --- |
| `BOE-A-2025-19878` | `ReadError` | `3d0cac28af8d403bb5dbe0c109871989` |
| `BOE-B-2024-30150` | `TimeoutError` | `f359443003e543ac851870fa0863c355` |

The real CLI exposes the repeatable option `--retry-error-boe`. It requires
`--documents`, a new `--output-dir` and
`--expected-extraction-config-id`; cumulative history is supplied with
`--attempts`, the bounded cohort with `--scope`, and real calls remain disabled
unless `--execute-model` is present.

The offline dry-run used the versioned `main-01` scope and omitted
`--execute-model`. Its plan was:

| Measure | Result |
| --- | ---: |
| Scope documents | 250 |
| Compatible existing | 248 |
| Explicit error retries | 2 |
| Previous successes selected | 0 |
| Semantic/validation cases selected | 0 |
| Source/config mismatches | 0 |
| Model calls required if authorized | 2 |
| Model calls planned by this dry-run | 0 |

The dry-run explicitly reported that no model, network or write execution was
performed.

## 6. Historical-attempt preservation

The extraction stage copies the full compatible attempt history into fresh
staging before execution, appends one new attempt per explicitly selected BOE,
rejects duplicate new IDs and verifies before publication that every historical
attempt ID is still present and that the row count increased exactly by the
execution count. The selection and review rules then determine the current
result without deleting the failed predecessor.

Consequently, a later authorized execution must contain:

```text
3d0cac28af8d403bb5dbe0c109871989  ReadError
+ new attempt for BOE-A-2025-19878

f359443003e543ac851870fa0863c355  TimeoutError
+ new attempt for BOE-B-2024-30150
```

## 7. Exact future retry command

```bash
# DO NOT RUN — GEMINI RETRIES NOT YET AUTHORIZED
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01 \
  --scope config/evaluation/final_p2_execution_scopes_v1/main-01.csv \
  --retry-error-boe BOE-A-2025-19878 \
  --retry-error-boe BOE-B-2024-30150 \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01-retry-01 \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --execute-model
```

This command was not executed. Its output path is currently absent.

## 8. Post-retry materialization and new blocker

If both retries succeed, their fresh snapshot would preserve 252 attempts,
select 245 automatic current extractions and leave the five semantic reviews
pending. The existing review contract can then validate the four corrected
extractions and the rejection described above; in memory that disposition
leaves no semantic review row.

However, a final cumulative snapshot cannot yet be published reproducibly by
the current public CLI:

1. the deterministic patch also changes the canonical payload of three
   already-successful attempts: `BOE-B-2024-14806`, `BOE-B-2024-27588` and
   `BOE-B-2024-41345`;
2. `pipeline extract` deliberately reuses compatible successes and does not
   recanonicalize their persisted JSON;
3. `pipeline recanonicalize` accepts only the separately registered historical
   freeze identity `67a0bd9d0759a322`, while `main-01` uses the active identity
   `4b54b89dbfe8640e`;
4. its dry-run against `main-01` therefore fails closed with
   `Historical extraction configuration is incompatible`; even after that
   identity gate, batch replay requires a complete, review-free, automatic
   source snapshot.

Using manual reviews for deterministic changes to already-valid attempts would
misclassify deterministic derivation as human correction. Manually joining
Parquets or bypassing the approved identity registry would violate the
documented operational contract.

Before authorizing the retries, a separate minimal REQUIRED block must provide
a controlled cumulative materialization path that:

- explicitly selects current-identity attempts for deterministic replay;
- accepts the incomplete `main-01` source while preserving every original
  attempt and its lineage;
- records the three purely deterministic repairs as derived attempts, applies
  the rectification-only human correction and records the geothermal case as
  rejected;
- appends the two later retry attempts;
- rebuilds selection and review state and publishes atomically to a new path;
- proves 250 documents accounted, 249 current extractions, one rejected case
  and zero blocking reviews if both retries succeed.

No such materialization was implemented or executed in this disposition task.

## 9. Gate

- Human disposition for `BOE-B-2024-46241`: **CLOSED**.
- Human temporal disposition for `BOE-B-2026-4032`: **CLOSED**.
- Three other semantic blocker cases: **RESOLVED OFFLINE**.
- Operational retry candidates: **EXACTLY TWO; NOT AUTHORIZED**.
- `main-02`: **NOT AUTHORIZED**.
- Final cumulative `main-01`: **BLOCKED BY MATERIALIZATION PATH**.

Recommendation: **do not authorize the two Gemini retries until the minimal
cumulative recanonicalization/materialization blocker is resolved and reviewed**.
