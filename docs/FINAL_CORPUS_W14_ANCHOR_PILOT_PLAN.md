# Final corpus W14 anchor pilot plan

Status on 2026-08-24: **prepared offline; Gemini execution is not
authorized**. P2 remains the contractual corpus baseline, `main-04` remains
paused, the two `main-03` retries remain unauthorized and the final holdout
remains sealed and unexecuted.

## 1. Pilot definition and gate

W14 is the inclusive publication window from **2026-08-07 through
2026-08-20**. It is a bounded anchor-only experiment intended to measure the
quality and product breadth of a recent cohort before any decision to pivot
away from P2 or implement historical retrieval.

The offline funnel was recomputed from the validated source snapshot
`runs/final-corpus-preflight-20220101-20260820-v2/source`, whose document
identity is:

```text
1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf
```

| W14 funnel | Documents |
| --- | ---: |
| Canonical documents | 173 |
| Deterministic, no model | 124 |
| `MODEL_REQUIRED` | 49 |
| Sealed holdout overlap | 1 |
| Executable non-holdout scope | 48 |
| Classification conflicts | 0 |

The holdout row was excluded by identifier without inspecting its document
content. The executable scope is
`config/evaluation/final_w14_anchor_pilot_v1.csv`: it has the same schema as a
P2 main scope, 48 unique BOEs (25 series A and 23 series B), no deterministic
rows and no holdout row. Its established semantic fingerprint is:

```text
ed07c25e74aaff29c19e28362f70dfa973f40a0aa74b189d0077539b5fe1c2c2
```

The scope is also disjoint from the unauthorized operational retries
`BOE-B-2025-41490` and `BOE-B-2025-45035`.

## 2. Scope-safe reuse snapshot

The compatible cumulative parent is:

```text
runs/final-tfm-p2-20240101-20260820-v1/
extraction-main-03-recanonicalized-v2
```

Its loader-validated snapshot identity is:

```text
63a4de65b05468eb7a894d662ba7c47c7513d73eb7110a720ae11350190f69a4
```

The public `extraction-subset` operation performs a deterministic contractual
projection. It verifies the parent, preserves every attempt and manual-review
row for selected parent documents, reconstructs current selection and review
state with the production mechanisms, records parent/scope/code provenance
and atomically publishes a new standard extraction snapshot. It never creates
attempts for scope documents absent from the parent and does not relax
`extract` validation of attempts outside scope.

The offline W14 projection is:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/reuse-input
```

| Projection property | Result |
| --- | --- |
| Operation/version | `snapshot_type=extraction_subset`; stage/operation version `1` |
| Snapshot identity | `a367bed21b2197fcb47edec076e8dea7c526b76d4c4bf84e76fc222f4aafec29` |
| Deterministic code SHA-256 | `3f8784db511ca7822f4aa291d63a4bf78654f691fda05e3a4036bd6916453086` |
| Scope BOEs | 48 |
| Documents with reusable history | 6 |
| Preserved attempt rows / unique IDs | 20 / 20 |
| Duplicate attempt IDs | 0 |
| Current extractions | 6 |
| Manual reviews / blocking reviews | 0 / 0 |
| Scope BOEs absent from parent | 42 |
| Out-of-scope documents or attempts | 0 |
| Model calls used to build projection | 0 |

The 20 selected attempt rows are semantically identical to the complete
selected-document history in the parent. Source hashes, extraction config,
instructions and contract lineage all validate. Physical hashes of all six
parent artifacts were unchanged before and after publication.

## 3. Validated dry-run

This command was executed without `--execute-model`:

```bash
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-w14-anchor-pilot-20260807-20260820-v1/reuse-input \
  --scope config/evaluation/final_w14_anchor_pilot_v1.csv \
  --output-dir runs/final-w14-anchor-pilot-20260807-20260820-v1/extraction \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --dry-run
```

It reported 48 documents, 6 compatible existing extractions, 42 pending
documents, 0 explicit retries, 0 deterministic pending documents, 42 model
documents required and 0 model calls planned. It created no extraction output.

## 4. Cost basis

The real `main-01` through `main-03` evidence contains 753 root attempts for
750 documents: 859 requests, 7,525,777 input tokens, 2,789,406
output/thinking tokens and 3.6889208 provider hours. Estimates use the
versioned Standard prices of USD 0.30/M input tokens and USD 2.50/M
output/thinking tokens. Conservative time and cost take the worst observed
per-document main-scope rates independently.

| Estimate for 42 fresh documents | Value |
| --- | ---: |
| Expected provider requests | 48.104 |
| Expected provider minutes | 12.394774 |
| Conservative provider minutes | 12.858118 |
| Expected USD | 0.5169499 |
| Conservative USD | 0.5504375 |

These are planning estimates, not usage limits or authorization.

## 5. Future execution command

> [!CAUTION]
> **DO NOT RUN — GEMINI W14 PILOT NOT YET AUTHORIZED.** The command below is
> recorded for human review and must not be executed without a separate,
> explicit authorization.

```bash
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --attempts runs/final-w14-anchor-pilot-20260807-20260820-v1/reuse-input \
  --scope config/evaluation/final_w14_anchor_pilot_v1.csv \
  --output-dir runs/final-w14-anchor-pilot-20260807-20260820-v1/extraction \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --execute-model
```

This exact command isolates 42 fresh non-holdout W14 documents. It does not
select either `main-03` retry and does not execute `main-04`.

## 6. Post-pilot decision gate

If the bounded execution is later authorized and completes, stop for human
semantic review of the W14 anchor. Only after that review may an offline,
in-memory grouping and strict historical retrieval audit be repeated. A
separate human GO is required before implementing backfill, changing the final
corpus decision, running Silver/Gold or using a new dataset in Streamlit.

Until that gate, W14 is **ready for authorization, not authorized**. P2,
main-03 retry status and holdout status are unchanged.
