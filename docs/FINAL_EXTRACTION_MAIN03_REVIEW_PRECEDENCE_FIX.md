# Final P2 main-03 review precedence fix

This report closes the last semantic blocker in `main-03`: deterministic
canonicalization no longer overwrites valid component relations explicitly
approved in a structured manual review.

No BOE, Gemini, other-model, retry, `main-04` or holdout execution was
performed. Historical attempts and existing snapshots were not modified.

## 1. Root cause and invariant

The versioned `BOE-B-2024-3861` review was valid before canonicalization. It
contained two deliberately distinct infrastructure scopes in its first two
events and component targets for their three actions. The generic automatic
path then:

1. merged both non-storage components through
   `_merge_auxiliary_components()`;
2. remapped their targets and replaced them with `event` through
   `_infer_action_targets()`.

The selected output consequently changed from two components with targets
`component_1` and `component_2` to one component with targets `event`.

The implemented invariant is:

```text
valid explicit manual semantics > deterministic inference
```

It is applied only while validating a `manually_validated` payload. Valid
explicit targets, component boundaries and component-to-generation links are
preserved. Missing action targets continue to use the existing deterministic
inference. Automatic extractions continue to merge auxiliary components under
the existing heuristic. No BOE identifier is special-cased.

The review path remains fail-closed. It rejects an unknown explicit target, a
generation target that cannot survive documentary canonicalization, a reviewed
component that cannot be validated against the document and a component
without generation lineage. It does not bypass Pydantic, documentary or domain
validation and does not mutate the original payload.

## 2. Regression guarantees

Seven focused tests were added before the production change. They cover:

- preservation of an explicit reviewed component target;
- continued inference of a missing automatic target;
- preservation of reviewed component separation;
- continued merging of equivalent automatic auxiliary components;
- rejection of an invalid reviewed target;
- rejection of a reviewed component without generation lineage;
- idempotence of reviewed canonicalization.

The tests were red before the fix: four failed and three passed. After the fix,
all seven pass. The canonicalization, extraction validation, review,
review-I/O, recanonicalization and pipeline suites pass together: 440 tests.
The complete offline repository suite passes: 1,151 tests.

## 3. BOE-B-2024-3861 offline replay

The replay uses only the local source snapshot, persisted structured output,
the versioned review and current deterministic code. The result preserves:

- ten independent generation plants and ten publication events;
- the 30 kV component only in the two events supported by the source;
- the common SET/LAT 220 kV component in all ten events;
- component targets for every shared-infrastructure action;
- no grid infrastructure as a generation root;
- three distinct action types per event, with no duplicate action inside an
  event.

The repetition across ten independent events is the required event-level
representation; the fix introduces no artificial duplicate inside an event.
The review is selected as `manually_validated`, its source attempt remains
`167a4329f74740588a8ad3f6ea0b1350`, and the semantic blocker count is zero.

The other `main-03` deterministic cases remain resolved:

| BOE | Result | Events |
| --- | --- | ---: |
| `BOE-B-2024-45427` | `not_relevant_for_generation_projects` | 0 |
| `BOE-B-2025-26539` | `not_relevant_for_generation_projects` | 0 |

The cumulative loaders also preserve the prior gates: `main-01` accounts for
250 documents with 249 current, one rejected and zero blockers; `main-02`
accounts for 500 with 499 current, one rejected and zero blockers.

## 4. Identity gate

This is a compatible review/canonicalization precedence bugfix, not a contract,
scope or extraction-configuration change.

| Identity | Before | After |
| --- | --- | --- |
| Scope policy | `binary_named_generation_pre_model_guard_v4` | unchanged |
| Extraction config ID | `4b54b89dbfe8640e` | unchanged |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` | unchanged |
| Recanonicalization materialization version | `2` | unchanged |
| Deterministic code SHA-256 | `35b17723b8fe70e487b85faf28742417ec9ec49ce6d442b7a106f3bd619eed60` | `b40b22304745f54a42c35ff4145278ee7aa6df6909de422e6d829d95e8a342ef` |

The deterministic code identity changes as required for provenance; the model,
instructions, source, configuration and contract identities do not.

## 5. Cumulative offline materialization

The dry-run and publication both used the original `extraction-main-03`
snapshot. The semantically defective `extraction-main-03-recanonicalized`
snapshot remains preserved and was not used as input or overwritten.

The accepted candidate was published atomically at:

```text
runs/final-tfm-p2-20240101-20260820-v1/
extraction-main-03-recanonicalized-v2
```

| Replay measure | Count |
| --- | ---: |
| Source attempt rows | 1,501 |
| Precanonical roots evaluated | 748 |
| Outputs replayed successfully | 747 |
| Unchanged outputs | 723 |
| Changed outputs | 24 |
| Unexpected automatic-output changes versus the prior replay | 0 |
| Replay failures resolved by review | 1 |
| Semantic failures recovered | 15 |
| Human rejections | 1 |
| Manually validated selections | 2 |
| Operational errors preserved | 2 |
| New derived attempts | 747 |
| Model calls | 0 |

The contractual loader validates the candidate:

| Snapshot measure | Count |
| --- | ---: |
| Documents accounted | 750 |
| Current extractions | 747 |
| Rejected | 1 |
| Blocking reviews | 2 |
| Semantic blockers | 0 |
| Operational blockers | 2 |
| Attempt rows | 2,248 |
| Unique attempt IDs | 2,248 |
| Duplicate attempt IDs | 0 |

The remaining operational BOEs are:

```text
BOE-B-2025-41490
BOE-B-2025-45035
```

A second cumulative dry-run from v2 reused all 747 derived attempts, created
zero new derivations, produced zero semantic changes and retained zero
duplicate attempt IDs. A separate retry dry-run selected exactly those two
operational errors: two model documents would be required, while zero previous
successes, semantic cases or the reviewed `BOE-B-2024-3861` were selected. No
retry was executed.

## 6. Gate disposition

```text
main-01: CLOSED
main-02: CLOSED
main-03 semantic closure: CLOSED
main-03 operational retries: 2 PENDING — NOT AUTHORIZED
main-04: NOT AUTHORIZED
holdout: NOT EXECUTED
```

Final recommendation:

```text
MAIN-03 SEMANTICALLY CLOSED — READY FOR 2 OPERATIONAL RETRIES
```
