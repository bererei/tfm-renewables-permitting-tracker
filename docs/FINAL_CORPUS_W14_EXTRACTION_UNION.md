# Final W14 Extraction Union

## 1. Purpose

This block closes the offline extraction boundary of the final W14 corpus. It
combines the complete contractual histories of the anchor and conservative
historical scopes into one loader-valid extraction snapshot that can be passed
directly to `pipeline silver`. Silver, downstream, Gold and the holdout were
not executed.

## 2. Parent snapshots

The original anchor remains immutable at:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/extraction-final
snapshot identity: e7b7a5408f1420cf37ef4037502942fdd4e59536fa320b2ca16a4225e284623a
documents/current/blockers: 48/48/0
attempts: 110
```

Its deterministic provenance predated the final historical snapshot. The
authorised offline replay therefore published a new, semantically equivalent
parent without overwriting the original:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/extraction-final-v2
snapshot identity: d97afde9b9a9a2528bda69e97b4ae853fb813aa6efe78ebb941bc74b61775be9
documents/current/blockers: 48/48/0
attempts: 158
```

The replay preserved all 110 source attempts, added 48 deterministic attempts,
made zero model calls and left all 48 extraction payloads unchanged.

The historical parent is:

```text
runs/final-w14-anchor-pilot-20260807-20260820-v1/history-extraction-final-v2
snapshot identity: 8301be4e929cc9a029a94b496a8f564646f3c71b3e6f3cfa736046f69aef01e3
documents/current/blockers: 56/56/0
attempts/manual reviews: 128/1
```

## 3. Compatibility gate

The original pair was classified as `OFFLINE_RECANONICALIZATION_REQUIRED`:
the anchor declared deterministic code SHA
`099233062fe79e7e81144130224251484b32a21071bb082a682037260f050bbd`,
while history and the active implementation declare
`c178e23ade7cdaf0214dacca57dfe8f614fa685bb4debe96fcda9f866a237b66`.
After replay, both final parents agree on:

- source snapshot
  `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf`;
- extraction config `4b54b89dbfe8640e`;
- instructions SHA
  `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580`;
- contract SHA
  `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c`;
- model `gemini` / `google:gemini-2.5-flash`;
- scope policy `binary_named_generation_pre_model_guard_v4`;
- document validation version `25`;
- recanonicalisation materialisation version `2` and active deterministic
  code provenance.

The operation requires the common source explicitly and verifies that every
parent BOE and source-document hash belongs to it. The parent BOE sets are
48 and 56, their intersection is zero and their union is 104.

## 4. Union contract

`pipeline extraction-union` operation version `1` accepts at least two
disjoint extraction snapshots, one common source snapshot and a new output
path. It loads every parent contractually, preserves the complete attempts and
manual reviews, then recomputes effective selections and the review queue with
the production functions. It does not combine persisted
`current_extractions` or parent queues.

The output is `snapshot_type = extraction_union`. A valid empty parent is
accepted and contributes lineage without adding rows. Parents are sorted by
snapshot identity, so input order does not affect the semantic identity.

## 5. Attempt preservation

The final parents contribute 158 anchor attempts and 128 historical attempts.
Their attempt-ID intersection is zero. The union contains 286 rows, 286 unique
attempt IDs and zero duplicates, including errors, successes, retries and
deterministic/recanonicalised attempts. No attempt was changed or discarded.

## 6. Manual-review preservation

The anchor contributes zero manual reviews and history contributes one. The
union preserves that review and revalidates its source attempt, BOE, source
hash, config, validation version and corrected extraction. The final selection
counts are 103 `auto_validated` and one `manually_validated`; there are no
rejected documents in this union.

## 7. Collision policy

Version 1 fails closed before publication on:

- repeated parents or parent identities;
- BOE overlap;
- attempt or non-null manual-review ID collisions;
- source BOEs absent from the common source or source-hash conflicts;
- config, instructions, contract, model, policy or validation mismatch;
- stale or internally inconsistent deterministic provenance;
- corrupt artifacts/manifests or orphaned review lineage;
- any blocking review produced by recomputation.

There is no flag to bypass these gates and no implicit deduplication.

## 8. Identity and provenance

The union identity is:

```text
dea0f79d9b743dccff23f19995da6ff470866c1d717a2ad1a3af7c415d06eae3
```

It covers the sorted parent identities, common source identity, active
extraction/provenance identities, deterministic parent provenance, union code
SHA, document identity, attempt IDs and semantic manual-review identity. It
does not include the creation timestamp or parent argument order. The manifest
records both direct and root parent identities, source identity, counts,
artifacts and code SHA
`690a2a9c960812e1ffdd9497cf1dadebae5cd798f726f93a6842dbdfa7e7bdcb`.

Hashes of every file in the two original inputs were identical before and
after replay/union. Publication used a sibling staging directory, contractual
reload and atomic promotion; no staging directory remains.

## 9. Tests

Tests were written red first and cover basic union, complete multi-attempt
history, validated and rejected reviews, orphaned review lineage, duplicate
attempt IDs, BOE overlap, source/config/contract/instructions/hash mismatch,
stale deterministic code, parent immutability, atomic failure, idempotency,
order independence, an empty parent, CLI dry-run and loader round-trip.

The focal suite passed `247` tests. The full repository suite passed `1189`
tests in `139.45 s`, above the required baseline of 1180.

## 10. W14 union materialization

The published snapshot is:

```text
runs/final-w14-corpus-20220101-20260820-v1/extraction
```

Its manifest reports 104 documents, 286 attempts, one manual review, 104
current extractions, zero pending documents, zero rejected decisions, zero
blocking reviews and zero planned model calls. The source, original parents
and every previous run remain unchanged.

## 11. Loader validation

The production extraction loader re-read all five Parquet artifacts, verified
their hashes and counts, recomputed current selection and review queue, and
reproduced the same snapshot identity. A reverse-order dry-run reproduced the
same identity and counts without creating an output. Silver's loader can
therefore consume this snapshot directly.

## 12. Anchor regression

The union contains exactly the 48 anchor BOEs. All anchor `extraction_json`
payloads and selected attempt IDs are equal to `extraction-final-v2`; the five
review columns introduced by the combined manual-selection schema are entirely
null on anchor rows. The 40 generation roots are unchanged. Relative to the
original parent, the replay changes only deterministic attempt provenance and
adds no semantic extraction change.

## 13. History regression

The union contains exactly the 56 historical BOEs and their current
extractions are tabularly equal to `history-extraction-final-v2`.
`BOE-B-2023-27607` remains `manually_validated` with one publication event,
three generation assets, one shared component linked to all three assets and
one `declaracion_utilidad_publica / declarado` targeted at that component.
The shared DUP is not duplicated.

## 14. Silver readiness

`pipeline silver` can consume the union directly: **YES**. The corpus contains
none of the three BOEs targeted by the five approved rows in
`config/corrections/administrative_action_corrections.csv`, whose semantic
identity is
`12a401d7594129e69a473a6d44f71dc89e05334f18493ddf65fbae15106b9dea`.
Applicable corrections are therefore zero and the complete registry must be
omitted rather than subset manually.

The next gate should first run this exact preflight command:

```bash
uv run python -m renewables_permitting.pipeline silver \
  --extraction-snapshot runs/final-w14-corpus-20220101-20260820-v1/extraction \
  --output-dir runs/final-w14-corpus-20220101-20260820-v1/silver \
  --expected-extraction-config-id 4b54b89dbfe8640e \
  --dry-run
```

After human review, publication uses the same command without `--dry-run`.
The Silver implementation performs effective current selection first, applies
an approved corrections registry when applicable, and only then flattens and
validates the 13 tables. Neither command was run in this block.

## 15. Final corpus methodology

The document universe is 48 non-holdout anchor BOEs plus 56 conservatively
recovered historical BOEs, with zero overlap and 104 documents in total:

> Proyectos de generación con actividad publicada en el BOE durante la ventana
> ancla del 7 al 20 de agosto de 2026, con reconstrucción retrospectiva
> conservadora de publicaciones relacionadas observadas desde 2022.

Historical retrieval uses Tier 1 plus Tier 2 strict; Tier 3 is excluded. The
historical candidates were subsequently extracted and validated. This is not
an exhaustive census of the BOE, and the absence of a historical match does
not demonstrate the absence of a publication. The sealed holdout remains
separate: its contents were not inspected, history reports zero holdout
overlaps and the union introduces exactly the two audited parent universes.

P2 exhaustive execution is fallback only and abandoned for the final corpus.
`main-04` through `main-20` are not required, and the two old `main-03`
operational retries belong only to that fallback.

## 16. Next gate

The required next block is final Silver materialisation from the validated
104-current extraction snapshot. It must stop for human review before
downstream, Gold or product publication. Gemini, BOE, other models, web,
Silver, downstream, Gold and holdout calls performed in this union block: zero.
