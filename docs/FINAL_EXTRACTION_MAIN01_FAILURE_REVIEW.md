# Final Extraction main-01 Failure Review

## 1. Purpose

This report records an offline, read-only triage of the seven blocking review
cases published by the contractual `main-01` extraction snapshot. It separates
transient operational failures from model-output errors and deterministic code
defects. It does not resolve any queue item, authorize a retry, change the
extraction contract or authorize `main-02`.

Evidence was limited to the local source snapshot, persisted extraction
artifacts, active package code, contracts, validators, tests and frozen
development outputs. No Gemini or BOE calls were made. No response is inferred
where the run did not persist one.

## 2. Snapshot

The contractual loader accepted:

```text
runs/final-tfm-p2-20240101-20260820-v1/extraction-main-01/
```

The manifest and all declared artifacts are valid.

| Property | Value |
| --- | --- |
| attempts | 250 |
| current extractions | 243 |
| review queue | 7 |
| blocking review | 7 |
| document identity | `05dce41c3e646bff95b663fbb97a2580aee1603c0ab342e1c0f3e1c0e23a93d6` |
| extraction config | `4b54b89dbfe8640e` |
| instructions | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| contract | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| source policy | `binary_named_generation_pre_model_guard_v4` |
| model | `gemini` / `google:gemini-2.5-flash` |
| persisted usage | 286 requests; 2,391,308 input tokens; 776,142 output/thinking tokens |
| persisted usage cost estimate | USD 2.6577474; USD 2.6577 rounded |

The estimate applies the already documented paid rates of USD 0.30/M input
tokens and USD 2.50/M output tokens, including thinking. It is not a provider
invoice.

## 3. Review queue

All seven rows are `pending` and `blocking`. No manual review is present.

| BOE | Reason | Stage | Error | Attempt | Source document SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `BOE-A-2025-19878` | `extraction_error` | `agent_run` | `ReadError` | `3d0cac28af8d403bb5dbe0c109871989` | `364369e40afed6e1239cedda31717d3e47a0815db77aef341473acad4bd2d298` |
| `BOE-B-2024-30150` | `extraction_error` | `agent_run` | `TimeoutError` | `f359443003e543ac851870fa0863c355` | `c5fb0cac8dbad69db5cfca82bee6499fc05b30897f881aa25601a8f243367dd3` |
| `BOE-A-2026-14482` | `document_validation_failed` | `document_validation` | `DocumentExtractionValidationError` | `6525426ed18c4cd190f345452893c5a9` | `741d6bfcad3217f464af97600a89bf0659c78706167754ef1216005424792668` |
| `BOE-B-2024-29516` | `document_validation_failed` | `document_validation` | `DocumentExtractionValidationError` | `56e311ba3a5743e987d79c8a25979cd6` | `5e7dbe8a5133b7daf53075c418ec7781bb7ba370f39b997d44f9b2908f93ed44` |
| `BOE-B-2025-39508` | `document_validation_failed` | `document_validation` | `DocumentExtractionValidationError` | `9087bd70900749d0a370fd0aa4f5c18e` | `25a398504a264ca2272d6e927dee5d2173f0ffa92161329a971812654a806834` |
| `BOE-B-2024-46241` | `extraction_error` | `canonicalization` | `ValidationError` | `cde570883d314230af0ff882e4eb070b` | `90b169731a8785085653e0537aa7bf9fbd14e32947f2ed032d6f0b4f6e1f4035` |
| `BOE-B-2026-4032` | `extraction_error` | `canonicalization` | `ValidationError` | `ae5811ffa7ce49c9bf454d7c49f31f34` | `d98640db183f25b28ac94cd739edcf494bb87d7be34c4dce5338511a143265ec` |

## 4. Operational failures

### BOE-A-2025-19878 — `ReadError`

- The runner built the full-text prompt and entered `agent_run`.
- The persisted error message is empty. The record does not preserve an
  exception namespace or transport trace beyond `ReadError`.
- Duration was 0.032127 seconds. Persisted usage is zero requests and zero
  tokens. There is no pre-canonical extraction, parsed extraction or persisted
  response.
- `agent.run()` was invoked, but the local record cannot prove whether the
  provider accepted a request. It only proves that no response or usage was
  durably recorded.
- The pipeline transient wrapper consumed one of its two possible attempts. A
  statusless `ReadError` is not recognized by `_is_retryable_model_error()`, so
  it was raised immediately. No pipeline-level transient retry occurred.
- Source, config, instructions and contract identities match the snapshot.

This is an operational transport/read failure independent of document
semantics. Primary classification: **A. RETRY OPERATIONAL**. Execution
classification: **REQUIRES TOOLING**. A later explicit retry is semantically
safe only after the human authorizes it and a cumulative retry path exists.

### BOE-B-2024-30150 — `TimeoutError`

- The runner entered `agent_run`; duration was 482.184487 seconds.
- `MODEL_RUN_TIMEOUT_SECONDS` is 240 seconds,
  `TRANSIENT_RUN_ATTEMPTS` is 2 and the backoff is 2 seconds. The observed
  duration is consistent with exactly two exhausted 240-second model-run
  attempts plus the bounded backoff and local overhead.
- The 600-second document timeout was still active and was not itself
  exhausted. The failure came from the nested model-run timeout policy.
- Persisted usage is zero requests and zero tokens. No partial response,
  pre-canonical extraction or parsed extraction is persisted. The record cannot
  prove whether either timed-out provider operation was accepted remotely.
- Source, config, instructions and contract identities match the snapshot.

This is an operational timeout independent of a persisted semantic output.
Primary classification: **A. RETRY OPERATIONAL**. Execution classification:
**REQUIRES TOOLING**. The run exhausted exactly the configured pipeline-level
transient policy.

### Explicit retry procedure

The productive CLI does not currently support an explicit retry of a failed
attempt:

- `build_extraction_plan()` schedules only queue rows whose reason is
  `source_not_attempted`;
- an existing `error` attempt is counted as compatible and remains blocking;
- `--scope` restricts the documents but does not turn an attempted error back
  into an unattempted document;
- omitting `--attempts` could produce an isolated new snapshot, but no
  productive command then appends that new attempt to the complete immutable
  history and republishes a cumulative snapshot;
- `recanonicalize` cannot call the model and is not a retry mechanism.

Classification: **EXPLICIT RETRY REQUIRES SMALL TOOLING**. The minimum future
tool must accept an explicit BOE allowlist, require matching source/config
identity, append new attempts without deleting the failures, and publish a new
cumulative snapshot. It must not mutate `main-01`.

## 5. Document validation failures

### BOE-A-2026-14482

The final persisted structured output identifies `Rincón del Cabello` as a
45.25 MWp photovoltaic generation asset and records
`correccion_errores / rectificado` plus the title-derived
`terminacion_procedimiento / desistido`.

The source states:

> infraestructura híbrida fotovoltaica «Rincón del Cabello», de 45,25 MWp, y
> su infraestructura de evacuación

The separate reference to “su infraestructura de evacuación” makes the first
named, rated photovoltaic infrastructure the generation root, not the
evacuation component. The final output is supported.

`_generation_name_has_documentary_context()` rejects the name because
`_GENERATION_DESCRIPTOR_PATTERN` recognizes `planta`, `parque`, `central`,
`instalación` and `proyecto`, but not the explicit expression
`infraestructura híbrida fotovoltaica`. The error is:

```text
publication_events[1].generation_asset_1: la fuente no identifica la
denominación como planta de generación.
```

Classification: **VALIDATION BUG / CONTRACT REVIEW**. The contract already
represents the asset; no contract extension is required. Recommended action:
**PATCH_VALIDATOR** with a narrow, evidence-backed generation expression that
does not turn evacuation infrastructure into a root. A blind model retry is
**NO**: one document-validation retry was already allowed, and different model
wording cannot repair the validator's lexical gap.

### BOE-B-2024-29516

The output creates nine separate events for nine named photovoltaic
installations. Each event associates the shared LSMT as a component and targets
the granted authorizations and utility declaration to that component. This is
consistent with the rule that independent generation projects remain separate
while shared evacuation infrastructure may be linked to them.

The source states, in continuous local passages separated here by `[...]`:

> La infraestructura de evacuación denominada LSMT "SOL DEL HELIÓPOLIS & SOL
> DE TARSIS -ENTRENÚCLEOS" de 15 kV, es compartida por varias instalaciones de
> generación, que son objeto de proyecto y tramitación independiente. Se
> detalla en la tabla adjunta: [...] HSF SOL DEL HELIÓPOLIS [...] HSF SOL DE
> TARSIS [...] HSF ALCALÁ DE GUADAIRA 1 [...] HSF ALCALÁ DE GUADAIRA 11 [...]
> HSF ALCALÁ DE GUADAIRA 111 [...] HSF ALCALÁ IV [...] HSFALCALÁV [...] HSF
> ENTRENUCLEOS TEN [...] HSF ENTRENUCLEOS 5

All nine literal names are therefore identified by the source as independent
generation installations. The validator nevertheless emits the same generation
context error for events 1 through 9. `_find_literal_span()` tests one
punctuation/newline-delimited source unit at a time; the shared table heading
and each name occupy different units, so the table relationship is lost.

Classification: **VALIDATION BUG / CONTRACT REVIEW**. Recommended action:
**PATCH_VALIDATOR** to support an explicit generation-table heading and its
bounded rows without weakening the standalone-name false-positive guard. A
blind model retry is **NO**: the persisted final output already names exactly
the entities established by the source, and the previous corrective retry did
not change the deterministic rejection.

### BOE-B-2025-39508

The source title submits the request for “reconocimiento, en concreto, de
utilidad pública” of `Navabuena Solar` to public information. The model output
contains the supported, contract-valid action:

```text
declaracion_utilidad_publica / sometido_informacion_publica
```

The failure is caused by a deterministic inconsistency:

1. `_ACTION_PATTERNS[PUBLIC_UTILITY_DECLARATION]` recognizes “declaración de
   utilidad pública” but not “reconocimiento ... de utilidad pública”.
2. `_action_types_from_title()` therefore returns only `informacion_publica`.
3. `_canonicalize_actions()` adds that generic action and then deliberately
   removes it because the specific utility action already carries
   `sometido_informacion_publica`.
4. `validate_extraction_against_document()` compares action types only and
   reports the just-removed generic type as missing.

The exact error is:

```text
Faltan actuaciones actuales explícitas del título: ['informacion_publica'].
```

The source supports the model output; the combined canonicalization/validation
result is incorrect. Classification: **VALIDATION BUG / CONTRACT REVIEW**.
Recommended action: **PATCH_CANONICALIZATION** by recognizing the established
“reconocimiento ... de utilidad pública” title wording as
`declaracion_utilidad_publica`, with regression coverage for the normalized
specific action. The contract already allows this action/decision pair. A
blind model retry is **NO**.

## 6. Canonicalization failures

Both records reached the same boundary: a valid persisted `BOEAIExtraction`
was converted to `BOEProjectExtraction`, then
`canonicalize_project_extraction()` called `_canonicalize_actions()`. The
`AdministrativeAction.validate_action()` Pydantic validator correctly permits
only `rectificado` for `correccion_errores` among non-generic decisions.

For correction titles, `_action_types_from_title()` correctly returns only
`correccion_errores`, reflecting the current temporal policy that a correction
does not republish the corrected act. The defect is in `_decision_from_title()`:
its global `informacion_publica` branch runs before its
`correccion_errores -> rectificado` branch. `_canonicalize_actions()` therefore
tries to replace the valid decision with `sometido_informacion_publica`.
Assignment validation rejects the impossible intermediate object:

```text
correccion_errores + sometido_informacion_publica
```

The model did not persist that invalid combination in either case; the
canonicalizer imposed it.

### BOE-B-2024-46241

The source is a correction from 121 to 110 mining squares in the prior notice
for the `CIBELES CENTRO-SUR` geothermal-resources research permit. It quotes
the prior public-information wording, so both phrases can occur in one real
BOE. They are not one administrative action/decision pair: under the active
temporal policy the current act is the correction, while public information is
part of the corrected prior notice.

The model output contains only the valid
`correccion_errores / rectificado` action. It did not mix two actions, and no
second current action is needed. Canonicalization alone creates the rejected
combination. The contract is sufficient.

Independently, the model classifies a mining research permit for geothermal
resources as an electricity-generation project. The local source does not
identify `CIBELES CENTRO-SUR` as a plant or electrical generation project.
Once the canonicalization crash is fixed, the existing generation-context
validator should reject that separate model claim correctly.

Exact classification: **CANONICALIZATION BUG**. Recommended action:
**PATCH_CANONICALIZATION**, replay offline, and then accept the documentary
validator's generation-scope rejection if it is the resulting error. A blind
model retry is **NO**.

### BOE-B-2026-4032

The source is a correction notice for the public-information announcement of
`FV Recova Solar Ampliación`; it adds parcel ownership and parcels omitted from
the previously published affected-assets list. The source clearly supports the
named generation asset and a current correction.

The persisted model output contains separate, individually valid actions:

- `correccion_errores / rectificado`;
- `informacion_publica / sometido_informacion_publica`;
- two `modificacion_autorizacion / solicitado` actions; and
- `declaracion_utilidad_publica / solicitado`.

The model did not create the invalid correction/public-information pair. The
same ordering defect in `_decision_from_title()` rewrites the first action and
causes the Pydantic failure.

Whether the corrected prior notice should also be represented as separate
current public-information and application actions is a temporal human
decision. The active correction-only title policy says no, but the literal
title contains both concepts. The existing contract can represent either
decision, so this is not a contract gap. The immediate failure classification
is exactly **CANONICALIZATION BUG**. Recommended action:
**PATCH_CANONICALIZATION**, preserve `rectificado`, enforce the approved
correction temporal policy, and replay offline. A blind model retry is **NO**.

## 7. Root-cause analysis

| Root cause | Demonstrated effect | Classification |
| --- | --- | --- |
| Statusless `ReadError` is outside the pipeline transient retry predicate | One transport failure is preserved with no output or usage | Operational retry plus tooling gap |
| Two 240-second model-run timeouts exhausted | No durable response/output for one document | Operational retry plus tooling gap |
| Generation descriptor omits explicit `infraestructura híbrida fotovoltaica` | Valid named/rated generation asset rejected | Validation bug |
| Generation context is not propagated from a table heading to bounded table rows | Nine explicitly listed independent plants rejected | Validation bug |
| Public-utility title pattern omits `reconocimiento ... utilidad pública` | Specific normalized action is treated as a missing generic action | Canonicalization/title parsing bug |
| Generic public-information decision has precedence over correction decision | Valid `correccion_errores / rectificado` is mutated into an invalid pair | Canonicalization bug |

There is no demonstrated extraction contract gap. The existing enums and
action list can represent all five semantic documents.

## 8. Systemic-risk assessment

The versioned 4,989-document main scope and existing local extraction snapshots
were searched without model calls.

| Pattern | Local evidence | Risk before later scopes |
| --- | --- | --- |
| Correction title also contains public-information wording | 50 main titles; 48 after `main-01`; 3 in `main-02`. `_decision_from_title()` returns `sometido_informacion_publica` for all 50 correction actions. | **HIGH** |
| Public-utility recognition parsed as generic public information | 36 main titles; 33 after `main-01`; 4 in `main-02` | **HIGH** |
| `infraestructura híbrida fotovoltaica` | 8 main titles; 7 after `main-01` | **MEDIUM** |
| Shared-generation table matching the demonstrated layout | 2 main documents; 1 after `main-01` | **MEDIUM** |

The development snapshot contains eight
`declaracion_utilidad_publica / sometido_informacion_publica` action rows, and
the successful `main-01` selection contains 28. This confirms that the specific
action/decision pair is established contract behavior. Two other equivalent
“reconocimiento ... utilidad pública” documents in `main-01` passed only
because their model outputs used two actions instead of the equally valid
specific representation, demonstrating model-shape-dependent validation.

No correction/public-information title, hybrid-infrastructure title or shared
generation table occurs in the 140-document development source, explaining why
those regressions were not exposed by that sample. Counts above are lexical
evidence of exposure, not predictions that every matching document will become
a generation extraction.

## 9. Recommended disposition

The duplicate `code_change` headings below preserve the requested decision
matrix: the first states whether code is needed and the second names its scope.

| BOE | error_type | root_cause | source_supports_model_output | validator_correct | recommended_action | retry_model | code_change | code_change | human_decision | blocks_main_02 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `BOE-A-2025-19878` | `ReadError` | Transient read/transport failure; no durable output | N/A | N/A | `RETRY_OPERATIONAL` | Yes, explicitly | Yes | Add cumulative failed-attempt retry tooling | Authorize retry | Yes |
| `BOE-B-2024-30150` | `TimeoutError` | Exactly two model-run timeouts exhausted | N/A | N/A | `RETRY_OPERATIONAL` | Yes, explicitly | Yes | Same cumulative retry tooling | Authorize retry | Yes |
| `BOE-A-2026-14482` | `DocumentExtractionValidationError` | Generation descriptor lexical gap | Yes | No | `PATCH_VALIDATOR` | No | Yes | Narrow hybrid-photovoltaic generation context | No extraction decision | Yes |
| `BOE-B-2024-29516` | `DocumentExtractionValidationError` | Table heading context lost across source units | Yes | No | `PATCH_VALIDATOR` | No | Yes | Bounded generation-table validation | No extraction decision | Yes |
| `BOE-B-2025-39508` | `DocumentExtractionValidationError` | Public-utility recognition title pattern gap | Yes | No | `PATCH_CANONICALIZATION` | No | Yes | Recognize `reconocimiento ... utilidad pública` | No extraction decision | Yes |
| `BOE-B-2024-46241` | `ValidationError` | Correction decision overwritten by generic public information | Partial: correction yes; generation root no | Pydantic yes; canonicalization no | `PATCH_CANONICALIZATION` | No | Yes | Correction decision precedence | Confirm post-patch validator rejection | Yes |
| `BOE-B-2026-4032` | `ValidationError` | Same deterministic decision overwrite; extra-action temporal question remains | Partial | Pydantic yes; canonicalization no | `PATCH_CANONICALIZATION` | No | Yes | Correction precedence and approved temporal policy | Required for extra current actions | Yes |

Operational retries recommended: **2**. Blind retries for semantic cases:
**0**. Human extraction/domain decisions required: **1**, for the temporal
treatment of the additional actions in `BOE-B-2026-4032`. Human authorization
is also required before any code patch or operational retry, but that workflow
approval is distinct from a semantic extraction decision.

## 10. Main-02 gate

Gate classification:

```text
MAIN-02 BLOCKED BY CODE/CONTRACT BUG
```

The demonstrated blockers are code bugs; no contract patch is currently
required. `main-02` itself contains three exposed correction/public-information
titles and four exposed public-utility-recognition titles. Running it before
patching would knowingly repeat deterministic failures and make outcomes
depend on variable model output shape.

Required sequence before `main-02`:

1. human disposition of this report and the one temporal question;
2. minimal canonicalization/validation patches with regression tests;
3. offline replay of the five persisted semantic outputs;
4. explicit cumulative retry tooling and separate authorization for the two
   operational retries;
5. publication and review of a new cumulative `main-01` snapshot;
6. only then reconsider the `main-02` gate.

No retry, `main-02`, holdout or other scope has been executed by this review.

## 11. Human decisions

All decisions remain pending:

| Decision | Status |
| --- | --- |
| Accept the two operational cases as explicit-retry candidates | `PENDING` |
| Authorize minimal cumulative retry tooling | `PENDING` |
| Approve the four demonstrated deterministic code fixes | `PENDING` |
| Decide whether `BOE-B-2026-4032` carries only the current correction or also separate current public-information/application actions | `PENDING` |
| Keep `main-02` blocked until a reviewed cumulative `main-01` snapshot exists | `PENDING` |

```text
BLOCKER: YES — deterministic code defects are already exposed in main-02.
CONTRACT PATCH REQUIRED: NO.
MAIN-01 FAILURE REVIEW REVEALS CODE/CONTRACT BLOCKER
```
