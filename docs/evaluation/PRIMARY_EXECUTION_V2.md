# Durable primary execution of the frozen V2 holdout

Classification: **P0 / REQUIRED**. Objective: preserve the first documentary
execution, including terminal errors, without silently repeating an initiated
document. This is an operational controller, not part of the system evaluated.
Model execution, real predictions, real evaluation, production changes,
scoring changes, commits and deployment are outside the implementation block.

## Verified frozen boundaries

The implementation started from clean `tfm-evaluation` at
`a0cbe5f2f59b5eb48f34684d7f6b3c94273477ff`, equal to the local
`origin/tfm-evaluation` reference. No fetch is required or performed.

| Boundary | Identity |
| --- | --- |
| System `tfm-final` | `282de815bea4e248bdcba2c655e3ee078cb58a49` |
| Extraction config | `4b54b89dbfe8640e` |
| Truth `runs/final_holdout_p2_v1_truth_v2_frozen` | `e3f300253db94931345e9bbbc489cd810802f94339c3b6a0d751f98b32383b54` |
| Truth manifest SHA-256 | `4f32dc8f89fff8ae1b80f7fb5f94e9168d131f4dea3d0d025640e869c07c148c` |
| Evaluator `runs/final_holdout_p2_v1_evaluator_v2_frozen` | `956213df2a1669814f82491809d776998346d9e54cb1fdc8d9a5434e8dd26f77` |
| Evaluator manifest SHA-256 | `6d7193d555445d7514b918a31fc30ea57b905e0382912870add2da075c1fdd55` |
| Selection SHA-256 | `4e71f86cbaf23ba2d26c97fbd5a65b2acb0ccc7cd41616b626ec603f4f4fab4a` |
| Complete source identity | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| Selected 48-document identity | `c22187d73cfae19c078b29171bb5f757906a9a9ff9c1bea40e220d3738c2d2de` |
| `uv.lock` SHA-256 | `af47371305913f4913c05a73448a8be92f44fbceb3f604b491d629cc80639229` |

The controller lives under `evaluation/primary_execution/`. Adding files to
`evaluation/final_holdout_v2/` would change the existing evaluator declaration,
which recursively hashes that package. Its sibling location preserves both
frozen evaluation packages and production. The controller records its own Git
commit and Python-file hashes independently.

## Why a document is the execution unit

The frozen `runner.extract_documents` initializes `RunUsage`, document timeout,
validation retry count, prompt, payload and adjustments inside its document
loop. Each `agent.run` starts without inherited message history. The agent holds
configuration and a provider client, not a conversation across BOEs. Rebuilding
the client changes connection lifetime, not the per-document procedure.
The global `debug_state` retains last-document diagnostics only; production
never reads it as input for a subsequent document. Synthetic fixtures restore
that diagnostic after each test to preserve the existing import-boundary test.

The controller invokes the unchanged production CLI `main` with a single-BOE
scope in a separate process using the system worktree's own Python. The order
is the same stable ascending BOE order. Configuration, agent/transient/document
retries, native output, six-request usage limit, 600/240-second budgets, text
selection, prompt, validation and canonicalization are unchanged. Checkpoint
frequency remains five: the existing last-document flush handles a one-document
scope. UUID attempt IDs and wall-clock times are operational metadata; each
actual ID is preserved in aggregation. Event/action IDs remain document-local.

The proof uses three invented documents with a fake agent, including a terminal
error and an automatic transient retry. Batch and individual processing must
produce identical prompts, settings, limits, document-local usage behavior,
payloads and primary results after normalizing only timestamps/durations and
using controlled synthetic UUIDs. This does not assert identical Gemini replies.

## Durable states and interruption recovery

`journal.jsonl` is append-only, with sequence numbers, UTC timestamps, run ID,
previous-entry hash and entry hash. Appends are flushed and fsynced. A separately
atomically replaced `journal.head.json` records the committed tail, detecting
truncation to an earlier complete line. An incomplete line or inconsistent head
fails closed; it is never silently repaired or interpreted as pending work.

An advisory POSIX `flock` permits one cooperating writer. The child inherits
the lock descriptor, so parent death does not authorize another controller
while that child still runs. This is local-filesystem coordination, not a
distributed lease or protection against external manual edits. `primary-status`
opens files read-only; during an active append an inconsistent read fails closed
and can be repeated after the append completes.

| State | Meaning and continuation |
| --- | --- |
| `PENDING` | No durable start; eligible for execution. An empty/prepared job directory is recoverable if it contains no execution output. |
| `STARTED` | Durable start recorded and an active writer still owns the run. |
| `TERMINAL_SUCCESS` | Valid productive success and completion receipt; never execute again. |
| `TERMINAL_ERROR` | Valid productive error and completion receipt; never execute again. |
| `INDETERMINATE` | Started without a verifiable terminal receipt after the writer ended; stop and require a later explicit human decision. |

`RUN_PREPARED`, `RUN_INVOKED`, `DOCUMENT_STARTED`, `DOCUMENT_COMPLETED`,
`DOCUMENT_ERROR`, `RUN_INTERRUPTED`, `INCIDENT`, `RUN_EXECUTION_COMPLETED` and
`RUN_FINALIZED` retain operational history. The controller has no failed-BOE
retry option and never maps an indeterminate document back to pending.

| Interruption point | Recovery |
| --- | --- |
| Before `DOCUMENT_STARTED` | Still pending; a later invocation may start it. |
| Immediately after start / during worker | Indeterminate if no completion receipt exists; no retry. |
| Product returned but receipt not published | Preserve remaining files/logs for diagnosis; indeterminate. Do not invent the lost outcome. |
| Durable completion before terminal journal event | Verify every file/hash and recover the terminal event without a model call. |
| After N completed documents | Preserve/skip all N; only genuinely pending documents may continue. |
| During offline aggregation | Original document outputs survive. A new offline staging attempt is safe; no model work is involved. |
| After primary snapshot publication | Verify and finish the remaining seal; do not rebuild or overwrite that snapshot. |
| After final record/provenance publication | Verify and append the missing final journal event; do not change the freeze timestamp. |

A normal Ctrl-C stops the worker process group and records an interruption when
the parent can do so. SIGKILL/power loss cannot guarantee an interruption event;
the already durable start plus absence of receipt still prevents repetition.
Filesystem corruption or a torn journal requires human diagnosis, not automatic
recovery. Durable publication assumes the local filesystem honors fsync/rename.

## Layout and aggregation

```text
final-holdout-v2-primary-001/
  metadata.json
  .writer.lock
  journal.jsonl
  journal.head.json
  scopes/001.csv ...
  documents/001-BOE-.../
    job.json
    stdout.log / stderr.log
    launcher.stdout.log / launcher.stderr.log
    process.json
    extraction/                       # unchanged eight-file production snapshot
    completion.json                   # atomic durable document receipt
  primary/
    job.json / process.json / completion.json
    stdout.log / stderr.log / launcher.*.log
    extraction/                       # final eight-file primary snapshot
  finalization/
    execution_record.json
    provenance.json
    manifest.json
```

Document logs sit outside the staging directory cleaned by production. The
worker fsyncs the completed files and atomically publishes its receipt. A
snapshot without that receipt is not sufficient to infer a completed process.

Finalization requires exactly 48 terminal documents, including every terminal
error. It reads the registered parents in deterministic order, validates them
with the frozen production loader, combines attempts using
`combine_ai_extraction_attempt_frames`, and calls `run_extraction_stage` with
those attempts and `execute_model=False`. No Parquets are manually concatenated,
no attempt is replaced, and no payload is recanonicalized. The standard eight
production files are validated by the unmodified V2-B loader/primary guards.

The public `extraction-union` operation has an additional blocking-review gate;
it would reject the required terminal-error case. The controller therefore
reuses the lower-level combination helper and standard offline `extract`
publication, without changing either production policy or prediction format.

The queue is regenerated by frozen production; its wall-clock `queued_at` is
operational. A separate relational `primary_semantic_identity` excludes only
that queue timestamp. The native V2 snapshot ID continues to include physical
artifact hashes; it is not substituted or modified. Physical journal/log/file
hashes may bind absolute operational paths; semantic data identities do not
include controller paths.

The valid aggregate snapshot is published first. Only afterward is
`primary_predictions_frozen_at_utc` captured and the closed execution record and
provenance published atomically under `finalization/`. The final manifest binds
both directories. Until this seal exists, the aggregate is not a completed
primary experiment. The final journal event references the seal. Provenance
binds the journal prefix immediately before that final event, avoiding a
circular hash dependency. Existing publications are verified, never overwritten.

## Usage and execution record

The V1-compatible record retains its closed 21-field schema. `model_usage` is the
sum of the original reported usage columns, without estimates or repairs.
The closure audit counted 21 top-level `properties` and 21 `required` entries in
`evaluation/final_holdout_v1/execution_record.schema.json`. The required set in
V1 `validate_execution_record`, directly reused by V2 `predictions.py`, contains
exactly those same 21 names. The earlier preflight's count of 22 was a reporting
error, not a schema migration or a missing field. The schema is unchanged.
`document_executions_started` is a separate journal-derived number, never a
count of HTTP calls. Incidents and per-document exit codes are separate again.
Internal retries are exclusively production behavior; no provider internals are
instrumented. An unsuccessful HTTP invocation can be absent from reported usage.

**PRE-GEMINI BLOCKER, confirmed by the closure audit:**
`evaluation/final_holdout_v2/evaluator.py`, function `evaluate`, rejects when
`record["model_usage"]["requests"] < int(snapshot.attempts["attempt_origin"].eq("model").sum())`.
It compares reported usage against all model-origin documentary attempts,
including terminal errors. V1 `evaluate` contains the analogous condition, but
V2 does not call that function: V2 owns the guard diagnosed here.

The locked `pydantic-ai-slim==1.107.0` increments `RunUsage.requests` after its
non-streaming model request returns. A propagated error before that response
does not reach the increment. The locked Google adapter (`google-genai==2.8.0`)
can raise `ModelHTTPError`; the unchanged product applies two total transient
run attempts to a 503. If both fail before returning a response, the runner
preserves one `attempt_origin=model`, `extraction_status=error` record with zero
reported requests. Agent retries and document-validation retries do not
guarantee a response or repair that counter.

Minimal counterexample: one such model-origin error and zero requests triggers
`0 < 1`. The closure diagnostic additionally ran the unchanged controller and
runner on the existing three-document synthetic fixture, using a local
PydanticAI `FunctionModel` that raises 503 twice for one document. Two synthetic
successes plus that terminal error yielded two reported requests and three
model-origin attempts. The actual V2 `evaluate` rejected with
`Fewer recorded model requests than model-origin attempts.` before reaching
scoring or publishing a report. Network was blocked and all inputs/outputs were
temporary synthetic artifacts.

Consequently, a valid 48-document run with 47 single-response model successes
and one zero-usage error would be preserved and finalized, but rejected before
evaluation (`47 < 48`). Additional reported retries elsewhere can mask that
inequality; the existence of an error alone does not imply rejection.
The same `evaluate` also requires the evaluator freeze timestamp to precede
primary extraction. Fixing and refreezing only after that run would therefore
fail the existing temporal gate as well; the correction must precede Gemini.
Provenance's `frozen_evaluator_usage_guard_satisfied` exposes the current guard
without changing usage, discarding errors or repeating documents.

Proposed minimal correction, **not implemented**: apply the lower bound only
to attempts where `attempt_origin == "model"` and `extraction_status == "ok"`.
Successful model attempts return a response and reach the usage increment;
terminal errors may legitimately report zero. Preserve all existing integer,
non-negativity, token-consistency and primary-lineage checks. Add regression
coverage for zero-usage terminal errors and zero-usage successes, then review
and commit the evaluator fix separately and publish a new evaluator freeze
before Gemini. Matching, scoring, denominators, metrics, truth, temporal rules
and P0 remain outside that correction. No evaluator code or real freeze is
changed by this diagnostic block.

The record references and hashes the separate provenance in
`incident_retry_notes`. Provenance contains the verified system/environment,
controller commit/hash, freeze identities, source/selection identities, actual
run invocations, finalization argv, timestamps, journal prefix, every document
receipt/snapshot identity and observed incidents. Relative log references in the
execution record are relative to the run root; per-document logs are linked
through provenance. Exit code zero means the controller completed its logical
execution, including possible terminal extraction errors; each production
subprocess's actual code (including review-required code 4) is preserved.

## Future commands — not authorization to execute

First: human review → approved controller commit/push → separately approved
usage-guard fix/commit and new evaluator freeze → separately prepare and
verify the detached system worktree and its own locked `.venv` → make the API key
available. No real worktree or primary run is created by implementation tests.
The preparation example below records the currently verified evaluator pins.
After the separate fix/freeze, replace its evaluator path, identity and manifest
expectation with the newly verified values before preparing a real run.

Run these commands from the committed evaluation repository. Supply the actual
worktree location explicitly; preparation checks detached HEAD, cleanliness,
lock hash, offline `uv sync --check --locked`, Python 3.10 and productive module
origins through the worktree's own Python with `-I -B`. `PYTHONPATH` must be unset.
The worker checks its Git checkout again before each document.

```bash
REPO=/home/bgonzale/CiDaeN/15_TrabajoFinMaster/tfm-renewables-permitting-tracker
SYSTEM_ROOT=/tmp/tfm-final-282de815
RUN_ROOT="$REPO/runs/final-holdout-v2-primary-001"
cd "$REPO"

env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m evaluation.primary_execution.cli prepare-primary-run \
  --system-root "$SYSTEM_ROOT" \
  --truth "$REPO/runs/final_holdout_p2_v1_truth_v2_frozen" \
  --evaluator "$REPO/runs/final_holdout_p2_v1_evaluator_v2_frozen" \
  --source "$REPO/runs/final-corpus-preflight-20220101-20260820-v2/source" \
  --run-root "$RUN_ROOT" \
  --expected-system-commit 282de815bea4e248bdcba2c655e3ee078cb58a49 \
  --expected-config-id 4b54b89dbfe8640e \
  --expected-truth-id e3f300253db94931345e9bbbc489cd810802f94339c3b6a0d751f98b32383b54 \
  --expected-truth-manifest 4f32dc8f89fff8ae1b80f7fb5f94e9168d131f4dea3d0d025640e869c07c148c \
  --expected-evaluator-id 956213df2a1669814f82491809d776998346d9e54cb1fdc8d9a5434e8dd26f77 \
  --expected-evaluator-manifest 6d7193d555445d7514b918a31fc30ea57b905e0382912870add2da075c1fdd55

env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m evaluation.primary_execution.cli primary-status --run-root "$RUN_ROOT"
```

Review the materialized preflight before authorizing `run-primary`. Preparation
does not need a key and never calls a model. The execution command requires
`GOOGLE_API_KEY` or its productive alternative `GEMINI_API_KEY` before the first
document start. The key is inherited by the worker, never included in argv,
metadata or journal. Use the existing secret-entry procedure in USER_GUIDE.
Neither preparation nor execution automatically loads `.env`. The repository's
ignored `.env` declares `GOOGLE_API_KEY`; the closure audit checked names only,
not its value, and neither supported key was present in the process environment.
The detached worktree does not inherit the main checkout's ignored `.env` file.
An explicit `uv --env-file` launch from the evaluation checkout makes the key
available in process memory and the worker inherits it even with its own cwd
and interpreter. No key file needs copying into the worktree:

```bash
# Future launch, ONLY after the evaluator fix/freeze and primary authorization:
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
uv run --offline --no-sync --no-python-downloads --env-file "$REPO/.env" \
  "$REPO/.venv/bin/python" -m evaluation.primary_execution.cli run-primary \
  --run-root "$RUN_ROOT"
```

This launch procedure passed a temporary fake-key check of `require_api_key`
and `child_environment` inheritance (exit 0), without loading the real `.env`,
constructing a provider or making an authentication request. Do not print or
capture the environment; the command contains the file path, never the secret.

```bash
# ONLY AFTER explicit authorization of the materialized preflight:
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m evaluation.primary_execution.cli run-primary --run-root "$RUN_ROOT"

# Same command for a safe continuation; it skips all terminal documents.
# Any INDETERMINATE document blocks the complete continuation.

# Offline, after every document is terminal:
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m evaluation.primary_execution.cli finalize-primary --run-root "$RUN_ROOT"
```

The later evaluator inputs are `$RUN_ROOT/primary/extraction` and
`$RUN_ROOT/finalization/execution_record.json`, with the existing truth/evaluator
pins. `finalize-primary` never invokes scoring. Validation/evaluation remains a
separate gate, using the commands in USER_GUIDE and the V2-B runbook.

## Verification and documentation impact

Tests use invented BOE-2099 documents, fake agents, temporary repositories and
temporary outputs. They exercise journal corruption, all requested interruption
windows, source/system gates, terminal errors, resume, deterministic content,
publication recovery, unchanged usage, original payloads and V2-B acceptance.
All pytest commands used the existing local interpreter and cached pytest,
without installing dependencies or accessing the network:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/home/bgonzale/.cache/uv/archive-v0/uKyO9ltGZAXoEVCV/lib/python3.10/site-packages:.:src \
.venv/bin/python -m pytest <SCOPE> -q -p no:cacheprovider
```

That `PYTHONPATH` supplies the test runner only; synthetic controller fixtures
clear it, and the public controller rejects it for real execution.

| Scope / check | Actual result |
| --- | --- |
| `tests/evaluation/test_primary_execution.py`, successive development runs | 45 passed / 97.83 s; 69 passed / 125.00 s; 75 passed / 145.66 s; 77 passed / 152.20 s |
| Same file, `-k final`, after two finalization regressions were added | 6 passed, 73 deselected / 34.96 s |
| `tests/evaluation --ignore=tests/evaluation/test_primary_execution.py` | 343 passed / 219.33 s |
| `tests/test_pipeline.py tests/extraction` | 986 passed / 146.18 s |
| Complete repository suite in the initial implementation block (empty scope), exactly one invocation | **1 failed, 1,772 passed / 682.47 s** |
| `tests/evaluation/test_primary_execution.py tests/extraction/test_runner.py::test_runner_import_surface_has_no_agent_or_top_level_execution`, after fixture isolation fix | **80 passed / 154.82 s** |
| Complete repository suite, one new invocation explicitly authorized by the closure request, after the fixture fix | **1,773 passed / 661.26 s (0:11:01), exit 0** |
| Local FunctionModel 503 diagnostic through the unchanged runner/controller and actual V2 evaluator | Valid synthetic primary: 2 successes + 1 terminal error, 2 reported requests / 3 model attempts; expected usage rejection before scoring, no report published |
| `uv run --offline --no-sync --no-python-downloads --env-file <temporary fake env>` launch check | Exit 0; API-key presence gate and worker environment inheritance pass; real `.env` not loaded |
| Public CLI `--help` for preparation, run, status and finalization | All four exit 0; no real preparation/run |
| `git diff --check` and whitespace checks on new files | Pass |
| Read-only truth/evaluator loaders and before/after SHA-256 inventories | Expected identities pass; all 26 protected files and inventories unchanged |
| `git diff --exit-code tfm-final -- src config pyproject.toml uv.lock` and diff of V1/V2 packages against HEAD | Empty; frozen executable boundaries unchanged |

The sole complete-suite failure was
`tests/extraction/test_runner.py::test_runner_import_surface_has_no_agent_or_top_level_execution`:
synthetic controller fixtures left the frozen runner's `debug_state` populated.
The fixture now restores that global using `monkeypatch`; no controller or
production behavior changed after the complete run. The initial implementation
block did not rerun the complete suite, respecting its single-invocation limit.
The ordered
controller-plus-import-regression run passes all 80 tests, verifying the fixture
correction separately. The later closure request explicitly authorized one new
complete suite from that corrected state: **1,773 passed in 661.26 s**, exit 0.
No controller, production, evaluator or test code changed in this closure;
only the affected documentation was updated. Acceptance is **READY FOR CONTROLLER
COMMIT**, with human authorization still required. Gemini remains blocked by
the separately diagnosed evaluator usage guard; its proposed fix is not
implemented and no real evaluator is refrozen here.

Documentation impact: new operational CLI, run layout, continuation/finalization
and actual evaluator-freeze status. Documents reviewed: AGENTS, TFM_CLOSEOUT,
USER_GUIDE, V1/V2 evaluation contracts, V2_B_EVALUATOR, the execution-record schema
and template, and FINAL_EXTRACTION_EXECUTION_PLAN_P2. Documents updated: this
procedure, TFM_CLOSEOUT, USER_GUIDE and the V2-B runbook. Reason: make the durable
primary protocol reviewable without changing any frozen executable boundary.
The closure update additionally records the post-fix full-suite result, corrects
the earlier field-count report, documents explicit `.env` loading and promotes
the demonstrated usage incompatibility to a pre-Gemini blocker.
