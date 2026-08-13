# TFM core data freeze — 2026-08-13

## 1. Status

```text
Status: FROZEN
Validation: PASSED
Freeze date: 2026-08-13
```

This document declares the final freeze of the TFM core data.

## 2. Frozen scope

The freeze covers:

- extraction contract and canonicalization;
- the recanonicalized extraction snapshot;
- versioned human corrections;
- the 13 normalized Silver tables;
- deterministic INE location resolution;
- deterministic project grouping;
- Gold `projects`;
- Gold `project_events`.

## 3. Excluded scope

The freeze does not cover:

- `project_locations`;
- Streamlit;
- the review-candidate UI;
- user error reports;
- the final holdout;
- daily production automation;
- an external orchestrator.

These additive layers may be developed without reopening the freeze, provided
that they do not change the frozen semantics.

## 4. Identities

| Item | Frozen identity |
|---|---|
| Git HEAD validated | `7108d5d43d7f1c0d1cb8391c8002eca1b86e46ac` |
| Run | `runs/canonical-140-freeze-final-candidate-20260813/` |
| Run fingerprint | `ae603b6f364f6e24f0b700c10b037b57e230dbd8bab814387c575e67324f2144` |
| Extraction snapshot ID | `55582e7cc0ce6262fc43fbb5a6cb482a03f794d8d68956e01d4b9e081e0de855` |
| Extraction config | `8158661f76a31c87` |
| Contract hash | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| Instructions hash | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| Canonicalization policy | `termination_object_filter_environmental_terminal_whitelist_lexical_authorization_decisions_v3_idaa_substantive_outcomes_v1_explicit_relation_validation_conservative_grouping_v1` |
| Corrections identity | `12a401d7594129e69a473a6d44f71dc89e05334f18493ddf65fbae15106b9dea` |
| Silver ID | `2bebfe3100f21332f29e97868e0fdc518c2fe96ac33bbe3f8926e15d896ae6f6` |
| INE ID | `25a3bbb28f0c21c5` |
| Downstream ID | `2201abf25a45688013a229a6786fd87fb38c024e787259b699ead3d45b7b1a96` |

## 5. Results

| Metric | Count |
|---|---:|
| Documents | 140 |
| Attempts | 140 |
| Current extractions | 140 |
| Model calls during recanonicalization | 0 |
| Blocking review | 0 |
| Projects | 116 |
| Unique administrative actions | 165 |
| Project events | 169 |
| Multi-project actions | 4 |
| Resolved location mentions | 592 |
| Grouping rows | 119 |

## 6. Silver counts

| Table | Rows |
|---|---:|
| `publication_events` | 115 |
| `generation_asset_mentions` | 119 |
| `generation_asset_names` | 132 |
| `associated_components` | 128 |
| `associated_component_names` | 193 |
| `associated_component_generation_links` | 134 |
| `administrative_actions` | 165 |
| `administrative_action_targets` | 201 |
| `participant_mentions` | 307 |
| `location_mentions` | 592 |
| `generation_asset_relations` | 4 |
| `technical_mentions` | 725 |
| `case_file_references` | 42 |

## 7. Human corrections

Five corrections were approved and all five were applied, with zero unmatched
rows, zero ambiguous matches, and zero fingerprint mismatches. They are
traceable exclusions of historical administrative actions that had been
incorrectly attributed to the current publication. The generated Parquet
outputs remain derived artifacts and were not edited manually.

## 8. Included refinements

- `desestimado` is retained as a decision distinct from `denegado`;
- explicit negative decisions are not degraded to `solicitado`;
- IDAA records preserve their substantive outcome;
- historical antecedents are excluded through versioned corrections.

## 9. Validation

Formal validation passed with 934 tests. An independent deterministic
reconstruction produced the same extraction snapshot identity, Silver
identity, downstream identity, semantic table hashes, Gold contents, and
project IDs. Only operational timestamps differed.

The detailed evidence is recorded in
`runs/canonical-140-freeze-final-candidate-20260813-review/freeze_validation_report.md`
and
`runs/canonical-140-freeze-final-candidate-20260813-review/freeze_validation_summary.json`.

## 10. Regression controls

| Control | Frozen project ID |
|---|---|
| Badulaque | `project_5a5df66d62a75798b9ee1ea592fdd32f` |
| Volateo Solar | `project_3b917f88ca2f55d9b52a2fa2c5beca6a` |
| La Puebla 1 | `project_6f0cbfe16a235e118cbbc44f3ab097e3` |

## 11. Reopening rule

The freeze may be reopened only when a concrete defect materially affects:

- project identity;
- project grouping;
- administrative chronology;
- action attribution;
- final evaluation;
- reproducibility or provenance.

It is not reopened for presentation changes, new Streamlit filters,
`project_locations`, new charts, documentation improvements, or post-TFM
features.

## 12. Historical lineage

```text
runs/canonical-140-freeze-20260811/
→ historical freeze

runs/canonical-140-freeze-candidate-20260813/
→ corrected decision candidate

runs/canonical-140-freeze-final-candidate-20260813/
→ final corrected and validated freeze
```
