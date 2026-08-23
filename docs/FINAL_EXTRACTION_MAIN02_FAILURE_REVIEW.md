# Final Extraction main-02 Failure Review

## 1. Purpose

This REQUIRED, read-only review classifies the nine blocking rows published by
`main-02` before any decision about `main-03`. It separates one operational
timeout from eight reproducible deterministic failures, measures equivalent
exposure in the versioned P2 scopes and defines the smallest demonstrated
next actions.

This review did not call Gemini, BOE, another model, the web or any external
service. It did not execute a retry, `main-03`, the holdout, Silver, downstream
or Gold; modify code, tests, configuration, source or `runs/`; or create a
manual review.

## 2. Snapshot

The pre-check passed on branch `tfm-final` at
`91ea3070a8cd1823de78802c9ed5323fd39ad931`: local `HEAD` equalled
`origin/tfm-final`, the working tree was clean and `git diff --check` passed.

The contractual loader accepted:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-02
```

| Contractual measure | Result |
| --- | ---: |
| Documents accounted | 500 |
| Current extractions | 490 |
| Inherited human rejections | 1 |
| Blocking reviews | 9 |
| Attempt rows | 751 |
| Unique `attempt_id` | 751 |
| Duplicate `attempt_id` | 0 |
| Inherited `main-01` attempts | 501/501 preserved |
| New `main-02` attempts | 250 |
| New successful attempts | 241 |
| New failed attempts | 9 |

The 501-attempt history of `extraction-main-01-final-v2` is an exact subset of
the cumulative attempt log. Its 249 current selections, one human rejection
and two versioned manual-review rows remain present and unchanged.

| Lineage | Value |
| --- | --- |
| Source identity | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| Scope | `config/evaluation/final_p2_execution_scopes_v1/main-02.csv` |
| Scope policy | `binary_named_generation_pre_model_guard_v4` |
| Extraction config ID | `4b54b89dbfe8640e` |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| Document-validation version | `25` |

The 250 new attempts persisted 288 requests, 2,587,487 input tokens and
992,818 output/thinking tokens. At the approved budget basis of USD 0.30/M
input and USD 2.50/M output, including thinking, `main-02` cost USD
3.2582911. The cumulative `main-01` + `main-02` persisted cost is USD
5.9656419. These are local accounting estimates, not provider invoices.

## 3. Review queue

The queue and latest attempts independently reconstruct exactly one
`OPERATIONAL / TimeoutError`, eight
`DOCUMENT_EXTRACTION_VALIDATION / DocumentExtractionValidationError`, zero
`CANONICALIZATION_VALIDATION` and zero `OTHER` cases.

| BOE | Attempt ID | Error type / stage | Exact reason | Output | Requests | Input | Output/thinking |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| `BOE-A-2025-7777` | `3c73cf35a9aa4b098a361a803548acbd` | `TimeoutError` / `agent_run` | Two model-run timeouts exhausted; no provider message persisted | No | 2 | 27,368 | 131,040 |
| `BOE-B-2024-22754` | `b2bbb642d8db4a2aaa524b34406756a2` | `DocumentExtractionValidationError` / `document_validation` | Missing title action `informacion_publica` | Yes | 2 | 9,768 | 24,846 |
| `BOE-B-2024-3263` | `cf3afa1238704019bbb447066b7876e4` | `DocumentExtractionValidationError` / `document_validation` | Missing title action `informacion_publica` | Yes | 2 | 9,564 | 7,551 |
| `BOE-B-2024-41261` | `bc571dad83184dd8884e38a0df70d753` | `DocumentExtractionValidationError` / `document_validation` | Missing title action `informacion_publica` | Yes | 2 | 14,772 | 7,594 |
| `BOE-B-2024-43565` | `b5f097f6ff004e5cad0ce235e5d11157` | `DocumentExtractionValidationError` / `document_validation` | Possible false-negative scope | Yes | 2 | 6,826 | 2,719 |
| `BOE-B-2024-9915` | `e83e2babded84ef9a87e0c272073614f` | `DocumentExtractionValidationError` / `document_validation` | Asset name lacks generation context | Yes | 2 | 7,864 | 21,565 |
| `BOE-B-2025-7992` | `c77adc89d99f4bb588409d8a4eb19834` | `DocumentExtractionValidationError` / `document_validation` | Possible false-negative scope | Yes | 2 | 10,764 | 3,190 |
| `BOE-B-2026-18178` | `84160e63bc33424cb3915e2b564394ae` | `DocumentExtractionValidationError` / `document_validation` | Missing title action `informacion_publica` | Yes | 2 | 8,472 | 8,673 |
| `BOE-B-2026-441` | `ca66809a32ed4bd6bca3eb5b161b0d9a` | `DocumentExtractionValidationError` / `document_validation` | Possible false-negative scope | Yes | 2 | 6,932 | 2,619 |

All eight semantic rows retain both the precanonical and canonical structured
output. The timeout retains neither.

## 4. Operational timeout

`BOE-A-2025-7777` failed in `agent_run` after 482.026251 seconds. The policy
allows two transient model runs of at most 240 seconds each, separated by a
two-second backoff, within the 600-second document budget. The elapsed time,
two recorded requests and empty error message are therefore consistent with
two exhausted model-run timeouts rather than a document-budget timeout. No
structured response was persisted.

The attempt retains source SHA-256
`f78c2762c33914c3c68de0f62720f3c99071d689635c5cf5fb3e44ca4f4ca03f`,
the active config, contract and instructions identities, and its token usage.
It is compatible with the cumulative snapshot.

Disposition: **`RETRY_OPERATIONAL`**, subject to a separate explicit human
authorization. The existing repeatable `--retry-error-boe` path is suitable:
an offline `extract --dry-run` over the `main-01` + `main-02` scopes selected
exactly this BOE, reported 499 compatible existing documents, one pending
model-required retry and zero model calls planned. It printed
`DRY RUN: no model/network/write execution performed` and did not create its
output path. A correctly authorized retry would append one new attempt and
would repeat model calls for zero of the 499 already resolved documents.

## 5. Information-publication failures

All four sources explicitly publish a public-information procedure. In every
case the structured output already represents that procedure through the more
specific contractual action
`declaracion_utilidad_publica / sometido_informacion_publica`.

| BOE | Publication and minimal title/source evidence | Persisted relevant output | Validator result | Classification | Offline replay |
| --- | --- | --- | --- | --- | --- |
| `BOE-B-2024-22754` | Regional energy announcement: “se somete a información pública la solicitud de reconocimiento de utilidad pública”; shared evacuation infrastructure serves Arañuelo A-D | Four events, each with `declaracion_utilidad_publica / sometido_informacion_publica` | Demands generic `informacion_publica` | **B — CANONICALIZATION BUG** | YES |
| `BOE-B-2024-3263` | Regional energy announcement: “se somete a información pública ... declaración en concreto de utilidad pública” for FV Killington | Precanonical output has the specific and generic actions; canonical output correctly retains only the specific submitted action | Demands the generic action again | **B — CANONICALIZATION BUG** | YES |
| `BOE-B-2024-41261` | Regional energy announcement: “se somete a información pública la solicitud de declaración en concreto de utilidad pública” for FV Tan Energy 3 | `declaracion_utilidad_publica / sometido_informacion_publica` | Demands generic `informacion_publica` | **B — CANONICALIZATION BUG** | YES |
| `BOE-B-2026-18178` | Regional energy announcement: “se somete al trámite de información pública la solicitud de declaración, en concreto de utilidad pública”; shared evacuation serves Ronda 1-5 | Five canonical events, each with the specific submitted action | Demands generic `informacion_publica` | **B — CANONICALIZATION BUG** | YES |

The shared title parser recognizes only narrower punctuation forms of
`declaración/reconocimiento ... de utilidad pública`. These four legitimate
variants are consequently parsed as generic `informacion_publica`. The
canonicalizer then correctly removes a generic action as redundant when the
specific action already has decision `sometido_informacion_publica`; the
document validator reuses the incomplete title classification and demands the
discarded generic action. The rejection is therefore model-shape-dependent
and semantically incorrect.

An in-memory punctuation-tolerant extension of the existing public-utility
title pattern made all four persisted outputs pass, preserving respectively
4, 1, 1 and 5 publication events. No new model information or human domain
decision is needed. The required action is **`PATCH_CANONICALIZATION`**, with
positive and negative title regressions and cumulative offline
recanonicalization afterward.

## 6. Scope/context failures

The three models all returned `not_relevant_for_generation_projects` with no
events. The sources support those outputs; the current high-precision guard
mistakes generation vocabulary in the title for a named generation project.

| BOE | Source describes a generation project | Model treats as generation | Validator accepts context | Demonstrated family | Classification | Blind retry |
| --- | --- | --- | --- | --- | --- | --- |
| `BOE-B-2024-43565` | **NO** — procurement correction for a photovoltaic system supplying the Alicante I desalination plant | NO | NO | Auxiliary generation / procurement | **SCOPE/CONTEXT BUG** | NO |
| `BOE-B-2025-7992` | **NO** — prior-occupation acts concern a named replacement of a medium-voltage overhead-line segment | NO | NO | Standalone evacuation/grid infrastructure | **SCOPE/CONTEXT BUG** | NO |
| `BOE-B-2026-441` | **NO** — generic correction to a second grant call covering plural wind installations and small hydro plants; no named project | NO | NO | Generic programme/correction | **SCOPE/CONTEXT BUG** | NO |

None belongs to the already corrected hybrid-photovoltaic or bounded
generation-table families. The first is the known auxiliary-generation
domain family, the second is evacuation/grid infrastructure rather than a
generation root, and the third lacks the named plant required by the contract.

High-precision, BOE-independent in-memory guards for these three exact
contexts made all three persisted non-relevant outputs pass with zero events.
The required action is **`PATCH_SCOPE_CONTEXT`**, not a model retry or a
relaxation of the named-project domain rule.

## 7. Naming/evidence failure

`BOE-B-2024-9915` concerns an evacuation line to the Arguineguín substation.
The source expressly says that it enables evacuation for “varias instalaciones
de generación de energía renovable (PSF Agueda I, Agueda II, Agueda III,
Agueda IV)”. It later mentions `PSF Agueda II` and `PSF Agueda IV` in the
evacuation description.

The model identified four photovoltaic generation roots and kept the line as
an associated evacuation component; it did **not** promote the infrastructure
to project root. Its `names_raw`, however, expanded the shared `PSF` prefix to
all four names. `PSF Agueda III` and `PSF Agueda IV` are not literal in the
bounded list, so current canonicalization drops them. `PSF Agueda II` survives
because it occurs later, but the validator does not propagate the explicit
generation context of the bounded list to that later full-name mention and
rejects event 2.

Disposition: **VALIDATOR TOO STRICT at the final symptom, with a safer
`PATCH_CANONICALIZATION` treatment**. The validator should remain strict about
literal names. Canonicalization can instead recognize the bounded
generation-list grammar, retain the literal first item and remove only a
demonstrably shared prefix from subsequent items (`Agueda II`, `Agueda III`,
`Agueda IV`). An in-memory simulation produced four literal generation assets,
four events and passed the current validator. Source support is partial for the
model's exact strings but complete for the four underlying plants; no Gemini
retry or human domain decision is needed.

## 8. Offline replay

The eight semantic attempts were replayed from local source and persisted
precanonical JSON through the current canonicalizer and document validator.
The baseline result was **0 PASS / 8 FAIL**, reproducing exactly four missing
`informacion_publica` errors, three false-negative scope errors and one
generation-name-context error.

The three general in-memory simulations described above then produced **8
PASS / 0 FAIL**. They used no BOE identifier special cases and did not modify
the snapshot:

1. punctuation-tolerant public-utility title recognition;
2. high-precision non-project context for auxiliary supply, a line-replacement
   object and a generic grant-call correction;
3. literal normalization of repeated prefixes in one bounded generation list.

The hypothetical rules were also replayed over the 248 automatically selected
`main-01` precanonical outputs; the one manual selection was preserved and
validated directly. All **249 current selections passed**, the human rejection
remained one and the blocking queue remained zero. Seven automatic results
had a deterministic before/after difference, all within the demonstrated
public-utility title family. No scope or naming-list exposure occurred in
`main-01`.

This proves feasibility and count preservation; it does not replace regression
tests, review of semantic diffs or publication of a fresh cumulative snapshot.

## 9. Systemic risk

Counts below use accent-insensitive exact lexical patterns over the versioned
P2 source and scopes. The development count uses the 140-document frozen
development source. The holdout was not inspected. Lexical exposure is not a
claim that every row must become a generation extraction.

| Exact demonstrated pattern | Development | `main-01` | `main-02` | `main-03..20` | Examples / probable impact | Risk |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Public-information title with a public-utility punctuation variant parsed only as generic | 1 | 1 | 4 | **41** | `BOE-B-2024-3156` passed only with a different model action shape; remaining examples include `BOE-B-2024-4999`, `BOE-B-2025-42797` and `BOE-B-2024-3383`; up to 41 future lexical exposures | **HIGH** |
| Photovoltaic system for complementary/auxiliary supply | 0 | 0 | 1 | 1 | `BOE-B-2025-11172` in `main-20` | MEDIUM |
| Generation wording whose named object is a line-segment replacement | 0 | 0 | 1 | 1 | `BOE-B-2024-31060` in `main-03` | MEDIUM |
| Generic repowering grant-call correction without a named plant | 0 | 0 | 1 | 0 | Only the current blocker | LOW |
| Bounded generation list with one shared `PSF` prefix and four items | 0 | 0 | 1 | 0 | Only the current blocker | LOW |

The development utility exposure is `BOE-B-2022-41006`, whose main object is a
transport line rather than a generation project. The one `main-01` exposure is
`BOE-B-2024-3156`; it passed because its model shape retained both a specific
and a generic action. This confirms that current success depends on model
shape rather than a stable semantic rule.

The public-utility parser defect is the highest systemic risk: 46 exact P2
exposures comprise 1 in `main-01`, 4 already blocking in `main-02` and 41 in
unexecuted main scopes. `main-03` must remain blocked until the deterministic
patch is implemented, tested and replayed.

## 10. Per-BOE disposition

| BOE | Error type | Root cause | Source supports output | Validator correct | Offline fix possible | Model retry needed | Human decision needed | Code patch needed | Systemic risk | Recommended action | Blocks `main-03` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `BOE-A-2025-7777` | `TimeoutError` | Two 240-second model-run timeouts | N/A | N/A | NO | YES | NO | NO | LOW | `RETRY_OPERATIONAL` | YES |
| `BOE-B-2024-22754` | Document validation | Public-utility punctuation variant parsed as generic information | YES | NO | YES | NO | NO | YES | HIGH | `PATCH_CANONICALIZATION` | YES |
| `BOE-B-2024-3263` | Document validation | Same parser/deduplication contradiction | YES | NO | YES | NO | NO | YES | HIGH | `PATCH_CANONICALIZATION` | YES |
| `BOE-B-2024-41261` | Document validation | Same parser/deduplication contradiction | YES | NO | YES | NO | NO | YES | HIGH | `PATCH_CANONICALIZATION` | YES |
| `BOE-B-2026-18178` | Document validation | Same parser/deduplication contradiction | YES | NO | YES | NO | NO | YES | HIGH | `PATCH_CANONICALIZATION` | YES |
| `BOE-B-2024-43565` | Document validation | Auxiliary supply/procurement mistaken for a generation root | YES | NO | YES | NO | NO | YES | MEDIUM | `PATCH_SCOPE_CONTEXT` | YES |
| `BOE-B-2025-7992` | Document validation | Named line replacement mistaken for a generation root | YES | NO | YES | NO | NO | YES | MEDIUM | `PATCH_SCOPE_CONTEXT` | YES |
| `BOE-B-2026-441` | Document validation | Generic programme mistaken for a named project | YES | NO | YES | NO | NO | YES | LOW | `PATCH_SCOPE_CONTEXT` | YES |
| `BOE-B-2024-9915` | Document validation | Shared-prefix list not normalized; bounded generation context is lost | PARTIAL | PARTIAL | YES | NO | NO | YES | LOW | `PATCH_CANONICALIZATION` | YES |

Totals: eight semantic cases are fixable offline; one future operational retry
is recommended; one case would require a new Gemini attempt; zero cases require
a human extraction/domain decision; eight BOEs require deterministic code
treatment grouped into **three cohesive patch families**.

## 11. Main-03 gate

```text
MAIN-03 BLOCKED BY SYSTEMIC CODE BUG
```

The unresolved `main-02` queue alone prevents cumulative continuation. In
addition, the public-utility parser defect has 41 exact exposures in remaining
main scopes, including `main-03`. Continuing would knowingly reproduce a
model-shape-dependent deterministic failure.

## 12. Required next action

Human disposition should authorize or reject the following bounded sequence:

1. implement and test the three demonstrated patch families without changing
   the Pydantic contract, instructions or extraction identity;
2. replay all eight persisted semantic outputs and the full `main-01` baseline
   offline, and inspect every semantic diff;
3. recanonicalize the complete eligible cumulative history into a fresh
   snapshot with zero model usage;
4. separately authorize exactly one `--retry-error-boe BOE-A-2025-7777`
   operational attempt, preserving its failed predecessor;
5. publish and loader-validate a new cumulative `main-02` snapshot with 500
   documents accounted and zero blockers;
6. obtain human review before considering `main-03`.

`main-03` remains **NOT AUTHORIZED** and the holdout remains **NOT EXECUTED**.
No current blocker should be converted into a manual correction merely to
avoid a general deterministic fix.

Recommendation:

```text
MAIN-02 FAILURE REVIEW REVEALS SYSTEMIC CODE BLOCKER
```
