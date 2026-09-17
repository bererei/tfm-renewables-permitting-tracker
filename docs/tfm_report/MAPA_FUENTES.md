# Mapa de fuentes y plan de redacción

Fecha: 2026-09-15. Clasificación: **REQUIRED — revisión humana integral de la memoria**.
La revisión partió de `tfm-evaluation@584ba04565c11808315af5e8ffd8f4eddb58de82`
con árbol limpio. El working tree contiene únicamente los cambios documentales
de esta fase. No se hace fetch, staging, commit o push.
Documento de trabajo para revisión; no se incorpora al PDF.
Reglas pedagógicas vigentes: [REGLAS_REDACCION.md](REGLAS_REDACCION.md).
El capítulo 2 conserva la función y los límites del BOE; el capítulo 3 concentra
el acceso programático, los candidatos, la persistencia y los corpus.
Las rutas indicadas son relativas a la raíz del repositorio.

## Regla de uso

El estado vigente procede de `docs/TFM_CLOSEOUT.md`, checkpoint de septiembre.
Las cifras experimentales proceden exclusivamente de
`docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md`. Los contratos fijan las reglas;
los informes históricos explican decisiones en su fecha. No se recalculan
métricas ni se convierten diagnósticos posteriores en puntuación primaria.

Sistema evaluado: `tfm-final@282de815bea4e248bdcba2c655e3ee078cb58a49`.
La rama de redacción es `tfm-evaluation`. La primera fase partió de
`8e85ea58340deb929e95ebab80693a1e5d473864`. La fase anterior del núcleo metodológico partió de
`0387e765e4155f4f67bb9ab6fc8fd58b69927166`, con árbol limpio y la referencia
local `origin/tfm-evaluation` en el mismo commit. No se hace fetch, commit o push.
El Gold final es v2, con downstream ID
`316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86`.
Estas identidades se transcriben de la documentación, sin rematerializar datos.

## 1. Introducción — redactado para revisión

Archivo: `chapters/01_introduccion.tex`.

- Fuentes principales: `README.md`, `AGENTS.md`, `docs/TFM_CLOSEOUT.md`,
  `docs/USER_GUIDE.md` §§1–3 y 16.
- Reutilizado de `chapters/ch1.tex`: pregunta sobre evolución administrativa
  y propósito de seguimiento. El resto era demostrativo.
- Límite de evaluación: resultados canónicos §§1, 3 y 10; las métricas no
  evalúan Gold, agrupación longitudinal o usabilidad.
- Alcance temporal: `docs/FINAL_CORPUS_W14_EXTRACTION_UNION.md` §15 y
  `docs/FINAL_W14_ADMIN_ACTION_CORRECTIONS.md` §9.
- TODO-CITA: motivación institucional de transición energética. No se añaden
  porcentajes, previsiones o cifras de potencia sin fuente.

## 2. Contexto administrativo y BOE — redactado para revisión

Archivo: `chapters/02_contexto.tex`.

- Referencias existentes reutilizadas: Ley 24/2013, Ley 21/2013,
  Real Decreto 1955/2000 y documentación de API BOE en `bib/ref.bib`.
  No se verificaron en web los textos legales consolidados ni sus artículos.
- Semántica documental: `AGENTS.md`, `docs/USER_GUIDE.md`,
  `docs/FINAL_W14_ADMIN_ACTION_TEMPORAL_AUDIT.md` y
  `docs/FINAL_W14_ADMIN_ACTION_CORRECTIONS.md`.
- Ejemplo: Don Rodrigo II, BOE-B-2026-12663 (23/04/2026) y
  BOE-A-2026-17939 (19/08/2026). Se reutiliza la traza comprobada de la auditoría,
  junto con el estado corregido aprobado; no se inspeccionan nuevos BOE ni se
  utiliza un caso del holdout como motivación de desarrollo.
- Acceso programático (2.2): concepto, necesidad y diferencia entre metadatos
  de sumarios y XML de candidatos; detalle aplicado en 3.2. Confirmación en
  `boe_source.py`, `boe_documents.py` y `pipeline.py::run_source_stage`.
- Tabla 2.2: dos publicaciones de Don Rodrigo II, derivada exclusivamente
  de la traza de la auditoría temporal y su corrección aprobada.
- TODO-CITA: acceso y conexión; artículos/versiones aplicables a información
  pública, estudio/DIA/informe, AAP/AAC/DUP/explotación; alcance institucional
  del BOE. Revisar fecha de la entrada del RD 1955/2000 (actualmente 2001).
- No se inventa una secuencia legal universal ni se deriva estado operativo
  de una autorización previa o de construcción.

## 3. Datos y corpus — redactado para revisión de contenido

Archivo: `chapters/03_datos.tex`. Seis secciones completas; no quedan TODO
sustantivos. F02 incorporada; tabla compacta con finalidad, periodo/referencia,
BOE y uso. Cifras transcritas de fuentes canónicas, sin recálculo.

En las matrices, código relativo a `src/renewables_permitting/`, tests relativos
a `tests/`. «—» significa que la afirmación no requiere manifest propio.

| Sección | Documentación | Código | Tests revisados como respaldo | Manifests / notas históricas |
| --- | --- | --- | --- | --- |
| 3.1 BOE como fuente | User Guide §§1–3; contexto 2.2; correcciones W14 §6 | `boe_source.py`, `boe_documents.py` | `test_boe_source.py`, `test_boe_documents.py` | Ejemplo Don Rodrigo II previamente verificado; función oficial del BOE pendiente de referencia externa |
| 3.2 API y adquisición | User Guide §10; documentación API ya citada en 2.2 | `boe_source.py::fetch_boe_summary`, `parse_boe_summary`; `boe_http.py`; `boe_documents.py`; `pipeline.py::run_source_stage` | Pruebas de retries/404, XML y persistencia de `test_boe_source.py`, `test_boe_documents.py`; garantías fuente de `test_pipeline.py` localizadas | Esquema del manifest de source en `pipeline.py`; `FINAL_CORPUS_INGESTION_AUDIT.md` solo como historia: «sin retries» no describe el código actual |
| 3.3 Candidatos/relevancia | Guía de calidad; `FINAL_CORPUS_CANDIDATE_FUNNEL_AUDIT.md` y preflight P2 como antecedentes de decisiones | `boe_candidates.py::TITLE_KEYWORDS`, `select_energy_candidates`; `extraction/canonicalization.py::_scope_guard_from_document`; `runner.py` | `test_boe_candidates.py`: título como único seleccionador, sin mutación; tests de alcance/validación de extracción | Política `title_keywords_v1` y su identidad; alcance actual v4. El ejemplo de carretera es hipotético, no una observación nueva |
| 3.4 Identidad | User Guide §3 | `extraction/documents.py::_source_document_hash`, `build_source_document`, `select_document_text`; `boe_documents.py` | Tests documentales y de compatibilidad del pipeline | Manifest W14 de extracción; hash del XML distinto de la huella BOE/fecha/título/texto preparado |
| 3.5.1 Desarrollo/exposición | `config/evaluation/README.md`; `core_data_freeze_2026-08-13.md`; `HOLDOUT_EXPOSURE_PROVENANCE.md` | — | No nueva selección ni estadística | 140 de desarrollo; 479 registrados como expuestos. Registro existente `config/evaluation/development_used_documents.csv`, sin editar |
| 3.5.2 Producto W14 | Plan ancla, backfill §§2–10, unión W14 y correcciones W14 §§4–9 | `pipeline.py`, `project_history.py` como fuente ya contrastada en la primera fase | Garantías de unión/materialización documentadas, sin ejecutarlas | `runs/final-w14-corpus-20220101-20260820-v1/extraction/manifest.json`; Silver/downstream v2. 48 ancla + 56 históricos = 104; 80 BOE relevantes y 86 proyectos. P2 amplio no se presenta como completado |
| 3.5.3 Holdout | Resultados canónicos §§1–2, contrato de evaluación V2 y cierre TFM | No ejecución | No se reevalúa | Selección congelada de 48 BOE, seis estratos, ocho por estrato; se transcribe del registro canónico. Separado de exposición y W14 |
| 3.6 Transición a metodología | User Guide y guía de calidad | `pipeline.py::run_source_stage`; `extraction/runner.py` | Tests fuente/candidatos/extracción citados arriba | F02 separa recuperación, selección, alcance y extracción; no confirma toda relevancia antes de Gemini |

La tabla 3.1 usa intervalos de búsqueda o referencias de congelación, no fechas
mínimas/máximas observadas inventadas. Sus filas no son sumables salvo ancla e
histórico. No se atribuye al holdout una medida de cobertura del primer filtro.
No se inspeccionaron nuevos BOE ni se realizó investigación web.

## 4. Metodología — 16 secciones redactadas para revisión

Archivo: `chapters/04_metodologia.tex`. Se sigue la secuencia conceptual
solicitada. F03 y F05 se conservan; se incorpora F04; F06 queda preparada
mediante el TODO detallado, sin mezclar sistema actual con POST-TFM.

| Sección | Documentación / declaración | Código principal | Tests / evidencia leída | Manifests / historia |
| --- | --- | --- | --- | --- |
| 4.1 Prototipo a sistema | README; AGENTS; guía de usuario | Paquete `src/`, `pipeline.py` | Markdown e imports de notebooks 01, 03, 07, 10, 11 y 12; no se ejecutan ni leen outputs para nuevos casos | Notebook 07 llama al paquete; otros conservan lógica exploratoria. No se afirma migración completa |
| 4.2 Bronze/Silver/Gold | User Guide §§2–3; contrato Silver; guía Streamlit | `pipeline.py`, `extraction/flat_materialization.py`, `downstream.py`, `gold.py` | Pruebas de materialización, pureza y orden | Manifests de extracción/Silver/downstream W14; determinismo del contenido lógico para entradas fijadas, no de nuevas respuestas o timestamps |
| 4.3 Referencia INE | Informe downstream W14 §3, User Guide | `ine_reference.py` (construcción, validación, identidad, carga), `pipeline.py` (refresh), `downstream.py` | `test_ine_reference.py`: códigos, jerarquía, orden, round trip | `runs/ine-reference-20260614-25a3bbb28f0c21c5/manifest.json`, leído: 8.132 filas, fuentes `codine_ccaaprovincia_20260614.csv` y `diccionario26.csv`. Edición bibliográfica pendiente |
| 4.4 Gemini | Instrucciones vigentes; resultados canónicos §1 | `extraction/config.py`, `documents.py`, `instructions.py`, `models.py`, `agent.py`, `runner.py` | Tests del contrato y la extracción; selección documental examinada en código | Modelo `google:gemini-2.5-flash`, config `4b54b89dbfe8640e`; texto completo salvo regla del anexo de bienes/derechos, con huella propia |
| 4.5 Contratos/validación | Contrato Silver y guía de calidad | `extraction/models.py`, `agent.py`, `runner.py`, `validation.py` | `test_models.py`, `test_validation.py`: enums, referencias y diagnósticos; límites de retries contrastados en config/runner | Pydantic → identidad fuente → canonicalización → validación documental. Figura F04 no invierte controles |
| 4.6 Evidencia/trazabilidad | `AUDITORIA_REVISION_REPORTES.md`; correcciones W14 | `validation.py`, `review.py`, `runner.py` | Tests de literalidad; evidencia real ya comprobada de Don Rodrigo II | Fragmento literal de información pública, sin inventar un BOE; linaje de corrección y Silver preservados |
| 4.7 Canonicalización | Políticas de dominio; resultados canónicos §8 solo para señalar conexión posterior | `canonicalization.py::canonicalize_project_extraction`, `canonicalize_reviewed_project_extraction`, `_repair_action_evidence`, `_canonicalize_actions` | `test_canonicalization.py`, `test_validation.py`: información pública, evidencias, referencias y preservación de semántica humana | No se reduce a formato: puede incorporar/omitir/reorganizar contenido. Precanónico y ajustes conservados; sin nueva ejecución ni métricas |
| 4.8 Silver | `architecture/silver_extraction_contract.md`; correcciones W14 | `flatten.py`, `flat_contract.py`, `flat_validation.py`, `flat_materialization.py` | `test_flat_materialization.py`: tablas vacías, schema, PK/FK, errores sin publicación y round trip; tests de correcciones de auditoría previa | `runs/final-w14-corpus-20220101-20260820-v2/silver/manifest.json`. Documento sin eventos queda fuera de las 13 tablas; evidencias son campos, sidecar no es tabla 14 |
| 4.9 Resolución territorial | Auditoría de revisión; informe downstream | `location_resolution.py`, `ine_reference.py`, `project_grouping.py`, `downstream.py` | `test_location_resolution.py`, `test_project_grouping.py`, `test_ine_reference.py` | Manifest INE y `runs/final-w14-corpus-20220101-20260820-v2/downstream/downstream_manifest.json`; tabla de seis estados, sin cola territorial unificada |
| 4.10 Grouping | PLAN_FIGURAS, downstream W14 §5; correcciones W14 §6 | `project_grouping.py` | `test_project_grouping.py`; traza Don Rodrigo II ya verificada | Gold v2 y clave documentada. Igualdad nominal/tecnología/anclaje; sin municipio, promotor, similitud difusa o confianza. UUID5 estable mientras lo sea la clave |
| 4.11 Revisión/correcciones | `AUDITORIA_REVISION_REPORTES.md`; User Guide §§11–13 | `admin.py`, `review.py`, `corrections.py`, `pipeline.py::run_silver_stage` | Se reutiliza auditoría de los tests de CLI, review y corrections | Cuatro JSON genéricos, 16 exclusiones master y 11 aplicadas W14 comprobados en la auditoría anterior. No se vuelven a contar ni aplicar |
| 4.12 P0 | Guía de calidad; auditoría temporal/correcciones W14 | `historical_antecedents.py`, `historical_antecedent_reviews.py` | Tests de señales, pureza y resolución exacta de la auditoría | CURRENT ≠ exclusión; ANTECEDENT aprobado se aplica después. Ejemplo 2023/2025 explícitamente conceptual, sin métricas P0 |
| 4.13 CLI | README, User Guide, evaluación V2/controlador | `pipeline.py`, `admin.py`, `evaluation/final_holdout_v2/cli.py`, `evaluation/primary_execution/cli.py` | Ayuda Admin comprobada en auditoría; parser y contratos de roles de la documentación | Cuatro responsabilidades; herramientas de evaluación/controlador diferenciadas del sistema productivo congelado |
| 4.14 Pytest | README; User Guide §14; `.github/workflows/tests.yml` | Contratos y transformaciones del paquete | Tests citados por concepto; CI ejecuta extracción, no toda la suite | Se describe evidencia de ingeniería, sin usar cantidad de tests como métrica científica ni afirmar ejecuciones nuevas |
| 4.15 User Guide | `docs/USER_GUIDE.md` | Operaciones referenciadas por la guía | Correspondencia con comandos reales documentados; sin ejecutar operaciones | Guía complementaria versionada; no demuestra por sí sola usabilidad ni disponibilidad del archivo de entrega |
| 4.16 IA de desarrollo | Declaración explícita aportada en la solicitud; AGENTS; resultados canónicos §1 y aprobación humana W14 §1 | Separación Gemini productivo / herramientas de desarrollo | Markdown de notebooks y reglas del proyecto; no se deduce autoría de Git | Manifests truth/evaluador leídos: 13/09/2026 09:57:08 y 14:59:31 UTC; ejecución primaria empieza 15:06:50 UTC. Congelación anterior a predicciones, sin ajuste retrospectivo |

Las rutas de módulos de extracción sin prefijo en esta matriz pertenecen a
`src/renewables_permitting/extraction/`. Las rutas `evaluation/` son relativas a la raíz del repositorio, fuera de
`src/`. Las filas de CLI remiten a sus puntos de entrada; los argumentos completos permanecen en User Guide y anexos.
No se modifica esa guía, AGENTS, código, tests ni configuraciones productivas.

Precisiones frente a historia: el README aún alude a cinco exclusiones en un
párrafo; para el estado final se utiliza el registro y el informe W14 que
acreditan 16 en el master y 11 aplicables al W14. El contrato Silver describe
la proyección relacional base; las exclusiones aprobadas previas al flattening
y el sidecar se contrastan con código final y el informe v2. La memoria no
presenta antiguas propuestas de Silver Curated como una capa implementada.

La declaración de uso de asistentes procede de la solicitud y queda redactada para
revisión humana, sin atribuir a Codex decisiones metodológicas ni autoría. El
registro de freezes corrobora la secuencia de artefactos; no demuestra por sí
solo quién realizó cada interacción o commit. Gemini se explica en 4.4;
ChatGPT, Codex y AGENTS en 4.16. No se necesita investigación web para describir
esa declaración de uso, ni se inventa una referencia bibliográfica del testimonio.

## 5. Aplicación — base sustantiva redactada

Archivo: `chapters/05_aplicacion.tex`. Quedan pendientes capturas y evidencia
de aceptación/entrega pública; no quedan párrafos de funcionalidad en TODO.

| Sección | Documentación | Código / tests de contraste | Evidencia / límites |
| --- | --- | --- | --- |
| 5.1 Objetivo y arquitectura | User Guide §§6–8; STREAMLIT_CODE_GUIDE §§1–2 | `streamlit_app.py`, `app_data.py`; tests del cargador referenciados en guía | Gold v2, cuatro tablas; no Silver, modelo ni pipeline desde interfaz |
| 5.2 Resumen/mapa/catálogo | User Guide §7; FINAL_STREAMLIT_PRODUCT_ALIGNMENT | `app_queries.py` (última decisión/filtros), `app_geometry.py`, `streamlit_app.py`; tests de consultas citados por guía | Misma fila para condiciones administrativas; mapa de ámbitos publicados, universos y ceros. Cartografía local, TODO-CITA de ediciones |
| 5.3 Ficha | User Guide, correcciones W14 §6 | `streamlit_app.py::_render_detail`, consultas de ficha/cronología | Don Rodrigo II ya verificado; cronología observada, sin certificación de estado jurídico |
| 5.4 Metodología/reporting | Auditoría de revisión; User Guide §7 | `_render_methodology`, `_render_report_channel`, `app_reporting.py`; tests mailto/fallback inspeccionados en auditoría previa | Correo externo, sin persistencia, queue o Admin automático; capturas no generadas |

## 6. Metodología experimental — redactada para revisión científica

Archivo: `chapters/06_evaluacion.tex`. Catorce secciones, reorganizadas para
introducir cada concepto antes de sus reglas o métricas. La revisión pedagógica
conserva el contenido científico y las cifras. Las fuentes de
estado final son resultados canónicos y manifests; los runbooks conservan
estados históricos de sus bloques, explícitamente superados por el cierre
de septiembre. No hay discrepancias numéricas o de identidad entre la
solicitud, las tablas canónicas y el resumen inmutable leído.

| Sección | Fuente principal | Respaldo y límite |
| --- | --- | --- |
| 6.1 Objetivo | Contrato V2 §§1, 4, 11; resultados §§1, 10 | Sistema completo congelado: extracción, canonicalización y validación; no atribuir métricas exclusivamente a Gemini ni evaluar Gold/usabilidad |
| 6.2 Desarrollo/holdout | Resultados §2; cierre septiembre; capítulo 3 y sus fuentes verificadas | 140 desarrollo, 479 expuestos, 104 W14, 48 holdout; cero solapamientos documentados. Seis estratos A/B × año, ocho por estrato, semilla 20260821. Sin nueva selección |
| 6.3 Referencia humana | Contrato V2 §§1–6; tabla A de resultados | Definición antes de detalle; alcance V2 remitido a 6.6. 48 documentos, 30 relevantes/18 negativos, 30 eventos, 37 activos, 81 actuaciones = 36 actuales + 45 históricas, 111 localizaciones |
| 6.4 Anotación ciega | Declaración explícita aportada en esta solicitud; contrato V2 §8; manifest truth | Manifest: `predictions_exposed_during_annotation=false`, un `primary_reviewer`. QA asistida realizada después de anotar cada BOE según declaración aportada en la solicitud; no se infiere ejecución de QA a partir del exportador ni acuerdo interanotador |
| 6.5 Freeze truth | Manifest truth leído y SHA físico comprobado | Creación 09:57:08.540285 UTC; identidad/manifest completos abajo. No se lee ni altera el working truth |
| 6.6 Alcance V2 y P0 | Contrato V2 §§1–6 y 11; capítulo 4.11 | Campos primarios fijados antes de predicciones; P0 avisa, no autoexcluye. CURRENT/ANTECEDENT distinguen función temporal en el documento |
| 6.7–6.8 Comparación y jerarquía | Contrato V2 §11; `evaluation/final_holdout_v2/scoring_rules.json`; V2_B_EVALUATOR | Alias exactos con orden, conjuntos completos de eventos, candidatos por evidencia y nombre de localización. Atributos excluidos de las claves; correspondencias forzadas 1:1; current-only, pares, soporte y P0 |
| 6.9 Corrección previa | V2_B_EVALUATOR, “Bounded usage-guard fix”; manifest definitivo | Mínimo de requests solo sobre intentos modelo `ok`. Tests sintéticos `test_requests_guard_preserves_pre_fix_scientific_results` y `test_requests_guard_accepts_preserved_transport_error` leídos; no ejecutados. No se modificaron scoring ni métricas |
| 6.10 Controlador | PRIMARY_EXECUTION_V2, “Durable states”; execution record y provenance | Solo PENDING continúa; terminales preservados, INDETERMINATE bloquea. Tests de interrupción/reanudación leídos. Registro final 48/47/1 y ceros restantes; no se invoca el controlador |
| 6.11 Predicciones | Execution record original; manifest extracción; resumen evaluación | Snapshot generado antes del sello; freeze 15:32:07.325125 UTC. Informe a 15:36:43.131585 UTC. No se confunde fecha de creación del manifest de extracción con freeze de predicciones |
| 6.12 Métricas | Contrato V2 §11, “Metrics”; reglas congeladas; tablas B/C/F | Ejemplo A/B/C frente a A/B/D puramente didáctico. Atributos condicionados, evidencia y P0 después del matching. Agregación micro por tarea; null por denominador cero, F1 cero si P y R definidos y cero. Sin accuracy global |
| 6.13 Secuencia/F07 | Identidades y cronología de artefactos abajo | La referencia y el evaluador entran en scoring offline, nunca en Gemini. Cuatro fases verticales y barrera previa a predicciones |
| 6.14 Reproducibilidad | Resultados §§1, 11; manifests y execution record | Prefijos en tabla del cuerpo, cadenas completas en registro canónico y aquí. Integridad no equivale a corrección ni accesibilidad del archivo de entrega |

Tests pertinentes consultados como respaldo, sin ejecución:
`tests/evaluation/test_scoring_v2b.py` (normalización, conjuntos, atributos,
evidencia, localizaciones); `test_evaluator_v2b.py` (guard y equivalencia
científica sintética); `test_primary_execution.py` (estados e interrupciones).
Los dos últimos nombres son relativos a `tests/evaluation/`.

### Identidades y cronología contrastadas en modo de solo lectura

Rutas desde la raíz. Los SHA siguientes son los hashes físicos de los manifests,
salvo el execution record, que identifica el JSON original.

| Elemento | Artefacto | Identidad completa | SHA-256 del manifest |
| --- | --- | --- | --- |
| Sistema | `tfm-final` | `282de815bea4e248bdcba2c655e3ee078cb58a49` | Commit; no manifest de sistema añadido |
| Truth | `runs/final_holdout_p2_v1_truth_v2_frozen` | `e3f300253db94931345e9bbbc489cd810802f94339c3b6a0d751f98b32383b54` | `4f32dc8f89fff8ae1b80f7fb5f94e9168d131f4dea3d0d025640e869c07c148c` |
| Evaluador | `runs/final_holdout_p2_v1_evaluator_v2_frozen_2c0632b` | `a617ef6155cfcd8c403b0c55542cb753fac22f7893f57f3861af665ae23dda5b` | `f9e33836d1995a70f24094469cb1e39908e3f30874deee11ba175b5255457d1c` |
| Predicciones | `runs/final-holdout-v2-primary-001/primary/extraction` | `154c9b42e840f5d3c8989f8470680d040f40113700f040023ebdbae70e21a500` | `c1464ef49d01f3fe5f7e839fe1af0f00a736d2eba030ebd2871c7760c81c3277` |
| Evaluación | `runs/final-holdout-v2-evaluation-primary-001` | `4686355d47e0e21ad4b88e313e5ddd9561195e6696893945da6610b1f3b371fd` | `1fbd44dea97c03bebb9f34d109862e51e8db181da3ec35b1cf63caadae6e23ae` |

El evaluador pertenece al commit `2c0632b89d59ef3f7e25c24ee61e74ca3ac3c6f1`.
El freeze antiguo es histórico; no se reseña como entrada actual ni se altera.
El registro `runs/final-holdout-v2-primary-001/finalization/execution_record.json`
tiene SHA `8332a7cfe78455daf5983537db851224455cbdd0455360c04677672df4264181`.

Todas las fechas siguientes son del **13/09/2026, UTC**:

| Hito | Hora exacta | Fuente |
| --- | --- | --- |
| Truth congelado | 09:57:08.540285 | `created_at` del manifest truth |
| Evaluador definitivo congelado | 14:59:31.922147 | `created_at_utc` del manifest evaluador |
| Inicio ejecución | 15:06:50.219263 | Execution record |
| Fin ejecución | 15:28:00.612890 | Execution record |
| Freeze de predicciones | 15:32:07.325125 | Execution record |
| Informe de evaluación | 15:36:43.131585 | `created_at_utc` de evaluation_summary |

Las tablas/figuras del PDF abrevían identidades y muestran horas al segundo
o minuto, según su caption. No se recalculan identidades semánticas ni métricas.

## 7. Resultados — primarios y post-hoc separados

Archivo: `chapters/07_resultados.tex`. Secciones 7.1–7.6 primarias;
7.7 “Análisis diagnóstico posterior a la evaluación”. F08 se traslada aquí
desde el TODO de discusión; el capítulo 8 remite a ella sin repetir diagnóstico.

Fuente primaria numérica única:
`docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md` §§2–7, contrastada mediante
lectura de `runs/final-holdout-v2-evaluation-primary-001/evaluation_summary.json`.
No se ejecuta scoring, validadores productivos ni lectura de Parquet para
reconstruir cifras. Redondeo editorial de métricas a tres decimales.

| Sección / cifra | Fuente canónica | Campo o artefacto de origen |
| --- | --- | --- |
| 7.1: 48 documentos, 47 éxitos, 1 error, restantes 0 | Resultados §7 | Execution record y `finalization/provenance.json`; estados finales ya declarados |
| 7.2: 46/48, accuracy 0.9583333333; matriz 30/0/0 y 1/16/1 | Resultados §3, tabla D | Resumen: `metrics.document_scope`; error de scope 13309 y ausencia 32569 identificados por documento canónico |
| 7.3: activos 20/19/17; eventos 13/25/17; actuaciones 1/57/35; localizaciones 43/95/68 | Tabla B | `metrics.entity_detection.<entity>`: TP/FP/FN, precision/recall/F1 leídos, no calculados |
| 7.3: pares 1/59/38; denominadores 60 y 39 | Tabla E | `metrics.action_asset_pairs` |
| 7.3: históricos no extraídos 45 y contaminación emparejada 0 | Resultados §3 | `metrics.entity_detection.administrative_action`; cero no demuestra ausencia semántica en predicciones sin match |
| 7.4: 20/20 generación, 43/43 nivel, tres atributos de actuación 1/1 | Tabla C | `metrics.field_accuracy` |
| 7.4: conjunto exacto 1/1 | Tabla C | `metrics.affected_assets_exact_set`; condicionado, sin sumar pares |
| 7.5: soporte 0/1 y fragmentos del caso 7540 | Resultados §5 | `metrics.action_evidence_support`; cita compuesta transcrita del diagnóstico verificado, con `[...]` |
| 7.6: TP=FP=FN=0; TN=1; no adjudicado=1; omitidos=45; P/R/F1 null; falsos avisos 0/1 | Tabla F | `metrics.p0`; ningún positivo adjudicable |
| Nota de desarrollo: 11/11 y 0/5 | Resultados §6 y referencia al replay W14 | Evidencia previa de desarrollo, sin nueva ejecución ni agregación al holdout |

### Diagnóstico 7.7: transcripción del análisis aprobado

Fuente exclusiva: resultados canónicos §§8–9. No se vuelven a examinar los
BOE ni sus predicciones para producir explicaciones nuevas.

| Subsección | Cifra o caso transferido | Apartado de origen / límite |
| --- | --- | --- |
| 7.7.1 Cascada | Activos 37/39/20; eventos 30/38/13; actuaciones 36 actuales/58/1; siete activos TP bajo eventos sin match | §8 Cascada. Son recuentos primarios, no estimación causal adicional |
| 7.7.2 Actuaciones | FN 18+17=35; FP 37+20=57; ambigüedad 0 | §8 Actions, motivos prioritarios. Sin reasignación ni nuevos matches |
| 7.7.3 Evidencia | 18 títulos exactos y dos otros fragmentos entre 20 sin candidato | §8 Actions; caso 2440. La función congelada `_repair_action_evidence` fue contrastada en la fase metodológica previa; no se puntúa salida alternativa |
| 7.7.4 Activos | 14 descriptores, dos “existente”, uno PFVH/Planta; dos FP adicionales | §8 Assets; Hipódromo 27493 y Envatios XXIV Fase I. Semejanza post-hoc no crea TP |
| 7.7.5 Eventos | 15 FN/20 FP por activos; 2 FN/4 FP por división; 1 FP scope; cero merges observados | §8 Events; caso 11661 con dos activos TP y evento 0/2/1 |
| 7.7.6 Localizaciones | 61 FN/92 FP bajo evento sin match; 7 FN/3 FP dentro de eventos emparejados | §8 Locations. No interpretar toda fila como topónimo inventado |
| 7.7.7 Relaciones | Todos FP/FN bajo actuaciones sin match; exact-set 1/1 | §8 Action → asset. Dependencias no sumables como causas |
| 7.7.8 Error terminal | 32569, document_validation, ocho incidencias, exit 4; dos requests y 50.801 tokens | Resultados §7; exit 4 y estado contrastados en `finalization/provenance.json`. Sin reintento ni uso del payload fallido |
| 7.7.9 Ejemplos | 27493, 11661, 2440 y 7540 | Selección de cuatro patrones del §9; scope/error terminal se mencionan además por ser resultados obligatorios |

El cierre de 7.7 mantiene el diagnóstico separado y prepara su interpretación
en el capítulo 8, sin proponer cambios retrospectivos de contrato.

## 8. Discusión y limitaciones — redactado para revisión

Archivo: `chapters/08_discusion.tex`.
Fuentes: resultados canónicos §§8–10 y Discussion-ready statements;
capítulos 3 y 6 para límites del corpus y del diseño.

La discusión parte de las métricas primarias y utiliza únicamente el
diagnóstico post-hoc aprobado para delimitar interpretaciones. No se vuelven a
analizar predicciones, corregir matches ni calcular resultados. F08 permanece
en 7.7.1 y se interpreta por referencia, sin duplicar la figura.

| Bloque | Fuente y uso | Límite explícito |
| --- | --- | --- |
| 8.1–8.2 Lectura global y alcance | Resultados §§3 y 10; capítulos 3–4 | 46/48 solo mide alcance; sin exactitud global ni cobertura del filtro BOE |
| 8.3 Activos | Diagnóstico §8 Assets | 14 variantes cortas, dos “existente” y un contraste PFVH/Planta; no crea TP post-hoc |
| 8.4 Eventos | Diagnóstico §8 Events y F08 | 15 FN/20 FP asociados a activos; 2 FN/4 FP por splits; 1 FP de alcance; cero merges observados |
| 8.5 Localizaciones | Diagnóstico §8 Locations; metodología territorial 4.9 | 61 FN/92 FP bajo evento sin match; 7 FN/3 FP dentro; no evalúa ubicación física ni perfección territorial |
| 8.6–8.7 Actuaciones y evidencia | Diagnóstico §8 Actions; caso 2440 | 18/37 bajo evento sin match; 17/20 sin candidato; 18 títulos y dos fragmentos; interacción, no causalidad única |
| 8.8–8.9 Atributos y relaciones | Resultados tablas C y E | Denominadores condicionados; 1/1 no es rendimiento general; pares dependen de actuación emparejada |
| 8.10 P0 | Resultados §6 y tabla F | Sin positivos adjudicables; replay 11/11 y 0/5 solo como desarrollo |
| 8.11 Error terminal | Resultados §7 | 32569 se conserva; error de alcance por ausencia, sin errores de entidades |
| 8.12–8.13 Fuentes y mejora | Resultados §§8–10; metodología 4.4–4.7 | Distingue modelo, canonicalización, representación y matching; no reasigna FP/FN |
| 8.14 Limitaciones | Contrato V2, capítulos 2–6 y resultados §10 | Muestra, anotación, alcance, jerarquía, P0, fuente, dominio/modelo y post-hoc restringen las inferencias |
| 8.15 Generalización | Síntesis de alcance validado | Método transferible con adaptación; cifras no extrapolables sin nueva evaluación |

Casos empleados, con una función pedagógica cada uno: Hipódromo para variante
nominal; 11661 para división de evento; 2440 para evidencia/canonicalización;
13309 para alcance incorrecto; y 32569 para error terminal. No se añaden casos,
figuras, correspondencias ni métricas. Dos tablas nuevas resumen fuentes de
discrepancia y limitaciones, sin repetir la tabla de resultados.

## 9. Conclusiones y trabajo futuro — estructura

Archivo: `chapters/09_conclusiones.tex`.
Depende de los objetivos del capítulo 1 y de los capítulos 7–8 revisados.
Fuentes: resultados canónicos, `docs/TFM_CLOSEOUT.md` y
`docs/USER_GUIDE.md`. No incorpora resultados nuevos.

| Sección | Fuente principal | Respuesta y límite |
| --- | --- | --- |
| 9.1 Apertura y aportación | Capítulos 1, 3–5 | BOE no longitudinal; sistema completo desde adquisición hasta consulta, no solo Gemini |
| 9.1.1 Aprendizaje | Resultados primarios y diagnóstico aprobado | Scope 46/48; rendimiento desigual; cascada sin reasignar métricas ni causalidad exclusiva |
| 9.1.2 Utilidad y reproducibilidad | Capítulos 4–6; User Guide | Seguimiento asistido y trazable; no registro oficial, autonomía plena ni cola unificada actual |
| 9.1.3 Objetivos | Objetivo general y seis específicos de 1.3–1.4 | Cumplimiento técnico explícito y matices empíricos; Gold/grouping sin métrica independiente |
| 9.2.1 Calidad | Diagnóstico 7.7 y Discusión | Alias controlados, granularidad, evidencia y actuaciones; ninguna corrección retrospectiva |
| 9.2.2 Evaluación | P0 y limitaciones | Conjunto P0 independiente y nuevos protocolos; el holdout final no se usa para ajuste |
| 9.2.3 Enriquecimiento | Alcance y cierre TFM | `environmental_outcome` derivado, siguiente hito prudente, hibridación, promotor, potencia y componentes |
| 9.2.4 Gobierno | Revisión humana y reporting | Cola persistente futura; una incidencia aceptada produce corrección versionada y regeneración |
| 9.2.5 Operación | CLI y mecanismos existentes; F09 | Scheduler, incrementalidad, publicación y monitorización como propuesta POST-TFM |

La potencia se distingue de la producción energética. El promotor se plantea
como señal futura, no como clave rígida. Las comparaciones de modelos requieren
el mismo protocolo y criterios previos.

## Preliminares y anexos

Dedicatoria: restaurada como TODO antes de la declaración, con el formato
básico original. Agradecimientos: conservados como contenido personal pendiente.
Resumen y Abstract: redactar después de conclusiones. Declaración institucional
y título propuesto: revisión humana. No suprimir secciones por estar vacías.
Anexo A: resultados §§1 y 11; acceso verificable al archivo de entrega aún
pendiente. Anexo B: detalle contractual y glosario estrictamente necesarios.

## Figuras y tablas

Estado heredado del núcleo: F02 (API/corpus) y F04 (extracción/validación) incorporadas
como TikZ. F01, F03 y F05 conservadas sin cambios de fuente. F06 preparada en
4.11; F07/F08 se incorporan en la fase experimental; F09 se incorpora en
9.2.5 como propuesta POST-TFM. Las figuras anteriores se conservan íntegras. No se
crean capturas de Streamlit ni de anotación.

Tablas: corpus revisada editorialmente sin cambiar cifras; capas y CLI
conservadas; familias Silver y estados territoriales incorporadas. La fase experimental incorpora composición V2, estados del controlador,
identidades, matriz scope, métricas, atributos, P0 y diagnóstico de actuaciones. Ubicación y comprobación visual
en `PLAN_FIGURAS.md`.

## Necesidades bibliográficas

No se realizó investigación web ni se inventaron entradas. Se preservan las
cinco entradas de `bib/ref.bib` (cuatro citadas). El RD-ley 23/2020 queda sin
citar hasta justificar su papel. Sus rutas locales de Zotero son metadatos
históricos y no garantizan acceso a las fuentes; no se imprimen como referencias.

Pendiente: transición energética/planificación; legislación consolidada y
preceptos concretos; alcance del BOE y documentación API accesible; extracción
estructurada/LLM y Gemini; Pydantic; resolución de entidades y evaluación
(precision, recall, F1, muestreo); fuentes INE y cartografía IGN/Natural Earth;
Streamlit; declaración metodológica de uso de asistentes. Seleccionar solo
referencias necesarias para las afirmaciones finalmente redactadas.

### TODO-CITA concretos de la fase sustantiva

- 3.1: función institucional y alcance oficial del BOE.
- 3.2: completar URL/fecha de consulta de la referencia API ya existente, formatos y estados.
- 4.3: edición/procedencia de los dos CSV INE efectivamente usados.
- 4.4: LLM, extracción estructurada y documentación pertinente de Gemini 2.5 Flash.
- 4.5: Pydantic y salida estructurada con Pydantic AI.
- 5.1: Streamlit como herramienta de construcción de la aplicación.
- 5.2: ediciones y condiciones de uso de IGN/CNIG y Natural Earth locales.

No se presenta medallion como teoría general ni se atribuyen a bibliografía
externa las decisiones propias de capas o pruebas: no se crea una cita por
cada herramienta o afirmación de implementación. Subsisten los TODO-CITA
jurídicos/contextuales de capítulos 1–2, sin desarrollarlos en esta fase.
Las cinco entradas bibliográficas se conservan; no se hace investigación web.

## Control de calidad de la fase del núcleo metodológico (cerrada)

Se revisaron las seis secciones de datos, las dieciséis de metodología y las
cuatro de aplicación con los siete criterios de la solicitud: concepto antes
del término, finalidad, aplicación concreta, ejemplo cuando ayuda, ausencia
de inventario innecesario de código, respaldo y separación actual/futuro.
Los ejemplos hipotéticos se identifican como tales; Don Rodrigo II reutiliza
la evidencia comprobada, sin introducir documentos del holdout. Las cifras
del corpus proceden de registros canónicos y no son métricas nuevas.

La analogía de materia prima introduce las capas; la huella digital introduce
SHA-256; el tipo de actuación inadmisible ilustra el contrato. Las tablas de
familias Silver y de estados territoriales evitan enumeraciones extensas.
La canonicalización se explica con sus consecuencias semánticas y P0 mantiene
la decisión humana. No se atribuyen funciones futuras a la CLI o al correo.

Aceptación de esta fase: **READY FOR CONTENT REVIEW**. Quedan los siete
TODO-CITA anteriores, F06 y las capturas previstas, además de la revisión
humana. La compilación y la inspección visual se registran en
`PLAN_FIGURAS.md`; no se declara terminada la memoria completa.

## Control científico de la fase experimental

La anotación y la QA efectivas se describen según declaración aportada en la solicitud,
sin inventar identidad de otro revisor o una medida interanotador. Las
declaraciones históricas de “pendiente de freeze” en contratos/runbooks no
se usan como estado actual: el cierre canónico y los artefactos definitivos
documentan la secuencia posterior. Esta diferencia temporal está explícita;
no se detectó discrepancia entre cifras o identidades canónicas.

| Control | Resultado y ubicación vigente |
| --- | --- |
| A Holdout definido antes de usarlo | PASS — 6.2, conjunto reservado y analogía |
| B Ground truth definido antes de usarlo | PASS — 6.3, referencia con la que comparar |
| C Anotación humana ciega inequívoca | PASS — 6.4, anotación personal anterior; QA posterior y decisión humana |
| D V2 fijado antes de predicciones | PASS — 6.3 y 6.6 |
| E Referencia congelada antes de predicciones | PASS — 6.5, 09:57:08 UTC |
| F Evaluador congelado antes de predicciones | PASS — 6.9, 14:59:31 UTC |
| G Corrección anterior a Gemini | PASS — 6.9 frente a inicio 15:06:50 en 6.10 |
| H Predicciones congeladas antes de scoring offline | PASS — 6.11, 15:32:07 frente a 15:36:43 UTC |
| I Matching anterior a atributos condicionados | PASS — 6.7–6.8 antes de 6.12.2 |
| J TP/FP/FN anteriores a precisión/recall/F1 | PASS — 6.12.1, ejemplo → significado → fórmulas |
| K Primario y post-hoc separados | PASS — 7.1–7.6 frente a 7.7, encabezado y salto de página |
| L P0 sin sobreinterpretación | PASS — 6.6.1 y 6.12.4; límites explícitos en 7.6 |
| M Sin exactitud global inventada | PASS — 6.1, 6.12 y capítulo 7 |
| N Voz consistente | PASS — impersonal y primera persona singular para acciones humanas personales |

TODO-CITA nuevos: referencia metodológica sobre holdout y separación de
predicciones (6.2); precisión/recall/F1 y agregación micro (6.12).
Los artefactos propios respaldan las reglas particulares del experimento.
No se realizó investigación web ni se alteró la bibliografía.

Compilación, revisión visual y protección de archivos: `PLAN_FIGURAS.md`.
No se ejecutaron tests de software ni evaluación; las comprobaciones de
esta fase son documentales, de integridad, LaTeX y visuales.

Aceptación tras la revisión pedagógica: **READY FOR PEDAGOGICAL REVIEW**.
Pendientes de este bloque: revisión humana y dos TODO-CITA metodológicos.
La captura C04 sigue siendo opcional y no se ha generado.

## Revisión humana integral — 2026-09-15

Esta sección sustituye, para el estado actual, los inventarios de pendientes
de las fases históricas anteriores. La revisión no altera datos ni resultados.

- Capítulo 1: la motivación del PNIEC procede de la página oficial del MITECO,
  verificada con denominación 2023–2030 y actualización de 25/09/2024.
- Capítulo 2: la figura EIA utiliza exclusivamente los artículos 33 y 45–47
  del texto consolidado de la Ley 21/2013 consultado en el BOE; no incluye EAE.
- Capítulo 3: Parquet se describe con la documentación oficial de Apache. Las
  relaciones 140/479/104/48 proceden de `HOLDOUT_EXPOSURE_PROVENANCE.md`,
  `TFM_CLOSEOUT.md` y los informes W14 ya auditados.
- Capítulo 4: los papeles de Gemini, Pydantic AI y Pydantic se verificaron
  contra `extraction/agent.py`, `config.py` y `models.py`, y se respaldan
  con la documentación oficial de Pydantic AI. F06 se contrasta con la Admin
  CLI, los registros de revisión y el flujo de materialización ya documentado.
- Capítulos 5–9: las capturas siguen como TODO; el controlador se resume sin
  cambiar 47 éxitos/1 error; el caso Hipódromo procede del diagnóstico
  canónico; F09 mantiene cloud como opción POST-TFM sin servicios elegidos.

La ronda bibliográfica de 2026-09-17 resolvió las trece citas que aún estaban
marcadas: normativa de acceso y conexión; preceptos de AAP/AAC/DUP/explotación
y del paralelismo de F01; alcance institucional del BOE; documentación de la
API; edición de los CSV INE; configuración de Gemini 2.5 Flash; arquitectura
Medallion; Streamlit; cartografía IGN/CNIG y Natural Earth; y referencias
metodológicas sobre holdout y métricas. Se conservaron las referencias ya
resueltas de PNIEC, EIA, salida estructurada con Pydantic AI/Pydantic y
Parquet. La referencia institucional duplicada sobre el BOE permanece
consolidada en el capítulo 2.

- **Documentation impact:** capítulos, bibliografía, figuras y documentación
  auxiliar de la memoria.
- **Documents reviewed:** cierre TFM, procedencia de exposición, contratos y
  código de extracción, documentación W14/holdout/resultados y fuentes
  oficiales citadas.
- **Documents updated:** capítulos 1–7 y 9, bibliografía, cinco figuras nuevas,
  cuatro figuras revisadas, configuración de paginación y los cuatro documentos
  auxiliares de redacción.
- **Reason:** segunda versión legible y verificable para lectura humana, con
  progresión conceptual y separación entre sistema, producto y evaluación.
