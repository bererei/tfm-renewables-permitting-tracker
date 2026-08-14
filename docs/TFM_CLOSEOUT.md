# TFM closeout roadmap

This document is the source of truth for current status, delivery priorities,
calendar, risks and phase gates through **31 August 2026**. Stable engineering
rules live in `AGENTS.md`; user procedures and command examples are implemented
in `docs/USER_GUIDE.md`, committed at checkpoint `898df2b`.

## Mission

Deliver a complete, reproducible and evaluated vertical product:

```text
BOE
→ extraction
→ validated Silver
→ deterministic INE enrichment
→ project grouping
→ Gold chronology and territory
→ read-only Streamlit application
```

Decision rule:

```text
complete + reproducible + evaluated
>
perfect + exhaustive
```

Delivery deadline: **31 August 2026**. Scope freeze: **19 August 2026**.

## Status vocabulary

- **Implemented**: the behavior exists in the working repository.
- **Validated**: the relevant automated or reproducibility checks passed at its
  recorded checkpoint.
- **Committed**: the implementation is in Git history.
- **Pushed**: the commit is reachable from `origin/tfm-final`.
- **Deployed**: a reproducible public instance exists; local execution alone is
  not deployment.

## Current status — 14 August 2026

| Area | Status | Evidence |
| --- | --- | --- |
| 13-table Silver contract and materialization | Implemented, validated, committed and pushed | Included in the final core freeze |
| Versioned human action corrections | Implemented, validated, committed and pushed | Five approved exclusions applied without editing derived Parquets |
| Deterministic territory resolution and project grouping | Implemented, validated, committed and pushed | Included in the final core freeze |
| Core freeze: `projects` and `project_events` | Frozen and reproducibly validated | `docs/freezes/core_data_freeze_2026-08-13.md`; tag `tfm-core-freeze-2026-08-13` |
| Gold `project_locations` and `project_location_sources` | Implemented, persistently materialized, reproducibly validated, committed and pushed | Commit `9a0916d`; frozen project IDs and `project_events` semantics unchanged |
| Local read-only Streamlit MVP | Implemented, validated, committed and pushed | Commit `479f513`, also at `origin/tfm-final` |
| Closeout documentation consolidation | Committed and pushed | Commit `f64e5d7`, also at `origin/tfm-final` |
| `docs/USER_GUIDE.md` | Implemented, reviewed, committed and pushed | Commit `898df2b`, also at `origin/tfm-final` |
| `docs/STREAMLIT_CODE_GUIDE.md` and selective comments | Implemented — pending human review | Technical architecture and non-obvious decisions documented without behavior changes |
| Local read-only Gold explorer | REQUIRED pending | Not implemented |
| Public read-only web application | REQUIRED pending | No deployment has been declared |

The core freeze covers extraction and canonicalisation, versioned corrections,
the 13 Silver tables, INE enrichment, grouping, `projects` and
`project_events`. The two location tables and Streamlit were deliberately
additive and remain outside that frozen scope, as the freeze declaration
states.

The local MVP already provides:

- a contractual Gold loader that verifies the expected downstream identity and
  the four table contracts;
- read-only access to `projects`, `project_events`, `project_locations` and
  `project_location_sources`, with no Silver or pipeline access;
- deterministic filters, including OR within a dimension, AND between
  dimensions, same-row action/decision matching and territorial hierarchy;
- a project catalogue, project detail, published administrative chronology and
  methodology view;
- query, loader and downstream regression tests plus Streamlit `AppTest`
  coverage.

Current phase: **product completion**.

Current gate: human review of `docs/STREAMLIT_CODE_GUIDE.md` and the selective
Spanish comments.

Next: review and commit the code guide and comments, then add the local Gold
audit view.

## REQUIRED before delivery

1. **Consolidate documentation — COMMITTED AND PUSHED.** Stable rules live in
   `AGENTS.md` and volatile planning here; checkpoint `f64e5d7`.
2. **Create `docs/USER_GUIDE.md` — COMMITTED AND PUSHED.** The complete first
   version documents the local product and update workflow; checkpoint
   `898df2b`.
3. **Create `docs/STREAMLIT_CODE_GUIDE.md` — IMPLEMENTED, PENDING HUMAN
   REVIEW.** It explains file responsibilities, safe extension points,
   UI/data separation and focused tests.
4. **Add selective Spanish comments — IMPLEMENTED, PENDING HUMAN REVIEW.** The
   comments cover only non-obvious loader, cache, filter and navigation
   decisions, without changing behavior.
5. **Add a local read-only Gold explorer — REQUIRED PENDING.** Cover the four
   Gold tables with rows, columns, dtypes, PK/FK, nulls, domains, simple filters
   and a data dictionary; it must not write data.
6. **Perform the visual review and priority improvements — PLANNED.** Focus on
   clarity, navigation, filters, project detail, chronology, territorial scope,
   methodology, empty states and non-technical language.
7. **Publish a reproducible read-only web version — REQUIRED PENDING.** Keep
   pipeline execution, writes, authentication and administration out of the
   public app.
8. **Complete final validation and delivery — PLANNED.** Include product and
   methodological evaluation, the pending final holdout, reproducibility
   evidence, screenshots, documentation and the written TFM. The holdout
   remains outside the frozen data scope, as declared by the freeze document.

## CONDITIONAL work

Audit promoter, participants, capacity, associated components and publication
title before adding any of them. For each field, measure coverage, nullability,
quality, ambiguity, granularity, history and lineage.

Implement a field before delivery only when all of these conditions hold:

- the data already exists with sufficient quality;
- its Gold granularity and contract are clear;
- its source lineage is preserved;
- the change is bounded and does not reopen the frozen core;
- it does not put REQUIRED work or the deadline at risk.

Streamlit must not read Silver directly to compensate for a missing Gold field.
Missing, ambiguous or low-quality fields are documented limitations, not a
reason to force a late schema expansion.

## POST-TFM backlog

- public “Reportar posible error” button and persistent report storage;
- separate administrative application;
- authentication, authorisation and role management;
- report review and assisted/versioned correction generation;
- controlled administrative pipeline execution;
- daily BOE updates, scheduling, monitoring and full automation;
- production hardening beyond the minimum reproducible public deployment.

The public and administrative applications remain separate. Reports and
approved corrections must never edit Gold or other derived Parquets directly.

## Calendar

| Window | Planned outcome | Status at 14 Aug |
| --- | --- | --- |
| 14–15 Aug | Close MVP and planning | MVP `479f513` and planning consolidation `f64e5d7` committed and pushed |
| 15–18 Aug | User guide, code guide and selective comments | User guide committed; code guide and comments implemented — pending human review |
| 18–21 Aug | Local Gold explorer and structural/semantic audit | Planned |
| 21–23 Aug | Priority visual and usability improvements | Planned |
| 23–25 Aug | Audit missing fields and decide CONDITIONAL scope | Planned |
| 25–27 Aug | Reproducible read-only web publication | Planned |
| 27–29 Aug | Final evaluation, validation, screenshots and documentation | Planned |
| 30–31 Aug | Incident margin, written TFM and delivery | Planned |

After the **19 August scope freeze**, start only work that directly protects a
REQUIRED deliverable, fixes a blocker in the vertical product, or preserves
critical reproducibility. Do not use the remaining calendar to add convenience
features.

## Risks and scope cuts

| Risk | Control or cut |
| --- | --- |
| Documentation drifts from the executable CLI | Verify every documented command against the real CLI and update the user guide with affected changes |
| Conditional fields consume the delivery window | Audit first; omit any field without reliable granularity and lineage |
| Public deployment expands into operations | Deploy only the read-only Gold application; defer admin, writes, accounts and automation |
| Visual refinement delays validation | Fix only comprehension, navigation and accessibility issues that affect the demonstration |
| A late data concern reopens extraction | Apply the freeze reopening rule below; record secondary issues as limitations |
| A new snapshot is mistaken for validated output | Require manifests, contractual identities, reproducible checks and explicit validation status |

Cut scope in this order when schedule risk appears:

1. omit all CONDITIONAL fields;
2. limit visual work to defects that impede comprehension;
3. keep deployment minimal and read-only;
4. preserve validation, reproducibility, documentation and the written TFM.

## Documentation and operational deliverables

`docs/USER_GUIDE.md` is the committed source for architecture
concepts, real CLI commands, adding BOE documents, extraction/review,
corrections from VS Code, Silver/Gold regeneration, validation, publication,
rollback, examples, troubleshooting and glossary. The practical correction
procedure belongs there, not in `AGENTS.md` or this roadmap.

`docs/STREAMLIT_CODE_GUIDE.md` now documents module responsibilities, safe UI
changes, adding columns or filters, view changes and the tests required for each
kind of modification; it remains pending human review.

The documentation Definition of Done is stated once in `AGENTS.md`. Before
delivery, confirm that the user guide examples execute against the real CLI and
that README, guides, screenshots and deployment instructions agree on the
validated Gold snapshot.

## Public web publication gate

The minimum public deployment must:

- use a pinned, validated four-table Gold snapshot and verify its expected
  downstream identity;
- remain read-only and expose no filesystem path, secret or pipeline control;
- preserve the local MVP's contractual loading and methodology explanation;
- document environment configuration and a reproducible deployment procedure;
- pass local regression and `AppTest` checks before the deployed instance is
  visually verified.

This gate does not authorise a write path, external model call, live BOE fetch,
account system or administrative correction workflow.

## Freeze and corrections

The historical extraction-freeze tag and runs remain immutable references. The
final core freeze may be reopened only for a concrete, evidenced material defect
that affects project identity, grouping, administrative chronology, action
attribution, final evaluation, reproducibility or provenance. Presentation
changes, additional filters, documentation, additive location views and
POST-TFM features do not reopen it.

Approved manual corrections remain versioned inputs applied before Silver. Do
not edit generated Parquets. Distinguish isolated from systematic defects,
review diffs and tests, calculate technical identifiers automatically, and
regenerate validated Silver and Gold. The detailed operator workflow is
implemented in `docs/USER_GUIDE.md`.

## Final delivery checklist

- [x] Documentation consolidation reviewed, committed and pushed (`f64e5d7`).
- [x] `docs/USER_GUIDE.md` complete, reviewed, committed and pushed (`898df2b`).
- [ ] `docs/STREAMLIT_CODE_GUIDE.md` and selective comments complete.
- [ ] Local Gold explorer and audit complete without writes.
- [ ] Priority visual review complete on the local app.
- [ ] CONDITIONAL fields explicitly included or cut after audit.
- [ ] Minimal public read-only deployment reproducible and visually verified.
- [ ] Relevant tests, Streamlit `AppTest` and final evaluation pass.
- [ ] Freeze and additive Gold identities remain verified.
- [ ] Screenshots, limitations, reproducibility evidence and final report ready.
- [ ] Final changes reviewed, committed and pushed; delivery artifacts recorded.

Do not require perfection to close the TFM. Do not start the next item
automatically: finish its acceptance evidence and stop for human review.
