# Figuras y recursos pedagógicos — primera integración

Clasificación: **REQUIRED — memoria; pendiente de revisión visual humana**.
Base de contraste: `tfm-evaluation@a7eadca9564df9d982f1145c22b3e39f4c0dc6fd`.
El sistema productivo auditado permanece en
`tfm-final@282de815bea4e248bdcba2c655e3ee078cb58a49`.

## Alcance y procedencia

Se utilizan las decisiones revisadas comunicadas por la autora sobre
«Autorización de Proyectos Renovables», «Lógica del grouping», «Pipelines» y
«Proceso diario». No se reproducen sus diagramas antiguos. La implementación
se contrasta con código, tests y artefactos finales; las decisiones revisadas
son la fuente editorial, sin atribuir una nueva lectura literal de los originales.

Esta integración incorpora F01, F03 y F05, sus textos de apoyo y tres tablas.
Desarrolla CLI/User Guide y reserva las restantes figuras y capturas mediante
TODO. No completa todos los capítulos ni modifica código, tests, runs,
resultados, bibliografía o PDF raíz. Los IDs F01–F09 son IDs de planificación;
la numeración visible de LaTeX depende del capítulo y de las figuras incorporadas.

## Selección cerrada para integración progresiva

| ID | Figura / capítulo | Estado | Fuente y correcciones esenciales |
| --- | --- | --- | --- |
| F01 | Procedimiento administrativo / 2.1 | Incorporada; conceptual, TODO-CITA | Decisiones revisadas sobre autorizaciones y contexto del capítulo 2. Vías parcialmente paralelas, DIA condicionante, DUP sin posición fija respecto de AAC; AE provisional/definitiva como contexto |
| F02 | API del BOE y corpus / 3.1 | TODO detallado; actual | `boe_source.py`, `boe_documents.py`, `boe_http.py`, `boe_candidates.py`, `pipeline.py::run_source_stage`. Filtrar títulos antes del XML; separar alcance y extracción |
| F03 | Arquitectura general / 4.2 | Incorporada; actual | `pipeline.py`, `ine_reference.py`, `downstream.py`. Panel INE independiente, dos CSV locales, dimensión y manifest/hashes; no descarga automática ni coste cuantificado |
| F04 | Extracción IA y validación / 4.4 | TODO detallado; actual | `extraction/documents.py`, `models.py`, `runner.py`, `canonicalization.py`, `validation.py`, `review.py`. Respetar el orden ejecutado: canonicalización antes de la validación documental final; no atribuir las reglas al modelo |
| F05 | Grouping / 4.5 | Incorporada; actual | `project_grouping.py` y `tests/test_project_grouping.py`. Igualdad de clave nominal/tecnológica/territorial; UUID5; sin municipio, promotor, fuzzy matching ni scores |
| F06 | Flujo de revisión y corrección humana implementado / 4.7 | TODO detallado; opción A, solo actual | `AUDITORIA_REVISION_REPORTES.md`, `admin.py`, `extraction/review.py`, P0, correcciones y `run_silver_stage`. Separar decisiones genéricas, CURRENT y ANTECEDENT; regeneración del operador; territorio independiente. Sin reportes ni rama futura |
| F07 | Metodología experimental / 6.3 | TODO detallado; experimento realizado | `docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md`, contrato V2 y controlador primario. Sistema/truth/evaluator fijados antes de la ejecución; predicciones congeladas antes de evaluar; post-hoc separado |
| F08 | Cascada de matching / 8.2 | TODO detallado; explicación post-hoc | Resultados canónicos §8. POST-HOC DIAGNOSTIC — NOT PRIMARY SCORING. Padre emparejado necesario pero no suficiente; no crear correspondencias ni métricas |
| F09 | Arquitectura propuesta para una futura operación diaria / 9.2.1 | TODO detallado; TRABAJO FUTURO | Decisiones revisadas sobre proceso diario, CLI real, `TFM_CLOSEOUT.md` y `USER_GUIDE.md`. Diferenciar mecanismos existentes y scheduler/reportes persistentes/cola/coordinación propuestos |

Las nueve figuras son REQUIRED en la selección solicitada. La implementación
del sistema descrito en F09 sigue siendo POST-TFM. No se añade otra figura
de referencia INE, otra de capas ni otra sobre evolución del grouping.

## Mensaje, relación con el texto y citas

| ID | Mensaje / texto que complementa | Ejemplo | Referencia necesaria |
| --- | --- | --- | --- |
| F01 | Un proyecto genera publicaciones distintas; sustituye el antiguo TODO genérico del procedimiento | Remisión posterior a Don Rodrigo II, tabla longitudinal existente | TODO-CITA de paralelismo, condicionamiento ambiental, DUP y modalidades de AE |
| F02 | Recuperar, filtrar, decidir alcance y extraer son operaciones distintas; apoya los pasos de 3.1 | No necesita otro BOE; los endpoints ya están explicados | API oficial y código de adquisición; no inventar endpoints |
| F03 | Fuente → estructura → consulta; la referencia territorial es una entrada independiente | Analogía breve y tabla de capas, no un segundo flujo idéntico | Código y procedencia/edición INE (TODO-CITA) |
| F04 | Gemini no entrega Silver/Gold directamente; amplía el bloque de controles de F03 | Solo si aclara salida frente a reglas, sin reutilizar resultados como demostración | Modelo, Pydantic (TODO-CITA), runner y contratos |
| F05 | Las menciones con igual clave comparten identidad; sustituye el TODO genérico de agrupación | Don Rodrigo II de 2026 y Bianor separado; límite HSF de 2022 | Código/tests y Silver/Gold final v2 |
| F06 | La incidencia exige decisión trazable antes de regenerar; amplía revisión sin duplicar F04 | CURRENT/ANTECEDENT; no todos los casos modifican contenido | Guía de calidad, CLI admin y correcciones aprobadas |
| F07 | El orden de los freezes protege la separación entre anotación y predicción; apoya 6.3 | No necesita otro caso; cronología documentada | Resultados canónicos y protocolo |
| F08 | Una discrepancia de identidad puede propagarse por la jerarquía; apoya el diagnóstico de 8.2 | Conteos ya fijados: activos 37/39/20, eventos 30/38/13, actuaciones 36 actuales/58/1 match actual | Diagnóstico aprobado; no recalcular scoring |
| F09 | Una operación diaria exige coordinación adicional; amplía los TODO de operación y gobierno | No necesita caso real de un servicio inexistente | Propuesta de la autora y límites comprobados del sistema |

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

Pendientes: principales entidades (4.4), composición del holdout (6.1),
métricas y ejemplo didáctico (6.6), tablas primarias y atributos condicionados
(7) y limitaciones (8.4). Referenciar tablas existentes en vez de duplicarlas.

Capturas reservadas, no generadas: C01 vista general, C02 mapa/filtros,
C03 ficha/publicaciones (capítulo 5; seleccionar dos o tres en total) y C04
anotación ciega opcional (6.2). Capturar tras la revisión de publicación;
cada imagen tendrá caption, etiqueta y referencia textual.

## Lenguaje visual y fuentes versionables

- TikZ ya disponible mediante `todonotes` de la plantilla; bibliotecas
  `arrows.meta`, `positioning`, `calc`. No instalar herramientas ni externalizar.
- Estilo común en `include/diagramas.tex`; fuentes en
  `figs/procedimiento_administrativo.tex`, `figs/arquitectura_sistema.tex` y
  `figs/grouping_implementado.tex`.
- Tipografía del documento; nodos de 10 pt y notas de 9 pt, sin reducción global.
  Color `tema`, fondos suaves, bordes y flechas vectoriales.
- F01 usa enlace discontinuo para la relación no secuencial de DUP.
  F09 deberá incorporar una leyenda explícita actual/propuesto; el color no
  será el único medio para distinguirlos.
- Las tres figuras tienen caption, etiqueta y referencia desde el texto.
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
Log: `build/compilacion-revision-reportes.txt`. PDF actual:
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

## Impacto documental

- **Documentation impact:** apoyos pedagógicos y redacción acotada de la memoria.
- **Documents reviewed:** cierre TFM, reglas y mapa de fuentes, plantilla,
  compilación, User Guide, contratos, informes W14 y resultados canónicos.
- **Documents updated:** este plan, mapa/reglas de redacción, inventario de
  compilación y fuentes LaTeX afectadas. El manual operativo no cambia.
- **Reason:** validar primero tres diagramas coherentes con el sistema,
  conservando como TODO el resto de la integración.
