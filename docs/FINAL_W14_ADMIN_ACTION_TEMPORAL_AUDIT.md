# Final W14 administrative-action temporal audit

Audit date: **2026-08-26**. Human approval and application date:
**2026-08-27**. The audited input was W14 Gold with downstream identity
`e3664ebb4efa0876262aed522d8c68e670c13c9ddee5f1fc0c8b76b74481b6e3`.
The original read-only audit is now closed by the human approval and the
validated corrected Gold recorded in
`docs/FINAL_W14_ADMIN_ACTION_CORRECTIONS.md`.

## Method

The audit inspected all 244 unique Silver `administrative_actions`. Candidate
generation was deliberately broader than a regex decision. It combined:

1. whether action evidence was the publication title or a separate passage;
2. the passage position relative to an explicit dispositive block;
3. past-tense, previous-resolution and previous-publication signals;
4. composite evidence containing `[...]` that cannot be found as one literal
   substring;
5. a final manual reading of title, evidence and surrounding source text.

Regex and position only produced candidates. Every classification below was
made after inspecting the local source document. Continuous quotes remain
continuous; composite evidence is identified as such.

| Result | Count |
| --- | ---: |
| Actions audited | 244 |
| Candidates reviewed in source | 16 |
| Historical antecedents misattributed | 11 |
| Ambiguous — human review required | 0 |
| False alarms / true current actions | 5 |

The 11 confirmed rows affect four publications and seven canonical projects.

## Human approval and application status

The responsible human reviewer approved **8 semantic decisions** and the
complete inventory of **11 technical correction rows**:

> Apruebo las 8 decisiones semánticas descritas y las 11 filas técnicas de
> corrección propuestas. Confirmo que las actuaciones señaladas son
> antecedentes históricos y deben excluirse de las publicaciones actuales
> correspondientes, conservándose en sus publicaciones históricas correctas
> cuando proceda.

The rows use `reviewer=human_tfm_review`, `reviewed_on=2026-08-27` and
`decision_source=human_approval:final-w14-admin-action-temporal-audit:2026-08-27`.
They are present in the versioned master and were applied through the
contractual W14 corrections subset. Status: **APPROVED AND APPLIED**.

## Don Rodrigo II trace

### Source and extraction

| Stage | `BOE-B-2026-12663` | `BOE-A-2026-17939` |
| --- | --- | --- |
| Publication date | 2026-04-23 | 2026-08-19 |
| Source SHA-256 | `f7d6626e56473abb2d0dc445add6125498f01abd3586289bea434546dcbae434` | `0e89105565d747e66b145b058e39e5e4598353c2851b9929bc807e1b77f2df6b` |
| Effective attempt | `a671cdedc0ca938343bdf4d3b5634492` | `4d9a022fffe5e13db702f714a176be9b` |
| Source attempt | `5b642bec0af340a997b371e2dd1f97e7` | `b052571d7ffc4faea593dc94064d7848` |
| Extraction config | `4b54b89dbfe8640e` | `4b54b89dbfe8640e` |
| Events/actions | 2 / 4 | 1 / 6 |

The April announcement creates two independent events: event 1 for Don
Rodrigo II and event 2 for Bianor. Grouping maps the Don Rodrigo II mentions
from both publications to
`project_a3f24a913ba8501e830acfbb67c18a29` by strong exact name. Bianor maps to
`project_3336ab1bea4c54bf99c1eb2313c77445`.

### April current actions

For Don Rodrigo II, `BOE-B-2026-12663_event_1` contains:

| Administrative action ID | Type | Decision |
| --- | --- | --- |
| `BOE-B-2026-12663_event_1_action_1` | `autorizacion_administrativa_previa` | `sometido_informacion_publica` |
| `BOE-B-2026-12663_event_1_action_2` | `autorizacion_administrativa_construccion` | `sometido_informacion_publica` |

Both use the announcement title as evidence. The same two current actions are
present in event 2 for Bianor. In this contract, information-public status is
represented as the decision on the requested authorization, rather than as a
separate `informacion_publica` action.

### August raw actions and finding

`BOE-A-2026-17939_event_1` currently contains six Silver and Gold actions:

| Action | Type/decision | Classification |
| --- | --- | --- |
| `_action_1` | `solicitud_tramitacion / solicitado` | Historical antecedent misattributed |
| `_action_2` | `subsanacion_documentacion / subsanado` | Historical antecedent misattributed |
| `_action_3` | `solicitud_tramitacion_ambiental / solicitado` | Historical antecedent misattributed |
| `_action_4` | `informacion_publica / sometido_informacion_publica` | Historical antecedent misattributed |
| `_action_5` | `autorizacion_administrativa_previa / autorizado` | True current action |
| `_action_6` | `autorizacion_administrativa_construccion / autorizado` | True current action |

The exact evidence that caused `_action_4` is:

> la petición fue sometida a información pública, de conformidad con lo
> previsto en el referido Real Decreto 1955/2000, de 1 de diciembre, con la
> publicación el 23 de abril de 2026 en el «Boletín Oficial del Estado» y el 24
> de abril de 2026 en el «Boletín Oficial de la Provincia de Sevilla».

It precedes the dispositive block and explicitly points to the April
publication. The August dispositive only grants AAP and AAC. Therefore the
August public-information row is a **HISTORICAL ANTECEDENT MISATTRIBUTED**, not
a current action.

## Corpus-wide candidate disposition

| BOE | Action IDs | Disposition | Source finding |
| --- | --- | --- | --- |
| `BOE-A-2023-17979` | event 1 action 2 | Historical antecedent misattributed | The DIA was formulated by the prior resolution of 20 April 2023; this publication grants AAP. |
| `BOE-A-2025-13976` | event 1 action 1 | True current action | The publication itself formulates the terminal environmental decision; mismatch arose only from composite quote matching. |
| `BOE-A-2026-17939` | event 1 actions 1–4 | Historical antecedents misattributed | Requests, corrections and April public information occur before `resuelve`; the publication grants AAP and AAC. |
| `BOE-B-2025-30392` | events 1–4 action 3 | Historical antecedents misattributed | One environmental report was formulated by the prior resolution of 7 May 2025 and repeated once per asset in the later public-information announcement. |
| `BOE-B-2026-26871` | event 1 action 1 | True current action | The utility declaration occurs in the dispositive passage. |
| `BOE-B-2026-26938` | event 1 actions 4–5 | Historical antecedents misattributed | A municipal environmental qualification and a 2025 territorial report are listed under `Antecedentes de hecho`; the current resolution grants AAP, AAC and DUP. |
| `BOE-B-2026-27230` | event 1 action 1 | True current action | The action appears immediately after the dispositive marker. |
| `BOE-B-2026-27231` | event 1 action 1 | True current action | The action appears immediately after the dispositive marker. |
| `BOE-B-2026-27384` | event 1 action 1 | True current action | The publication title and resolution declare utility in the present act. |

Confirmed action types are: one DIA, one generic application, one document
remediation, one environmental application, one public-information action,
four environmental-impact reports, one mislabelled environmental
qualification and one territorial report stored as `otro`.

## Root cause

The primary cause is **MODEL EXTRACTION ERROR**. For all four affected BOEs,
the precanonical and canonical outputs contain the same number and sequence of
`action_type / decision` pairs. Canonicalisation normalised other details but
did not introduce these actions.

There is also a validation gap: the structural/documentary validator accepts a
literal evidence passage but does not determine whether that passage is a
current dispositive act or an antecedent. A blind deterministic exclusion is
unsafe because five nearby candidates are valid current actions. A future
systemic safeguard should therefore create a semantic warning/review candidate
from discourse position, prior dates/publications and title/dispositive
disagreement; it must not delete actions automatically.

For the 11 source-verified rows, the existing correction layer is appropriate:
`entity_type=administrative_action`, `operation=exclude` and
`reason_code=historical_antecedent_misattributed`. Every affected event retains
at least one valid current action after exclusion.

## Approved and applied correction inventory

These are the approved technical rows. Uniform fields are
`correction_version=1`, `entity_type=administrative_action`,
`operation=exclude` and
`reason_code=historical_antecedent_misattributed`; all have `status=approved`
and the human provenance recorded above.

| Proposed correction ID | Target | Expected type | Expected decision | Evidence SHA-256 |
| --- | --- | --- | --- | --- |
| `historical-action-exclusion-v1-17979-dia` | `BOE-A-2023-17979_event_1_action_2` | `declaracion_impacto_ambiental` | `favorable` | `794be563d3de5159d8220673b0a3b94b75947404221c3baee7e1bfa97d87f4b4` |
| `historical-action-exclusion-v1-17939-request` | `BOE-A-2026-17939_event_1_action_1` | `solicitud_tramitacion` | `solicitado` | `128e62d8ff6105477d6146c7783af4c3025ffdb1c1e61124ab8b95d6fef32e7c` |
| `historical-action-exclusion-v1-17939-remediation` | `BOE-A-2026-17939_event_1_action_2` | `subsanacion_documentacion` | `subsanado` | `2a3610419bea5fd2a445fa8b32c57a2780e00aec22cc3743aeb67dfdb9be15f6` |
| `historical-action-exclusion-v1-17939-environmental-request` | `BOE-A-2026-17939_event_1_action_3` | `solicitud_tramitacion_ambiental` | `solicitado` | `71e760d1403f0c22a45d11b38a15a2221eb74d50b4832153bdc20c4b133573fa` |
| `historical-action-exclusion-v1-17939-public-information` | `BOE-A-2026-17939_event_1_action_4` | `informacion_publica` | `sometido_informacion_publica` | `9b39305621d4b75738ad56cb51b94e5097c2396c66bff6b4547094a22cb7877d` |
| `historical-action-exclusion-v1-30392-aspe-iia` | `BOE-B-2025-30392_event_1_action_3` | `informe_impacto_ambiental` | `sin_efectos_adversos_significativos` | `e62cb331985498767241e889d85e6b339a2c3502cbf2da934c477d7c2914130f` |
| `historical-action-exclusion-v1-30392-banuela-iia` | `BOE-B-2025-30392_event_2_action_3` | `informe_impacto_ambiental` | `sin_efectos_adversos_significativos` | `20205f2821e823cb704e50b6ba7133e3876af7ef35d2a7b6f854a23ff3f0164c` |
| `historical-action-exclusion-v1-30392-turbon-iia` | `BOE-B-2025-30392_event_3_action_3` | `informe_impacto_ambiental` | `sin_efectos_adversos_significativos` | `d438d72da4613c7ac0e1a620f8e3d1c72c1a057c4a86396fbb3850a87c3a6926` |
| `historical-action-exclusion-v1-30392-aitana-iia` | `BOE-B-2025-30392_event_4_action_3` | `informe_impacto_ambiental` | `sin_efectos_adversos_significativos` | `d40f1aa1b374e54e5e03ffe2a02ca726de554dcee8b776a42cd23dc74927a320` |
| `historical-action-exclusion-v1-26938-environmental-qualification` | `BOE-B-2026-26938_event_1_action_4` | `informe_determinacion_afeccion_ambiental` | `sin_efectos_adversos_significativos` | `b8baf8113840fdd2810c17a785e1fd08f5134903467aa8897309abe30e7709d3` |
| `historical-action-exclusion-v1-26938-territorial-report` | `BOE-B-2026-26938_event_1_action_5` | `otro` | `favorable` | `5978e11e23587fc3b9bebe42cdf7fd3e016d65eb09f3a996eaaca1c321607440` |

## Approved application

The production correction function accepted all 11 approved targets and
fingerprints. The mandatory in-memory gate completed before publication:

```text
administrative actions before = 244
proposed exclusions           = 11
administrative actions after  = 233
```

Don Rodrigo II becomes:

```text
23/04/2026 — BOE-B-2026-12663
  AAP / sometido_informacion_publica
  AAC / sometido_informacion_publica

19/08/2026 — BOE-A-2026-17939
  AAP / autorizado
  AAC / autorizado
```

The April announcement remains current and August no longer duplicates public
information or the other historical processing steps. Silver and Gold were
then materialized under the new v2 run; the original extraction and every v1
derived artifact remain immutable.

## User-report correction workflow

```text
Streamlit mailto
→ human triage
→ local source verification
→ CURRENT / ANTECEDENT / AMBIGUOUS classification
```

- extraction structure or semantics → versioned `manual_review`;
- historical antecedent misattributed → approved
  `administrative_action_correction` exclusion;
- false positive of `possible_historical_antecedent` → approved action-level
  `CURRENT` decision in `config/manual_reviews/historical_antecedent_reviews.csv`,
  with no extraction or correction change;
- location or grouping → deterministic technical correction/rule plus tests,
  because no generic downstream correction contract exists.

After approval: recanonicalise when applicable, materialise a new Silver,
rebuild downstream and Gold, validate identities and invariants, and only then
redeploy or repoint Streamlit. Never edit generated Gold or Parquet files.

## Gate decision

**CLOSED — 8 HUMAN DECISIONS APPROVED; 11 TECHNICAL ROWS APPLIED.** The
corrected Gold is loader-valid and the negative controls are unchanged.

The repeated pattern now has the upstream systemic safeguard
`possible_historical_antecedent` (`historical_antecedent` policy v1). It runs
after canonical/documentary validation while building the review queue and
requires both a strong temporal/structural signal and an independent contextual
signal. It preserves the extracted action and routes unresolved findings to a
blocking human review; it never decides `ANTECEDENT/CURRENT` or applies an
exclusion. Diagnostics retain action identity, original evidence and hash,
signals, source positions/section, excerpt, document hash, attempt lineage and
policy version.

The executable pre-correction replay in
`tests/extraction/test_historical_antecedents.py` detects **11/11** approved
historical rows and **0/5** negative controls. Exact reconciliation against the
versioned correction identity resolves the eleven approved findings, leaving
zero new pending reviews. A separate exact, versioned `CURRENT` decision can
resolve a future false positive without mutating the extracted action; partial
resolution within one BOE leaves every unresolved sibling finding blocking.
The detector contains no BOE-specific production
exception. The environmental-outcome distinction illustrated by
`BOE-A-2025-17072` and `BOE-A-2025-17147` remains P1 and outside this safeguard.
