# Primera fase de la memoria — revisión humana

Fecha: 2026-09-14. **REQUIRED**. Estado: **READY FOR HUMAN REVIEW**.
Esta aceptación técnica se refiere a la primera fase, no a la memoria completa.
Corrección solicitada el 14/09: dedicatoria restaurada, API explícita y reglas
pedagógicas en [REGLAS_REDACCION.md](REGLAS_REDACCION.md). El registro de
compilación inicial se conserva como histórico; la corrección se documenta al final.

Objetivo único: convertir la plantilla activa en una estructura compacta,
redactar los capítulos iniciales respaldados por el repositorio y dejar
trazabilidad para continuar después de la revisión de la autora.

No objetivos: desarrollo, experimentos, nuevas métricas, revisión de truth,
scoring, modelos, notebooks, Streamlit o datos. Sin web, Gemini, commit o push.
Cambios exclusivamente en `docs/tfm_report/`.

## Auditoría inicial

- Principal: `tfm_report_bgd.tex`, clase `book`, A4/12pt/openany.
- Plantilla institucional CIDaeN/UCLM, versión 0.0, atribuida a Luis de la Ossa.
  Se conserva `template_original/tfm-template.tex`. No se localizaron dentro
  de la memoria instrucciones adicionales de extensión o índice obligatorio;
  la conformidad académica final corresponde a la autora.
- Inclusiones: opciones, configuración, colores, portada y preámbulo.
  Fuente Carlito, márgenes, títulos, cabeceras, flotantes y estilo BibTeX
  `apalike`. Se mantienen.
- Capítulos antiguos: `ch1.tex` («Aspecto», lipsum y dos notas de objetivos),
  `ch2.tex` (tablas académicas, figuras, búsqueda en árbol y ecuación de ejemplo)
  y `ch3.tex` (marcas de revisión). Se conservan intactos pero no se incluyen.
- Preámbulo: dedicatoria de ejemplo, declaración de «trabajo fin de grado»
  con título sin completar, resumen y agradecimientos lipsum. Sin Abstract.
- Anexo activo: «Anexo 1», con lipsum. Se sustituye por dos destinos pertinentes.
- Opciones: título genérico de plantilla y julio de 2026. Se propone título
  específico y septiembre de 2026; identidad de autora y tutores conservada.
- Bibliografía: cinco entradas, cuatro reutilizadas. Sin nuevas referencias.
  Los metadatos locales de Zotero no acreditan acceso a documentos normativos.
- Figuras: logos UCLM/CIDaeN y fotografía de ejemplo ESIIAB. No se han borrado.
- Auxiliares y PDF de una compilación antigua estaban versionados junto al
  fuente. Se mantienen los auxiliares históricos; el PDF principal se actualiza
  con el nuevo resultado y los auxiliares nuevos van a `build/` (ignorado).

## Cambios y criterio editorial

Nueve capítulos; las limitaciones se integran en Discusión y el trabajo futuro
en Conclusiones. La narración avanza de problema y conceptos administrativos
a datos, transformaciones, consulta, evaluación, resultados e interpretación.
El índice impreso muestra capítulos y secciones; las subsecciones permanecen
numeradas en el cuerpo. No se imprime un índice vacío de figuras, algoritmos
o listados. Se conserva el índice de tablas.

Redactados: Introducción, Contexto y un primer borrador de Datos/corpus.
Los capítulos 4–9 y anexos contienen solo estructura y TODO ligados a fuentes.
Resumen/Abstract siguen pendientes. El ejemplo de Don Rodrigo II procede de
la auditoría temporal ya verificada, no de una nueva lectura del holdout.

La declaración de autoría se adapta a máster y al título, con revisión y firma
pendientes. En la primera intervención se retiró indebidamente la sección
de dedicatoria junto con su texto de muestra; esta corrección la restaura
como TODO, antes de la declaración de autoría. `include/redaccion.tex`
centraliza TODO y TODO-CITA. Se retira únicamente el paquete lipsum de la
configuración; no se rediseña la plantilla. Se desactivan anclas de página
durante la portada para evitar duplicados al comenzar la numeración principal.

## Diferencias encontradas y tratamiento

Importantes pero no bloqueantes para esta fase:

1. Los estados «holdout no ejecutado» o «freeze pendiente» en
   `config/evaluation/README.md`, contratos V2/V2-B y procedimiento de ejecución
   son anteriores al cierre. `contract.json` incluso conserva por contrato
   el estado V2-A; el propio contrato explica por qué no debe cambiarse.
   Para el estado vigente se usa el checkpoint de septiembre y resultados
   finales. No se modifican esos documentos ni declaraciones congeladas.
2. El informe `FINAL_CORPUS_W14_DOWNSTREAM_MATERIALIZATION.md` describe Gold
   v1; `FINAL_W14_ADMIN_ACTION_CORRECTIONS.md` fija Gold v2. No se trasladan
   las 251 filas de eventos v1 al estado final, que documenta 240. Son filas
   Gold, no el número de BOE ni el de eventos humanos de evaluación.
3. `src/renewables_permitting/__info__.md` enumera módulos históricos y
   `pipenv`; README, paquete y CLI actuales muestran otra organización y uv.
   No se utiliza ese apunte como fuente de arquitectura.
4. El notebook 07 importa extracción del paquete; los notebooks 10–12 aún
   conservan lógica exploratoria. No se afirma que todos sean ya envoltorios
   mínimos de producción. El paquete y los contratos actuales prevalecen.
5. La auditoría de ingestión antigua declaraba falta de retry; los módulos
   actuales de fuente importan `request_with_transient_retries`. No se copia
   aquella limitación como descripción actual.
6. El contrato de Silver menciona futuras tablas «Curated»; eso no significa
   que falten hoy correcciones. La guía y el informe v2 documentan su aplicación
   trazable antes de aplanar las 13 tablas, sin crear una nueva capa Curated.

Pendientes de entrega, sin impedir esta revisión: referencias normativas
concretas, verificación bibliográfica, título y declaración institucional,
redacción posterior, QA de anotación realmente realizado, capturas y acceso
al archivo externo de reproducibilidad. No se inventan esos datos.

## Índice propuesto

Dedicatoria, declaración y agradecimientos conservados como preliminares.
Resumen y Abstract al principio, redactados al final.

### 1. Introducción

- Contexto y motivación
- Problema abordado
- Objetivo general
- Objetivos específicos
- Alcance
- Estructura de la memoria

### 2. Contexto administrativo y fuente de información

- Tramitación de proyectos de generación renovable
  - Acceso y conexión a la red
  - Evaluación ambiental e información pública
  - Autorizaciones y utilidad pública
- El BOE y su acceso programático
- El problema del seguimiento longitudinal

### 3. Datos y construcción del corpus

- Acceso programático al BOE y adquisición
  - Consulta de sumarios y recuperación del XML
  - Conservación de la fuente
  - Control de errores y límites
- Identidad documental
- Selección de candidatos y decisión de relevancia
- Corpus de desarrollo
- Corpus final
- Separación del conjunto de evaluación

### 4. Metodología y arquitectura del sistema

- Del desarrollo exploratorio al código reutilizable
- Organización en capas Bronze, Silver y Gold
- Extracción estructurada mediante Gemini
- Contratos, validación y canonicalización
- Agrupación de menciones en proyectos
- Resolución territorial
- Revisión humana y antecedentes históricos
  - Decisiones y correcciones versionadas
  - Salvaguarda de antecedentes históricos
- Reproducibilidad y proceso de desarrollo
  - Interfaz de línea de comandos y pruebas
  - Desarrollo asistido por IA

### 5. Aplicación de consulta

- Objetivo, usuarios y arquitectura
- Resumen, catálogo y filtros
- Ficha del proyecto y cronología
- Metodología, reporte y límites

### 6. Metodología experimental

- Diseño independiente y selección del holdout
- Referencia humana y anotación ciega
- Versiones congeladas y orden del experimento
- Emparejamiento y reglas de puntuación V2-B
- Temporalidad, evidencia y salvaguarda P0
- Métricas y ejemplo didáctico
- Reproducibilidad y registro de ejecución

### 7. Resultados

- Composición y resultado operativo
- Resultados primarios: clasificación documental
- Resultados primarios: detección de entidades
- Resultados primarios: atributos condicionados
- Resultados primarios: actuación y activo afectado
- Resultados primarios: evidencia y P0

### 8. Discusión y limitaciones

- Interpretación de los resultados primarios
- Diagnóstico posterior de las discrepancias
- Validez y límites de la evaluación
- Límites del corpus y utilidad del sistema

### 9. Conclusiones y trabajo futuro

- Conclusiones respecto a los objetivos
- Trabajo futuro
  - Operación
  - Calidad y gobierno
  - Enriquecimiento funcional

Anexos: A, Reproducibilidad y acceso a los artefactos; B, Contrato documental
y material de apoyo. Referencias bibliográficas.

## Documentación y trazabilidad

- **Documentation impact:** solo memoria y sus recursos de revisión.
- **Documents reviewed:** `AGENTS.md`, README, cierre TFM, guía de usuario,
  contratos Silver y evaluación V2, calidad/revisión, corpus W14, correcciones,
  agrupación/territorio, exposición de desarrollo, resultados finales y guías
  de aplicación. Se detallan por sección en [MAPA_FUENTES.md](MAPA_FUENTES.md).
  Se inspeccionaron de forma acotada configuración, CLI, tests y markdown/imports
  de notebooks para confirmar el relato; no se ejecutaron notebooks ni tests.
- **Documents updated:** principal LaTeX, preámbulo, opciones, retirada de
  lipsum, nuevos capítulos y macros, PDF; nuevos mapa de fuentes y este informe.
- **Reason:** iniciar la redacción definitiva por fases dentro del alcance
  autorizado. No se modifica USER_GUIDE ni documentación general porque no
  cambia ningún comando operativo, contrato, ruta de datos o comportamiento.

## Compilación y verificaciones de la primera intervención — histórico

Mecanismo de la plantilla: XeLaTeX + BibTeX, coordinados mediante latexmk.
No se instalaron paquetes.

Primer intento, desde `docs/tfm_report/`:

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build tfm_report_bgd.tex
```

Exit code 0, pero cuatro avisos de cita no resuelta: se estaba leyendo el
`tfm_report_bgd.bbl` histórico del directorio fuente. Este PDF provisional no
se entrega. También se detectaron anclas de portada duplicadas, ya corregidas.

Compilación válida y comando recomendado desde `docs/tfm_report/`:

```bash
latexmk -xelatex -bibtex -interaction=nonstopmode -halt-on-error -outdir=build -jobname=tfm_memoria_fase1 tfm_report_bgd.tex
```

Exit code **0**. BibTeX utiliza cuatro entradas y reporta cero warnings.
El jobname separado evita leer los auxiliares históricos. PDF: 33 páginas A4,
`build/tfm_memoria_fase1.pdf`, copiado mediante `shutil.copyfile` a
[tfm_report_bgd.pdf](tfm_report_bgd.pdf) para revisión. Incluye TODO deliberados;
no equivale a 33 páginas de memoria terminada.

Log final: sin referencias o citas indefinidas, sin imágenes ausentes y sin
caracteres perdidos. Advertencias conservadas:

- hooks obsoletos de paquetes y opciones de ligaduras no disponibles en Carlito;
- configuración de captions de algoritmos/listados todavía sin uso;
- overfull de 67,05614 pt en el bloque del logo CIDaeN de la portada conservada:
  revisión visual confirma que el logo queda dentro de la página, sin recorte;
- overfull de 0,30453 pt en un párrafo con cita legal, cosmético.

Verificaciones realizadas (sin pruebas del sistema ni recálculo):

- `.venv/bin/python -B -m renewables_permitting.pipeline --help`: exit 0;
  confirma la CLI real y los nombres de sus fases; no ejecuta pipeline.
- `pdfinfo build/tfm_memoria_fase1.pdf`: exit 0, 33 páginas A4.
- `pdftotext -layout build/tfm_memoria_fase1.pdf build/memoria-texto.txt`:
  exit 0; índice, español, tabla y referencias comprobados en texto.
- `pdftoppm -f 1 -singlefile -scale-to 1100 -png ...` y
  `pdftoppm -f 20 -singlefile -scale-to 1300 -png ...`: exit 0;
  portada y tabla de corpus inspeccionadas visualmente con `view_image`.
- Comprobación documental Python ad hoc, exit 0: 17 fuentes TeX activas,
  14 etiquetas únicas, referencias resueltas, cuatro citas existentes de cinco
  entradas, imágenes presentes, sin lipsum ni demostraciones activas.
  No es una prueba científica ni una ejecución de pytest.
- Inspección de log final y `.blg` mediante `rg`/lectura: avisos anteriores;
  ninguna cita pendiente de resolución técnica. TODO-CITA son pendientes
  bibliográficos deliberados y siguen visibles.

Los logs y comprobaciones están en `build/compilacion-fase1.txt`,
`build/tfm_memoria_fase1.log` y `build/verificacion-documental.txt` (ignorados).
Los auxiliares antiguos de la raíz no deben usarse para juzgar esta compilación.
La primera inspección de notebooks con `python` falló por ausencia de ese alias;
se completó con `.venv/bin/python -B`, sin ejecutar celdas.

## Aceptación y siguiente paso

Revisar índice, título, primeros tres capítulos, citas pendientes y declaración
de uso de asistentes prevista. No iniciar el siguiente bloque automáticamente.
Después de la aceptación y de un commit/push expresamente autorizado, cerrar
Datos y redactar Metodología/Arquitectura y Aplicación. La metodología
experimental precederá a Resultados; seguirán Discusión, Conclusiones y,
por último, Resumen/Abstract. No se ha hecho commit ni push.


## Corrección de preliminares y progresión — 2026-09-14

Clasificación **REQUIRED**. **READY FOR HUMAN REVIEW** para esta corrección.
La instrucción de la autora autoriza corregir el bloque previo, sin avanzar
a nuevos capítulos. La sección de compilación anterior es un registro histórico.

### Alcance y comprobación de preliminares

Dedicatoria restaurada antes de la declaración de autoría, con espacio vertical,
alineación derecha y `TODO: Dedicatoria`, conforme a la posición original
comprobada mediante `git show HEAD:docs/tfm_report/elements/preambulo.tex`.
Se conservan portada, declaración, Resumen, Abstract, Agradecimientos e índices
pertinentes. Los agradecimientos siguen como texto personal pendiente; no se
propone eliminarlos. El índice de figuras sigue previsto para cuando existan
figuras; no se recuperan los ejemplos de algoritmos/listados.

No se eliminaron archivos. Los auxiliares LaTeX que ya estaban modificados al
comenzar se preservaron byte a byte. Se capturaron sus hashes antes de editar
en `build/estado-antes-correccion.json` y se compararon al terminar.

### Estructura y pedagogía

- 2.2: «El BOE y su acceso programático»: fuente, dificultad manual, concepto
  de API y uso de metadatos/enlaces, antes de detalles de implementación.
- 3.1: «Acceso programático al BOE y adquisición», con consulta y XML,
  conservación de la fuente, errores y límites.
- 3.3: «Selección de candidatos y decisión de relevancia»: se diferencia
  el filtro de títulos de la clasificación y extracción posteriores.
- Se explican pipeline, endpoint, HTTP/GET, JSON, Bronze, snapshot, Parquet,
  manifest y caché antes de apoyarse en esos términos. Una lista breve aclara
  el orden real: filtro de títulos antes de descargar los XML.
- Tabla de dos publicaciones de Don Rodrigo II basada en la auditoría y
  correcciones ya verificadas. Se conserva la tabla del corpus sin cambiar cifras.
- `REGLAS_REDACCION.md` registra el criterio sencillo/directo/completo/progresivo,
  la conservación de secciones reales como TODO y los mensajes de las figuras
  y capturas previstas. Se enlaza desde el principal y el mapa de fuentes.
- La introducción se revisó y se conservó. En capítulos 4, 6 y 8 se ajustaron
  únicamente notas TODO: analogía de capas, agrupación, uso de asistentes,
  ejemplo de matching y explicación de cascada. No se redactaron capítulos nuevos.

### Precisión de la descripción API

Fuentes leídas: `boe_source.py`, `boe_documents.py`, `boe_http.py`,
`boe_candidates.py`, `pipeline.py::run_source_stage`,
`extraction/documents.py`, guardas de alcance y tests existentes de
sumarios/documentos; guía de usuario y referencias de la primera fase.
`MAPA_FUENTES.md` contiene la tabla de afirmación → función concreta.

Puntos que determinan el relato:

- Sumarios GET por fecha, con `Accept: application/json`; XML obtenido desde
  `url_xml` del sumario, después del filtro de candidatos.
- La comprobación de identidad candidato/XML compara ID y fecha. No exige
  igualdad de títulos; la entrada conserva el título del sumario.
- La política actual sí reintenta determinados fallos transitorios; esto
  difiere de la auditoría de ingestión antigua que decía «sin retry».
- Persistencia de una instantánea validada no implica caché ni reanudación
  automática de adquisición. Un fallo impide publicar la fuente como completa.
- La relevancia no queda resuelta para todos los candidatos antes de Gemini;
  clasificación y extracción se completan en su salida y validación.

No se llamó a la API, Gemini u otro servicio; no se ejecutó el pipeline,
se recalcularon métricas ni se modificaron tests o contratos.

### Compilación y controles de esta corrección

Desde `docs/tfm_report/`:

```bash
latexmk -xelatex -bibtex -interaction=nonstopmode -halt-on-error -outdir=build -jobname=tfm_memoria_correccion tfm_report_bgd.tex
```

Dos ejecuciones, ambas exit 0; la segunda incorpora la precisión del control
ID/fecha/título. Resultado final: **39 páginas A4**, 214.572 bytes, incluidas
las secciones futuras TODO. `build/tfm_memoria_correccion.pdf` se copia a
`tfm_report_bgd.pdf`. Ninguna instalación ni cambio de configuración adicional.

El log final no contiene referencias/citas indefinidas, errores o caracteres
perdidos; BibTeX no reporta warnings. Persisten los avisos de paquetes,
ligaduras, captions no usados y los overfull previos de 67,05614 pt en el bloque
del logo y 0,30453 pt en una cita legal. El underfull observado en la primera
compilación de esta corrección no aparece en la final.

Comandos y comprobaciones documentales:

- `pdfinfo build/tfm_memoria_correccion.pdf`: exit 0, tamaño/formato anteriores.
- `pdftotext -layout build/tfm_memoria_correccion.pdf build/correccion-texto.txt`:
  exit 0; comprobados orden de preliminares, índice API/candidatos y acentos.
- `pdftoppm` con `-singlefile -png`, páginas 3, 20 y 19, resoluciones máximas
  1000, 1200 y 1000: exit 0. `view_image` confirma dedicatoria, lista/endpoint API
  y tabla longitudinal legibles. No se declara inspección visual de las 39 páginas.
- Comprobación Python documental ad hoc: exit 0; 17 entradas TeX activas,
  18 etiquetas únicas, cuatro citas existentes de cinco referencias, imágenes
  presentes, sin ejemplos/lipsum activos ni referencias pendientes de resolución.
- Comparación de hashes con el inicio de esta corrección: ningún archivo
  eliminado ni auxiliar previo alterado. Los únicos cambios son los listados abajo.

No se ejecutó pytest: el bloque es editorial y se verificó mediante compilación,
lectura, inspección visual y controles documentales, no pruebas productivas.
Logs: `build/compilacion-correccion.txt`, `build/tfm_memoria_correccion.log`,
`build/verificacion-correccion.txt`.

### Archivos de esta corrección

Rutas relativas a `docs/tfm_report/`:

- `elements/preambulo.tex`
- `tfm_report_bgd.tex`
- `tfm_report_bgd.pdf`
- `chapters/02_contexto.tex`
- `chapters/03_datos.tex`
- `chapters/04_metodologia.tex` (solo TODO)
- `chapters/06_evaluacion.tex` (solo TODO)
- `chapters/08_discusion.tex` (solo TODO)
- `MAPA_FUENTES.md`
- `REVISION_FASE_1.md`
- `REGLAS_REDACCION.md` (nuevo)

**Documentation impact:** reglas, preliminares y claridad de la memoria.
**Documents reviewed:** plantilla histórica, capítulos existentes, cierre,
guía y fuentes/garantías de adquisición indicadas.
**Documents updated:** los once archivos anteriores.
**Reason:** corrección expresa de la autora sin desarrollo ni avance de fase.
Los TODO-CITA, validación académica y redacción posterior siguen pendientes.
Sin commit ni push; detenerse para revisión humana de esta corrección.
