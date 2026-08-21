# Final Extraction Preflight — P2

## 1. Purpose

This is the last read-only technical gate before any Gemini execution for the
Final TFM corpus. It verifies the approved period, source, scope policy,
extraction identity, funnel, holdout design, corrections, execution safety,
historical usage, pricing and budget. It does not authorize the model run.

Audit date: **2026-08-21**. Repository state at the start of the audit:

- branch: `tfm-final`;
- `HEAD` and `origin/tfm-final`:
  `b232ccaaea43a574373053361a488250ab1c99d0`;
- working tree: clean;
- BOE calls: **0**;
- Gemini calls: **0**;
- other model calls: **0**;
- pricing-only official Google web requests: **2**.

## 2. Final target period

The Final TFM target is **P2**, from **2024-01-01 through 2026-08-20,
inclusive**. P3, from **2025-01-01 through 2026-08-20**, remains only a
delivery-risk fallback.

The product must describe this as the *analysed period* and a project's first
record as its *first publication in the analysed period*. This corpus does not
prove a complete historical lifecycle, the first publication ever, or the
project's consolidated current legal status.

## 3. Source snapshot

The source is reused by direct reference:

`runs/final-corpus-preflight-20220101-20260820-v2/source/`

Its verified identity is:

`1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf`

The `source` v1 manifest, tabular artifact hashes, 1,454 summary hashes and
25,347 XML hashes all reproduce. The snapshot covers 2022-01-01 through
2026-08-20 and therefore all of P2. It contains 1,693 dates, 1,454 successful
summaries, 239 no-publication dates, 328,629 BOE items, 25,347 candidates and
25,347 prepared documents. BOE identifiers are unique; every document has
`xml_status=ok`; there are no parse errors or incomplete staging siblings.

Classification: **SOURCE SNAPSHOT REUSABLE FOR P2**. No redownload and no
manual Parquet copy are required. Current official source drift is already
represented by the snapshot.

## 4. Scope and extraction identity

The effective policy and configuration were derived from production code:

| Property | Effective value |
| --- | --- |
| Scope policy | `binary_named_generation_pre_model_guard_v4` |
| R1 | enabled |
| R3 | enabled |
| R2 | not implemented |
| R4 | not implemented |
| Old extraction config | `8158661f76a31c87` |
| Current extraction config | `4b54b89dbfe8640e` |
| Provider | `gemini` |
| Model | `google:gemini-2.5-flash` |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| Contract schema SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| `AGENT_RETRIES` | 3 |
| Per-document timeout | 600 seconds |
| Per-model-run timeout | 240 seconds |
| Usage limit | at most 6 model requests per document |
| Document-validation retry | 1 |
| Outer transient run attempts | 2 total, hence 1 retry |
| Transient backoff | 2 seconds before the retry |
| Checkpoint interval | 5 documents |
| Concurrency | 1 document; sequential and not configurable |

These hashes match the expected current v4 identity. Strict identity is
enforced: compatible automatic reuse from old-config extractions is **0**.

## 5. P2 funnel

The production classifier reconstructs the exact invariant:

| P2 outcome | Documents |
| --- | ---: |
| Canonical documents | 19,489 |
| Deterministic, no model | 14,452 |
| `MODEL_REQUIRED` | 5,037 |
| Conflicts | 0 |

`19,489 = 14,452 + 5,037 + 0`.

## 6. Annual distribution

| Year | Canonical | Deterministic | `MODEL_REQUIRED` | Model rate |
| ---: | ---: | ---: | ---: | ---: |
| 2024 | 8,258 | 6,102 | 2,156 | 26.1080% |
| 2025 | 7,152 | 5,362 | 1,790 | 25.0280% |
| 2026 through 20 August | 4,079 | 2,988 | 1,091 | 26.7468% |

## 7. Source drift

`BOE-A-2026-11850` is present once in source v2, dated 2026-06-03. Its
current source hash is
`c95bafebaa350dbbb18b2ac36e5d5a137508a94f36045f1780832b5152259558`;
the development source hash was
`53ba075b46c616e4870d4a88f7e7762146c7dc07003b83d506700aa08d1ebc12`.
The current text corrects the duplicated wording `de la la` to `de la`.

There is no BOE-specific rule in production code or tests. Under v4 it is
`MODEL_REQUIRED`. Its old extraction is not reusable; a future attempt must
derive a new identity from the current document hash and config ID.

## 8. Holdout exposure registry

`config/evaluation/development_used_documents.csv` validates as follows:

| Check | Result |
| --- | ---: |
| Rows | 479 |
| Unique BOE IDs | 479 |
| Historical exposure rows | 152 |
| Classifier-audit rows | 327 |
| Duplicate BOE IDs | 0 |
| P2 exposed BOEs | 263 |
| P2 provisional holdout-eligible BOEs | 19,226 |

The `usage_type` values all belong to the declared domain. The reproducible
master fingerprint is
`2e9da51070304ac15d5d941cdc2f1f9861da0c71d34cb6fb64cac34905e90f80`;
the historical subset fingerprint is
`d1168bbeb9b4cc907c8dad9ba31fdc38f438bde6068b890c24ff7174867959a6`.

## 9. Holdout objective

The primary objective is **A: measure AI extraction quality on unseen BOE
documents**. The observed result includes canonicalisation because it is part
of the extraction output, but the holdout must not be presented as an
independent estimate of classifier, canonicalisation, complete pipeline,
grouping or downstream quality. The pre-model classifier already has separate
audit evidence.

The primary unit is the **BOE document**. It matches the agent input,
source/extraction identity and exposure registry; it is reproducible and keeps
human review and leakage accounting at the same granularity.

## 10. Holdout design

Choose **H1**, solely from P2 documents classified `MODEL_REQUIRED` by v4.
H2 would dilute the estimate with deterministic decisions and mix distinct
pipeline layers.

The exact H1 pool is:

| Pool | Documents |
| --- | ---: |
| P2 `MODEL_REQUIRED` | 5,037 |
| Development-exposed `MODEL_REQUIRED` | 139 |
| Holdout-eligible H1 | 4,898 |

The eligible pool is 97.2404% of P2 `MODEL_REQUIRED`: 2,113 in 2024, 1,755
in 2025 and 1,030 in 2026. Its year/series cells are 2024 A=880, B=1,233;
2025 A=615, B=1,140; 2026 A=368, B=662.

Recommended sizes are **minimum 30**, **preferred 48**, **maximum 72**.
With six year-by-series strata these correspond to 5, 8 and 12 reviews per
stratum. Forty-eight provides balanced temporal and BOE-series coverage while
remaining feasible before 31 August.

## 11. Holdout selection strategy

Use the six pre-model strata `publication_year × BOE series (A/B)`, fixed seed
`20260821`, and deterministic hash ranking. Within each stratum, sort by:

```text
sha256(seed | source_snapshot_id | extraction_config_id | boe_id)
```

Select the first quota rows, never using Gemini, extraction, grouping or Gold
fields. This is preferable to runtime pseudo-random state because each choice
can be reconstructed directly from source, v4, the exposure registry, P2 and
the seed.

A versioned selection artifact is required but is deliberately not created in
this preflight. Proposed path:

`config/evaluation/final_holdout_p2_v1.csv`

Proposed columns:

```text
holdout_version, identifier_boe, publication_date,
source_document_sha256, year, boe_series, stratum_population,
stratum_quota, selection_rank, selection_hash, seed,
source_snapshot_id, extraction_config_id, scope_policy,
period_start, period_end
```

Its identity should be SHA-256 over canonical UTF-8 lines sorted by BOE ID,
including the selection lineage and metadata above.

Status: **HOLDOUT STRATEGY READY — VERSIONED SELECTION ARTIFACT REQUIRED**.

## 12. Holdout execution

Use **Option A**. Exclude the holdout from the main extraction; run it only
after instructions, contract, scope, canonicalisation and review criteria are
frozen. Then build one cumulative full-P2 extraction snapshot by reusing the
main attempts and calling only the selected holdout documents.

If the holdout passes and no rule changes follow, its one-time results may be
included in the final corpus. If it fails, either accept and document the
limitation or change the system and retire this holdout, selecting a new
untouched one for any new final evaluation. The same failed holdout must not be
used both for tuning and renewed final claims.

The 48 preferred holdout calls are part of the 5,037 total, not additional to
them: main=4,989 and holdout=48.

## 13. Corrections

The versioned registry contains **5** corrections, all inside P2 and none
outside it. The file SHA-256 is
`51ac0cea06c02547e5ebfb20ee8a5239fca80519de9ee6bff3781bb511386411`;
its semantic ID is
`12a401d7594129e69a473a6d44f71dc89e05334f18493ddf65fbae15106b9dea`.

| Correction ID | BOE/date | Target | Source hash | Present and compatible |
| --- | --- | --- | --- | --- |
| `historical-action-exclusion-v1-16662-dia` | BOE-A-2024-16662 / 2024-08-10 | `BOE-A-2024-16662_event_1_action_2`, DIA/desfavorable | `9e9c7fca7e48120bfcf71d38e7e78885e124f03947105a8e423a25b916c19064` | yes |
| `historical-action-exclusion-v1-16662-public-information` | BOE-A-2024-16662 / 2024-08-10 | `BOE-A-2024-16662_event_1_action_3`, public information/convocado | same | yes |
| `historical-action-exclusion-v1-9608-environmental-request` | BOE-A-2024-9608 / 2024-05-13 | `BOE-A-2024-9608_event_1_action_1`, environmental request/solicitado | `1661f4b527654e11a7a69df0b7766949c07994761986581122e8af905af87d0d` | yes |
| `historical-action-exclusion-v1-9608-document-remediation` | BOE-A-2024-9608 / 2024-05-13 | `BOE-A-2024-9608_event_1_action_2`, remediation/subsanado | same | yes |
| `historical-action-exclusion-v1-26110-dia` | BOE-A-2025-26110 / 2025-12-19 | `BOE-A-2025-26110_event_1_action_2`, DIA/favorable | `3b77b5dbf16bd88ee12e037443994b5ba60c5531674425e0d3a2863c259cdb26` | yes |

The correction application is fail-closed: every supplied target must exist
exactly once and retain its action type, decision and evidence fingerprint.
There is no official partial-registry selector. The complete registry is valid
for P2 because all five targets are in the corpus. Applicability must be
revalidated against the new extraction outputs before Silver; it is currently
not a corrections blocker.

## 14. Extraction persistence

Persistence is **MIXED**:

- documents and initial attempts are copied into a fresh sibling staging
  directory;
- extraction is sequential, one document at a time;
- attempts are checkpointed every 5 completed documents with an atomic
  temporary-file replacement inside staging;
- each attempt persists parsed pre-canonical JSON, canonical JSON or the
  error, aggregate token/request usage and duration;
- provider raw responses and detailed thinking-token metadata are **not**
  persisted;
- current selection, manual-review result, review queue and the stage manifest
  are built only after all extraction work;
- the complete staging directory is atomically renamed to the final output.

Thus final publication is atomic, but intermediate progress is not a published
or automatically resumable extraction snapshot.

## 15. Resume and interruption

Resume is **PARTIALLY SUPPORTED**. A completed compatible extraction snapshot
or explicit attempts Parquet can be reused under strict source/config
identity. There is no automatic discovery or recovery of an in-flight staging
directory, no per-document provider-response cache and no partial manifest.

| Abrupt stop after | Successful calls checkpointed | Parsed output and aggregate usage | Final manifest | Staging | Automatic next-run reuse |
| ---: | --- | --- | --- | --- | --- |
| 10 documents | yes, in staging | yes | no | removed on graceful interruption; may remain on hard kill | no |
| 500 documents | yes, in staging | yes | no | same | no |
| 3,000 documents | yes, in staging | yes | no | same | no |

At exact checkpoint multiples all completed attempt rows are in the staging
Parquet. A non-multiple hard stop may lose up to four rows. Normal exception or
interrupt cleanup removes staging; a hard kill or power failure may leave an
orphan, but reuse requires manual, validated recovery through `--attempts` and
is not a contractual automatic resume path.

Consequently, a normal relaunch after a late failed stage can call Gemini again
for every model document in that stage. With 5,037 model documents this is a
**BLOCKER BEFORE GEMINI** and the interruption cost risk is **HIGH**.

## 16. Chunking

The CLI has no date, year, limit, offset, shard, batch, continuation, append,
overwrite, force or retry flag. It does support one or more inclusion scopes
through `--scope`, and compatible prior work through `--attempts`.

Independent yearly snapshots cannot be manually concatenated and there is no
merge command. A contractual single snapshot can, however, be rebuilt
cumulatively: run a bounded scope, then a larger cumulative scope using the
prior completed snapshot as `--attempts`; the last full-P2 run validates,
deduplicates and publishes one extraction snapshot.

Classification:

- subset/chunk capability: **PARTIALLY SUPPORTED**;
- year-based chunks as an economically safe plan: **no** (2024 alone still
  requires 2,156 model documents);
- contractual merge: **yes only through cumulative rebuild**, not independent
  Parquet merge;
- bounded cumulative scope creation and a validated continuation runbook/tool:
  **REQUIRED BEFORE GEMINI**.

## 17. Concurrency

The runner is asynchronous internally but awaits one document at a time. Task
concurrency and worker count are both **1**; there is no semaphore, batch or
parallel worker pool. Concurrency is not configurable by CLI, environment or
active extraction config. This preflight does not recommend changing it.

## 18. Model retries and failure behavior

`AGENT_RETRIES=3` is the agent's model/tool/output-validation retry budget; it
is not an HTTP retry count. Every document is capped at six model requests.
One explicit document-validation retry is possible while under that cap.

The runner performs at most two outer run attempts (one retry) for timeout or
status 408, 425, 429, 500, 502, 503 or 504, with a 2-second backoff. A generic
network error without a recognized transient status/timeout is not retried by
this outer policy. Malformed or Pydantic-invalid output can consume agent
validation retries. A usage-limit failure is final for that document.

After definitive failure, an error attempt is persisted and processing
continues; final selection leaves the case in a blocking review queue. This
preserves corpus visibility but prevents a valid final extraction/Silver gate
until the failure is resolved.

## 19. Historical Gemini usage

The primary comparable evidence is the independent model run at:

`runs/canonical-140-freeze-20260811/extraction/attempts.parquet`

It used Gemini 2.5 Flash with full text and config `67a0bd9d0759a322` on
2026-08-11. Its prompt/schema/scope predate v4, so it is comparable but not
identical. Later final recanonicalisation repeats the same usage values and is
not counted as another model run.

| Metric | Observed |
| --- | ---: |
| Corpus documents | 140 |
| Model documents analysed | 123 |
| Successful model documents | 123 |
| Failed model documents | 0 |
| Model requests | 138 |
| Documents with more than one request | 15 (12.1951%) |
| Extra requests | 15 |
| Mean requests/document | 1.121951 |
| Maximum requests/document | 2 |
| Input tokens | 1,634,596 |
| Output tokens, including any thinking | 434,378 |
| Separately persisted thinking tokens | unavailable |
| Total relevant tokens | 2,068,974 |

All-model-document token distribution:

| Tokens/document | Count | Mean | Median | p75 | p90 | p95 | Min | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Input | 123 | 13,289.40 | 10,226 | 17,388 | 25,828.6 | 32,052.8 | 3,107 | 63,809 |
| Output | 123 | 3,531.53 | 3,513 | 5,233.5 | 7,805 | 8,959.6 | 184 | 15,299 |
| Total relevant | 123 | 16,820.93 | 14,223.5 | 22,292 | 32,776.6 | 37,905.4 | 3,496 | 64,719 |

For projection, the 108 one-request documents provide the no-retry base:
input mean 11,504.59, median 8,456.5 and p90 22,629.2; output mean
2,918.85, median 2,835 and p90 5,910.3.

Evidence classification: **USAGE EVIDENCE PARTIAL**. Aggregate provider usage
is real, but raw responses, separately itemized thinking tokens and detailed
retry causes are not persisted. The current prompt, schema and classifier also
differ from the historical config.

`THINKING ACCOUNTING`: the active Google adapter includes candidates plus
thoughts in output tokens, while the attempt store retains only that aggregate.
Thinking is therefore included in projected output and must not be added again.

## 20. Token projection

The historical request multiplier is `138 / 123 = 1.121951`, implying about
614 additional requests and **5,651 expected requests** for 5,037 model
documents.

| Scenario | Retry treatment | Input tokens | Output including thinking | Total relevant tokens |
| --- | --- | ---: | ---: | ---: |
| Median | no-retry base | 42,595,390 | 14,279,895 | 56,875,286 |
| Median | observed-retry adjusted | 47,789,950 | 16,021,346 | 63,811,296 |
| Mean | no-retry base | 57,948,633 | 14,702,257 | 72,650,890 |
| Mean | observed-retry adjusted | 65,015,539 | 16,495,215 | 81,510,754 |
| Conservative p90 | no-retry base | 113,983,280 | 29,770,181 | 143,753,462 |
| Conservative p90 | observed-retry adjusted | 127,883,680 | 33,400,691 | 161,284,371 |

The expected total can also be scaled directly from all historical model
documents, yielding approximately 66.94 million input and 17.79 million output
tokens. Its proximity to the retry-adjusted mean is a useful independent
sanity check.

Historical provider duration implies **22.2 orientative provider hours** for
5,037 documents at 226.94 documents/hour. This is non-contractual and excludes
human review, corrections, Silver, Gold, validation and deployment; outages
and future retry behavior can increase it.

## 21. Official pricing

Production maps `google:` to the Google provider using the Gemini Developer
API client (`vertexai=False`) and API-key credentials, not Vertex AI. No local
pricing table exists.

Official source consulted twice on 2026-08-21:
[Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
(page last updated 2026-08-13).

Gemini 2.5 Flash Standard paid pricing is **USD 0.30 per million text input
tokens** and **USD 2.50 per million output tokens, including thinking**. There
is no applicable context-length price threshold for this model's standard
rate. The pipeline does not use context caching, Batch, Flex, Priority or
grounding pricing. The account's billing tier is not locally provable, so the
free tier must not be assumed and paid Standard pricing is the budget basis.

## 22. Cost projection

The calculation is:

```text
input USD  = input_tokens  / 1,000,000 × 0.30
output USD = output_tokens / 1,000,000 × 2.50
total USD  = input USD + output USD
```

Thinking is already included in output and is not double-counted.

| Scenario | No-retry USD | Observed-retry adjusted USD |
| --- | ---: | ---: |
| Median | 48.48 | 54.39 |
| Mean / expected | 54.14 | **60.74** |
| p90 / conservative | 108.62 | **121.87** |

The 48-document holdout is included once in the 5,037 total. Under the
retry-adjusted mean, main extraction is approximately USD 60.16 and holdout
USD 0.58; under p90 they are USD 120.71 and USD 1.16. No EUR conversion is
reported because no permitted current FX source was consulted.

Monetary status: **ESTIMATED**, using official paid list prices and real local
usage evidence; actual billing tier and future usage remain variable.

## 23. Budget and economic risk

`EXPECTED COST = USD 60.74` and `CONSERVATIVE COST = USD 121.87`.

The proposed **OPERATOR BUDGET CAP is USD 157.00**. It is the retry-adjusted
p95 component projection (USD 156.12) rounded upward to a usable control, not
automatic authorization and not a code-enforced cap.

The one-run amount is moderate, but economic risk is **HIGH** because the
current interruption path can repeat large portions of a paid run. The cost
sanity check passes; resume safety does not.

## 24. Disk capacity

Source v2 occupies **1,053,506,147 bytes (0.981 GiB)**. Free space at audit
time was **859,189,399,552 bytes (about 800.18 GiB)** with the filesystem 17%
used. Comparable development extraction directories occupy about 3.0 MB for
140 documents. Linear scaling suggests hundreds of MB rather than hundreds of
GB, but that is orientative; staging can temporarily duplicate an extraction
stage and final Silver/Gold size was not estimated as a contractual value.

Disk risk: **LOW**. No files were removed.

## 25. Final dry-run

The production `pipeline extract` dry-run used source v2 and an ephemeral,
in-memory-derived P2 scope. It did not pass `--execute-model`, created no run
output and reported:

```text
period: 2024-01-01 through 2026-08-20
scope policy: binary_named_generation_pre_model_guard_v4
source snapshot: 1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf
extraction config: 4b54b89dbfe8640e
canonical documents: 19489
compatible existing attempts: 0
deterministic pending: 14452
model required: 5037
conflicts: 0
model planned: 0
Gemini calls: 0
BOE calls: 0
```

Result: **DRY RUN PASSED**. The temporary scope file was removed; no
operational run artifact was created or modified.

## 26. Final run naming

Proposed run root, not yet created:

`runs/final-tfm-p2-20240101-20260820-v1/`

Conceptual paths are `extraction-main/` for the non-holdout attempt snapshot,
`extraction/` for the cumulative full-P2 extraction, then `silver/` and
`downstream/`. Source remains a direct reference to the validated source v2;
copying approximately 1 GB would add no identity or safety guarantee.

## 27. Future extraction command

The CLI exposes `--documents`, `--output-dir`, optional repeatable `--scope`,
optional `--attempts`, `--manual-reviews`, `--execute-model`, required
`--expected-extraction-config-id`, and `--dry-run`. It has inclusion scopes but
no exclusion flag. Therefore the commands below are exact in syntax but **not
executable until the named deterministic scope artifacts exist and bounded
cumulative resume mitigation has been validated**.

Main extraction:

```bash
DO NOT RUN UNTIL HUMAN AUTHORIZATION
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction-main \
  --scope runs/final-tfm-p2-20240101-20260820-v1/scopes/main-p2-v1.csv \
  --execute-model \
  --expected-extraction-config-id 4b54b89dbfe8640e
```

Holdout and cumulative final extraction:

```bash
DO NOT RUN UNTIL HUMAN AUTHORIZATION
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m renewables_permitting.pipeline extract \
  --documents runs/final-corpus-preflight-20220101-20260820-v2/source \
  --output-dir runs/final-tfm-p2-20240101-20260820-v1/extraction \
  --attempts runs/final-tfm-p2-20240101-20260820-v1/extraction-main \
  --scope runs/final-tfm-p2-20240101-20260820-v1/scopes/p2-all-v1.csv \
  --execute-model \
  --expected-extraction-config-id 4b54b89dbfe8640e
```

With a complete main snapshot and validated scopes, the second call would
reuse 4,989 main documents and call only the 48 selected holdout documents,
then publish one full-P2 extraction snapshot. Smaller cumulative scopes are
still required to make the main run interruption-safe.

## 28. Human approval package

```text
FINAL TFM PERIOD: 2024-01-01 through 2026-08-20 inclusive
FALLBACK: 2025-01-01 through 2026-08-20 only if delivery is materially threatened
SOURCE SNAPSHOT: 1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf
SCOPE POLICY: binary_named_generation_pre_model_guard_v4
EXTRACTION CONFIG: 4b54b89dbfe8640e
PROVIDER: gemini, Gemini Developer API
MODEL: google:gemini-2.5-flash
CANONICAL DOCUMENTS: 19,489
DETERMINISTIC: 14,452
MODEL_REQUIRED: 5,037
HOLDOUT OBJECTIVE: AI extraction quality on unseen BOE documents
HOLDOUT UNIT: BOE document
HOLDOUT DESIGN: H1, MODEL_REQUIRED and development-unexposed
HOLDOUT SIZE: 30 minimum / 48 preferred / 72 maximum
HOLDOUT SEED: 20260821
HOLDOUT EXECUTION: Option A, after freeze; one subsequent cumulative full-P2 snapshot
CORRECTIONS: 5/5 inside P2 and source-compatible; revalidate after extraction
RESUME: PARTIALLY SUPPORTED; no automatic in-flight recovery
CHUNKING: cumulative scoped rebuild supported; bounded plan/tooling still required
INTERRUPTION RISK: HIGH — BLOCKER BEFORE GEMINI
CONCURRENCY: sequential, 1, not configurable
MODEL RETRIES: agent=3; at most 6 requests/document; one outer transient retry
HISTORICAL TOKEN EVIDENCE: PARTIAL; 123 model documents and 138 requests
EXPECTED INPUT TOKENS: 65,015,539, retry-adjusted mean
EXPECTED OUTPUT/THINKING TOKENS: 16,495,215, retry-adjusted mean
EXPECTED MODEL REQUESTS: about 5,651, including about 614 extra requests
OFFICIAL PRICING: USD 0.30/M input; USD 2.50/M output including thinking
EXPECTED COST: USD 60.74
CONSERVATIVE COST: USD 121.87
OPERATOR BUDGET CAP: USD 157.00
DISK RISK: LOW
EXTRACTION COMMAND: specified above but not executable until required artifacts/mitigation exist
GEMINI: NOT AUTHORIZED
```

## 29. Recommendation

The source, policy, extraction identity, funnel, exposure provenance,
corrections, token projection, pricing and disk checks pass. The holdout
strategy is reproducible but still requires its versioned selection artifact.

The current long-run persistence design can delete normal-interruption
checkpoints and has no automatic recovery of hard-kill staging. A late failure
can therefore repeat thousands of paid calls. Before human authorization:

1. create and review the deterministic versioned H1 selection artifact;
2. generate and validate deterministic P2, main and bounded cumulative scope
   artifacts without inspecting model outputs;
3. validate a cumulative `--attempts` continuation runbook/tool that limits
   the maximum paid work lost in one failed stage;
4. repeat the dry-run for those exact scopes and obtain explicit human approval.

**BLOCKER: in-flight resume/interruption safety for the 5,037-document model
workload.**

**REQUIRED residual: versioned holdout selection, bounded cumulative scopes,
validated continuation procedure and human review.**

**FINAL EXTRACTION PREFLIGHT P2 REVEALS RESUME BLOCKER**
