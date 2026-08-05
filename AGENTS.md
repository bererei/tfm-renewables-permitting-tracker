# TFM BOE Energy Tracker

## Objective

Track the administrative lifecycle of named electricity-generation plants
published in the BOE.

## Domain rules

- Generation plants are the only project-grouping roots.
- Storage and evacuation infrastructure are associated components.
- Do not create generation projects from standalone storage or grid infrastructure.
- Manual corrections must remain traceable and must not edit derived Parquet files.
- Gold tables must be regenerable from validated Silver sources.

## Refactoring rules

- Do not change the extraction contract or validated extraction semantics without explicit approval.
- Preserve the pilot invariants and regression guarantees enforced by `tests/extraction`.
- Move code incrementally from notebooks to `src`.
- Do not duplicate functions between notebooks and `src`.
- Add or update tests before deleting notebook implementations.
- Keep notebooks as orchestration and audit layers.
