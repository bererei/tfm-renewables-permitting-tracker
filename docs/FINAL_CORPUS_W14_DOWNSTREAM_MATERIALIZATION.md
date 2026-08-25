# Final W14 Downstream Materialization

## 1. Purpose

This report closes the REQUIRED deterministic downstream and Gold gate for the
final W14 corpus. It resolves administrative locations, groups generation
mentions and publishes the four-table Gold dataset from the validated Silver
snapshot. The operation made zero Gemini, BOE, web or other model calls; it did
not execute extraction, recanonicalization, holdout or Streamlit.

## 2. Silver input

- Path: `runs/final-w14-corpus-20220101-20260820-v1/silver`
- Silver ID: `1fdcdb0fc15d7ccef062dd69a9fb35d2f85ddff5ec6a4a0ecba035332eb28014`
- Extraction parent ID:
  `dea0f79d9b743dccff23f19995da6ff470866c1d717a2ad1a3af7c415d06eae3`
- Extraction config: `4b54b89dbfe8640e`
- Contractual tables: 13
- Generation-asset mentions: 159
- Location mentions: 828

The production loader revalidated the Silver manifest, hashes, schemas,
dtypes, PK/FK and polymorphic relations before downstream processing. Only
`generation_asset_mentions` enters grouping; components, storage, evacuation
infrastructure, substations and lines cannot become independent project roots.

## 3. INE reference

- Path: `runs/ine-reference-20260614-25a3bbb28f0c21c5`
- Reference ID: `25a3bbb28f0c21c5`
- Semantic SHA-256:
  `25a3bbb28f0c21c52dbc38e572b4fdc91385579063e6d217b18b7a67b259cfac`
- Physical municipality Parquet SHA-256:
  `56c002e74f0f949bd77af6401a68944de82af1afd0805b793cd411e9f84d83bf`
- Municipalities: 8,132
- Province codes: 52
- Autonomous-community codes: 19

The reference loader validated the manifest and content without downloading
anything.

## 4. Location resolution

The deterministic resolver preserved all 828 Silver rows and resolved each
administrative level independently:

| Level/status | Rows |
| --- | ---: |
| Overall `resolved` | 624 |
| Overall `partially_resolved` | 204 |
| Municipality `resolved` | 624 |
| Municipality `not_found` | 21 |
| Municipality `not_provided` | 183 |
| Municipality `ambiguous`/`conflict` | 0 |
| Province `resolved` | 809 |
| Province `not_provided` | 19 |
| Province `ambiguous`/`conflict` | 0 |
| Autonomous community `resolved` | 828 |
| Autonomous community unresolved/ambiguous/conflict | 0 |

The 204 partial rows retain valid province and/or autonomous-community facts;
a missing municipality does not discard higher-level evidence. Every resolved
municipality, province and autonomous-community code exists in the INE
dimension: zero incompatible codes. No row is wholly unresolved because all
828 retain a resolved autonomous community.

The published `resolved_locations.parquet` has 828 rows, no null/duplicate PK,
semantic ID
`2d3fe25955e70b677d0ec1f0ae354527fc46cbf2de4f1b57605f4bacb81d7611`
and physical SHA-256
`e2b61b4d33e5db4c0d4586ca2ccc93efaac6b5bf922b84b21c81ffc74c7c28c4`.

## 5. Grouping

The production rule normalizes documentary plant names by removing only
leading generation descriptors, preserves distinctive tokens and aliases,
and combines the canonical name identity with exact technology and a stable
territorial anchor. Province is preferred, autonomous community is used when
province is unavailable, and municipality never changes the key. A fixed
UUID5 namespace derives `project_id` from this versioned match key, independent
of physical row order.

| Metric | Result |
| --- | ---: |
| Input generation mentions | 159 |
| Grouped mentions | 159 |
| Ungrouped mentions | 0 |
| Canonical projects | 86 |
| `strong_exact_name` mentions | 90 |
| `documentary_variant` mentions | 31 |
| `singleton` mentions | 38 |
| Ambiguous/conflicting groups | 0 |
| Duplicate mention IDs | 0 |

Three mentions, all three manually reviewed 27607 roots, use the explicit
`geography:unresolved` key and become three deterministic singleton projects.
This is not an ungrouped or ambiguous status: the grouping contract assigns
all 159 mentions and has no separate unresolved-group output.

`project_grouping.parquet` has semantic ID
`8021c957139b51ac3b9ebb7546012ad7a7bbf1ec1d7362f48051699c41b10062`
and physical SHA-256
`6e58a2b851fc9e61070c7ed1b36b782b7475e2f6a7c04706e232ca72bd3833b0`.

## 6. Gold contract

Gold contract version `2` contains exactly four tables:

| Table | Purpose and grain | Primary key | Main FK |
| --- | --- | --- | --- |
| `projects` | one canonical generation project | `project_id` | — |
| `project_events` | one project × administrative action attribution | `project_id`, `administrative_action_id` | project |
| `project_locations` | one canonical project × territory association | `project_location_id` | project |
| `project_location_sources` | one project territory × Silver location mention | `project_location_id`, `location_mention_id` | project location; event/BOE/date provenance |

`projects` stores identity, technology, available municipality/province values,
first/last observed publication and publication/action counts.
`project_events` stores the dated BOE chronology, action, decision and literal
evidence. The two territorial tables preserve canonical administrative units
and their source mentions.

## 7. Materialization

The CLI dry-run loaded the exact Silver and INE identities and left the output
absent. A separate in-memory execution of the production resolver, grouping
and Gold builders completed with no validation issue. The same CLI without
`--dry-run` then atomically published:

```text
runs/final-w14-corpus-20220101-20260820-v1/downstream/
├── downstream_manifest.json
├── resolved_locations.parquet
├── project_grouping.parquet
└── gold/
    ├── manifest.json
    ├── projects.parquet
    ├── project_events.parquet
    ├── project_locations.parquet
    └── project_location_sources.parquet
```

- Downstream contract: `2`
- Build version: `deterministic_downstream_v2`
- Created at: `2026-08-25T12:43:20.068876Z`
- Downstream/Gold ID:
  `e3664ebb4efa0876262aed522d8c68e670c13c9ddee5f1fc0c8b76b74481b6e3`

The first shell attempt never entered the pipeline because the sandbox blocked
the local `uv` cache lock. The output remained absent, and the identical
command was rerun with cache access; this introduced no semantic or contract
change.

## 8. PK/FK validation

The application-facing Gold loader accepted all four tables and independently
recomputed the downstream identity. Exact validation results are:

| Table | Rows | PK nulls | PK duplicates | FK violations | Physical SHA-256 | Semantic SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `projects` | 86 | 0 | 0 | 0 | `81875c99da2eab17cb16f7d3092e66006ac2370f8bd56dd3b7c5a964c17e203d` | `2595ff2b5b881d824c23c7328d0ef039d61fcad5876255ea93d2b7335c34ec3c` |
| `project_events` | 251 | 0 | 0 | 0 | `f75ad6e22f0b760b1bb067acff87fb6ef1f9fee0cb23019a5c054977a856684d` | `00933afb289c918e222938b4407c2c0bd12c05f6caa2fd4cd6e58903f73e6f85` |
| `project_locations` | 453 | 0 | 0 | 0 | `96389d23b40a76aeab88cc2a7e7b4c12e1920c02c1941d1968083171f9a521fd` | `a35f470f31c829c80575703639a9fdafc4b9048450a7ac06909a9fcb76a1b9f2` |
| `project_location_sources` | 839 | 0 | 0 | 0 | `06e2a7611977344a4220b2d543b942b0d335d90a644cdb0153deba1101167ee7` | `cd247c2753d836b3f85592d4690a94c87ef51b2cea6db989c70f6f951777ebfe` |

Schemas and dtypes match exactly. Project, location, location-source and
event/BOE/date relationships have zero dangling values. Direct checks back to
Silver found zero location-provenance and zero project-event provenance
violations.

## 9. Project metrics

| Metric | Result |
| --- | ---: |
| Projects | 86 |
| Projects with technology | 86 |
| Projects with at least one publication | 86 |
| Projects with administrative actions | 86 |
| Projects with territory | 83 |
| Projects without resolved territory | 3 |
| Projects with exactly one BOE | 38 |
| Projects with at least two BOEs | 48 |
| Projects with at least three BOEs | 14 |
| Projects with at least four BOEs | 10 |
| BOEs linked to one project | 51 |
| BOEs linked to more than one project | 29 |

The true 29 multi-project BOEs are calculated after grouping from BOE-to-project
membership. The Silver proxies were 25 BOEs with more than one event and 29
with multiple asset mentions; equality with the latter is coincidental because
events and asset mentions are not canonical projects.

Gold represents 80 unique relevant BOEs. The 24 non-relevant extraction rows
remain part of the extraction/Silver lineage but produce zero Gold project
events.

## 10. Longitudinal metrics

The chronology spans `2022-01-11` through `2026-08-20`:

| Metric | Result |
| --- | ---: |
| Projects observed in at least two calendar years | 26 |
| Projects observed in at least three calendar years | 10 |
| Projects observed in at least four calendar years | 1 |
| Median first-to-last span | 70 days |
| P75 first-to-last span | 323.75 days |
| Maximum first-to-last span | 1,623 days |

First and last publication mean only the first and last observations inside
the reconstructed corpus, not an exhaustive administrative history.

`project_events` contains 251 rows, 86 projects, 80 BOEs and zero duplicate
`project_id × administrative_action_id` identities. Sixteen action types and
sixteen decisions are represented. The current query layer deterministically
derives 195 latest project/action-type rows using publication date, event
index, action index and action ID as tie-breakers. This is the latest published
situation per procedure, not a definitive current legal status.

Observed action types are `autorizacion_administrativa_construccion`,
`autorizacion_administrativa_previa`, `correccion_errores`,
`declaracion_impacto_ambiental`, `declaracion_utilidad_publica`,
`evaluacion_impacto_ambiental`, `informacion_publica`,
`informe_determinacion_afeccion_ambiental`, `informe_impacto_ambiental`,
`levantamiento_actas_previas_ocupacion`, `modificacion_autorizacion`, `otro`,
`solicitud_tramitacion`, `solicitud_tramitacion_ambiental`,
`subsanacion_documentacion` and `terminacion_procedimiento`.

Observed decisions are `autorizado`, `convocado`, `declarado`, `denegado`,
`desestimado`, `desfavorable`, `desistido`, `favorable`, `formulado`,
`modificado`, `rectificado`, `requiere_evaluacion_ambiental_ordinaria`,
`sin_efectos_adversos_significativos`, `solicitado`,
`sometido_informacion_publica` and `subsanado`.

## 11. Territory coverage

| Metric | Result |
| --- | ---: |
| `project_locations` rows | 453 |
| Municipality-level rows | 348 |
| Province-level rows | 91 |
| Autonomous-community-level rows | 14 |
| `project_location_sources` rows | 839 |
| Distinct Silver location mentions represented | 828 |
| Multi-project source expansions | 11 |
| Projects with municipality | 83 |
| Projects with province | 83 |
| Projects with autonomous community | 83 |

The joint territory-bundle semantic hash is
`31e3d498b617981c7626c541cc7c1c401f18c3fded2006fecf3a9e0f087af4d3`.
Every project territory is traceable to a Silver location mention, event, BOE
and publication date. These territories are administrative places appearing
in BOE publications; they are not exact physical plant coordinates and must
not be presented as density.

## 12. Manual-review regression

`BOE-B-2023-27607` remains correctly represented:

| Generation root | Project ID |
| --- | --- |
| HSF ANUBIS | `project_1121f855fc4c51c7bfc58d3071561a6f` |
| HSF AFRODITA | `project_edccf9d6d2025341bf65e017b472a100` |
| HSF DEMETER | `project_85725bdff399523c928aca1c60f548ee` |

The Atenea–Marchamorón infrastructure creates no project root. Silver contains
one shared component and one source DUP. Gold attributes that same action once
to each of the three distinct projects, producing three valid
project/action rows and zero duplicate action inside any project. This is
shared-action attribution, not semantic duplication.

The development-only examples Badulaque, Volateo Solar, La Puebla 1, FV
Andévalo and PE Angostillos do not appear as projects in this final W14 Gold;
no assertion about their development-corpus histories was imposed.

## 13. Historical-link assessment

The 78 versioned `project_history_candidates` links were compared with final
project membership using only their anchor generation mention and historical
BOE project IDs:

| Final grouping disposition | Links |
| --- | ---: |
| Same final grouped project | 34 |
| Historical BOE non-relevant / not associated | 2 |
| Different strict grouping / unresolved | 42 |

The earlier extraction-stage audit reported 41/2/35 using normalized plant
name/key plus technology. Final grouping additionally requires its strict
territorial match key; seven links therefore remain unconfirmed here. No ad
hoc rule was added to force them, and the 42 unresolved links are not Gold
validation blockers.

## 14. Gold ↔ Streamlit compatibility

Classification: **APP COMPATIBLE WITH FINAL GOLD**. The production app loader
accepted the final directory and exact downstream ID, and pure catalogue,
latest-action, filter, detail, timeline, territory and territorial-source
queries executed successfully.

| Product question | Support | Source |
| --- | --- | --- |
| Number of projects | YES | `projects` |
| Number of relevant BOE publications | YES | distinct `project_events.boe_id`; full 104-document analyzed count is not a Gold fact |
| Administrative territories | YES | `project_locations` and sources |
| Unique BOE evolution by year | YES | dated distinct BOEs in project events/sources |
| Latest published situation by action type | YES | deterministic query over `project_events` |
| Complete observed project chronology | YES | `project_events` |
| Evidence supporting an action | YES | `project_events.evidence` |
| First/last appearance in analyzed period | YES | `projects` |

Concrete alignment work remains outside this block:

- configure `RENEWABLES_GOLD_DIR` to the final Gold path and
  `RENEWABLES_EXPECTED_DOWNSTREAM_ID` to `e3664ebb…b6e3`; defaults still point
  to the validated development dataset by design;
- implement the approved final KPI/map/temporal/administrative presentation;
- provide an approved external administrative geometry layer for the map.

Gold already supplies CCAA, province and municipality codes/names and distinct
project membership, but contains no polygon geometry. Temporal and
administrative chart data are available; the current Streamlit MVP has not yet
implemented those final dashboard charts. Project detail data are available
for identity, technology, observed first/last publication, BOE/action counts,
latest procedures, territories, chronology, BOE links and literal evidence.

## 15. Manifest and reproducibility

Both manifests are valid. They record Silver ID, extraction config, INE ID and
SHA-256, resolved-location and grouping semantic IDs, Gold table hashes and
counts, contract/build versions and the downstream ID. Build version is the
available code provenance; no separate Git-commit field exists in the current
manifest.

The application Gold loader verified physical and semantic hashes and
recomputed the downstream ID. A second complete resolver → grouping → Gold
build was executed only in memory and matched all six persisted DataFrames
exactly, including dtypes and values. It recomputed the same ID
`e3664ebb4efa0876262aed522d8c68e670c13c9ddee5f1fc0c8b76b74481b6e3`.
The creation timestamp is excluded from that deterministic identity. No second
final directory, overwrite, `--force` or manual Parquet edit was used.

The extraction and Silver loaders still return their original identities, and
their physical hashes remain unchanged. The holdout stayed sealed, excluded
and uninspected.

## 16. Final methodology

“Proyectos de generación con actividad publicada en el BOE durante la ventana
ancla del 7 al 20 de agosto de 2026, con reconstrucción retrospectiva
conservadora de publicaciones relacionadas observadas desde 2022.”

This is not an exhaustive census. Historical retrieval uses Tier 1 plus Tier 2
strict; Tier 3 is excluded. Chronologies are observed within the reconstructed
corpus, so first/last refer to that observation period. The territorial layer
represents administrative places cited in BOE publications, not exact physical
locations.

## 17. Next gate

After human review and an explicitly approved commit/push, the next REQUIRED
block is final Streamlit alignment over this validated Gold, including the
approved dashboard presentation, external administrative geometry decision and
minimum safe reporting channel. Holdout remains sealed and must not be started
inside this gate.
