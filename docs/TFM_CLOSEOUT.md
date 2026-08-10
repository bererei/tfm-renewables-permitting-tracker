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
Extraction freeze: DONE
tag: tfm-extraction-freeze-2026-08

Current phase:
Gold chronology

Next:
Executable Python pipeline
```

The extraction core is frozen. Reopen it only when concrete evidence shows
that a defect blocks project identification, grouping, chronology, the final
pipeline, or final evaluation.

## Roadmap

| Phase | Window | Status |
| --- | --- | --- |
| 1. Extraction freeze | Completed | DONE |
| 2. Deterministic INE enrichment | 10–11 Aug | DONE |
| 3. Project grouping | 12–15 Aug | DONE |
| 4. Gold chronology | 16–17 Aug | CURRENT |
| 5. Executable Python pipeline | 18–19 Aug | NEXT |
| 6. Streamlit | 20–23 Aug | PLANNED |
| 7. Final holdout evaluation | 24–26 Aug | PLANNED |
| 8. Documentation / delivery | 27–31 Aug | PLANNED |

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

The tag `tfm-extraction-freeze-2026-08` marks the frozen extraction core. Do
not reopen the extraction contract, canonicalisation, granularity, targets,
participants, or components unless a demonstrated defect prevents this flow:

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
