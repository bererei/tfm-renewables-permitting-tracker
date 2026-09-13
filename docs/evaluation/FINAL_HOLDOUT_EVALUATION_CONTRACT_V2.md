# Final holdout evaluation contract V2 — annotation and truth publication

Status: **annotation and immutable truth-publication tooling implemented;
evaluator, matching and metrics not implemented**. The real V2 truth freeze
has not been executed; implementation awaits human review.

Contract identifier: `final_holdout_evaluation_contract_v2`.

Frozen system under evaluation:
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
V2 defines **no categorical temporal-status accuracy**. The detailed matching,
handling of ambiguous truth and scoring implementation remain a later V2-B gate.

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
The future P0 false warning rate is `FP / (FP + TN)` over extracted/matched,
adjudicable **current** actions. It is distinct from the rate of all warnings
over all extracted actions. Zero-denominator handling remains to be frozen with
V2-B. No metric or scoring implementation is added by this decision.

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

CLI examples, **only after implementation review, approved commit/push and
separate authorization for the real freeze**; not executed during development:

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
`frozen_truth_intact=true` and `evaluator_implemented=false`. Preserve the
printed manifest hash in the approved execution record. Later verification
can bind that external reference with `--expected-manifest-sha256 <SHA256>`.
Checksums detect drift; an independently preserved manifest hash also detects
coordinated rewriting of publication metadata and its internal checksum.
This is verified artifact immutability, not filesystem write protection or a
digital signature. The verification command never writes to the truth.

## 11. Remaining V2-B gate

Before any system prediction is executed, Phase V2-B must separately implement,
test, review and freeze:

- deterministic primary-entity matching;
- effective action-attribution scoring;
- the approved reduced primary metrics and explicit diagnostic exclusions;
- P0 scoring;
- prediction-isolation checks;
- immutable evaluation artifacts consuming the already frozen V2 truth.

V2-A must never be described as an executable final evaluation.
