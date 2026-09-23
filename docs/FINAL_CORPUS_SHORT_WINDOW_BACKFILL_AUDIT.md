# Final Corpus Short-Window Backfill Audit

## 1. Decision

This offline audit compares four fixed anchor windows ending on the contractual
cutoff, 2026-08-20, in traditional mode and with conservative historical
backfill from 2022-01-01.

The decision is:

```text
INSUFFICIENT EVIDENCE — RUN SMALL ANCHOR PILOT FIRST
```

The exact pilot candidate is **W14**, 2026-08-07 through 2026-08-20. Its
non-holdout model scope contains 48 documents, six already have compatible
current extractions and **42 new anchor calls** would be needed. At observed
rates that is 0.207 provider hours and USD 0.5169; the conservative endpoint is
0.214 hours and USD 0.5504.

This report does not authorize that pilot. It does not change the final corpus,
implement history retrieval, execute either remaining `main-03` retry, execute
`main-04`, inspect or execute the holdout, or call any service.

W14 is the only credible short-window product candidate: it already exposes
eight projects, four autonomous communities and four action types, and its
provisional central projection is 34 projects. However, only 6 of its 48
non-holdout model documents have been extracted. That is insufficient evidence
to approve a corpus pivot or a new retrieval contract.

## 2. Current P2 baseline

The source snapshot is unchanged and has the expected contractual document
identity:

```text
1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf
```

It covers 2022-01-01 through 2026-08-20 and contains 328,629 BOE items,
25,347 canonical candidates and 25,347 parsed documents.

| P2 property | Documents |
| --- | ---: |
| Canonical P2 documents | 19,489 |
| Deterministic, no model | 14,452 |
| `MODEL_REQUIRED` | 5,037 |
| Attempted in `main-01`…`main-03` | 750 |
| Pending non-holdout mains | 4,239 |
| Sealed holdout | 48 |
| **Fresh model documents remaining** | **4,287** |
| Separate operational retries pending | 2 |

The 753 persisted real model attempts for 750 documents consumed 7,525,777
input tokens, 2,789,406 output/thinking tokens and 3.6889 accumulated provider
hours. At the versioned Standard prices of USD 0.30/M input tokens and USD
2.50/M output/thinking tokens, paid cost is USD 9.2312481.

| Remaining-P2 estimate | Provider hours | USD |
| --- | ---: | ---: |
| Lower observed scope rate | 19.84 | 46.43 |
| Aggregate observed rate | 21.09 | 52.77 |
| Conservative observed scope rate | 21.87 | 56.18 |

These 4,287 fresh documents and their cost projection do not include the two
pending retries. The retries remain unauthorized and are not needed for this
audit.

## 3. Window definitions

The dates are fixed before inspecting project yield; no day was moved to make
a window more attractive.

| Window | Start | End | Days | Historical search |
| --- | --- | --- | ---: | --- |
| W1 | 2026-08-20 | 2026-08-20 | 1 | 2022-01-01…2026-08-19 |
| W3 | 2026-08-18 | 2026-08-20 | 3 | 2022-01-01…2026-08-17 |
| W7 | 2026-08-14 | 2026-08-20 | 7 | 2022-01-01…2026-08-13 |
| W14 | 2026-08-07 | 2026-08-20 | 14 | 2022-01-01…2026-08-06 |

The historical search always stops before the anchor start. Tier 3 is excluded.

## 4. Traditional-mode funnels

To keep the holdout sealed, `MODEL_REQUIRED` below means the exact executable
non-holdout rows already registered in versioned `main-*` scopes. “Outside
main model scope” is the exact remaining candidate count; it contains
deterministic no-model rows and any sealed holdout row, which this audit does
not open or identify.

| Window | BOE items A/B | Canonical candidates A/B | Outside main model scope | `MODEL_REQUIRED` A/B | Reusable | Anchor new calls | Blocked/non-reusable |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| W1 | 115: 50/65 | 20: 1/19 | 16 | 4: 1/3 | 1 | 3 | 0 |
| W3 | 327: 110/217 | 54: 7/47 | 43 | 11: 5/6 | 2 | 9 | 0 |
| W7 | 779: 271/508 | 87: 13/74 | 65 | 22: 11/11 | 2 | 20 | 0 |
| W14 | 1,935: 808/1,127 | 173: 27/146 | 125 | 48: 25/23 | 6 | 42 | 0 |

Traditional mode has no pre-anchor chronology. Even if its projected project
count is useful, publication spans are bounded by 0, 2, 6 or 13 days and the
currently observed anchor grouping contains no multi-publication project.

## 5. Existing extraction reuse

Reuse was checked against the latest semantically valid cumulative snapshot:

```text
runs/final-tfm-p2-20240101-20260820-v1/
extraction-main-03-recanonicalized-v2
```

Compatibility requires exact equality of BOE ID, source document SHA-256,
extraction config ID, instructions SHA-256 and contract SHA-256. All observed
anchor extractions are compatible; none of the two operational errors belongs
to these windows.

| Window | Anchor model documents | Already paid/reusable | New anchor calls | Reuse rate |
| --- | ---: | ---: | ---: | ---: |
| W1 | 4 | 1 | 3 | 25.00% |
| W3 | 11 | 2 | 9 | 18.18% |
| W7 | 22 | 2 | 20 | 9.09% |
| W14 | 48 | 6 | 42 | 12.50% |

The low percentages do not indicate an identity problem. The first three main
scopes are a deterministic hash sample of the full P2 model universe, not a
chronological execution.

## 6. Observed anchor projects

Available current extractions were flattened, resolved against the production
INE dimension and grouped with `group_projects()` in memory. No parallel
project-grouping rule was introduced.

| Window | Extracted model docs | Generation docs | Events | Asset mentions | Observed projects | Anchor multi-publication projects | Coverage assessment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| W1 | 1/4 | 1 | 1 | 1 | 1 | 0 | INSUFFICIENT |
| W3 | 2/11 | 2 | 2 | 2 | 2 | 0 | INSUFFICIENT |
| W7 | 2/22 | 2 | 2 | 2 | 2 | 0 | INSUFFICIENT |
| W14 | 6/48 | 4 | 8 | 8 | 8 | 0 | PARTIAL |

W1 observes `FV Ekienea`. W3 and W7 add `Ges`, whose three-character name is
deliberately unusable as a retrieval signature. W14 additionally observes five
independent Envatios/Los Pradillos projects and `Carina Solar 10`.

The broader compatible 2026 hash sample supplies calibration rather than
pretending that one or two projects are representative: 154 extracted model
documents include 69 generation documents, 113 asset mentions and 109
production-grouped projects.

## 7. Historical signatures

Each in-memory project signature uses only:

- exact normalized documentary generation names;
- explicit aliases;
- production grouping name keys;
- distinctive name tokens;
- generation technology;
- resolved municipality, province and autonomous-community terms as
  corroboration.

Promoter, power, embeddings, fuzzy edit distance and associated grid or storage
names are not requirements. Infrastructure never creates a generation root.

Generic tokens such as `solar`, `eólico`, `fotovoltaico`, `parque`, `planta`
and `proyecto` cannot establish a candidate. Very short names such as `Ges`
also cannot establish one.

## 8. Tier-1 retrieval

Tier 1 requires an exact normalized documentary alias that is lexically usable
and corpus-distinctive. A phrase is rejected when it occurs in more than
`max(10, 0.05% of the searched corpus)` documents.

Observed short-window results are:

| Window | Tier-1 project↔BOE links | Unique historical BOEs | Reusable | New calls | Projects with candidate history |
| --- | ---: | ---: | ---: | ---: | ---: |
| W1 | 4 | 4 | 0 | 4 | 1 |
| W3 | 4 | 4 | 0 | 4 | 1 |
| W7 | 4 | 4 | 0 | 4 | 1 |
| W14 | 6 | 6 | 0 | 6 | 2 |

All four W1/W3/W7 matches belong to `FV Ekienea`. W14 adds two exact matches
for `Envatios XXIV Fase I`. No short-window historical BOE is linked to more
than one observed project.

## 9. Strict Tier-2 retrieval

Strict Tier 2 requires all distinctive project-name tokens plus at least one
corroboration from compatible technology or resolved territory. It also
requires either two distinctive tokens with a rare alphabetic token, or one
rare token of at least seven characters occurring in no more than three
documents. Tier-1 matches are removed before Tier 2.

Strict Tier 2 adds no match for the currently observed W1/W3/W7/W14 projects.
This is a precision-preserving result, not a reason to relax the rule.

On the 109-project calibration cohort, Tier 1+2 produces 177 project-document
links and 145 unique historical BOEs: 140 unique BOEs appear in Tier 1 and 11
in Tier 2, with overlap across projects/tiers. Deduplication removes 32 excess
link-level extraction decisions. The 145 unique documents resolve to 16
compatible reuses, three deterministic no-model decisions and 126 projected
new model calls.

Tier 3 is explicitly excluded from the proposed TFM backfill because the prior
audit demonstrated low precision and ambiguous volume.

## 10. Precision

Precision uses only historical links that already have a compatible current
extraction. No new document was manually inspected.

| Tier | Evaluated links | Confirmed related | False positive | Ambiguous | Conservative precision |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tier 1 | 18 | 11 | 0 | 7 | 61.11% |
| Tier 2 strict | 3 | 0 | 0 | 3 | 0.00% |

Tier 1 has 100% precision among the 11 decisive evaluated links, but treating
seven ambiguous links as if they were confirmed would be unsupported. Tier 2
strict has no observed false positive but also no confirmed link; its precision
is therefore **insufficiently evidenced**, not proven high.

The short-window candidate sets themselves have no compatible historical
extraction and consequently have `UNKNOWN` local precision. This is the main
reason not to approve backfill before the pilot.

## 11. Historical recall

The regression reuses only development-exposed evidence recorded by the prior
versioned audit. It simulates knowing the latest project publication and asks
whether strict retrieval recovers its known earlier BOEs.

| Project | Expected earlier BOEs | Tier 1 recovered | Tier 1+2 recovered | Missed |
| --- | ---: | ---: | ---: | ---: |
| Badulaque | 3 | 3 | 3 | 0 |
| Volateo Solar | 1 | 1 | 1 | 0 |
| La Puebla 1 | 1 | 1 | 1 | 0 |
| **Total** | **5** | **5** | **5** | **0** |

Observed recall is 100% (5/5), but it covers only three projects with stable,
distinctive names. It does not establish recall for complete renames,
infrastructure-only references, geography changes or severe spelling variants.

## 12. Chronology richness

The following are deterministic candidate-chronology measures, not claims of a
complete legal lifecycle.

| Window | Observed projects with pre-anchor history | ≥2 years | ≥3 years | ≥4 years | Earliest | Median span days | P75 | Max | Median/max BOE per project |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| W1 | 1/1 | 1 | 1 | 1 | 2023 | 1,224 | 1,224 | 1,224 | 5/5 |
| W3 | 1/2 | 1 | 1 | 1 | 2023 | 612 | 918 | 1,224 | 3/5 |
| W7 | 1/2 | 1 | 1 | 1 | 2023 | 612 | 918 | 1,224 | 3/5 |
| W14 | 2/8 | 2 | 2 | 1 | 2022 | 0 | 306 | 1,623 | 1/5 |

The zero W14 median is correct: six of eight observed projects have only their
anchor publication, while two have long candidate histories.

The larger calibration cohort provides a less volatile planning reference:
55/109 projects have candidate history across at least two years, 27 span at
least three years and 11 span at least four. Earliest year is 2022, median span
is 226 days, P75 is 846, maximum is 1,623, median BOE/project is two and maximum
is ten.

## 13. Full-window projections

Project bounds reuse the previously versioned representative 2026 hash-sample
projection rates rather than extrapolating from each tiny window. Historical
candidate/call bounds use the strict calibration ratios over 109 projects and
never fall below the candidates already observed in a window.

These are planning estimates, not a corpus contract:

| Window | Projects lower/central/upper | Historical candidates lower/central/upper | Historical reusable lower/central/upper | Historical new calls lower/central/upper | Projects with history central | ≥3-year projects central |
| --- | --- | --- | --- | --- | ---: | ---: |
| W1 | 2 / 3 / 4 | 4 / 4 / 5 | 0 / 0 / 1 | 4 / 4 / 5 | 2 | 1 |
| W3 | 6 / 8 / 11 | 8 / 11 / 15 | 1 / 1 / 2 | 7 / 9 / 13 | 4 | 2 |
| W7 | 11 / 16 / 22 | 15 / 21 / 29 | 2 / 2 / 3 | 13 / 18 / 25 | 8 | 4 |
| W14 | 25 / 34 / 48 | 33 / 45 / 64 | 4 / 5 / 7 | 29 / 39 / 55 | 17 | 8 |

The project cohort is defined by anchor activity. Historical extraction enriches
those project chronologies; it is not allowed to silently redefine the anchor
cohort merely because a multi-project BOE contains another generation root.

## 14. Cost and runtime

Traditional anchor-only mode uses exact remaining calls. Backfill values are
lower/central/conservative projections from today and already exclude paid
anchor extractions.

| Window | Traditional new calls | Traditional expected hours/USD | Traditional conservative hours/USD | Backfill total calls L/C/U | Backfill hours L/C/U | Backfill USD L/C/U |
| --- | ---: | --- | --- | --- | --- | --- |
| W1 | 3 | 0.015 / 0.0369 | 0.015 / 0.0393 | 7 / 7 / 8 | 0.032 / 0.034 / 0.041 | 0.076 / 0.086 / 0.105 |
| W3 | 9 | 0.044 / 0.1108 | 0.046 / 0.1180 | 16 / 18 / 22 | 0.074 / 0.089 / 0.112 | 0.173 / 0.222 / 0.288 |
| W7 | 20 | 0.098 / 0.2462 | 0.102 / 0.2621 | 33 / 38 / 45 | 0.153 / 0.187 / 0.230 | 0.357 / 0.468 / 0.590 |
| W14 | 42 | 0.207 / 0.5169 | 0.214 / 0.5504 | 71 / 81 / 97 | 0.329 / 0.398 / 0.495 | 0.769 / 0.997 / 1.271 |

Central projected savings versus the 4,287-document remaining P2 baseline are:

| Window | Calls saved | Percent | Provider hours saved | USD saved |
| --- | ---: | ---: | ---: | ---: |
| W1 | 4,280 | 99.84% | 21.05 | 52.68 |
| W3 | 4,269 | 99.58% | 21.00 | 52.54 |
| W7 | 4,249 | 99.11% | 20.90 | 52.30 |
| W14 | 4,206 | 98.11% | 20.69 | 51.77 |

The savings are material for every window. They do not remove human review,
implementation, validation, Silver, Gold, deployment or deadline risk.

## 15. Streamlit suitability

| Window | Diversity currently observed | Project projection | Product assessment | Main risk |
| --- | --- | --- | --- | --- |
| W1 | One BOE-B project, one province/CCAA, three action types | 2–4 | TOO SMALL FOR DEMO | Almost no breadth |
| W3 | Two projects, A+B, two provinces/CCAA, three action types | 6–11 | MINIMAL BUT USABLE — UNCERTAIN | Only 2/11 extracted |
| W7 | Same two observed projects; balanced A/B model scope | 11–22 | MINIMAL BUT USABLE — IF VALIDATED | Only 2/22 extracted |
| W14 | Eight projects, A+B, four provinces/CCAA, four action types | 25–48 | GOOD DEMO CORPUS — CANDIDATE | Only 6/48 extracted |

W14 is the smallest evaluated window that plausibly supports both KPIs, the
territorial map, publication evolution, administrative situations, project
list and detailed chronology. It is not yet an approved corpus because its
project yield and retrieval precision remain partially observed.

The central planning comparison is:

| Window | Days | Anchor model | Reusable | Anchor new | Historical candidates | Historical reusable | Historical new | Total new | Projects | Projects with history | Median span days | ≥3 years | USD | Hours | Demo quality | Methodological risk | Implementation risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| W1 | 1 | 4 | 1 | 3 | 4 | 0 | 4 | 7 | 3 | 2 | 1,224 | 1 | 0.086 | 0.034 | TOO SMALL FOR DEMO | High: one observed project | Medium-high: retrieval stage absent |
| W3 | 3 | 11 | 2 | 9 | 11 | 1 | 9 | 18 | 8 | 4 | 612 | 2 | 0.222 | 0.089 | MINIMAL BUT USABLE — UNCERTAIN | High: 2/11 extracted | Medium-high: retrieval stage absent |
| W7 | 7 | 22 | 2 | 20 | 21 | 2 | 18 | 38 | 16 | 8 | 612 | 4 | 0.468 | 0.187 | MINIMAL BUT USABLE — IF VALIDATED | High: 2/22 extracted | Medium-high: retrieval stage absent |
| W14 | 14 | 48 | 6 | 42 | 45 | 5 | 39 | 81 | 34 | 17 | 0 | 8 | 0.997 | 0.398 | GOOD DEMO CORPUS — CANDIDATE | Medium-high: 6/48 extracted and local precision unknown | Medium-high: retrieval stage absent |

## 16. Incremental daily operation

Traditional daily operation remains conceptually possible:

```text
new one-day source
→ deterministic pre-model classification
→ reuse compatible BOEs
→ extract only remaining BOEs
→ Silver → grouping → Gold
```

Tracker mode adds one bounded branch:

```text
new BOE
→ already processed?
→ extract if needed
→ known project?
   ├─ yes: add the publication
   └─ no: derive a versioned project signature
           → search accumulated historical source
           → reuse compatible BOEs
           → extract only new unique BOEs
```

A new explicit alias may rerun deterministic historical retrieval without
calling the model for any already compatible BOE.

If W14 is later approved, Final TFM corpus mode would fix W14 plus history from
2022. Operational daily mode would process one new day and backfill only newly
observed projects. The traditional one-day mode without backfill must remain
available.

## 17. Overlap and reuse

Document identity is independent of project-document candidate identity:

- one BOE found for N projects produces N traceable candidate links but at most
  one extraction;
- a compatible extracted BOE produces zero Gemini calls;
- the same BOE with a different source hash fails closed as source drift;
- new aliases append candidate relations but do not mutate attempts;
- deterministic ordering and candidate-manifest identity are required.

This audit found no multi-project historical BOE in the tiny window-specific
sets, but the 109-project calibration has 177 links for 145 unique documents,
demonstrating why document-level deduplication is contractual.

## 18. Minimal implementation

No implementation is justified before the W14 pilot gate. If a human GO is
later given, the smallest coherent patch is:

- new focused module `src/renewables_permitting/project_history.py`;
- pure public functions equivalent to `build_project_signatures()`,
  `retrieve_project_history_candidates()`,
  `validate_project_history_candidates()` and
  `materialize_project_history_candidates()`;
- one versioned `project_history_candidates` Parquet plus manifest and one
  deduplicated extraction-scope CSV;
- tests in `tests/test_project_history.py` and minimal CLI integration tests.

The candidate contract needs cohort/signature versions, project ID, BOE ID,
publication date, source SHA-256, tier, literal match reason/evidence, reuse
disposition and anchor lineage. Tests must cover exact aliases, generic-token
rejection, strict corroboration, infrastructure non-roots, Tier-3 exclusion,
multi-project deduplication, compatible reuse, source drift, sealed-holdout
exclusion, empty outputs, deterministic ordering and manifest round trips.

The existing CLI already supports source date ranges, extraction scopes,
cumulative attempts, Silver and downstream. It does not have a project-history
candidate stage and `run` cannot derive an anchor cohort and then extend it
historically in one invocation.

The least disruptive interface is a separate planning/materialization command,
conceptually:

```text
pipeline history
  --anchor-downstream ...
  --source-documents ...
  --anchor-start 2026-08-07
  --anchor-end 2026-08-20
  --history-start 2022-01-01
  --output-dir ...
```

Its deduplicated scope then feeds the existing `extract`, `silver` and
`downstream` stages. Adding a speculative all-in-one tracker orchestrator before
validating the candidate contract would increase deadline risk.

## 19. Methodology

The exact public wording if W14 is later approved is:

> Proyectos de generación con actividad publicada en el BOE durante la
> ventana ancla 2026-08-07 a 2026-08-20, con reconstrucción retrospectiva
> conservadora de sus publicaciones relacionadas observadas desde 2022.

Required limitations are:

- this is not an exhaustive census of generation projects;
- a chronology contains observed BOE publications, not a complete legal
  lifecycle;
- retrospective search prioritizes precision over exhaustive recall;
- absence of a match does not demonstrate absence of a publication;
- the cohort excludes projects without a publication in the anchor window;
- unresolved candidate links cannot be presented as confirmed history.

The existing sealed 48-document holdout remains an extraction-quality
evaluation for P2 and was not opened. It must not be relabelled as a retrieval
evaluation. A later history-retrieval evaluation needs a separate untouched set
of project-document relationships. No holdout artifact changes in this audit.

The audit was entirely offline: Gemini calls, BOE calls, other model calls and
web requests were all zero. No extraction, Silver, downstream or Gold stage was
executed. `runs/`, source, code, tests and configuration remained unchanged.

## 20. Recommendation

W1 is too small. W3 and W7 remain dominated by one distinctive longitudinal
project and cannot yet demonstrate product breadth. W14 has the best balance:
42 bounded new anchor calls, eight already observed projects, multiple
territories/actions and two long candidate histories. Its incomplete 6/48
coverage nevertheless prevents an immediate GO.

The next human gate should authorize or reject only this bounded action:

```text
W14 anchor pilot
MODEL_REQUIRED non-holdout: 48
already reusable: 6
new model calls: 42
expected provider hours / USD: 0.207 / 0.5169
conservative provider hours / USD: 0.214 / 0.5504
historical model calls during pilot: 0
```

After review of the completed anchor, rebuild production grouping in memory,
repeat strict Tier-1/Tier-2 retrieval and make a separate GO/NO-GO decision on
implementation. Until then, P2 remains the current corpus decision, `main-04`
is paused, the two retries remain unauthorized and the holdout remains
unexecuted.

```text
INSUFFICIENT EVIDENCE — RUN SMALL ANCHOR PILOT FIRST
```
