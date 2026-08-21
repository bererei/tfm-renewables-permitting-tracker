# Final Corpus Candidate Funnel Audit

## 1. Purpose

This read-only audit explains the candidate funnel materialized at:

```text
runs/final-corpus-preflight-20220101-20260820-v2/source/
```

It evaluates whether safe deterministic rules could materially reduce model
work before authorizing the Final Corpus Build. It does not change the source
policy, preclassifier, code, tests, run artifacts or the frozen development
corpus. It does not call the BOE, Gemini or any other external service.

The principal result is twofold:

- conservative pre-model candidates can reduce `MODEL_REQUIRED` by 15,367
  documents, or 65.08%, while preserving all 75 validated known positives;
- the remaining 8,244 model documents are still **NOT PLAUSIBLE FOR AUGUST**
  once review, Gold, dashboard, deployment, holdout and documentation are
  considered.

The operational recommendation is therefore to improve the pre-model boundary
only after human approval, preserve the inclusive source snapshot, and reduce
the temporal period. No model execution is authorized by this audit.

## 2. Current measured funnel

The source snapshot and the validated 140-document extraction snapshot were
loaded through the production boundaries. The source conflict already recorded
for `BOE-A-2026-11850` was quarantined before model accounting.

| Classification | Documents | Status |
| --- | ---: | --- |
| BOE items | 328,629 | MEASURED |
| Canonical title candidates | 25,347 | MEASURED |
| `EXTRACTION_REUSABLE` | 133 | MEASURED |
| `DETERMINISTIC_NO_MODEL` | 1,602 | MEASURED |
| `MODEL_REQUIRED` | 23,611 | MEASURED |
| Source identity conflict | 1 | MEASURED |

The universe reconciles exactly:

```text
25,347 = 133 + 1,602 + 23,611 + 1
```

The implemented transitions are:

| Transition | Production code | Input | Output | Criterion and reduction | Recall objective |
| --- | --- | ---: | ---: | --- | --- |
| BOE summaries to items | `boe_source.parse_boe_summary()` and pipeline source stage | 1,693 dates | 328,629 items | Parse all published summary items; no energy filtering | Complete requested dates |
| Item to candidate | `boe_candidates.select_energy_candidates()` | 328,629 | 25,347 | OR over 26 literal substrings in normalized `titulo`; removes 303,282 items | Deliberately broad title recall |
| Candidate to document | `boe_documents.build_extractor_document_input()` | 25,347 | 25,347 | Valid local XML, identity and parse checks; zero losses | Lossless canonical source boundary |
| Document to reuse | `pipeline.build_extraction_plan()` through `build_review_queue()` | 25,347 | 133 | Same BOE, source hash and active extraction lineage/configuration | Exact reuse only |
| Pending to deterministic | `preclassify_document_without_model()` | 25,213 non-conflicted pending | 1,602 | Only high-precision forced non-relevant families | Prefer precision over negative recall |
| Remaining to model | same plan | 23,611 | 23,611 | No deterministic decision exists | Preserve uncertain candidates |

## 3. Candidate selection

`title_keywords_v1` uses only `titulo`; department, section and epigraph do not
select a document. `normalize_text()` lowercases, performs NFKD/ASCII
normalization, removes accents, replaces non-alphanumeric characters with
spaces and collapses whitespace. The selector applies an OR of escaped literal
substrings. It does not use word boundaries, weights, negative rules or text.

Overlaps are extensive: 18,906 candidates have one trigger, while 6,441 have
between two and thirteen. Counts below are therefore not additive. `Exclusive`
means that no other configured keyword matched the title. `Positive` is the
number of the 75 validated project-specific development BOEs matching the
keyword.

| Keyword | Total | % candidates | 2022/23/24/25/26 | Exclusive | Overlap | Model | Positive |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| `almacenamiento` | 915 | 3.61% | 111/145/175/248/236 | 547 | 368 | 471 | 10 |
| `autorizacion administrativa de construccion` | 1,874 | 7.39% | 240/460/511/395/268 | 0 | 1,874 | 1,837 | 16 |
| `autorizacion administrativa previa` | 3,545 | 13.99% | 460/1,100/920/642/423 | 31 | 3,514 | 3,472 | 33 |
| `bateria` | 335 | 1.32% | 41/41/65/84/104 | 169 | 166 | 164 | 3 |
| `declaracion de impacto ambiental` | 1,106 | 4.36% | 252/381/195/173/105 | 0 | 1,106 | 1,048 | 24 |
| `energia electrica` | 1,082 | 4.27% | 178/210/258/244/192 | 503 | 579 | 952 | 2 |
| `energia solar` | 9 | 0.04% | 3/1/2/1/2 | 4 | 5 | 7 | 0 |
| `instalacion solar` | 225 | 0.89% | 22/54/66/56/27 | 2 | 223 | 201 | 3 |
| `eolic` | 1,371 | 5.41% | 131/363/416/306/155 | 15 | 1,356 | 1,350 | 21 |
| `evacuacion` | 3,901 | 15.39% | 370/1,254/1,063/788/426 | 105 | 3,796 | 3,715 | 64 |
| `fotovoltaic` | 3,152 | 12.44% | 330/1,026/823/619/354 | 159 | 2,993 | 2,922 | 53 |
| `hibridacion` | 559 | 2.21% | 17/61/141/185/155 | 0 | 559 | 540 | 16 |
| `impacto ambiental` | 1,770 | 6.98% | 381/559/330/312/188 | 189 | 1,581 | 1,598 | 34 |
| `afeccion ambiental` | 152 | 0.60% | 0/35/67/49/1 | 1 | 151 | 143 | 9 |
| `informacion publica` | 19,427 | 76.64% | 1,509/2,018/6,736/5,915/3,249 | 16,684 | 2,743 | 18,907 | 17 |
| `infraestructura de evacuacion` | 2,181 | 8.60% | 169/592/639/500/281 | 0 | 2,181 | 2,105 | 42 |
| `linea de evacuacion` | 143 | 0.56% | 23/51/38/16/15 | 0 | 143 | 138 | 1 |
| `linea electrica` | 308 | 1.22% | 50/88/87/59/24 | 29 | 279 | 303 | 0 |
| `parque eolico` | 1,104 | 4.36% | 93/301/373/234/103 | 0 | 1,104 | 1,089 | 17 |
| `planta fotovoltaica` | 326 | 1.29% | 43/105/68/60/50 | 0 | 326 | 310 | 4 |
| `planta solar` | 686 | 2.71% | 105/205/181/128/67 | 7 | 679 | 679 | 7 |
| `plantas solares` | 70 | 0.28% | 16/22/14/12/6 | 0 | 70 | 68 | 2 |
| `repotenciacion` | 43 | 0.17% | 7/7/7/18/4 | 3 | 40 | 42 | 1 |
| `solar termica` | 0 | 0.00% | 0/0/0/0/0 | 0 | 0 | 0 | 0 |
| `subestacion` | 1,278 | 5.04% | 294/321/266/226/171 | 255 | 1,023 | 1,116 | 1 |
| `utilidad publica` | 2,726 | 10.75% | 387/640/719/614/366 | 203 | 2,523 | 2,659 | 13 |

The largest trigger is `informacion publica`: it selects 76.64% of the entire
candidate corpus and 18,907 model-required documents. The next largest
triggers—`evacuacion`, administrative authorization, `fotovoltaic` and
`utilidad publica`—are more closely aligned with the domain but overlap
heavily.

## 4. Annual growth

Candidate rates were 3.39% in 2022, 5.45% in 2023, 10.95% in 2024, 9.48% in
2025 and 8.98% through 20 August 2026. The 2023-to-2024 increase is not
explained by a comparable rise in plant-specific language:

- total candidates increased by 4,640;
- `informacion publica` matches increased by 4,718, from 2,018 to 6,736;
- exclusive `informacion publica` matches increased by 4,789;
- section V-B increased by 4,780 candidates, while section III fell by 137;
- candidates assigned to the Ministry for Ecological Transition increased by
  4,504;
- the six largest prefix increases were generic Confederación Hidrográfica or
  Comisaría de Aguas announcements.

| Normalized prefix | 2023 | 2024 | Increase |
| --- | ---: | ---: | ---: |
| `anuncio de la comisaria de aguas de` | 43 | 1,706 | 1,663 |
| `anuncio de la confederacion hidrografica del guadiana` | 100 | 1,484 | 1,384 |
| `anuncio de la confederacion hidrografica del tajo` | 2 | 663 | 661 |
| `anuncio de la confederacion hidrografica del mino` | 45 | 403 | 358 |
| `anuncio de la confederacion hidrografica del duero` | 111 | 446 | 335 |
| `anuncio de la confederacion hidrografica del jucar` | 35 | 239 | 204 |

The underlying BOE item population supports the same conclusion: Ministry
items rose from 3,611 to 9,265, and Ministry titles containing the exact phrase
`informacion publica` rose from 693 to 5,358. The local evidence therefore
shows a large increase in published water-administration notices using the
generic trigger, not merely a normalization artifact and not an equivalent
increase in energy projects. It does not establish the institutional reason
for that publication change, which would require evidence outside this audit.

## 5. Candidate title analysis

The 25,347 candidates contain 23,794 raw titles and 23,661 normalized titles.

| Population | Rows | Unique raw titles | Unique normalized titles | Dominant section |
| --- | ---: | ---: | ---: | --- |
| Reusable | 133 | 133 | 133 | III: 83; V-B: 44 |
| Deterministic | 1,602 | 1,547 | 1,542 | V-A procurement: 1,039 |
| Model required | 23,611 | 22,114 | 21,986 | V-B: 20,312 |

The model population is dominated by repetitive institutional prefixes:

| Prefix | Model documents |
| --- | ---: |
| Confederación Hidrográfica del Guadiana | 3,566 |
| Comisaría de Aguas | 3,483 |
| Confederación Hidrográfica del Duero | 1,258 |
| Confederación Hidrográfica del Tajo | 1,218 |
| Confederación Hidrográfica del Miño | 1,063 |
| Demarcación de Carreteras | 716 |
| Confederación Hidrográfica del Júcar | 677 |
| Área de Industria y Energía | 575 |
| Delegación Territorial de Economía | 506 |
| Demarcación de Costas | 433 |

The reusable group has varied, project-specific resolutions and notices. The
deterministic group is largely procurement already recognized by the guard.
The model group mixes genuine project acts with high-volume water, road,
railway, coast and port notices whose only trigger is often the generic phrase
`informacion publica`.

## 6. Deterministic classifier

`preclassify_document_without_model()` calls `_scope_guard_from_document()`.
It uses the canonicalized title for procurement, explicit generation,
non-generation sector objects, gas and standalone storage. Full source text is
used only to detect an auxiliary renewable installation in a sector project.
It does not use BOE section, department or epigraph. Positive generation and
action patterns prevent a forced negative but still route the document to the
model; the function only materializes `FORCE_NOT_RELEVANT`.

| Current reason | Count | 2022/23/24/25/26 |
| --- | ---: | --- |
| Public procurement, not a plant lifecycle act | 1,040 | 204/219/203/252/162 |
| Non-generation sector project | 425 | 41/67/84/119/114 |
| Gas infrastructure without electrical generation | 60 | 7/8/12/19/14 |
| Standalone storage without linked generation | 59 | 2/3/12/22/20 |
| Auxiliary generation in a non-generation sector project | 18 | 2/7/5/3/1 |

Only 1,602 documents are resolved because the guard intentionally implements
five narrow, high-precision negative families. It has no general treatment for
water-basin notices, transport/coast institutions or all procurement wording.
This is confirmed by the validated negatives: only 17 of 65 would be forced
non-relevant by the current guard, while the other 48 would require model
under an otherwise fresh plan.

The preclassifier emits a decision and reason, not a source keyword or an
extracted technology/type. Keyword intersections remain observable from the
candidate title but are overlapping selection signals rather than causal
reason fields; technology extraction has not yet occurred at this boundary.

## 7. Known positives

The correct positive regression set is not the complete list of 152 documents
used during development. It is the 75 rows in validated frozen
`current_extractions` whose `document_scope` is
`generation_project_specific`. There are 65 separately validated non-relevant
documents.

| Positive regression | Result |
| --- | ---: |
| Validated positives | 75 |
| Present in the 2022–2026 source | 72 |
| Retained within the source period | 72 of 72 |
| Retained across all frozen positives | 75 of 75 |
| Observed title-policy recall in either population | 100% |
| Incorrectly forced negative by current preclassifier | 0 |

The positive set is a useful regression boundary but is neither exhaustive nor
a substitute for a holdout. Its most frequent triggers are `evacuacion` (64),
`fotovoltaic` (53), `infraestructura de evacuacion` (42), `impacto ambiental`
(34) and prior authorization (33).

## 8. Known negatives

```text
LABELED NEGATIVE SET AVAILABLE
```

The frozen current extractions contain 65 validated
`not_relevant_for_generation_projects` documents: 61 are in the v2 period and
four are from 2021. All 65 were selected by the deliberately broad title
policy. The existing guard recognizes 17. The remaining 48 demonstrate that
high candidate recall and high negative precision do not by themselves provide
adequate negative recall.

Documents without an extraction or manual label were not treated as negatives.

## 9. MODEL_REQUIRED samples

Sampling was performed only in memory with seed `20260820`:

1. five model-required documents per year, after excluding reuse and the source
   conflict;
2. three documents for each of the eight largest model keyword populations;
3. examples from the eight most frequent normalized prefixes.

The sample is descriptive, is not stored in `runs/`, is not a holdout and is
not used as ground truth. It includes both genuine acts and clear noise:

- a 2024 water concession notice whose only trigger is `informacion publica`;
- a 2022 road-layout public-information notice;
- 2023 and 2024 named wind/solar authorizations with multiple domain triggers;
- a 2025 hydroelectric project that must be protected from water-family rules;
- general energy remuneration rules and cultural-protection notices.

This confirms that a generic exclusion of all `informacion publica` documents
would be unsafe; the institutional/object context and explicit-generation
exceptions are essential.

## 10. Irrelevant families

Four recurrent families merit candidate pre-model rules. Volumes below refer
only to documents currently in `MODEL_REQUIRED`.

| Family | Evidence and volume | Years | False-negative risk | Known positives hit |
| --- | --- | --- | --- | ---: |
| Water-basin bodies without explicit generation | 12,182; water concessions, vertidos, user rights and hydraulic-domain notices from Confederaciones/Comisarías | 37/432/5,113/4,275/2,325 | MEDIUM: an unusual hydro project might omit explicit generation wording | 0 |
| Explicit water proceedings beyond those bodies | 9,486 standalone, but only 92 additional to the first family | 14/324/4,083/3,293/1,772 | MEDIUM: requires strict hydro/electric exceptions | 0 |
| Road, rail, coast and port bodies without explicit generation | 3,086 | 719/693/667/666/341 | MEDIUM: title may omit an associated generation object | 0 |
| Narrow missed procurement wording | 35 | 10/8/15/2/0 | LOW with exact contracting/offer phrases | 0 |

The known-positive result is necessary but not sufficient: the 75 positives
are small and derive from the same development process. Each family still
requires excluded-candidate audit before production use.

## 11. Candidate deterministic rules

All four candidates belong in the **PRE-MODEL CLASSIFIER**, not the source
filter. This preserves the inclusive source snapshot and makes exclusions
versioned, reviewable and reversible.

| Rule | Condition summary | Model reduction | Reduction | Positive impact | Risk | Testing |
| --- | --- | ---: | ---: | ---: | --- | --- |
| R1 — water body | Confederación Hidrográfica or Comisaría de Aguas in title; reject only without explicit electrical/hydroelectric generation | 12,182 | 51.59% | 0/75 | MEDIUM | High: negative proceedings plus hydro exceptions |
| R2 — water object | Public-information title with explicit water concession/vertido/hydraulic-domain object; preserve explicit generation | 9,486 standalone; 92 marginal after R1 | 40.18% standalone | 0/75 | MEDIUM | High: object whitelist and counterexamples |
| R3 — transport/coast | Strict issuing-body title patterns; preserve explicit generation | 3,086 | 13.07% | 0/75 | MEDIUM | High: institutional negatives plus generation exceptions |
| R4 — procurement variants | Exact `procedimiento de contratación`, offer-opening/presentation, non-award or `convoca la licitación` phrases | 35 standalone; 8 marginal after R1–R3 | 0.15% standalone | 0/75 | LOW | High: existing procurement suite extension |

R4 deliberately excludes a broad `Objeto:` rule: the local corpus contains
correction notices with that wording that concern actual named generation
authorizations. Likewise, BOE section V-A alone is not proposed because section
metadata is not part of the current `BOESourceDocument` preclassifier boundary.

## 12. Rule simulations

The simulations are ad hoc in-memory masks, not production behavior. They
apply only to the current 23,611 model documents and retain an explicit
generation/hydroelectric exception. Source candidates remain 25,347.

| Simulation step | Marginal reduction | Cumulative reduction | Remaining model |
| --- | ---: | ---: | ---: |
| Current production | — | — | 23,611 |
| Add R1 | 12,182 | 12,182 | 11,429 |
| Add R2 | 92 | 12,274 | 11,337 |
| Add R3 | 3,085 | 15,359 | 8,252 |
| Add narrow R4 | 8 | 15,367 | 8,244 |

The conservative combination reduces model work by 65.0841% and preserves
75/75 known positives. Its reconstructed candidate universe would be:

```text
25,347 = 133 reusable
       + 16,969 deterministic (1,602 current + 15,367 simulated)
       + 8,244 model required
       + 1 source conflict
```

| Year | Current model | Model after simulation |
| ---: | ---: | ---: |
| 2022 | 1,974 | 1,208 |
| 2023 | 3,282 | 2,140 |
| 2024 | 7,914 | 2,112 |
| 2025 | 6,712 | 1,738 |
| 2026 through 20 August | 3,729 | 1,046 |
| **Total** | **23,611** | **8,244** |

## 13. Operational feasibility

```text
CURRENT FUNNEL: NOT PLAUSIBLE FOR AUGUST
CONSERVATIVE SIMULATION: NOT PLAUSIBLE FOR AUGUST
```

The validated development metadata provides a derived throughput of 226.94
documents per summed provider-hour. Linear scaling gives about 104 summed
provider-hours for the current funnel and 36.3 for the simulated funnel. These
are orientation values, not wall-clock forecasts: they omit rate limits, changing
document mix, failures, review and all subsequent pipeline/product work.

Even after the 65% reduction, 8,244 model outputs would need automated gates,
blocking-queue resolution, targeted semantic review, Gold validation and human
corpus approval while dashboard, deployment, holdout and delivery evidence
remain pending. No defensible August target can be declared from these data.

## 14. Period implications

The candidate rules remove most of the anomalous 2024–2026 water-notice surge,
but the residual model workload remains large in every year. The full
2022–2026 period is therefore not operationally viable under the current
deadline, even with the conservative mitigation.

Period reduction requires a human decision. This audit does not select the new
start date. It specifically does not recommend measuring or adding 2021/2020
while 2022–2026 remains infeasible.

## 15. Source drift

`BOE-A-2026-11850` has one exact physical text difference:

| Source | Canonical source SHA-256 | Text length |
| --- | --- | ---: |
| Legacy/development-local document | `53ba075b46c616e4870d4a88f7e7762146c7dc07003b83d506700aa08d1ebc12` | 3,300 |
| Current v2 official source | `c95bafebaa350dbbb18b2ac36e5d5a137508a94f36045f1780832b5152259558` | 3,297 |

The only diff operation deletes three characters:

```text
de la la sección
→
de la sección
```

No relevant legal or extraction semantics change: it is a grammatical
duplication correction. The hash difference remains contractually material,
so no prior extraction may be reused under the new source identity.

Recommended general policy:

```text
same BOE ID + same source hash
→ reuse eligible, subject to extraction lineage/configuration

same BOE ID + different source hash
→ source drift
→ no automatic extraction reuse
→ compare and audit the exact diff
→ current official source wins for the Final TFM corpus only after approval
→ create a new extraction identity
```

The development freeze remains unchanged. For this isolated document the
recommended decision is **CURRENT OFFICIAL SOURCE WINS FOR FINAL CORPUS + NO
EXTRACTION REUSE WHEN SOURCE HASH CHANGES**.

## 16. Recall safeguards

Any future pre-model patch must include:

1. regression over the 75 known positives, while acknowledging its limited
   coverage;
2. synthetic positive exceptions and negative examples for every family;
3. a reproducible random audit stratified by rule and year over excluded
   candidates;
4. an untouched final holdout, never used to tune these rules;
5. a versioned scope-classifier identity and resulting extraction config ID;
6. before/after counts, annual distributions, overlap and review of changed
   rows;
7. explicit review of hydroelectric, railway-adjacent generation and ambiguous
   title counterexamples.

Rules must not be optimized against the 75 positives alone. Zero observed hits
does not prove zero false-negative risk.

## 17. Recommended architecture

```text
A. KEEP SOURCE, IMPROVE PRE-MODEL CLASSIFIER
```

The source filter already has 100% observed recall over validated positives and
has produced a complete, hashed source snapshot. Tightening it would make
false negatives disappear before XML/text and complicate retrospective audit.
The pre-model boundary can use title plus canonical text, record an explicit
reason, retain the source document and be rerun without network access.

This architectural recommendation does not make the full period feasible; the
separate operational recommendation remains period reduction.

## 18. Minimal next patch

Subject to human approval, the smallest coherent patch would:

- extend `extraction/canonicalization.py::_scope_guard_from_document()` with
  cohesive, named water, transport/coast and narrow procurement predicates;
- preserve the existing explicit-generation and hydroelectric exceptions;
- add stable reason strings and no new source filtering;
- bump `SCOPE_CLASSIFICATION_POLICY` in `extraction/config.py`, which must
  derive a new `EXTRACTION_CONFIG_ID`;
- add positive/negative/counterexample regressions in
  `tests/extraction/test_canonicalization.py` and update configuration/pipeline
  identity snapshots only where derivable;
- rerun the read-only extraction plan and this funnel comparison.

Changing classifier behavior without changing its version/config identity is
not acceptable. The new config ID also means the 133 historical extractions
are not automatically compatible with the new plan. Their reuse or controlled
reissue/recanonicalization must be explicitly designed and validated; it must
not be hidden by retaining the old ID.

The source candidate policy ID and source manifest do not change. No BOE
redownload and no source rerun are required. The funnel preflight must be
recomputed after the patch, but it can consume the existing v2 source snapshot.

## 19. Final source reuse

```text
REUSABLE AS FINAL SOURCE SNAPSHOT
```

The snapshot covers every requested date, has valid manifest/artifact hashes,
unique document IDs, zero download/parse failures and a production-derived
document identity. Once the human source-drift policy approves the current
official text, it can be passed directly to a later Final Corpus Build for the
same 2022–2026 period. Neither pre-model changes nor period feasibility require
editing it.

If the final period changes, a new complete source snapshot for that approved
period is required by the single-snapshot pipeline boundary; manual Parquet
merging remains outside the approved design.

## 20. Human decisions

Before any extraction:

1. approve or reject the four candidate pre-model families;
2. approve the source-drift policy and current official source for
   `BOE-A-2026-11850`;
3. select a reduced final temporal period;
4. decide how compatible historical extraction outputs are reissued under the
   required new classifier/config identity;
5. approve the excluded-candidate audit design and acceptance threshold.

## 21. Recommendation

```text
CANDIDATE FUNNEL AUDIT SHOWS PERIOD REDUCTION REQUIRED
```

The audit identifies a material, testable pre-model mitigation and recommends
implementing it before any model work. It also shows that the mitigation alone
does not make the full multiyear funnel plausible for August. Source remains
inclusive; no model calls are authorized; the next action is a human funnel
mitigation and period decision.
