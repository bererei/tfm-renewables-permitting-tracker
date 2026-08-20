# Final Corpus Preflight — 2022–2026 v2

## 1. Purpose

This source-only preflight measures the complete interval from 1 January 2022
through 20 August 2026 after the bounded BOE retry mitigation introduced in
`5919503`. It does not execute extraction, Gemini, Silver, downstream or Gold.

The BOE source stage completed, but the overall preflight is **INCOMPLETE**:
one current official BOE document has the same identifier as a local legacy
source document and a different canonical source hash. The affected document
is quarantined from extraction reuse and model planning pending a human source
identity decision.

## 2. Retry mitigation context

The v1 attempt stopped at `BOE-B-2024-24843:request_error` and remains recorded
in `docs/FINAL_CORPUS_PREFLIGHT_2022.md`. Before v2, the active implementation
was inspected and confirmed to provide:

- at most four HTTP requests per source operation: one initial request and
  three retries;
- backoff delays of 1, 2 and 4 seconds;
- retries for request connection/time-out/chunked-response errors and HTTP
  408, 429, 500, 502, 503 and 504;
- a final fail-closed result after retry exhaustion;
- fresh staging followed by atomic publication;
- no cache or resume mechanism.

## 3. Period

| Metric | Value | Status |
| --- | ---: | --- |
| Start | 2022-01-01 | MEASURED |
| End | 2026-08-20 | MEASURED |
| Boundary semantics | Inclusive | VERIFIED |
| Calendar dates requested | 1,693 | MEASURED |
| Calendar dates represented in the manifest | 1,693 | MEASURED |
| Missing or duplicate dates | 0 | MEASURED |

The cut-off is fixed, inclusive and reproducible.

## 4. Source execution

The exact source command was:

```bash
uv run python -m renewables_permitting.pipeline source \
  --start-date 2022-01-01 \
  --end-date 2026-08-20 \
  --output-dir runs/final-corpus-preflight-20220101-20260820-v2/source
```

Timing and command output were captured under `/tmp`, outside the repository.
The new destination did not exist before execution. No `--force` option, v1
artifact or source cache was used.

The stage published:

```text
runs/final-corpus-preflight-20220101-20260820-v2/source/
```

with `source_completed = true`.

## 5. Runtime

| Metric | Value | Status |
| --- | --- | --- |
| Start UTC | 2026-08-20T17:19:51Z | MEASURED |
| End UTC | 2026-08-20T21:19:35Z | MEASURED |
| Start local | 2026-08-20T18:19:51+0100 | MEASURED |
| End local | 2026-08-20T22:19:35+0100 | MEASURED |
| Wall-clock | 14,364.53 s (3 h 59 min 24.53 s) | MEASURED |
| Process exit status | 0 | MEASURED |
| Maximum resident set | 3,169,172 KiB | MEASURED |

## 6. Retry observations

The stage performed 27,040 source operations: 1,693 summary operations and
25,347 XML operations. Including retries, 27,043 HTTP requests were observed.

| Metric | Count | Status |
| --- | ---: | --- |
| Operations requiring retry | 3 | MEASURED |
| Summary operations requiring retry | 0 | MEASURED |
| XML operations requiring retry | 3 | MEASURED |
| Recovered after one retry | 3 | MEASURED |
| Recovered after two retries | 0 | MEASURED |
| Recovered after three retries | 0 | MEASURED |
| Retry exhaustion | 0 | MEASURED |

The three recovered XML operations were:

| BOE | Final request attempt | Result |
| --- | ---: | --- |
| `BOE-B-2022-37665` | 2 of 4 | downloaded |
| `BOE-B-2024-24126` | 2 of 4 | downloaded |
| `BOE-B-2025-15053` | 2 of 4 | downloaded |

`BOE-B-2024-24843`, which blocked v1, is present as one candidate, one
downloaded XML and one canonical document. It did not emit a retry log entry,
so it succeeded on the first request in v2.

## 7. Source integrity

The source manifest is valid JSON and declares stage/version `source/1`, the
requested interval, candidate policy `title_keywords_v1` with ID
`79289feae5d557be`, and document identity:

```text
1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf
```

The identity was recalculated with the production document boundary and
matched the manifest. Every physical Parquet hash and row count also matched:

| Artifact | Rows | SHA-256 | Status |
| --- | ---: | --- | --- |
| `boe_items.parquet` | 328,629 | `dde76317a97270884edeb0edb1d74068bc940d4e822d8ba2745896a6b66e0f0a` | VERIFIED |
| `candidates.parquet` | 25,347 | `1554ffe85583276b6cd2b38ab6e5c68306c481193afd25b1dace74364393da58` | VERIFIED |
| `xml_download_log.parquet` | 25,347 | `cd1b34fd882d9813767ee49fb95dcd5deb49f40b57a40ac2f8de684e2db4c164` | VERIFIED |
| `documents.parquet` | 25,347 | `324b93188953183bc84a3561f1af56f2c8c7187985f0c89f2454197ec6249190` | VERIFIED |

All 25,347 candidate IDs are unique and appear exactly once in the XML log and
canonical documents. All XML statuses are `downloaded`, all document XML
statuses are `ok`, and parse errors are zero. No staging directory remained.
The final destination appeared only after successful staging publication.

The 1,693 requested dates divide into 1,454 successful publication dates and
239 expected `no_publication` dates. There are no failed or silently omitted
dates.

## 8. Funnel

| Funnel measure | Value | Status |
| --- | ---: | --- |
| BOE items | 328,629 | MEASURED |
| Items rejected by `title_keywords_v1` | 303,282 | DERIVED |
| Candidate items | 25,347 | MEASURED |
| Candidate rate | 7.7130% | DERIVED |
| XML downloads | 25,347 | MEASURED |
| Canonical documents | 25,347 | MEASURED |
| Unique canonical BOE IDs | 25,347 | MEASURED |
| Duplicate IDs | 0 | MEASURED |
| XML/download failures | 0 | MEASURED |
| Parse failures | 0 | MEASURED |

The selector does not persist a finer rejection taxonomy. Therefore the exact
303,282-item complement can only be labelled as not matching the active title
keyword policy; no more specific rejection reasons are inferred.

## 9. Annual distribution

| Year | BOE items | Candidates/documents | Candidate rate | Publication days | No-publication days |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 66,002 | 2,240 | 3.3938% | 314 | 51 |
| 2023 | 66,331 | 3,618 | 5.4545% | 312 | 53 |
| 2024 | 75,443 | 8,258 | 10.9460% | 314 | 52 |
| 2025 | 75,405 | 7,152 | 9.4848% | 313 | 52 |
| 2026 through 20 August | 45,448 | 4,079 | 8.9751% | 201 | 31 |
| **Total** | **328,629** | **25,347** | **7.7130%** | **1,454** | **239** |

## 10. Development overlap

`config/evaluation/development_used_documents.csv` reconstructs 152 unique
development BOE IDs. Against v2:

| Measure | Count | Status |
| --- | ---: | --- |
| Versioned development BOE IDs | 152 | MEASURED |
| Present in source v2 | 143 | MEASURED |
| Outside the requested period | 9 | MEASURED |
| Source v2 documents not used in development | 25,204 | DERIVED |
| Development coverage by v2 | 94.0789% | DERIVED |
| Development overlap as share of source v2 | 0.5642% | DERIVED |

All nine absent development IDs are 2021 documents. Of the 143 present IDs,
133 have reusable frozen extractions. The other ten are versioned development
documents but do not have an approved extraction in the 140-document freeze;
they remain non-reusable.

## 11. Source identity comparison

The production `prepare_documents()` boundary was applied read-only to both
the v2 documents and the 1,266 locally available legacy source documents.
Comparison used exact `(boe_id, source_document_sha256)` identity.

| Classification | Count | Status |
| --- | ---: | --- |
| `EXACT_SOURCE_MATCH` | 1,252 | MEASURED |
| `NEW_SOURCE_DOCUMENT` | 24,094 | MEASURED |
| `BOE_MATCH_HASH_DIFFERENT` | 1 | MEASURED |

The conflict is `BOE-A-2026-11850`. The current official XML-derived text has
3,297 characters and removes a duplicated article found in the 3,300-character
legacy text:

```text
legacy:  ... nulidad de la la sección 6 bis ...
v2:      ... nulidad de la sección 6 bis ...
```

The v2 source hash is
`c95bafebaa350dbbb18b2ac36e5d5a137508a94f36045f1780832b5152259558`.
The BOE is neither a versioned development document nor part of the frozen
extractions or correction registry. This makes the conflict isolated from
reuse, but the task's source-identity gate still requires it to be quarantined
and approved by a human before any model execution. No source artifact was
changed to reconcile it.

## 12. Extraction reuse

The sole extraction reference was the validated snapshot at
`runs/canonical-140-freeze-final-candidate-20260813/extraction/`. Its 140
attempts are `ok`, `classified` and document-validation `passed`; its 140
current selections are `auto_validated`. All use the active extraction config.

Of those 140 BOEs, 133 fall in the v2 period and every one has an exact source
hash match. Seven are outside the period in 2021.

| Classification | Count | Status |
| --- | ---: | --- |
| `EXTRACTION_REUSABLE` | 133 | MEASURED |
| `EXTRACTION_NOT_REUSABLE` | 25,213 | DERIVED |
| `EXTRACTION_REUSE_CONFLICT` | 0 | MEASURED |
| Quarantined source-identity conflict | 1 | MEASURED |

The source-conflict document was not evaluated as reusable and is excluded
from authorised model work.

## 13. Deterministic classification

The production `build_extraction_plan()` and
`preclassify_document_without_model()` functions were run read-only with model
execution disabled. Before the source quarantine, the production plan measured
133 compatible extractions, 1,602 deterministic decisions and 23,612 model-
required documents. The conflicted BOE belongs to that last raw category.

After enforcing the source-identity gate:

| Classification | Count | Status |
| --- | ---: | --- |
| `EXTRACTION_REUSABLE` | 133 | MEASURED |
| `DETERMINISTIC_NO_MODEL` | 1,602 | MEASURED |
| `MODEL_REQUIRED` authorised after quarantine | 23,611 | DERIVED |
| Source identity conflicts/errors | 1 | MEASURED |
| **Canonical document universe** | **25,347** | **RECONCILED** |

The exact reconstruction is:

```text
25,347 = 133 + 1,602 + 23,611 + 1
```

The reusable extraction rate is 0.5247%. The total no-model rate is 6.8450%.

## 14. Net model requirement

`MODEL_REQUIRED` is 23,611 documents after quarantining the source conflict,
or 93.1511% of all canonical documents. The unquarantined production
preclassifier count is 23,612.

| Year | Reusable | Deterministic | Model required | Conflict | Total |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 10 | 256 | 1,974 | 0 | 2,240 |
| 2023 | 32 | 304 | 3,282 | 0 | 3,618 |
| 2024 | 28 | 316 | 7,914 | 0 | 8,258 |
| 2025 | 25 | 415 | 6,712 | 0 | 7,152 |
| 2026 through 20 August | 38 | 311 | 3,729 | 1 | 4,079 |
| **Total** | **133** | **1,602** | **23,611** | **1** | **25,347** |

Gemini and other model calls during this preflight were exactly zero.

## 15. Extraction configuration

The active code and frozen manifest agree:

| Field | Value | Status |
| --- | --- | --- |
| Provider | `gemini` | VERIFIED |
| Model | `google:gemini-2.5-flash` | VERIFIED |
| Extraction config ID | `8158661f76a31c87` | VERIFIED |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` | VERIFIED |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` | VERIFIED |
| Document validation version | `25` | VERIFIED |

No agent was constructed or executed.

## 16. Runtime evidence

The frozen attempt metadata contains 123 model-backed documents and 17
deterministic reissues. The model-backed records preserve 1,951.17 seconds of
source attempt duration, 138 provider requests, 1,634,596 input tokens and
434,378 output tokens. The derived throughput is 226.94 documents per summed
provider-hour. All 123 records are successful; 108 used one request and 15 used
two. The metadata does not distinguish whether each second request came from
agent validation or transient retry.

Linear scaling of this small, selected development sample to 23,611 documents
gives 104.04 summed provider-hours and about 397 million total tokens. This is
only a workload indicator: it is not a wall-clock forecast and does not cover
rate limits, future document mix, failures, review, checkpoints or provider
availability. Therefore:

```text
EXTRACTION_DURATION = UNKNOWN
MONETARY_COST = UNKNOWN
```

No contractual local pricing source exists, so no monetary estimate is made.
The runtime contract permits at most six model requests per document, with one
document-validation retry and up to two transient run attempts per invocation.
For the quarantined 23,611-document set, the minimum is 23,611 provider
requests and the contractual cap is 141,666. These are bounds, not a forecast.

## 17. Human review

Automated controls can validate schemas, canonicalization, evidence and
document invariants; select compatible valid attempts; build a blocking review
queue; validate lineage; and prevent publication while blocking rows remain.

Human work remains necessary for semantic audit, ambiguous/uncertain outputs,
provider or document-validation failures, correction decisions, final corpus
approval and the later holdout. The exact number of human review rows is
`UNKNOWN`; one model document is not assumed to equal one human review.

For 2022 alone, 1,974 documents require model processing. Relative to the
140-document validated baseline and the 26 versioned challenge audit decisions
(17 v1 and 9 v2), the review and approval exposure is classified **VERY HIGH**.
This is a scale classification, not an invented queue count.

## 18. Corrections

The versioned registry contains five corrections over three BOEs:

| BOE | Correction count | Present in v2 | Source hash compatible |
| --- | ---: | --- | --- |
| `BOE-A-2024-9608` | 2 | yes | yes |
| `BOE-A-2024-16662` | 2 | yes | yes |
| `BOE-A-2025-26110` | 1 | yes | yes |

The production correction loader and application function were exercised in
memory against the frozen current extractions and snapshot identity
`55582e7cc0ce6262fc43fbb5a6cb482a03f794d8d68956e01d4b9e081e0de855`.
All five fingerprints found exactly one target and all five corrections were
applicable. The input DataFrame remained unchanged.

```text
CORRECTION_REGISTRY_COMPLETE_APPLICABLE = YES
CORRECTION_CONFLICTS = 0
```

## 19. Holdout-eligible pool

No holdout was selected or inspected case by case. Removing every one of the
152 versioned development BOE IDs from source v2 leaves 25,204 eligible
documents, or 99.4358% of source v2.

| Year | Holdout-eligible documents |
| ---: | ---: |
| 2022 | 2,229 |
| 2023 | 3,584 |
| 2024 | 8,229 |
| 2025 | 7,126 |
| 2026 through 20 August | 4,036 |
| **Total** | **25,204** |

The pool is quantitatively sufficient for a later holdout definition. Its
existence does not authorise selection before extraction/review and functional
policy are frozen.

## 20. Source reliability

```text
SOURCE RELIABILITY ACCEPTABLE
```

The source stage covered all 1,693 dates, completed all 27,040 operations,
recovered all three transient XML failures, exhausted no retries and published
atomically after 3.99 hours. This is positive operational evidence for the
retry mitigation. The separate source-identity drift is a provenance decision,
not a transport reliability failure.

## 21. Storage

| Measure | Size | Status |
| --- | ---: | --- |
| Complete source snapshot | 1,053,506,147 bytes (1.0535 GB; 0.9811 GiB) | MEASURED |
| `summaries/` | 323,137,891 bytes | MEASURED |
| `xml/` | 553,816,446 bytes | MEASURED |
| `boe_items.parquet` | 48,691,006 bytes | MEASURED |
| `candidates.parquet` | 6,074,048 bytes | MEASURED |
| `documents.parquet` | 112,608,655 bytes | MEASURED |
| `manifest.json` | 6,611,578 bytes | MEASURED |
| `xml_download_log.parquet` | 2,562,427 bytes | MEASURED |
| Files | 53,846 | MEASURED |
| Free local filesystem space | 859,246,354,432 bytes (about 859.2 GB) | MEASURED |
| Filesystem use | 17% | MEASURED |

Disk risk is **LOW**. No artifact was deleted.

## 22. Deadline assessment

```text
DEADLINE CLASSIFICATION = RED
```

Source is no longer the critical reliability blocker, but only 6.8450% of the
corpus avoids model execution. The admissible plan still contains 23,611 model
documents, unknown model wall-clock duration, a very high review exposure and
one unresolved source identity. After 20 August only eleven full calendar days
remain before delivery, while Final Corpus Build, correction/review, Gold,
dashboard MUST SHIP work, geometries, deployment, holdout, screenshots,
reproducibility and written documentation are still scheduled. The measured
source runtime alone does not drive this classification.

## 23. Period recommendation

The required exact recommendation regarding 2021 is:

```text
HUMAN DECISION REQUIRED
```

Do not proceed to 2021 while the source identity gate is unresolved and the
2022 start already produces a RED deadline assessment. A human must first
decide whether the current official text of `BOE-A-2026-11850` supersedes the
legacy local source and then approve a feasible final temporal scope. The
preflight does not change that scope automatically.

If a marginal 2021 measurement is nevertheless approved later, an independent
2021-01-01 through 2021-12-31 source-only snapshot is the smallest sufficient
way to measure its additional items, candidates and source cost. It does not
require repeating 2022–2026 merely for measurement. If 2021 is selected for
the actual final corpus, the current CLI's single-snapshot boundary means a
fresh full 2021–2026 source build is the reproducible final-build strategy;
manual snapshot merging is not approved.

## 24. Next decision

1. Human review must resolve the isolated official-source hash drift without
   editing generated artifacts.
2. Human review must choose a feasible final period in light of the RED
   schedule and 23,611 model-required documents.
3. Only after both decisions may a new, explicitly authorised Final Corpus
   Build begin.

Until then:

```text
2022 SOURCE PREFLIGHT V2 INCOMPLETE
```
