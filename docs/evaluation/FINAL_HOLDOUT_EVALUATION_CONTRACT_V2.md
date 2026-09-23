# Final holdout evaluation contract V2 — annotation, publication and V2-B scoring

Status: **V2 truth frozen; V2-B implemented, pending human review and evaluator
freeze**. V2-B development uses synthetic predictions only. No final system
predictions or metrics have been inspected or produced in this block.

The sole final evaluation truth is `runs/final_holdout_p2_v1_truth_v2_frozen`
(48 documents), with `truth_artifact_id`
`e3f300253db94931345e9bbbc489cd810802f94339c3b6a0d751f98b32383b54`
and manifest SHA-256
`4f32dc8f89fff8ae1b80f7fb5f94e9168d131f4dea3d0d025640e869c07c148c`.

Contract identifier: `final_holdout_evaluation_contract_v2`.

Frozen system under evaluation, identified by a private historical ref that is
not resolvable from the public repository:
`tfm-final@282de815bea4e248bdcba2c655e3ee078cb58a49`.

## 1. Methodological rationale

> Primary evaluation scope reduced before model execution to align annotation
> effort and reported metrics with the TFM objectives and final product.

The reduction was defined while Gemini/system-under-evaluation predictions had
never been executed or inspected. It is not based on expected or observed
model performance. The holdout membership and source-document identities do
not change.

V1 remains immutable and historically preserved in
`evaluation/final_holdout_v1/` and
`docs/evaluation/FINAL_HOLDOUT_EVALUATION_CONTRACT_V1.md`. V2 uses a separate
truth artifact and never overwrites a V1 workspace.

## 2. Phase boundary

Phase V2-A contains only:

- the reduced truth schema and validation;
- canonical terminology and QA paths;
- blind human-annotation helpers and Streamlit UI;
- deterministic AI-QA package export from completed human truth;
- non-destructive V1-to-V2 migration.

Phase V2-A does **not** contain:

- V2 entity matching;
- V2 metrics or evaluator;
- prediction loading;
- P0-result loading;
- extraction or model execution.

Those capabilities belong to Phase V2-B and must be reviewed and frozen before
the system under evaluation is executed.

V2-B now implements those evaluation capabilities, except extraction/model
execution, which remains outside the evaluator. The machine-readable scoring
declaration is `evaluation/final_holdout_v2/scoring_rules.json`.
`contract.json` remains byte-identical to the annotation declaration bound by
the frozen truth manifest. Its historical `evaluator_status` describes V2-A;
it is superseded for tooling status by this section and the V2-B declaration.
Changing that annotation declaration would invalidate the existing truth freeze.

The separately authorized P0 truth-publication block adds `freeze-truth` and
`validate-frozen-truth` before V2-B. It preserves the annotation schema, V1 and
the production system, and implements no matching or scoring.

## 3. Truth tables

V2 keeps the ten normalized V1 tables to preserve compatible human work:

| Table | V2 role |
| --- | --- |
| `documents.csv` | PRIMARY |
| `events.csv` | PRIMARY |
| `generation_assets.csv` | PRIMARY |
| `associated_components.csv` | SECONDARY / DIAGNOSTIC |
| `technical_mentions.csv` | SECONDARY / DIAGNOSTIC |
| `administrative_actions.csv` | PRIMARY |
| `action_targets.csv` | SECONDARY / DIAGNOSTIC |
| `participants.csv` | SECONDARY / DIAGNOSTIC |
| `locations.csv` | PRIMARY |
| `evidence_passages.csv` | PRIMARY only for administrative-action evidence; otherwise SECONDARY |

`administrative_actions.csv` adds the V2-primary field:

`expected_affected_generation_asset_keys_json`

It is the exhaustive set of human truth `asset_key` values affected by that
action. Every key must identify a scored generation asset in the same document
and event. In the UI the value is always selected through a multiselect; the
annotator never writes JSON.

An empty array is explicit unresolved work and is allowed only while the
document is draft or the action is not scored. It blocks completion for a
scored action. A genuinely unsafe action-level adjudication uses the frozen
applicability/adjudication semantics rather than an invented asset.

## 4. Primary annotation scope

### Document

For every holdout BOE annotate:

- `expected_document_scope`;
- `scope_applicability`;
- `scope_adjudication`.

### Event

Record every independently distinguishable publication-event/project unit.
Generation plants remain the roots. A shared-component event remains valid
only under the established domain rule for one action on a component shared by
all recorded generation roots.

### Generation asset

For each event record:

- every relevant named generation asset;
- every materially useful literal alias;
- the generation type when stated or contractually safe.

### Administrative action

Record every relevant/current administrative action exactly once, including:

- `expected_action_type`;
- `expected_decision`;
- `expected_is_modification`;
- `temporal_status`;
- `expected_affected_generation_asset_keys_json`.

The affected-asset set is always explicit. A single-asset event is not
automatically assumed correct.

`temporal_status` preserves the existing annotation values:

- `current`;
- `historical_antecedent`;
- `ambiguous_not_safely_determinable`;
- `not_applicable` where the entity itself is not scored.

P0 truth will be derived from this field in V2-B. No P0 output is read during
annotation.

### Approved temporal evaluation decision — 2026-09-13

The positive expected universe for primary action extraction is **`current`**.
An extracted current truth action is an extraction TP when correctly matched;
an omitted current truth action is an extraction FN. A prediction corresponding
to `historical_antecedent` is an extraction FP due to historical contamination.
A historical antecedent correctly omitted by the extractor is **not** an
extraction FN. This explicitly supersedes the V1 historical-inclusive extraction
denominator for V2; V1 code and its historical results remain unchanged.

Historical rows remain in human truth for temporal-contamination identification,
P0 adjudication and diagnostic analysis. Their existing `scored_truth` annotation
does not make them positive expected current-action extractions. No annotation
is changed or required to be repeated by this decision.

`temporal_status` is a **truth adjudication variable**, not a categorical model
output. Production `AdministrativeAction` has no equivalent output field, so
V2 defines **no categorical temporal-status accuracy**. Section 11 defines the
implemented matching, ambiguity handling and scoring rules.

P0 is an alarm applied to an already extracted action. For a safely adjudicable
extracted action, before any later human CURRENT/ANTECEDENT intervention:

| Temporal truth | Warning | P0 outcome |
| --- | --- | --- |
| `historical_antecedent` | Yes | TP |
| `historical_antecedent` | No | FN |
| `current` | Yes | FP |
| `current` | No | TN |

An omitted historical action is never a P0 FN: the detector received no such
action. A historical prediction is an extraction FP even when its P0 warning is
a detector TP; the two evaluations measure different behavior. Warnings that
cannot be safely linked to adjudicable truth are reported as `unadjudicated`,
never forced into TP/FP/FN/TN. Ambiguous temporal truth is reported separately.
The P0 false warning rate is `FP / (FP + TN)` over extracted/matched,
adjudicable **current** actions. It is distinct from the rate of all warnings
over all extracted actions. The subsequent V2-B implementation and explicit
zero-denominator convention are defined in section 11.

### Location

Record every raw municipality, province or autonomous-community mention that
administratively locates the project/event. Do not include places appearing
only as environmental or contextual geography. Do not perform manual INE
resolution.

### Administrative-action evidence

Every scored action needs at least one strong, continuous and literal source
passage. Include distinct materially different valid action contexts where
needed. Repeated alternatives that add no semantic context are not required.

No non-action owner requires evidence for V2 completion.

## 5. Secondary, non-blocking annotation

The following data may be retained or added for diagnosis, but absence never
blocks completion:

- associated components;
- exact V1 action-target representation;
- technical mentions;
- participants, including explicit promoter;
- component, asset, participant, location and other non-action evidence.

Optional principal-power diagnostic:

1. At most one comparable principal generation power per asset/event.
2. Prefer one explicit total `potencia_instalada`.
3. Otherwise use one explicit total `potencia_pico`.
4. Accept one standalone W/kW/MW/GW value only.
5. Combined values, ranges and qualified MWp/MWn/MWac/MWdc values are not
   comparable.
6. Component/storage power, voltage, length, count and unit power are not part
   of the diagnostic.

This is secondary only; V2-A implements no numeric metric.

## 6. Completion

A complete `generation_project_specific` document requires:

- applicable, scored document scope;
- at least one scored event;
- at least one scored generation asset and one scored administrative action in
  every scored event;
- action type, decision, modification flag and current/historical/explicitly
  ambiguous temporal status for every scored action;
- a non-empty explicit affected-generation-asset set for every scored action;
- at least one scored action-specific evidence passage for every scored action;
- human confirmation that project-administrative locations are exhaustive
  where present in the source.

A complete `not_relevant_for_generation_projects` document must have scored
scope and no scored primary entity or administrative-action evidence.

Components, exact targets, technical mentions, participants and non-action
evidence are never completion requirements. Present optional rows must still
satisfy schema, domain and foreign-key validation.

## 7. Canonical terminology and paths

The versioned registry in
`evaluation/final_holdout_v2/contract.json` is the single runtime source used
by both the annotation UI and QA exporter.

| Human concept | Canonical entity |
| --- | --- |
| Documento | `document` |
| Evento / proyecto publicado | `event` |
| Activo de generación | `generation_asset` |
| Componente asociado | `associated_component` |
| Mención técnica | `technical_mention` |
| Actuación administrativa | `administrative_action` |
| Objetivo de la actuación | `action_target` |
| Participante | `participant` |
| Localización | `location` |
| Evidencia | `evidence_passage` |

Path grammar:

```text
document.<field>
<entity>/<local_key>.<field>
evidence_passage/<owner_entity>/<owner_key>
```

Examples:

```text
document.expected_document_scope
generation_asset/asset_1.names_json
generation_asset/asset_1.expected_generation_type
administrative_action/action_1.expected_action_type
administrative_action/action_1.expected_decision
administrative_action/action_1.expected_is_modification
administrative_action/action_1.temporal_status
administrative_action/action_1.expected_affected_generation_asset_keys_json
location/location_2.expected_location_level
evidence_passage/administrative_action/action_1
```

The UI shows a Spanish label and this exact path. The QA package uses the same
path in `Entidad/campo`.

## 8. Blind annotation UI and QA export

Launch from the repository root after a V2 workspace has been authorized and
created:

```bash
UV_OFFLINE=1 uv run streamlit run \
  evaluation/final_holdout_v2/annotation_app.py
```

The UI reads only the V2 human truth workspace and canonical source snapshot.
It has no prediction, attempts, current-extraction, review-queue, P0 or model
input. Primary sections are prominent; all secondary editors live under
**Opcional / diagnóstico**.

**Descargar paquete para revisión IA** is enabled only for a complete V2
document. Its deterministic Markdown contains:

- local BOE source text;
- primary V2 human truth first;
- a clearly separated **Datos secundarios / diagnósticos — no bloqueantes**
  appendix;
- fixed QA instructions limited to primary requirements;
- canonical `Entidad/campo` paths.

It contains no system-under-evaluation output.

## 9. Non-destructive V1 migration

The migration command is:

```bash
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m evaluation.final_holdout_v2.cli migrate-v1-truth \
  --source <V1_TRUTH_WORKSPACE> \
  --output <NEW_V2_TRUTH_WORKSPACE>
```

It refuses an existing destination and a destination inside the V1 workspace.
It preserves document/source identity, holdout membership and compatible human
rows, while recording V1 truth artifact ID and migration version in V2
metadata. It never reads predictions.

Affected assets are derived only from human V1 target semantics:

- generation-asset target → that scored asset;
- event target → every scored generation asset in that event;
- associated-component target → the component's scored related assets.

An absent, ambiguous, unscored or empty supporting relation produces `[]` and
an unresolved migration entry. It is not guessed.

Every migrated project-specific document becomes `draft` and requires explicit
V2 revalidation, even if complete in V1. A complete, scored non-relevant
document may remain complete when it contains no scored V2-primary entities.
This is a generic rule with no BOE-specific exception.

The planned real destination is new:

`runs/final_holdout_p2_v1_truth_v2_working`

Running that real migration requires separate human authorization. Phase V2-A
implementation and tests use synthetic workspaces only.

## 10. Immutable V2 truth publication

`evaluation/final_holdout_v2/freeze.py` adapts publication to V2. It reuses V2
schema/completeness/FK validation, the annotation boundary's reserved-key check,
canonical source-identity validation and `validate_evidence_literal()`. It does
not use V1's freeze, which rewrites CSV and metadata and has V1-specific schema
and identity semantics.

The **working truth** contains ten annotation CSVs and original
`truth_metadata.json`, without a publication manifest. The **frozen truth** is
a new directory containing byte-identical copies of those eleven files, a
byte-identical `holdout_selection.csv`, and a new `manifest.json`: thirteen
files in total. Secondary data and migration/reviewer provenance are preserved.
No new annotation field or secondary-entity requirement is introduced.

Before publication the tool requires non-empty, complete V2 truth, exact
selection membership and document hashes, the selection SHA-256 recorded in
metadata, and a consistent `source_snapshot_id`. It recomputes the selected
source-document hashes from canonical BOE title/date/text and checks every
provided evidence passage against that source using the existing literal
validator. Snapshot-level provenance comes from the selection/metadata; the
tool does not recompute the unselected source corpus. The number of documents
comes from the validated selection: the real selection has 48, synthetic tests
may have fewer. It does not hardcode 48 or read prediction artifacts.

The existing `truth_semantic_identity()` algorithm is unchanged: canonical
table rows, truth-contract version and holdout/source identities determine the
truth ID; local paths, publication time and manifest fields do not. All ten
contractual tables, including retained secondary data and annotation notes,
continue to participate exactly as before.

Publication copies to a sibling staging directory, validates the copy, writes
and verifies the manifest, checks that working files/selection are unchanged,
then renames to the final destination. Existing destinations, symlinks used as
truth files, unexpected files and destinations inside the working workspace are
rejected. There is no overwrite option. On failure the staging directory is
removed; existing inputs/destinations are neither repaired nor restored. This
uses the repository's **single-writer convention**, not cross-process locking.

The manifest uses schema/version `final_holdout_truth_manifest_v2` and records:

- frozen status, truth-contract version/declaration hash and semantic truth ID;
- semantic hashes for all ten tables and physical SHA-256 for twelve files;
- selection/source identities, document count and reviewer/date provenance;
- the preserved declaration that predictions were not exposed;
- UTC publication time, `v2_truth_freeze_v1` and the freeze function entry point;
- a fingerprint of actual freeze/validation source files and `uv.lock`, computed
  by `_tool_source_hash()` even when code is uncommitted; no Git commit is guessed;
- a canonical manifest checksum independent of the annotated truth identity.

`load_truth(..., require_frozen=True)` rejects working truth and verifies the
manifest schema/checksum, exact file inventory, physical hashes, semantic
identity, provenance, completeness and copied selection. A manifest found by
ordinary `load_truth()` is also verified; corruption is never silently treated
as working truth. The existing annotation write boundary rejects frozen truth.
Verification needs no original source directory: documentary validation was
performed before publication and the validated bytes are hash-bound.

The publication command below documents the already completed truth freeze;
**do not repeat it on the existing destination**. V2-B development only verifies
that frozen truth read-only. A new real truth publication would require a
separate authorization and a new destination.

```bash
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m evaluation.final_holdout_v2.cli freeze-truth \
  --truth runs/final_holdout_p2_v1_truth_v2_working \
  --output runs/final_holdout_p2_v1_truth_v2_frozen \
  --holdout config/evaluation/final_holdout_p2_v1.csv \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source

UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m evaluation.final_holdout_v2.cli validate-frozen-truth \
  --truth runs/final_holdout_p2_v1_truth_v2_frozen
```

Both commands report the truth ID, count, manifest physical SHA-256,
`frozen_truth_intact=true` and `evaluator_implemented=true`. Preserve the
printed manifest hash in an approved external record. Later verification
can bind that external reference with `--expected-manifest-sha256 <SHA256>`.
Checksums detect drift; an independently preserved manifest hash also detects
coordinated rewriting of publication metadata and its internal checksum.
This is verified artifact immutability, not filesystem write protection or a
digital signature. The verification command never writes to the truth.

## 11. V2-B matching and scoring — defined before prediction exposure

Version: `final_holdout_scoring_v2_b_1`. All rules below are corpus-independent.
There is no fuzzy matching, external geographic knowledge, LLM, adjudication
at scoring time, macro average or global system accuracy.

| Entity | Candidate identity | Scoring after matching |
| --- | --- | --- |
| Generation asset | Within the same BOE, intersection of exact normalized aliases | Entity TP/FP/FN; `expected_generation_type` accuracy on applicable matched pairs |
| Event | Equal, nonempty **complete** sets of already matched assets in the same BOE | Entity TP/FP/FN; an unmatched truth asset or any extra/unmatched prediction asset prevents a match; split/merge remains visible |
| Administrative action | Same BOE, matched event, and at least one predicted evidence fragment contained in an accepted passage of that action | Current-only entity detection, current action attributes, attribution, evidence support; temporal contamination and P0 separately |
| Administrative location | Matched event and exact normalized `location_name_raw` | Entity TP/FP/FN and applicable matched `expected_location_level` accuracy; level, INE codes and geography do not participate in matching |

Name normalization reuses V1: Unicode NFKD, casefold, removal of `Mn`
diacritics, non-alphanumeric characters replaced with spaces, collapsed spaces,
**word order preserved**. V1's normalization docstring saying “order independent”
is inaccurate about words; its actual code preserves them. V1 is not edited.

Every assignment uses only edges present in **all maximum-cardinality 1:1
matchings**. No tie is resolved by attribute values, target sets, input order,
or arbitrary preference. Ambiguous scored truth stays FN when it is an expected
positive; unresolved predictions stay FP. Asset type is never a matching key;
action type, decision, modification and affected assets are never action keys.
Candidate edges and unresolved identities are published for audit.

Non-applicable or non-scored truth rows are excluded. A prediction forced to
such a row, or in a remaining candidate component containing only excluded
truth, is excluded from the relevant entity denominator. A mixed component with
scored truth remains unresolved and penalized. Predictions beneath an excluded
event are excluded from action/location scoring. Exclusion does not turn an
uncertain entity into a confirmed match. The frozen V2 loader requires every
completed document scope to be scored; there is no excluded-document denominator
in the final interface.

### Actions, temporal contamination and evidence

Action candidates include current and historical truth on equal terms; neither
status nor scored attributes breaks a tie. Accepted scored passages belonging
to that **action owner** alone may anchor a scored action. Unscored owner
passages may shield an excluded entity but cannot anchor a scored action.

Matched current actions are TP; unmatched current truth is FN. Matched historical
predictions contribute exactly one primary FP and one
`historical_contamination_fp`. Every other unresolved prediction contributes
one `other_fp`. Omitted history is reported as `historical_not_extracted`, never
FN. Temporally ambiguous truth and predictions assigned exclusively to it are
excluded from primary action extraction, action attributes, attribution and P0;
their counts remain explicit. A current/historical matching tie remains generic
FP/FN without guessing a historical-contamination label.

Action type, decision and modification accuracies apply only to matched current
actions. An absent prediction is incorrect where truth expects a value;
`is_modification` is not defaulted to false by the evaluator. Expected `__NA__`
excludes that field only. Generation and location fields follow the same
applicable-pair rule. Counts include correct, denominator, excluded and accuracy.

Evidence uses V1's literal functions: NFKC, casefold and whitespace collapse,
preserving punctuation. Literal `[...]` separates fragments. Candidate matching
requires **any** nonempty fragment to lie within an accepted owner passage;
`evidence_supported` requires a nonempty set and **all** fragments to lie within
one or more accepted passages of that same action. Empty evidence cannot anchor
a match and produces detection errors; the support predicate itself is false.
The published support rate is conditional on matched current actions, with
`supported` and denominator. It measures documentary support, **not independent
semantic understanding**, because evidence also participates in matching.

### Effective action-to-generation attribution

The production reference is `gold._action_project_attributions` and
`gold.build_project_events`. V2 projects their existing target semantics to
local generation-asset identities before cross-publication grouping:

- direct asset target → that predicted asset;
- event target → all predicted generation assets in the event;
- component target → only its explicit `related_generation_asset_refs`.

No component matching against secondary human truth is required. A known
component without generation links produces an empty set in Gold; V2 likewise
creates no asset and records `no_explicit_generation_links`. Missing/unknown
targets or parent references are reported in `unresolved_targets_json`; no
parent or synthetic asset is inferred. An actually predicted generation asset
without an asset match is retained with its distinct `prediction:` identity;
resolved assets use `truth:` identities. Sets remove duplicate references only.

Exact-set accuracy is conditional on matched current actions: projected set
equals `expected_affected_generation_asset_keys_json` and no unresolved target
remains. Pair scoring is corpus micro over **(action, generation asset)**:
intersection TP, extra predicted assets FP, absent expected assets FN. An omitted
or unmatched current action contributes every expected pair as FN. Historical
and unmatched predicted actions contribute each projected pair as FP; their
truth pairs never add historical FN. Excluded actions do not contribute pairs.
An unresolved target that establishes no generation asset creates no invented
pair FP; it remains an attribution diagnostic and cannot pass exact-set. Such
an action can still be an entity FP. The pair and entity denominators therefore
measure different units and are not interchangeable.

### Document scope and P0

Scope uses the explicit `extraction_json.document_scope` produced by the frozen
system. The cached attempt scope, when present, must agree. Failed attempts and
uncertain/missing scope contribute a `missing` prediction, counted incorrect
on a scored document. The confusion matrix has the two truth classes and a
third prediction column `missing`; no truth-based scope inference occurs.

P0 reads the original `possible_historical_antecedent` review-queue findings,
before human CURRENT/ANTECEDENT interventions. Each warning must identify the
same BOE and frozen positional event/action indices. Repeated alarms for one
action count once. Unresolvable finding IDs, warnings for nonexistent or
unmatched actions, and warnings against excluded/temporally ambiguous truth are
`unadjudicated` and never enter TP/FP/FN/TN. Historical omitted truth is reported
as `missing_extraction_not_p0_fn`.

On safely matched extracted actions: historical warning/no warning = TP/FN;
current warning/no warning = FP/TN. An extraction historical FP may simultaneously
be a P0 TP. False warning rate is `FP / (FP + TN)` over adjudicable extracted
current actions, with its own numerator, denominator and undefined reason.

### Metrics, denominators and ordering

One helper defines micro precision `TP/(TP+FP)`, recall `TP/(TP+FN)` and
`F1=2PR/(P+R)`. Each ratio includes its denominator. Precision or recall with a
zero denominator is JSON `null` with `zero_denominator`; F1 is `null` when either
is undefined. When both are defined and zero, F1 is explicitly zero. Its
`f1_denominator` is `P+R` when defined, otherwise null. Accuracy/support/false
warning rates with no applicable observations are likewise null with a reason.

Entity results are summed across documents before ratios. Attribute accuracies
are micro over applicable matched pairs, not conditional document averages.
Per-document entity TP/FP/FN totals are counts for drill-down, not a combined
system metric. Secondary entity detection, exact targets, power, participants,
non-action evidence and all other out-of-scope fields are not scored.

Relational CSV/Parquet row order has no effect on matching, metrics or sorted
report tables. Frozen production JSON array indices identify events, actions
and locations and must remain intact to retain the original P0 references;
reordering nested prediction arrays is not a relational row shuffle. Physically
different input artifacts retain their different physical provenance hashes.

## 12. Evaluator freeze, provenance and reports

`freeze-evaluator` requires verified frozen truth and explicit expected truth ID
and manifest hash. It binds that truth to a new evaluator artifact containing
`manifest.json` and the exact `scoring_rules.json`. Its evaluator identity covers
the scoring configuration, contract/version, relative code/configuration file
hashes, production Python reference code, `pyproject.toml` and `uv.lock`. It
contains no absolute paths, timestamps, metrics or prediction inputs. The
manifest separately records UTC creation time and truth/selection/source hashes.
`validate-evaluator` verifies the copied rules, manifest integrity and current
checkout against the declaration; optional external hashes pin the exact seal.

V1 has immutable **truth/result publication**, not a standalone evaluator-freeze
command. V2 adapts its staging/hash pattern and implements the missing evaluator
seal separately. It does not call V1 scoring or alter V1 files.

`evaluate` requires this evaluator freeze, its bound frozen truth, explicit
predictions, an execution record and a new output directory. The unchanged V1
execution-record schema/template is deliberately reused: its version describes
run provenance, not scoring. Validation pins the frozen system/config/model,
source and selection IDs, snapshot identity, UTC run/freeze times and model
usage. The evaluator freeze must precede extraction start. One fresh primary
attempt per document is required; duplicate IDs, incompatible lineage, inherited
attempts, retries as additional primary attempts, current-payload drift and
holdout manual/historical corrections or reviews are rejected. Source hashes
are recomputed from canonical source contents; manifest document identity,
artifact hashes/row counts and review identity are checked. No production
canonicalisation or P0 detector is rerun for scoring.

Outputs are `evaluation_summary.json`, twelve typed Parquet tables
(`document_results`, `entity_results`, `candidate_pairs`, `entity_matches`,
`unmatched_truth`, `unmatched_predictions`, `field_results`,
`affected_asset_sets`, `action_asset_pairs`, `evidence_results`, `p0_results`,
`error_inventory`), exact copies of truth/evaluator manifests and the execution
record, plus a report `manifest.json`. Summary contains primary metrics, counts,
denominators, scoring configuration, UTC time and all input identities.
Matches include explicit excluded/historical outcomes; consumers must use
`outcome`, not assume every structural match is an extraction TP.

Every table is deterministically ordered with a stable empty schema and checked
through a Parquet round trip. Semantic report identity excludes report-creation
time and paths; physical file hashes include all bytes. `validate-evaluation`
checks output bytes, copied provenance and semantic identity without loading the
original inputs. It is an integrity verifier, not a second scoring run or a
digital signature. External manifest hashes detect a resealed artifact.

Both publications use a sibling staging directory and reject existing or nested
input destinations. Inputs/code are checked again before rename; failures clean
staging and do not restore or rewrite source inputs. A single writer per
destination remains the convention; no cross-process exclusion is claimed.

The evaluator semantics are implemented in
[`evaluation/final_holdout_v2/`](../../evaluation/final_holdout_v2/) and the
operational interface is documented in the User Guide. The definitive freeze,
execution and results are recorded in
[`FINAL_HOLDOUT_V2_RESULTS.md`](FINAL_HOLDOUT_V2_RESULTS.md).
