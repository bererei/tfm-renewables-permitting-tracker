# TFM closeout roadmap

This document is the source of truth for development priorities and phase
gates through the TFM delivery at the end of August 2026. Keep it practical and
update it only when the delivery plan changes.

## Mission

Deliver a complete vertical product before the end of August 2026:

```text
BOE
→ extraction
→ deterministic INE enrichment
→ project grouping
→ Gold chronology
→ executable Python pipeline
→ Streamlit
```

Decision rule:

```text
complete + reproducible + evaluated
>
perfect + exhaustive
```

## Current status

```text
Final core data freeze: DONE — validated 2026-08-13
freeze declaration: docs/freezes/core_data_freeze_2026-08-13.md
validated run: runs/canonical-140-freeze-final-candidate-20260813/
historical tag preserved: tfm-extraction-freeze-2026-08
historical canonical run preserved: canonical-140-freeze-20260811
Deterministic INE enrichment: DONE
Project grouping: DONE
Gold implementation: DONE
Pipeline integration implementation: DONE
Batch recanonicalization capability: DONE
Limited extraction freeze fixes: DONE
IDAA substantive decision refinement: DONE
Human correction layer: DONE — 5 approved historical-action exclusions
Final corrected canonical run: DONE
Formal freeze validation: DONE — PASSED
Gold validation against freeze-run Silver: DONE
Additive Gold project locations implementation: DONE
Additive Gold project locations materialization and validation: DONE
Local read-only Streamlit MVP: IMPLEMENTED AND VALIDATED

Current phase:
Product completion

Current gate:
Human checkpoint for the local Streamlit MVP

Next:
Final product validation
TFM documentation and delivery
```

The executable Python orchestration layer is complete. The historical canonical
140 run and extraction-freeze tag remain immutable references. The limited
decision fixes, batch recanonicalization, substantive IDAA outcomes, and five
versioned human exclusions have been applied to a new corrected canonical run.
Its Silver and Gold outputs passed formal validation and an independent
deterministic reconstruction without model calls. The final core data freeze is
declared in `docs/freezes/core_data_freeze_2026-08-13.md`.

The additive `project_locations` and `project_location_sources` code,
contracts, persistent materialization and final validation are complete
without changing frozen project IDs or `project_events` semantics. The local
read-only Streamlit MVP is implemented and validated over the four Gold
tables. Public deployment and UI-based reports/assisted corrections remain
pending. The next REQUIRED work is final product validation and TFM
documentation/delivery.

Outside this limited decision correction, the extraction core remains frozen.
Reopen it only when concrete evidence shows that a defect blocks project
identification, grouping, chronology, the final pipeline, or final evaluation.

## Roadmap

| Phase | Window | Status |
| --- | --- | --- |
| 1. Extraction freeze | Completed | FINAL CORE DATA FREEZE DONE; HISTORICAL FREEZE PRESERVED |
| 2. Deterministic INE enrichment | 10–11 Aug | DONE |
| 3. Project grouping | 12–15 Aug | DONE |
| 4. Gold implementation | 16–17 Aug | DONE |
| 5. Pipeline integration + canonical regeneration | 18–19 Aug | DONE |
| 6. Gold validation against freeze-run Silver | Completed 13 Aug | DONE |
| 7. Project locations + Streamlit MVP | 20–23 Aug | IMPLEMENTED AND VALIDATED — CHECKPOINT PENDING |
| 8. Final holdout evaluation | 24–26 Aug | PLANNED |
| 9. Documentation / delivery | 27–31 Aug | PLANNED |

## Scope freeze

The scope freeze is **19 August 2026**. After that date, start work only when
it directly affects:

- a broken pipeline;
- project identity or grouping;
- incorrect chronology;
- a broken Streamlit application;
- final evaluation;
- critical reproducibility.

Do not add new features after the scope freeze.

## Priority classification

Classify every proposal before development:

| Priority | Meaning |
| --- | --- |
| BLOCKER | Prevents the vertical product from working correctly. |
| REQUIRED | Necessary to deliver the defined minimum TFM. |
| OPTIONAL | Improves the system, but delivery works without it. |
| POST-TFM | Must be deferred until after delivery. |

While BLOCKER or REQUIRED work remains, do not start OPTIONAL or POST-TFM
work.

## Deferred work

Treat the following as OPTIONAL or POST-TFM unless evidence proves that they
block the vertical product:

- exhaustive refinement of `administrative_action_targets`;
- participant propagation refinement;
- component-link refinement;
- complex linguistic coordination in the extractor;
- a sophisticated semantic-warning framework;
- an administrative correction interface;
- daily BOE automation;
- cloud or production deployment;
- cosmetic refactors;
- Streamlit features not needed to demonstrate the objective.

## Extraction freeze rule

The tag `tfm-extraction-freeze-2026-08` and its canonical run remain historical
references. Demonstrated chronology defects authorised one limited reopening:
the contract and canonicalisation of explicit `desestim*` authorization
decisions and substantive IDAA decisions. The resulting corrected run has been
recanonicalized, corrected, independently reproduced, formally validated, and
declared as the final core data freeze in
`docs/freezes/core_data_freeze_2026-08-13.md`. Approved corrections remain
separate versioned inputs applied before Silver.

Outside that limited correction, do not reopen the extraction contract,
canonicalisation, granularity, targets, participants, or components unless a
demonstrated defect prevents this flow:

```text
project identity
→ grouping
→ chronology
→ pipeline/evaluation
```

Record secondary defects as known limitations.

## INE phase exit criteria

The completed phase is **deterministic INE location enrichment**. Its production
logic must live in Python modules, not depend on a notebook, and remain
deterministic and reproducible.

Minimum behavior:

- resolve municipalities on a best-effort basis when evidence is sufficient;
- allow an unresolved municipality without blocking the pipeline;
- resolve a province independently when its evidence is sufficient, even if
  the municipality remains unresolved;
- derive the autonomous community deterministically from reliable territorial
  information, especially province or INE codes, when possible;
- keep independent `municipality_resolution_status`,
  `province_resolution_status`, and
  `autonomous_community_resolution_status` values;
- reuse existing contracts and enums instead of creating redundant concepts;
- include deterministic tests and reproducible outputs;
- avoid exhaustive resolution of all Spanish toponymy.

The phase exits when all of those criteria are satisfied by production `.py`
code and an unresolved municipality does not prevent province or autonomous
community resolution.

## Pipeline integration exit criteria

The executable Python pipeline must cover this local transformation path:

```text
BOE source
→ document preparation
→ extraction
→ validated Silver
→ INE
→ grouping
→ Gold
```

It must not require notebooks. Streamlit consumes Gold and is not part of the
transformation pipeline.

## Definition of Done for a phase

A phase can close when:

- its minimum objective is met;
- relevant tests pass;
- it produces reproducible output;
- non-blocking limitations are identified;
- the diff has been reviewed;
- the phase changes have been committed;
- the commit has been pushed.

Do not require perfection to close a phase, and do not start the next phase
automatically.
