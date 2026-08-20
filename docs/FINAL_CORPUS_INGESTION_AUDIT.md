# Final Corpus Ingestion Audit

## 1. Purpose

Esta auditoría determina cómo construir de forma reproducible el corpus final
multianual del TFM antes de descargar nuevos BOE o autorizar llamadas al
modelo. Es una auditoría **read-only** de arquitectura, cobertura local,
volumen y planificación realizada el **2026-08-20**.

No es un preflight ni una autorización de build. Durante la auditoría no se
ejecutó `source`, `extract`, Silver, downstream ni Gold; no se llamó al BOE,
Gemini ni ningún servicio externo.

Conclusiones ejecutivas:

- la CLI y el código admiten un intervalo inclusivo y un único snapshot source
  nuevo para todo el periodo;
- el contrato técnico se clasifica como **FULL MULTI-YEAR REBUILD SUPPORTED**;
- la ejecución operativa de un rango largo es frágil porque `source` es
  secuencial y no tiene retry, resume ni cache contractual;
- no existe soporte para combinar snapshots documentales y no debe hacerse una
  unión manual de Parquets;
- la reutilización de extracción está **SUPPORTED CONTRACTUALLY** cuando
  coinciden BOE, hash documental y configuración efectiva;
- la cobertura local no permite calcular los totales de 2022, 2021 o 2020;
- una referencia local aparentemente completa de 2023 contiene 65.818 ítems y
  3.615 coincidencias con la política de títulos vigente, de modo que los tres
  escenarios presentan riesgo de calendario **RED** hasta medir el funnel
  completo;
- la estrategia recomendada es full rebuild por fases, empezando el preflight
  por el escenario mínimo de 2022 y deteniéndose para decisión humana antes de
  cualquier llamada al modelo.

## 2. Current baseline

| Concepto | Baseline auditado |
| --- | --- |
| Branch | `tfm-final` |
| HEAD | `a8af57ee9c6df63c66c79eee418421f1f1f51386` |
| `origin/tfm-final` | mismo SHA que HEAD |
| Working tree inicial | limpio |
| Development corpus | 140 documentos; baseline congelado de desarrollo y regresión |
| Core freeze | tag `tfm-core-freeze-2026-08-13`; run `canonical-140-freeze-final-candidate-20260813` |
| Extraction snapshot ID | `55582e7cc0ce6262fc43fbb5a6cb482a03f794d8d68956e01d4b9e081e0de855` |
| Silver ID | `2bebfe3100f21332f29e97868e0fdc518c2fe96ac33bbe3f8926e15d896ae6f6` |
| Frozen downstream ID | `2201abf25a45688013a229a6786fd87fb38c024e787259b699ead3d45b7b1a96` |

Se mantienen tres conceptos separados:

```text
Development corpus → desarrollo, tests y regresión
Final TFM corpus    → nueva materialización multianual
Deployment dataset → Gold final publicado y validado
```

El build final no sobrescribe el development corpus, no mueve el tag y no
reabre el core freeze. El nuevo corpus tendrá identidades, cardinalidades y
manifests propios.

## 3. Final corpus scenarios

La fecha final es fija e inclusiva: **2026-08-20**.

| Escenario | Inicio | Fin | Días naturales del intervalo | Carácter |
| --- | --- | --- | ---: | --- |
| A — corto | 2022-01-01 | 2026-08-20 | 1.693 | mínimo de viabilidad |
| B — recomendado inicialmente | 2021-01-01 | 2026-08-20 | 2.058 | preferencia metodológica inicial |
| C — amplio | 2020-01-01 | 2026-08-20 | 2.424 | máxima cobertura comparada |

Ninguno queda aprobado por esta auditoría. La elección final es humana y debe
apoyarse en un source-only preflight.

## 4. Methodological period trade-offs

Un inicio tardío produce censura por la izquierda. Una cronología puede
contener, por ejemplo, información pública anterior al inicio del intervalo,
una decisión ambiental posterior y autorizaciones aún más tarde. Empezar en
2022 puede ocultar una parte sustantiva de esa secuencia.

Ningún inicio garantiza recuperar la primera publicación histórica absoluta
de cada proyecto. La metodología y la UI deben usar:

> Primera publicación en el periodo analizado.

No deben usar “primera publicación histórica del proyecto” salvo evidencia
externa que lo sostenga.

| Escenario | Cobertura longitudinal | Riesgo de censura izquierda | Cronologías | Serie temporal | Coste operativo relativo |
| --- | --- | --- | --- | --- | --- |
| 2022 | media | alto | puede perder antecedentes próximos | útil, más corta | menor de los tres, pero no demostrado como manejable |
| 2021 | alta, unos cinco años y medio | medio | mejor equilibrio metodológico | alta | mayor que 2022; volumen exacto desconocido |
| 2020 | más alta | menor, nunca cero | mejor oportunidad de enlazar antecedentes | máxima | mayor; incremento exacto desconocido |

La regla previa a la decisión es:

1. preferir 2020 si su incremento frente a 2021 es manejable y aporta valor
   longitudinal sustantivo;
2. preferir 2021 si cubre con margen build, revisión, despliegue y holdout;
3. usar 2022 solo si 2021 amenaza claramente el cierre;
4. no bajar de 2022 sin **STOP AND HUMAN DECISION**.

## 5. Source CLI

La ayuda real expone:

```text
source --start-date START_DATE --end-date END_DATE
       --output-dir OUTPUT_DIR [--dry-run]
```

Resultados:

| Pregunta | Respuesta observada |
| --- | --- |
| Una fecha | sí, usando el mismo inicio y fin |
| Intervalo | sí |
| Inicio y fin | obligatorios y en `YYYY-MM-DD` |
| Inclusividad | sí, confirmada por `inclusive_date_range()` |
| Múltiples fechas/lista de BOE | no |
| Input local en `source` | no |
| Output | directorio nuevo obligatorio |
| Output existente | se rechaza, también si es symlink |
| Dry-run | sí; muestra rango, número de fechas y destino, sin red ni escritura |
| Filtros configurables | no; aplica la política fija `title_keywords_v1` |
| Deduplicación configurable | no |

`run` acepta alternativamente `--documents` o el par fecha inicial/final. Los
demás subcomandos confirmados por `--help` son `extract`, `recanonicalize`,
`silver`, `downstream`, `build-reference-data` y `refresh-reference-data`.

## 6. Source architecture

### 6.1 Flow

```text
rango inclusivo de fechas
→ sumario BOE diario
→ items normalizados
→ selección determinista por keywords del título
→ descarga XML de cada candidato
→ parseo de identidad, fecha, título y texto
→ documents.parquet
→ manifest del snapshot source
```

La política vigente es `title_keywords_v1`, ID
`79289feae5d557be`. Solo usa `titulo` normalizado. No usa cuerpo, sección,
departamento ni un clasificador para seleccionar candidatos.

### 6.2 Unit and identity

La clave documental canónica es `identificador`, es decir, el BOE ID. El
`doc_file_stem` combina fecha y BOE ID para nombrar el XML, pero no sustituye a
la clave.

`source_document_sha256` es SHA-256 de:

```text
boe_id + "\n" + publication_date + "\n" + title + "\n" + canonical_text
```

La identidad documental del snapshot es SHA-256 de los pares ordenados
`(identificador, source_document_sha256)`. El manifest añade hashes de
sumarios, XML y artefactos físicos.

### 6.3 Duplicate handling

No hay una coalescencia silenciosa:

- `parse_boe_summary()` rechaza BOE IDs duplicados dentro de un sumario;
- `run_source_stage()` concatena las fechas, ordena por fecha/ID y rechaza BOE
  IDs duplicados entre sumarios;
- `prepare_documents()` vuelve a exigir identificadores únicos;
- candidatos y documentos conservan una fila por BOE ID cuando el source es
  válido.

La garantía es **fail closed on duplicate**, no “keep first/last”.

### 6.4 Materialization

El stage obtiene primero todos los sumarios y XML, escribe en un staging
adyacente, genera cuatro Parquets, sumarios, XML y manifest, y renombra el
staging al destino nuevo. Un fallo no publica un snapshot parcial.

Artefactos contractuales:

- `boe_items.parquet`;
- `candidates.parquet`;
- `xml_download_log.parquet`;
- `documents.parquet`;
- `summaries/` y `xml/`;
- `manifest.json`.

### 6.5 Full rebuild classification

```text
FULL MULTI-YEAR REBUILD SUPPORTED
```

La clasificación se basa en el intervalo inclusivo real, el ensamblado de un
solo conjunto de items/candidatos/documentos, la unicidad global por BOE ID y
la publicación atómica de un snapshot nuevo. No hace falta combinar Parquets
para construir un rango completo desde cero.

### 6.6 Operational limitation

El soporte contractual no equivale a robustez operacional demostrada para
varios años:

- sumarios y XML se obtienen secuencialmente;
- no hay retry del source, resume, checkpoint ni cache reutilizable;
- todos los resultados se mantienen antes de publicar;
- cualquier `failed` de sumario o XML aborta todo el stage;
- volver a ejecutar exige un destino nuevo y repite la red del intervalo.

El source-only preflight debe demostrar el rango elegido. Si la falta de
resume/retry impide completarlo de forma fiable, debe aplicarse **STOP AND
HUMAN DECISION** antes de considerar un hardening mínimo; nunca se debe caer en
un merge manual de Parquets.

## 7. Local source coverage

### 7.1 Inventory

| Path relativo | Contenido | Filas/ficheros | Periodo observado | Cobertura y uso |
| --- | --- | ---: | --- | --- |
| `data/bronze/boe/` | sumarios y metadata diarios legacy | 51 éxitos + 7 días sin publicación | 2021-07-07 a 2026-06-20 | parcial; no es snapshot source de la CLI actual |
| `data/silver/boe_items/boe_items.parquet` | items BOE legacy | 13.544; 51 fechas; 0 IDs duplicados | 2021-07-07 a 2026-06-20 | parcial, útil para diagnóstico |
| `data/silver/boe_candidates/boe_candidates_normalized.parquet` | candidatos legacy | 1.266; 51 fechas; 0 IDs duplicados | mismo | parcial; no registra la policy ID actual |
| `data/bronze/boe_docs_xml/` | XML y log legacy | 1.266 XML; todos `downloaded` | mismo | cache local no consumible por `source` |
| `data/silver/boe_candidates_docs_text/boe_candidates_docs_text.parquet` | texto parseado | 1.266 documentos válidos | mismo | permite auditar el plan de extracción, no el escenario final |
| `data/delete/boe_2023.csv` | inventario BOE legacy de 2023 | 65.818 items; 311 fechas | 2023-01-02 a 2023-12-30 | referencia de volumen, sin manifest/hash/XML contractual |
| `runs/canonical-140-freeze-final-candidate-20260813/extraction/` | development corpus congelado | 140 documentos/intentos vigentes | 2021-07-07 a 2026-06-20 | baseline y fuente contractual de attempts reutilizables |

No existe en `runs/` un snapshot source de la CLI actual que cubra uno de los
tres escenarios completos.

### 7.2 Real continuity and gaps

Los Parquets legacy de items/candidatos abarcan solo 51 fechas con publicación:

| Año | Items | Candidatos/documentos | Fechas con publicación |
| ---: | ---: | ---: | ---: |
| 2021 | 135 | 13 | 1 |
| 2022 | 764 | 11 | 1 |
| 2023 | 905 | 116 | 4 |
| 2024 | 1.128 | 92 | 4 |
| 2025 | 628 | 71 | 2 |
| 2026 | 9.984 | 963 | 39 |

La única ventana continua inspeccionada es **2026-05-01 a 2026-06-11**:
cubre los 42 días naturales, con 36 publicaciones y 6 domingos sin BOE. En esa
ventana hay 9.223 items y 947 candidatos/documentos, un 10,27 %.

Fuera de esa ventana predominan fechas aisladas. No hay datos locales de 2020,
solo una fecha de 2021 y una de 2022, y no existe cobertura posterior a
2026-06-20 hasta el cutoff. Sobre los días naturales de cada escenario, las
fechas de sumario local con publicación representan solo 2,95 % en A, 2,48 %
en B y 2,10 % en C. Esta proporción no pretende medir días BOE; demuestra la
discontinuidad del cache.

### 7.3 2023 legacy reference

El CSV legacy de 2023 contiene las 311 fechas de lunes a sábado del año, IDs
únicos y coincide exactamente con los 905 items de las cuatro fechas que
también existen en el cache parseado. Aplicando en memoria la normalización y
keywords de `title_keywords_v1` se obtienen:

| Métrica 2023 | Resultado |
| --- | ---: |
| BOE items | 65.818 |
| Títulos candidatos | 3.615 |
| Candidate/item | 5,49 % |

Es una referencia local fuerte para **un año**, pero está bajo `data/delete/`,
carece de manifest, hashes source y `url_xml`, y no puede usarse como snapshot
contractual ni como estimación exacta de los otros años.

## 8. Candidate funnel

El funnel real es:

```text
BOE item
→ título contiene alguna keyword vigente
→ candidate
→ XML descargado y verificado
→ document
→ preclasificación determinista sin modelo
→ model input, solo si la preclasificación no resuelve el documento
```

Reglas y descartes:

- todos los items sin keyword se excluyen antes de descargar XML;
- no hay ranking, muestreo ni límite de candidatos;
- un fallo XML no descarta una fila: bloquea todo el source stage;
- `build_extractor_document_input()` exige mismo BOE ID y fecha entre
  candidato y XML;
- `prepare_documents()` exige texto no vacío, `xml_status=ok` e ID único;
- el extractor determina sin modelo ciertos documentos que no pueden crear un
  proyecto de generación nombrado; el resto llega al modelo.

Conteos locales read-only:

| Corpus local | Items | Candidatos | Documents | Reutilizables | Deterministas nuevos | Modelo nuevo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cache discontinuo | 13.544 | 1.266 | 1.266 | 140 | 65 | 1.061 |

Los últimos tres valores proceden de `build_extraction_plan()` con los 1.266
documentos locales, la configuración activa y los attempts del freeze. El
plan se ejecutó con `execute_model=False`: **0 llamadas planificadas y 0
llamadas realizadas**. No representa una tasa extrapolable a años completos.

```text
MODEL RUN COUNT ESTIMATE: UNKNOWN FOR ALL THREE SCENARIOS
MONETARY COST NOT ESTIMATED
```

El development corpus contiene 140 documentos seleccionados para desarrollo,
no todos los candidatos del periodo. Su distribución es 7 (2021), 10 (2022),
32 (2023), 28 (2024), 25 (2025) y 38 (2026).

## 9. Scenario volume estimates

```text
INSUFFICIENT LOCAL COVERAGE
```

No se calculan totales de escenario mediante extrapolación. Las cifras
parciales siguientes son observaciones de fechas discontinuas, no estimaciones:

| Escenario | BOE items totales | Candidatos | Documents | Observación local parcial |
| --- | --- | --- | --- | --- |
| A — 2022 | UNKNOWN | UNKNOWN | UNKNOWN | 13.409 items y 1.253 candidates/docs en 50 fechas locales |
| B — 2021 | UNKNOWN | UNKNOWN | UNKNOWN | 13.544 items y 1.266 candidates/docs en 51 fechas locales |
| C — 2020 | UNKNOWN | UNKNOWN | UNKNOWN | igual que B porque no hay datos de 2020 |

Los tres escenarios incluyen el año 2023, cuya referencia legacy arroja
65.818 items y 3.615 candidatos. Esto no completa los totales, pero demuestra
que ningún escenario debe presupuestarse como una ampliación pequeña del
development corpus de 140 documentos.

El preflight debe medir para el intervalo elegido:

- fechas solicitadas, sumarios exitosos, días sin publicación y fallos;
- items/candidatos/documentos totales, únicos, por año y por mes;
- ratio candidato/item;
- duplicados y XML fallidos;
- solapamiento exacto por BOE ID y hash con documentos conocidos;
- deterministas, reutilizables y netos que requieren modelo.

## 10. Reuse analysis

| Capa | Reutilización | Veredicto |
| --- | --- | --- |
| Source | `source` no acepta cache, snapshots previos ni merge; vuelve a obtener todo el rango. `--documents` permite omitir source solo si ya existe un corpus completo validado, que hoy no existe. | no reutilizable contractualmente para construir los escenarios |
| XML/texto/candidatos legacy | sirven para auditoría y comparación de hashes, pero no forman un snapshot source actual ni pueden copiarse manualmente al nuevo run | referencia solamente |
| Extraction | `extract --attempts` acepta un snapshot o Parquet y selecciona attempts compatibles por documento/configuración | reutilizable contractualmente |
| Silver | las filas dependen del conjunto final y de las correcciones; no se mezclan ni reutilizan como output final | rebuild completo |
| INE reference | la dimensión validada `25a3bbb28f0c21c5` puede reutilizarse como input downstream | reutilizable |
| Downstream/Gold | agrupación, IDs, cronología y territorios dependen del nuevo Silver; no se unen con el Gold de 140 | rebuild completo |
| Corrections | el CSV versionado se reaplica como input solo si todos sus targets coinciden exactamente | reutilizable con validación estricta |

Reutilizar un fichero no equivale a una materialización contractual. La nueva
cadena debe conservar manifests, hashes e identidades propios.

## 11. AI extraction reuse

```text
SUPPORTED CONTRACTUALLY
```

La compatibilidad exige:

- mismo `identificador`/BOE ID;
- mismo `source_document_sha256`, por tanto misma fecha, título y texto;
- mismo `EXTRACTION_CONFIG_ID` y versión de validación;
- por transitividad del config ID, mismas instrucciones, contrato, modelo y
  políticas efectivas;
- attempt válido o decisión manual con linaje válido.

`extract --attempts` verifica el artefacto si recibe un snapshot, reconstruye
la cola respecto del corpus objetivo y ejecuta solo los `source_not_attempted`.
Errores o inciertos previos se envían a revisión; no se relanzan
automáticamente.

El freeze contiene 140 attempts vigentes con config activa
`8158661f76a31c87`, hash documental verificable y cero blockers. El diagnóstico
local confirmó la reutilización exacta de los 140 dentro de los 1.266 textos
locales.

Potencial máximo antes de volver a verificar el source nuevo:

| Escenario | Documentos del freeze dentro del periodo |
| --- | ---: |
| A — 2022 | 133 |
| B — 2021 | 140 |
| C — 2020 | 140 |

Son máximos, no garantías: si el XML oficial o su parseo produce un título o
texto distinto, cambia el hash y ese documento vuelve a estar pendiente.

## 12. Recanonicalization

`recanonicalize` reaplica la canonicalización determinista vigente a un
snapshot histórico completo y explícitamente aprobado. No llama al modelo.

Límites exactos:

- usa `precanonical_extraction_json`, que es la salida Pydantic estructurada
  pre-canónica, no el payload HTTP raw del proveedor;
- solo admite identidades históricas incluidas en la allowlist productiva;
- exige mismo conjunto y hash de documentos que el snapshot fuente;
- exige una selección automática vigente por documento, cero blockers y cero
  decisiones manuales transferidas;
- reemite determinísticamente los documentos preclasificados que no tenían
  payload de modelo;
- no añade documentos, no combina snapshots y no sustituye `extract`;
- no es un migrador genérico de schemas: solo funciona si el contrato histórico
  aprobado puede validarse y transformarse al contrato activo.

Produce nuevos attempt IDs, config/target provenance, canonical outputs y
snapshot identity; conserva el source attempt y el hash documental. El freeze
de 140 ya está en la configuración activa, por lo que no necesita
recanonicalización para reutilizarse en el corpus final.

## 13. Model/config identity

Configuración validada instalada:

| Campo | Valor |
| --- | --- |
| Provider | `gemini` |
| Model | `google:gemini-2.5-flash` |
| Agent retries | 3 |
| Request limit por documento | 6 |
| Reintentos transitorios del run | 2 |
| Retry de validación documental | 1 |
| Timeout del documento | 600 s |
| Timeout de cada model run | 240 s |
| Checkpoint de attempts | cada 5 documentos |
| Config ID | `8158661f76a31c87` |
| Instructions SHA-256 | `153b0a19c0f0709c78396acd8e0350e7d3b8d67044db14f76029cc9acbdf5580` |
| Contract SHA-256 | `7960b8718df138c75e92230a4b4b32c03872cdd7c6ac20a5f3521226e709c81c` |
| Document validation | `25` |

Un “model run” planificado es un documento que necesita agente. Su mínimo
teórico es una ejecución de agente por documento neto, pero los requests al
proveedor pueden ser mayores por retries y por el único retry de validación,
siempre bajo el límite de seis requests por documento. No se multiplica
automáticamente el conteo por todos los límites.

Cambiar provider, modelo, instrucciones, contrato o políticas cambia la
identidad efectiva, invalida la reutilización automática de attempts, genera
un snapshot de extracción distinto y exige nueva validación. La recomendación
es mantener la configuración validada salvo defecto material y aprobación
humana.

## 14. Human review burden

Evidencia observada del development corpus:

- 140/140 extracciones vigentes y 0 blockers en el freeze final;
- 17 hallazgos humanos históricos en 10 BOE del challenge v1: 15 major y 2
  minor;
- 9/9 comprobaciones humanas `CORRECTED_OK` en challenge v2;
- 5 correcciones versionadas sobre 3 BOE;
- 592 menciones territoriales: 404 resueltas, 187 parciales y 1 no encontrada;
- 119 menciones de plantas agrupadas en 116 proyectos, sin cola de grouping
  versionada.

La cola cero es el resultado final tras desarrollo y corrección, no una tasa de
éxito representativa del corpus multianual. No existe una métrica local
representativa de warnings, errores, revisiones y grouping para todos los
candidatos anuales.

| Escenario | Carga humana | Motivo |
| --- | --- | --- |
| 2022 | VERY HIGH / UNKNOWN exacta | solo 2023 aporta 3.615 candidatos de referencia; revisión neta pendiente de preflight |
| 2021 | VERY HIGH / UNKNOWN exacta | superconjunto de 2022 |
| 2020 | VERY HIGH / UNKNOWN exacta | mayor superconjunto y sin cobertura local de 2020 |

No se extrapola el 140-document corpus. El preflight debe fijar los conteos y
la capacidad humana antes de autorizar IA.

## 15. Corrections

El registro vigente contiene **5 correcciones aprobadas sobre 3 BOE**:

| BOE | Fecha | Correcciones |
| --- | --- | ---: |
| `BOE-A-2024-9608` | 2024-05-13 | 2 |
| `BOE-A-2024-16662` | 2024-08-10 | 2 |
| `BOE-A-2025-26110` | 2025-12-19 | 1 |

Los tres BOE caen dentro de A, B y C. En el corpus acumulativo se debe aplicar
el CSV completo mediante `silver --corrections`. La aplicación exige una
coincidencia exacta de entidad, tipo, decisión y evidencia; cero o varias
coincidencias bloquean la materialización. El preflight debe confirmar los
tres BOE y los cinco targets antes de Silver.

Si un escenario excluyese un target, no se debe recortar el CSV de forma
improvisada: se detiene el build y se toma una decisión humana sobre el alcance
de correcciones aplicable.

## 16. Holdout

El final holdout **no existe todavía**. No hay IDs, fechas, tamaño ni regla de
muestreo aprobados.

Lo que sí está fijado:

- se selecciona después de congelar contrato, prompt, canonicalización,
  validación y política de revisión;
- no puede incluir ninguno de los 152 BOE de
  `development_used_documents.csv`;
- `development_challenge_sample` y sus auditorías son desarrollo, no holdout;
- los documentos de holdout no se usan para modificar reglas, prompts,
  canonicalización, dashboard o decisiones de desarrollo.

No se inventa una exclusión en este audit. Antes de la primera extracción
productiva, el preflight debe registrar qué procedimiento reservará el
holdout, cuándo se evaluará y si se incorporará al deployment dataset solo
después de la evaluación, sin tuning posterior. Esa decisión permanece
humana.

## 17. Full rebuild vs merge

| Criterio | Option A — full multi-year rebuild | Option B — histórico + cohortes |
| --- | --- | --- |
| Soporte actual | sí, intervalo completo | no hay subcomando de merge source |
| Reproducibilidad | un snapshot, una policy y un manifest | requeriría contrato y tooling nuevos |
| Deduplicación | unicidad global por BOE ID, fail closed | una unión manual puede ocultar colisiones |
| Trazabilidad | sumarios/XML/documentos ligados | procedencias heterogéneas difíciles de probar |
| Reuse de IA | sí, mediante `--attempts` tras comparar hashes | también sería posible, pero el source combinado no es contractual |
| Riesgo | red larga sin resume/retry | mayor riesgo semántico y de linaje |
| Complejidad | productiva existente | implementación nueva o proceso manual inseguro |
| Plazo | depende del preflight | incompatible con closeout salvo blocker demostrado |

Recomendación: **Option A**. Los artefactos source se reconstruyen; los attempts
compatibles se reutilizan. Si Option A falla operacionalmente, no se adopta
Option B manual: se informa y se decide humanamente el hardening mínimo.

## 18. Final run structure

Naming conceptual, sin crear directorios:

```text
runs/final-multiyear-preflight-20220101-20260820/
└── source/

runs/final-multiyear-<start>-20260820-v1/
├── source/
├── extraction/
├── extraction-reviewed-v1/     # solo si existe una revisión posterior
├── silver/
├── downstream/
└── review/                      # informes humanos, no Parquets editados
```

Cada salida de stage es nueva e inmutable. Una nueva decisión produce un
sufijo/version nueva; no se edita ni renombra un candidato como validado.

El deployment artifact se publica después del gate de deployment, fuera de
`runs/`, con el periodo y downstream ID en su declaración/versionado. El path
concreto aún no tiene convención aprobada y debe cerrarse en ese gate; no se
debe improvisar en el preflight.

## 19. Final build phases

Se recomienda **PHASE-BY-PHASE**, no `run` integral:

1. `source` para el periodo fijo;
2. validar manifest, conteos, duplicados y XML;
3. **STOP FOR HUMAN REVIEW** — aprobar volumen y periodo;
4. `extract --dry-run --attempts <freeze extraction>` sin `--execute-model`;
5. **STOP FOR HUMAN REVIEW** — aprobar llamadas netas y capacidad de revisión;
6. `extract --execute-model` con checkpoint y destino nuevo;
7. revisar `review_queue.parquet`;
8. **STOP FOR HUMAN REVIEW** — resolver blockers sin repetir attempts;
9. `silver --corrections` con el registro completo;
10. validar 13 tablas, corrections y round trip;
11. `downstream` con la referencia INE validada;
12. validar resolución, grouping, Gold, dominios, PK/FK y linaje;
13. **STOP FOR HUMAN REVIEW** — aprobar corpus y downstream ID;
14. construir y validar el deployment artifact;
15. smoke test, performance, seguridad, holdout y evidencia final.

`run` sí propaga el rango a source y orquesta extraction, Silver y downstream,
pero no ofrece pausa después de source, no acepta `--corrections` y, con
`--execute-model`, puede pasar directamente de las descargas a IA. Si no se
autoriza modelo, puede dejar source construido antes de terminar con código 3,
pero esto no sustituye los checkpoints explícitos.

## 20. Preflight specification

El siguiente **FINAL CORPUS PREFLIGHT** debe ocurrir antes de gastar llamadas
al modelo:

1. comprobar branch, HEAD, working tree y que el core freeze sigue intacto;
2. confirmar cutoff fijo `2026-08-20` y escenario a medir;
3. confirmar output nuevo, no symlink, espacio disponible y naming;
4. ejecutar primero `source --dry-run` y revisar rango/destino;
5. ejecutar source-only, con autorización de BOE pero sin modelo;
6. exigir cero fallos de sumario/XML y verificar el manifest;
7. registrar días, items, candidatos, documentos, ratios y distribución anual;
8. exigir BOE IDs únicos y document hashes reproducibles;
9. comparar ID+hash contra los 140 documentos conocidos;
10. registrar conocidos/reutilizables, nuevos y hashes divergentes;
11. ejecutar el plan de extracción sin `--execute-model` y registrar
    deterministas, netos de IA y mínimo de agent runs;
12. registrar retries como riesgo, sin convertirlos en llamadas seguras
    previstas;
13. verificar provider/model/config/instructions/contract IDs;
14. estimar espacio a partir del snapshot source real y verificar espacio libre;
15. comprobar los cinco targets de correcciones;
16. documentar la exclusión de `development_used_documents.csv` del futuro
    holdout y la decisión pendiente de reserva;
17. definir capacidad y responsable de revisión humana;
18. emitir GO/NO-GO para periodo, IA y ruta de output;
19. obtener confirmación humana final antes de `--execute-model`.

El `--dry-run` de `source` no proporciona conteos: el preflight cuantitativo
requiere una ejecución source-only real y, por tanto, llamadas al BOE y un
snapshot nuevo. No se ha realizado en esta auditoría.

## 21. Scenario comparison

| Criterio | 2022 | 2021 | 2020 |
| --- | --- | --- | --- |
| Años aproximados | 4,6 | 5,6 | 6,6 |
| Longitudinal coverage | media | alta | más alta |
| Left-censoring risk | alto | medio | menor, nunca cero |
| Source volume | UNKNOWN; contiene referencia 2023 de 65.818 items | UNKNOWN; > 2022 | UNKNOWN; > 2021 |
| Candidate volume | UNKNOWN; contiene referencia 2023 de 3.615 | UNKNOWN; > 2022 | UNKNOWN; > 2021 |
| Estimated new AI extractions | UNKNOWN | UNKNOWN | UNKNOWN |
| Reuse potential | hasta 133 docs, sujeto a hash | hasta 140 | hasta 140 |
| Human review load | VERY HIGH / UNKNOWN exacta | VERY HIGH | VERY HIGH |
| Schedule risk | RED | RED | RED |
| Methodological value | suficiente solo si se acepta mayor censura | mejor equilibrio | máximo, incremento no medido |
| Recommendation | preflight como feasibility floor | preferir solo si A deja margen | considerar solo si incremento frente a 2021 es manejable |

`KNOWN` en esta tabla se limita a intervalos y referencias locales;
`ESTIMATED` no se utiliza para inventar totales; `UNKNOWN` requiere preflight.

## 22. Deadline risk

Fecha de auditoría: **2026-08-20**. Entrega: **2026-08-31**.

| Escenario | Deadline recommendation | Evidencia, sin estimar horas |
| --- | --- | --- |
| 2022 | RED | el año 2023 por sí solo tiene 3.615 títulos candidatos; faltan source, IA, revisión, Gold, dashboard, deployment y holdout |
| 2021 | RED | añade un año al escenario ya RED y su volumen no está medido |
| 2020 | RED | máximo periodo, sin cobertura local de 2020 y con mayor carga monotónica |

La ruta crítica es:

```text
source completo
→ plan/reuse/IA
→ revisión y correcciones
→ Silver/Gold
→ validación final
→ deployment
→ holdout y evidencia
```

El espacio local no es hoy el riesgo principal: se observaron 803 GiB libres.
El riesgo dominante es el número de candidatos, la fragilidad del source largo,
las llamadas netas y la revisión humana.

Required residuals antes del build:

- decisión humana de periodo;
- source-only preflight completo;
- demostración de ejecución source sin fallos o decisión de hardening;
- conteo neto de IA y capacidad de revisión;
- procedimiento de holdout.

## 23. Parallelizable work

### Dataset-independent

Después de aprobar el preflight pueden avanzar contra el development corpus,
sin cambiar el design freeze:

- funciones puras y tests de queries/KPI ya aprobados;
- layout, estados vacíos y microcopy dentro de la especificación cerrada;
- infraestructura de charts y mapa sin cardinalidades hardcoded;
- mecanismo mailto mínimo;
- documentación de deployment, rollback y seguridad;
- investigación y versionado de geometrías una vez aprobada su fuente.

### Final-data-dependent

Deben repetirse o cerrarse con el deployment dataset:

- cardinalidades, dominios y valores KPI;
- rendimiento y memoria;
- cobertura de códigos INE y joins de geometrías;
- project IDs, grouping y cronologías finales;
- filtros, mapa y charts sobre dominios reales;
- downstream ID, manifest, smoke tests, screenshots y rollback;
- holdout y resultados de la memoria.

### Geometries

```text
EXTERNAL REFERENCE DATA REQUIRED
```

La obtención/validación de geometrías puede avanzar en paralelo cuando exista
una fuente humana aprobada. Esta auditoría no buscó ni descargó geometrías. La
cobertura de todos los códigos INE debe revalidarse después del build final.

## 24. Recommendation

### Recommended ingestion strategy

```text
FULL MULTI-YEAR REBUILD
PHASE-BY-PHASE
```

Construir source una sola vez para el periodo finalmente aprobado, reutilizar
attempts compatibles mediante hashes/config, reconstruir Silver y downstream,
y aplicar las correcciones versionadas. No combinar snapshots y no usar `run`
integral para esta operación con checkpoints/correcciones.

### Recommended period for preflight

```text
HUMAN DECISION AFTER SOURCE-ONLY PREFLIGHT
```

El primer preflight debe medir **Scenario A — 2022-01-01 a 2026-08-20** como
feasibility floor. Si su carga neta no cabe con margen, B y C tampoco caben y
se aplica STOP AND HUMAN DECISION. Solo si A es manejable se mide/autoriza el
incremento de 2021 y después el de 2020 conforme a la regla metodológica.

La fecha final recomendada permanece fija e inclusiva: **2026-08-20**.

## 25. Next gate

### Next step

```text
FINAL CORPUS PREFLIGHT
```

No iniciar el build ni autorizar modelo antes de la decisión de periodo y del
GO humano sobre el preflight.
