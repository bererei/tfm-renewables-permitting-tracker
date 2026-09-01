# Final Holdout Evaluation Contract V1

## 1. Status and identities

This document freezes `final_holdout_evaluation_contract_v1` before any
holdout membership, source document, label or prediction is inspected.

| Role | Frozen identity |
| --- | --- |
| System under evaluation | `tfm-final` at `282de815bea4e248bdcba2c655e3ee078cb58a49` |
| Extraction configuration | `4b54b89dbfe8640e` |
| Provider/model | `gemini` / `google:gemini-2.5-flash` |
| Evaluation tooling | `tfm-evaluation` at the later approved tooling commit |
| Evaluation contract | `final_holdout_evaluation_contract_v1` |

Evaluation code is isolated under `evaluation/final_holdout_v1/`. It does not
import or execute the pipeline, construct a model agent, apply corrections or
write into a prediction snapshot. The production prompt, extraction models,
canonicalization, historical-antecedent detector, Silver, Gold and Streamlit
remain unchanged.

## 2. Primary evaluation boundary

The primary result evaluates the frozen canonical extraction output produced
before holdout-specific human intervention. It covers:

- document scope;
- publication events/project mentions;
- generation assets and generation type;
- associated components as a secondary entity diagnostic;
- technical mentions as a secondary diagnostic, with exact MW comparison only
  when one unambiguous W/kW/MW/GW literal is annotated;
- administrative actions, action type, decision, modification flag, targets,
  evidence and temporal attribution;
- participants and roles;
- raw administrative location mentions and levels;
- P0 historical-antecedent warnings;
- review routing as a separate operational diagnostic.

The holdout does **not** independently evaluate INE resolution, project
grouping, Silver, Gold or Streamlit. A later downstream execution can only be
reported as a smoke/reproducibility diagnostic and cannot change the primary
score.

No global accuracy is defined.

## 3. Truth tables and explicit missingness

The header-only templates are versioned in
`evaluation/final_holdout_v1/templates/`. The normalized tables are:

| Table | Grain |
| --- | --- |
| `documents.csv` | One row per holdout BOE |
| `events.csv` | One human-defined publication event/project mention |
| `generation_assets.csv` | One named generation asset within an event |
| `associated_components.csv` | One associated storage/grid component |
| `technical_mentions.csv` | One technical mention owned by an asset/component |
| `administrative_actions.csv` | One administrative action within an event |
| `action_targets.csv` | One truth action-to-entity target |
| `participants.csv` | One participant mention within an event |
| `locations.csv` | One raw administrative location mention |
| `evidence_passages.csv` | One permitted continuous source passage for an entity |

Annotation workload classification:

- **Primary and necessary:** documents, events, generation assets,
  administrative actions, action targets, participants, locations and
  action-owned evidence passages.
- **Useful secondary:** associated components, technical mentions and
  non-action evidence passages. They preserve observable extraction detail but
  do not broaden the primary score.
- **Derivable and therefore not entered:** repeated contract/source/reviewer
  columns in child tables, evidence IDs/evidence-key arrays, target-row IDs and
  location hints that are not scored by V1, plus normalized MW values derived
  from annotated raw technical text.

`documents.csv` owns contract/holdout version, BOE ID, source hash and
reviewer/date provenance. Child rows retain `identificador_boe`, their simple
annotation-local keys, applicability, adjudication and optional notes; source
and reviewer provenance are inherited through the validated document foreign
key rather than copied manually into every row. Keys such as `event_1`,
`asset_1` or `action_1` are chosen by the annotator and are not production IDs,
hashes or matching outputs.

Evidence ownership is declared once in `evidence_passages.csv` by
`owner_type` + `owner_key`; entity rows do not repeat evidence-key arrays.
Action targets likewise use the semantic composite
`action_key` + `target_type` + `target_truth_key`, so the annotator does not
invent target-row IDs. This keeps the ten-table relational contract while
removing derivable bookkeeping.

Closed applicability domain:

- `applicable`
- `not_applicable`
- `unknown`

Closed adjudication domain:

- `scored_truth`
- `ambiguous_not_safely_determinable`
- `excluded_from_scoring`

The literal marker `__NA__` represents an explicitly non-applicable field.
Blank cells are invalid. `scored_truth` is valid only with
`applicability=applicable`. JSON list columns must contain explicit JSON arrays.

`documents.annotation_status` is `draft` or `complete`. The artifact cannot be
frozen while any document is draft. A complete project-specific document needs
at least one scored event; every scored event needs at least one scored
generation asset and one scored administrative action. A complete non-relevant
document cannot have scored events.

## 4. Blind annotation protocol

The seal is broken only after explicit human authorization. The annotator may
see:

- the BOE source document;
- its BOE identity and source hash;
- the empty annotation tables and this contract.

The annotator must not see:

- `attempts.parquet` or any extraction JSON;
- `current_extractions.parquet`;
- `review_queue.parquet` or P0 findings;
- model logs, errors, aggregate counts or evaluation results;
- any system-derived entity list.

Annotate each document in this order:

1. Decide whether the document is `generation_project_specific` or
   `not_relevant_for_generation_projects`. If the source is genuinely
   indeterminate, record explicit ambiguity; do not force a class.
2. For a project-specific document, create one event per independently
   distinguishable generation project/action unit under the frozen domain
   rules. A shared-component event is allowed only when the BOE publishes one
   action on a component shared by every recorded generation root.
3. Record every named generation asset and all literal name variants used by
   the BOE. Record generation type only when stated or contractually safe.
4. Record associated components only when the source establishes their
   relationship with a generation asset. Standalone grid infrastructure is not
   a generation project.
5. Record technical mentions as raw source values; do not calculate a second
   normalized value. V1 derives MW only from one unambiguous power value with
   one standalone W/kW/MW/GW unit. Ranges, combined figures, missing units, or
   qualified units such as MWac, MWdc and MWp remain qualitative only.
6. Record each administrative action exactly once, including type, decision,
   modification flag and explicit targets. Independently classify temporal
   status as `current`, `historical_antecedent`, or explicit ambiguity.
7. Record participants and roles only when the BOE states the relationship.
8. Record raw municipality/province/community mentions only. Do not resolve
   them against INE and do not infer a missing level.
9. Add one evidence row per continuous literal passage that validly supports
   an entity, using its existing owner key. Multiple valid alternatives are
   separate rows. Never join discontinuous text as one passage and do not
   create separate evidence IDs.
10. Mark the document complete only after confirming that every table is
    exhaustive for that document. Preserve reviewer and adjudication notes.

Facts not stated by the BOE are omitted or explicitly not applicable. Genuine
ambiguity is evidence about the source, not an annotation failure.

## 5. Frozen normalization and matching

All matching is deterministic, order-independent and hierarchical. Generated
production IDs and physical row order are never matching keys.

### 5.1 Text normalization

Name identity uses Unicode NFKD, case-folding, removal of combining marks,
replacement of punctuation/non-alphanumeric characters by spaces, and
whitespace collapse. It performs no fuzzy edit-distance comparison.

Evidence uses Unicode NFKC, case-folding and whitespace collapse while
retaining punctuation. A prediction fragment is acceptable only when its full
normalized text is contained in an entity-specific accepted truth passage.
Production composite evidence is split at the literal `[...]` delimiter.

### 5.2 Entity matching

- **Generation assets:** at least one exact normalized alias in common within
  the same document. Generation type is not used as the key because it is a
  scored field.
- **Events:** the non-empty set of already matched generation assets must be
  exactly equal. This prevents event matching by row order or summary prose.
- **Components:** exact normalized name, or exact normalized description for
  an unnamed component, within a matched event.
- **Actions:** within a matched event, at least one predicted evidence fragment
  must be contained in an accepted action-specific truth passage. Action type,
  decision and targets are not used as matching keys.
- **Participants:** exact normalized participant name within a matched event;
  role is scored afterward.
- **Locations:** exact normalized raw location name within a matched event;
  level is scored afterward.
- **Technical mentions:** matched owner, matched event and entity-specific
  evidence anchor. Attribute/value are scored afterward.

Forced one-to-one matches are removed iteratively. The evaluator never chooses
between equally valid remaining candidates. A system-created many-to-many
ambiguity is reported and penalized as unresolved expected/predicted entities.
Predictions tied only to truth explicitly marked ambiguous/excluded are omitted
from denominators and reported separately.

## 6. Evidence evaluation

Production documentary validation answers whether evidence is literal and
structurally admissible. V1 semantic evidence evaluation asks whether every
predicted evidence fragment lies inside a passage that the blind annotator
assigned to that exact truth entity.

Evidence is not correct merely because the text occurs elsewhere in the BOE.
The blind annotator must verify every scored truth passage as literal source
text. V1 validates evidence ownership and completeness but does not copy the
source into the truth artifact or repeat that literal-containment check.
Multiple valid passages are alternatives in `evidence_passages.csv`; a
composite prediction must have every fragment supported by an accepted
passage.

## 7. Frozen metrics

All entity metrics are corpus-level micro metrics. Field accuracy is micro over
scored, deterministically matched entities. Field coverage is the number of
applicable matched fields for which the prediction contains a value divided by
all applicable matched fields. A missing prediction is uncovered and
incorrect; truth marked `__NA__` is excluded. Macro averages are not produced.

For each primary entity class:

- `precision = TP / (TP + FP)`
- `recall = TP / (TP + FN)`
- `F1 = 2PR / (P + R)`

Precision is JSON `null` when `TP+FP=0`; recall is `null` when `TP+FN=0`; F1
is `null` if either input is undefined and `0.0` when both are defined and
zero. Explicit ambiguous/excluded truth is absent from denominators and counted
separately. System-created matching ambiguity contributes unresolved FN/FP.
If document scope itself is ambiguous or excluded, every predicted entity in
that document is reported as excluded and cannot become a false positive.

Primary metrics:

- document-scope exact-match accuracy;
- event detection precision/recall/F1;
- generation-asset detection precision/recall/F1;
- generation-type accuracy on matched assets;
- administrative-action detection precision/recall/F1;
- action-type, decision, modification, target-set and semantic-evidence
  accuracy on matched actions;
- participant detection precision/recall/F1 and role accuracy;
- raw-location detection precision/recall/F1 and level accuracy.

Associated components and technical mentions are secondary diagnostics. MW
correctness is exact after deterministic decimal conversion to MW; there is no
data-dependent tolerance. A value that is absent, ambiguous, a range or cannot
be parsed as exactly one unit-bearing value is not scored numerically.

### Strict document exact match

`document_extraction_exact_match` is retained as a secondary, deliberately
strict metric. A document passes only when document scope, every primary entity
set and every primary matched field above are correct. It is not scored for a
document with explicitly ambiguous/excluded primary truth. Entity order and
optional diagnostic component/technical fields do not affect it. It must not
be presented as the single system accuracy.
A matching ambiguity created by the system is an error and therefore makes the
strict document result false; it does not remove that document from the exact-
match denominator.

## 8. P0 safeguard

P0 is evaluated only for matched extracted actions with determinate temporal
truth:

| Truth/output | Count |
| --- | --- |
| Historical antecedent + warning | TP |
| Current + warning | FP |
| Historical antecedent + no warning | FN |
| Current + no warning | TN |

Ambiguous temporal truth is excluded and reported. A completely missing
historical action is an extraction FN, not a P0 FN. A warning on an unmatched
predicted action is unadjudicated. Primary P0 results use the detector output
before any later `CURRENT` or `ANTECEDENT` human decision.

P0 precision, recall and F1 use action-level micro counts and the same
zero-denominator rules. Warning rate is reported separately over predicted
actions.

## 9. Review routing

Review routing is not extraction accuracy. The evaluator reports:

- fraction of documents sent to blocking review;
- reason-code distribution;
- fraction of definitely incorrect scored extractions routed to review;
- fraction of strictly correct scored extractions unnecessarily routed;
- ambiguous/excluded documents routed to review.

Sending all documents to review cannot improve extraction precision/recall and
would produce a 100% review rate plus unnecessary-review penalties.

## 10. Truth lifecycle and seal protection

Header-only templates can be validated without touching the holdout:

```bash
uv run python -m evaluation.final_holdout_v1.cli validate-truth \
  --truth evaluation/final_holdout_v1/templates
```

The future initialization command refuses before reading either input unless
the operator supplies `--break-seal`:

```bash
uv run python -m evaluation.final_holdout_v1.cli init-truth \
  --holdout config/evaluation/final_holdout_p2_v1.csv \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --output <NEW_BLIND_ANNOTATION_DIR> \
  --holdout-version final_holdout_p2_v1 \
  --reviewer-id <REVIEWER_ID> \
  --break-seal
```

It prints an audit warning, initializes only document identity/hash rows, and
never accepts a prediction path. It neither executes extraction nor calls a
model.

After blind annotation:

```bash
uv run python -m evaluation.final_holdout_v1.cli validate-truth \
  --truth <BLIND_ANNOTATION_DIR> --require-complete

uv run python -m evaluation.final_holdout_v1.cli freeze-truth \
  --truth <BLIND_ANNOTATION_DIR> \
  --output <NEW_IMMUTABLE_TRUTH_DIR>
```

Truth identity hashes canonical rows sorted by stable keys, so physical row
order does not change `truth_artifact_id`. The frozen manifest also records
exact file hashes, semantic table hashes, source/holdout identities and
reviewer provenance. Existing outputs are never overwritten.

## 11. One-shot execution record

`evaluation/final_holdout_v1/execution_record.template.json` is an unpopulated
template; `execution_record.schema.json` is its closed machine-readable schema.
The completed record must contain run ID, UTC times, exact argv,
exit code, frozen commit/config, provider/model, source and holdout identities,
extraction snapshot identity, stdout/stderr references, Python version,
`uv.lock` SHA-256, usage totals and incident/retry notes.

The evaluator requires `manual_intervention_before_primary_freeze=false` and
verifies the record against the snapshot and truth identities.

## 12. Primary-prediction safeguards

The evaluator fails closed unless:

- the extraction manifest has the frozen config/model/prompt/contract identity;
- the extraction manifest declares P0 policy V1 and binds the copied correction
  and CURRENT-review registries by hash;
- prediction documents exactly equal the frozen truth document universe and
  source hashes;
- exactly one fresh model-origin or frozen-policy deterministic attempt exists
  per document;
- attempts have no inherited source attempt;
- `current_extractions` exactly selects every successful primary attempt and
  has no changed payload;
- no holdout-specific generic manual review exists;
- no copied historical correction or `CURRENT` review targets a holdout BOE;
- the execution record identifies the exact snapshot;
- prediction file hashes remain unchanged before and after evaluation.

Explicit operational retries or later human-assisted snapshots require a
separate report and cannot be passed off as the primary result.
Automatic transient retries inside the frozen provider-call policy remain one
persisted attempt and are recorded in the execution incident notes. A fresh
deterministic attempt produced by the frozen pre-model policy is also primary;
it is not a reused model output. A manual rerun creates additional persisted
attempt history and is therefore rejected as primary.

## 13. Evaluation command and outputs

```bash
uv run python -m evaluation.final_holdout_v1.cli evaluate \
  --truth <IMMUTABLE_TRUTH_DIR> \
  --predictions <IMMUTABLE_PRIMARY_EXTRACTION_DIR> \
  --execution-record <EXECUTION_RECORD_JSON> \
  --output <NEW_IMMUTABLE_EVALUATION_DIR>
```

The output is staged and atomically published only to a new path:

- `manifest.json`
- `metrics.json`
- `summary.md`
- `document_results.parquet`
- `entity_matches.parquet`
- `unmatched_expected.parquet`
- `unmatched_predicted.parquet`
- `field_results.parquet`
- `p0_results.parquet`
- `review_routing_results.parquet`
- `validation_issues.parquet`

The manifest binds the evaluation contract, truth ID/file hashes, prediction
snapshot/artifact hashes, frozen production commit/config, execution-record
hash and semantic output hashes. No input is modified.

Recommended immutable paths are:

```text
runs/final-holdout-p2-v1-primary-<UTC>/extraction/
runs/final-holdout-p2-v1-truth-<VERSION>/
runs/final-holdout-p2-v1-evaluation-<UTC>/
```

## 14. Interpretation and limitations

- The fixed holdout remains modest; confidence intervals are not claimed by
  V1 and no threshold is tuned from its observations.
- Blind human truth can still contain judgment error. Reviewer identity,
  ambiguity and adjudication notes remain visible, but V1 does not implement a
  multi-reviewer consensus study.
- Exact name/evidence matching favors auditability over fuzzy recall. All
  unresolved many-to-many cases remain explicit.
- Entity-field accuracy is conditional on a deterministic entity match and
  must be read together with entity precision/recall.
- P0 is evaluated only on actions the extraction produced; completely missing
  actions remain extraction errors.
- Downstream product correctness requires its existing independent contracts
  and is outside this holdout score.
- The primary result is one-shot: it must not be used to retune the system and
  then rescore the same holdout. Any later human-assisted or post-change result
  is secondary and must remain clearly separated from the frozen primary run.
