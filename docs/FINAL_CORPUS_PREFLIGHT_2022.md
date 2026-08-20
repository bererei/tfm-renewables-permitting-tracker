# Final Corpus Preflight — 2022–2026

## 1. Purpose

Este documento registra el preflight source-only real del escenario mínimo
considerado para el corpus final. Su objetivo era medir el funnel exacto antes
de autorizar cualquier llamada al modelo.

El source falló de forma cerrada durante la descarga XML. No publicó un
snapshot y, por tanto, no se utilizan conteos parciales mantenidos en memoria.

```text
SOURCE PREFLIGHT INCOMPLETE
STOP — PIPELINE MITIGATION REQUIRED
```

No se ejecutaron `extract`, `recanonicalize`, Silver, downstream, Gold ni
ningún modelo.

## 2. Period

| Campo | Valor | Tipo de evidencia |
| --- | --- | --- |
| Inicio | `2022-01-01` | MEASURED — argumento fijo |
| Fin | `2026-08-20` | MEASURED — argumento fijo e inclusivo |
| Fechas solicitadas | 1.693 | DERIVED — `inclusive_date_range()` y dry-run |
| Escenario | 2022–2026 | MEASURED — alcance autorizado |

No se probó 2021 ni 2020.

## 3. Source execution

Dry-run ejecutado:

```bash
uv run python -m renewables_permitting.pipeline source \
  --start-date 2022-01-01 \
  --end-date 2026-08-20 \
  --output-dir runs/final-corpus-preflight-20220101-20260820-v1/source \
  --dry-run
```

Ejecución source-only real:

```bash
uv run python -m renewables_permitting.pipeline source \
  --start-date 2022-01-01 \
  --end-date 2026-08-20 \
  --output-dir runs/final-corpus-preflight-20220101-20260820-v1/source
```

El destino no existía antes de ambos comandos. No se usó `--force` ni se
ejecutó el subcomando integral `run`.

El CLI no registra un timestamp de inicio y no llegó a crear manifest con
`created_at`; por ello los tiempos exactos de inicio, fin y duración quedan
`UNKNOWN`. La sesión fue prolongada, pero no se transforma esa observación en
una métrica inventada.

## 4. Source integrity

| Control | Resultado | Tipo de evidencia |
| --- | --- | --- |
| Estado terminal | fallo, exit code 1 | MEASURED |
| Mensaje | `pipeline failed: BOE XML source failed: ['BOE-B-2024-24843:request_error']` | MEASURED |
| Fallos de sumario | 0 detectados antes de entrar en XML | DERIVED — el código aborta antes de XML si existe alguno |
| Días con publicación | UNKNOWN | no se publicó manifest |
| Días sin publicación | UNKNOWN | no se publicó manifest |
| XML fallidos | 1 reportado: `BOE-B-2024-24843` | MEASURED |
| Parse failures | UNKNOWN; no se alcanzó materialización/parseo contractual | no hay artefactos |
| Duplicados | UNKNOWN | no hay snapshot publicable que validar |
| Documentos inconsistentes | UNKNOWN | no hay `documents.parquet` |
| Snapshot final | ausente | MEASURED |

La implementación obtiene todos los resultados XML antes de materializar. Un
único `request_error` abortó el stage y no se publicaron Parquets, XML ni
manifest. El directorio conceptual del run tampoco existe después del fallo.

## 5. Funnel

El funnel exacto no puede calcularse a partir de un source incompleto:

| Métrica | Resultado | Tipo de evidencia |
| --- | --- | --- |
| BOE items | UNKNOWN | no publicado |
| Candidate items | UNKNOWN | no publicado |
| Candidate rate | UNKNOWN | no publicado |
| XML/documentos disponibles | UNKNOWN | no publicado |
| Documentos canónicos deduplicados | UNKNOWN | no publicado |
| Duplicados BOE ID | UNKNOWN | no publicado |
| Descartados/fallidos | 1 fallo XML terminal conocido; total publicable UNKNOWN | MEASURED / UNKNOWN |

No se presentan los conteos parciales que el proceso mantuvo en memoria.

## 6. Annual distribution

| Año | Source documents | Reusable | Deterministic | Model required |
| --- | --- | --- | --- | --- |
| 2022 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| 2023 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| 2024 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| 2025 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| 2026 hasta 20 agosto | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

La distribución anual requiere el snapshot source completo.

## 7. Development overlap

El registro versionado vigente contiene **152 BOE usados durante desarrollo**.
No se comparó ese conjunto contra un snapshot incompleto.

| Métrica | Resultado |
| --- | --- |
| `DEVELOPMENT_BOE_IDS` | 152 IDs versionados |
| Solapamiento con preflight | UNKNOWN |
| BOE nuevos | UNKNOWN |
| BOE de desarrollo fuera del periodo | UNKNOWN |
| Porcentaje de solapamiento | UNKNOWN |

## 8. Source reuse

No se ejecutó la comparación por BOE y `source_document_sha256` porque no
existe `documents.parquet` contractual.

| Clase | Conteo |
| --- | --- |
| `EXACT SOURCE MATCH` | UNKNOWN |
| `BOE MATCH / HASH DIFFERENT` | UNKNOWN |
| `NEW DOCUMENT` | UNKNOWN |

No se copiaron ni combinaron artefactos manualmente.

## 9. Extraction reuse

El reuse sigue estando soportado contractualmente, pero no puede medirse para
este preflight sin los hashes documentales nuevos.

| Clase | Conteo |
| --- | --- |
| `EXTRACTION_REUSABLE` | UNKNOWN |
| `EXTRACTION_NOT_REUSABLE` | UNKNOWN |
| `EXTRACTION_REUSE_CONFLICT` | UNKNOWN |

No se modificó ni copió ninguna extracción del core freeze.

## 10. Deterministic classification

No se ejecutó `build_extraction_plan()` ni ninguna preclasificación sobre un
universo incompleto.

| Clase | Conteo |
| --- | --- |
| `DETERMINISTIC_NO_MODEL` | UNKNOWN |
| `MODEL_REQUIRED` | UNKNOWN |
| Conflicts/errors | 1 error source terminal; conflictos de reuse UNKNOWN |

## 11. Net model requirement

```text
TOTAL SOURCE DOCUMENTS = UNKNOWN
EXTRACTION_REUSABLE = UNKNOWN
DETERMINISTIC_NO_MODEL = UNKNOWN
MODEL_REQUIRED = UNKNOWN
CONFLICTS / BLOCKERS = 1 SOURCE BLOCKER
```

La igualdad de reconstrucción no puede comprobarse. No se autoriza IA con un
universo documental incompleto.

## 12. Extraction configuration

La identidad validada continúa siendo:

| Campo | Valor | Compatibilidad |
| --- | --- | --- |
| Provider | `gemini` | no ejecutado |
| Model | `google:gemini-2.5-flash` | no ejecutado |
| Config ID | `8158661f76a31c87` | contrato esperado |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` | contrato esperado |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` | contrato esperado |
| Agent retries | 3 | no ejecutado |
| Request limit por documento | 6 | no ejecutado |
| Retry de validación documental | 1 | no ejecutado |
| Reintentos transitorios del run | 2 | no ejecutado |

La configuración instalada coincide con la identidad auditada. Esto no
autoriza modelo mientras source permanezca incompleto.

## 13. Runtime evidence

No existe metadata contractual de duración porque el stage falló antes del
manifest. Tampoco existe evidencia local suficiente para estimar la duración
de `MODEL_REQUIRED`, cuyo conteo es desconocido.

```text
SOURCE RUNTIME = UNKNOWN EXACT
EXTRACTION DURATION = UNKNOWN
```

## 14. Review burden

```text
HUMAN REVIEW BURDEN = UNKNOWN
```

La evidencia histórica de correcciones y revisiones permanece válida, pero no
se extrapola sin `MODEL_REQUIRED`, warnings, errores y review queue del corpus
completo. Automated validation y human review siguen siendo cargas distintas.

## 15. Corrections

El registro versionado sigue conteniendo cinco correcciones aprobadas sobre
tres BOE. Su pertenencia temporal a 2022–2026 está demostrada por sus fechas,
pero su presencia y hash en el nuevo source no pueden verificarse sin el
snapshot.

| Control | Resultado |
| --- | --- |
| Correcciones versionadas | 5 |
| BOE target | 3 |
| Targets temporalmente dentro del escenario | 5 |
| Targets presentes en el nuevo source | UNKNOWN |
| Hash documental nuevo compatible | UNKNOWN |
| Conflictos de aplicación | UNKNOWN |

No se aplicó ni modificó el CSV.

## 16. Holdout-eligible pool

No se seleccionó holdout ni se inspeccionó contenido para elegir ejemplos.

| Métrica | Resultado |
| --- | --- |
| Pool elegible total | UNKNOWN |
| Distribución anual | UNKNOWN |
| Exclusión de development IDs | pendiente de snapshot completo |

Los 152 BOE de desarrollo continúan excluidos conceptualmente del futuro
holdout.

## 17. Source reliability

```text
SOURCE RELIABILITY BLOCKER
```

La causa inmediata es un `request_error` de un único XML. El impacto es
material: tras una ejecución prolongada y secuencial, el stage aborta sin
publicar y no dispone de retry, resume ni cache contractual.

La mitigación mínima antes de repetir el preflight es añadir retries acotados
con backoff únicamente para fallos transitorios de sumario/XML, preservando el
fallo cerrado ante respuestas inválidas y la publicación atómica. Si esa
medida no demuestra una ejecución completa, debe decidirse humanamente un
checkpoint/cache run-scoped verificable; no se permite un merge manual de
Parquets.

Esta auditoría no implementa la mitigación.

## 18. Storage

| Métrica | Resultado |
| --- | --- |
| Tamaño del source preflight | 0 bytes publicados |
| Artefactos principales | ninguno |
| Ficheros del run | 0 |
| Espacio libre | no reevaluado tras el fallo |
| Riesgo de espacio | UNKNOWN; no es la causa observada |

No se borraron ni comprimieron caches.

## 19. Deadline assessment

```text
2022 DEADLINE ASSESSMENT = RED
```

El escenario no puede calificarse como viable: el source no terminó, la carga
neta de IA y revisión sigue desconocida y el fallo exige un cambio mínimo más
repetición completa antes del Final Corpus Build.

## 20. Recommendation

```text
STOP — PIPELINE MITIGATION REQUIRED
```

No procede medir 2021. Primero debe aprobarse e implementarse la mitigación
mínima de fallos transitorios y repetirse exactamente el preflight 2022–2026
en un destino nuevo.

## 21. Next decision

La decisión humana pendiente es si autorizar la reapertura mínima del bloque
source para añadir retry/backoff y su regresión offline. Tras esa corrección:

1. repetir source-only 2022–2026 con el mismo cutoff;
2. exigir snapshot completo y manifest válido;
3. medir funnel, reuse, `MODEL_REQUIRED`, correcciones y pool elegible;
4. decidir el periodo;
5. solo después decidir si se mide el incremento aislado de 2021.

No se debe repetir innecesariamente 2022–2026 para comparar 2021 una vez que
exista un snapshot 2022 completo, pero cualquier medición incremental debe
mantener su propio manifest y no sustituye al full rebuild contractual final.
