# Final P2 main-03 human disposition

This report records the approved human disposition for `BOE-B-2024-3861`
and the offline materialization check performed before authorizing the two
remaining operational retries.

No BOE, Gemini, other-model, `main-04` or holdout execution was performed.
No retry was executed. Historical attempts and source snapshots were not
modified.

## 1. Identity and review lineage

The review is versioned at:

```text
config/manual_reviews/boe_ai/BOE-B-2024-3861.json
```

It records `review_status=manually_validated`, reviewer
`human_tfm_review`, a real UTC review timestamp and this validated lineage:

| Field | Value |
| --- | --- |
| Source attempt | `167a4329f74740588a8ad3f6ea0b1350` |
| Source document SHA-256 | `c1bdc293cb128f443213f8b9fdf52a2342bc9aad4a9a20805383c5eec2a81da8` |
| Extraction config | `4b54b89dbfe8640e` |
| Document validation version | `25` |

The local BOE source confirms ten independently processed generation plants,
a 30 kV line shared only by `HSF La Romera` and `HSF Los Mangos`, and
`SET Torreluenga 30/220 kV` plus its 220 kV line shared by all ten plants.
The review payload therefore preserves ten generation events, represents the
all-ten scope as `component_1`, adds the two-plant 30 kV scope as
`component_2` in the first two events, and uses only component targets. It
contains one instance of each of the three action types inside each required
independent event, with no duplicate action inside an event and no generation
asset target.

The review JSON, Pydantic extraction model, lineage and documentary evidence
validate. Applying the review removes `BOE-B-2024-3861` from the review queue
before recanonicalization.

## 2. Deterministic replay

The cumulative dry-run used the 750-document `main-01` + `main-02` +
`main-03` scope, the current deterministic code, the source snapshot and only
the new review in addition to the decisions inherited from the snapshot.

| Replay measure | Count |
| --- | ---: |
| Source attempt rows | 1,501 |
| Replayable root outputs | 748 |
| Semantically unchanged outputs | 723 |
| Changed outputs | 24 |
| Replay failures resolved by review | 1 |
| Semantic failures recovered | 15 |
| Human rejections | 1 |
| Manually validated selections | 2 |
| Operational errors preserved | 2 |
| New derived attempts required | 747 |
| Projected attempt rows / unique IDs | 2,248 / 2,248 |
| Duplicate attempt IDs | 0 |
| Model calls | 0 |

`BOE-B-2024-45427` and `BOE-B-2025-26539` replay as classified,
`not_relevant_for_generation_projects`, with zero publication events. They do
not require human reviews.

## 3. Published offline snapshot and blocker

The dry-run had no unresolved semantic queue item, so the pipeline published
the new atomic output at:

```text
runs/final-tfm-p2-20240101-20260820-v1/
extraction-main-03-recanonicalized
```

The contractual loader accepts the snapshot and verifies 750 documents, 747
current extractions, one rejection, two blocking operational reviews and
2,248 unique attempt IDs with no duplicates. The operational BOEs remain:

```text
BOE-B-2025-41490
BOE-B-2025-45035
```

The independent semantic inspection after loading nevertheless found a
blocking mismatch. The manual JSON has two components and component-only
targets in each of the first two events, but the selected extraction has one
merged component and `target=event` for their three actions.

This is caused by two current canonicalization rules:

1. `_merge_auxiliary_components()` merges every non-storage component inside
   an event into one `sistema_evacuacion`, regardless of distinct sharing
   scope;
2. `_infer_action_targets()` replaces the entity list with `event` when the
   title mentions every entity remaining after that merge.

Consequently, the loader proves structural reproducibility but does not
preserve the approved human component scopes. The published directory must
not be treated as the accepted `main-03` candidate.

## 4. Gate disposition

```text
main-01: CLOSED
main-02: CLOSED
main-03 human decision: RECORDED
main-03 semantic closure: BLOCKED — REVIEW PAYLOAD NOT PRESERVED
main-03 operational retries: 2 PENDING — NOT AUTHORIZED
main-04: NOT AUTHORIZED
holdout: NOT EXECUTED
```

The retry dry-run was not repeated after this blocker because the validated
candidate prerequisite failed. The previously established operational pair
remains unchanged, but neither call is authorized by this block.

Final recommendation:

```text
MAIN-03 DISPOSITION REQUIRES CORRECTION
```
