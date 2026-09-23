# Compilación y política de artefactos de la memoria

Clasificación: **REQUIRED — limpieza acotada previa al commit de la memoria**.
Esta política sustituye la copia automática del PDF de trabajo a la raíz
utilizada en las revisiones anteriores. No modifica el contenido de la memoria.

## Fuentes y configuración

Versionar `.tex`, `bib/ref.bib`, imágenes necesarias (incluido
`figs/logouclm.pdf`), `.latexmkrc` y documentación de redacción.
Conservar las fuentes activas, la bibliografía y los recursos necesarios para
reproducir el documento público.

No se ignoran globalmente los PDF ni extensiones ambiguas como `.out`:
las exclusiones nuevas se limitan al nombre del documento principal.
`build/` y `*.log` ya estaban ignorados por el `.gitignore` del repositorio.

## Compilar desde terminal

Desde `docs/tfm_report/`, ejecutar:

```bash
latexmk -synctex=1 -interaction=nonstopmode -halt-on-error -file-line-error tfm_report_bgd.tex
```

`.latexmkrc` selecciona XeLaTeX, permite regenerar la bibliografía con BibTeX
y establece `build/` como directorio de salida. No hace falta cambiar el
nombre de trabajo para evitar bibliografías antiguas: los auxiliares de la raíz
se trasladaron a un respaldo local y no participan en la compilación.

Abrir **`build/tfm_report_bgd.pdf`** para revisar el estado actual.
Su archivo de navegación es `build/tfm_report_bgd.synctex.gz`.
LaTeX/BibTeX pueden necesitar varias pasadas, coordinadas por una invocación
normal de latexmk. No se instalan dependencias ni se ejecuta el pipeline.

## Política permanente de `build/` y revisiones temporales

`build/` es un directorio ignorado y regenerable, reservado exclusivamente
para los outputs de compilación de la memoria LaTeX activa. No se utiliza para
capturas o imágenes de inspección, texto extraído del PDF, logs de auditoría,
JSON, estados Git, PDFs comparativos ni otros artefactos temporales de revisión.

Esos artefactos se generan fuera del repositorio, preferentemente bajo
`/tmp/tfm_report_review/` o en otro directorio temporal específico de la tarea.
Si una evidencia merece conservación académica, su incorporación al repositorio
y su ubicación documental deben decidirse expresamente. Antes de promover el
PDF de entrega se verificará una compilación reproducible desde un `build/`
limpio.

## LaTeX Workshop

Se reutiliza la receta local existente de `.vscode/settings.json`, que ya
seleccionaba XeLaTeX, `-synctex=1`, compilación al guardar y visor `tab`.
Solo se añadieron estos dos ajustes:

```json
"latex-workshop.latex.outDir": "%DIR%/build"
```

Y en los argumentos de la herramienta latexmk:

```json
"-outdir=%OUTDIR%"
```

El visor y la compilación quedan apuntando al mismo directorio que contiene
PDF y SyncTeX. El resto de los ajustes de VSCode, incluidos los de Python,
se conserva. `.vscode/` ya estaba ignorado y continúa siendo configuración
local; estos dos ajustes quedan documentados aquí para reproducirlos en
otro equipo. `.latexmkrc` sí es configuración versionable de la memoria.
No se ha abierto ni automatizado la interfaz gráfica de VSCode en esta tarea.

## Auxiliares retirados del seguimiento

Todos tienen el prefijo `docs/tfm_report/tfm_report_bgd`:

- `.aux`
- `.bbl`
- `.blg`
- `.fdb_latexmk`
- `.fls`
- `.loalgorithm`
- `.locode`
- `.lof`
- `.lot`
- `.out`
- `.synctex.gz`
- `.toc`
- `.xdv`

Se usó `git rm --cached` sobre estos trece nombres explícitos: las bajas
quedan preparadas en el índice para el próximo commit, sin hacer commit.
Añadir `.gitignore` por sí solo no habría retirado archivos ya versionados.
Los archivos físicos se trasladaron, sin perder sus bytes, a
`build/limpieza-latex-20260914/auxiliares-raiz/`. El log generado de la raíz
también se conserva allí. Salidas anteriores con el mismo nombre dentro de
`build/` se guardaron en `compilacion-anterior/` bajo ese respaldo.

El `.bbl` no es una fuente editada a mano ni una dependencia de entrega
precompilada: el principal usa `\bibliography{bib/ref}`, el `.blg` identifica
BibTeX y el `.fdb_latexmk` lo registra como generado desde `bib/ref.bib`.
El historial solo registra su incorporación inicial junto a la plantilla.
Por ello se trata como artefacto regenerable, conservando intacto el `.bib`.

## PDF público y PDF institucional

El PDF de trabajo se genera en `build/tfm_report_bgd.pdf` y no se versiona. El
PDF histórico de la raíz queda fuera de la distribución pública. La futura
release debe generar expresamente su PDF público desde estas fuentes y sin
`figs/firma_signature_black.png`; la inclusión condicional permite que la
ausencia no genere errores, TODO ni placeholders.

Si la entrega institucional requiere firma, puede generarse localmente un PDF
separado con esa imagen. Ese PDF firmado es privado: no se versiona, no se
publica ni se utiliza como artefacto público reproducible.

## Alcance documental

- **Documentation impact:** exclusivamente operación LaTeX y política Git.
- **Documents reviewed:** `.gitignore`, cierre TFM, plantilla/principal,
  bibliografía y auxiliares, historial de Git, configuración LaTeX Workshop
  e informes de revisión existentes.
- **Documents updated:** este documento; `.gitignore`, `.latexmkrc` y los
  dos ajustes locales de VSCode. Ningún capítulo, preámbulo, estilo, imagen
  o referencia bibliográfica cambia en esta limpieza.
- **Reason:** separar fuentes y salidas regenerables antes de un commit
  revisable, sin perder trabajo ni alterar el experimento.

## Validación de la limpieza inicial — 2026-09-14

Una invocación del comando anterior: **exit 0**, PDF de **39 páginas A4**
en `build/tfm_report_bgd.pdf`. El log confirma que se lee `.latexmkrc` y
que la bibliografía procede de `build/tfm_report_bgd.bbl`, regenerada por
BibTeX sin warnings. No hay referencias/citas indefinidas ni caracteres
perdidos. Persisten los avisos cosméticos ya conocidos de la plantilla:
ligaduras/hooks, captions no usados y overfull de 67,05614 pt en el bloque
del logo y 0,30453 pt en una cita legal. No se corrigieron estilos ni redacción.

Comprobaciones ejecutadas:

```bash
pdfinfo build/tfm_report_bgd.pdf
synctex view -i 5:0:chapters/01_introduccion.tex -o build/tfm_report_bgd.pdf
synctex edit -o 13:184.452667:321.370758:build/tfm_report_bgd.pdf
```

Todas con exit 0. La navegación directa encuentra la página 13 y la inversa
vuelve a `chapters/01_introduccion.tex`, línea 5. Se verificaron las opciones
locales de Workshop y la existencia conjunta de PDF/SyncTeX; no se afirma
una comprobación visual del visor de VSCode.

El control documental mediante Python confirmó:

- 31 archivos previos de fuentes, documentación, imágenes y PDF idénticos
  byte a byte, incluidos todos los capítulos y el PDF raíz;
- las 13 bajas del índice afectan exclusivamente a los auxiliares enumerados;
- sus copias locales conservan los hashes iniciales;
- las reglas ignore excluyen auxiliares/build y dejan visibles todas las
  fuentes y el PDF de figura;
- el JSON de Workshop conserva exactamente sus ajustes anteriores salvo
  `outDir` y el argumento `-outdir=%OUTDIR%`;
- `git diff --check` y `git diff --cached --check` pasan.

El primer intento de actualizar el índice encontró `.git` de solo lectura;
la repetición autorizada con permisos de escritura completó `git rm --cached`.
No se hizo commit ni push. No se ejecutaron tests productivos: las comprobaciones
corresponden únicamente a compilación, navegación, Git y preservación de archivos.

## Inventario exacto de fuentes conservadas

Actualizado en la primera integración de figuras de 2026-09-14:
TikZ ya está disponible mediante `todonotes`; `include/diagramas.tex` carga
sus bibliotecas y define los estilos comunes. Los tres diagramas se compilan
directamente desde fuentes `.tex`, sin conversión externa ni imágenes raster.
El inventario actual incluye trece diagramas. La revisión integral añade EIA,
conjuntos documentales, contrato, flujo operativo y F06; además revisa F03,
F04 y F09 con el mismo mecanismo y sin dependencias nuevas.
Las figuras activas forman parte de las fuentes versionadas y se validan mediante
la compilación canónica y la revisión visual del PDF resultante.

Además de `.gitignore` en la raíz, los siguientes archivos públicos bajo
`docs/tfm_report/` son versionables. El PDF se genera desde estas fuentes;
`.vscode/settings.json` permanece como configuración local ignorada.

```text
.latexmkrc
COMPILACION.md
bib/ref.bib
chapters/01_introduccion.tex
chapters/02_contexto.tex
chapters/03_datos.tex
chapters/04_metodologia.tex
chapters/05_aplicacion.tex
chapters/06_evaluacion.tex
chapters/07_resultados.tex
chapters/08_discusion.tex
chapters/09_conclusiones.tex
chapters/anexos.tex
elements/portada.tex
elements/preambulo.tex
figs/CIDaeN.png
figs/api_boe_corpus.tex
figs/arquitectura_sistema.tex
figs/cascada_matching.tex
figs/conjuntos_documentales.tex
figs/contrato_extraccion.tex
figs/esiiab.png
figs/evaluacion_impacto_ambiental.tex
figs/logouclm.pdf
figs/logouclm.png
figs/extraccion_validacion.tex
figs/flujo_operativo_pipeline.tex
figs/grouping_implementado.tex
figs/metodologia_experimental.tex
figs/operacion_diaria_futura.tex
figs/procedimiento_administrativo.tex
figs/revision_correcciones.tex
include/colores.tex
include/configuracion.tex
include/diagramas.tex
include/opciones.tex
include/redaccion.tex
tfm_report_bgd.tex
```

## Revisión humana integral — 2026-09-15

La compilación final se ejecutó desde `docs/tfm_report/` con el comando habitual
indicado al principio de este documento. Terminó con **exit 0** y generó
`build/tfm_report_bgd.pdf`, de **101 páginas A4**, junto a su archivo SyncTeX.
El PDF contiene **13 figuras** y **18 tablas**. No hay referencias ni citas
indefinidas, destinos duplicados, caracteres perdidos o marcadores `??`.

La numeración del catálogo PDF se comprobó directamente: `PageLabels` comienza
con estilo romano minúsculo en el índice físico 0 y cambia a decimal en el
índice 14. Por tanto, las catorce páginas preliminares se etiquetan `i`--`xiv`
y el capítulo 1 empieza en la etiqueta `1`. Para obtenerlo, `\frontmatter` se
ejecuta antes de la portada y `hyperref` usa `plainpages=false` y
`pdfpagelabels`; los enlaces se conservan activos sin bordes visibles.

Persisten los dos `overfull` históricos: **67,05614 pt** en el logo de portada y
**0,30453 pt** en la cita legal inicial. No se añadió ningún `overfull`. El log
final contiene cuatro `underfull vbox` y dos `underfull hbox`; el log anterior a
esta revisión contenía cuatro avisos `underfull`. Los dos avisos adicionales proceden
de la redistribución de páginas y de líneas de TODO/bibliografía, y la inspección
visual no muestra cortes ni solapamientos. Permanecen además los avisos de
hooks, ligaduras de Carlito y configuraciones de caption no utilizadas de la
plantilla.

Se revisaron visualmente portada y preliminares, la transición al capítulo 1,
las figuras nuevas y revisadas, los lugares C01--C04, el caso Hipódromo, la
tabla 9.1 y F09. Durante esa revisión se eliminaron los bordes visibles de los
enlaces y se corrigieron cruces de líneas en el flujo operativo y F06. La figura
de corpus ya había sido rediseñada tras detectar solapamientos en su primera
versión. El PDF raíz versionado no se actualizó.

## Reconstrucción limpia reproducible — 2026-09-17

Se preservaron fuera del repositorio los trece artefactos de la compilación de
trabajo y se vació completamente `build/`. Desde `docs/tfm_report/` se ejecutó
el procedimiento canónico, sin reutilizar auxiliares:

```bash
latexmk -synctex=1 -interaction=nonstopmode -halt-on-error -file-line-error tfm_report_bgd.tex
```

La ejecución terminó con **exit 0** y regeneró exclusivamente los trece outputs
activos. El PDF resultante es A4, tiene **105 páginas**, **13 figuras**, **18
tablas** y **18 referencias bibliográficas utilizadas**. No contiene referencias
o citas indefinidas ni marcadores `??`. Su SHA-256 es
`3f96d6eda5f8fc4ea8cc3a2dce93441b7b34e3f238619b60bb5c3924d4d3e165`.

El texto extraído con conservación aproximada de layout fue byte a byte idéntico
al baseline. Las 105 páginas renderizadas con los mismos parámetros también
fueron byte a byte idénticas. El PDF binario solo difiere por la fecha de
creación, el identificador interno derivado y siete bytes de tamaño; son
diferencias no materiales.

El perfil final de avisos no cambió respecto al baseline: permanecen los dos
`overfull` históricos de 67,05614 pt y 0,30453 pt, seis `underfull vbox`, doce
avisos `fontspec`, tres hooks obsoletos y dos configuraciones `caption` sin uso.
No apareció ningún warning nuevo. La validación se clasificó
**REPRODUCIBLE — NON-MATERIAL DIFFERENCES**.

El nuevo `build/` se conserva como compilación de trabajo limpia. El PDF raíz
tracked no se modificó: solo se promoverá después de cerrar el contenido, los
preliminares, Streamlit y sus capturas, y la revisión final de entrega.

## Integración del despliegue público y capturas — 2026-09-18

El procedimiento canónico compiló con **exit 0** tras integrar la URL pública
y cuatro capturas de Streamlit. El PDF de trabajo resultante es A4 y tiene
**107 páginas**. Las cuatro imágenes, sus captions y sus referencias se
renderizan en el capítulo 5; no hay referencias o citas indefinidas ni
marcadores `??`.

El perfil de avisos conserva los dos `overfull` históricos de 67,05614 pt y
0,30453 pt, los avisos de `fontspec`, hooks y configuraciones de `caption` ya
documentados. No permanece ningún aviso nuevo atribuible a las capturas o al
texto de despliegue. El PDF raíz versionado no se promovió.
