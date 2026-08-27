# Final W14 administrative-action corrections

Application date: **2026-08-27**. This report closes the approved correction
block over the immutable W14 extraction snapshot
`dea0f79d9b743dccff23f19995da6ff470866c1d717a2ad1a3af7c415d06eae3`.
No model, BOE or web call was used.

## 1. Human approval

The responsible human reviewer approved the eight semantic decisions and the
complete inventory of eleven technical rows:

> Apruebo las 8 decisiones semánticas descritas y las 11 filas técnicas de
> corrección propuestas. Confirmo que las actuaciones señaladas son
> antecedentes históricos y deben excluirse de las publicaciones actuales
> correspondientes, conservándose en sus publicaciones históricas correctas
> cuando proceda.

The applied rows record `reviewer=human_tfm_review`,
`reviewed_on=2026-08-27` and
`decision_source=human_approval:final-w14-admin-action-temporal-audit:2026-08-27`.
Codex materialized the approved decision; it did not make the substantive
decision.

## 2. Approved decisions

The audit classified eleven extracted actions in four BOEs as historical
antecedents, grouped into eight human semantic decisions: the earlier DIA in
`BOE-A-2023-17979`; four antecedent procedure steps in
`BOE-A-2026-17939`; the earlier environmental report repeated across four
plants in `BOE-B-2025-30392`; and two earlier reports in
`BOE-B-2026-26938`. Every row is an approved
`administrative_action/exclude` correction with reason code
`historical_antecedent_misattributed`.

## 3. Corrections master

The versioned master changed from five to sixteen rows. Its original five
physical CSV rows are byte-for-byte unchanged; correction IDs are unique and
the contractual loader accepts the updated registry.

| Metric | Before | After |
| --- | --- | --- |
| Rows | 5 | 16 |
| Semantic identity | `12a401d7594129e69a473a6d44f71dc89e05334f18493ddf65fbae15106b9dea` | `6cd1893c1cc75b239b29e88b7aa04cb407503f9a56b6063e152e9e8cbcef0318` |
| Physical SHA-256 | `51ac0cea06c02547e5ebfb20ee8a5239fca80519de9ee6bff3781bb511386411` | `1d757237cd203dae096dcc36b7af5f041bc7f1d0e31fd9bfdce6e1add4c050b0` |
| Duplicate correction IDs | 0 | 0 |

The eleven added correction IDs are:

- `historical-action-exclusion-v1-17979-dia`;
- `historical-action-exclusion-v1-17939-request`;
- `historical-action-exclusion-v1-17939-remediation`;
- `historical-action-exclusion-v1-17939-environmental-request`;
- `historical-action-exclusion-v1-17939-public-information`;
- `historical-action-exclusion-v1-30392-aspe-iia`;
- `historical-action-exclusion-v1-30392-banuela-iia`;
- `historical-action-exclusion-v1-30392-turbon-iia`;
- `historical-action-exclusion-v1-30392-aitana-iia`;
- `historical-action-exclusion-v1-26938-environmental-qualification`;
- `historical-action-exclusion-v1-26938-territorial-report`.

## 4. W14 corrections subset

The productive `pipeline corrections-subset` command derived
`runs/final-w14-corpus-20220101-20260820-v2/corrections` from the sixteen-row
master and the immutable 104-document W14 extraction. It selected eleven rows,
recorded the five old rows as out of scope and reported zero failures. The
subset materialization ID is
`764e76757d094034d9d8e079a2d493995a7e28e78655fae5ff83e36ffe995da6`;
the semantic identity of its selected correction CSV is
`78895e8d717c0f86c849418d52a9c6cc5f08bb4ed589eac638319802e6ed77c0`.
Every selected row resolved exactly one action and matched its expected ID,
type, decision and evidence fingerprint.

The mandatory in-memory application gate produced:

```text
administrative actions before = 244
approved exclusions           = 11
administrative actions after  = 233
unexpected removals           = 0
```

## 5. Silver v2

`runs/final-w14-corpus-20220101-20260820-v2/silver` contains all thirteen
contract-valid Silver tables. Its materialization ID is
`1ade4c5e07c1cb13f06c86c0c3e8bd08316b0ee02a35d213dc05b797528fa978`;
the parent extraction and correction identities are the expected values above.
The `administrative_actions` table has 233 rows. Its applied-corrections
sidecar contains the same eleven IDs, the common approved reason code and none
of the five out-of-scope master rows. Schema, domain, PK, FK and polymorphic
relationship validation passed before and after the Parquet round trip.

## 6. Don Rodrigo II

The corrected chronology is:

```text
19/08/2026 — BOE-A-2026-17939
  AAP / autorizado
  AAC / autorizado

23/04/2026 — BOE-B-2026-12663
  AAP / sometido_informacion_publica
  AAC / sometido_informacion_publica
```

August no longer contains the historical request, remediation, environmental
request or public-information rows. April remains unchanged. No action was
moved, copied or synthesized.

## 7. Other corrected BOE

- `BOE-A-2023-17979` retains only its current AAP; the earlier DIA is excluded.
- Each of the four events in `BOE-B-2025-30392` retains its current AAP/AAC
  public-information representation; the earlier environmental report is
  excluded once per affected event.
- `BOE-B-2026-26938` retains AAP, AAC and DUP; the earlier environmental
  qualification and territorial report are excluded.
- `BOE-B-2023-27607` remains one event with three generation assets, one
  shared component, three asset-component links, one DUP and one target.

## 8. Negative controls

All thirteen flattened-table projections remain identical for the five true
current-action controls:

- `BOE-A-2025-13976`;
- `BOE-B-2026-26871`;
- `BOE-B-2026-27230`;
- `BOE-B-2026-27231`;
- `BOE-B-2026-27384`.

Their Gold event semantics are also identical between v1 and v2.

## 9. Downstream / Gold v2

The downstream dry-run accepted Silver v2 and the unchanged INE reference
`runs/ine-reference-20260614-25a3bbb28f0c21c5`. The materialized output is
`runs/final-w14-corpus-20220101-20260820-v2/downstream`, with Gold under its
`gold` directory and downstream ID
`316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86`.
All resolved-location, grouping and Gold loaders and PK/FK checks passed.

| Metric | Gold v1 | Gold v2 | Result |
| --- | ---: | ---: | --- |
| Projects | 86 | 86 | Same project IDs |
| Distinct relevant BOE | 80 | 80 | Unchanged |
| Project-event rows | 251 | 240 | Eleven approved semantic rows removed |
| Project locations | 453 | 453 | Exact equality |
| Project-location sources | 839 | 839 | Exact equality |

Project grouping and resolved locations are exactly equal. Seven affected
project summaries have lower `n_administrative_actions`; no other project
summary field changed. Semantic comparison of `project_events` found exactly
the eleven approved removals and no additions. Physical row comparison also
shows Don Rodrigo's two remaining August action IDs reindexed from `_action_5`
and `_action_6` to `_action_1` and `_action_2`; their publication, type,
decision and evidence semantics are unchanged.

## 10. Streamlit regression

AppTest loaded corrected Gold through the public
`RENEWABLES_GOLD_DIR` and `RENEWABLES_EXPECTED_DOWNSTREAM_ID` configuration,
without application code changes. It reported 86 projects and 80 relevant
BOEs. Latest and historical modes, full-action and action-plus-decision chart
selection, descending project chronology, map, catalogue, detail and bounded
`mailto:` reporting smoke tests passed. Don Rodrigo displays August before
April with the corrected actions above. The existing default dataset was not
silently repointed; deployment/default selection is a separate operation.

## 11. Reproducibility

An independent Silver rebuild in a temporary directory reproduced the same
Silver ID and all thirteen tables exactly. An independent downstream rebuild
reproduced the same downstream ID, four Gold tables, resolved locations and
project grouping exactly.

The original v1 artifacts remain physically unchanged. Aggregate directory
fingerprints before and after the v2 operation were:

| Immutable input/output | Fingerprint |
| --- | --- |
| Extraction v1 | `f4b7c9f3bf9fa2ca4a1221b13d21800a9da0bc1d728086bd1c25378d15e47c67` |
| Silver v1 | `2d42a15a9f1b15cced20a0ce9d5388df29738fe146d0a08cb12fa879691a9cea` |
| Downstream/Gold v1 | `163fb6e3adf478986ab0618ea56efe14360519f458a0a024725756de4b5548fe` |

The holdout was neither run nor inspected.

## 12. Residual safeguard

The corrected corpus remains closed. The subsequent REQUIRED block implemented
the systemic `possible_historical_antecedent` warning and fail-closed review
safeguard without changing this correction materialization. It uses combined
temporal/structural and contextual evidence, preserves every extracted action,
and reconciles exact approved correction fingerprints before creating pending
reviews. A distinct versioned `CURRENT` review registry resolves a detector
false positive without changing the extraction or inventing a no-op correction;
no such row is needed for the five controls because the detector does not flag
them. Its pre-correction replay is 11/11 approved rows and 0/5 controls; see
`docs/FINAL_W14_ADMIN_ACTION_TEMPORAL_AUDIT.md` and
`docs/architecture/extraction_quality_review.md`.
