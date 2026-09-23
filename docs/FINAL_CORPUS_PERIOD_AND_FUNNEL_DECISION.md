# Final Corpus Period and Funnel Decision

## 1. Purpose

This read-only audit compares four temporal scopes inside the already
materialized source snapshot:

```text
runs/final-corpus-preflight-20220101-20260820-v2/source/
```

It evaluates the four candidate rules from
`FINAL_CORPUS_CANDIDATE_FUNNEL_AUDIT.md`, their false-negative risk, the
operational cost of each period and the contractual effect of changing the
scope classifier. It performs no source, extraction, pipeline or model run and
does not change the final period. Its recommendations remain subject to human
approval.

The closed recommendation package is:

```text
period: P3 — 2025-01-01 through 2026-08-20
classifier patch: R1 + R3 only
source drift: current official source wins; changed hash is not reusable
reuse: strict aggregate config identity; no compatibility exception
source redownload: no
model calls now: no
```

## 2. Inputs

The audit loaded the source Parquet files and the frozen 140-document
extraction snapshot through local pandas/package boundaries. It inspected the
active contracts, configuration and selection code. All calculations were in
memory.

| Input | Identity or size |
| --- | --- |
| Git HEAD privado histórico | `587141137be5d25dbcaeae6cffb38f61103f7a1c` |
| Source documents | 25,347 |
| Source BOE items | 328,629 |
| Source document identity | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| Candidate policy | `title_keywords_v1` / `79289feae5d557be` |
| Current reusable extractions | 133 |
| Current deterministic documents | 1,602 |
| Current `MODEL_REQUIRED` | 23,611 |
| Quarantined source conflict | 1 |
| Prior conservative aggregate | 8,244 `MODEL_REQUIRED` |

The source universe again reconciles as:

```text
25,347 = 133 reusable + 1,602 deterministic + 23,611 model + 1 conflict
```

## 3. Period scenarios

The end date is fixed. No 2020 or 2021 scenario was inspected.

| Scenario | Start | End | Approximate longitudinal span |
| --- | --- | --- | --- |
| P0 | 2022-01-01 | 2026-08-20 | 4 years 8 months |
| P1 | 2023-01-01 | 2026-08-20 | 3 years 8 months |
| P2 | 2024-01-01 | 2026-08-20 | 2 years 8 months |
| P3 | 2025-01-01 | 2026-08-20 | 1 year 8 months |

These are publication windows, not complete project lifetimes. All four have
left censoring for projects whose first relevant publication predates the
start date.

## 4. Current funnels

Before any new rule, the measured funnels are:

| Scenario | BOE items | Canonical documents | Reusable | Deterministic | Model | Conflict | Model rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P0 | 328,629 | 25,347 | 133 | 1,602 | 23,611 | 1 | 93.15% |
| P1 | 262,627 | 23,107 | 123 | 1,346 | 21,637 | 1 | 93.64% |
| P2 | 196,296 | 19,489 | 91 | 1,042 | 18,355 | 1 | 94.18% |
| P3 | 120,853 | 11,231 | 63 | 726 | 10,441 | 1 | 92.97% |

The annual components used to construct those scenarios are:

| Year | BOE items | Documents | Reusable | Deterministic | Model | Conflict |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 66,002 | 2,240 | 10 | 256 | 1,974 | 0 |
| 2023 | 66,331 | 3,618 | 32 | 304 | 3,282 | 0 |
| 2024 | 75,443 | 8,258 | 28 | 316 | 7,914 | 0 |
| 2025 | 75,405 | 7,152 | 25 | 415 | 6,712 | 0 |
| 2026 through 20 August | 45,448 | 4,079 | 38 | 311 | 3,729 | 1 |

Reducing the period alone therefore does not solve the candidate problem.
Even P3 sends 92.97% of canonical documents to the model under the current
classifier.

## 5. Rule simulations

### Reproducibility finding

R1 and R3 are reproducible from the prior report: their documentary
membership and annual totals match exactly. R2 and R4 were recorded as prose
conditions plus aggregates, not as an executable mask or a versioned list of
BOE IDs. A literal conservative reconstruction does not reproduce their
reported membership:

| Rule | Prior reported model count | Literal reconstruction | Result |
| --- | ---: | ---: | --- |
| R1 — water body | 12,182 | 12,182 | Exact |
| R2 — water object | 9,486 | 9,793 | Mismatch: +307 |
| R3 — transport/coast | 3,086 | 3,086 | Exact |
| R4 — procurement variants | 35 | 33 | Mismatch: -2 |

The prior P0 aggregate of 8,244 is internally consistent with the recorded
aggregate reductions, but exact R2/R4 document membership cannot be recovered
from the report. The literal four-rule reconstruction gives 8,231 instead.
This is not treated as production behavior and is not used to approve R2 or
R4.

### Literal reconstruction by period

The table below satisfies the requested comparative simulation while keeping
the specification gap visible. Reductions are incremental in rule order.

| Scenario | Model before | R1 reduction | After R1 | R2 incremental | After R2 | R3 incremental | After R3 | R4 incremental | Final literal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P0 | 23,611 | 12,182 | 11,429 | 110 | 11,319 | 3,080 | 8,239 | 8 | 8,231 |
| P1 | 21,637 | 12,145 | 9,492 | 102 | 9,390 | 2,361 | 7,029 | 6 | 7,023 |
| P2 | 18,355 | 11,713 | 6,642 | 85 | 6,557 | 1,670 | 4,887 | 2 | 4,885 |
| P3 | 10,441 | 6,600 | 3,841 | 59 | 3,782 | 1,006 | 2,776 | 0 | 2,776 |

Incremental reductions as a percentage of the initial model population are:

| Scenario | R1 | R2 literal | R3 | R4 literal |
| --- | ---: | ---: | ---: | ---: |
| P0 | 51.59% | 0.47% | 13.04% | 0.03% |
| P1 | 56.13% | 0.47% | 10.91% | 0.03% |
| P2 | 63.81% | 0.46% | 9.10% | 0.01% |
| P3 | 63.21% | 0.57% | 9.64% | 0.00% |

R2 contributes little after R1. R4 contributes nothing in P3. Their
specification ambiguity is therefore not justified by operational benefit.

## 6. Known-positive recall

Known positives were reconstructed from the frozen, validated
`current_extractions`, not from all development documents.

| Scenario | Known positives | R1 retained | R1+R2 retained | +R3 retained | +R4 retained |
| --- | ---: | ---: | ---: | ---: | ---: |
| P0 | 72 | 72 | 72 | 72 | 72 |
| P1 | 69 | 69 | 69 | 69 | 69 |
| P2 | 43 | 43 | 43 | 43 | 43 |
| P3 | 29 | 29 | 29 | 29 | 29 |

Observed known-positive recall is 100% for every rule and cumulative
combination. This is a regression check, not proof of complete recall.

## 7. Known negatives

The frozen dataset contains 65 known negatives, of which 61 fall inside P0.
Rule sensitivity was evaluated independently of their current reusable status.
The R2/R4 columns refer to the literal reconstruction and are complementary
evidence only.

| Scenario | Known negatives | R1 caught | R1+R2 caught | +R3 caught | +R4 caught | Remaining after all |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P0 | 61 | 8 | 11 | 17 | 17 | 44 |
| P1 | 54 | 8 | 10 | 16 | 16 | 38 |
| P2 | 48 | 8 | 9 | 15 | 15 | 33 |
| P3 | 34 | 5 | 5 | 11 | 11 | 23 |

Standalone observed catches are R1=8, R2=8, R3=6 and R4=0. The approved
R1+R3 pair catches 14/61 (22.95%) in P0 and 11/34 (32.35%) in P3. These rates
do not estimate performance on the unlabeled universe.

## 8. Exclusion audit

Before inspecting results, the audit fixed this sample design with seed
`20260821`:

- R1: 3 documents per year, 15 total;
- R2: 2 marginal and 2 R1-overlap documents per year, 20 total;
- R3: 3 documents per year, 15 total;
- R4: census of all 33 documents in the literal model population.

This gives 83 rule-level reviews over 82 unique documents; one R1/R2-overlap
document is intentionally reviewed in both strata. The size is sufficient to
look for gross family-definition failures and recurring counterexamples, but
not to estimate a low false-negative probability statistically. Titles,
section/department metadata and only the source passages needed to understand
the domain were reviewed.

| Rule stratum | Reviewed | Clearly irrelevant | Potentially relevant | Ambiguous |
| --- | ---: | ---: | ---: | ---: |
| R1 | 15 | 15 | 0 | 0 |
| R2 marginal/overlap | 20 | 20 | 0 | 0 |
| R3 | 15 | 15 | 0 | 0 |
| R4 literal census | 33 | 33 | 0 | 0 |
| **Total decisions** | **83** | **83** | **0** | **0** |

Representative findings include:

- R1: groundwater concessions for irrigation, discharge authorizations,
  riverside tree planting, a pontoon and dam-maintenance works;
- R2 marginal: irrigation modernization, public-hydraulic-domain works and
  discharge permits outside the named basin bodies;
- R3: road, railway, beach-service and port concessions; one environmental
  report concerned a standalone transmission line/substation, not a named
  generation project;
- R4: procurement dates, tenders, offer opening and contracted maintenance or
  supplies rather than plant lifecycle acts.

No sampled document was classified as potentially relevant or ambiguous.
This sample is classifier-development evidence and is permanently ineligible
for the final holdout.

## 9. Hydro safeguards

There is one validated hydroelectric positive:

```text
BOE-B-2023-19087
```

Its title explicitly states that the water use is destined for `producción de
energía eléctrica`, and its extracted generation type is `hidroelectrica`.
R1 and the literal R2 preserve it. All 75 frozen positives, including this
one, are retained.

R1 must preserve a document whenever the title contains any explicit
`hidroeléctric*` wording or `producción de energía eléctrica`, in addition to
the existing explicit-generation pattern. This exception is material: three
unlabeled basin notices mention hydroelectric use and would otherwise be
excluded.

Conceptual risk remains where a basin title omits the generating purpose while
the body text establishes it. The random audit found no such case, but cannot
prove absence across 12,182 exclusions. The patch therefore still requires
synthetic hydro counterexamples and a larger post-patch exclusion audit before
model execution.

## 10. Approved-rule candidates

| Rule | Decision | Reason |
| --- | --- | --- |
| R1 | **APPROVE FOR PATCH** | Exact reproducibility, 12,182 model reduction, 15/15 sample clearly irrelevant, 0/75 positive impact; explicit hydro exception required |
| R2 | **REVISE BEFORE PATCH** | Prose does not reproduce recorded membership; only 110 literal marginal documents after R1; avoid broadening water exclusions without a versioned exact predicate |
| R3 | **APPROVE FOR PATCH** | Exact reproducibility, 3,086 model reduction, 15/15 sample clearly irrelevant and 0/75 positive impact |
| R4 | **REVISE BEFORE PATCH** | Census is clearly irrelevant, but membership does not reproduce and marginal benefit is 8 in P0 and 0 in P3 |

The minimum approved set is therefore:

```text
R1 + R3
```

It removes 15,268 current model documents in P0—99 fewer than the prior
four-rule aggregate—without taking the specification risk of R2/R4.

## 11. Final simulated funnels

### Analytical funnel with currently compatible reuse

| Scenario | Documents | Reusable | Current deterministic | Newly deterministic R1+R3 | Final model | Model rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P0 | 25,347 | 133 | 1,602 | 15,268 | 8,343 | 32.92% |
| P1 | 23,107 | 123 | 1,346 | 14,512 | 7,125 | 30.83% |
| P2 | 19,489 | 91 | 1,042 | 13,387 | 4,968 | 25.49% |
| P3 | 11,231 | 63 | 726 | 7,607 | 2,834 | 25.23% |

These rows preserve current compatible reuse only to isolate the effect of
R1+R3. The recommended patch changes the aggregate extraction config identity,
so this is not the execution plan.

### Execution funnel under the recommended strict identity policy

Under Option A in section 17, automatic reuse becomes zero. Formerly reusable
documents are evaluated again by the current and new deterministic rules; the
remainder becomes model work.

| Scenario | Documents | Automatic reuse | Current deterministic | Newly deterministic R1+R3 | Final model | Conflict after approval |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P0 | 25,347 | 0 | 1,619 | 15,280 | 8,448 | 0 |
| P1 | 23,107 | 0 | 1,360 | 14,524 | 7,223 | 0 |
| P2 | 19,489 | 0 | 1,053 | 13,399 | 5,037 | 0 |
| P3 | 11,231 | 0 | 734 | 7,616 | 2,881 | 0 |

Only 46 of P3's 63 formerly reusable documents would require a new model call;
17 are deterministic under the approved policy. The additional model document
is `BOE-A-2026-11850`, after the human source-drift approval turns it from a
quarantined conflict into a new official-source extraction. This small cost
favors the strict contract over a new compatibility layer.

## 12. Longitudinal value

| Scenario | Longitudinal value | Left censoring | Representativeness | Operational assessment |
| --- | --- | --- | --- | --- |
| P0 | Best chance of observing repeated publications and longer trajectories | Lowest of the four, still material | Broadest observed period | Excessive cost |
| P1 | Clearly stronger than P2/P3 for multi-step trajectories | Material | Strong multi-year coverage | Still excessive cost |
| P2 | Three publication years can show meaningful repeated decisions | Higher | Includes anomalous 2024 water-notice volume | Threatens delivery |
| P3 | Two publication years can still show repeat publications and chronology | Highest | Final-period view, not a complete lifecycle cohort | Minimum viable longitudinal option |

No scenario supports claiming complete project histories. P3 preserves a
multi-year publication view, but findings must explicitly acknowledge left
censoring and the truncated administrative history.

## 13. Operational feasibility

The observed 226.94 documents per summed provider-hour is used only as an
orientation. It is not contractual, is not a wall-clock promise and excludes
review, incidents, corrections, Silver/Gold, dashboard completion, deployment
and holdout.

| Scenario | Final model under strict identity | Orientative provider-hours | Feasibility |
| --- | ---: | ---: | --- |
| P0 | 8,448 | 37.23 | **RED** |
| P1 | 7,223 | 31.83 | **RED** |
| P2 | 5,037 | 22.20 | **RED** |
| P3 | 2,881 | 12.69 | **AMBER** |

P2 still implies roughly 5,000 model outputs plus their automated and human
review only days before the data-model freeze. P3 materially reduces that
load, but 2,881 model outputs remain substantial; it is AMBER, not GREEN.
Immediate review gates, scope discipline and incident margin remain necessary.

## 14. Period recommendation

```text
RECOMMENDED PERIOD: P3 — 2025-01-01 through 2026-08-20
```

P0 and P1 are red. P2 retains better longitudinal value but remains red once
review and all remaining delivery work are considered. Under the stated
selection rule, P3 is therefore the appropriate fallback: it retains two
publication years, reduces model work materially and is the only AMBER option.

This is a recommendation for human approval, not a change to the final period.
The existing source snapshot can supply P3 through a deterministic, reviewed
scope over its manifest-bound documents; no manual Parquet merge is needed.

## 15. Source drift

For `BOE-A-2026-11850`, the exact difference remains:

```text
development: de la la sección
current:     de la sección
```

The current official source hash is contractually different even though the
change has no relevant extraction semantics. The approved recommendation is:

```text
CURRENT OFFICIAL SOURCE WINS FOR FINAL CORPUS
development freeze remains unchanged
source hash change -> no automatic reuse
new source/extraction identity -> re-extract and revalidate
```

This is **APPROVE** under current tooling. Selection already joins attempts on
both BOE ID and `source_document_sha256`; the changed document cannot reuse an
old attempt automatically. No source or extraction artifact is modified here.

## 16. Classifier identity

`SCOPE_CLASSIFICATION_POLICY` is currently an explicit member of
`EXTRACTION_CONFIG`, and `EXTRACTION_CONFIG_ID` is the stable hash of the full
configuration. The active pair is
`binary_named_generation_pre_model_guard_v3` / `8158661f76a31c87`.
Existing attempt selection requires exact config ID, source hash and validation
version.

Changing `_scope_guard_from_document()` must therefore change the extraction
config ID under the current contract. This is not merely a model eligibility
filter: the same guard is also applied during canonicalization and document
validation and can force a model output to non-relevant. Model semantics and
scope policy cannot be declared compatible without re-evaluating the document.

Conceptually:

- model/instruction/schema/canonicalization settings describe extraction
  semantics;
- the scope policy describes eligibility and a deterministic terminal result;
- today both intentionally contribute to one aggregate extraction identity.

A separate `scope_classification_policy_id` could make compatibility more
expressive, but would also require a new compatibility contract, manifest
fields, selection logic and migration tests. The 46 P3 calls it would save do
not justify that architecture before August delivery. Keep the aggregate ID
and record the updated scope policy explicitly in the extraction manifest.

## 17. Extraction reuse

| Option | Correctness | Reproducibility | Risk/change | Calendar impact |
| --- | --- | --- | --- | --- |
| A — new config invalidates reuse | Matches the active exact-identity contract | Straightforward; every output has one coherent config | No compatibility exception; 133 current reuses become 0 | Adds 104 P0 or 46 P3 model calls after deterministic guards |
| B — retain reuse if extraction semantics match | Can be sound only after proving unchanged output semantics per document | Requires separate semantic identities and explicit compatibility evidence | New selection/manifest/migration logic; guard also runs post-model | Saves few calls but adds engineering/review risk |
| C — controlled reissue/recanonicalization | Preserves model lineage while generating a new target identity | Strong if raw/precanonical lineage is complete | Existing tooling helps, but historical identity mapping and deterministic branches still need design/tests | More work than Option A for a small P3 saving |

Recommendation: **Option A for August**. It sacrifices no integrity, requires
no compatibility mechanism and adds only 46 model calls in P3. The number of
automatically preserved reusable extractions after the patch is therefore:

```text
0
```

The 133 frozen extractions remain regression evidence. They are not deleted or
rewritten. A separate compatibility identity is an OPTIONAL/POST-TFM design,
not part of the required classifier patch.

## 18. Holdout protection

The following are ineligible for a future holdout:

- all 152 versioned development documents;
- all 82 unique documents inspected in this audit;
- every document inspected in the prior funnel audit;
- any later post-patch exclusion-audit document.

After subtracting versioned development and this audit's recorded sample, the
upper bounds are:

| Scenario | Documents | Development IDs present | New inspected non-development | Holdout-eligible upper bound |
| --- | ---: | ---: | ---: | ---: |
| P0 | 25,347 | 143 | 82 | 25,122 |
| P1 | 23,107 | 132 | 64 | 22,911 |
| P2 | 19,489 | 98 | 47 | 19,344 |
| P3 | 11,231 | 69 | 22 | 11,140 |

These are upper bounds, not selectable pools. The previous audit did not
version the IDs of its in-memory samples, so their additional exclusion cannot
be calculated exactly. Before holdout selection, all inspected BOE IDs must be
consolidated in a versioned exclusion input. No holdout is selected here.

For reproducibility, the 82 unique documents inspected in this audit are:

```text
2022: BOE-B-2022-1225, BOE-B-2022-15281, BOE-B-2022-16569,
      BOE-B-2022-1968, BOE-B-2022-20099, BOE-B-2022-20119,
      BOE-B-2022-22545, BOE-B-2022-22781, BOE-B-2022-22941,
      BOE-B-2022-27735, BOE-B-2022-32100, BOE-B-2022-36829,
      BOE-B-2022-36886, BOE-B-2022-38363, BOE-B-2022-40867,
      BOE-B-2022-40918, BOE-B-2022-41290, BOE-B-2022-4383
2023: BOE-B-2023-10657, BOE-B-2023-16478, BOE-B-2023-18972,
      BOE-B-2023-20547, BOE-B-2023-20718, BOE-B-2023-22020,
      BOE-B-2023-22764, BOE-B-2023-32517, BOE-B-2023-32537,
      BOE-B-2023-34545, BOE-B-2023-35879, BOE-B-2023-37504,
      BOE-B-2023-5684, BOE-B-2023-5859, BOE-B-2023-7163,
      BOE-B-2023-7374, BOE-B-2023-7642
2024: BOE-B-2024-10988, BOE-B-2024-11215, BOE-B-2024-12614,
      BOE-B-2024-15589, BOE-B-2024-16232, BOE-B-2024-16519,
      BOE-B-2024-19281, BOE-B-2024-19766, BOE-B-2024-20569,
      BOE-B-2024-22461, BOE-B-2024-24015, BOE-B-2024-26575,
      BOE-B-2024-26634, BOE-B-2024-27052, BOE-B-2024-27217,
      BOE-B-2024-30934, BOE-B-2024-31971, BOE-B-2024-33752,
      BOE-B-2024-34086, BOE-B-2024-34338, BOE-B-2024-35786,
      BOE-B-2024-40440, BOE-B-2024-45488, BOE-B-2024-47278,
      BOE-B-2024-7951
2025: BOE-B-2025-2035, BOE-B-2025-20664, BOE-B-2025-20693,
      BOE-B-2025-27635, BOE-B-2025-34190, BOE-B-2025-35280,
      BOE-B-2025-37280, BOE-B-2025-38570, BOE-B-2025-39619,
      BOE-B-2025-45866, BOE-B-2025-5961, BOE-B-2025-5999
2026: BOE-A-2026-9070, BOE-B-2026-13607, BOE-B-2026-16167,
      BOE-B-2026-17651, BOE-B-2026-18658, BOE-B-2026-26177,
      BOE-B-2026-26937, BOE-B-2026-3935, BOE-B-2026-799,
      BOE-B-2026-8301
```

## 19. Minimal next patch

After human approval, one bounded patch should:

1. implement only R1 and R3 as cohesive predicates in
   `extraction/canonicalization.py::_scope_guard_from_document()`;
2. preserve explicit generation, any `hidroeléctric*` wording and
   `producción de energía eléctrica` before excluding R1/R3;
3. bump `SCOPE_CLASSIFICATION_POLICY`, thereby deriving a new
   `EXTRACTION_CONFIG_ID`;
4. expose the policy string in the extraction manifest without creating a
   second compatibility system;
5. add positive, negative, hydro, standalone-grid and institutional
   counterexamples plus config/manifest identity regressions;
6. add or version the deterministic P3 scope for 2025-01-01 through
   2026-08-20;
7. run the offline dry-run plan against source v2 and the frozen attempts.

No source redownload is required. The offline verification path is:

```text
source v2 documents
-> approved P3 scope
-> active pre-model classifier
-> exact-config attempt selection
-> deterministic/model counts
```

The existing `pipeline extract --dry-run` boundary can perform this plan with
the new config ID, the source snapshot and frozen attempts. It does not need
`--execute-model` and must report 0 compatible reuses, 2,880 planned model
documents from ordinary funnel records plus one new official-source extraction
for `BOE-A-2026-11850`: 2,881 total. It must also report deterministic counts
before any real execution is authorized.

## 20. Human decisions

Before the patch or any model call, the human reviewer must approve:

1. P3 as the final publication period;
2. R1 and R3 as the only classifier rules in the next patch;
3. R2 and R4 as `REVISE BEFORE PATCH`, hence excluded from that patch;
4. the hydro exceptions and post-patch exclusion-audit threshold;
5. current official source wins for `BOE-A-2026-11850`;
6. Option A strict config identity with zero automatic reuse;
7. versioning all inspected IDs before final holdout selection.

No decision in this document authorizes extraction or changes the final
period by itself.

## 21. Recommendation

```text
PERIOD/FUNNEL DECISION AUDIT COMPLETE — READY FOR HUMAN APPROVAL
```

P3 plus R1+R3 is the smallest evidence-backed package that materially reduces
the funnel without depending on unreproducible R2/R4 membership or a new reuse
architecture. It remains AMBER and requires an explicit human GO before the
classifier patch, offline reclassification or any model call.
