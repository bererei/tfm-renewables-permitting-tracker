# TFM BOE Energy Tracker

## Mission

Build a reproducible research pipeline that reconstructs the administrative
lifecycle of named electricity-generation projects from official BOE
publications.

Prioritize a complete, validated, explainable, and evaluable pipeline over
additional fields, product features, deployment, or architectural complexity.

## TFM closeout mode — highest project priority

Read `docs/TFM_CLOSEOUT.md` before proposing or implementing development work;
it is the source of truth for the roadmap and phase gates through delivery.

Current phase: **deterministic INE location enrichment**. Next: **project
grouping**.

- Classify every new proposal as BLOCKER, REQUIRED, OPTIONAL, or POST-TFM. Do
  not start OPTIONAL or POST-TFM work while BLOCKER or REQUIRED work remains.
- Give each development task one primary objective. Inspect before modifying,
  declare non-goals, and implement the smallest sufficient change.
- Run focused tests and the appropriate regression suite. Report the diff,
  test results, Git status, and remaining risks, then stop for human review.
- Do not commit unless explicitly requested, and do not start the next phase
  automatically.
- Do not migrate notebooks unless their logic is required by the final Python
  pipeline or Streamlit application.
- Prefer a documented non-blocking limitation over an unnecessary refactor.
- Do not reopen the frozen extractor unless evidence shows that it blocks the
  vertical product, as defined in `docs/TFM_CLOSEOUT.md`.

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
- Ambiguous or pending records must not pass silently into Gold as confirmed
  data.
- Gold outputs must be fully regenerable from validated Silver inputs,
  versioned rules, and explicit manual overrides.
- Gold primary keys, foreign keys, granularities, and publication provenance
  must be validated.
- Do not publish a partial or invalid Gold snapshot over the last valid one.

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
- Do not expand work into Streamlit, authentication, administration, feedback,
  scheduling, or deployment unless explicitly requested.

## Extraction safeguards

- Do not change the extraction contract, prompt semantics, canonicalisation
  policy, or validated pilot invariants without explicit approval.
- Preserve regression guarantees enforced by `tests/extraction` unless an
  approved contract or domain correction requires updating them.
- Separate essential extraction fields from optional enrichment.
- A failure in optional enrichment must not discard a valid core event unless
  the active contract requires it.
- Do not make real provider or model calls unless the task explicitly requires
  them.
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

## Verification

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

## Completion report

For non-trivial changes or when closing a phase, report:

- initial diagnosis;
- files changed;
- behavior or contracts changed;
- tests and checks executed;
- results;
- remaining limitations or risks;
- acceptance criteria satisfied or pending;
- recommended next step.

Unless the task specifies another severity scale, classify findings as:

1. blocking for the TFM;
2. important but non-blocking;
3. optional improvement.
