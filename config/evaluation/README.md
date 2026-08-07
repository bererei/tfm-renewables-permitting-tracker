# Evaluation document sets

The 100-document pilot was the initial sample used to develop and validate the
extraction pipeline.

`development_challenge_sample.csv` is a directed development sample used to
discover defects and improve the extraction pipeline. It is not a final
evaluation sample. Its categories and signals record only the pre-extraction
criteria used to select each document.

`development_challenge_human_audit.csv` records human decisions about defects
found during that challenge and ties each decision to the exact audited
extraction through its lineage. It is a development artifact, not a holdout;
its BOEs are already development documents, and later pipeline results must not
overwrite this historical audit.

`development_used_documents.csv` records BOEs already used in the pilot, as
development examples, as regression cases, or in the development challenge
sample. Every document in this registry is excluded from the future final
holdout.

The final holdout does not yet exist. It must be selected only after the
extraction contract, prompt, canonicalisation, validation, and relevant review
policy have been frozen. Holdout documents must not appear in
`development_used_documents.csv`.
