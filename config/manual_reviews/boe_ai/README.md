# Revisiones manuales de extracciones BOE

Este directorio contiene decisiones manuales versionadas que actúan como
entradas reproducibles del pipeline. Cada fichero JSON corresponde a una
revisión. Para aprobar la propuesta exacta de la cola o rechazar la extracción
completa usa la CLI, que deriva el formato y la procedencia:

```bash
uv run python -m renewables_permitting.admin validate-extraction --help
uv run python -m renewables_permitting.admin reject-extraction --help
```

Las decisiones `manually_validated` y `rejected` requieren:

- `identificador_boe`, `source_document_sha256` y `source_attempt_id`;
- `reviewer`, `review_notes` y `reviewed_at_utc` con contenido explícito;
- `corrected_extraction` válido cuando el estado sea `manually_validated`.

`source_attempt_id` vincula la decisión con una única fila del registro de
intentos. El BOE, el hash documental, la configuración y la versión deben
coincidir. Las plantillas incluyen `extraction_config_id` y
`document_validation_version`; si una entrada no los declara, se obtienen del
intento fuente validado, nunca de valores inventados. Las revisiones `pending`
no son decisiones finales y no afectan a la selección.

La CLI sólo aprueba `proposed_extraction_json` sin editarlo o registra
`rejected`; no es un editor JSON. Una corrección estructural distinta de la
propuesta sigue siendo developer-only y debe conservar el formato de
`create_manual_review_file()` además de superar el mismo loader y la revisión
humana.

Estos JSON deben revisarse mediante Git. Los Parquet y demás outputs derivados
se regeneran desde ellos y nunca se editan manualmente. No se almacenan aquí
respuestas completas del modelo, salvo la extracción completa necesaria para
una validación manual.
