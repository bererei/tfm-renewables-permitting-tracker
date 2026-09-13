# V2-B evaluator — implementation and freeze procedure

Classification: **P0 / REQUIRED**. Objective: make the final extraction
evaluation reproducible and reviewable before prediction exposure. Production,
truth annotation, V1 scoring, downstream data, product features and model
execution are outside this block. Methodology is defined in
[`FINAL_HOLDOUT_EVALUATION_CONTRACT_V2.md`](FINAL_HOLDOUT_EVALUATION_CONTRACT_V2.md),
sections 11–12, and `evaluation/final_holdout_v2/scoring_rules.json`.

Implementation started on a clean `tfm-evaluation` checkout at
`0f4de38ec0899606747730c11c75fdacc6bf3b8e`, equal to the local
`origin/tfm-evaluation` tracking ref. `tfm-final` remains
`282de815bea4e248bdcba2c655e3ee078cb58a49`. No remote fetch, prediction contents,
model execution or real evaluator publication is needed for implementation.

## Reviewed production/V1 semantics

| Reference | Explicit V2 decision |
| --- | --- |
| V1 `matching.normalize_name` | Reuse actual normalization, including preserved word order; document the inaccurate historical docstring |
| V1 `matching.deterministic_match` | Reuse forced maximum-cardinality matching and excluded-only component handling; never choose a tie |
| V1 literal evidence functions | Reuse any-fragment candidate and all-fragment support; restrict scored action anchoring to accepted passages of that owner |
| V1 event matching | Require complete sets on both sides; extra unmatched predicted assets cannot disappear |
| V1 action detection | Replace historical-inclusive positives with current-only positives; historical contamination is one FP per matched historical prediction |
| Production `BOEProjectExtraction`, `PublicationEvent`, `AdministrativeAction` | Read existing explicit scope and local event/asset/action structure; preserve missing scored fields; no temporal output field exists |
| Production `gold._action_project_attributions` | Use event expansion, direct assets and explicit component links; unit is local generation asset, not a later grouped project |
| V1 prediction loader/primary guards and execution record | Reuse pinned frozen-system/lineage checks, adding duplicate identity, canonical source, document manifest, artifact counts and original-queue identity checks |
| V1 publication | Reuse the pattern of new destination, sibling staging and hashes; V1 has no independent evaluator-freeze command, so V2 supplies that boundary |

There is no compatibility issue requiring a new production projection. A known
component with no explicit generation link yields no project attribution in
Gold. V2 preserves that empty projection and exposes the missing link; it never
infers a parent. Pair scoring counts actual projected assets only, while
exact-set scoring cannot pass with unresolved targets.

`contract.json` and the truth ID algorithm remain unchanged because the real
frozen truth binds that exact annotation declaration. The separate V2-B rules
declaration supersedes the historical annotation-stage evaluator status without
resealing truth.

## Modules and artifact boundaries

- `predictions.py`: read-only adapter and provenance checks; no canonicalisation,
  correction application, extractor or model calls.
- `scoring.py`: candidate graphs, assignments, scoped metrics inputs, effective
  assets, P0 and audit tables; pure computation.
- `metrics.py`: common micro counts, ratios and null-denominator convention.
- `artifacts.py`: hash, inventory and single-writer publication primitives.
- `evaluator_freeze.py`: evaluator identity, truth binding, freeze and verification.
- `evaluator.py`: public frozen-input boundary, execution validation, Parquet
  round trips, report publication and independent report integrity verification.
- `cli.py`: existing annotation/truth commands plus evaluator operations.

Internal pure scoring helpers are for deterministic tests and computation.
The public `evaluate` API/CLI requires the verified evaluator artifact and its
bound frozen truth; a working truth is rejected. Synthetic fixtures exercise
the same publication interface with invented BOE-2099 documents and computed
source hashes. No fixture is derived from final predictions.

## Ordered human gates

Evaluator review/commit and the separate real freeze have since completed.
The controller implementation preflight verified `tfm-evaluation` at
`a0cbe5f2f59b5eb48f34684d7f6b3c94273477ff`, and the actual artifact is
`runs/final_holdout_p2_v1_evaluator_v2_frozen`, created
`2026-09-13T11:17:43.423742+00:00`. Its evaluator identity is
`956213df2a1669814f82491809d776998346d9e54cb1fdc8d9a5434e8dd26f77`
and manifest SHA-256 is
`6d7193d555445d7514b918a31fc30ea57b905e0382912870add2da075c1fdd55`.
Its truth binding is the verified V2 truth/manifest identity documented in the
primary procedure. Do not reseal or overwrite either artifact.

The closure audit identified a **PRE-GEMINI BLOCKER** in this evaluator's
`evaluate` usage guard: it counts terminal model-origin errors toward a minimum
request count that PydanticAI does not guarantee. A local synthetic 503 sequence
reproduces a valid primary record rejected before scoring. The proposed bounded
correction is to count only successful model-origin attempts in that lower bound;
no matching, scoring, metric, truth, temporal or P0 rule changes. This is a
diagnosis only; evaluator code and the frozen artifact remain unchanged. See
the usage section of [PRIMARY_EXECUTION_V2.md](PRIMARY_EXECUTION_V2.md).

The remaining sequence is controller review → approved controller commit/push
→ separately approved usage-guard fix/commit and a new evaluator freeze
→ verified detached productive environment → API key → prepared-run review
→ separately authorized primary execution. The controller remains outside this
frozen package; see [PRIMARY_EXECUTION_V2.md](PRIMARY_EXECUTION_V2.md).
Preserve all primary errors and original outputs before any human semantic
intervention. Additional attempts cannot replace the first execution.
The commands below verify the existing artifact. After the approved fix/freeze,
use the new evaluator path/identity/manifest for real preparation and evaluation;
never overwrite the current freeze or reseal it after inspecting predictions.

```bash
UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m evaluation.final_holdout_v2.cli validate-evaluator \
  --evaluator runs/final_holdout_p2_v1_evaluator_v2_frozen \
  --expected-evaluator-identity 956213df2a1669814f82491809d776998346d9e54cb1fdc8d9a5434e8dd26f77 \
  --expected-manifest-sha256 6d7193d555445d7514b918a31fc30ea57b905e0382912870add2da075c1fdd55
```

The evaluator identity covers relative Python/JSON/CSV files under both isolated
evaluation packages, production Python/resource code, `evaluation/__init__.py`,
`pyproject.toml` and `uv.lock`. It binds the V1 code that is reused, not V1
scoring results. No `runs/`, paths, timestamps or metrics enter this identity.
Documentation and test-only edits do not reseal executable behavior. Archive the
committed checkout alongside the evaluator artifact; hashes do not embed an
executable copy of the source repository. External manifest hashes pin creation
time and truth binding as well as the semantic evaluator identity.

## Future offline evaluation, after separately authorized primary execution

Populate the unchanged
`evaluation/final_holdout_v1/execution_record.template.json` according to its
adjacent schema. `record_version=final_holdout_execution_record_v1` is an
execution provenance version; V2 evaluation still uses only V2 truth/scoring.
The record captures the **actual** argv, timestamps, status, model usage, run ID,
source/selection/snapshot identities and log paths. The external primary
controller now produces this record at `finalization/execution_record.json`
and the snapshot at `primary/extraction/`. It never calls this evaluator.

```bash
UV_OFFLINE=1 uv run python -m evaluation.final_holdout_v2.cli \
  validate-execution-record --record <ACTUAL_EXECUTION_RECORD_JSON>

UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
uv run python -m evaluation.final_holdout_v2.cli evaluate \
  --truth runs/final_holdout_p2_v1_truth_v2_frozen \
  --evaluator runs/final_holdout_p2_v1_evaluator_v2_frozen \
  --expected-evaluator-identity 956213df2a1669814f82491809d776998346d9e54cb1fdc8d9a5434e8dd26f77 \
  --expected-evaluator-manifest-sha256 6d7193d555445d7514b918a31fc30ea57b905e0382912870add2da075c1fdd55 \
  --predictions <FROZEN_PRIMARY_EXTRACTION_DIRECTORY> \
  --execution-record <ACTUAL_EXECUTION_RECORD_JSON> \
  --output <NEW_V2_EVALUATION_DIRECTORY>

UV_OFFLINE=1 uv run python -m evaluation.final_holdout_v2.cli \
  validate-evaluation --evaluation <V2_EVALUATION_DIRECTORY> \
  --expected-manifest-sha256 <RECORDED_REPORT_MANIFEST_SHA256>
```

The report contains the summary, twelve typed tables, three copied provenance
documents and its manifest (17 files). Entity/action/pair outcomes, candidate
graphs, missing values, exclusions, ambiguous matches, unresolved targets and
unadjudicated P0 warnings remain available for analysis. The evidence support
rate is conditional documentary support. Pair metrics and exact-set accuracy
have different units/denominators. Neither is a global system accuracy.

## Validation scope

Run focused V2-B tests, `tests/evaluation`,
`tests/extraction/test_historical_antecedents.py`, then one final full repository
suite, using the documented offline pytest environment. Tests cover the
requested entity/action/location errors, ambiguity, temporal/P0 confusion,
effective targets against Gold, complete event sets, missing fields, provenance,
freeze/report corruption, no-overwrite/partial publication and row-order
invariance. Exact results of the closing verification belong in the closeout
checkpoint and implementation handoff; these are software-test results, not
holdout performance metrics.

### Closing execution record — 2026-09-13

The existing offline environment supplies Python from `.venv` and pytest from
the already cached distribution; no dependency or lockfile was changed. The
actual common command prefix was:

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/home/bgonzale/.cache/uv/archive-v0/uKyO9ltGZAXoEVCV/lib/python3.10/site-packages:.:src \
.venv/bin/python -m pytest <SCOPE> -q -p no:cacheprovider
```

| Scope / execution | Actual result |
| --- | --- |
| `tests/evaluation/test_scoring_v2b.py`, first development batch | 69 passed, 10.19 s |
| `tests/evaluation/test_evaluator_v2b.py`, first development batch | 65 passed, 59.68 s |
| Both files together after extending coverage | **153 passed, 82.34 s** |
| `tests/evaluation` | **343 passed, 217.31 s** |
| `tests/extraction/test_historical_antecedents.py` | **15 passed, 8.49 s** |
| Empty scope: one final full repository run | **1,694 passed, 547.32 s** |

The V2 CLI top-level and `evaluate --help` commands were run with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:src .venv/bin/python -m evaluation.final_holdout_v2.cli`.
Synthetic CLI tests exercise freeze/verify, execution-record validation,
evaluate and report verification. No command above executes a real evaluator
freeze or holdout evaluation.

Diagnostic checks: `git branch --show-current`,
`git rev-parse HEAD origin/tfm-evaluation tfm-final`, `git status --short`,
`git diff --stat`, `git diff --name-status`, `git diff --check`, and
`git diff --exit-code tfm-final -- src config pyproject.toml uv.lock streamlit_app.py`.
The diff excludes production, V1, annotation contracts, notebooks and real data.
The 24 files in the working/frozen truth inventories remain byte-identical;
the final frozen loader verifies the approved truth ID, manifest hash and 48
documents. These are integrity/test facts, not system-performance results.

Documentation impact: new evaluation CLI, frozen evaluator/report boundaries,
matching/scoring rules and a completed real truth-freeze status require updates.
Documents reviewed: `AGENTS.md`, `docs/TFM_CLOSEOUT.md`, `docs/USER_GUIDE.md`,
V1 and V2 evaluation contracts, and the V1 execution-record schema/template.
Documents updated: this implementation/runbook record, the V2 evaluation
contract, `docs/USER_GUIDE.md` and `docs/TFM_CLOSEOUT.md`.
Reason: publish the methodology and actual validation evidence before model
execution, preserving the immutable annotation declaration and V1 history.
