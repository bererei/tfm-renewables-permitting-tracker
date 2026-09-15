# Figuras y recursos pedagógicos — integración progresiva

Clasificación: **REQUIRED — memoria; experimento y resultados para revisión científica**.
Primera integración: `tfm-evaluation@a7eadca9564df9d982f1145c22b3e39f4c0dc6fd`.
Fase sustantiva anterior: `tfm-evaluation@0387e765e4155f4f67bb9ab6fc8fd58b69927166`.
Fase experimental actual: `tfm-evaluation@d0014a1922e0cf664cfc04491e986b59bf636442`.
El sistema productivo auditado permanece en
`tfm-final@282de815bea4e248bdcba2c655e3ee078cb58a49`.

## Alcance y procedencia

Se utilizan las decisiones revisadas comunicadas en las solicitudes sobre
«Autorización de Proyectos Renovables», «Lógica del grouping», «Pipelines» y
«Proceso diario». No se reproducen sus diagramas antiguos. La implementación
se contrasta con código, tests y artefactos finales; las decisiones revisadas
son la fuente editorial, sin atribuir una nueva lectura literal de los originales.

La primera integración incorporó F01, F03 y F05, sus textos de apoyo y tres tablas.
La fase sustantiva anterior incorporó F02/F04, desarrolló los capítulos 3/4 y la base
del 5 y añadió tablas de familias Silver y estados territoriales. F06 queda
preparada y las capturas continúan en TODO. No modifica código, tests, runs,
resultados, bibliografía o PDF raíz. Los IDs F01–F09 son IDs de planificación;
la numeración visible de LaTeX depende del capítulo y de las figuras incorporadas.
La fase experimental desarrolla 6/7 e incorpora F07/F08. La fase de Discusión
y Limitaciones reutiliza F08 mediante referencia y añade
dos tablas, sin incorporar otra figura. Las cinco figuras anteriores se
conservan sin cambios.

## Selección cerrada para integración progresiva

| ID | Figura / capítulo | Estado | Fuente y correcciones esenciales |
| --- | --- | --- | --- |
| F01 | Procedimiento administrativo / 2.1 | Incorporada; conceptual, TODO-CITA | Decisiones revisadas sobre autorizaciones y contexto del capítulo 2. Vías parcialmente paralelas, DIA condicionante, DUP sin posición fija respecto de AAC; AE provisional/definitiva como contexto |
| F02 | API del BOE y corpus / 3.2 y 3.6 | Incorporada; actual | `boe_source.py`, `boe_documents.py`, `boe_http.py`, `boe_candidates.py`, `pipeline.py::run_source_stage`. Filtrar títulos antes del XML; separar alcance y extracción |
| F03 | Arquitectura general / 4.2 | Incorporada; actual | `pipeline.py`, `ine_reference.py`, `downstream.py`. Panel INE independiente, dos CSV locales, dimensión y manifest/hashes; no descarga automática ni coste cuantificado |
| F04 | Extracción IA y validación / 4.5 | Incorporada; actual | `extraction/documents.py`, `models.py`, `runner.py`, `canonicalization.py`, `validation.py`, `review.py`. Respetar el orden ejecutado: canonicalización antes de la validación documental final; no atribuir las reglas al modelo |
| F05 | Grouping / 4.10 | Incorporada; actual | `project_grouping.py` y `tests/test_project_grouping.py`. Igualdad de clave nominal/tecnológica/territorial; UUID5; sin municipio, promotor, fuzzy matching ni scores |
| F06 | Flujo de revisión y corrección humana implementado / 4.11 | TODO detallado; opción A, solo actual | `AUDITORIA_REVISION_REPORTES.md`, `admin.py`, `extraction/review.py`, P0, correcciones y `run_silver_stage`. Separar decisiones genéricas, CURRENT y ANTECEDENT; regeneración del operador; territorio independiente. Sin reportes ni rama futura |
| F07 | Metodología experimental / 6.13 | Rediseñada; cuatro fases cronológicas | `docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md`, contrato V2 y controlador primario. Sistema/truth/evaluator fijados antes de la ejecución; predicciones congeladas antes de evaluar; post-hoc separado |
| F08 | Cascada de matching / 7.7.1 | Revisada; cadena causal vertical | Resultados canónicos §8. POST-HOC DIAGNOSTIC — NOT PRIMARY SCORING. Padre emparejado necesario pero no suficiente; no crear correspondencias ni métricas |
| F09 | Arquitectura propuesta para una futura operación diaria / 9.2.5 | Incorporada; PROPUESTA POST-TFM | Decisiones revisadas sobre proceso diario, CLI real, `TFM_CLOSEOUT.md` y `USER_GUIDE.md`. Trazo continuo para mecanismos existentes y discontinuo para scheduler, incrementalidad, publicación/monitorización y cola/coordinación propuestas |

Las nueve figuras son REQUIRED en la selección solicitada. La implementación
del sistema descrito en F09 sigue siendo POST-TFM. No se añade otra figura
de referencia INE, otra de capas ni otra sobre evolución del grouping.

## Mensaje, relación con el texto y citas

| ID | Mensaje / texto que complementa | Ejemplo | Referencia necesaria |
| --- | --- | --- | --- |
| F01 | Un proyecto genera publicaciones distintas; sustituye el antiguo TODO genérico del procedimiento | Remisión posterior a Don Rodrigo II, tabla longitudinal existente | TODO-CITA de paralelismo, condicionamiento ambiental, DUP y modalidades de AE |
| F02 | Recuperar, filtrar, decidir alcance y extraer son operaciones distintas; apoya los pasos de 3.2 y el cierre de 3.6 | No necesita otro BOE; los endpoints ya están explicados | API oficial y código de adquisición; no inventar endpoints |
| F03 | Fuente → estructura → consulta; la referencia territorial es una entrada independiente | Analogía breve y tabla de capas, no un segundo flujo idéntico | Código y procedencia/edición INE (TODO-CITA) |
| F04 | Gemini no entrega Silver/Gold directamente; amplía el bloque de controles de F03 | Solo si aclara salida frente a reglas, sin reutilizar resultados como demostración | Modelo, Pydantic (TODO-CITA), runner y contratos |
| F05 | Las menciones con igual clave comparten identidad; sustituye el TODO genérico de agrupación | Don Rodrigo II de 2026 y Bianor separado; límite HSF de 2022 | Código/tests y Silver/Gold final v2 |
| F06 | La incidencia exige decisión trazable antes de regenerar; amplía revisión sin duplicar F04 | CURRENT/ANTECEDENT; no todos los casos modifican contenido | Guía de calidad, CLI admin y correcciones aprobadas |
| F07 | El orden de los freezes protege la separación entre anotación y predicción; apoya 6.13 | No necesita otro caso; cronología documentada | Resultados canónicos y protocolo |
| F08 | Una discrepancia de identidad puede propagarse por la jerarquía; apoya el diagnóstico de 7.7.1 | Conteos ya fijados: activos 37/39/20, eventos 30/38/13, actuaciones 36 actuales/58/1 match actual | Diagnóstico aprobado; no recalcular scoring |
| F09 | Una operación diaria exige coordinación adicional; amplía los TODO de operación y gobierno | No necesita caso real de un servicio inexistente | Propuesta solicitada y límites comprobados del sistema |

## Precisiones de grouping verificadas

La clave es `v1|name:<identidad>|technology:<tipo>|geography:<anclaje>`.
Se eliminan descriptores iniciales de una lista explícita, conservando números
y sufijos. Alias distintos producen una identidad de conjunto, no un grafo de
coincidencias transitivas. El anclaje reúne provincias resueltas del evento;
solo si faltan, utiliza CCAA. Si faltan ambos, conserva `unresolved`.
Ambigüedad/conflicto de provincia o CCAA impide agrupar. La ausencia admisible
no es una garantía general de singleton; en el corpus final sus tres menciones
sí forman tres proyectos individuales. Cambiar la clave puede cambiar el ID.

El ejemplo procede de
`runs/final-w14-corpus-20220101-20260820-v2/{silver,downstream}`:

- `BOE-B-2026-12663` y `BOE-A-2026-17939` comparten
  `v1|name:don rodrigo ii|technology:fotovoltaica|geography:province:41`,
  proyecto `project_a3f24a913ba8501e830acfbb67c18a29`.
- Bianor conserva otra identidad aun compartiendo el anuncio de abril.
- `HSF DON RODRIGO II` de 2022 conserva otra clave y proyecto. Se documenta
  como límite nominal, sin autorizar una fusión ni afirmar una validación
  longitudinal mediante el holdout.

Se verificaron en la auditoría previa seis hashes de los archivos consultados
y el linaje de Silver v2 y Gold. No se regeneraron datos para crear las figuras.

## Tablas y capturas

Incorporadas: siglas administrativas (PACC, EIA, EsIA, DIA, AAP, AAC, DUP, AE),
capas Bronze/Silver/Gold e interfaces CLI. Se conservan la composición del
corpus y el ejemplo longitudinal ya existentes, sin alterar sus cifras.

Incorporadas en la fase sustantiva: familias Silver (4.8) y estados territoriales
(4.9). La tabla del corpus añade la separación finalidad/uso sin cambiar cifras.
Incorporadas ahora: composición V2 (6.3), estados del controlador (6.10),
identidades (6.14), scope (7.2), métricas (7.3), atributos condicionados (7.4),
P0 (7.6) y diagnóstico de actuaciones (7.7.2). Las fórmulas y el ejemplo
didáctico se explican en 6.12 sin otra tabla. Discusión incorpora una tabla de
fuentes de discrepancia (8.12) y otra de limitaciones (8.14), sin repetir las
métricas. F08 se reutiliza mediante referencia desde 8.4; no se añade otra
figura. Referenciar tablas existentes en vez de duplicarlas.

Capturas reservadas, no generadas: C01 vista general, C02 mapa/filtros,
C03 ficha/publicaciones (capítulo 5; seleccionar dos o tres en total) y C04
anotación ciega opcional (6.4). Capturar tras la revisión de publicación;
cada imagen tendrá caption, etiqueta y referencia textual.

## Lenguaje visual y fuentes versionables

- TikZ ya disponible mediante `todonotes` de la plantilla; bibliotecas
  `arrows.meta`, `positioning`, `calc`. No instalar herramientas ni externalizar.
- Estilo común en `include/diagramas.tex`; fuentes en
  `figs/procedimiento_administrativo.tex`, `figs/arquitectura_sistema.tex` y
  `figs/grouping_implementado.tex`; se añaden `figs/api_boe_corpus.tex` y
  `figs/extraccion_validacion.tex` en la fase anterior. Esta fase añade
  `figs/metodologia_experimental.tex` y `figs/cascada_matching.tex`.
  La fase de conclusiones añade `figs/operacion_diaria_futura.tex`.
- Tipografía del documento; nodos de 10 pt y notas de 9 pt, sin reducción global.
  Color `tema`, fondos suaves, bordes y flechas vectoriales.
- F01 usa enlace discontinuo para la relación no secuencial de DUP.
  F09 incorpora una leyenda explícita actual/propuesto y distingue ambos
  estados mediante trazo continuo/discontinuo; el color no es el único medio.
- Las ocho figuras incorporadas tienen caption, etiqueta y referencia desde el texto.
  Se activa el índice de figuras; se conserva el índice de tablas.
- Compilación y PDF intermedio en `build/`, según `COMPILACION.md`.
  El PDF raíz continúa reservado para una actualización de hito aprobada.

## Compilación y revisión de la primera integración de figuras

Resultado de esa revisión: **READY FOR VISUAL REVIEW**. PDF intermedio entonces:
`build/tfm_report_bgd.pdf`, 49 páginas A4. Se ejecutó desde esta carpeta:

```bash
latexmk -synctex=1 -interaction=nonstopmode -halt-on-error -file-line-error tfm_report_bgd.tex
```

Se repitió tras corregir espaciado, alineación de rótulos y saltos de línea
de los TODO; la última invocación termina con exit 0. Log:
`build/compilacion-figuras.txt`. No se compilaron ni ejecutaron componentes
del pipeline o de evaluación.

| Recurso | Número LaTeX | Página impresa | Página del archivo PDF |
| --- | --- | ---: | ---: |
| F01 Procedimiento | Figura 2.1 | 7 | 21 |
| F03 Arquitectura | Figura 4.1 | 17 | 31 |
| F05 Grouping | Figura 4.2 | 19 | 33 |
| Siglas | Tabla 2.1 | 4 | 18 |
| Capas | Tabla 4.1 | 15 | 29 |
| CLI | Tabla 4.2 | 21 | 35 |

Se inspeccionaron renders de las tres figuras y de las tres tablas: cajas,
flechas, texto y captions legibles y dentro de página. El índice contiene
tres figuras y cinco tablas, incluidas las dos tablas previas. No hay
referencias/citas indefinidas, caracteres perdidos ni errores LaTeX. Las
fuentes están embebidas; los diagramas son vectoriales. Subsisten los avisos
previos de ligaduras/hooks, captions de listados no utilizados y dos
desbordamientos conocidos: 67,05614 pt en el logo de la plantilla y
0,30453 pt en la cita legal inicial. No hay nuevos desbordamientos.

La revisión visual humana y la comprobación de los TODO-CITA jurídicos
siguen pendientes; esta entrega no declara cerrada la memoria completa.

## Auditoría posterior de revisión y reportes — 2026-09-14

Resultado: **READY FOR HUMAN REVIEW**, con evidencias y clasificación en
`AUDITORIA_REVISION_REPORTES.md`. Se ajustaron únicamente la revisión y P0
del capítulo 4, la separación territorial de su cola, el reporte del capítulo 5
y la cola unificada propuesta en el capítulo 9. F06 mantiene un TODO detallado
del flujo real; la integración futura se reserva para F09. Los tres diagramas
ya incorporados se conservan sin cambios.

Una invocación del comando de compilación anterior terminó con **exit 0**.
Log: `build/compilacion-revision-reportes.txt`. PDF de aquella auditoría:
`build/tfm_report_bgd.pdf`, **49 páginas A4**. Las referencias nuevas quedan
resueltas en la última pasada; no hay citas indefinidas, caracteres perdidos
ni nuevos desbordamientos. Subsisten los avisos previos enumerados arriba.

| Contenido de esta auditoría | Página impresa | Página del archivo PDF |
| --- | --- | --- |
| 4.6 Estados territoriales y control independiente | 18 y 20 | 32 y 34 |
| 4.7.1 Decisiones y correcciones; TODO de F06 | 20–21 | 34–35 |
| 4.7.2 P0 y ejemplo real | 21 | 35 |
| 5.4 Reporting público | 24 | 38 |
| 9.2.2 Cola unificada POST-TFM | 31–32 | 45–46 |

Se inspeccionaron los renders de las seis páginas con texto modificado:
`build/revision-reportes-p{32,34,35,38,45,46}.png`. No se observaron cortes
ni solapamientos; las referencias muestran sus números. La tabla CLI se
desplaza a la página impresa 22 (PDF 36); las figuras F01/F03/F05 mantienen
sus páginas anteriores. La numeración posterior se actualiza automáticamente.
Las páginas de la primera integración, arriba, se conservan como registro
histórico de esa revisión.

Se comprobó por hashes que los demás archivos versionados, el PDF raíz,
el índice, HEAD y `tfm-final` permanecen idénticos al inicio de la auditoría.
Los cambios de capítulos de esta tarea solo afectan a las secciones indicadas;
el resto del contenido y los apoyos previos se conservan. No se ejecutaron
tests productivos ni regeneración de datos. No hubo staging, commit o push.

## Redacción sustantiva del núcleo — 2026-09-14

Resultado: **READY FOR CONTENT REVIEW**. Se desarrollan las seis secciones
de datos, las dieciséis de metodología y la base de aplicación. La revisión
pedagógica y la trazabilidad por sección constan en `MAPA_FUENTES.md`.
Se incorporan F02/F04 y dos tablas; las fuentes de F01/F03/F05 se conservan.
F06 mantiene el TODO del circuito real. No se generan capturas de aplicación.

PDF intermedio de esta fase: `build/tfm_report_bgd.pdf`, **63 páginas A4**.
La última invocación del comando anterior termina con **exit 0**; se repitió
durante la revisión para corregir un desbordamiento mínimo en P0, precisar
la explicación de filtros y abreviar el título del corpus en el índice.
Log final: `build/compilacion-nucleo.txt`.

| Recurso | Número LaTeX | Página impresa | Página del archivo PDF |
| --- | --- | ---: | ---: |
| F01 Procedimiento, conservada | Figura 2.1 | 7 | 21 |
| Corpus, tabla revisada | Tabla 3.1 | 15 | 29 |
| F02 API y corpus, nueva | Figura 3.1 | 16 | 30 |
| Capas | Tabla 4.1 | 18 | 32 |
| F03 Arquitectura, conservada | Figura 4.1 | 20 | 34 |
| F04 Extracción y validación, nueva | Figura 4.2 | 23 | 37 |
| Familias Silver, nueva | Tabla 4.2 | 26 | 40 |
| Estados territoriales, nueva | Tabla 4.3 | 27 | 41 |
| F05 Grouping, conservada | Figura 4.3 | 29 | 43 |
| Interfaces CLI | Tabla 4.4 | 32 | 46 |

Los índices contienen **cinco figuras y siete tablas**. No hay referencias
o citas indefinidas, caracteres perdidos ni marcadores `??` en el texto
extraído. Se comprobaron acentos y ñ. Las referencias bibliográficas
pendientes siguen explícitas como TODO-CITA, no como entradas inventadas.

Se inspeccionaron individualmente los renders de las páginas PDF
12, 13, 29, 30, 32, 33, 35, 37, 40, 41, 44, 45, 46, 47, 49 y 51, conservados como
`build/nucleo-pN.png`. Las nuevas figuras, las cinco tablas prioritarias,
las notas INE/Gemini, la revisión humana, la declaración de asistentes y la
aplicación son legibles, sin cortes ni solapamientos. Los espacios y saltos
de esta redacción siguen sujetos a la integración futura de F06 y capturas.

No hay nuevos overfull: permanecen los **67,05614 pt** del logo de portada y
los **0,30453 pt** de la cita legal del capítulo 2. Subsisten los avisos de
hooks, ligaduras y captions no utilizados de la plantilla. Hay tres underfull
verticales (páginas impresas 18, 21 y 35) y uno horizontal en la nota INE
(página 19); se inspeccionaron y no provocan pérdida de texto. Son ajustes
de composición no bloqueantes para revisar el contenido.

La comparación por SHA-256 con el estado inicial confirma que los únicos
archivos versionados modificados son los tres capítulos autorizados y cuatro
documentos auxiliares. El PDF raíz, la bibliografía, las tres figuras previas
y todos los demás capítulos se conservan íntegros. El índice Git, HEAD,
`origin/tfm-evaluation` local y `tfm-final` no cambian. No se ejecutaron pruebas
de software, servicios BOE/Gemini ni evaluaciones; se leyeron las pruebas
pertinentes como respaldo y se verificó la memoria mediante LaTeX y revisión
documental/visual. No hubo staging, commit o push. Los resultados de build
permanecen ignorados.

## Impacto documental de la fase sustantiva

- **Documentation impact:** apoyos pedagógicos y redacción acotada de la memoria.
- **Documents reviewed:** cierre TFM, reglas y mapa de fuentes, plantilla,
  compilación, User Guide, contratos, informes W14 y resultados canónicos.
- **Documents updated:** este plan, mapa/reglas de redacción, inventario de
  compilación y fuentes LaTeX afectadas. El manual operativo no cambia.
- **Reason:** explicar el núcleo implementado de forma progresiva, mantener
  trazabilidad por sección y verificar sus apoyos sin alterar el sistema
  congelado, las operaciones documentadas ni los resultados experimentales.

## Metodología experimental y resultados — 2026-09-14

Resultado de esta fase: **READY FOR SCIENTIFIC REVIEW**.
La rama inicial fue `tfm-evaluation@d0014a1922e0cf664cfc04491e986b59bf636442`,
con árbol limpio y referencia local origin coincidente. Se desarrollan los
capítulos 6 y 7; el 8 solo sustituye el antiguo TODO de diagnóstico/F08
por una conexión para discutir lo ya presentado. No se cierran Discusión,
Limitaciones, Conclusiones, Resumen o Abstract.

La última compilación, desde `docs/tfm_report/`, termina con **exit 0**:

```bash
latexmk -synctex=1 -interaction=nonstopmode -halt-on-error -file-line-error tfm_report_bgd.tex
```

PDF actual: `build/tfm_report_bgd.pdf`, **79 páginas A4**.
Log: `build/compilacion-experimento.txt`. Se repitió durante la revisión
para corregir los solapamientos iniciales de F07, despejar flechas de F08,
ajustar cabeceras y eliminar tres desbordamientos nuevos. Una separación
de página vacía los floats primarios antes de abrir el post-hoc; así ninguna
tabla primaria aparece después de su encabezado diagnóstico.

| Recurso | Número | Página impresa | Página PDF |
| --- | --- | ---: | ---: |
| Composición V2 | Tabla 6.1 | 40 | 54 |
| Estados del controlador | Tabla 6.2 | 44 | 58 |
| F07 Metodología experimental | Figura 6.1 | 45 | 59 |
| Identidades del experimento | Tabla 6.3 | 47 | 61 |
| Alcance documental | Tabla 7.1 | 49 | 63 |
| Métricas de entidades/relaciones | Tabla 7.2 | 49 | 63 |
| Atributos condicionados | Tabla 7.3 | 50 | 64 |
| P0 | Tabla 7.4 | 51 | 65 |
| Diagnóstico de actuaciones | Tabla 7.5 | 53 | 67 |
| F08 Cascada de matching | Figura 7.1 | 54 | 68 |

Se revisaron individualmente los renders de las tablas y figuras indicadas,
más las fórmulas (PDF 60), evidencia/P0 (65) y apertura post-hoc (67).
Las imágenes locales de revisión se conservan como `build/experimento-pN.png`.
No son capturas de Streamlit ni fuentes versionables.
Las columnas caben sin reducción global; los avisos N=1 y P0 sin sensibilidad
van en el mismo float que sus tablas. F07 dirige truth y evaluador solo a la
evaluación offline; F08 conserva rótulo post-hoc y flechas legibles.

Los índices contienen **siete figuras y quince tablas**; etiquetas y
referencias están resueltas, sin citas indefinidas, caracteres perdidos o
marcadores `??`. Se conservan como TODO-CITA las fuentes externas pendientes.
Las fórmulas, acentos y caracteres españoles se inspeccionaron en el PDF.

No hay nuevos overfull. Se mantienen los previos de portada (67,05614 pt)
y cita legal del capítulo 2 (0,30453 pt), además de avisos de hooks,
ligaduras y captions de la plantilla. Los underfull previos corresponden a
las páginas impresas 18, 19, 21 y 35. El nuevo underfull vertical de página
50 (badness 6995) produce espaciado amplio, sin pérdida ni solapamiento:
se considera no bloqueante para revisar el contenido científico.

La comparación de las cinco filas de métricas contra valores ya presentes
en `evaluation_summary.json` verifica transcripción y redondeo; no ejecuta
fórmulas de scoring ni reconstruye resultados. La revisión científica A–K y
la procedencia de cada cifra, incluidas las categorías post-hoc, constan en
`MAPA_FUENTES.md`.

Protección comprobada antes de la revisión de voz narrativa: SHA-256 de los
**305 archivos versionados fuera de los seis
editados** sin cambios, incluido el PDF raíz, los capítulos 1–5 y 9,
anexos, bibliografía y las cinco figuras previas. Manifests de truth,
evaluador, predicciones y evaluación, resumen y execution record idénticos
a los leídos al inicio. Staging, HEAD, origin local y tfm-final intactos.
No se modificaron código, tests, datos ni runs; no se ejecutaron Gemini,
evaluación o pruebas de software. Los outputs de build permanecen ignorados.
No hubo commit ni push.

### Impacto documental de esta fase

- **Documentation impact:** metodología experimental y presentación científica.
- **Documents reviewed:** cierre TFM, resultados canónicos, contrato V2,
  runbooks V2-B y controlador, mapa/plan de memoria, reglas congeladas,
  tests pertinentes y manifests/registro de ejecución.
- **Documents updated:** capítulos 6/7, conexión/TODO del 8, mapa de fuentes,
  este plan e inventario de fuentes de `COMPILACION.md`; dos nuevos TikZ.
- **Reason:** explicar y hacer revisables el diseño, los denominadores y el
  diagnóstico aprobado conservando las fronteras del experimento.
  El User Guide y los documentos experimentales canónicos no requieren cambios.

Siguiente bloque, solo tras revisión humana y commit/push manual:
Discusión → Limitaciones → Conclusiones → Resumen/Abstract →
revisión bibliográfica/TODO-CITA → revisión visual final.


## Cierre de revisión de voz narrativa — 2026-09-14

Bloque REQUIRED exclusivamente estilístico, posterior a la verificación
experimental anterior. Norma: voz académica impersonal y primera persona
singular limitada a acciones personales que acreditan intervención humana.
Se ajustaron 4.16, 6.4, 6.10, el TODO de 8.3, el rótulo de anotación de F07,
los TODO preliminares y un comentario de opciones. La regla queda fijada en
`REGLAS_REDACCION.md`; el mapa y este plan usan formulaciones neutrales.

La búsqueda final abarcó todos los capítulos, incluidos los ejemplos históricos,
el archivo principal, figuras, preliminares y documentación de redacción.
No quedan referencias personales en tercera persona ni plural colectivo en
la narración de los capítulos. Se conserva la declaración institucional en
primera persona (`elements/preambulo.tex:12`) y cinco menciones en el registro
histórico `REVISION_FASE_1.md` (líneas 11, 23, 34, 278 y 397): documentan
revisiones anteriores y no establecen el estilo de la memoria. El rol genérico
de revisión de correcciones de 4.11, los rótulos de portada y las referencias
a terceros tampoco son referencias narrativas personales.

Comando desde `docs/tfm_report/`:

```bash
latexmk -synctex=1 -interaction=nonstopmode -halt-on-error -file-line-error tfm_report_bgd.tex
```

Resultado: exit 0, 79 páginas A4; log local `build/compilacion-voz.txt`.
Sin referencias o citas indefinidas ni marcadores `??`. Se mantienen los
avisos previos descritos arriba; la revisión de voz no añade overfull.
Inspección visual del PDF: páginas físicas 5 y 8 (preliminares), 12 (índice),
47 (IA de desarrollo), 54 (anotación/QA), 58 (límites y secuencia),
59 (F07) y 72 (TODO de discusión). Sin nuevas pérdidas ni solapamientos.
Renders de revisión ignorados: `build/voz-pN.png`. La paginación de las
figuras y tablas del registro experimental anterior se conserva.

Protección frente al inicio de esta revisión: todos los tokens numéricos,
etiquetas, referencias, citas y bloques tabulares/ecuaciones LaTeX idénticos.
Capítulo 7, figura F08 y archivo principal idénticos byte a byte. El diff de
voz fue revisado frase a frase; no altera cronología, freezes, reglas V2-B,
denominadores, arquitectura o interpretación post-hoc. Frente al inicio del
bloque experimental, los 301 archivos versionados fuera de los diez editados
conservan SHA-256, incluido el PDF raíz. Los seis artefactos experimentales
comprobados también conservan SHA-256. Índice Git y referencias intactos.
No se ejecutaron pruebas de software, evaluación ni llamadas a modelos.

- **Documentation impact:** voz narrativa y reglas de redacción.
- **Documents reviewed:** cierre TFM, todos los capítulos, archivo principal,
  preliminares, figuras y documentación auxiliar de memoria.
- **Documents updated:** capítulos 4/6/8, F07, preliminares, comentario de
  opciones, reglas de redacción, mapa de fuentes y este registro.
- **Reason:** explicitar las acciones humanas personales y evitar la tercera
  persona en la narración, conservando el contenido científico. Sin impacto
  en User Guide, código, tests, datos, resultados canónicos ni runs.

Aceptación: **READY FOR VOICE REVIEW**. Se detiene el bloque para revisión
humana; no se hace staging, commit ni push.

## Discusión y limitaciones — 2026-09-14

Estado vigente: **READY FOR DISCUSSION REVIEW**. El capítulo 8 ocupa las
páginas impresas 60–69 (PDF 74–83). Reutiliza F08 por referencia; no añade
figuras. La tabla 8.1, fuentes de discrepancia, aparece en la página impresa
65 (PDF 79); la tabla 8.2, limitaciones, en la 67 (PDF 81). No repiten métricas.

Se inspeccionaron visualmente las diez páginas del capítulo. Las dos tablas
caben sin reducción global ni solapamientos. La distinción sistema/Gemini,
el denominador 1/1, P0 sin positivos adjudicables, el error terminal y la
frontera primario/post-hoc permanecen explícitos. No hay nuevas figuras,
capturas o TODO-CITA. La política y el inventario de `COMPILACION.md` no
requieren cambios en este bloque.

Compilación habitual: exit 0, 89 páginas A4. F07 permanece en PDF 62 y F08
en PDF 70. Se conservan los dos overfull históricos y los cuatro underfull
previos; no aparecen referencias indefinidas, caracteres perdidos ni avisos
nuevos de cajas. Log local: `build/compilacion-discusion.txt`.
