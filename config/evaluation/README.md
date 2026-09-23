# Evaluation document sets

The 100-document pilot was the initial sample used to develop and validate the
extraction pipeline.

`development_challenge_sample.csv` is a directed development sample used to
discover defects and improve the extraction pipeline. It is not a final
evaluation sample. Its categories and signals record only the pre-extraction
criteria used to select each document.

`development_challenge_human_audit.csv` records human decisions about defects
found in the original challenge run. `development_challenge_v2_human_audit.csv`
records the later human validation of corrections and generalisation in v2.
Both are development artifacts, not final holdouts; v2 does not replace or
rewrite the historical v1 audit, and each decision retains the lineage of the
exact extraction reviewed.

`development_used_documents.csv` records BOEs already used in the pilot, as
development examples, as regression cases, or in the development challenge
sample. Every document in this registry is excluded from the future final
holdout.

The final holdout was selected only after the extraction contract, prompt,
canonicalisation, validation and relevant review policy were frozen. Holdout
documents must not appear in `development_used_documents.csv`.

`final_holdout_p2_v1.csv` is the frozen 48-document final holdout for P2. It
was selected exclusively from development-unexposed `MODEL_REQUIRED`
documents using the versioned source/config identities, six pre-model
year-by-BOE-series strata and seed `20260821`. It contains selection lineage,
not model outputs, and has not yet been executed.

`final_p2_execution_scopes_v1/` contains the bounded, pairwise-disjoint main
model scopes and the complete P2 scope used by the controlled execution plan.
Its manifest declares counts, identities and fingerprints. These CSVs are
versioned execution inputs; operational extraction snapshots remain under
ignored `runs/` paths.
