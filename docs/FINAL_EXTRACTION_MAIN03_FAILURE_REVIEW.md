# Final Extraction main-03 Failure Review

## 1. Purpose

This read-only review determines the disposition of the five blocking reviews
published by Final P2 `main-03` before any authorization of `main-04`. It uses
only the versioned code, the local source snapshot and persisted extraction
artifacts. It does not execute Gemini, query BOE, retry a document, publish a
snapshot or modify any run.

The review is REQUIRED because it identifies a deterministic validation gap
with exact exposures in `main-04`. The gate conclusion is:

```text
MAIN-04 BLOCKED BY SYSTEMIC CODE BUG
```

## 2. Snapshot

The contractual loader successfully loaded:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-03
```

| Property | Observed value |
| --- | ---: |
| Documents accounted | 750 |
| Current extractions | 744 |
| Rejected documents | 1 |
| Blocking reviews | 5 |
| Attempt rows | 1,501 |
| Unique attempt IDs | 1,501 |
| Duplicate attempt IDs | 0 |

The snapshot preserves the expected cumulative input and identities:

| Lineage field | Observed value |
| --- | --- |
| Previous cumulative input | `runs/final-tfm-p2-20240101-20260820-v1/extraction-main-02-final` |
| Source directory | `runs/final-corpus-preflight-20220101-20260820-v2/source/` |
| Source snapshot ID | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| Scope policy | `binary_named_generation_pre_model_guard_v4` |
| Extraction config ID | `4b54b89dbfe8640e` |
| Extraction contract ID | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |

The cumulative snapshot has valid loader, source, configuration, contract and
materialization provenance. No duplicate or incompatible attempt was found.

## 3. Review queue

The queue and durable attempts agree on these five blockers; the list was read
from the artifacts rather than assumed from the task:

| BOE | Failure | Stage | Structured output | Requests | Input tokens | Output/thinking tokens |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `BOE-B-2024-3861` | `TimeoutError` | `agent_run` | yes | 4 | 140,056 | 107,973 |
| `BOE-B-2024-45427` | `DocumentExtractionValidationError` | `document_validation` | yes | 2 | 8,912 | 1,993 |
| `BOE-B-2025-26539` | `DocumentExtractionValidationError` | `document_validation` | yes | 2 | 7,288 | 1,081 |
| `BOE-B-2025-41490` | `TimeoutError` | `agent_run` | no | 1 | 4,151 | 65,522 |
| `BOE-B-2025-45035` | `ReadError` | `agent_run` | no | 0 | 0 | 0 |

## 4. Recoverable timeout with output

### `BOE-B-2024-3861`

The timed-out attempt
`167a4329f74740588a8ad3f6ea0b1350` lasted 600.103 seconds. Its persisted
precanonical and canonical structured outputs are present and parse at the
Pydantic boundary. The output contains 10 events, 10 generation assets and 30
administrative actions, so it is structurally complete rather than truncated
or corrupt.

The local source describes shared evacuation infrastructure and then identifies
ten independently processed generation installations in a two-column table:
`Denominación` and `N.º de expediente`. The current bounded table-name helper
only recognizes the already-supported three-column form that also includes a
promoter. Consequently, current validation accepts the first two names from
other context but rejects assets 3 through 10 because it cannot prove that the
table denominations are generation plants.

There is a second semantic issue that prevents automatic acceptance: the first
two events target their actions at the event, whereas events 3 through 10
target `component_1`, although the publication concerns the same shared
evacuation infrastructure. A human must confirm the intended target
representation before publication.

The critical classification is therefore:

```text
structured output: schema-complete, not contractually valid under current code
current offline replay: FAIL
disposition: HUMAN REVIEW REQUIRED
new Gemini call required: NO
```

This is closest to option C: persisted content exists and is reusable, but it
cannot be accepted safely until the deterministic parser gap and target
disposition are resolved. The historical `TimeoutError` remains immutable
attempt provenance; any later deterministic derivation must preserve it rather
than rewrite the attempt.

## 5. Operational failures

### `BOE-B-2025-41490`

Attempt `bc39c1e457fa4f83809b1ee0d1f26236` timed out after 482.124 seconds.
There is no persisted structured output from which to reconstruct an
extraction. The request and usage counters are real attempt provenance, but
they do not constitute a reusable model result.

An isolated retry dry-run selected exactly this BOE: one pending document, one
explicit error retry, zero deterministic reuses and one model-required item.
Because it was a dry-run, planned/executed model calls were zero and no prior
success was selected.

```text
disposition: SAFE EXPLICIT RETRY
```

### `BOE-B-2025-45035`

Attempt `30fba907973b4eae9f19b54569dff538` failed with `ReadError` after
0.951 seconds, before any provider request or token usage was recorded. It has
no structured output and is an operational failure rather than a semantic
rejection.

Its isolated retry dry-run likewise selected exactly one pending document and
one explicit error retry, with zero deterministic reuses, no previous success
selected and zero planned/executed calls in dry-run mode.

```text
disposition: SAFE EXPLICIT RETRY
```

## 6. Document validation failures

### `BOE-B-2024-45427`

The publication accepts a withdrawal and archives the public-utility
proceeding for the electrical-installation project `LAAT 220 kV SET
Guadalsolar – SET Mirabal`. The source publishes a current administrative
action, but it does not name an electricity-generation plant: this is
standalone grid infrastructure. `Guadalsolar` is part of a company/substation
proper name, not the name of a solar generation asset.

The model output is a schema-valid `not_relevant` result with zero events. That
semantic result is correct. Current post-model validation rejects it because
the generation detector matches the substring `solar` inside `Guadalsolar` in
an electrical-installation context.

| Question | Answer |
| --- | --- |
| Source names a generation plant | NO |
| Source publishes a current administrative action | YES, for grid infrastructure |
| Model output represents the document correctly | YES |
| Validator is correct | NO |
| Root cause | `SCOPE_CONTEXT BUG` in the grid-infrastructure/proper-name boundary |
| Disposition | `RESOLVED NON-RELEVANT` after a bounded deterministic validation fix |

The grid-infrastructure family is already known, but its post-model exception
does not cover this exact proper-name collision. The fix must remain narrow;
changing the pre-model scope policy is neither necessary nor authorized.

### `BOE-B-2025-26539`

The publication submits an irrigation-community energy-optimization project
to public information. Its photovoltaic installation is auxiliary to pumping
and electromechanical equipment; the source does not identify a named
electricity-generation plant as a project root. The only occurrence resembling
`planta` is a postal floor reference.

The model output is a schema-valid `not_relevant` result with zero events and
is semantically correct. Current validation rejects it because the title's
photovoltaic wording triggers a project review before the narrower
non-generation main-object context can resolve the output. The existing
auxiliary-generation exception covers other bounded facilities, but not this
irrigation/pumping form.

| Question | Answer |
| --- | --- |
| Source names a generation plant | NO |
| Source publishes a current administrative action | YES, for the irrigation optimization project |
| Model output represents the document correctly | YES |
| Validator is correct | NO |
| Root cause | `SCOPE_CONTEXT BUG` in the auxiliary-generation boundary |
| Disposition | `RESOLVED NON-RELEVANT` after a bounded deterministic validation fix |

This case must be fixed in post-model validation. Broadening the pre-model
guard would change execution identity and could suppress cases that still need
model review.

## 7. Offline replay

Each persisted output was parsed with the current Pydantic contract and replayed
in memory from the local source through current canonicalization and document
validation.

| BOE | Pydantic boundary | Current replay | Semantic disposition |
| --- | --- | --- | --- |
| `BOE-B-2024-3861` | PASS | FAIL | Human target decision plus deterministic table-parser fix; no Gemini |
| `BOE-B-2024-45427` | PASS | FAIL | Correct `not_relevant`; bounded validator fix |
| `BOE-B-2025-26539` | PASS | FAIL | Correct `not_relevant`; bounded validator fix |

Three structured-output cases were replayed. Zero are publishable through the
current code without a correction. None requires a new Gemini call.

## 8. Systemic-risk analysis

The search used only local, non-holdout source documents assigned to
`main-01` through `main-20`. Future matches are risk candidates based on the
exact local text pattern; they are not semantic adjudications.

### Two-column independent-generation table

The unsupported `Denominación` / `N.º de expediente` table form occurs in two
historical documents (`BOE-B-2024-3861` and `BOE-B-2024-20846`) and in these 10
future-scope candidates:

| Scope | BOE candidates |
| --- | --- |
| `main-04` | `BOE-B-2024-3383`, `BOE-B-2024-45425` |
| `main-05` | `BOE-B-2024-25911`, `BOE-B-2024-26040` |
| `main-07` | `BOE-B-2025-12011` |
| `main-09` | `BOE-B-2024-17699` |
| `main-11` | `BOE-B-2025-6108`, `BOE-B-2025-21042` |
| `main-13` | `BOE-B-2025-42645` |
| `main-16` | `BOE-B-2024-29695` |

Risk is HIGH because two exact exposures are already present in `main-04`.
The minimum conceptual patch is to extend the bounded generation-table parser
to the exact two-column form when the surrounding text explicitly establishes
independent generation installations. Regression tests must reject unrelated
two-column tables and preserve current supported forms.

### Standalone grid title with a generation substring in a proper name

`BOE-B-2024-45427` is the one historical exact match found. No exact future
equivalent was found. A superficially similar future document that explicitly
names a photovoltaic plant was excluded from the count. Risk is LOW. The
minimum patch is a narrow post-model exception for a standalone LAAT/SET
publication with no genuine named generation plant.

### Auxiliary photovoltaic irrigation/pumping project

One future-scope candidate, `BOE-B-2025-16990` in `main-05`, shares the exact
auxiliary irrigation/energy-efficiency context. Together with the historical
`BOE-B-2025-26539`, this gives one future and one historical exposure. Risk is
MEDIUM. The minimum patch is a bounded post-model exception for the auxiliary
irrigation/pumping context without a named generation-project root.

These patches correct validation of existing semantics. If confined to the
post-model validator and bounded documentary matcher, established precedent
allows the scope policy, extraction config ID, instructions and contract ID to
remain unchanged; the deterministic implementation fingerprint changes. Any
change to the pre-model scope guard would instead require an explicit identity
assessment and likely a new configuration identity.

## 9. Retry requirements

Exactly two documents require a new Gemini call:

```text
BOE-B-2025-41490
BOE-B-2025-45035
```

The combined dry-run selected two pending documents and two explicit error
retries. It selected zero previous successes, zero semantic-error documents
and zero deterministic reuses. It reported two model-required documents, but
planned and executed zero model calls because `--execute-model` was absent.

No retry is appropriate for `BOE-B-2024-3861`, `BOE-B-2024-45427` or
`BOE-B-2025-26539`. Their persisted structured results must be addressed
offline after the bounded deterministic fixes and, for `3861`, human target
disposition.

## 10. Per-BOE disposition

| BOE | Final disposition | New Gemini call |
| --- | --- | ---: |
| `BOE-B-2024-3861` | `HUMAN REVIEW REQUIRED`; preserve and replay the structured output after the table-parser fix | no |
| `BOE-B-2024-45427` | `RESOLVED NON-RELEVANT` after bounded deterministic validation fix | no |
| `BOE-B-2025-26539` | `RESOLVED NON-RELEVANT` after bounded deterministic validation fix | no |
| `BOE-B-2025-41490` | `SAFE EXPLICIT RETRY` | yes |
| `BOE-B-2025-45035` | `SAFE EXPLICIT RETRY` | yes |

## 11. Main-04 gate

```text
MAIN-04 BLOCKED BY SYSTEMIC CODE BUG
```

Before `main-04`, the REQUIRED residual work is to implement and test the three
bounded validation corrections, obtain the human target disposition for
`BOE-B-2024-3861`, recanonicalize all eligible persisted structured outputs
homogeneously and validate the cumulative snapshot. Only after that work is
reviewed may the two isolated operational retries be separately authorized.
`main-04` and the holdout remain unauthorized.

No Gemini, BOE, other-model or web call was made during this review. No run,
attempt, code, test, configuration or manual-review artifact was modified.
