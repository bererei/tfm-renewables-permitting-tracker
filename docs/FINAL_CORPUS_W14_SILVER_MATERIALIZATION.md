# Final W14 Silver Materialization

## 1. Purpose

This report closes the REQUIRED Silver gate for the final W14 corpus. The
operation was offline: it made zero Gemini, BOE, web or other model calls and
did not execute location resolution, project grouping, Gold or the holdout.
All Parquet files were produced by the product CLI; none was edited directly.

## 2. Extraction parent

- Path: `runs/final-w14-corpus-20220101-20260820-v1/extraction`
- Snapshot type: `extraction_union`
- Snapshot identity: `dea0f79d9b743dccff23f19995da6ff470866c1d717a2ad1a3af7c415d06eae3`
- Extraction config: `4b54b89dbfe8640e`
- Documents/current extractions/blockers: 104/104/0
- Attempts: 286 rows, 286 unique IDs and no duplicates
- Selection: 103 `auto_validated`, one `manually_validated`, no rejected
- Event-producing/non-relevant extractions: 80/24
- Holdout rows: zero; no holdout content was inspected.

Physical SHA-256 values were recorded before publication and verified again
afterwards. They remained unchanged:

| Artifact | SHA-256 |
| --- | --- |
| `attempts.parquet` | `428cb9275885ef9171efbf1bb6de94a5a9f6d41dd5da4cf6d85a4efc0fbb9595` |
| `current_extractions.parquet` | `6e00b0c70b6a328c9d444c5cdd9e509c2173c0fd98659c49f38c05bd2e3cfcc2` |
| `documents.parquet` | `39dfdba8b5cdf5ad8f22c384f17bf8863b13dbebe622cd6425bd6782bd28fc7c` |
| `manifest.json` | `ec88a6b407f8ddc1df486e9579580b73e2711e10cb34f94eeb04c70b58c7240d` |
| `manual_reviews.parquet` | `9a13e94d00d688b83392ae36a7dc624a5bff60d606bd5cca6a588afa542b3a99` |
| `review_queue.parquet` | `dae1f6ab609bd0aa24ccec6b0a734b7517bd2a9acb2dc2ebc660955545f087f8` |

## 3. Corrections gate

`config/corrections/administrative_action_corrections.csv` loads with identity
`12a401d7594129e69a473a6d44f71dc89e05334f18493ddf65fbae15106b9dea`,
five approved rows and three target BOEs (`BOE-A-2024-16662`,
`BOE-A-2025-9608` and `BOE-A-2025-26110`). Its intersection with the 104 W14
BOEs is empty. Consequently the CLI was invoked without `--corrections`; the
manifest records `applied=false`, zero approved/applied rows and no sidecar.

## 4. Silver contract

`FLAT_TABLE_SPECS` is the source of truth. `FLAT_CONTRACT_VERSION` is `1`;
there is no separate flat-schema fingerprint or materialization-version field.
Column names, order, Pandas/PyArrow types, nullability, PK, 19 direct FK rules
and five polymorphic branches derive from that contract. The exact inventory
is:

| Table | Grain | Primary key | Main foreign keys |
| --- | --- | --- | --- |
| `publication_events` | one publication event | `event_id` | — |
| `generation_asset_mentions` | one generation-asset mention in an event | `generation_asset_mention_id` | event |
| `generation_asset_names` | one name of an asset mention | `generation_asset_mention_id`, `name_index` | event, asset mention |
| `associated_components` | one associated component in an event | `associated_component_id` | event |
| `associated_component_names` | one name of a component | `associated_component_id`, `name_index` | event, component |
| `associated_component_generation_links` | one component-to-asset link | `associated_component_id`, `link_index` | event, component, asset mention |
| `administrative_actions` | one administrative action in an event | `administrative_action_id` | event |
| `administrative_action_targets` | one target of an action | `administrative_action_id`, `target_index` | event, action; polymorphic target |
| `participant_mentions` | one participant mention | `participant_mention_id` | event |
| `location_mentions` | one administrative-location mention | `location_mention_id` | event |
| `generation_asset_relations` | one directed relation between asset mentions | `generation_asset_relation_id` | event, source asset, target asset |
| `technical_mentions` | one technical attribute mention | `technical_mention_id` | event; polymorphic owner |
| `case_file_references` | one case-file reference | `case_file_reference_id` | event |

Only `generation_asset_mentions` is an input to project grouping. Associated
infrastructure remains a component and cannot become a generation root.

## 5. Dry-run

The exact documented command, without `--corrections`, exited with code zero:

```text
silver: current=104 output=.../final-w14-corpus-20220101-20260820-v1/silver
DRY RUN: Silver was not materialized
```

The destination and any `.silver.staging-*` path remained absent. The current
CLI dry-run validates the extraction loader, zero-blocker review gate and
destination; without a corrections file it does not run the in-memory
flattening. Full contract validation therefore occurred during atomic
publication and was repeated independently with the production loader.

## 6. Materialization

The same command without `--dry-run` and without `--corrections` published
atomically to `runs/final-w14-corpus-20220101-20260820-v1/silver`. It validated
the typed tables before writing, wrote them to staging, reloaded and validated
the Parquet round-trip, wrote the manifest, and renamed staging only after all
checks passed.

- Created at: `2026-08-25T12:23:57.528656Z`
- Materialization ID: `1fdcdb0fc15d7ccef062dd69a9fb35d2f85ddff5ec6a4a0ecba035332eb28014`
- Tables: 13, with no missing or extra tables or columns
- Contract/relational/domain issues: zero

## 7. Table inventory

Every table has its exact contractual columns and dtype order. All PK null and
duplicate counts are zero; no whole-row duplicate exists. No final table is
empty. Contractual typed-empty behavior remains covered by the focal tests.

| Table | Rows | Columns | PK nulls/duplicates | FK rules/issues | Physical SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| `publication_events` | 154 | 8 | 0/0 | 0/0 | `750a501c030f3094763e58e8cb548cb1d68d7b6eadd90ac9a918ea1f91b6ce36` |
| `generation_asset_mentions` | 159 | 7 | 0/0 | 1/0 | `9dbd22f55459cc0ff4bd87a50a86b63ee117ed5007ec06356f02744a06d97d59` |
| `generation_asset_names` | 180 | 6 | 0/0 | 2/0 | `fca083355a84511c7b1e5ca573f5a2c41e64c3fcd5774f96b97048ae2d1e881b` |
| `associated_components` | 166 | 8 | 0/0 | 1/0 | `6b3e075631d634a9b43c35105c1131ea5e8386bf356b6a8552670dcc30e02fdc` |
| `associated_component_names` | 196 | 6 | 0/0 | 2/0 | `0d6dad581d19c31c81d412ae241a70163a2119fbdea84bd1c1b92ac50d91faa3` |
| `associated_component_generation_links` | 171 | 7 | 0/0 | 3/0 | `c74770ae4aeddc887acfc6e8945feb412e1d12fd7b1aad741b6fa621b53d93dd` |
| `administrative_actions` | 244 | 9 | 0/0 | 1/0 | `e421d7fc034b8dbc22f69bca8727f2e72147c7ee9e622f7756e7dceac4d8b016` |
| `administrative_action_targets` | 290 | 8 | 0/0 | 2/0 | `52a55369cfae54d07d26823d7ebaf1c025ae5e10f42d16c665fb2e1c2449d43b` |
| `participant_mentions` | 243 | 7 | 0/0 | 1/0 | `d987f055ec1265dc6487046ddde8b922a8fabd511f756e636b7e9eeaf30ea0bc` |
| `location_mentions` | 828 | 9 | 0/0 | 1/0 | `68289836090963f7c6a3622c3234c3f1c6c9d1aaaa1dd83559213af63970d364` |
| `generation_asset_relations` | 3 | 10 | 0/0 | 3/0 | `11360243a37f620297e64896a9f1d8092bffb6086d5590ab65d8a13a248be042` |
| `technical_mentions` | 630 | 11 | 0/0 | 1/0 | `eff0a9a5a516154035f61dd7be350433cc3b90159cf3a1e7ca92856f1deb79ce` |
| `case_file_references` | 171 | 6 | 0/0 | 1/0 | `745192c2a01fafa0a5e95547ccd26855250972b15cf3d90fdcd1eca539d61dfd` |

Columns in contractual order are:

- `publication_events`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `event_index`, `event_summary`,
  `n_generation_assets`, `n_associated_components`,
  `n_administrative_actions`.
- `generation_asset_mentions`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `generation_asset_mention_id`,
  `local_generation_asset_ref`, `generation_type`, `evidence`.
- `generation_asset_names`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `generation_asset_mention_id`, `name_index`,
  `name_raw`.
- `associated_components`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `associated_component_id`, `local_component_ref`,
  `component_type`, `description_raw`, `evidence`.
- `associated_component_names`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `associated_component_id`, `name_index`, `name_raw`.
- `associated_component_generation_links`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `associated_component_id`, `link_index`,
  `local_generation_asset_ref`, `generation_asset_mention_id`.
- `administrative_actions`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `administrative_action_id`, `action_index`,
  `action_type`, `decision`, `is_modification`, `evidence`.
- `administrative_action_targets`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `administrative_action_id`, `target_index`,
  `target_ref`, `target_entity_id`, `target_kind`.
- `participant_mentions`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `participant_mention_id`, `participant_name_raw`,
  `participant_role`, `evidence`.
- `location_mentions`: `event_id`, `identificador_boe`, `fecha_publicacion`,
  `location_mention_id`, `location_name_raw`, `location_level`,
  `province_hint_raw`, `autonomous_community_hint_raw`, `evidence`.
- `generation_asset_relations`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `generation_asset_relation_id`,
  `source_generation_asset_ref`, `source_generation_asset_mention_id`,
  `target_generation_asset_ref`, `target_generation_asset_mention_id`,
  `relation_type`, `evidence`.
- `technical_mentions`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `technical_mention_id`, `owner_kind`, `owner_ref`,
  `generation_asset_mention_id`, `associated_component_id`, `attribute_type`,
  `value_raw`, `evidence`.
- `case_file_references`: `event_id`, `identificador_boe`,
  `fecha_publicacion`, `case_file_reference_id`, `reference_index`,
  `case_file_reference_raw`.

## 8. PK/FK validation

`validate_flat_tables()` passed before writing, after staging read-back, in the
published loader and in an independent in-memory rebuild. It checked all 13 PK
definitions and 19 direct FK rules, including same-event coherence, local/global
references, consecutive logical indices and positional identifiers. Result:
zero PK issues and zero dangling or cross-event FK values.

Five contract-derived polymorphic branches also passed: action targets to
events, generation assets and associated components, plus technical owners on
generation assets and associated components. Discriminators, exactly-one
owner shape, target/owner IDs, local refs and event ownership produced zero
issues.

## 9. Domain validation

The production validator derives controlled values from the active enums for
`generation_type`, `component_type`, `action_type`, `decision`,
`participant_role`, `location_level`, `relation_type` and `attribute_type`.
It additionally validates target/owner discriminators. There were zero domain
violations. `classification_status` and `document_scope` are upstream
extraction fields rather than columns of the 13-table Silver contract; the
contractual extraction loader validated the input before flattening.

## 10. Manual-review regression

`BOE-B-2023-27607` remains `manually_validated` and materializes as:

- one row in `publication_events`;
- three rows in `generation_asset_mentions`: HSF ANUBIS, HSF AFRODITA and
  HSF DEMETER;
- one row in `associated_components` for the shared Atenea–Marchamorón
  evacuation infrastructure;
- three rows in `associated_component_generation_links`, targeting local refs
  `generation_asset_1`, `generation_asset_2` and `generation_asset_3`;
- one `administrative_actions` row with
  `declaracion_utilidad_publica / declarado`;
- one `administrative_action_targets` row with `target_kind` equal to
  `associated_component` and `target_ref` equal to `component_1`.

The shared DUP is represented once, and infrastructure does not become a
generation root.

## 11. Manifest and identity

The manifest records the materialization ID, flat contract version, extraction
config, creation timestamp, 104-row lineage and canonical input identity,
80/24 with/without-event counts, 154 materialized events, corrections absence,
and each table's schema, PK, row count and physical hash. The production loader
verified all those fields and hashes.

The current Silver manifest does not have separate fields named parent
extraction snapshot ID, Git/code provenance or validation status. Parentage is
captured as complete per-input identity/lineage; the exact parent path and
snapshot ID are fixed in this versioned report, while successful publication
and loader validation are the validation evidence. No field was invented.

The semantic materialization ID hashes contract version, extraction config,
canonical input identity, input counts and semantic table hashes. The
timestamp is deliberately excluded.

## 12. Round-trip

`load_flat_materialization()` reloaded exactly 13 tables and verified the
manifest, artifact set, physical hashes, PyArrow schemas, row counts, complete
relational contract and deterministic materialization ID. The reloaded table
set, schemas, dtypes, counts and identity all match; validation issues: zero.

## 13. Reproducibility

A second transformation was performed only in memory from the unchanged 104
current extractions. It used `flatten_current_extractions()`,
`apply_flat_table_types()` and `validate_flat_tables()`. After contractual PK
ordering, every value and dtype matched the published Parquet tables exactly,
all row counts matched and the recomputed ID was again
`1fdcdb0fc15d7ccef062dd69a9fb35d2f85ddff5ec6a4a0ecba035332eb28014`.
No second final directory, overwrite or `--force` was used.

## 14. Final corpus metrics

| Metric | Value |
| --- | ---: |
| Corpus BOEs | 104 |
| Relevant generation BOEs | 80 |
| Non-relevant BOEs | 24 |
| Publication events | 154 |
| Generation asset mentions | 159 |
| Administrative actions | 244 |
| Associated components | 166 |
| Administrative location mentions | 828 |
| Participant mentions | 243 |
| Case-file references | 171 |
| Generation asset relations | 3 |
| BOEs with more than one publication event | 25 |
| BOEs with more than one generation-asset mention | 29 |

The contract permits multiple assets in one integrated/shared event, so the
25-event count is the conservative structural multi-project proxy. These are
mentions and events, not canonical Gold project counts. The 24 non-relevant
BOEs correctly contribute no invented project/event rows; all 80 relevant BOEs
are traceable through `identificador_boe`, `event_id` and entity IDs.

## 15. Downstream readiness

Classification: **READY FOR DOWNSTREAM**. The current downstream CLI accepts
this Silver path directly, loads it with the contractual loader, resolves
`location_mentions`, groups only `generation_asset_mentions`, and then builds
Gold. Its required administrative dimension already exists and loads offline:

- path: `runs/ine-reference-20260614-25a3bbb28f0c21c5`;
- semantic reference ID: `25a3bbb28f0c21c5`;
- semantic reference SHA-256:
  `25a3bbb28f0c21c52dbc38e572b4fdc91385579063e6d217b18b7a67b259cfac`;
- rows: 8,132 municipalities.

No downstream stage was run during this gate.

## 16. Next gate

The next REQUIRED operation, subject to human review and authorization, is the
final deterministic downstream materialization using:

```bash
uv run python -m renewables_permitting.pipeline downstream \
  --silver-snapshot runs/final-w14-corpus-20220101-20260820-v1/silver \
  --municipality-reference runs/ine-reference-20260614-25a3bbb28f0c21c5 \
  --output-dir runs/final-w14-corpus-20220101-20260820-v1/downstream \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --dry-run
```

This command was identified from the current CLI but was not executed.
