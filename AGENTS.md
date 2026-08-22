# TFM BOE Energy Tracker

## Mission

Build a reproducible research pipeline that reconstructs the administrative
lifecycle of named electricity-generation projects from official BOE
publications.

Prioritize a complete, validated, explainable, and evaluable pipeline over
additional fields, product features, deployment, or architectural complexity.

## TFM closeout mode — highest project priority

Read `docs/TFM_CLOSEOUT.md` before proposing or implementing development work;
it is the source of truth for current status, priorities, calendar, risks and
phase gates through delivery.

Final core data freeze: **COMPLETE**. The validated run is
`runs/canonical-140-freeze-final-candidate-20260813/`, and its versioned
declaration is `docs/freezes/core_data_freeze_2026-08-13.md`. The freeze covers
the extraction contract and canonicalisation, versioned human corrections,
the 13 Silver tables, deterministic INE enrichment and project grouping, and
Gold `projects` and `project_events`. The additive location tables and the
local Streamlit MVP are validated extensions, not additions to the frozen
scope.

Current phase: **product completion**.

- REQUIRED priorities are the approved data and product gates, the minimum
  dashboard, safe error reporting, public read-only deployment, final visual
  and security review, holdout, reproducibility evidence, screenshots and the
  written TFM.
- CONDITIONAL fields require an evidence audit and explicit human GO before
  Gold or Streamlit work. Streamlit must never read Silver directly.
- POST-TFM work includes the administrative application, authentication and
  roles, UI-driven corrections, operational automation and non-essential
  refactors.

Classify every proposal as BLOCKER, REQUIRED, CONDITIONAL, OPTIONAL, or
POST-TFM. Give each task one primary objective, inspect before modifying,
declare non-goals, implement the smallest sufficient change and stop for human
review before starting the next block. Do not commit unless explicitly
requested. Prefer a documented non-blocking limitation over unnecessary scope.

## August 2026 delivery guardrails

1. REQUIRED work always precedes CONDITIONAL, OPTIONAL and POST-TFM work.
2. Do not perform optional refactors while REQUIRED deliverables remain.
3. Do not reopen the core freeze unless a material correctness defect is
   demonstrated and the human reviewer approves reopening it.
4. Streamlit consumes validated Gold; never add ad-hoc Silver joins to the app.
5. Do not re-extract the frozen corpus merely to add presentation fields. An
   evidence audit must demonstrate necessity and the human reviewer must
   approve it.
6. Document a field as a limitation when it cannot be modelled reliably; do not
   infer it.
7. Every functional block ends with tests, documentation impact review, human
   review and an explicitly approved commit/push before the next block begins.
8. After the functional freeze, allow only bug fixes, security, deployment,
   documentation and validation work.
9. Do not add speculative architecture or administrative functionality before
   the August submission.
10. Before selecting a holdout, register every BOE manually inspected for
    development or evaluation in `config/evaluation/development_used_documents.csv`.

Once `docs/USER_GUIDE.md` exists, any change to CLI commands, paths,
environment variables, contracts, pipeline behavior, corrections, Gold tables,
navigation, deployment or the update procedure must update that guide in the
same commit. Verify documented commands against the real CLI.

## Sources of truth

- Treat approved domain rules, active data contracts, validated specifications,
  and package code as the primary sources of truth.
- Treat tests as executable regression guarantees, while verifying that they do
  not contradict approved domain rules or active contracts.
- Treat notebooks as orchestration, exploration, audit, and documentation
  layers—not as independent production implementations.
- Do not assume that documentation, comments, notebooks, historical outputs, or
  existing tests necessarily describe the intended current behavior; verify
  them against the active contracts and domain rules.
- Preserve behavioral guarantees enforced by valid regression tests unless the
  task explicitly corrects a contradiction with approved domain rules or active
  contracts.
- If the repository contains `docs/TFM_CONTEXT.md` or `docs/TFM_PLAN.md`, read
  the relevant sections before planning broad changes.
- Report contradictions between code, tests, documentation, contracts, and the
  requested behavior instead of resolving them silently.

## Domain rules

- Named electricity-generation plants are the roots used to group publications
  into canonical projects.
- Do not create a canonical generation project solely from standalone storage,
  evacuation, transmission, distribution, or other grid infrastructure.
- Storage and evacuation infrastructure may be associated with a named
  generation project when the BOE establishes that relationship.
- Within one BOE publication, represent each independent generation project as
  a separate publication event when the document provides enough evidence to
  distinguish it from the others.
- Do not group independent projects merely because they share a publication,
  promoter, administrative file, province, environmental procedure, or
  evacuation infrastructure.
- Multiple assets may remain in the same event when they form an integrated
  project, such as hybridisation, storage incorporation, substitution, or
  repowering.
- A project-specific document must identify a generation plant and at least one
  administrative action published in the document and linked to that plant or
  its associated components.
- A document classified as not relevant for generation projects must not create
  project events.
- Do not force uncertain classifications, locations, matches, or statuses.
  Preserve uncertainty and route it to review.
- Prefer omitting an uncertain secondary field over storing unsupported data or
  rejecting an otherwise valid administrative event.
- Do not create rules that special-case a BOE identifier when a general domain
  rule can express the required behavior.

## Evidence and traceability

- Never fabricate evidence, references, identifiers, metrics, or test results.
- Evidence must be a literal continuous passage from the source or explicitly
  separated literal fragments using `[...]` when composite evidence is
  permitted.
- Do not join discontinuous fragments and present them as a continuous quote.
- Preserve the source BOE identifier, publication date, and relevant evidence
  for every administrative event.
- Distinguish verified facts, deterministic derivations, model outputs, manual
  decisions, and unresolved cases.
- Every deterministic adjustment and manual correction must retain its reason,
  provenance, and applicable version.

## Silver data contract

- The 13 normalized Silver tables form one relational contract.
- Keep table names, column names, column order, dtypes, nullability, domains,
  primary keys, foreign keys, and polymorphic relationships explicit.
- Derive validation rules from the canonical contract instead of maintaining
  duplicate schema definitions.
- Treat physical row order as irrelevant to relational integrity.
- Apply deterministic ordering only when materializing outputs for
  reproducibility.
- Validation must not mutate input DataFrames.
- Empty tables must retain their complete schemas and dtypes.
- Do not use empty strings as missing values.
- Handle missing values with pandas null semantics such as `isna()` rather than
  requiring every in-memory null to be exactly `None`.
- Validate tables before writing and after reading them back from Parquet.
- A failed materialization must not publish a partial output or modify an
  existing valid materialization.
- Unless explicit concurrency coordination is implemented, assume a single
  writer for each materialization destination and do not claim cross-process
  exclusion guarantees.

## Manual decisions and Gold data

- Manual corrections must be stored as versioned, traceable inputs or
  overrides.
- Never edit generated Parquet files manually.
- Preserve the original extraction when applying a correction.
- Distinguish an isolated data defect from a systematic defect before choosing
  a correction or a code change.
- Review the correction diff and relevant tests, then regenerate and validate
  Silver and Gold.
- Calculate correction IDs, hashes, fingerprints and versions in code whenever
  they are derivable; do not enter them manually.
- Ambiguous or pending records must not pass silently into Gold as confirmed
  data.
- Gold outputs must be fully regenerable from validated Silver inputs,
  versioned rules, and explicit manual overrides.
- Gold primary keys, foreign keys, granularities, and publication provenance
  must be validated.
- Do not publish a partial or invalid Gold snapshot over the last valid one.

## Streamlit and operational runs

- Streamlit is a read-only presentation layer over validated, versioned Gold.
  It must not read Silver, execute the pipeline, call BOE/model services or
  provide data/correction write paths. An approved error-report channel must
  remain bounded, validated and separate from Gold and the correction flow.
- Keep a future administrative application separate from the public app.
- Treat `runs/` as regenerable, run-scoped operational output. Do not edit
  derived artifacts in place, alias a candidate as validated, or overwrite the
  last valid snapshot with a partial or invalid publication.
- Version declarations, contracts, rules and manual inputs in their designated
  repository paths; do not version operational runs merely to preserve them.
- Preserve lineage, manifests, semantic identities and reproducible ordering
  across materializations.

## Code organisation and refactoring

- Keep reusable production logic under `src/renewables_permitting`.
- Keep notebooks thin: they may configure, call, inspect, visualise, and audit
  package functionality.
- Move notebook logic into `src` incrementally.
- Do not duplicate functions between notebooks and `src`.
- Reuse existing utilities and contracts before creating new helpers.
- Add or update tests before deleting or replacing validated notebook
  implementations.
- Preserve public APIs, data contracts, and extraction semantics unless the task
  explicitly authorises a change.
- Keep modules focused on one responsibility and avoid speculative
  abstractions.
- Do not add dependencies unless they are necessary for the requested outcome.
- Do not expand work into authentication, administration, feedback, scheduling
  or automation unless explicitly requested and allowed by the closeout plan.

## Extraction safeguards

- Reopen the final core freeze only for a concrete, evidenced material defect
  in project identity, grouping, chronology, action attribution, final
  evaluation, reproducibility or provenance; presentation and additive product
  work do not qualify.
- Do not change the extraction contract, prompt semantics, canonicalisation
  policy, or validated pilot invariants without explicit approval.
- Preserve regression guarantees enforced by `tests/extraction` unless an
  approved contract or domain correction requires updating them.
- Separate essential extraction fields from optional enrichment.
- A failure in optional enrichment must not discard a valid core event unless
  the active contract requires it.
- Do not make real provider or model calls unless the task explicitly requires
  them.
- Before authorizing a long model run, require validated bounded scopes and a
  cumulative continuation path from durable attempts; reject resume inputs
  whose source or extraction identity is incompatible.
- Retry failed model attempts only through explicit BOE selection. Append a
  new attempt and preserve the failed historical attempt unchanged.
- Prefer offline tests, fixtures, mocks, and previously stored outputs during
  development.
- Record model, prompt, validation, and policy versions whenever extraction
  behavior depends on them.

## Change workflow

Before editing:

1. Read this file and the relevant project documentation.
2. Inspect Git status and preserve existing unrelated changes.
3. Inspect the affected implementation, contracts, and tests.
4. Identify existing code that can be reused.
5. State the intended scope and any contradictions or risks.

During editing:

- Make the smallest coherent change that satisfies the task.
- Preserve unrelated user changes.
- Do not modify data, notebooks, contracts, or pipeline stages outside the
  stated scope.
- Do not weaken validation merely to make a failing test pass.
- Do not make silent behavioral or contract changes.
- Add regression tests for every corrected defect.
- Keep test fixtures deterministic and independent of network access unless an
  integration test explicitly requires it.
- Do not commit, push, merge, publish, or deploy unless explicitly requested.

## Definition of Done

- Use the repository's documented commands and CI configuration as the
  authority for verification commands.
- Run the smallest relevant test suite during development.
- Run all affected subsystem tests before declaring the task complete.
- Run the full suite when closing a phase or changing shared contracts.
- Validate data outputs structurally and relationally, including Parquet
  round trips when applicable.
- Check formatting or diff integrity and inspect final Git status.
- Confirm that out-of-scope notebooks and data were not modified.
- Report all verification commands executed and their actual results.
- Report diagnostic commands when their output materially affected the
  implementation or conclusions.
- Do not claim that tests pass if they were not run or their execution was
  incomplete.
- Review documentation impact and update only the affected sources of truth.
  Report `Documentation impact`, `Documents reviewed`, `Documents updated` and
  `Reason`.
- For non-trivial changes, report the diagnosis, files and behavior changed,
  checks and results, remaining risks, acceptance status and next step.
- Stop for human review. Commit, push, publish or deploy only when explicitly
  authorised, and do not start the next functional block beforehand.

Unless the task specifies another severity scale, classify findings as:

1. blocking for the TFM;
2. important but non-blocking;
3. optional improvement.
