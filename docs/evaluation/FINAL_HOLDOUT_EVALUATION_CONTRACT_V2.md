# Final holdout evaluation contract V2 — Phase V2-A

Status: **annotation contract and tooling implemented; evaluator, matching,
metrics and truth freeze not implemented**.

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
- `freeze-truth`;
- extraction or model execution.

Those capabilities belong to Phase V2-B and must be reviewed and frozen before
the system under evaluation is executed.

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

`temporal_status` preserves V1 semantics:

- `current`;
- `historical_antecedent`;
- `ambiguous_not_safely_determinable`;
- `not_applicable` where the entity itself is not scored.

P0 truth will be derived from this field in V2-B. No P0 output is read during
annotation.

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

## 10. Remaining V2-B gate

Before any system prediction is executed, Phase V2-B must separately implement,
test, review and freeze:

- deterministic primary-entity matching;
- effective action-attribution scoring;
- primary and secondary metrics;
- P0 scoring;
- prediction-isolation checks;
- truth freeze and immutable evaluation artifacts.

V2-A must never be described as an executable final evaluation.
