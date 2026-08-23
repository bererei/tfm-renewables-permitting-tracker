# Final P2 main-02 deterministic blocker fix

This report records the bounded offline correction and cumulative replay of the
eight deterministic blockers found in `main-02`. No BOE, Gemini, other model,
Silver, downstream, Gold, `main-03` or holdout execution was performed.

## 1. Identity gate

The three scope/context cases were classified as **B — scope policy semantics
changed; new config required** if implemented in the pre-model guard. The
`scope_classification_policy` is part of the extraction configuration payload,
so changing historical source eligibility there would require a new identity.

The correction therefore leaves the pre-model guard and configuration payload
unchanged. A narrow post-model validator exception accepts an already produced
non-relevant result only for the three audited non-project contexts. It does
not invent another model output or turn infrastructure into a generation root.

| Identity | Before | After |
| --- | --- | --- |
| Scope policy | `binary_named_generation_pre_model_guard_v4` | `binary_named_generation_pre_model_guard_v4` |
| Extraction config ID | `4b54b89dbfe8640e` | `4b54b89dbfe8640e` |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` | same |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` | same |

The deterministic implementation fingerprint is
`945d895322bb662c841394f46311288c2765cc168195bf18586435b927dab406`;
recanonicalization materialization version remains `2`.

## 2. Utility-public parser

The title parser previously recognized only a subset of punctuation around
`declaración/reconocimiento ... de utilidad pública`. It could consequently
demand a generic public-information action after canonicalization had correctly
retained the more specific DUP submitted to public information.

The parser now accepts the demonstrated plain, comma and `en concreto`
variants. Existing precedence still produces one specific DUP action, keeps
`sometido_informacion_publica` for a current publication and does not republish
a historical act mentioned by a correction.

| BOE | Offline result | Events |
| --- | --- | ---: |
| `BOE-B-2024-22754` | PASS | 4 |
| `BOE-B-2024-3263` | PASS | 1 |
| `BOE-B-2024-41261` | PASS | 1 |
| `BOE-B-2026-18178` | PASS | 5 |

## 3. Shared-prefix handling

Canonicalization now recognizes only the bounded grammar
`instalaciones de generación de energía renovable (PSF X, Y, ...)`. A `PSF`
prefix is removed from a subsequent model name only when its literal unprefixed
form is an item in those same parentheses. The validator then recognizes that
literal item's local generation context.

The rule does not propagate to another paragraph, an item outside the list or
a generic infrastructure list. `BOE-B-2024-9915` now passes with four events
and the literal names `PSF Agueda I`, `Agueda II`, `Agueda III` and
`Agueda IV`.

## 4. Out-of-scope handling

The post-model exception is restricted to three source-title combinations:

- an auxiliary photovoltaic system for complementary IDAM/desalination supply;
- a named line-segment replacement embedded in generation wording;
- a generic repowering programme for plural wind installations and small
  hydro plants.

The persisted non-relevant outputs for `BOE-B-2024-43565`,
`BOE-B-2025-7992` and `BOE-B-2026-441` all pass with zero events. Contrasts
with a genuinely named generation plant remain rejected as possible false
negatives. Generation roots therefore remain generation plants only.

## 5. Tests

The initial focused RED run produced eight failures and four passing negative
controls. After the patch, all 12 new cases pass. The regressions cover the
four utility variants, prior valid/negative/historical cases, the bounded-list
positive and three non-propagation cases, and an out-of-scope plus named-plant
contrast for each context family.

Affected focal suites pass:

```text
canonicalization + validation                         222 passed
active recanonicalization                              22 passed
pipeline + config + review + review I/O + runner      298 passed
total focal                                            542 passed
full repository suite                                1,135 passed
```

The recanonicalization test fixture also received a deterministic source
timestamp. Its previous use of wall-clock time became later than its fixed
replay instant during 23 August and made queue precedence time-dependent; no
production behavior changed.

## 6. Offline replay

Replay used the versioned local source, persisted precanonical model outputs
and the corrected deterministic code. All eight `main-02` semantic blockers
were resolved offline: five became valid project-specific selections and three
became valid non-relevant selections. Cases requiring Gemini: **0**.

The complete cumulative plan found 499 root outputs: 498 replayed
successfully and one existing human rejection resolved the remaining replay
failure. Relative to those root outputs, 474 were semantically unchanged and
24 changed. Twelve historical failed roots were recovered: nine
project-specific and three non-relevant. The 24 changes are confined to the
already approved utility-public/canonical evidence rules and the bounded-list
fix; no new change family or newly invalid output appeared.

Relative to the prior cumulative current selection, the new snapshot adds
exactly the eight corrected BOEs, removes none, and changes 14 existing
selections only within the utility-public canonicalization family.

## 7. Main-01 regression

The immutable `extraction-main-01-final-v2` was loader-validated again and was
not modified:

```text
documents = 250
current extractions = 249
human rejected = 1
blocking reviews = 0
attempts = unique attempt IDs = 501
```

## 8. Future-scope impact

The exact installed logic was evaluated offline over the 4,489 documents in
`main-03` through `main-20`; the holdout was not inspected.

| Pattern | Future lexical exposures |
| --- | ---: |
| Utility-public parser delta | 168 |
| Of those, explicit public-information procedures | 110 |
| Audited post-model non-project contexts | 4 |
| Bounded shared `PSF` prefix list | 0 |

The previous exploratory estimate of 41 utility and two scope exposures was
therefore conservative. The fresh count uses all versioned remaining scopes
and the exact production matchers; two equivalent generic grant calls account
for the additional scope cases.

## 9. New main-02 snapshot

The source snapshot remains unchanged. The offline materialization was
published atomically at:

```text
runs/final-tfm-p2-20240101-20260820-v1/
extraction-main-02-recanonicalized
```

Its snapshot identity is
`63008cfd34c584f1bb774b9740c0b2b08343ce102f88f834695476512663b4dc`.
The loader confirms 500 documents, 498 current extractions, one inherited human
rejection, one blocking review, 1,249 attempt rows, 1,249 unique attempt IDs
and zero duplicate IDs. The manifest records zero added model requests and
zero added input/output tokens.

## 10. Remaining timeout

The only blocking review is `BOE-A-2025-7777` with its historical
`TimeoutError`. It was not retried. An explicit retry dry-run selected exactly
one document, required one model document, planned zero calls, selected zero
prior successes and selected none of the eight semantic cases.

Status: **1 OPERATIONAL RETRY PENDING — NOT AUTHORIZED**.

## 11. Main-03 gate

A read-only continuation dry-run is contractually planifiable: it accounts for
750 scoped documents, reuses all previous 500 without a model call and leaves
only the 250 `main-03` documents as new model-required work. It planned zero
calls. `main-03` remains **NOT AUTHORIZED**, and the holdout remains
**NOT EXECUTED**.
