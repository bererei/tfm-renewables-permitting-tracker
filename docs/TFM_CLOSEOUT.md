# TFM Closeout

Operational source of truth for status, dependencies, gates, calendar, risks
and scope cuts through the **31 August 2026** delivery. Stable engineering
rules live in `AGENTS.md`; user procedures in `docs/USER_GUIDE.md`; Streamlit
architecture in `docs/STREAMLIT_CODE_GUIDE.md`.

Decision rule:

```text
complete + reproducible + evaluated
>
perfect + exhaustive
```

The August delivery scope is frozen from **19 August 2026**. Only the REQUIRED
work listed here may enter the product.

## 1. Current validated state

| Area | Status | Evidence |
| --- | --- | --- |
| Core extraction, Silver, INE enrichment, grouping, `projects` and `project_events` | FROZEN, validated, committed and tagged | `docs/freezes/core_data_freeze_2026-08-13.md`; `tfm-core-freeze-2026-08-13` |
| Gold `project_locations` and `project_location_sources` | Validated, committed and pushed | `9a0916d`; frozen project membership and events unchanged |
| Local read-only Streamlit MVP | Validated, committed and pushed | `479f513` |
| `docs/USER_GUIDE.md` | Reviewed, committed and pushed | `898df2b` |
| `docs/STREAMLIT_CODE_GUIDE.md` | Reviewed, committed and pushed | `cb144e1` |
| Gold data explorer | Validated, committed and pushed | `c35136d`; local and disabled by default |
| Canonical BOE URL fix | Tested, committed and pushed | `c35136d` |
| Administrative situation filters | Validated, committed and pushed | `523887a`: latest/historical, situation, action, OR/AND and `matching_action_types` |
| `APP_DATA_CATALOG` — Gate 1 | PASSED — implemented, audited and human-reviewed on 2026-08-19 | `docs/APP_DATA_CATALOG.md` |
| `APP_PRODUCT_SPEC` — Gate 2 | **PASSED 2026-08-20**; human product decisions recorded | `docs/APP_PRODUCT_SPEC.md` |
| Final Corpus Ingestion Audit | Implemented + audited — pending human review | `docs/FINAL_CORPUS_INGESTION_AUDIT.md` |
| Final Corpus Preflight 2022 v2 | Source snapshot reusable; isolated source drift resolved by human decision | Current official source wins for the Final TFM corpus; changed source hash is not automatically reusable; `docs/FINAL_CORPUS_PREFLIGHT_2022_V2.md` preserves the pre-decision audit |
| Candidate funnel audit | Human-reviewed; R1+R3 approved | R2/R4 remain unimplemented; historical evidence is preserved in `docs/FINAL_CORPUS_CANDIDATE_FUNNEL_AUDIT.md` |
| Pre-model R1+R3 mitigation | Implemented + tested — pending human review | Policy `binary_named_generation_pre_model_guard_v4`; strict offline P1/P2/P3 model counts 7,223/5,037/2,881; no model or source calls |
| Period/funnel decision | **P2 REMAINS CURRENT — SHORT-WINDOW ALTERNATIVE PENDING HUMAN DECISION** | No corpus pivot is approved; `main-04` is paused and remains unauthorized |
| Anchor + historical backfill audit | **COMPLETED — CONTINUE P2** | No anchor/history implementation enters this TFM; see `docs/FINAL_CORPUS_ANCHOR_BACKFILL_AUDIT.md` |
| Short-window + conservative backfill audit | **COMPLETED — PENDING HUMAN DECISION** | W14 is the only plausible demo candidate; recommendation is a bounded 42-call anchor pilot before any pivot; see `docs/FINAL_CORPUS_SHORT_WINDOW_BACKFILL_AUDIT.md` |
| Holdout exposure provenance | **RESOLVED — 479 development-exposed BOEs versioned** | `docs/HOLDOUT_EXPOSURE_PROVENANCE.md`; P2 exposed: 263; P2 provisionally eligible: 19,226 |
| Source reliability mitigation | Operationally validated in v2 | Three transient XML failures recovered after one retry; zero exhausted retries |
| Final P2 extraction `main-01` | **CLOSED — 250 ACCOUNTED; 249 CURRENT; 1 REJECTED; 0 BLOCKERS** | Loader-validated `extraction-main-01-final-v2` has 501 unique attempts; see `docs/FINAL_EXTRACTION_MAIN01_IDEMPOTENCY_FIX.md` |
| Final P2 extraction `main-02` | **CLOSED — 500 ACCOUNTED; 499 CURRENT; 1 REJECTED; 0 BLOCKERS** | Loader-validated `extraction-main-02-final`; eight deterministic blockers were resolved offline and the one isolated operational retry completed; cumulative `main-01` + `main-02` model cost USD 5.9837646; see `docs/FINAL_EXTRACTION_MAIN02_BLOCKER_FIX.md` |
| Final P2 extraction `main-03` | **SEMANTICALLY CLOSED — 750 ACCOUNTED; 747 CURRENT; 1 REJECTED; 2 OPERATIONAL BLOCKERS** | The approved `BOE-B-2024-3861` semantics are preserved in loader-valid `extraction-main-03-recanonicalized-v2`; semantic blockers are zero and the two operational retries remain unauthorized; see `docs/FINAL_EXTRACTION_MAIN03_REVIEW_PRECEDENCE_FIX.md` |
| Deterministic `main-02` blocker fix | **CLOSED** | Eight semantic blockers resolved offline with unchanged extraction identity; the separate operational retry also completed |
| Deterministic `main-01` blocker fix | **IMPLEMENTED + TESTED + COMMITTED** | Four confirmed families corrected without changing extraction identity; offline replay and P2 impact audit in `docs/FINAL_EXTRACTION_MAIN01_BLOCKER_FIX.md` |
| Explicit error retry tooling | **IMPLEMENTED + TESTED; NO FURTHER GEMINI CALLS AUTHORIZED** | The two `main-01` retries and the separate `main-02` retry completed; the two `main-03` candidates remain unauthorized |
| Recanonicalization idempotence and attempt uniqueness | **IMPLEMENTED + TESTED; ENFORCED** | Equivalent derivations are reused, conflicting collisions fail closed, loaders/publication reject duplicate `attempt_id`; the invalid historical snapshot is retained and rejected |
| Final `main-01` disposition | **CLOSED + MATERIALIZED** | One rejection, one rectification-only manual selection, zero operational or semantic blockers; final evidence in `docs/FINAL_EXTRACTION_MAIN01_IDEMPOTENCY_FIX.md` |

The validated application reads only the four contractual Gold tables,
verifies the expected downstream identity and never reads Silver or executes
the pipeline. Project detail always uses the complete published chronology,
independently of the filters used to locate the project.

The current 140-document **development corpus** is the frozen baseline for
development, contracts, tests, regression, architectural validation and
dashboard design; it is not the final product corpus. The **Final TFM corpus**
will be a separate, new multi-year materialization used for the written
results, definitive screenshots, metrics, map, charts and demonstration. Its
validated, versioned Gold publication is the **deployment dataset**, with its
own downstream ID, manifest, hashes and rollback. In short:

```text
Development corpus → development and regression
Final TFM corpus    → final materialization
Deployment dataset → published Gold
```

Current phase: **product completion**. Gates 1 and 2 are complete. Public
deployment, implementation of the approved minimum safe error reporting and
the final holdout remain pending. `project_components` and
`project_relationships` are approved concepts deferred to POST-TFM, not August
Gold contracts.

## 2. August delivery objective

Deliver a public Streamlit dashboard for following named electricity-generation
projects through administrative information published in the BOE. The product
must be secure, reproducible, documented, validated and **read-only with
respect to Gold and the analytical pipeline**.

The approved product scope includes:

- dynamic project and BOE-publication KPIs;
- a territorial map;
- latest-published-situation and publication-evolution charts;
- project exploration using the implemented filters;
- project detail with full published chronology;
- methodology, limitations and data-version information;
- a separate minimum safe channel for reporting possible errors.

Exact pages, layout, widgets, navigation, chart granularity, map interaction,
libraries, empty states and wireframes belong to
`docs/APP_PRODUCT_SPEC.md`, not to this roadmap.

### Critical methodological definitions

- **Territory:** the planned measure is the number of distinct projects
  associated with each published territory. Do not call it density without a
  denominator. The map represents administrative territories in which BOE
  publications place an installation or associated component; it does not
  represent exact plant coordinates.
- **Administration:** use **última decisión publicada por trámite**. Do not
  present the result as an inferred legal **estado actual**.
- **Power:** **REJECTED FOR AUGUST / POST-TFM — NEEDS MODELLING**. Do not show
  a global KPI, a canonical project figure, energy production or a raw sum.
  The two REQUIRED safe KPIs are distinct projects and distinct BOE
  publications over the filtered product set; Gate 2 defines their exact
  filter interaction in `docs/APP_PRODUCT_SPEC.md`.

### Read-only and error reporting boundary

The dashboard and data layer are read-only: they do not modify Gold, Silver,
`runs/` or the pipeline. A separate reporting channel may accept bounded user
input, but it must not modify analytical data, execute the pipeline, approve a
correction or become part of the analytical query layer. “Public app
read-only” refers to the dataset and dashboard; it does not forbid an isolated,
approved report submission mechanism.

### Documentation boundaries

| Document | Responsibility |
| --- | --- |
| `docs/APP_DATA_CATALOG.md` | What data exists, its quality/granularity, and whether it is usable |
| `docs/APP_PRODUCT_SPEC.md` | What product to build from approved data, including KPIs and wireframes |
| `docs/TFM_CLOSEOUT.md` | When and in what dependency order work is performed |
| `AGENTS.md` | Stable invariants, safety and Definition of Done |

Do not duplicate the future catalogue or product specification here.

## 3. Required deliverables

Complete in dependency order:

1. **APP_DATA_CATALOG — Gate 1. COMPLETE.** Created, audited and human-reviewed
   on 19 August in
   `docs/APP_DATA_CATALOG.md`. Audit current Gold and potentially useful
   extracted data for source, granularity, coverage, nullability, cardinality,
   temporality, ambiguity, normalization, provenance and duplicate-count risk.
   Record GO/NO-GO as `READY FOR GOLD`, `NEEDS MODELLING`,
   `DO NOT USE FOR TFM`, or `POST-TFM`.
2. **APP_PRODUCT_SPEC — Gate 2. COMPLETE.** Human-reviewed on 20 August with
   two KPIs, map and approved charts, explicit filters, current navigation,
   mailto reporting and the August detail scope fixed. Components and
   relationships are deferred. Do not create separate `APP_QUESTIONS.md` or
   `APP_WIREFRAMES.md`.
3. **Final corpus ingestion audit — REQUIRED.** Inspect the real CLI and code
   before running anything to determine whether source supports a multi-year
   interval and one complete snapshot, whether a clean new run is possible,
   whether snapshots must be combined, deduplication behavior, run naming,
   outputs, candidate/document scale and model-call needs. Treat a full
   multi-year rebuild as the preferred hypothesis only if the audit supports
   it; do not assume this capability.
4. **Final Corpus Build — REQUIRED.** Preflight, build, review and validate a
   new multi-year corpus and produce the deployment dataset described below.
   Do not modify or alias the 140-document development freeze.
5. **KPI definitions.** Freeze project and BOE-publication counts plus only the
   additional measures approved by Gates 1 and 2. Power is excluded from the
   August dashboard.
6. **Approved Gold extensions.** No candidate Gold extension enters August:
   `project_components` and `project_relationships` are deferred to POST-TFM.
7. **Dashboard.** Implement the approved KPIs, territorial map, latest-situation
   view and publication evolution without regressing existing exploration.
8. **Project detail.** Add only fields approved by the data catalogue while
   preserving full chronology, BOE evidence and the non-legal-status wording.
9. **Minimum safe error reporting.** Implement the approved preformatted mailto
   with bounded project/entity context and a safely configured recipient. It
   cannot modify data or approve corrections.
10. **Security.** Preserve contractual Gold loading, expected downstream ID,
   safe paths/errors, pinned dependencies, secrets outside Git and a disabled
   public Gold explorer.
11. **Deployment.** Publish a simple versioned artifact derived from validated
   Gold, with reproducible configuration, rollback and smoke tests. Do not
   deploy directly from an ignored `runs/` directory.
12. **Final validation.** Run focused regressions, the full suite,
    reproducibility and security checks, visual review and production smoke
    tests after the functional freeze.
13. **Final holdout.** Select it only after the extraction/review policy and
    functional product are frozen. Exclude all 479 documents versioned in
    `development_used_documents.csv`; the holdout remains outside the core
    freeze. Exposure provenance is resolved, but no holdout has been selected.
14. **Delivery evidence.** Prepare screenshots, limitations, data identities,
    written-TFM evidence and synchronized documentation.
15. **Git closeout.** Review, commit and push only approved files, record the
    deployed version and preserve a clean final state.

Operational constraints that remain in force:

- Corrections use VS Code + Codex + versioned inputs + tests + regeneration.
  The human decides evidence and approval; derivable IDs and hashes are
  calculated by code. Streamlit does not correct data.
- The CLI does not yet combine a historical document snapshot and a new cohort
  automatically. Never replace the cumulative corpus with a partial cohort;
  full accumulation automation is POST-TFM unless indispensable for delivery.
- Every functional block closes with tests, documentation-impact review,
  human review and an explicitly approved commit/push before the next gate.

### Final corpus ingestion audit and preflight — REQUIRED

The audit must decide from the real CLI/code whether to reconstruct the full
interval in one new run or combine snapshots. If source can reproducibly build
the full interval, prefer **FULL MULTI-YEAR REBUILD** over manual merging for
reproducibility, deduplication and operational clarity; this remains a
hypothesis until verified.

Before execution, a preflight records source BOE count, candidates, documents
that actually require extraction, estimated model calls, disk space and time
per phase. The unknown scale, cost, model-call duration and human-review load
are a REQUIRED schedule risk, not a reason to estimate by running the pipeline
during planning.

### Final Corpus Build — REQUIRED

Before definitive deployment:

1. fix the final temporal period;
2. obtain all BOE candidates for that period;
3. build a complete and reproducible document corpus;
4. run extraction;
5. perform review;
6. apply approved corrections;
7. build Silver;
8. resolve territories;
9. group projects;
10. build Gold;
11. validate the result;
12. create the final downstream ID;
13. run regressions;
14. review cardinalities and domains;
15. obtain human corpus approval;
16. produce the deployment artifact.

Existing versioned corrections apply whenever their targets are present. New
errors follow review → human decision → versioned correction → tests → rebuild;
never edit Silver or Gold. Record unresolved blocking reviews before
deployment rather than forcing automatic resolution.

The final operational audit repeats row counts, domains, null coverage, PK/FK,
grouping, project IDs, locations, latest actions, mappings, URLs, geometries
and performance. It does not automatically reopen promoter, power or exhaustive
hybridisation. Deployment acceptance uses the final manifest and downstream
ID, expected tables, schemas, integrity, domains, geometry coverage, filters,
charts, map, detail, URLs, reporting, acceptable performance and smoke tests;
it never expects the development-corpus cardinalities.

The sequence is Final Corpus Build → final validation → functional freeze →
holdout under the existing procedure → final release. The holdout definition
and exclusion of `development_used_documents.csv` remain unchanged.

## 4. Conditional scope

Gate 1 decided:

- promoter, participants, power, a canonical project-power/assets model,
  exhaustive multi-technology, an exhaustive hybridisation flag, publication
  title and a complete publications dimension are **NO-GO FOR AUGUST / POST-TFM**;
- `project_components`, with storage only as a component, and positive explicit
  `project_relationships` remain approved concepts, but Gate 2 defers both to
  **POST-TFM**;
- external administrative geometry at CCAA, province and municipality levels
  is approved for August, subject to the later technical
  source/licence/simplification audit.

The deferred concepts are not implemented Gold contracts and must not be
designed or built before delivery. The August project detail works only with
existing Gold and contains no empty components/relationships sections.

## 5. Post-TFM

- administrative application;
- authentication, authorisation and roles;
- persistent full reporting/review backend;
- correction approval or pipeline execution from a UI;
- automatic document-snapshot accumulation and daily updates;
- advanced monitoring and a complete publications dimension;
- nonessential refactors and speculative architecture.

The minimum August report channel does not authorise these capabilities. If a
safe persistent solution requires a database, authentication or workflow
backend that violates the stop conditions, stop and apply the scope-cut rule.

## 6. Human gates and freezes

| Gate | Acceptance required before continuing |
| --- | --- |
| **1 — Data** | **PASSED 2026-08-19**; `APP_DATA_CATALOG` reviewed and explicit GO/NO-GO recorded |
| **2 — Product** | **PASSED 2026-08-20**; human decisions, KPI semantics and wireframes accepted |
| **3 — Gold** | Approved contracts/materialization validated, or explicit NO-GO confirms no extension |
| **4 — UI** | Dashboard functionally and visually reviewed |
| **5 — Deployment** | Public artifact deployed and smoke-tested with approved identity |
| **6 — Final** | Holdout, tests, reproducibility, documentation and delivery evidence accepted |

Codex must not skip or combine gates.

Gate 2 fixes two KPIs, the three-level map and two required charts, explicit
filters as the cross-filter mechanism, current navigation and mailto reporting.
Components and relationships are deferred. No material product decision remains
open.

| Freeze | Effective point | Consequence |
| --- | --- | --- |
| **Design freeze** | Effective after the Gate 2 commit dated 2026-08-20 | No new pages, KPIs, charts, detail data or reporting functions except approved material defects |
| **Data-model freeze** | End of 24 August | No Gold changes except material defects |
| **Functional freeze** | End of 27 August | Only bug fixes, security, deployment, documentation and validation |

The 140-document core freeze remains an unchanged development/regression
baseline at `runs/canonical-140-freeze-final-candidate-20260813/`, with tag
`tfm-core-freeze-2026-08-13`. It can reopen only for an evidenced material
defect in identity, grouping, chronology, action attribution, evaluation,
reproducibility or provenance, with explicit human approval. The Final TFM
corpus is a separate run with new identities, cardinalities and manifests; it
does not move the tag or rewrite the baseline.

## 7. Calendar 19–31 August

| Window | Outcome |
| --- | --- |
| **19–20 Aug** | Planning and Gates 1–2 closed; design freeze effective after Gate 2 commit |
| **20–21 Aug** | Final corpus ingestion audit, then preflight |
| **21–22 Aug** | Final temporal scope and reproducible build approach approved |
| **22–24 Aug** | Final multi-year build, extraction and first review; data-model freeze |
| **24–25 Aug** | Corrections, final Gold build, domains/cardinalities and human corpus approval |
| **25–27 Aug** | Dashboard MUST SHIP, project detail, minimum reporting and final-corpus performance; functional freeze |
| **27–28 Aug** | Publication artifact, security, deployment and smoke tests |
| **28–29 Aug** | Priority visual review, bug fixes and screenshots |
| **29–30 Aug** | Full suite, holdout, reproducibility, documentation and written TFM |
| **31 Aug** | Incident buffer and submission; no planned feature work |

**SCHEDULE RISK:** the ingestion path and extraction/review load are not yet
measured. The concrete mitigation is to close the audit/preflight by 21 August,
finish the build and first review by 24 August, keep both candidate Gold
extensions deferred, and reserve 25–27 August for the MUST SHIP dashboard. The
multi-year build must not slip to 30–31 August.

## 8. Stop conditions and scope-cut rule

Stop and report before acting if work requires:

- reopening or re-extracting the 140-document core freeze; the separately
  approved Final Corpus Build is not a core-freeze reopen;
- a new database, heavy dependency or complex authentication;
- a major architectural change;
- changes to project IDs or membership;
- Gold tables or fields not approved by Gate 1;
- ambiguous KPI semantics or loss of reproducibility;
- violation of the design, data-model or functional freeze.

Report the problem, impact, minimum solution, complete solution and August
recommendation. Human approval is required before continuing.

If the deadline is at risk, cut scope in this order:

1. preserve a correct, reproducible final corpus, extraction/review and Gold;
2. preserve the dashboard MUST SHIP and a minimal versioned deployment;
3. remove `project_relationships`, `project_components` and all other
   CONDITIONAL data;
4. remove chart-click interactions and nonessential visual refinements;
5. keep only the minimum isolated reporting channel;
6. preserve holdout, tests, reproducibility, security and documentation.

Across all cuts, prioritize correctness, reproducibility and security over
visual refinement, additional data, automation and administration. Never
sacrifice traceability for a visualization.

## 9. Final delivery checklist

Already closed; reopen only for a material bug:

- [x] Core data freeze validated and tagged.
- [x] Streamlit MVP committed and pushed (`479f513`).
- [x] User and Streamlit code guides committed and pushed.
- [x] Gold explorer and BOE URL fix committed and pushed (`c35136d`).
- [x] Administrative situation filters committed and pushed (`523887a`).

Remaining delivery checks:

- [x] Gate 1 reviewed on 2026-08-19; data, KPI and scope decisions recorded.
- [x] Gate 2 reviewed on 2026-08-20; product, KPI interaction and wireframes accepted.
- [ ] Final corpus ingestion audit and preflight approved.
- [ ] Final multi-year corpus built, reviewed and human-approved.
- [ ] Final Gold/downstream identity, domains, geometries and performance validated.
- [x] Candidate Gold extensions explicitly deferred to POST-TFM.
- [ ] Design, data-model and functional freezes declared on schedule.
- [ ] Focused tests and full suite pass after functional freeze.
- [ ] Final holdout completed without changing frozen development policy.
- [ ] Production publication artifact and identities verified.
- [ ] Public deployment and rollback smoke-tested; Gold explorer disabled.
- [ ] Security and priority visual reviews completed.
- [ ] Screenshots, limitations, documentation and written TFM synchronized.
- [ ] Final Git state reviewed, committed and pushed; submission recorded.

## Next required action

```text
FINAL CORPUS INGESTION AUDIT — PENDING HUMAN REVIEW
→ FINAL CORPUS PREFLIGHT 2022 V2 — SOURCE SNAPSHOT REUSABLE
→ SOURCE IDENTITY DRIFT — RESOLVED; CURRENT OFFICIAL SOURCE WINS
→ CANDIDATE FUNNEL R1+R3 — APPROVED AND IMPLEMENTED, PENDING PATCH REVIEW
→ SOURCE RELIABILITY — ACCEPTABLE
→ STRICT CONFIG IDENTITY — IMPLEMENTED; AUTOMATIC LEGACY REUSE = 0
→ HOLDOUT EXPOSURE PROVENANCE — RESOLVED; 479 BOE VERSIONED
→ P2 EXPOSURE — 263; PROVISIONALLY ELIGIBLE — 19,226
→ P2 TARGET PERIOD — 2024-01-01 TO 2026-08-20 INCLUSIVE
→ FINAL EXTRACTION PREFLIGHT P2 — COMPLETED
→ RESUME MITIGATION — VALIDATED IN REAL EXECUTION
→ HOLDOUT — 48 BOE SELECTED + VERSIONED; NOT EXECUTED
→ FINAL P2 MAIN-01 — CONTRACTUALLY CLOSED; 250 ACCOUNTED; 249 CURRENT; 1 REJECTED; 0 BLOCKERS
→ GEMINI MAIN-01 — EXECUTED; 2 AUTHORIZED OPERATIONAL RETRIES COMPLETED
→ DETERMINISTIC BLOCKER FIX — IMPLEMENTED + TESTED + COMMITTED
→ SEMANTIC DISPOSITION — CLOSED; 46241 REJECTED, 4032 RECTIFICATION-ONLY
→ EXPLICIT ERROR RETRY — EXACTLY 2 BOE COMPLETED; BOTH SUCCESSFUL
→ CUMULATIVE RECANONICALIZATION — IDEMPOTENT + TESTED + MATERIALIZED OFFLINE
→ ATTEMPT UNIQUENESS — ENFORCED IN LOADERS AND PUBLICATION
→ MAIN-01 AND MAIN-02 GEMINI RETRIES — CLOSED
→ FINAL P2 MAIN-02 — CLOSED; 500 ACCOUNTED; 499 CURRENT; 1 REJECTED; 0 BLOCKERS
→ CUMULATIVE MAIN-01 + MAIN-02 MODEL COST — USD 5.9837646
→ MAIN-02 DETERMINISTIC BLOCKERS — 8/8 RESOLVED OFFLINE
→ MAIN-02 TIMEOUT — ISOLATED OPERATIONAL RETRY COMPLETED
→ FINAL P2 MAIN-03 — EXECUTED; 245 SUCCESS; 5 BLOCKERS
→ MAIN-03 COST — USD 3.2474835; CUMULATIVE MODEL COST — USD 9.2312481
→ MAIN-03 FAILURE REVIEW — SYSTEMIC VALIDATION BUG AND HUMAN DISPOSITION REQUIRED
→ MAIN-03 DETERMINISTIC + REVIEW PRECEDENCE FIXES — IMPLEMENTED + 1,151 TESTS PASS
→ MAIN-03 TARGET DECISION — BOE-B-2024-3861 PRESERVED + VALIDATED
→ MAIN-03 REVIEW PRECEDENCE FIX — IMPLEMENTED + TESTED
→ MAIN-03 OFFLINE SNAPSHOT V2 — 750 ACCOUNTED; 747 CURRENT; 1 REJECTED; 2 OPERATIONAL BLOCKERS
→ MAIN-03 OPERATIONAL RETRIES — 2 CANDIDATES; NOT AUTHORIZED
→ ANCHOR + HISTORICAL BACKFILL AUDIT — COMPLETED; CONTINUE P2
→ SHORT-WINDOW BACKFILL AUDIT — COMPLETED; HUMAN DECISION PENDING
→ W14 PILOT — 48 NON-HOLDOUT MODEL DOCS; 6 REUSABLE; 42 NEW CALLS; NOT AUTHORIZED
→ CORPUS PIVOT — NOT APPROVED; P2 REMAINS CURRENT
→ GEMINI — NO FURTHER CALLS AUTHORIZED
→ MAIN-04 — PAUSED; NOT AUTHORIZED
→ HOLDOUT — NOT EXECUTED
→ NEXT: HUMAN DECISION ON BOUNDED W14 ANCHOR PILOT
```

The source, configuration, funnel, corrections and cost evidence pass the P2
preflight. The holdout and bounded cumulative execution package are versioned
and tested. The two human decisions remain versioned. The two authorized
`main-01` operational retries and the isolated `main-02` retry succeeded. The
idempotent offline rematerialization at
`runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01-final-v2` preserves
501 unique attempts, 249 current extractions, one rejection and zero blockers.
The loader and publication gate now enforce attempt uniqueness. The cumulative
offline `main-02` result is closed with 500 documents accounted, 499 current
extractions, one inherited rejection and zero blockers. `main-03` executed 250
new documents: 245 succeeded and five entered blocking review. Two
deterministic false blockers replay as non-relevant and the approved
`BOE-B-2024-3861` review now survives canonicalization without changing its
component scopes or targets. The loader-valid cumulative snapshot
`extraction-main-03-recanonicalized-v2` accounts for 750 documents, with 747
current extractions, one inherited rejection, zero semantic blockers and two
operational blockers. The operational retries for `BOE-B-2025-41490` and
`BOE-B-2025-45035` remain separate and unauthorized. The holdout remains
unexecuted and `main-04` remains paused and unauthorized. The prior annual
anchor/backfill decision remains historical evidence. The short-window audit
does not change the corpus: W14 is only a candidate for a bounded anchor pilot,
pending human decision, and P2 remains current until that gate is resolved.
