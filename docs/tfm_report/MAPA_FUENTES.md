# Mapa de fuentes y plan de redacción

Fecha: 2026-09-14. Clasificación: **REQUIRED — redacción sustantiva del núcleo metodológico**.
Documento de trabajo para revisión; no se incorpora al PDF.
Reglas pedagógicas vigentes: [REGLAS_REDACCION.md](REGLAS_REDACCION.md).
Corrección del 14/09: se conserva la dedicatoria y se desarrolla el acceso
programático en 2.2; la fase sustantiva lo desarrolla en 3.2, conectado con
candidatos/relevancia en 3.3 y con el cierre conceptual de 3.6.
Las rutas indicadas son relativas a la raíz del repositorio.

## Regla de uso

El estado vigente procede de `docs/TFM_CLOSEOUT.md`, checkpoint de septiembre.
Las cifras experimentales proceden exclusivamente de
`docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md`. Los contratos fijan las reglas;
los informes históricos explican decisiones en su fecha. No se recalculan
métricas ni se convierten diagnósticos posteriores en puntuación primaria.

Sistema evaluado: `tfm-final@282de815bea4e248bdcba2c655e3ee078cb58a49`.
La rama de redacción es `tfm-evaluation`. La primera fase partió de
`8e85ea58340deb929e95ebab80693a1e5d473864`. Esta redacción sustantiva parte de
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
| 4.16 IA de desarrollo | Declaración explícita de la autora en la solicitud; AGENTS; resultados canónicos §1 y aprobación humana W14 §1 | Separación Gemini productivo / herramientas de desarrollo | Markdown de notebooks y reglas del proyecto; no se deduce autoría de Git | Manifests truth/evaluador leídos: 13/09/2026 09:57:08 y 14:59:31 UTC; ejecución primaria empieza 15:06:50 UTC. Congelación anterior a predicciones, sin ajuste retrospectivo |

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

La declaración de uso de asistentes procede de la autora y queda redactada para
su revisión, sin atribuir a Codex decisiones metodológicas ni autoría. El
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

## 6. Metodología experimental — estructura

Archivo: `chapters/06_evaluacion.tex`.
Fuentes: contrato V2 §§3–12, `evaluation/final_holdout_v2/scoring_rules.json`,
`docs/evaluation/V2_B_EVALUATOR.md`, `docs/evaluation/PRIMARY_EXECUTION_V2.md`,
resultados canónicos §§1–2, 5–7, 10–11 y `docs/TFM_CLOSEOUT.md`.

Orden de explicación: conjunto independiente → referencia humana/ground truth
→ anotación ciega → freezes → emparejamiento jerárquico → temporalidad/P0
→ métricas → reproducibilidad. Ejemplo numérico didáctico separado del experimento.
Mantener semántica current-only, reglas de evidencia, atribución y denominadores.

Dependencia documental: precisar el QA realmente efectuado y la procedencia de
anotación. No afirmar interanotador formal, independencia de una segunda persona
o exhaustividad semántica por integridad de archivos. El evaluador definitivo
es `…_frozen_2c0632b`, no el primer freeze histórico. No se ejecuta nada.

## 7. Resultados — estructura

Archivo: `chapters/07_resultados.tex`.
Única fuente: `docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md`.
Orden: tabla A y estados operativos → scope/matriz D → activos, eventos,
actuaciones, localizaciones (B) → atributos (C) → actuación/activo (E)
→ evidencia y P0 (F). Copiar bloques LaTeX A–F con denominadores y redondeo
ya documentado. **PRIMARY RESULTS**. No trasladar porcentajes 1/1 como
rendimiento general ni sustituir null por cero.

## 8. Discusión y limitaciones — estructura

Archivo: `chapters/08_discusion.tex`.
Fuentes: resultados canónicos §§8–10 y Discussion-ready statements;
capítulos 3 y 6 para límites del corpus y del diseño.

Primero interpretar resultados primarios; después presentar
**POST-HOC DIAGNOSTIC — NOT PRIMARY SCORING** como sección separada.
La cascada jerárquica, alias, splits, evidence/canonicalization y ejemplos
proceden del diagnóstico aprobado. No volver a analizar predicciones ni
corregir matches. Separar error del modelo, procesamiento determinista,
regla de matching y representación; no inferir causas que no se aislaron.

## 9. Conclusiones y trabajo futuro — estructura

Archivo: `chapters/09_conclusiones.tex`.
Depende de objetivos aceptados y capítulos 7–8 revisados.
Fuentes: resultados canónicos, `docs/TFM_CLOSEOUT.md` §§4–5,
`docs/USER_GUIDE.md` §16. Responder a objetivos sin nuevas métricas.
Futuro agrupado en operación, calidad/gobierno y enriquecimiento funcional;
no confundir potencia con producción ni proponer tuning del holdout cerrado.

## Preliminares y anexos

Dedicatoria: restaurada como TODO antes de la declaración, con el formato
básico original. Agradecimientos: conservados como contenido personal pendiente.
Resumen y Abstract: redactar después de conclusiones. Declaración institucional
y título propuesto: revisión de la autora. No suprimir secciones por estar vacías.
Anexo A: resultados §§1 y 11; acceso verificable al archivo de entrega aún
pendiente. Anexo B: detalle contractual y glosario estrictamente necesarios.

## Figuras y tablas

Estado de esta fase: F02 (API/corpus) y F04 (extracción/validación) incorporadas
como TikZ. F01, F03 y F05 conservadas sin cambios de fuente. F06 preparada en
4.11; F07/F08/F09 siguen pendientes para sus fases correspondientes. No se
crean capturas de Streamlit ni de anotación.

Tablas: corpus revisada editorialmente sin cambiar cifras; capas y CLI
conservadas; familias Silver y estados territoriales incorporadas. No se
incorporan aún tablas experimentales nuevas. Ubicación y comprobación visual
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

## Control de calidad de esta fase

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
TODO-CITA anteriores, F06 y las capturas previstas, además de la revisión de
la autora. La compilación y la inspección visual se registran en
`PLAN_FIGURAS.md`; no se declara terminada la memoria completa.
