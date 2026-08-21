# Holdout exposure provenance

## Purpose

This document records the complete, reproducible exclusion boundary for the
future final holdout. A BOE publication that was inspected during development,
evaluation design, correction or validation is not unseen data and must not be
selected for the holdout.

The authoritative exclusion set is
`config/evaluation/development_used_documents.csv`. It contains one row per
BOE. Historical uses remain unchanged; newly reconstructed exposure is recorded
with `usage_type=classifier_audit` and points back to this document.

No holdout was selected while preparing this provenance record.

## Exposure rule

A document is **development-exposed** when its content or extraction result was
shown and used to develop, audit, correct, classify or validate a system
decision. A BOE identifier merely mentioned in an operational log, synthetic
fixture, bulk path listing or download check is not exposure by itself.

Examples excluded as merely mentioned include `BOE-B-2024-24843` (retry-path
fixture) and `BOE-B-2026-10001` (synthetic hash-change input). Synthetic
`999xx`/`00000` identifiers were also excluded.

## Reconstruction method

The set was reconstructed from five independently identifiable sources:

1. the existing versioned development registry;
2. the original candidate-funnel audit and its exact deterministic sampling
   code;
3. the 82 identifiers enumerated by the period/funnel decision audit;
4. the manually reviewed source-identity drift;
5. persisted semantic inputs and outputs in the legacy development notebooks.

The original private session logs were used only to recover the lost audit
procedure and its outputs. Future exclusion does not depend on those logs:
the final BOE set is now in the versioned registry and the source membership
of every new row is recorded in the appendix below.

Identifiers were unioned and deduplicated by `identificador_boe`. The registry
remains a one-row-per-BOE exclusion registry, not a multi-use ledger.

For audit fingerprints, identifiers are sorted lexicographically, joined with
a newline, terminated with one final newline and hashed as UTF-8 with SHA-256.

| Set | Count | SHA-256 |
| --- | ---: | --- |
| Complete exposed registry | 479 | `2e9da51070304ac15d5d941cdc2f1f9861da0c71d34cb6fb64cac34905e90f80` |
| New `classifier_audit` rows | 327 | `7c35f32bcb80a8417b73e336d26354f03e8aaf296df4dde55ec6734efa6832ce` |

## Existing development registry

The historical registry contained 152 unique BOEs: 100 pilot documents, 40
development-challenge documents, 9 development examples and 3 regression
cases. Their identifiers, usage types, reasons, references and row order are
preserved exactly. If a historical BOE also appears in another source, its
original row remains authoritative and no duplicate row is added.

## Candidate funnel audit

The original stratified sample contained 72 unique BOEs from 73 selections;
`BOE-B-2024-19767` occurred in two strata and was deduplicated. The exact
sampling procedure used seed `20260820` over the historical `MODEL_REQUIRED`
frame: five random rows per year, three random rows for each of the eight most
frequent title triggers, and the first three rows for each of the eight most
frequent normalized seven-token title prefixes.

| Candidate-audit evidence | Value |
| --- | --- |
| Original sample | 72 unique BOEs |
| All BOEs semantically exposed during the audit session | 180 unique BOEs |
| Seed | `20260820` |
| Source document identity | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| Original-sample lineage fingerprint | `d3fbb14f9afb1c0431d8372b9d5eb48cab73b5ada355d6d7cd4ee25ed1c11563` |

The lineage fingerprint hashes sorted lines of
`identificador_boe|publication_date|source_document_sha256` for the 72-BOE
sample. The wider 180-BOE set includes the follow-up annual sample, section and
title-prefix censuses, R1/R2/R3/R4 samples, and the source-drift review that
informed the classifier audit.

## Period/funnel audit

The later period/funnel audit explicitly enumerated 82 unique BOEs. Its
versioned evidence remains in `docs/FINAL_CORPUS_PERIOD_AND_FUNNEL_DECISION.md`.
Thirty-three of those BOEs overlap with the 180 candidate-audit exposures; none
overlapped the historical 152-row registry.

## Source drift

`BOE-A-2026-11850` was manually inspected to resolve source identity drift.
It is already included in the 180 candidate-audit BOEs and is counted only once
in the master set.

## Legacy semantic inspection

Persisted cells and outputs in the legacy development notebooks demonstrated
semantic exposure for 195 real BOEs. Of these, 101 were absent from the
historical registry; 98 add new master IDs after overlap with the candidate and
period audits. Operational download-log tails and synthetic identifiers were
not treated as semantic exposure.

## Master set and overlaps

| Source, applied in order | Source rows | New unique BOEs |
| --- | ---: | ---: |
| Historical registry | 152 | 152 |
| Candidate audit, excluding separately reported drift | 179 | 179 |
| Period/funnel audit | 82 | 49 |
| Source drift | 1 | 1 |
| Legacy BOEs absent from the historical registry | 101 | 98 |
| **Master exposed set** |  | **479** |

Pairwise evidence overlaps relevant to the reconstruction are:

- candidate audit ∩ period audit: 33 BOEs;
- source drift ∩ candidate audit: 1 BOE;
- legacy-new ∩ candidate audit: 3 BOEs;
- legacy-new ∩ period audit: 1 BOE.

The annual master distribution is 12 BOEs from 2021, 58 from 2022, 146 from
2023, 93 from 2024, 65 from 2025 and 105 from 2026.

## P2 and P3 exclusion coverage

P2 is the canonical source interval from 1 January 2024 through 20 August
2026. Identity-only comparison against the validated local source snapshot
produced:

| Measure | Count |
| --- | ---: |
| P2 canonical BOEs | 19,489 |
| Development-exposed P2 BOEs | 263 |
| Provisional holdout-eligible P2 BOEs | 19,226 |
| Development-exposed P3 BOEs | 170 |

`19,489 - 263 = 19,226`. These counts describe the pool only; no holdout sample
has been selected and no model output was used to choose one.

## Holdout rule

Every BOE in `config/evaluation/development_used_documents.csv` must be
excluded before any future holdout selection. Any additional BOE manually
inspected during development or evaluation must first be added to that registry
under the applicable historical use or `classifier_audit`.

## Machine-auditable classifier exposure appendix

The following table contains exactly the 327 rows added as
`classifier_audit`. Multiple labels preserve overlapping provenance without
creating duplicate registry rows.

<!-- classifier-audit-provenance:start -->
| BOE | Reconstructed exposure source(s) |
| --- | --- |
| `BOE-A-2022-17801` | candidate funnel audit |
| `BOE-A-2022-1839` | candidate funnel audit |
| `BOE-A-2023-10299` | legacy semantic inspection |
| `BOE-A-2023-10305` | legacy semantic inspection |
| `BOE-A-2023-10307` | legacy semantic inspection |
| `BOE-A-2023-10308` | legacy semantic inspection |
| `BOE-A-2023-10311` | legacy semantic inspection |
| `BOE-A-2023-10317` | legacy semantic inspection |
| `BOE-A-2023-10326` | legacy semantic inspection |
| `BOE-A-2023-11003` | legacy semantic inspection |
| `BOE-A-2023-11171` | legacy semantic inspection |
| `BOE-A-2023-11179` | candidate funnel audit |
| `BOE-A-2023-11309` | legacy semantic inspection |
| `BOE-A-2023-12328` | legacy semantic inspection |
| `BOE-A-2023-12894` | candidate funnel audit |
| `BOE-A-2023-13039` | legacy semantic inspection |
| `BOE-A-2023-13045` | candidate funnel audit, legacy semantic inspection |
| `BOE-A-2023-13052` | candidate funnel audit, legacy semantic inspection |
| `BOE-A-2023-13055` | legacy semantic inspection |
| `BOE-A-2023-13064` | legacy semantic inspection |
| `BOE-A-2023-13070` | legacy semantic inspection |
| `BOE-A-2023-14818` | legacy semantic inspection |
| `BOE-A-2023-17787` | candidate funnel audit |
| `BOE-A-2023-17789` | legacy semantic inspection |
| `BOE-A-2023-17790` | legacy semantic inspection |
| `BOE-A-2023-17793` | legacy semantic inspection |
| `BOE-A-2023-1933` | legacy semantic inspection |
| `BOE-A-2023-1940` | legacy semantic inspection |
| `BOE-A-2023-21279` | legacy semantic inspection |
| `BOE-A-2023-22750` | legacy semantic inspection |
| `BOE-A-2023-25620` | candidate funnel audit |
| `BOE-A-2023-25627` | legacy semantic inspection |
| `BOE-A-2023-2575` | legacy semantic inspection |
| `BOE-A-2023-2578` | legacy semantic inspection |
| `BOE-A-2023-2581` | legacy semantic inspection |
| `BOE-A-2023-2587` | legacy semantic inspection |
| `BOE-A-2023-2591` | legacy semantic inspection |
| `BOE-A-2023-2600` | legacy semantic inspection |
| `BOE-A-2023-2601` | legacy semantic inspection |
| `BOE-A-2023-26690` | candidate funnel audit |
| `BOE-A-2023-2921` | legacy semantic inspection |
| `BOE-A-2023-3822` | legacy semantic inspection |
| `BOE-A-2023-49` | legacy semantic inspection |
| `BOE-A-2023-50` | legacy semantic inspection |
| `BOE-A-2024-11046` | candidate funnel audit |
| `BOE-A-2024-14380` | legacy semantic inspection |
| `BOE-A-2024-16665` | legacy semantic inspection |
| `BOE-A-2024-16668` | legacy semantic inspection |
| `BOE-A-2024-16670` | legacy semantic inspection |
| `BOE-A-2024-25512` | candidate funnel audit |
| `BOE-A-2024-27000` | candidate funnel audit |
| `BOE-A-2024-8598` | candidate funnel audit |
| `BOE-A-2025-10974` | candidate funnel audit |
| `BOE-A-2025-14202` | candidate funnel audit |
| `BOE-A-2025-17116` | candidate funnel audit |
| `BOE-A-2025-4246` | candidate funnel audit |
| `BOE-A-2025-5501` | candidate funnel audit |
| `BOE-A-2025-5502` | candidate funnel audit |
| `BOE-A-2025-7090` | candidate funnel audit |
| `BOE-A-2026-10210` | legacy semantic inspection |
| `BOE-A-2026-10320` | legacy semantic inspection |
| `BOE-A-2026-10654` | legacy semantic inspection |
| `BOE-A-2026-10730` | legacy semantic inspection |
| `BOE-A-2026-10974` | legacy semantic inspection |
| `BOE-A-2026-11295` | legacy semantic inspection |
| `BOE-A-2026-11673` | legacy semantic inspection |
| `BOE-A-2026-11771` | legacy semantic inspection |
| `BOE-A-2026-11850` | candidate funnel audit, source drift review |
| `BOE-A-2026-12586` | legacy semantic inspection |
| `BOE-A-2026-13448` | legacy semantic inspection |
| `BOE-A-2026-16635` | candidate funnel audit |
| `BOE-A-2026-16732` | candidate funnel audit |
| `BOE-A-2026-2868` | legacy semantic inspection |
| `BOE-A-2026-5523` | candidate funnel audit |
| `BOE-A-2026-9070` | period/funnel audit |
| `BOE-A-2026-9581` | legacy semantic inspection |
| `BOE-A-2026-9583` | legacy semantic inspection |
| `BOE-A-2026-9585` | legacy semantic inspection |
| `BOE-A-2026-9684` | legacy semantic inspection |
| `BOE-B-2021-32557` | legacy semantic inspection |
| `BOE-B-2021-32563` | legacy semantic inspection |
| `BOE-B-2021-32565` | legacy semantic inspection |
| `BOE-B-2022-10058` | candidate funnel audit |
| `BOE-B-2022-10103` | candidate funnel audit |
| `BOE-B-2022-10105` | candidate funnel audit |
| `BOE-B-2022-10109` | candidate funnel audit |
| `BOE-B-2022-10873` | candidate funnel audit |
| `BOE-B-2022-1108` | candidate funnel audit |
| `BOE-B-2022-12042` | candidate funnel audit |
| `BOE-B-2022-12047` | candidate funnel audit |
| `BOE-B-2022-1225` | period/funnel audit |
| `BOE-B-2022-12378` | candidate funnel audit |
| `BOE-B-2022-13912` | candidate funnel audit |
| `BOE-B-2022-15281` | period/funnel audit |
| `BOE-B-2022-15722` | candidate funnel audit |
| `BOE-B-2022-16569` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-1968` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-20099` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-20119` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-21983` | candidate funnel audit |
| `BOE-B-2022-22545` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-22781` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-22941` | period/funnel audit |
| `BOE-B-2022-2315` | candidate funnel audit |
| `BOE-B-2022-27735` | period/funnel audit |
| `BOE-B-2022-28523` | candidate funnel audit |
| `BOE-B-2022-28524` | candidate funnel audit |
| `BOE-B-2022-31755` | candidate funnel audit |
| `BOE-B-2022-32100` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-33258` | candidate funnel audit |
| `BOE-B-2022-33662` | candidate funnel audit |
| `BOE-B-2022-36468` | candidate funnel audit |
| `BOE-B-2022-36829` | period/funnel audit |
| `BOE-B-2022-36886` | period/funnel audit |
| `BOE-B-2022-37769` | candidate funnel audit |
| `BOE-B-2022-38363` | period/funnel audit |
| `BOE-B-2022-38988` | candidate funnel audit |
| `BOE-B-2022-40867` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-40918` | period/funnel audit |
| `BOE-B-2022-41290` | candidate funnel audit, period/funnel audit |
| `BOE-B-2022-4383` | period/funnel audit |
| `BOE-B-2022-4695` | candidate funnel audit |
| `BOE-B-2022-4743` | candidate funnel audit |
| `BOE-B-2022-6487` | candidate funnel audit |
| `BOE-B-2022-7056` | candidate funnel audit |
| `BOE-B-2022-7965` | candidate funnel audit |
| `BOE-B-2022-9743` | candidate funnel audit |
| `BOE-B-2023-10073` | candidate funnel audit |
| `BOE-B-2023-10657` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-11458` | candidate funnel audit |
| `BOE-B-2023-155` | candidate funnel audit |
| `BOE-B-2023-16478` | period/funnel audit |
| `BOE-B-2023-16840` | legacy semantic inspection |
| `BOE-B-2023-17281` | legacy semantic inspection |
| `BOE-B-2023-17825` | candidate funnel audit |
| `BOE-B-2023-18094` | candidate funnel audit |
| `BOE-B-2023-18602` | legacy semantic inspection |
| `BOE-B-2023-18972` | period/funnel audit |
| `BOE-B-2023-19076` | legacy semantic inspection |
| `BOE-B-2023-19077` | legacy semantic inspection |
| `BOE-B-2023-19563` | legacy semantic inspection |
| `BOE-B-2023-20547` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-20718` | period/funnel audit |
| `BOE-B-2023-2174` | legacy semantic inspection |
| `BOE-B-2023-2186` | legacy semantic inspection |
| `BOE-B-2023-2189` | legacy semantic inspection |
| `BOE-B-2023-2190` | legacy semantic inspection |
| `BOE-B-2023-22020` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-22764` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-2405` | candidate funnel audit |
| `BOE-B-2023-25265` | candidate funnel audit |
| `BOE-B-2023-26780` | candidate funnel audit |
| `BOE-B-2023-26905` | candidate funnel audit |
| `BOE-B-2023-28503` | candidate funnel audit |
| `BOE-B-2023-28504` | candidate funnel audit |
| `BOE-B-2023-28719` | candidate funnel audit |
| `BOE-B-2023-29010` | candidate funnel audit |
| `BOE-B-2023-29175` | candidate funnel audit |
| `BOE-B-2023-30099` | candidate funnel audit |
| `BOE-B-2023-31118` | candidate funnel audit |
| `BOE-B-2023-31129` | candidate funnel audit |
| `BOE-B-2023-31184` | candidate funnel audit |
| `BOE-B-2023-3161` | legacy semantic inspection |
| `BOE-B-2023-31657` | candidate funnel audit |
| `BOE-B-2023-3173` | legacy semantic inspection |
| `BOE-B-2023-32020` | candidate funnel audit |
| `BOE-B-2023-32028` | candidate funnel audit |
| `BOE-B-2023-32517` | period/funnel audit |
| `BOE-B-2023-32537` | period/funnel audit |
| `BOE-B-2023-32539` | candidate funnel audit |
| `BOE-B-2023-32551` | candidate funnel audit |
| `BOE-B-2023-33586` | candidate funnel audit |
| `BOE-B-2023-34365` | candidate funnel audit |
| `BOE-B-2023-34540` | candidate funnel audit |
| `BOE-B-2023-34545` | period/funnel audit |
| `BOE-B-2023-34843` | candidate funnel audit |
| `BOE-B-2023-34858` | candidate funnel audit |
| `BOE-B-2023-35011` | legacy semantic inspection |
| `BOE-B-2023-35624` | candidate funnel audit |
| `BOE-B-2023-35879` | period/funnel audit |
| `BOE-B-2023-35885` | candidate funnel audit |
| `BOE-B-2023-35968` | candidate funnel audit |
| `BOE-B-2023-36467` | candidate funnel audit |
| `BOE-B-2023-36468` | candidate funnel audit |
| `BOE-B-2023-36470` | candidate funnel audit |
| `BOE-B-2023-36472` | candidate funnel audit |
| `BOE-B-2023-36473` | candidate funnel audit |
| `BOE-B-2023-36849` | candidate funnel audit |
| `BOE-B-2023-37504` | period/funnel audit |
| `BOE-B-2023-4051` | candidate funnel audit |
| `BOE-B-2023-5470` | candidate funnel audit |
| `BOE-B-2023-5684` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-5859` | period/funnel audit |
| `BOE-B-2023-7163` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-7374` | period/funnel audit |
| `BOE-B-2023-7642` | candidate funnel audit, period/funnel audit |
| `BOE-B-2023-9376` | legacy semantic inspection |
| `BOE-B-2024-10156` | candidate funnel audit |
| `BOE-B-2024-10279` | candidate funnel audit |
| `BOE-B-2024-10859` | candidate funnel audit |
| `BOE-B-2024-10874` | candidate funnel audit |
| `BOE-B-2024-10988` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-11215` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-1181` | candidate funnel audit |
| `BOE-B-2024-12614` | period/funnel audit |
| `BOE-B-2024-12743` | candidate funnel audit |
| `BOE-B-2024-12926` | candidate funnel audit |
| `BOE-B-2024-13656` | candidate funnel audit |
| `BOE-B-2024-13997` | candidate funnel audit |
| `BOE-B-2024-15589` | period/funnel audit |
| `BOE-B-2024-16232` | period/funnel audit |
| `BOE-B-2024-16519` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-17284` | legacy semantic inspection |
| `BOE-B-2024-17292` | legacy semantic inspection |
| `BOE-B-2024-19059` | candidate funnel audit |
| `BOE-B-2024-19222` | candidate funnel audit |
| `BOE-B-2024-19281` | period/funnel audit |
| `BOE-B-2024-19766` | period/funnel audit |
| `BOE-B-2024-19767` | candidate funnel audit |
| `BOE-B-2024-20569` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-2108` | candidate funnel audit |
| `BOE-B-2024-2110` | candidate funnel audit |
| `BOE-B-2024-22461` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-24015` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-24813` | candidate funnel audit |
| `BOE-B-2024-25903` | candidate funnel audit |
| `BOE-B-2024-26575` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-26634` | period/funnel audit |
| `BOE-B-2024-26966` | candidate funnel audit |
| `BOE-B-2024-27052` | candidate funnel audit, period/funnel audit, legacy semantic inspection |
| `BOE-B-2024-27097` | legacy semantic inspection |
| `BOE-B-2024-27217` | period/funnel audit |
| `BOE-B-2024-27273` | candidate funnel audit |
| `BOE-B-2024-30934` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-31971` | period/funnel audit |
| `BOE-B-2024-33752` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-34086` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-34338` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-35786` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-37613` | candidate funnel audit |
| `BOE-B-2024-40078` | candidate funnel audit |
| `BOE-B-2024-40440` | period/funnel audit |
| `BOE-B-2024-40454` | candidate funnel audit |
| `BOE-B-2024-43565` | candidate funnel audit |
| `BOE-B-2024-45488` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-45867` | candidate funnel audit |
| `BOE-B-2024-47278` | candidate funnel audit, period/funnel audit |
| `BOE-B-2024-4999` | candidate funnel audit |
| `BOE-B-2024-6003` | candidate funnel audit |
| `BOE-B-2024-6104` | candidate funnel audit |
| `BOE-B-2024-7033` | candidate funnel audit |
| `BOE-B-2024-7951` | period/funnel audit |
| `BOE-B-2024-9691` | candidate funnel audit |
| `BOE-B-2025-11793` | candidate funnel audit |
| `BOE-B-2025-17359` | candidate funnel audit |
| `BOE-B-2025-2035` | candidate funnel audit, period/funnel audit |
| `BOE-B-2025-20664` | candidate funnel audit, period/funnel audit |
| `BOE-B-2025-20693` | period/funnel audit |
| `BOE-B-2025-27372` | candidate funnel audit |
| `BOE-B-2025-27493` | candidate funnel audit |
| `BOE-B-2025-27635` | period/funnel audit |
| `BOE-B-2025-28421` | candidate funnel audit |
| `BOE-B-2025-31461` | candidate funnel audit |
| `BOE-B-2025-32414` | candidate funnel audit |
| `BOE-B-2025-32903` | legacy semantic inspection |
| `BOE-B-2025-32975` | legacy semantic inspection |
| `BOE-B-2025-32981` | legacy semantic inspection |
| `BOE-B-2025-34190` | period/funnel audit |
| `BOE-B-2025-35280` | period/funnel audit |
| `BOE-B-2025-37280` | period/funnel audit |
| `BOE-B-2025-37985` | candidate funnel audit |
| `BOE-B-2025-38570` | period/funnel audit |
| `BOE-B-2025-39619` | period/funnel audit |
| `BOE-B-2025-42239` | candidate funnel audit |
| `BOE-B-2025-45199` | candidate funnel audit |
| `BOE-B-2025-45866` | period/funnel audit |
| `BOE-B-2025-46007` | candidate funnel audit |
| `BOE-B-2025-46945` | legacy semantic inspection |
| `BOE-B-2025-46948` | legacy semantic inspection |
| `BOE-B-2025-46958` | legacy semantic inspection |
| `BOE-B-2025-47482` | candidate funnel audit |
| `BOE-B-2025-5807` | candidate funnel audit |
| `BOE-B-2025-5961` | period/funnel audit |
| `BOE-B-2025-5999` | period/funnel audit |
| `BOE-B-2025-6095` | candidate funnel audit |
| `BOE-B-2026-10587` | candidate funnel audit |
| `BOE-B-2026-12797` | candidate funnel audit |
| `BOE-B-2026-13607` | period/funnel audit |
| `BOE-B-2026-14204` | candidate funnel audit |
| `BOE-B-2026-14390` | legacy semantic inspection |
| `BOE-B-2026-14475` | legacy semantic inspection |
| `BOE-B-2026-14572` | candidate funnel audit |
| `BOE-B-2026-15080` | legacy semantic inspection |
| `BOE-B-2026-15406` | legacy semantic inspection |
| `BOE-B-2026-15420` | legacy semantic inspection |
| `BOE-B-2026-15995` | legacy semantic inspection |
| `BOE-B-2026-16027` | legacy semantic inspection |
| `BOE-B-2026-16132` | legacy semantic inspection |
| `BOE-B-2026-16167` | period/funnel audit |
| `BOE-B-2026-16329` | legacy semantic inspection |
| `BOE-B-2026-16354` | candidate funnel audit |
| `BOE-B-2026-16423` | candidate funnel audit |
| `BOE-B-2026-16615` | legacy semantic inspection |
| `BOE-B-2026-16633` | legacy semantic inspection |
| `BOE-B-2026-17092` | legacy semantic inspection |
| `BOE-B-2026-17105` | legacy semantic inspection |
| `BOE-B-2026-17411` | legacy semantic inspection |
| `BOE-B-2026-17651` | period/funnel audit |
| `BOE-B-2026-18076` | candidate funnel audit |
| `BOE-B-2026-18476` | legacy semantic inspection |
| `BOE-B-2026-18491` | legacy semantic inspection |
| `BOE-B-2026-18554` | legacy semantic inspection |
| `BOE-B-2026-18638` | legacy semantic inspection |
| `BOE-B-2026-18652` | candidate funnel audit |
| `BOE-B-2026-18654` | candidate funnel audit |
| `BOE-B-2026-18658` | period/funnel audit |
| `BOE-B-2026-20295` | candidate funnel audit |
| `BOE-B-2026-21592` | candidate funnel audit |
| `BOE-B-2026-24899` | candidate funnel audit |
| `BOE-B-2026-25610` | candidate funnel audit |
| `BOE-B-2026-26177` | period/funnel audit |
| `BOE-B-2026-26937` | period/funnel audit |
| `BOE-B-2026-3935` | period/funnel audit |
| `BOE-B-2026-799` | period/funnel audit |
| `BOE-B-2026-8118` | candidate funnel audit |
| `BOE-B-2026-8301` | period/funnel audit |
| `BOE-B-2026-9895` | candidate funnel audit |
<!-- classifier-audit-provenance:end -->

## Limitations

This registry protects methodological independence; it does not claim that all
exposed documents were relevant extraction cases or that exposure labels are
mutually exclusive. P2/P3 counts depend on the stated source snapshot identity.
A different future source snapshot must revalidate membership by BOE identity
before holdout selection.
