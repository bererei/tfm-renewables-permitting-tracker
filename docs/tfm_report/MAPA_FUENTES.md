# Mapa de fuentes y plan de redacción

Fecha: 2026-09-14. Clasificación: **REQUIRED — memoria escrita, fase 1**.
Documento de trabajo para revisión; no se incorpora al PDF.
Reglas pedagógicas vigentes: [REGLAS_REDACCION.md](REGLAS_REDACCION.md).
Corrección del 14/09: se conserva la dedicatoria y se desarrolla el acceso
programático en 2.2 y 3.1, conectado con candidatos/relevancia en 3.3.
Las rutas indicadas son relativas a la raíz del repositorio.

## Regla de uso

El estado vigente procede de `docs/TFM_CLOSEOUT.md`, checkpoint de septiembre.
Las cifras experimentales proceden exclusivamente de
`docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md`. Los contratos fijan las reglas;
los informes históricos explican decisiones en su fecha. No se recalculan
métricas ni se convierten diagnósticos posteriores en puntuación primaria.

Sistema evaluado: `tfm-final@282de815bea4e248bdcba2c655e3ee078cb58a49`.
La rama de redacción es `tfm-evaluation`; inspección inicial en
`8e85ea58340deb929e95ebab80693a1e5d473864`, con árbol limpio.
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
  de sumarios y XML de candidatos; detalle aplicado en 3.1. Confirmación en
  `boe_source.py`, `boe_documents.py` y `pipeline.py::run_source_stage`.
- Tabla 2.1: dos publicaciones de Don Rodrigo II, derivada exclusivamente
  de la traza de la auditoría temporal y su corrección aprobada.
- TODO-CITA: acceso y conexión; artículos/versiones aplicables a información
  pública, estudio/DIA/informe, AAP/AAC/DUP/explotación; alcance institucional
  del BOE. Revisar fecha de la entrada del RD 1955/2000 (actualmente 2001).
- No se inventa una secuencia legal universal ni se deriva estado operativo
  de una autorización previa o de construcción.

## 3. Datos y corpus — primer borrador redactado

Archivo: `chapters/03_datos.tex`.

| Afirmación o sección | Fuente principal y confirmación acotada |
| --- | --- |
| API, adquisición y Bronze conceptual (3.1) | `docs/USER_GUIDE.md` §§2–3 y 5; `boe_source.py`, `boe_documents.py`, `boe_http.py`, `pipeline.py::run_source_stage`; lectura de tests fuente/documentos y ayuda CLI de la primera fase |
| Identidad documental | `docs/USER_GUIDE.md` §3; `extraction/documents.py`; `docs/FINAL_CORPUS_INGESTION_AUDIT.md` como historia, no descripción actual de retries |
| Títulos y candidatos | `boe_candidates.py::select_energy_candidates`, `TITLE_KEYWORDS`; `tests/test_boe_candidates.py` confirma título como único campo seleccionador |
| Reglas de alcance | `docs/FINAL_CORPUS_CANDIDATE_FUNNEL_AUDIT.md`, decisión de periodo/funnel y preflight P2 como evolución; comportamiento actual confirmado en `extraction/canonicalization.py::_scope_guard_from_document` y configuración v4 |
| Piloto y challenge | `config/evaluation/README.md`, `docs/freezes/core_data_freeze_2026-08-13.md` |
| Exclusión de exposición | `docs/HOLDOUT_EXPOSURE_PROVENANCE.md`; registro versionado `config/evaluation/development_used_documents.csv` localizado, sin alterarlo |
| W14 | `docs/FINAL_CORPUS_W14_ANCHOR_PILOT_PLAN.md` §1; `docs/FINAL_CORPUS_W14_EXTRACTION_UNION.md` §15 |
| Histórico conservador | `docs/FINAL_CORPUS_W14_BACKFILL_IMPLEMENTATION.md` §§2–10: antes de 2024, fuente canónica; desde 2024, scopes P2; Tier 3 excluido |
| Cifras finales del producto | `docs/TFM_CLOSEOUT.md`; `docs/FINAL_W14_ADMIN_ACTION_CORRECTIONS.md` §9: 104 analizados, 80 relevantes, 86 proyectos |
| Holdout | resultados canónicos §§1–2, checkpoint de cierre, `docs/FINAL_EXTRACTION_PREFLIGHT_P2.md`, contrato V2 |

La tabla 3.1 transcribe tamaños verificados documentalmente. Distingue
intervalos de búsqueda de extremos observados y conjuntos no sumables.
No recalcula selecciones, exposición ni estadísticas. No se atribuye al holdout
una estimación de cobertura del primer filtro o del censo completo del BOE.

Antes de cerrar el capítulo: revisar con la autora si necesita más detalle del
cambio P2 → W14. No ampliar por defecto la tabla con recuentos intermedios.
No hay nuevas referencias bibliográficas externas para las cifras propias;
la referencia API está introducida en el capítulo 2.

### Detalle verificado del acceso programático — corrección 2026-09-14

Todos los módulos siguientes están en `src/renewables_permitting/`.
La inspección ha sido de lectura, sin peticiones de red ni ejecución del pipeline.

| Explicación incorporada | Evidencia de implementación |
| --- | --- |
| Intervalo inclusivo y solicitudes secuenciales | `boe_source.py::inclusive_date_range`, `fetch_boe_summaries` |
| GET diario a `https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD`, JSON | `BOE_SUMMARY_BASE_URL`, `_summary_url`, `fetch_boe_summary`, cabecera `Accept: application/json` |
| Metadatos y control de duplicados | `BOE_ITEM_COLUMNS`, `parse_boe_summary`; `run_source_stage` comprueba además duplicados entre fechas |
| Filtro antes del XML | `run_source_stage`: `select_energy_candidates(items)` precede a las llamadas `fetch_boe_document_xml` |
| XML obtenido mediante el enlace del sumario | `run_source_stage` pasa `row.url_xml` como `source_url`; `fetch_boe_document_xml` realiza GET sobre él |
| Preparación de texto, no OCR de PDF | `parse_boe_document_xml`, `_canonical_xml_text`: recorrido de la raíz XML, normalización de espacios, separación de bloques y celdas |
| Identidad compatible con candidato | `build_extractor_document_input`: exige coincidencia de ID y fecha, no de título; conserva el título del sumario. `_source_document_hash` en `extraction/documents.py` incorpora título y texto de la entrada |
| Estados del sumario | `fetch_boe_summary`: success, no_publication, failed; 404 HTTP o BOE → no_publication |
| Estados XML | `fetch_boe_document_xml`: enlace ausente, error de petición/HTTP, respuesta vacía o XML inválido; 404 → http_error |
| Reintentos acotados | `boe_http.py`: una petición y hasta tres reintentos, esperas 1/2/4 s; HTTP 408/429/500/502/503/504 y excepciones transitorias definidas; timeout por defecto 30 s en ambos módulos |
| Persistencia y publicación | `materialize_boe_summary`, `materialize_boe_document_xml`, `run_source_stage`: sumarios/XML/metadatos/tablas y manifest en directorio temporal; destino nuevo |
| Ausencia de caché/resume en adquisición | `run_source_stage` obtiene sumarios/XML antes del staging; `source` no tiene opciones de caché/reanudación. Los resultados fallidos de descarga no se publican como snapshot parcial |
| Clasificación posterior al primer filtro | `extraction/canonicalization.py::preclassify_document_without_model`, `_scope_guard_from_document`; los casos sin decisión determinista requieren modelo/validación |

Tests leídos como garantías existentes: `tests/test_boe_source.py` y
`tests/test_boe_documents.py`; también se localizaron controles en
`tests/test_pipeline.py`. No se ejecutaron ni modificaron tests.
La auditoría histórica que decía «sin retry» no describe el código actual;
la ausencia de reanudación/caché es una limitación distinta.

## 4. Metodología y arquitectura — estructura, sin redacción definitiva

Archivo: `chapters/04_metodologia.tex`.

| Sección | Fuentes para la siguiente fase |
| --- | --- |
| 4.1 Exploración y migración | `README.md`; markdown e imports de notebooks 01, 03, 07, 10, 11 y 12; `src/renewables_permitting/pipeline.py`. No afirmar migración completa de todos los notebooks |
| 4.2 Capas | `docs/USER_GUIDE.md` §§2–3; `docs/architecture/silver_extraction_contract.md`; `extraction/flat_contract.py`; `gold.py` |
| 4.3 Gemini | `extraction/config.py`, `documents.py`, `models.py`, `instructions.py`; resultados §1 para modelo/configuración congelados |
| 4.4 Contratos y reglas | contrato Silver; `extraction/models.py`, `validation.py`, `canonicalization.py`, `flat_validation.py`; tests focales de extracción |
| 4.5 Agrupación | downstream W14 §5; `project_grouping.py`; `tests/test_project_grouping.py`; traza Don Rodrigo II |
| 4.6 Territorio | downstream W14 §§3–4; `ine_reference.py`, `location_resolution.py`, `project_locations.py`; tests territoriales; fuentes INE locales |
| 4.7 Revisión y P0 | `docs/architecture/extraction_quality_review.md`; auditoría temporal y correcciones W14; `extraction/historical_antecedents.py`, `corrections.py`; registros versionados de revisión |
| 4.8 CLI, pruebas e IA de apoyo | `README.md`, guía de usuario, `AGENTS.md`, `.github/workflows/tests.yml`; declaración de uso aportada por la autora; correcciones W14 §1 para separar aprobación humana e implementación |

Distinguir P0 (advertencia no destructiva) de corrección y de recuperación
retrospectiva. Para el estado final de Gold, complementar el informe downstream
v1 con el informe de correcciones v2; no mezclar identidades ni cardinalidades.

La declaración de uso de ChatGPT/Codex procede de la petición de la autora.
Git no acredita por sí solo quién redactó, revisó o ejecutó manualmente cada
commit. Su aprobación de esta sección es necesaria antes de presentarla como
declaración final. Gemini se explica en 4.3; asistentes de desarrollo en 4.8.2.

## 5. Aplicación — estructura

Archivo: `chapters/05_aplicacion.tex`.
Fuentes: `docs/STREAMLIT_CODE_GUIDE.md`, `docs/USER_GUIDE.md` §§6–8,
`docs/FINAL_STREAMLIT_PRODUCT_ALIGNMENT.md`, `docs/APP_PRODUCT_SPEC.md`.

Describir Gold-only, consultas, mapa administrativo local sin tiles externos,
catálogo/filtros, ficha, cronología, metodología y correo sin persistencia.
No confundir con la app de anotación ni afirmar una validación de usabilidad.
Dependencias: capturas y evidencia de la revisión visual/entrega pública real.
No se modifica ni se ejecuta Streamlit en esta fase de redacción.

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

Prioridad REQUIRED, para fases posteriores:

1. Procedimiento administrativo simplificado (cap. 2), tras verificación legal.
2. Arquitectura global con Bronze → Silver → Gold y rama experimental (cap. 4).
   Reutilizar conceptualmente Mermaid de `docs/USER_GUIDE.md` §2; puede integrar
   la figura de capas para evitar repetición.
3. Extracción, validación y revisión (cap. 4); fuente: contrato y guía de calidad.
4. Selección, anotación y freezes del holdout (cap. 6).
5. Cascada de matching (cap. 8), solo con el diagnóstico aprobado.
6. Capturas revisadas de resumen y ficha (cap. 5).

En `docs/tfm_report/figs/` solo se localizaron logos institucionales y la imagen
ESIIAB de ejemplo; no hay allí diagramas técnicos ni capturas del producto.
Los diagramas Mermaid documentales son esquemas, no figuras terminadas de tesis.
No se genera ninguna figura en esta fase.

Tabla de corpus y tabla de seguimiento de Don Rodrigo II: incluidas.
El plan de las ocho clases de diagramas, los mensajes y las capturas está en
`REGLAS_REDACCION.md`; se añaden adquisición y agrupación explícitas.
Tabla de corpus: conservada sin cambiar cifras. Pendientes: entidades/contrato resumido (cap. 4),
composición del holdout y tablas primarias A–F. Evitar duplicar cuadros si una
referencia entre capítulos basta. Los casos detallados pueden ir al anexo B.

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
