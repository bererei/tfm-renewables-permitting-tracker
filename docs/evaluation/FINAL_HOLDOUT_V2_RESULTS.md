# Final Holdout V2 Results

Classification: **P0 / REQUIRED — DOCUMENTATION AND RESULTS PRESENTATION**.

**TECHNICAL EVALUATION FREEZE: COMPLETE — 2026-09-13.**

Documento canónico de resultados experimentales finales. Registra los artefactos
inmutables de V2-B y el diagnóstico posterior aprobado. Este cierre documental
no modifica el experimento, no repite la evaluación y no reanaliza los BOE.
Las secciones 3–6 contienen **PRIMARY RESULTS**; la sección 8 contiene
**POST-HOC DIAGNOSTIC — NOT PRIMARY SCORING**.

## 1. Experimental identity

Identidades completas verificadas en modo read-only antes de redactar este
documento. Las fechas proceden de los registros originales y se expresan en UTC.

| Elemento | Identidad / SHA-256 / fecha |
| --- | --- |
| Frozen production commit, tag `tfm-final` | `282de815bea4e248bdcba2c655e3ee078cb58a49` |
| Truth artifact ID | `e3f300253db94931345e9bbbc489cd810802f94339c3b6a0d751f98b32383b54` |
| Truth manifest SHA-256 | `4f32dc8f89fff8ae1b80f7fb5f94e9168d131f4dea3d0d025640e869c07c148c` |
| Evaluator identity | `a617ef6155cfcd8c403b0c55542cb753fac22f7893f57f3861af665ae23dda5b` |
| Evaluator manifest SHA-256 | `f9e33836d1995a70f24094469cb1e39908e3f30874deee11ba175b5255457d1c` |
| Primary run ID | `final-holdout-v2-primary-001` |
| Prediction snapshot identity | `154c9b42e840f5d3c8989f8470680d040f40113700f040023ebdbae70e21a500` |
| Prediction manifest SHA-256 | `c1464ef49d01f3fe5f7e839fe1af0f00a736d2eba030ebd2871c7760c81c3277` |
| Execution record SHA-256 | `8332a7cfe78455daf5983537db851224455cbdd0455360c04677672df4264181` |
| Evaluation output ID | `4686355d47e0e21ad4b88e313e5ddd9561195e6696893945da6610b1f3b371fd` |
| Evaluation manifest SHA-256 | `1fbd44dea97c03bebb9f34d109862e51e8db181da3ec35b1cf63caadae6e23ae` |
| Fecha de ejecución primaria | 2026-09-13 |
| Inicio del execution record | `2026-09-13T15:06:50.219263+00:00` |
| Fin del execution record | `2026-09-13T15:28:00.612890+00:00` |
| Freeze de predicciones primarias | `2026-09-13T15:32:07.325125+00:00` |
| Creación del informe de evaluación | `2026-09-13T15:36:43.131585+00:00` |

El evaluador definitivo pertenece al checkout
`2c0632b89d59ef3f7e25c24ee61e74ca3ac3c6f1`. Su freeze precede a la
ejecución primaria. El freeze histórico
`runs/final_holdout_p2_v1_evaluator_v2_frozen`, con identidad `956213df…`,
queda **supersedido para este experimento**, conservado sin sobrescritura.

El sistema completo evaluado incluye extracción, canonicalización y validación
documental congeladas. Modelo registrado: `google:gemini-2.5-flash`; proveedor
`gemini`; configuración `4b54b89dbfe8640e`. Los resultados no aíslan el
comportamiento del modelo respecto al procesamiento determinista.

## 2. Holdout composition

**Tabla A — Holdout.**

| Característica | Valor |
| --- | --- |
| Publicaciones | 48 |
| `generation_project_specific` | 30 |
| `not_relevant_for_generation_projects` | 18 |
| Estratos | A/B × 2024/2025/2026: seis |
| Publicaciones por estrato | 8 |
| Eventos truth | 30 |
| Activos de generación truth | 37 |
| Actuaciones truth | 81: 36 actuales y 45 antecedentes |
| Localizaciones truth | 111 |

Los 45 antecedentes se conservan para diagnóstico temporal y P0, pero no
forman parte del denominador positivo de detección de actuaciones actuales.
La selección y la frontera de exposición de desarrollo se describen en
[Holdout exposure provenance](../HOLDOUT_EXPOSURE_PROVENANCE.md) y el
[contrato V2](FINAL_HOLDOUT_EVALUATION_CONTRACT_V2.md). El archivo de selección
congelado se identifica en la sección 11.

## 3. Primary results

**PRIMARY RESULTS — V2-B congelado.**

Fuente: `evaluation_summary.json` y tablas del informe inmutable. Las tablas
Markdown presentan los valores decimales a diez decimales; los bloques LaTeX
los presentan a seis y el JSON conserva la precisión original. El redondeo
de presentación no cambia las métricas.
La agregación es micro sobre el corpus.

**Tabla B — Entity detection**, con la fila relacional de actuación → activo
como referencia conjunta; esta última no representa otra clase de entidad.

| Entity | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| Generation assets | 20 | 19 | 17 | 0.5128205128 | 0.5405405405 | 0.5263157895 |
| Events | 13 | 25 | 17 | 0.3421052632 | 0.4333333333 | 0.3823529412 |
| Administrative actions (current) | 1 | 57 | 35 | 0.0172413793 | 0.0277777778 | 0.0212765957 |
| Locations | 43 | 95 | 68 | 0.3115942029 | 0.3873873874 | 0.3453815261 |
| Action → asset | 1 | 59 | 38 | 0.0166666667 | 0.0256410256 | 0.0202020202 |

`historical_not_extracted=45` y `historical_contamination_fp=0`. El segundo
valor cuenta predicciones emparejadas con antecedentes; no demuestra ausencia
semántica de antecedentes entre las predicciones sin match.

**Document scope:** correctos = 46; denominador = 48;
accuracy = **0.9583333333**. No se combina con las métricas de entidades.

**Tabla D — Document scope confusion matrix.**

| Truth / Prediction | `generation_project_specific` | `not_relevant_for_generation_projects` | `missing` |
| --- | --- | --- | --- |
| `generation_project_specific` | 30 | 0 | 0 |
| `not_relevant_for_generation_projects` | 1 | 16 | 1 |

Los errores son `BOE-A-2025-13309` (negativo truth, positivo predicho) y
`BOE-B-2024-32569` (negativo truth, predicción ausente por fallo terminal).
No hay clase truth `missing`; sí una columna predicha `missing`.

**Tabla E — Action → asset.**

| TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- |
| 1 | 59 | 38 | 0.0166666667 | 0.0256410256 | 0.0202020202 |

Los denominadores primarios de pares son 60 para precisión y 39 para recall.
La unidad es la relación entre actuación y activo local de generación; no se
evalúa aquí el agrupamiento posterior de proyectos Gold.

## 4. Conditional attributes

**PRIMARY RESULTS. Tabla C — Conditional attributes.**

| Attribute | Correct | Denominator (N) | Accuracy |
| --- | --- | --- | --- |
| generation_type | 20 | 20 | 1.0000000000 |
| location_level | 43 | 43 | 1.0000000000 |
| action_type | 1 | 1 | 1.0000000000 |
| decision | 1 | 1 | 1.0000000000 |
| is_modification | 1 | 1 | 1.0000000000 |
| affected_assets exact-set | 1 | 1 | 1.0000000000 |

Todas estas accuracies se condicionan a pares correctamente emparejados y
campos aplicables. Los atributos de actuación y el conjunto exacto se
condicionan además a actuaciones actuales. No se usan los atributos para
crear correspondencias. El conjunto exacto tiene un caso aplicable; las
otras 92 filas diagnósticas de conjuntos quedan fuera de ese denominador.

Redacción válida: «Entre las actuaciones actuales emparejadas, el tipo, la
decisión y el indicador de modificación coincidieron con la referencia en
el único caso evaluable —1/1 para cada atributo—». No presentar ese 1/1 como
evidencia general de rendimiento de actuaciones.

## 5. Evidence

**PRIMARY RESULTS:** `supported=0`, `denominator=1`,
`support_rate=0.0000000000`.

El denominador contiene solo actuaciones actuales emparejadas. El único caso
es `BOE-A-2026-7540|action_6` frente a
`BOE-A-2026-7540|pred_event_1:action_3`.

Su evidencia predicha contiene los fragmentos separados:

> se declara, en concreto, la utilidad pública [...] de la modificación de la línea subterránea a 30 kV

El segundo fragmento está dentro del pasaje aceptado y permite el candidato.
El primero no lo está: el pasaje truth comienza «Declarar, en concreto, la
utilidad pública». La regla de candidato exige algún fragmento respaldado;
la de soporte exige todos. Esta explicación documental del caso no añade
una tasa independiente ni una nueva adjudicación.

El 0/1 no mide la evidencia de todas las actuaciones extraídas, ni constituye
una medida general de comprensión semántica.

## 6. P0

**PRIMARY RESULTS. Tabla F — P0/evidence.**

| Medida | Valor | Denominador / interpretación |
| --- | --- | --- |
| Evidence supported | 0 | 1 actuación actual emparejada |
| Evidence support rate | 0.0000000000 | 0/1 |
| P0 TP | 0 | Antecedentes emparejados con warning |
| P0 FP | 0 | Actuaciones actuales emparejadas con warning |
| P0 FN | 0 | Antecedentes emparejados sin warning |
| P0 TN | 1 | Actuaciones actuales emparejadas sin warning |
| P0 adjudicated | 1 | Universo total adjudicable |
| P0 unadjudicated | 1 | Warning sin adjudicación segura; fuera del denominador |
| P0 missing_extraction_not_p0_fn | 45 | Antecedentes sin extracción emparejada; no son FN de P0 |
| P0 precision | `null` | TP + FP = 0; `zero_denominator` |
| P0 recall | `null` | TP + FN = 0; `zero_denominator` |
| P0 F1 | `null` | `undefined_precision_or_recall` |
| P0 false warning rate | 0.0000000000 | FP / (FP + TN) = 0/1 |

`null` significa «no definido», no cero. El detector se evalúa sobre
actuaciones extraídas y adjudicables; los 45 antecedentes sin match no
constituyen oportunidades observadas de detección para P0.

El TN corresponde a la actuación actual emparejada de `BOE-A-2026-7540`.
El warning no adjudicado corresponde a `BOE-A-2026-4227`,
`pred_event_1:action_3`. No se convierte retrospectivamente en FP o TP.

Este holdout no aporta antecedentes extraídos emparejados suficientes para
estimar sensibilidad de P0. La tasa 0/1 tampoco permite generalizar su
comportamiento ante actuaciones actuales.

**Evidencia separada de desarrollo:** el
[replay específico previo](../FINAL_W14_ADMIN_ACTION_TEMPORAL_AUDIT.md)
documenta 11/11 antecedentes detectados y 0/5 controles negativos.
No se volvió a ejecutar en este cierre, no pertenece al holdout y sus
conteos o métricas no se agregan a la Tabla F.

## 7. Terminal execution outcome

| Estado final | Documentos |
| --- | --- |
| TERMINAL_SUCCESS | 47 |
| TERMINAL_ERROR | 1 |
| PENDING | 0 |
| STARTED | 0 |
| INDETERMINATE | 0 |
| Total | 48 |

`TERMINAL_SUCCESS` es un estado operativo de extracción y no significa que
la predicción sea semánticamente correcta.

El error terminal es **BOE-B-2024-32569**:
`DocumentExtractionValidationError`, etapa `document_validation`, con ocho
incidencias de denominaciones no identificadas como plantas de generación
por la validación documental. El intento y sus payloads fallidos quedan
preservados. No se reintentó después del protocolo ni se sustituyó su salida.

El registro conserva un intento documental y cero retries explícitos de
errores previos. El uso reportado es 2 requests, 24.476 tokens de entrada,
26.325 de salida y 50.801 totales; no representa un recuento independiente
de llamadas HTTP. No se estima uso adicional.

El evaluador trata la predicción como ausente al estar en estado `error`.
Aporta un error de scope; aporta cero FP/FN de entidades y cero errores de
pares actuación → activo porque la truth del BOE es negativa. No se
aprovecha el payload fallido para reemplazar ese resultado.

## 8. Post-hoc diagnostic

**POST-HOC DIAGNOSTIC — NOT PRIMARY SCORING**

Esta sección transcribe el diagnóstico read-only ya verificado y aprobado.
No forma parte del scoring preespecificado, no crea nuevos matches, no usa
fuzzy matching y no modifica resultados. Las categorías explican las filas
existentes; no son estimaciones de rendimiento bajo otras reglas.

### Cascada assets → events → actions

| Etapa | Truth | Predicción | Matches primarios |
| --- | --- | --- | --- |
| Activos de generación | 37 | 39 | 20 |
| Eventos | 30 | 38 | 13 |
| Actuaciones actuales / actuaciones predichas | 36 actuales | 58 | 1 actual |

De los 20 activos emparejados, 13 pertenecen a eventos emparejados y siete
a eventos sin match. Los 13 eventos emparejados contienen 18 actuaciones
truth actuales y 21 predichas; solo una arista candidata de actuación llega
a match. Las otras 18 actuaciones truth actuales quedan bajo eventos sin match.

### Actions

| Motivo diagnóstico prioritario | FN actuales | FP predichos |
| --- | --- | --- |
| DOCUMENT_FAILURE | 0 | 0 |
| EVENT_UNMATCHED | 18 | 37 |
| ACTION_NO_EVIDENCE_CANDIDATE | 17 | 20 |
| ACTION_AMBIGUOUS | 0 | 0 |
| OTHER | 0 | 0 |
| Total | 35 | 57 |

No hay ambigüedades registradas. La actuación adicional del BOE con scope
incorrecto está incluida en los 37 FP bajo eventos sin match.

De las 20 predicciones sin candidato bajo eventos emparejados, 18 utilizan
exactamente el título del BOE como evidencia final y dos otro fragmento.
El matching exige que un fragmento predicho esté contenido en un pasaje
aceptado de esa actuación; la equivalencia semántica o la contención inversa
no satisfacen automáticamente esa regla.

La función productiva congelada
`src/renewables_permitting/extraction/canonicalization.py::_repair_action_evidence`
puede priorizar el título. El diagnóstico previo verificó, por ejemplo, una
evidencia precanónica más corta y el título en la salida final de
`BOE-A-2024-2440`. No atribuir automáticamente a Gemini una decisión del
sistema completo ni presentar ese caso como evaluación de una salida alternativa.

### Assets

| Variante / discrepancia textual | FN | FP |
| --- | --- | --- |
| Abreviación o ausencia del descriptor incluido en truth | 14 | 14 |
| Adición de «existente» | 2 | 2 |
| PFVH San Blas / Planta fotovoltaica San Blas | 1 | 1 |
| Envatios XXIV - Fase I adicional | 0 | 1 |
| Activo del BOE con scope incorrecto | 0 | 1 |
| Total | 17 | 19 |

La semejanza textual observada no crea correspondencias primarias.
«Instalación fotovoltaica Hipódromo» y «Hipódromo» ilustran la sensibilidad
a descriptores. No se aplica normalización retrospectiva adicional.

### Events

| Clasificación prioritaria | FN | FP |
| --- | --- | --- |
| Asociados a algún activo truth sin match | 15 | 20 |
| Evento dividido con todos sus activos ya emparejados | 2 | 4 |
| Evento adicional por scope incorrecto | 0 | 1 |
| Total | 17 | 25 |

Los dos casos de división con activos emparejados son `BOE-A-2024-11661`
y `BOE-A-2024-27075`. En cada uno, un evento truth con dos activos se
divide en dos eventos predichos de un activo. Otros splits concurren con
variantes de alias; no se suman como causas independientes a esta tabla.
No se observaron merges.

### Locations

| Contexto jerárquico | FN | FP |
| --- | --- | --- |
| Evento padre sin match | 61 | 92 |
| Dentro de eventos emparejados | 7 | 3 |
| Total | 68 | 95 |

Por ejemplo, San Blas repite siete localizaciones en dos eventos sin match:
14 FP/6 FN. Esto no equivale a catorce topónimos inventados. Dentro de
eventos emparejados también hay discordancias raw, provincias presentes solo
como hints y localizaciones adicionales respecto a truth.

### Action → asset

| Estado de actuación | Estado de activo | TP | FP | FN |
| --- | --- | --- | --- | --- |
| Emparejada | Emparejado | 1 | 0 | 0 |
| Sin match | Emparejado | 0 | 28 | 22 |
| Sin match | Sin match | 0 | 31 | 16 |
| Total | | 1 | 59 | 38 |

Todos los FP/FN de pares pertenecen a actuaciones sin match. En parte de ellos
concurre además un activo sin match. Dentro de la única actuación emparejada,
exact-set = 1/1. Estas dependencias no son causas independientes sumables.

## 9. Representative cases

Selección previamente realizada por diversidad de patrones, conservada sin
una nueva anotación ni búsqueda de casos favorables.

| BOE | Patrón | Observación y límite interpretativo |
| --- | --- | --- |
| BOE-A-2024-14295 | Exclusión correcta | Normas UNE; scope negativo correcto y ninguna entidad. Acierto de scope, no prueba de extracción de eventos. |
| BOE-A-2025-13309 | Scope incorrecto | Asociación de presa/canal con Lafortunada-Cinqueta; 1 FP de activo, 1 de evento, 1 de actuación y 3 de localización respecto a truth. |
| BOE-A-2024-27493 | Alias | Hipódromo abreviado frente a denominación completa; propaga errores al evento y sus entidades. |
| BOE-A-2024-11661 | Split | Dos activos TP, pero evento 0 TP/2 FP/1 FN; identificación y agrupación son tareas distintas. |
| BOE-A-2024-2440 | Evidencia | Activo, evento y tres localizaciones emparejados; actuación sin candidato por título frente a disposición aceptada. |
| BOE-A-2025-13972 | Localizaciones repetidas | San Blas: 14 FP/6 FN bajo eventos sin match; jerarquía y granularidad concurren. |
| BOE-A-2025-17759 | Contexto y atributos | Cedillo adicional por proximidad; tipo/decisión diferentes de truth, fuera del denominador condicional. |
| BOE-A-2026-7540 | Único TP de actuación | Atributos y activos afectados correctos; soporte incompleto de evidencia. No generalizable con n=1. |
| BOE-B-2026-26939 | Omisión / representación | Dos actuaciones actuales truth frente a una predicha; Málaga aparece como hint, no como entidad. |
| BOE-B-2024-32569 | Terminal error | Scope ausente; sin errores de entidades porque truth no tiene entidades positivas. |

## 10. Interpretation boundaries

- **No existe global accuracy:** scope, detección, atributos, atribución,
  evidencia y P0 tienen tareas y denominadores distintos.
- **Los atributos son condicionales:** no describen las entidades sin match
  ni sustituyen precisión y recall de detección.
- **Evidence tiene denominator=1:** su resultado no es una tasa general de
  evidencia del sistema ni una prueba independiente de comprensión.
- **P0 no tiene positivos emparejados:** precisión/recall/F1 indefinidos;
  0/1 falsas alarmas no demuestra ausencia general de falsas alarmas.
- **El diagnóstico post-hoc no cambia scoring:** no convierte variantes
  nominales o citas relacionadas en nuevos TP.
- **El matching jerárquico propaga errores:** los fallos de diferentes niveles
  no son independientes ni siempre representan contenidos inventados.
- **Se evalúa el sistema completo:** canonicalización y validación documental
  intervienen en la salida final; no se atribuyen todos los errores al modelo.
- **La integridad no acredita exhaustividad semántica:** hashes y completitud
  no prueban por sí solos cobertura de todos los alias/pasajes ni una segunda
  revisión humana independiente. La memoria debe describir la provenance de
  anotación realmente documentada, sin inventar revisores o acuerdos.
- **No se encontró evidencia de implementation defect** en el diagnóstico
  aprobado. La constatación es acotada a las rutas examinadas; las reglas
  estrictas observadas coinciden con el contrato congelado.

## 11. Reproducibility

Todas las rutas siguientes son relativas a la raíz del repositorio. Los
artefactos operativos deben conservarse/distribuirse fuera de Git manteniendo
su estructura y hashes; una ruta o un hash no sustituye al archivo accesible.

| Artefacto | Ruta |
| --- | --- |
| Frozen truth | `runs/final_holdout_p2_v1_truth_v2_frozen` |
| Selección congelada | `runs/final_holdout_p2_v1_truth_v2_frozen/holdout_selection.csv` |
| Evaluador definitivo | `runs/final_holdout_p2_v1_evaluator_v2_frozen_2c0632b` |
| Run primario y journal | `runs/final-holdout-v2-primary-001` |
| Predicciones primarias | `runs/final-holdout-v2-primary-001/primary/extraction` |
| Execution record original | `runs/final-holdout-v2-primary-001/finalization/execution_record.json` |
| Provenance y manifest de finalización | `runs/final-holdout-v2-primary-001/finalization` |
| Evaluación | `runs/final-holdout-v2-evaluation-primary-001` |
| Métricas primarias | `runs/final-holdout-v2-evaluation-primary-001/evaluation_summary.json` |

Bindings adicionales del execution record:

| Binding | Identidad / SHA-256 |
| --- | --- |
| Holdout | `4e71f86cbaf23ba2d26c97fbd5a65b2acb0ccc7cd41616b626ec603f4f4fab4a` |
| Source snapshot | `1d3eec6ac15e293dbd83c80d8c8504b3d425e1fb07d8e84b8cfbb0ebbd659cbf` |
| `uv.lock` | `af47371305913f4913c05a73448a8be92f44fbceb3f604b491d629cc80639229` |

El informe contiene doce tablas Parquet, el resumen, copias de los manifests
truth/evaluador y del execution record, y su manifest: 17 archivos.
Las tablas son `document_results`, `entity_results`, `candidate_pairs`,
`entity_matches`, `unmatched_truth`, `unmatched_predictions`,
`field_results`, `affected_asset_sets`, `action_asset_pairs`,
`evidence_results`, `p0_results` y `error_inventory`.

`validate-evaluation` verifica hashes, identidad semántica del informe y las
copias de provenance. No ejecuta scoring ni necesita leer las predicciones
originales. No verifica por sí solo el directorio original de predicciones;
este se verificó además con `load_prediction_snapshot` y
`validate_primary_predictions`. La copia del execution record en evaluación
es byte-idéntica al original.

Los siguientes comandos existentes se ejecutaron desde el entorno local
preparado, sin red ni cambios de dependencias, antes de editar documentación.
Usar el checkout del evaluador `2c0632b…` con el entorno asociado a `uv.lock`.
No requieren API key ni cargar `.env`.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m evaluation.final_holdout_v2.cli \
  validate-frozen-truth \
  --truth runs/final_holdout_p2_v1_truth_v2_frozen \
  --expected-manifest-sha256 4f32dc8f89fff8ae1b80f7fb5f94e9168d131f4dea3d0d025640e869c07c148c

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m evaluation.final_holdout_v2.cli \
  validate-evaluator \
  --evaluator runs/final_holdout_p2_v1_evaluator_v2_frozen_2c0632b \
  --expected-evaluator-identity a617ef6155cfcd8c403b0c55542cb753fac22f7893f57f3861af665ae23dda5b \
  --expected-manifest-sha256 f9e33836d1995a70f24094469cb1e39908e3f30874deee11ba175b5255457d1c

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m evaluation.final_holdout_v2.cli \
  validate-execution-record \
  --record runs/final-holdout-v2-primary-001/finalization/execution_record.json

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m evaluation.final_holdout_v2.cli \
  validate-evaluation \
  --evaluation runs/final-holdout-v2-evaluation-primary-001 \
  --expected-manifest-sha256 1fbd44dea97c03bebb9f34d109862e51e8db181da3ec35b1cf63caadae6e23ae
```

Resultado: las cuatro CLI terminan con exit 0; truth informa
`frozen_truth_intact=true` y las otras tres `valid=true`. La validación
adicional de predicciones confirma su identidad, inventario, conteos y linaje
primario. Journal y metadata confirman 47 TERMINAL_SUCCESS, un TERMINAL_ERROR
y cero estados pendientes/iniciados/indeterminados. No se volvió a ejecutar
`evaluate`, la extracción ni la suite de tests.

Los encabezados pendientes de documentos históricos de implementación
describen aquellos bloques; este informe y [TFM_CLOSEOUT](../TFM_CLOSEOUT.md)
son la declaración del estado final. El contrato metodológico permanece intacto.

## Memory integration map

El documento activo [tfm_report_bgd.tex](../tfm_report/tfm_report_bgd.tex)
integra los capítulos `01`–`09` y `chapters/anexos.tex`. Los antiguos
`chapters/ch1.tex`–`ch3.tex` se conservan únicamente como ejemplos históricos y
no participan en la compilación. El contenido de evaluación ya se ha incorporado
a metodología experimental, resultados, discusión, conclusiones y anexos. La
bibliografía activa contiene 18 referencias utilizadas.

La compilación reproducible actual tiene 105 páginas A4 antes de cerrar Resumen,
Abstract y los demás elementos finales pendientes; por ello la paginación aún
puede cambiar. El mapa siguiente registra la ubicación editorial actual, no una
nueva fase experimental ni una modificación de los resultados.

| Resultado / evidencia | Integración actual | Tabla/Figura |
| --- | --- | --- |
| Composición y selección del holdout; contrato V2 | Capítulo 6, metodología experimental | Tabla de composición del holdout |
| Arquitectura BOE → extracción/validación → Silver → INE/agrupación → Gold → consulta | Capítulo 4, metodología y arquitectura | Figura de arquitectura; rama experimental separada en el capítulo 6 |
| Detección de entidades | Capítulo 7, resultados | Tabla de detección |
| Atributos condicionados y denominadores | Capítulo 7, resultados | Tabla de atributos condicionados |
| Scope y matriz de confusión | Capítulo 7, resultados | Matriz de clasificación documental |
| Actuación → activo | Capítulo 7, resultados | Tabla de pares actuación–activo |
| P0 y evidence | Capítulo 7; interpretación y límites en el capítulo 8 | Tabla de P0 y evidencia |
| Cascada y taxonomía aprobada | Capítulos 7 y 8 | Figura de cascada activos → eventos → actuaciones/localizaciones |
| Casos representativos | Capítulos 7 y 8 | Casos compactos y remisiones al detalle pertinente |
| Terminal error y resultado operativo | Capítulo 7 | Estado final de la ejecución |
| IDs, hashes, entorno y verificaciones | Capítulo 6 y anexos | Identidades y procedimiento reproducible |
| Aplicación sobre Gold | Capítulo 5 | Capturas finales todavía pendientes de cierre |

Fuentes de arquitectura y metodología revisadas:
[calidad de extracción](../architecture/extraction_quality_review.md),
[downstream W14](../FINAL_CORPUS_W14_DOWNSTREAM_MATERIALIZATION.md),
[guía técnica de aplicación](../STREAMLIT_CODE_GUIDE.md),
[contrato V2](FINAL_HOLDOUT_EVALUATION_CONTRACT_V2.md),
[procedimiento V2-B](V2_B_EVALUATOR.md) y
[guía de usuario](../USER_GUIDE.md).
Para las identidades finales de Gold, usar el estado corregido registrado en
`TFM_CLOSEOUT.md`, no el snapshot histórico v1 del informe downstream.
Gold y Streamlit no reciben métricas de este holdout.

La integración editorial no cambia truth, evaluador, predicciones, matching,
denominadores, métricas ni diagnóstico post-hoc. Las capturas y los elementos
finales de la memoria permanecen sujetos a sus gates de cierre.

## Results-ready statements

**Frases factuales basadas en PRIMARY RESULTS; listas para adaptar a la memoria.**

1. La evaluación final incluyó 48 publicaciones distribuidas en seis estratos,
   con 30 documentos relevantes y 18 no relevantes según la referencia humana.
2. La clasificación documental coincidió con la referencia en 46 de 48 casos,
   con una accuracy de 0,9583333333.
3. La detección produjo 20 TP de activos, 13 de eventos, uno de actuaciones
   actuales y 43 de localizaciones.
4. Los F1 fueron 0,5263157895 para activos, 0,3823529412 para eventos,
   0,0212765957 para actuaciones y 0,3453815261 para localizaciones.
5. Los atributos coincidieron en los pares aplicables: 20/20 tipos de
   generación, 43/43 niveles de localización y 1/1 para cada atributo de actuación.
6. La atribución actuación → activo produjo un TP, 59 FP y 38 FN; el único
   conjunto de activos evaluable sobre actuaciones emparejadas fue correcto.
7. La comprobación de evidencia tuvo un único caso evaluable y ningún caso
   completamente respaldado por los pasajes aceptados.
8. P0 registró un TN y un warning sin adjudicación; precisión, recall y F1
   quedaron indefinidos por ausencia de denominadores positivos.
9. El run concluyó con 47 documentos TERMINAL_SUCCESS y uno TERMINAL_ERROR,
   cuyo resultado fallido se preservó dentro de la evaluación.

## Discussion-ready statements

**Interpretaciones POST-HOC DIAGNOSTIC; no son nuevas métricas primarias.**

1. La dependencia jerárquica del matching permite que una discrepancia en un
   activo o evento se propague a actuaciones y localizaciones.
2. Los FN de activos asociados a variantes nominales no equivalen por sí solos
   a omisiones semánticas, aunque permanecen FN bajo la regla preespecificada.
3. La utilización de títulos en la salida final y de pasajes específicos en
   truth limita las correspondencias bajo contención literal direccional.
4. El comportamiento observado corresponde al sistema completo; la
   canonicalización puede determinar la evidencia final y no debe confundirse
   automáticamente con una decisión del modelo generativo.
5. Los atributos condicionados describen un subconjunto seleccionado por el
   matching y no permiten generalizar su accuracy a entidades sin correspondencia.
6. Los errores de actuación → activo dependen de actuaciones sin match, por lo
   que no constituyen una evaluación independiente de la resolución de targets.
7. Las localizaciones combinan efectos de jerarquía, granularidad y selección
   de contexto; el total de FP no puede identificarse con topónimos inventados.
8. La falta de antecedentes extraídos emparejados limita la evaluación de P0;
   el replay de desarrollo aporta contexto separado, sin completar ese denominador.
9. La ausencia de evidencia de implementation defect permite interpretar las
   reglas congeladas, pero no elimina sus limitaciones ni autoriza tuning
   retrospectivo sobre este holdout.

## LaTeX-ready tables

Las letras A–F son referencias de trabajo; LaTeX asignará la numeración final.
Los bloques se pueden trasladar a la plantilla XeLaTeX existente. Usan entornos
básicos, sin añadir paquetes. Para legibilidad tipográfica muestran seis
decimales; son redondeos de los mismos valores primarios de las tablas Markdown,
no métricas alternativas. La tabla F conserva `null` explícito. No se ha
compilado ni modificado la plantilla en este bloque.

### Tabla A — Holdout

```latex
\begin{table}[htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{p{6cm}p{6cm}}
\hline
Característica & Valor \\
\hline
Publicaciones & 48 \\
Proyectos específicos de generación & 30 \\
No relevantes para generación & 18 \\
Estratos & A/B $\times$ 2024/2025/2026 \\
Publicaciones por estrato & 8 \\
Eventos truth & 30 \\
Activos truth & 37 \\
Actuaciones truth & 36 actuales y 45 antecedentes \\
Localizaciones truth & 111 \\
\hline
\end{tabular}
\caption{Composición del holdout final V2.}
\label{tab:holdout-v2-a}
\end{table}
```

### Tabla B — Entity detection

```latex
\begin{table}[htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{lrrrrrr}
\hline
Entidad / relación & TP & FP & FN & Precisión & Recall & F1 \\
\hline
Activos de generación & 20 & 19 & 17 & 0.512821 & 0.540541 & 0.526316 \\
Eventos & 13 & 25 & 17 & 0.342105 & 0.433333 & 0.382353 \\
Actuaciones actuales & 1 & 57 & 35 & 0.017241 & 0.027778 & 0.021277 \\
Localizaciones & 43 & 95 & 68 & 0.311594 & 0.387387 & 0.345382 \\
Actuación $\rightarrow$ activo & 1 & 59 & 38 & 0.016667 & 0.025641 & 0.020202 \\
\hline
\end{tabular}
\caption{Resultados primarios V2-B; agregación micro. La última fila mide pares actuación--activo.}
\label{tab:holdout-v2-b}
\end{table}
```

### Tabla C — Conditional attributes

```latex
\begin{table}[htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{lrrr}
\hline
Atributo & Correctos & N & Accuracy \\
\hline
generation\_type & 20 & 20 & 1.000000 \\
location\_level & 43 & 43 & 1.000000 \\
action\_type & 1 & 1 & 1.000000 \\
decision & 1 & 1 & 1.000000 \\
is\_modification & 1 & 1 & 1.000000 \\
affected\_assets exact-set & 1 & 1 & 1.000000 \\
\hline
\end{tabular}
\caption{Accuracies condicionadas a pares emparejados y aplicables. Las actuaciones tienen N=1.}
\label{tab:holdout-v2-c}
\end{table}
```

### Tabla D — Document scope confusion matrix

G = `generation_project_specific`; N = `not_relevant_for_generation_projects`.

```latex
\begin{table}[htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{lrrr}
\hline
Truth / Predicción & G & N & Missing \\
\hline
G & 30 & 0 & 0 \\
N & 1 & 16 & 1 \\
\hline
\end{tabular}
\caption{Matriz de scope: G, generación específica; N, no relevante. Accuracy: 46/48.}
\label{tab:holdout-v2-d}
\end{table}
```

### Tabla E — Action → asset

```latex
\begin{table}[htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{rrrrrr}
\hline
TP & FP & FN & Precisión & Recall & F1 \\
\hline
1 & 59 & 38 & 0.016667 & 0.025641 & 0.020202 \\
\hline
\end{tabular}
\caption{Pares actuación--activo. Denominadores: precisión, 60; recall, 39.}
\label{tab:holdout-v2-e}
\end{table}
```

### Tabla F — P0/evidence

```latex
\begin{table}[htbp]
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{p{4cm}lp{6cm}}
\hline
Medida & Valor & Denominador / interpretación \\
\hline
Evidence supported & 0 & 1 actuación actual emparejada \\
Evidence support rate & 0.000000 & 0/1 \\
P0 TP / FP / FN / TN & 0 / 0 / 0 / 1 & 1 actuación adjudicable \\
P0 unadjudicated & 1 & Warning fuera del denominador \\
Antecedentes sin match & 45 & No son FN de P0 \\
P0 precision & null & TP + FP = 0 \\
P0 recall & null & TP + FN = 0 \\
P0 F1 & null & Precisión/recall no definidos \\
P0 false warning rate & 0.000000 & FP / (FP + TN) = 0/1 \\
\hline
\end{tabular}
\caption{P0 y evidencia: resultados y denominadores. Null indica una métrica no definida.}
\label{tab:holdout-v2-f}
\end{table}
```
