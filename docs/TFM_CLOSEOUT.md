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

The validated application reads only the four contractual Gold tables,
verifies the expected downstream identity and never reads Silver or executes
the pipeline. Project detail always uses the complete published chronology,
independently of the filters used to locate the project.

Current phase: **product completion**. Gate 1 is complete. Public deployment,
minimum safe error reporting and the final holdout remain pending. Minimal
`project_components` and explicit `project_relationships` are approved
candidates, not implemented Gold contracts.

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
  publications over the filtered product set; Gate 2 must define their exact
  filter interaction.

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
2. **APP_PRODUCT_SPEC — Gate 2.** Create and review
   `docs/APP_PRODUCT_SPEC.md` with business questions, approved KPIs,
   dimensions, measures, filters, pages, charts, map, interactions, error
   states, reporting behavior and Markdown/ASCII wireframes. Do not create
   separate `APP_QUESTIONS.md` or `APP_WIREFRAMES.md`.
3. **KPI definitions.** Freeze project and BOE-publication counts plus only the
   additional measures approved by Gates 1 and 2. Power is excluded from the
   August dashboard.
4. **Approved Gold extensions.** Implement only indispensable structures given
   explicit GO. A documented NO-GO is a valid completion outcome.
5. **Dashboard.** Implement the approved KPIs, territorial map, latest-situation
   view and publication evolution without regressing existing exploration.
6. **Project detail.** Add only fields approved by the data catalogue while
   preserving full chronology, BOE evidence and the non-legal-status wording.
7. **Minimum safe error reporting.** Gate 2 chooses the smallest secure
   mechanism. It may collect project/entity, error category, bounded
   description and optional suggested value, but cannot modify data or approve
   corrections.
8. **Security.** Preserve contractual Gold loading, expected downstream ID,
   safe paths/errors, pinned dependencies, secrets outside Git and a disabled
   public Gold explorer.
9. **Deployment.** Publish a simple versioned artifact derived from validated
   Gold, with reproducible configuration, rollback and smoke tests. Do not
   deploy directly from an ignored `runs/` directory.
10. **Final validation.** Run focused regressions, the full suite,
    reproducibility and security checks, visual review and production smoke
    tests after the functional freeze.
11. **Final holdout.** Select it only after the extraction/review policy and
    functional product are frozen. Exclude all documents in
    `development_used_documents.csv`; the holdout remains outside the core
    freeze.
12. **Delivery evidence.** Prepare screenshots, limitations, data identities,
    written-TFM evidence and synchronized documentation.
13. **Git closeout.** Review, commit and push only approved files, record the
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

## 4. Conditional scope

Gate 1 decided:

- promoter, participants, power, a canonical project-power/assets model,
  exhaustive multi-technology, an exhaustive hybridisation flag, publication
  title and a complete publications dimension are **NO-GO FOR AUGUST / POST-TFM**;
- `project_components`, with storage only as a component, and positive explicit
  `project_relationships` are approved candidates for **minimal modelling**;
- external administrative geometry at CCAA, province and municipality levels
  is approved for August, subject to the Gate 2 source/licence/simplification
  decision.

The approved candidates are not implemented Gold contracts. They must retain
lineage, use only existing Silver and require no re-extraction. Stop and drop
them from August if they require a core-freeze reopen, project-ID changes,
complex topology, unresolved ambiguity or more than one significant block
outside the calendar. Implement components first and cut relationships first.

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
| **2 — Product** | `APP_PRODUCT_SPEC`, KPI semantics and wireframes reviewed |
| **3 — Gold** | Approved contracts/materialization validated, or explicit NO-GO confirms no extension |
| **4 — UI** | Dashboard functionally and visually reviewed |
| **5 — Deployment** | Public artifact deployed and smoke-tested with approved identity |
| **6 — Final** | Holdout, tests, reproducibility, documentation and delivery evidence accepted |

Codex must not skip or combine gates.

| Freeze | Effective point | Consequence |
| --- | --- | --- |
| **Design freeze** | End of 22 August | No new product requirements except material defects |
| **Data-model freeze** | End of 24 August | No Gold changes except material defects |
| **Functional freeze** | End of 27 August | Only bug fixes, security, deployment, documentation and validation |

The core freeze remains separate and can reopen only for an evidenced material
defect in identity, grouping, chronology, action attribution, evaluation,
reproducibility or provenance, with explicit human approval.

## 7. Calendar 19–31 August

| Window | Outcome |
| --- | --- |
| **19–20 Aug** | Planning committed; start `APP_DATA_CATALOG` |
| **20–21 Aug** | Data catalogue closed; GO/NO-GO per field |
| **21–22 Aug** | Product spec, KPI semantics and wireframes reviewed; design freeze |
| **22–24 Aug** | Approved Gold extensions only; tests and validation; data-model freeze |
| **24–27 Aug** | Dashboard, project detail and minimum reporting; functional freeze |
| **27–28 Aug** | Publication artifact, security, deployment and smoke tests |
| **28–29 Aug** | Priority visual review, bug fixes and screenshots |
| **29–30 Aug** | Full suite, holdout, reproducibility, documentation and written TFM |
| **31 Aug** | Incident buffer and submission; no planned feature work |

## 8. Stop conditions and scope-cut rule

Stop and report before acting if work requires:

- reopening the core freeze or broad re-extraction;
- a new database, heavy dependency or complex authentication;
- a major architectural change;
- changes to project IDs or membership;
- Gold tables or fields not approved by Gate 1;
- ambiguous KPI semantics or loss of reproducibility;
- violation of the design, data-model or functional freeze.

Report the problem, impact, minimum solution, complete solution and August
recommendation. Human approval is required before continuing.

If the deadline is at risk, cut scope in this order:

1. remove all non-approved and CONDITIONAL data;
2. keep the rejected power KPI out of the August dashboard;
3. keep only the minimum isolated reporting channel;
4. limit visual work to comprehension, accessibility and demonstration defects;
5. keep deployment minimal, versioned and read-only;
6. preserve tests, holdout, reproducibility, security and documentation.

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
- [ ] Gate 2 reviewed; product, KPI interaction and wireframes accepted.
- [ ] Approved Gold extension validated or explicit NO-GO recorded.
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
Create and human-review docs/APP_PRODUCT_SPEC.md
→ complete Gate 2 — Product
```

Do not implement new Gold fields, the map, charts or a Streamlit redesign
before `docs/APP_PRODUCT_SPEC.md` is created and human-reviewed for
**Gate 2 — Product**.
