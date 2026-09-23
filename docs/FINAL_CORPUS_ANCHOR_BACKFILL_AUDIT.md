# Final Corpus Anchor + Historical Backfill Audit

## 1. Decision question

This offline audit evaluates whether the approved exhaustive P2 extraction
should be replaced by a project-centric corpus:

> Generation projects with relevant activity published in the BOE during
> 2026, with retrospective reconstruction of their related publications since
> 2022.

The audit uses the complete local source snapshot, compatible results already
paid for in `main-01` through `main-03`, production flattening, INE resolution
and project grouping, and exposed development regressions. It excludes every
holdout identifier before reading historical text. It makes no BOE, Gemini,
other-model or web call and does not execute or modify a pipeline stage.

The recommendation is:

```text
CONTINUE CURRENT P2 EXTRACTION
```

The anchor idea has genuine longitudinal value, but the present retrieval
evidence is not strong enough to replace P2 before the August deadline. Its
central estimate requires more model documents than the current plan, and the
apparently favourable Tier 1+2 variant has only five known historical BOEs of
recall evidence.

## 2. Current P2 baseline

The source loader identity remains:

```text
1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf
```

It covers 2022-01-01 through 2026-08-20. The current P2 model universe and
execution state reconcile as follows:

| Property | Documents |
| --- | ---: |
| P2 canonical documents | 19,489 |
| Deterministic, no model | 14,452 |
| P2 `MODEL_REQUIRED` | 5,037 |
| Already attempted in `main-01`…`main-03` | 750 |
| Pending non-holdout `main-04`…`main-20` | 4,239 |
| Pending holdout | 48 |
| Total model documents remaining | 4,287 |

The 750 attempted documents consumed USD 9.2312481 and 3.6889 accumulated
provider hours. This includes failed attempts and retries and is calculated
from the persisted input and output/thinking tokens at the versioned Standard
prices, not from the earlier planning estimate.

| Scope | Documents | Attempt rows | Provider hours | Documents/hour | USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| `main-01` | 250 | 252 | 1.2560 | 199.05 | 2.7073508 |
| `main-02` | 250 | 251 | 1.1573 | 216.01 | 3.2764138 |
| `main-03` | 250 | 250 | 1.2756 | 195.99 | 3.2474835 |
| **Observed total** | **750** | **753** | **3.6889** | **203.31** | **9.2312481** |

The observed mean is 0.004919 provider hours and USD 0.0123083 per model
document. Continuing full P2 therefore implies approximately **21.09 further
provider hours** and **USD 52.77**. These exclude human review, correction,
Silver, Gold, Streamlit and deployment time.

## 3. Anchor 2026 universe

The 2026 anchor is 2026-01-01 through 2026-08-20. Replaying the versioned P2
scope and v4 decisions gives:

| Anchor outcome | Documents |
| --- | ---: |
| Canonical candidates | 4,079 |
| Deterministic, no model | 2,988 |
| `MODEL_REQUIRED` | 1,091 |
| BOE-A model documents | 407 |
| BOE-B model documents | 684 |

The deterministic set consists of forced non-relevant decisions and therefore
requires no model under the current classifier contract. This audit does not
independently prove that the classifier has no false negatives. Completing the
model-reviewed part of the anchor concerns the 1,091 model documents.

## 4. Already-extracted anchor coverage

The first three main scopes contain 154 of the 1,091 anchor model documents.
All 154 have a compatible current extraction and none is in the five
`main-03` blockers.

| Observed 2026 result | Documents |
| --- | ---: |
| Attempted and compatible | 154 |
| Generation-project-specific | 69 |
| Non-relevant | 85 |
| Blocking review | 0 |
| Remaining anchor model documents | 937 |
| Remaining non-holdout | 921 |
| Withheld holdout metadata rows | 16 |

No paid 2026 result is counted again. The 16 holdout rows are counted only
from their versioned pre-model metadata; their document text was not inspected.

The main scopes are neither chronological nor stratified. They are the first
rows of one deterministic SHA-256 ranking of the complete non-holdout model
universe. Across the six `year × BOE series` cells, the largest deviation from
the expected hash-sample count is 1.06 standard deviations. The 2026 sample is
A=53/B=101 versus a population A=407/B=684. Classification:

```text
REPRESENTATIVE ENOUGH FOR PROJECTION
```

This supports bounded projection, not a claim that 154 documents establish
semantic prevalence exactly.

## 5. Observed anchor cohort

Production flattening, deterministic INE resolution and production project
grouping were run in memory over the 69 valid generation documents. All 498
location mentions avoided the grouping-blocking `ambiguous` and `conflict`
statuses.

| Cohort measure | Observed |
| --- | ---: |
| Generation documents | 69 |
| Generation-asset mentions | 113 |
| Documentary names | 134 |
| Groupable mentions | 113 |
| Potential canonical projects | 109 |
| Mean BOE publications/project | 1.0367 |
| Projects already observed in multiple BOEs | 4 |

Example canonical names include `Ado`, `Agrupación Maira Beta`, `Alcolrio`,
`Arada Solar`, `Campanario II Híbrido`, `Central de Zorita`, `DON RODRIGO II`,
`FV Recova Solar Ampliación` and `PEol-421 Tesouro`.

This is named `OBSERVED_ANCHOR_COHORT`. It is not the complete 2026 cohort:
937 anchor model documents remain. It also inherits any as-yet-undetected
semantic errors in the accepted extractions.

## 6. Project signatures

The audit built **109 signatures in memory**. Each signature contains only:

1. exact normalized documentary names;
2. the production grouping name identity after leading generation descriptors;
3. explicit aliases from `generation_asset_names`;
4. generation technology;
5. resolved municipality, province and autonomous-community names.

Promoter and power are not requirements. Associated SET, LAAT, evacuation or
BESS names are not project roots and do not create a signature. They may only
remain contextual evidence already attached to a generation root.

The simulated matching levels are:

- **Tier 1:** an exact normalized documentary alias that is corpus-distinctive;
- **Tier 2:** an exact production name key or observed alias that is
  corpus-distinctive;
- **Tier 3:** a less distinctive exact name/key plus compatible technology and
  at least one resolved territorial term.

“Corpus-distinctive” is operationalized conservatively: the phrase must be
lexically usable and occur in at most `max(10, 0.05% of the searched corpus)`,
which is 11 documents here. More frequent phrases cannot enter Tier 1 or 2.
This correction was necessary because literal equality alone treated generic
aliases such as `planta fotovoltaica`, toponyms and short names as high
precision.

No fuzzy edit-distance, promoter requirement, power requirement, machine
learning or model inference is used.

## 7. Historical retrieval

The signatures were searched deterministically over local canonical source
documents dated 2022-01-01 through 2025-12-31. All 48 holdout identifiers were
removed before text normalization and matching.

| Retrieval result | Count |
| --- | ---: |
| Project↔BOE candidate links | 2,570 |
| Historical BOEs unique after deduplication | 1,941 |
| BOEs linked to more than one project | 422 |
| Tier 1 links / unique BOEs | 187 / 155 |
| Tier 2 links / unique BOEs | 64 / 50 |
| Tier 3 links / unique BOEs | 2,319 / 1,829 |

Tier 3 dominates because generic or territorial names remain common even when
technology and territory are required. `Haza del Sol`, for example, still
produces many same-territory photovoltaic references. The result is a
candidate relationship, not a confirmed lifecycle event.

## 8. Deduplication and reuse

Extraction remains BOE-document-centric. The 2,570 relationships therefore
become 1,941 extraction decisions, not 2,570 model documents.

Compatibility was checked with the complete identity:

```text
boe_id
+ source_document_sha256
+ extraction_config_id
+ instructions_sha256
+ contract_schema_sha256
```

| Unique historical BOE disposition | Documents |
| --- | ---: |
| Compatible reusable extraction | 149 |
| Deterministic no-model decision | 25 |
| New model call required | 1,767 |
| Source drift/conflict | 0 |

Twenty-three candidates occur in the old development/core extraction but do
not satisfy the current strict extraction identity; they are not claimed as
reusable. The exact non-holdout 2022–2025 capacity still requiring a model
after current-compatible reuse is 6,735 unique BOEs.

Overlap handling must remain explicit:

- one BOE found by two projects is extracted once and retains two candidate
  links;
- a compatible historical extraction is reused without a provider call;
- a new BOE for a known project creates a new document extraction;
- a same-BOE/different-hash case fails closed as source drift;
- a new alias may add candidate links and reveal additional history without
  changing prior extraction identity.

Document extraction identity must therefore remain independent of
project-document candidate-link identity.

## 9. Retrieval precision

Precision was evaluated only where a candidate historical BOE already has a
compatible extraction. A link is confirmed when the extraction contains a
generation root with the production-normalized name/key and technology. A
non-relevant extraction is a false positive. A generation document without a
matching root is left ambiguous rather than manually adjudicated.

| Tier | Evaluated links | Confirmed | False positive | Ambiguous | Conservative empirical precision |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 26 | 11 | 0 | 15 | 42.31% |
| 2 | 7 | 2 | 1 | 4 | 28.57% |
| 3 | 164 | 8 | 5 | 151 | 4.88% |

The conservative precision denominator includes ambiguous cases. The decisive
subset is better, but excluding 170 ambiguous links would overstate evidence.
The measured result does not support calling current Tier 1 “high precision”
without a larger labelled evaluation, and it clearly rejects Tier 3 as an
economical extraction scope in its current form.

For cost sensitivity:

| Maximum tier | Unique BOEs observed | Reusable | Deterministic | New model documents observed |
| --- | ---: | ---: | ---: | ---: |
| Tier 1 | 155 | 20 | 6 | 129 |
| Tier 1+2 | 184 | 22 | 10 | 152 |
| Tier 1+2+3 | 1,941 | 149 | 25 | 1,767 |

Tier 1+2 is much cheaper, but its historical recall outside the very small
regression set below is unknown.

## 10. Historical recall

The regression used only already exposed, versioned development evidence and
simulated knowing the latest compatible project publication. Three projects
provide a valid longitudinal denominator:

| Project | Anchor | Known earlier BOEs | Recovered | Tier |
| --- | --- | ---: | ---: | --- |
| Badulaque | `BOE-A-2024-16664` | 3 | 3 | Tier 1 |
| Volateo Solar | `BOE-A-2024-16667` | 1 | 1 | Tier 1 |
| La Puebla 1 | `BOE-A-2025-26110` | 1 | 1 | Tier 1 |
| **Total** |  | **5** | **5** |  |

Observed known-history recall is therefore **100% (5/5)**, with zero misses.
The result is encouraging but not sufficient for a pivot: every recovered
history retains the same distinctive name token.

FV Andévalo and PE Angostillos were inspected only for test eligibility.
Andévalo has later exposed documents but no persisted compatible structured
extraction from which to construct the required latest-anchor signature;
using its 2024 extraction and treating a 2025 document as “history” would be
invalid. Angostillos has no known earlier BOE in the versioned Gold chronology.
Neither enters the recall denominator.

The available regression does not cover a complete rename without shared
tokens, severe spelling variation, a new module whose only link is
infrastructure, or a geography change that changes production grouping. Those
remain plausible false-negative causes.

## 11. Longitudinal coverage

Using all three tiers as candidate evidence:

| Candidate chronology measure | Observed projects |
| --- | ---: |
| Projects with at least one pre-2026 candidate | 92 |
| Projects spanning at least two calendar years | 92 |
| Projects spanning at least three calendar years | 66 |
| Earliest candidate publication | 2022 |
| Median first-to-anchor span | 1,082 days |
| Maximum first-to-anchor span | 1,659 days |

These figures show that a project-centric search can expose longer publication
spans. They do **not** prove complete project lifecycles: most historical
candidates are unextracted, Tier 3 precision is weak, and absence from the
retrieval is not evidence that no earlier publication exists.

## 12. Full-cohort projection

The project-count projection bootstraps project roots per hashed 2026 document
and preserves the observed grouping ratio:

| Projection | Lower | Central | Conservative upper |
| --- | ---: | ---: | ---: |
| Full 2026 anchor projects | 560 | 772 | 1,084 |

The backfill bounds deliberately use different evidential meanings:

- **lower:** the 1,767 new model documents already observed for only 109
  projects, with no assumption about unobserved projects;
- **central:** a saturating document-discovery projection over the exact 6,735
  remaining historical model-document capacity;
- **upper:** every remaining historical model document is selected.

| Calls from now | Lower | Central | Conservative upper |
| --- | ---: | ---: | ---: |
| Complete remaining anchor 2026 | 937 | 937 | 937 |
| Historical backfill | 1,767 | 5,955 | 6,735 |
| **Total additional model documents** | **2,704** | **6,892** | **7,672** |

The central and upper estimates exceed the 4,287 documents remaining in full
P2. Even the lower bound does not outperform the already-versioned P3 fallback:
P3 has 2,454 model documents remaining after the same paid scopes.

## 13. Calls, time and cost

The scenario endpoints use only the observed main-scope ranges: 0.004629 to
0.005102 provider hours and USD 0.0108294 to USD 0.0131057 per document. The
central value uses the actual aggregate mean.

| Scenario from now | Model documents | Provider hours | USD |
| --- | ---: | ---: | ---: |
| Continue full P2 | 4,287 | 21.09 | 52.77 |
| Anchor+backfill lower | 2,704 | 12.52 | 29.28 |
| Anchor+backfill central | 6,892 | 33.90 | 84.83 |
| Anchor+backfill upper | 7,672 | 39.15 | 100.55 |
| Existing P3 fallback | 2,454 | 12.07 | 30.20 |

Against P2, the optimistic lower bound saves 1,583 documents (36.92%), 8.57
provider hours and USD 23.48. The central estimate instead adds 2,605 documents
(60.77%), 12.81 hours and USD 32.06. A decision cannot rely on the favourable
endpoint while Tier 3 and unseen-name recall remain unresolved.

## 14. BOE-A fallback

A 2026 BOE-A-only anchor contains 407 model documents. Fifty-three have been
attempted; 30 are generation documents and produce 59 observed projects.

| BOE-A measure | Lower | Central | Conservative upper |
| --- | ---: | ---: | ---: |
| Projected projects | 264 | 453 | 722 |
| Historical backfill calls | 467 | 2,856 | 6,735 |
| Remaining anchor calls | 354 | 354 | 354 |
| **Total additional calls** | **821** | **3,210** | **7,089** |
| Provider hours | 3.80 | 15.79 | 36.17 |
| USD | 8.89 | 39.51 | 92.91 |

The central model count is lower than P2, but the analytical bias is
substantive: BOE-A favours administratively mature resolutions and omits
projects visible only through BOE-B public-information notices. It cannot be
presented as the full 2026 BOE project cohort and is not recommended merely to
reduce cost.

## 15. Strategy comparison

| Strategy | Anchor definition | Projected new model documents | Provider hours | USD | History start | Longitudinal value | Coverage and main bias | Implementation | Deadline risk |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| Continue P2 | All current v4 P2 model documents, 2024–2026 | 4,287 | 21.09 | 52.77 | 2024 | Medium | Broad candidate-period coverage; noisy source boundary | Existing path; resolve `main-03` first | HIGH but bounded |
| Anchor ALL 2026 + history | All confirmed BOE-A/B generation projects in 2026 | 2,704 / 6,892 / 7,672 | 12.52 / 33.90 / 39.15 | 29.28 / 84.83 / 100.55 | 2022 | Potentially high | Excludes projects without a 2026 publication; retrieval false negatives/positives | New candidate contract, indexing, validation and CLI | HIGH |
| Anchor BOE-A 2026 + history | Confirmed projects in 2026 BOE-A only | 821 / 3,210 / 7,089 | 3.80 / 15.79 / 36.17 | 8.89 / 39.51 / 92.91 | 2022 | Potentially high | Strong maturity and series bias; misses BOE-B-only projects | Same new layer | HIGH |

Under the evidence available on 23 August, continuing the approved P2 plan is
the best strategy. It has schedule risk, but its scope, identity, continuation
path and evaluation design already exist. The pivot would exchange known paid
work for a new retrieval-quality and implementation risk.

## 16. Incremental updates

The project-centric concept is compatible with later incremental operation:

```text
new BOE source dates
→ classify/extract new anchor documents
→ known project: add publication candidate
→ new project: create a versioned signature
→ search accumulated source retrospectively
→ reuse compatible document extractions
→ extract only new unique historical BOEs
→ regenerate validated Silver and Gold
```

Candidate-link identity must include the anchor/cohort identity, signature
version, project ID, BOE ID, source hash, match tier and reason. A newly
discovered alias may append links, but must not mutate an extraction attempt or
silently reinterpret a prior Gold snapshot.

## 17. Streamlit implications

No Streamlit change is made. If a future human decision approves the pivot,
the exact public universe wording must be:

> Projects of electricity generation with relevant activity published in the
> BOE during 2026, with retrospective reconstruction of their related observed
> publications since 2022.

The app could then answer:

- how many projects are in the observed 2026 cohort;
- where BOE publications locate them administratively;
- how their observed publications are distributed from 2022 to 2026;
- the latest published decision by procedure;
- each project's observed publication chronology.

It must also state that the corpus is not exhaustive for all projects active
in 2022–2026, absence in 2026 does not mean inactivity, retrieval may have
false negatives and the chronology is a record of observed publications, not
a complete legal lifecycle.

## 18. Holdout implications

The 48-document holdout was not opened or semantically searched. Only its
versioned identifiers and pre-model strata were used to exclude it. Sixteen
rows belong to the 2026 anchor metadata; 32 belong to earlier P2 years.

The holdout remains valid for its declared objective—AI extraction accuracy on
unseen P2 model documents—if executed only after the extraction policy is
frozen. It would not estimate anchor-cohort discovery, historical retrieval
recall or the precision of project-document links. Under a pivot, a human must
decide whether to retain it as a separate extraction-quality evaluation and
add an untouched retrieval evaluation. It must not be silently relabelled as
representative of the new analytical universe.

## 19. Minimal architecture change

A future pivot would need one bounded layer between the anchor cohort and
historical extraction, not a pipeline rewrite. A possible module is
`renewables_permitting.project_history` with public functions equivalent to:

```text
build_anchor_project_cohort(...)
build_project_history_signatures(...)
retrieve_project_history_candidates(...)
validate_project_history_candidates(...)
materialize_project_history_candidates(...)
```

The output should be a versioned `project_history_candidates` table plus a
manifest. Minimum columns are cohort/signature versions, `project_id`,
`identifier_boe`, source hash, tier, literal match evidence/reason and anchor
lineage. A separate deduplicated document scope feeds the existing extraction
command.

Tests would cover exact and alias matches, contextual disambiguation,
infrastructure non-roots, multi-project BOE deduplication, compatible reuse,
source drift, holdout exclusion, deterministic ordering, empty outputs,
manifest round trips, incremental alias discovery and longitudinal recall.

The least disruptive CLI shape is two explicit planning commands—conceptually
`pipeline cohort` and `pipeline history`—followed by the existing
`pipeline extract --scope`, Silver and downstream commands. Extending the
current all-in-one `run` before validating the candidate contract would add
unnecessary risk.

## 20. Methodological limitations

- The observed cohort covers 14.12% of anchor model documents, not the complete
  2026 cohort.
- Accepted extraction output is contractual evidence, not independent human
  ground truth; undetected semantic defects may affect project prevalence.
- Production grouping is intentionally conservative and may split renamed or
  geographically changed projects.
- Precision denominators are small for Tier 1 and Tier 2 and dominated by
  ambiguous generation documents.
- Known-history recall is 5/5 but covers only stable distinctive names; it is
  insufficient evidence for total renames or infrastructure-only references.
- Candidate chronology length is not lifecycle completeness.
- The projection assumes hashed-scope representativeness and uses saturation
  bounds; it is not a contractual budget.
- Provider hours are accumulated attempt durations, not wall-clock delivery
  time.
- No holdout text was inspected, so retrieval quality remains development-only
  evidence.

The minimum pivot criteria evaluate as follows:

| Criterion | Result |
| --- | --- |
| Material call reduction | FAIL centrally; only the optimistic lower bound saves calls |
| Defensible known-history recall | INSUFFICIENT: 100% on only five stable-name BOEs |
| Several hours saved | FAIL centrally; lower bound saves 8.57 hours |
| Bounded implementation | FAIL for the deadline: new contract, index, CLI and evaluation |
| Better chronology/cost balance than P3 | FAIL: even the lower ALL-anchor estimate exceeds P3 remaining documents |
| Explainable analytical universe | PASS |

## 21. Recommendation

```text
CONTINUE CURRENT P2 EXTRACTION
```

This does not authorize `main-04` or any provider call. First close the
systemic `main-03` validation blocker and obtain human review. Preserve the
anchor/backfill design as POST-TFM or contingency research unless a bounded,
labelled retrieval evaluation materially improves Tier 1+2 recall and
precision without Tier 3's volume.
