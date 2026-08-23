# Final P2 main-03 deterministic blocker fix

This report records the bounded offline correction of the three deterministic
blockers in Final P2 `main-03`. It also records why the cumulative candidate
was not published: `BOE-B-2024-3861` still requires one human target decision.

No BOE, Gemini, other model, Silver, downstream, Gold, `main-04` or holdout
execution was performed. Historical attempts and existing snapshots remain
unchanged.

## 1. Identity gate

The two scope/context defects are classified as **A — compatible post-model
bugfix**. Both documents were already eligible under scope policy v4 and both
persisted model outputs correctly say `not_relevant`. The fix changes only the
document validator that was contradicting those outputs.

| Identity | Before | After |
| --- | --- | --- |
| Scope policy | `binary_named_generation_pre_model_guard_v4` | same |
| Extraction config ID | `4b54b89dbfe8640e` | same |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` | same |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` | same |

The final deterministic implementation fingerprint for this uncommitted
candidate is
`35b17723b8fe70e487b85faf28742417ec9ec49ce6d442b7a106f3bd619eed60`.
Recanonicalization materialization version remains `2`.

## 2. Two-column generation table

`BOE-B-2024-3861` contains two explicit tables introduced as independently
processed generation installations. Their columns are only `Denominación` and
`N.º de expediente`; the previous validator recognized only the equivalent
three-column form with `Promotor`.

The bounded parser now accepts both forms when all these conditions hold:

- the immediately local introduction explicitly identifies generation
  installations with independent project processing;
- the headers are `Denominación` and an expediente column;
- each structured row has a bounded case-file value, optionally followed by
  its authority in parentheses; and
- the denomination is not itself a SET, substation, LAAT, LAT or line.

The rule ends at the first non-row. It does not propagate generation context to
another paragraph, a generic infrastructure table, an element after the table
or shared infrastructure.

The actual persisted output now validates all ten plants. The eight rows
previously rejected are:

- `HSF Sol Morón`;
- `HSF Las Encarnaciones`;
- `PE Las Hazas`;
- `PE Josmanil`;
- `PE Las Cabreras`;
- `PE Villanueva 2`;
- `PE Villanueva 1`; and
- `PE Cortijo Nuevo`.

## 3. Guadalsolar token boundary

`BOE-B-2024-45427` concerns the standalone electrical infrastructure `LAAT 220
kV SET Guadalsolar – SET Mirabal`. The old scope review found the substring
`solar` inside the proper name `Guadalsolar` and treated it as generation
evidence.

The post-model exception now requires a standalone grid-project grammar and
the absence of a complete generation-root token. `Guadalsolar` therefore does
not count as `solar`, while `planta solar`, `parque solar`, photovoltaic, wind,
hydroelectric, hybrid and other complete generation terms remain protected.

Offline result:

```text
BOE-B-2024-45427 = RESOLVED NON-RELEVANT
events = 0
new model call = no
```

## 4. Auxiliary irrigation generation

`BOE-B-2025-26539` is an irrigation-community energy-optimization project.
Its photovoltaic installation is auxiliary to replacement of pumping and
electromechanical equipment; it is not an independent generation-project
root.

The bounded post-model exception requires all of:

- a project whose main purpose is irrigation energy optimization,
  modernization or efficiency;
- an explicit photovoltaic installation; and
- pumping, irrigation or irrigation-community context.

It does not accept an independent named photovoltaic plant, a hybridization or
a generation project merely because it serves self-consumption.

Offline result:

```text
BOE-B-2025-26539 = RESOLVED NON-RELEVANT
events = 0
new model call = no
```

## 5. Human target decision package for BOE-B-2024-3861

### Plants

The source identifies ten independent generation plants: `HSF La Romera`,
`HSF Los Mangos`, the eight recovered rows listed above, and no infrastructure
root.

### Shared infrastructure

The source distinguishes two sharing scopes:

1. the 30 kV line associated only with `HSF La Romera` and `HSF Los Mangos`;
2. `SET Torreluenga 30/220 kV` and its 220 kV line, shared by all ten plants.

The persisted output aggregates both scopes into one `component_1` in every
event. The precanonical output targets all three actions at that component.
Current canonicalization instead targets `event` in the first two events and
`component_1` in the remaining eight.

### Administrative actions

The three current actions are unequivocally the request for modification of
prior authorization, modification of construction authorization and public
utility declaration concerning the shared evacuation infrastructure. The
source does not make those actions plant-generation-asset actions.

### Contractual options

- `target = event` is representable, but loses the explicit infrastructure
  object and can be read as a project-wide plant action.
- `target = generation_asset_1` is representable but unsupported and must not
  be used.
- component targets are representable and retain the published object, but the
  component must first be split according to the two sharing scopes.

Recommended human disposition: validate a corrected extraction with the same
ten events and one instance of each action per event; use both component
targets for `HSF La Romera` and `HSF Los Mangos`, and only the all-ten-plants
component for events 3–10. Do not target a generation asset and do not preserve
the current mixed `event`/`component_1` result. This is a recommendation, not a
recorded human decision.

## 6. Future-scope risk

The exact installed matchers were evaluated locally over non-holdout
`main-04` through `main-20`:

| Pattern | Future documents | `main-04` |
| --- | ---: | ---: |
| Explicit supported generation table | 17 | 2 |
| Grid proper-name collision that actually triggers project review | 0 | 0 |
| Auxiliary photovoltaic irrigation project | 1 | 0 |

The auxiliary case is `BOE-B-2025-16990` in `main-05`. The table count is
higher than the earlier lexical estimate because the production parser now
recognizes both column forms and expediente values with authority suffixes.
These are risk exposures, not model outputs or semantic adjudications.

Source selection and policy v4 are unchanged.

## 7. Offline cumulative replay

The active cumulative dry-run used the 750-document `extraction-main-03`
snapshot, its 1,501 immutable attempts, inherited reviews and the corrected
deterministic code.

| Replay measure | Count |
| --- | ---: |
| Eligible root outputs | 748 |
| Semantically unchanged | 723 |
| Semantically changed | 24 |
| Replay failure resolved by inherited rejection | 1 |
| Failed roots recovered | 15 |
| New deterministic derivations required | 747 |
| Projected attempt rows | 2,248 |
| Projected unique attempt IDs | 2,248 |
| Duplicate attempt IDs | 0 |
| Added model calls | 0 |

The 24 changed outputs are exactly the same 24 BOEs already recorded for the
approved `main-02` canonicalization families. The three `main-03` cases change
validation disposition without changing their semantic extraction JSON. No
unexpected family or newly invalid output appeared.

The immutable regressions remain:

```text
main-01: 250 accounted, 249 current, 1 rejected, 0 blockers
main-02: 500 accounted, 499 current, 1 rejected, 0 blockers
```

## 8. Snapshot publication gate

The technical replay would account for all 750 documents with 747 current
extractions, one inherited rejection and two operational blockers. However,
the human target decision above has not been recorded through the contractual
manual-review mechanism.

Therefore no `extraction-main-03-recanonicalized` directory was created and no
candidate can be called loader-valid. Publishing before that decision would
silently accept the mixed target representation.

```text
snapshot published = no
semantic target decisions pending = 1
operational blockers preserved = 2
```

## 9. Retry dry-run

The combined dry-run selected only:

```text
BOE-B-2025-41490
BOE-B-2025-45035
```

It reported 750 documents, 748 compatible existing results, two pending
documents, two explicit error retries, zero deterministic pending documents,
two future model documents required and zero model calls planned. No prior
success and none of the three semantic cases was selected for retry.

The retries remain **NOT AUTHORIZED**.

## 10. Tests and final gate

The new tests were written RED first. The focused RED set initially had the
three expected failures. After the bounded fixes:

```text
new focused controls                         12 passed
affected focal suites                       529 passed
full repository suite                     1,144 passed
```

The focal suites cover canonicalization, validation, config identity,
recanonicalization, pipeline, attempts and reviews. No warning or failure was
reported.

Final recommendation:

```text
MAIN-03 BLOCKER FIX AWAITS TARGET DECISION
```

After the human records the corrected target/component representation, repeat
the cumulative dry-run, publish a new snapshot, loader-validate it and only
then request separate authorization for the two operational retries. `main-04`
and the holdout remain unauthorized.
