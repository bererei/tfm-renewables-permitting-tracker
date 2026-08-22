# Final Extraction main-01 Blocker Fix

## 1. Scope and status

This REQUIRED change addresses only the four deterministic defect families
confirmed in `docs/FINAL_EXTRACTION_MAIN01_FAILURE_REVIEW.md` and adds a
bounded explicit retry path for historical error attempts. It does not alter
the extraction model, instructions, scope v4 or source data. It did not call
Gemini or BOE services, execute either operational retry, run `main-02`, or
write any snapshot under `runs/`.

Status: **IMPLEMENTED + TESTED — PENDING HUMAN REVIEW**.

The active identities remain:

| Identity | Value |
| --- | --- |
| Extraction config ID | `4b54b89dbfe8640e` |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |

## 2. Deterministic corrections

| Defect | Minimal correction | Guardrails |
| --- | --- | --- |
| `infraestructura híbrida fotovoltaica` rejected as a generation root | The document validator accepts that exact phrase when it shares a literal span with the asset name. | Evacuation infrastructure and generic or ambiguous photovoltaic infrastructure remain rejected. |
| Generation context in a table heading did not reach its rows | The validator parses only a local three-column `DENOMINACIÓN` / `EXPEDIENTE` / `PROMOTOR` table preceded by the demonstrated independent-generation context. | Context ends when the triplet structure ends; generic infrastructure tables and later document text receive no generation context. |
| `reconocimiento, en concreto, de utilidad pública` parsed as generic public information | The existing public-utility title pattern now recognizes that exact established wording. | Existing `declaración ... de utilidad pública` behavior remains; non-utility recognition does not match. |
| Correction decision overwritten by quoted public-information wording | Error-correction semantics are evaluated before the generic public-information decision. The narrowly recognized noun forms are `corrección/rectificación de error(es)`. | Ordinary public-information announcements remain unchanged and unrelated uses of `rectificación` do not become error corrections. |

No Pydantic contract change was required. The invalid pair
`correccion_errores / sometido_informacion_publica` was produced only by the
old canonicalizer; the contract correctly rejects it.

## 3. RED regressions and focal verification

The new regression tests were run before the production patch. The selected
set produced **14 expected failures and 8 passes**: the positive deterministic
cases and retry interface were red, while the negative guards already held.
After the patch the same selected set produced **24 passed**.

The broader affected offline suite covered canonicalization, document
validation, review, attempt I/O, runner finalization and pipeline orchestration:

```text
495 passed in 27.86s
```

The complete offline repository suite then produced:

```text
1111 passed in 104.89s (0:01:44)
```

The retry regressions prove explicit selection, immutable error history,
current success selection, preservation of an unselected error, rejection of
a success, incompatible config/contract/instructions, source drift, corrupt
structured history, duplicate historical IDs and a duplicate new attempt ID.
The CLI dry-run test proves that planning performs no publication.

## 4. Offline replay of persisted main-01 outputs

The replay read the immutable `main-01` attempts and documents, selected the
persisted precanonical output when available, and applied the patched
canonicalization and document validation in memory. No model response was
regenerated.

| BOE | Result | Deterministic conclusion |
| --- | --- | --- |
| `BOE-A-2026-14482` | **PASS** | The named 45.25 MWp hybrid photovoltaic infrastructure is accepted; the separate evacuation infrastructure remains a component. |
| `BOE-B-2024-29516` | **PASS** | All nine independent generation installations are accepted from their bounded table rows. |
| `BOE-B-2025-39508` | **PASS** | The output remains the single specific action `declaracion_utilidad_publica / sometido_informacion_publica`; no artificial generic action is needed. |
| `BOE-B-2024-46241` | **FAIL, different reason** | Correction precedence is fixed, then the documentary validator correctly rejects `CIBELES CENTRO-SUR`: the source describes a geothermal-resource mining research permit, not a named electricity-generation plant. |
| `BOE-B-2026-4032` | **PASS, human temporal decision pending** | The correction stays `rectificado`; the remaining actions are contract-valid, but their current-versus-historical interpretation is not decided here. |

Across the whole local `main-01` attempt log, 248 of 250 attempts contain a
structured output. The patched offline replay yields **247 PASS and 1 FAIL**.
All **243 prior successes still pass**. Five structured results have a semantic
before/after difference, including three prior successes; every difference is
inside the expected public-utility or correction family. There are **zero
unexpected affected outputs**.

The two attempts without structured output remain the operational `ReadError`
and `TimeoutError`; deterministic replay cannot and must not fabricate them.

## 5. P2 systemic impact audit

The versioned union of `main-01` through `main-20` contains 4,989 documents.
The following counts come from a fresh offline before/after analysis of that
exact union:

| Family | P2 exposure/change | `main-01` | `main-02` | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Correction plus public-information precedence | 50 decisions | 2 | 3 | Every corrected decision is now `rectificado`. |
| Utility-recognition title-type change | 46 type sets | 4 | 3 | All changes add the specific public-utility type; no unrelated type set changes. |
| Exact hybrid photovoltaic phrase | 8 lexical exposures | 1 | 0 | Validation changes only when a compatible structured output uses the demonstrated root. |
| Demonstrated shared-generation table layout | 6 documents | 1 | 0 | All six use the same local independent-generation heading and structured rows. |

The fresh direct comparison supersedes the exploratory counts in the failure
review where they differ. The earlier search under-counted utility title-set
changes and equivalent copies of the demonstrated table layout. This does not
introduce another semantic family: inspection confirmed the same exact wording
and table structure, and the 248-output replay found no unexpected changes.

## 6. Explicit operational retry tooling

`pipeline extract` now accepts a repeatable `--retry-error-boe <BOE_ID>` in
addition to the existing cumulative `--attempts` input. There is deliberately
no retry-all mode. Normal unattempted documents keep their established
continuation behavior; historical failures are still inert unless named.

Before agent construction, the planner requires each selected BOE to be in the
active scope and to have a latest unresolved error attempt. Existing resume
validation rejects source, config, contract, instructions, provider/model and
validation-version mismatches, invalid fields, corrupt structured JSON and
duplicate historical attempt IDs. A successful, unattempted, manually
resolved, uncertain or out-of-scope BOE cannot be selected as an error retry.

Execution writes only to a fresh staging directory. It must append exactly one
fresh attempt per execution document, with no ID collision. The historical
error must remain present before the new cumulative snapshot can be published.
The existing latest-attempt and manual-precedence rules then select the current
result. A failed retry therefore remains visible; a successful retry becomes
current without overwriting its failed predecessor.

No retry was executed in this change. The only later retry candidates already
identified for possible human authorization remain:

- `BOE-A-2025-19878` — `ReadError`;
- `BOE-B-2024-30150` — `TimeoutError`.

## 7. Identity assessment

These changes are bug fixes within the semantics already named by the active
canonicalization and documentary-match policies. They restore consistency
between exact source evidence, action parsing, current-publication correction
semantics and the existing contract. They do not introduce a new action,
decision, model field, prompt rule, scope policy or validation identity.

Consequently, `EXTRACTION_CONFIG_ID`, the contract SHA and instructions SHA do
not change. The 243 paid model outputs remain reusable. Their precanonical
lineage is sufficient for offline recanonicalization and revalidation; no
Gemini repetition is needed for any deterministic defect.

## 8. Pending human decision for BOE-B-2026-4032

The minimum evidence is:

- the title identifies an **“Anuncio de corrección de errores”** and quotes the
  earlier operation: **“por el que se somete a información pública la solicitud
  de Modificación de Autorización Administrativa Previa, Modificación de
  Autorización Administrativa de Construcción y Declaración, en concreto, de
  Utilidad Pública”**;
- the body states the concrete publication change: **“Se incluye la titularidad
  de las parcelas recogidas en la Relación de Bienes y Derechos Afectados
  publicada y se incluyen parcelas que, por error, no se publicaron”**;
- the replayed output contains the current correction plus public information,
  one deduplicated authorization-modification action and the public-utility
  request.

Human review must decide whether this publication event represents only the
parcel-list correction or also republishes the quoted public-information and
application actions as current. No historical action was automatically removed
and no manual correction was created.

## 9. Gate

`main-02` remains **NOT AUTHORIZED**. The next sequence is:

1. human review of this patch and identity assessment;
2. human disposition of `BOE-B-2024-46241`;
3. human temporal decision for `BOE-B-2026-4032`;
4. separate explicit authorization, if approved, for the two operational
   retries;
5. publication and review of a new cumulative `main-01` snapshot;
6. only then reconsider the `main-02` gate.
