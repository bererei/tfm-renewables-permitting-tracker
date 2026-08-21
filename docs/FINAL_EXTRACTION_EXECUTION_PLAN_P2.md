# Final P2 Extraction Execution Plan

## 1. Purpose

This runbook resolves the interruption-risk blocker identified by the Final
Extraction Preflight P2. It versions the unseen holdout, limits paid work to
bounded model batches, reuses every completed batch through the production
`--attempts` boundary and ends in one complete contractual P2 extraction.

This document is an execution plan, not model authorization. **Gemini remains
NOT AUTHORIZED** until the diff, tests, artifacts, budget and commands receive
explicit human approval.

## 2. Inputs and identities

| Input | Contractual value |
| --- | --- |
| Period | 2024-01-01 through 2026-08-20, inclusive |
| Source | `runs/final-corpus-preflight-20220101-20260820-v2/source/` |
| Source snapshot ID | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| Scope policy | `binary_named_generation_pre_model_guard_v4` |
| Extraction config | `4b54b89dbfe8640e` |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| P2 documents | 19,489 |
| Deterministic documents | 14,452 |
| Model documents | 5,037 |

The source is referenced directly. It is not copied, downloaded or modified.
Every continuation validates the extraction snapshot manifest and every
attempt's config, provider/model, instruction, contract, validation version,
BOE ID and current source hash before an agent can be constructed.

## 3. Holdout selection

The versioned holdout is:

`config/evaluation/final_holdout_p2_v1.csv`

It contains 48 unique `MODEL_REQUIRED` BOEs, eight from each
`publication year × BOE-A/B` stratum. All are in P2 and none occurs in
`development_used_documents.csv`. The fixed seed is `20260821`; selection is
the first eight documents per stratum ranked by:

```text
sha256(seed | source_snapshot_id | extraction_config_id | boe_id)
```

Selection fingerprint:

`617e3a9379cbe7b8f041330d4579fea6f34ea592956c19dc29ad65325bd0fb17`

The artifact contains only pre-model metadata and lineage. It does not contain
or depend on Gemini, extracted actions, technology, grouping or Gold output.
The holdout has been selected and versioned but **not executed**.

## 4. Main scopes

The manifest and CLI scopes are in:

`config/evaluation/final_p2_execution_scopes_v1/`

The model universe is partitioned after removing the 48 holdout BOEs. Main
documents are ranked by:

```text
sha256(seed | source_snapshot_id | extraction_config_id | main | boe_id)
```

The first 19 scopes contain 250 documents each and `main-20` contains 239.
They are pairwise disjoint, their union contains 4,989 BOEs, and none overlaps
the holdout. The versioned manifest records every row count and fingerprint.

| Property | Value |
| --- | --- |
| Main scopes | 20 |
| Maximum documents/scope | 250 |
| Main documents | 4,989 |
| Holdout documents | 48 |
| Complete model universe | 5,037 |
| Main collection fingerprint | `ec619d4b3f160ee516b51ca801aec6e2931175e2ffae6d381d48d31a7597f4ca` |
| Model universe fingerprint | `1b14f5b07520a0c36e94368d59a6669737eea3a49b56be761b76cd44cba1e124` |
| Complete P2 scope fingerprint | `86c2d9ad0abb4c82654b0ce68d2cf2e61b9a58b35ef85571031562697f67f3f7` |

`UNION(main scopes) + holdout = 5,037`, every intersection between main
scopes is empty, and `holdout ∩ main = ∅`.

## 5. Attempt persistence

Within one batch, attempts are atomically checkpointed every five documents
inside the batch's staging directory. The final snapshot is published by an
atomic directory rename only after selection, queue and manifest creation.

A completed batch snapshot is a durable continuation input. Passing it with
`--attempts` copies its validated attempt history into the next cumulative
stage. Existing successful documents are absent from `execution_document_ids`
and therefore do not call the agent again.

No partial staging directory is discovered automatically. A normal interrupt
cleans it; a hard crash may leave it for forensic inspection. The operator
must never treat an orphan staging Parquet as a validated snapshot.

## 6. Resume procedure

Each execution stage uses the union of all main scope files up to that stage.
Stage 1 has no attempts input. Stage N uses the completed stage N−1 directory
as `--attempts`. Therefore the planner sees prior BOEs as compatible and only
executes the new disjoint batch.

If stage N is interrupted:

1. leave any orphan staging directory untouched;
2. confirm that the final stage-N output does not exist;
3. keep the last completed stage N−1 snapshot;
4. repeat the exact stage-N dry-run using stage N−1 as `--attempts`;
5. verify `compatible existing`, pending count, config and hashes;
6. after authorization, repeat the exact stage-N model command.

The maximum repeated work is the current batch: **250 model documents** (239
in the last batch). At historical throughput this is about 1.10 provider
hours, USD 3.01 expected and USD 6.05 conservative. Historical request density
suggests about 280 provider requests; the contractual usage limit permits at
most 1,500 requests if every document consumed all six allowed requests.

No successful work from an earlier completed batch is repeated.

## 7. Failure semantics

Continuation is fail-closed:

- a missing attempts path fails before agent construction;
- an extraction snapshot with different stage, config, provider/model,
  instructions, contract, validation or scope policy is rejected;
- a row with a stale source hash or a BOE outside the cumulative scope is
  rejected;
- duplicate `attempt_id`, incomplete lineage, invalid status/timestamp or
  corrupt successful extraction JSON is rejected;
- multiple distinct valid attempts remain supported; the existing review
  contract selects the latest by `extracted_at`, then `attempt_id`;
- a definitive failed attempt is not converted to success or silently called
  again; it remains in the blocking review queue.

After every completed scope, any blocking review count stops the chain. The
operator must resolve or explicitly review the failed document before the
next cumulative stage. Silver remains protected by its existing completeness
gate.

## 8. Final materialization

After main-20, run one cumulative holdout stage with all main scopes plus the
holdout and `main-20` as attempts. It reuses 4,989 main attempts and can call
only the 48 holdout BOEs.

After the holdout is evaluated and accepted without changing the frozen
policy, run `extract` once over `p2_all.csv`, using the completed holdout stage
as attempts and **without `--execute-model`**. The planner reuses all 5,037
model attempts and creates the 14,452 deterministic attempts locally. The
result is one ordinary extraction snapshot for all 19,489 P2 documents, with
canonical production ordering, review queue, hashes and manifest.

This is the contractual union mechanism. There is no manual Parquet
concatenation, copying, aliasing or merge.

## 9. Dry-run validation

All 22 production-planner dry-runs passed offline on 2026-08-21:

- `main-01` through `main-19`: 250 documents, 0 deterministic, 250 model,
  0 conflicts each;
- `main-20`: 239 documents, 0 deterministic, 239 model, 0 conflicts;
- holdout: 48 documents, 0 deterministic, 48 model, 0 conflicts;
- complete P2: 19,489 documents, 14,452 deterministic, 5,037 model,
  0 conflicts.

Every dry-run reported model calls planned = 0. BOE, Gemini, other model and
web calls were all zero. No `runs/` output was created.

## 10. Cost and risk per scope

The manifest stores the orientative hours and expected/conservative cost for
each scope. Values use the approved P2 preflight evidence:

| Scope | Model documents | Hours | Expected USD | Conservative USD |
| --- | ---: | ---: | ---: | ---: |
| each `main-01`…`main-19` | 250 | 1.1016 | 3.01 | 6.05 |
| `main-20` | 239 | 1.0531 | 2.88 | 5.78 |
| holdout | 48 | 0.2115 | 0.58 | 1.16 |

The total P2 budget remains USD 60.74 expected, USD 121.87 conservative and
USD 157.00 operator cap. Batching does not add model documents; it controls
repeat exposure after interruption.

## 11. Operator runbook

Before each scope:

1. verify clean Git state and the approved `HEAD`;
2. verify source ID, config ID and the scope fingerprint in `manifest.json`;
3. verify that the output directory does not exist;
4. execute the exact dry-run and compare counts;
5. verify the previous completed snapshot before passing `--attempts`.

After each scope:

1. load and inspect `manifest.json`;
2. verify expected document, attempt and compatible-existing counts;
3. require blocking review = 0 before continuing;
4. record successful/error counts and usage from `attempts.parquet`;
5. preserve the snapshot immutably as the next continuation input.

Never delete validated attempts, use a force/overwrite workaround, mix source
or config identities, salvage orphan staging as a snapshot, or manually
concatenate Parquets.

## 12. Exact commands

These commands use only real `pipeline extract` flags. They are deliberately
prefixed with the authorization warning and must not be executed during this
change.

### Main stages 01–20 and continuation

Set `START_BATCH=1` for a new run. After an interruption in batch N, set it to
N; the loop reconstructs the cumulative scope arguments and reuses the last
completed N−1 snapshot.

```bash
# DO NOT RUN — GEMINI NOT YET AUTHORIZED
START_BATCH=1
scope_args=()

for batch in $(seq -w 1 20); do
  scope_args+=(
    --scope "config/evaluation/final_p2_execution_scopes_v1/main-${batch}.csv"
  )
  if ((10#${batch} < START_BATCH)); then
    continue
  fi

  output="runs/final-tfm-p2-20240101-20260820-v1/extraction-main-${batch}"
  test ! -e "${output}" || {
    echo "STOP: output already exists: ${output}" >&2
    exit 1
  }

  attempt_args=()
  if ((10#${batch} > 1)); then
    previous=$(printf '%02d' "$((10#${batch} - 1))")
    attempt_args=(
      --attempts
      "runs/final-tfm-p2-20240101-20260820-v1/extraction-main-${previous}"
    )
  fi

  UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
  uv run python -m renewables_permitting.pipeline extract \
    --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
    --output-dir "${output}" \
    "${attempt_args[@]}" \
    "${scope_args[@]}" \
    --expected-extraction-config-id 4b54b89dbfe8640e \
    --dry-run

  # DO NOT RUN — GEMINI NOT YET AUTHORIZED
  UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
  uv run python -m renewables_permitting.pipeline extract \
    --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
    --output-dir "${output}" \
    "${attempt_args[@]}" \
    "${scope_args[@]}" \
    --execute-model \
    --expected-extraction-config-id 4b54b89dbfe8640e

  uv run python -m json.tool "${output}/manifest.json" > /dev/null
  uv run python -c \
    'import json,sys; m=json.load(open(sys.argv[1], encoding="utf-8")); assert m["counts"]["blocking_review"] == 0' \
    "${output}/manifest.json"
  read -r -p "Review ${output}; type NEXT to continue: " decision
  test "${decision}" = "NEXT" || exit 0
done
```

The explicit prompt stops the loop after each stage so the operator can perform
the after-scope checks before allowing the next iteration. The compact loop is
the exact command for every main scope; it does not imply unattended
authorization.

### Holdout stage

```bash
# DO NOT RUN — GEMINI NOT YET AUTHORIZED
scope_args=()
for batch in $(seq -w 1 20); do
  scope_args+=(
    --scope "config/evaluation/final_p2_execution_scopes_v1/main-${batch}.csv"
  )
done
scope_args+=(--scope config/evaluation/final_holdout_p2_v1.csv)

# DO NOT RUN — GEMINI NOT YET AUTHORIZED
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-tfm-p2-20240101-20260820-v1/extraction-main-20 \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction-holdout \
  "${scope_args[@]}" \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --dry-run

# DO NOT RUN — GEMINI NOT YET AUTHORIZED
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-tfm-p2-20240101-20260820-v1/extraction-main-20 \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction-holdout \
  "${scope_args[@]}" \
  --execute-model \
  --expected-extraction-config-id 4b54b89dbfe8640e
```

### Complete final P2 extraction

```bash
# DO NOT RUN — GEMINI NOT YET AUTHORIZED
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-tfm-p2-20240101-20260820-v1/extraction-holdout \
  --scope config/evaluation/final_p2_execution_scopes_v1/p2_all.csv \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --dry-run

# DO NOT RUN — GEMINI NOT YET AUTHORIZED
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-tfm-p2-20240101-20260820-v1/extraction-holdout \
  --scope config/evaluation/final_p2_execution_scopes_v1/p2_all.csv \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction \
  --expected-extraction-config-id 4b54b89dbfe8640e
```

The final command contains no `--execute-model`. A dry-run of the exact command
must report compatible existing = 5,037, deterministic pending = 14,452 and
model calls required/planned = 0 before it is run without `--dry-run`.

## 13. Human authorization gate

Gemini may be authorized only after all of the following are approved:

- holdout and scope artifacts, schemas and four fingerprints;
- fail-closed attempt validation and regression tests;
- full test suite;
- dry-run counts for every scope;
- maximum repeat exposure of 250 model documents;
- exact run paths and commands;
- budget checkpoint and API-key handling;
- human decision that the holdout policy and extraction config are frozen.

Current status:

```text
RESUME MITIGATION: IMPLEMENTED + TESTED — PENDING HUMAN REVIEW
HOLDOUT: 48 BOE SELECTED + VERSIONED — NOT EXECUTED
GEMINI: NOT AUTHORIZED
NEXT: HUMAN REVIEW + EXPLICIT MODEL AUTHORIZATION
```
