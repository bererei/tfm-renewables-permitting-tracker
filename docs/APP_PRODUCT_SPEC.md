# Application Product Specification

## 1. Purpose

Este documento define **Gate 2 — Product** para la aplicación pública del TFM.
Convierte las decisiones de datos de
[`APP_DATA_CATALOG.md`](APP_DATA_CATALOG.md) en preguntas, medidas, filtros,
vistas, interacciones, estados y criterios de aceptación concretos. Es la
fuente funcional previa a cualquier cambio de Gold, mapa o Streamlit.

La lógica de diseño es:

```text
PREGUNTA
→ DATO
→ MÉTRICA O DIMENSIÓN
→ VISUALIZACIÓN
→ INTERACCIÓN EXPLÍCITA
```

La aplicación es un cuadro de mando analítico de solo lectura sobre Gold, no
un registro jurídico exhaustivo ni una aplicación administrativa. Streamlit no
lee Silver, no ejecuta el pipeline y no corrige datos.

**Gate 2 status:** `PRODUCT GATE PASSED`. Decisión humana registrada el
**2026-08-20**. Los detalles cosméticos pueden resolverse durante la
implementación sin reabrir este gate.

### Dataset lifecycle and terminology

- **Development corpus:** los 140 documentos actuales, utilizados para
  desarrollo, contratos, tests, regresiones, validación de arquitectura y
  diseño del dashboard. Constituyen la referencia de desarrollo, no el corpus
  final del producto.
- **Final TFM corpus:** el nuevo corpus multianual con las publicaciones BOE
  seleccionadas para el periodo final del TFM. Sustentará los resultados y
  métricas de la memoria, los screenshots definitivos, el mapa, los gráficos y
  la demostración del producto.
- **Deployment dataset:** el artefacto Gold validado generado desde el Final
  TFM corpus y publicado para la aplicación web. Tiene downstream ID, manifest,
  hashes y versión propios, y un procedimiento de rollback.

```text
Development corpus → desarrollo y regresión
Final TFM corpus    → materialización final
Deployment dataset → Gold publicado
```

Los tres conceptos son distintos. La especificación funcional es independiente
de sus cardinalidades: la aplicación calcula límites, filtros y medidas a
partir del deployment dataset efectivamente cargado.

## 2. Users and product goals

### Primary users

- una persona interesada en localizar y seguir proyectos energéticos publicados
  en el BOE;
- una investigadora que necesita comparar territorio, trámites y evolución
  documental;
- la autora del TFM durante la demostración, validación visual y auditoría local.

### Product goals

1. Resumir cuántos proyectos y publicaciones BOE cumplen una selección.
2. Mostrar dónde aparecen territorialmente esos proyectos.
3. Explicar sus situaciones publicadas sin presentarlas como estado jurídico.
4. Permitir pasar del conjunto agregado al proyecto y a la evidencia BOE.
5. Mantener definiciones, granularidades y filtros comprensibles para una
   persona familiarizada con Qlik Sense.

### Non-goals for August

- promotor o participantes;
- potencia global o canónica de proyecto;
- producción energética;
- listado exhaustivo de tecnologías;
- booleano exhaustivo de hibridación;
- título o dimensión completa de publicaciones;
- estado jurídico consolidado;
- administración, autenticación, correcciones o pipeline desde la UI.

## 3. Analytical concepts

| Concepto | Definición en el producto |
| --- | --- |
| Dimensión | Campo categórico o temporal que segmenta datos, como tecnología principal, territorio, trámite o fecha. |
| Medida | Agregación definida sobre un grano, como BOE distintos por año. |
| KPI | Medida principal presentada como tarjeta y recalculada con la selección global. |
| Filtro | Control explícito que restringe el conjunto analítico. |
| Selección | Valor activo de uno o varios filtros; Streamlit debe propagarlo mediante estado explícito. |
| Vista | Región funcional con una pregunta propia: Resumen, Explorar, Ficha o Metodología. |
| Granularidad | Unidad de una fila o conteo: proyecto, BOE, proyecto–trámite o territorio. |

Streamlit no ofrece por sí solo el motor asociativo de Qlik. Ningún click debe
considerarse filtro salvo que la aplicación lo traduzca explícitamente al
estado, lo muestre como selección activa y permita retirarlo.

## 4. Questions to answer

| Área | Pregunta | Dato | Medida o dimensión | Vista principal |
| --- | --- | --- | --- | --- |
| Visión general | ¿Cuántos proyectos hay en el conjunto filtrado? | `project_id` | proyectos distintos | Resumen |
| Visión general | ¿Cuántos BOE distintos respaldan la selección? | `boe_id` | publicaciones distintas | Resumen |
| Territorio | ¿Cómo se distribuyen los proyectos por CCAA, provincia y municipio? | códigos INE | proyectos distintos por código | Resumen |
| Administración | ¿Cómo se distribuyen las situaciones publicadas? | latest/historical actions | proyecto–trámite por decisión | Resumen |
| Tiempo | ¿Cómo evoluciona la publicación de BOE? | `publication_date`, `boe_id` | BOE distintos por periodo | Resumen |
| Seguimiento | ¿Qué proyectos cumplen una situación y uno o varios trámites? | acciones | filtros same-row y any/all | Explorar |
| Seguimiento | ¿La coincidencia es última por trámite o histórica? | interpretación temporal | dimensión latest/historical | Resumen, Explorar |
| Territorio | ¿Qué proyectos están asociados a un territorio seleccionado? | `project_locations` | conjunto de `project_id` | Resumen, Explorar |
| Proyecto | ¿Cuándo aparece por primera y última vez? | fechas Gold | mínimo/máximo publicados | Ficha |
| Proyecto | ¿Cuáles son sus últimas situaciones por trámite? | latest actions | una fila por trámite | Ficha |
| Proyecto | ¿Qué secuencia documental y evidencia lo respalda? | `project_events` | cronología completa | Ficha |
| Proyecto | ¿Qué territorios están asociados? | localizaciones Gold | jerarquía territorial | Ficha |

Los componentes y relaciones solo añadirían preguntas secundarias de ficha si
Gate 3 los implementase. No son necesarios para responder las preguntas
principales.

## 5. Gate 1 constraints

### Approved current data

Se puede usar identidad y nombre de proyecto, tecnología principal, fechas,
BOE ID, URL HTML derivada, actuaciones, decisiones, modificaciones, última
decisión publicada por trámite, evidencia y territorio con códigos INE.

### Approved external dependency

El mapa requiere geometrías administrativas poligonales versionadas para CCAA,
provincias y municipios. La selección de fuente queda pendiente de investigación
controlada en Gate 3.

### Approved concepts deferred after Gate 2

Gate 1 confirmó que `project_components` y `project_relationships` podrían
modelarse sin reextracción. Gate 2 decide **DROP FROM AUGUST** para ambos:
quedan como conceptos aprobados, pero diferidos a POST-TFM y fuera de la ficha
de agosto.

### Excluded

Promotor, participantes, potencia, multi-tecnología exhaustiva, `is_hybrid`
exhaustivo, títulos BOE y dimensión `publications` permanecen fuera de agosto.

### Contract domains in the final corpus

El Final TFM corpus puede incorporar nuevos trámites, decisiones, tecnologías
raíz, territorios y combinaciones ya admitidos por los contratos. La aplicación
debe mantener mappings legibles para valores conocidos y un fallback seguro y
legible para valores futuros que sigan siendo contractuales. Antes del
deployment final se auditan todos los dominios observados. Un valor que viole
un enum o contrato produce **STOP AND REVIEW**; Streamlit no lo descarta ni lo
oculta silenciosamente. Los valores observados en el development corpus no se
consideran un universo exhaustivo.

## 6. KPIs

### KPI 1 — Proyectos — REQUIRED

- **Etiqueta:** Proyectos.
- **Definición:** `nunique(project_id)` del conjunto de proyectos elegibles del
  deployment dataset tras aplicar los filtros.
- **Grano antes de agregar:** una fila por proyecto.
- **Interacción:** responde a todos los filtros globales.

### KPI 2 — Publicaciones BOE — REQUIRED

- **Etiqueta:** Publicaciones BOE.
- **Definición:** `nunique(boe_id)` de las publicaciones elegibles del
  deployment dataset que respaldan la selección.
- **Sin filtros administrativos o temporales:** cuenta todos los BOE asociados
  a los proyectos elegibles por nombre, tecnología y territorio.
- **Con fecha, situación o trámite activos:** cuenta solo los BOE de las filas
  que cumplen esos predicados y pertenecen a proyectos elegibles. En modo
  latest usa las filas latest que respaldan el match; en modo histórico usa
  las filas históricas que lo respaldan.
- **Garantía:** nunca incorpora BOE pertenecientes exclusivamente a proyectos
  fuera del conjunto elegible.

### KPI 3 — NOT REQUIRED / OPTIONAL POST-TFM

La fila principal tendrá dos KPIs. Los candidatos evaluados no justifican una
tercera tarjeta:

| Candidato | Clasificación | Razón |
| --- | --- | --- |
| actuaciones administrativas únicas | OPTIONAL como dato de ficha, no KPI global | aporta volumen, pero no mejora la pregunta ejecutiva y su grano difiere de proyecto/BOE |
| proyectos con una situación concreta | REJECTED como KPI separado | duplica el KPI Proyectos cuando esa situación ya es filtro |
| territorios representados | REJECTED como KPI principal | cambia de significado con el nivel activo del mapa |
| potencia | REJECTED | Gate 1: no normalizada ni aditiva |

No se añadirá una tarjeta vacía por simetría visual. La decisión humana de
Gate 2 fija exactamente dos KPIs REQUIRED.

## 7. Global filters

### Placement

Los filtros viven en la **sidebar** de Resumen y Explorar. La zona principal
empieza con un resumen compacto de filtros activos y una acción **Limpiar
filtros**. No se duplican controles de fecha o territorio encima de gráficos.

### Controls

| Grupo | Control | Cardinalidad | Semántica |
| --- | --- | --- | --- |
| Proyecto | Buscar proyecto | texto | coincidencia normalizada sobre nombre; no reemplaza selección exacta de fila |
| Proyecto | Tecnología principal | multiselección | OR dentro de tecnología |
| Territorio | Comunidad autónoma | multiselección | OR; restringe provincias y municipios disponibles |
| Territorio | Provincia | multiselección | OR; AND con CCAA; restringe municipios |
| Territorio | Municipio | multiselección | OR; AND con niveles padre |
| Administración | Interpretación temporal | selección única | Última decisión publicada por trámite, por defecto; o Cualquier publicación histórica |
| Administración | Situación publicada | multiselección | OR entre decisiones |
| Administración | Trámite | multiselección | OR o ALL según coincidencia |
| Administración | Coincidencia de trámites | selección única condicional | aparece con dos o más trámites: Al menos uno / Todos |
| Tiempo | Fecha desde / hasta | intervalo inclusivo | aplica sobre `publication_date` administrativa |

Todos son filtros principales. **Coincidencia de trámites** es contextual, no
un bloque avanzado permanente. Los municipios se cargan después de las
selecciones padre para evitar una lista irrelevante y estados incompatibles.
Las opciones y conteos se derivan del deployment dataset; ninguna cardinalidad
del development corpus es un límite funcional.

### Combination rules

- OR dentro de tecnología, CCAA, provincia, municipio y situación.
- AND entre categorías.
- Trámites usa **Al menos uno** o **Todos** de forma explícita.
- Fecha, trámite y situación conservan semántica **same-row**.
- Cambiar un padre territorial elimina selecciones hijas incompatibles y lo
  comunica de forma no intrusiva.

## 8. Date semantics

El intervalo global es inclusivo y se controla solo desde la sidebar. Su límite
inicial disponible es `min(publication_date)` y el final es
`max(publication_date)` del deployment dataset. Por defecto abarca todo el
corpus desplegado; ningún año se codifica como límite del producto. El gráfico
temporal no introduce un segundo brush de fechas en agosto.

| Objeto | Efecto de fecha |
| --- | --- |
| KPI Proyectos | cuenta proyectos con al menos una fila administrativa elegible dentro del intervalo, además de los restantes filtros |
| KPI Publicaciones BOE | cuenta BOE distintos de las filas administrativas elegibles dentro del intervalo |
| Gráfico temporal | limita el eje y las filas al intervalo; cuenta los mismos BOE de soporte del KPI BOE por periodo |
| Mapa | muestra todos los territorios canónicos de los proyectos elegibles; la fecha selecciona proyectos, no recorta el linaje territorial por fecha |
| Gráfico administrativo | aplica fecha después de construir latest o sobre todas las filas históricas, según el modo seleccionado |
| Tabla de proyectos | conserva una fila por proyecto que tenga match dentro del intervalo |
| Ficha | siempre muestra la cronología completa del proyecto; no hereda el recorte temporal del buscador |

Esta distinción debe aparecer en ayuda: el intervalo localiza proyectos y BOE
publicados en ese periodo, pero no redefine las fechas o la cronología canónica
de la ficha. Cambiar el intervalo recalcula KPIs, mapa, gráfico de situaciones,
serie temporal, tabla/listado de proyectos y publicaciones conforme a la
semántica de cada objeto. Cuando corresponda, la UI dice **proyectos con
publicaciones asociadas en el intervalo**, no “proyectos activos”.

## 9. Cross-filtering strategy

### REQUIRED AUGUST

- filtros explícitos de sidebar;
- cascada territorial;
- intervalo de fechas único;
- situación, trámite, interpretación y any/all;
- recálculo de KPIs, mapa, gráficos y tabla con una sola selección global;
- selección de una fila en Explorar para abrir la ficha;
- resumen visible de filtros activos y acción para limpiarlos.

### NOT REQUIRED FOR AUGUST

- click en una geometría para escribir CCAA/provincia/municipio en el mismo
  estado global y mostrarlo como filtro activo;
- click en una barra para añadir la situación publicada seleccionada.

Solo pueden entrar como OPTIONAL si el componente gráfico devuelve selecciones
estables, accesibles y testeables sin nueva dependencia ni complejidad de
estado. Si complican implementación o tests, se eliminan. Siempre tienen una
alternativa equivalente mediante filtros explícitos.

### POST-TFM

- selección directa o brush de intervalo sobre el gráfico temporal;
- lasso, multi-selección compleja o asociaciones implícitas tipo Qlik;
- sincronización persistente de selecciones entre sesiones.

**Decisión aprobada:** entregar filtros explícitos y selección de fila. No se
intenta reproducir el motor asociativo de Qlik. El click-to-cross-filter de mapa
o barras es OPTIONAL y no se duplica el control temporal.

## 10. Page architecture

| Vista | Acceso | Pregunta | Datos |
| --- | --- | --- | --- |
| Resumen | navegación principal y vista inicial | ¿Qué está ocurriendo en el conjunto seleccionado? | deployment dataset + geometría validada |
| Explorar | navegación principal | ¿Qué proyectos cumplen la selección? | catálogo Gold desplegado y filtros existentes |
| Ficha | selección/deep link de un proyecto | ¿Qué se ha publicado sobre este proyecto? | detalle completo del deployment dataset |
| Metodología | navegación principal | ¿Qué significan y qué no significan estos datos? | contenido documental |
| Auditoría de datos | solo variable local habilitada | ¿Es íntegro y trazable el Gold? | cuatro tablas Gold y vistas de auditoría |

La Ficha es una vista contextual, no una página que se recorra sin proyecto.
Resumen y Explorar comparten el estado global durante la sesión; la ficha se
carga por `project_id` contra el deployment dataset completo.

## 11. Dashboard — Resumen

### Visual order

1. Título: **Proyectos energéticos publicados en el BOE**.
2. Contexto de una frase: seguimiento documental, no estado jurídico.
3. Resumen de filtros activos y limpiar filtros.
4. Dos tarjetas KPI en fila horizontal.
5. Mapa territorial protagonista y gráfico administrativo, en proporción
   aproximada 2:1 en desktop.
6. Gráfico temporal a ancho completo.
7. Resumen corto de proyectos y enlace claro a **Explorar proyectos**.
8. Nota de versión/metodología y acceso al reporte de errores.

### Objects

| Objeto | Pregunta | Medida | Interacción principal |
| --- | --- | --- | --- |
| Proyectos | ¿Cuántos cumplen? | proyectos distintos | filtros globales |
| Publicaciones BOE | ¿Cuántos BOE respaldan? | BOE distintos de soporte | filtros globales |
| Mapa | ¿Dónde aparecen? | proyectos distintos por código | hover + nivel/drill + filtros; click-to-filter opcional |
| Últimas situaciones publicadas por trámite | ¿Qué situaciones se publican? | combinaciones proyecto–trámite; proyectos con un único trámite | filtros; click opcional |
| Serie | ¿Cuándo se publican? | BOE distintos por periodo | fecha global + granularidad local |
| Resumen de proyectos | ¿Cuáles son? | una fila por proyecto | seleccionar/ir a Explorar |

### Help and tooltips

- cada tarjeta indica que responde a filtros;
- mapa: nombre de territorio, nivel y proyectos distintos;
- barras: decisión, conteo y granularidad vigente; la ayuda aclara que, con
  Todos los trámites, un proyecto puede contribuir a más de una barra;
- serie: periodo y BOE distintos;
- ayuda administrativa: “publicado” no equivale a vigencia jurídica.

### Empty state

Si no hay resultados, KPIs muestran 0 y mapa, gráficos y tabla se sustituyen
por un único mensaje: **No hay proyectos que cumplan todos los filtros.** Se
ofrece limpiar filtros; no se muestran paneles vacíos contradictorios.

## 12. Territorial map

### Definition

- **Título:** Distribución territorial de proyectos.
- **Medida:** `nunique(project_id)` por código territorial, tras deduplicar
  (`project_id`, código).
- **Niveles:** comunidad autónoma, provincia y municipio.
- **Escala:** el mismo contrato debe funcionar con cualquier número de
  proyectos, municipios y años del deployment dataset.
- **Nota obligatoria:** “El mapa representa territorios asociados a los
  proyectos en las publicaciones, no coordenadas exactas de las
  instalaciones.”
- Nunca se denomina densidad ni se representan centroides como plantas.

### Navigation and drill

1. Estado inicial: España / comunidades autónomas.
2. El hover muestra territorio, nivel y proyectos distintos.
3. Seleccionar una CCAA, mediante control REQUIRED o interacción estable,
   permite cambiar a provincias de esa CCAA.
4. Seleccionar una provincia permite cambiar a municipios de esa provincia.
5. Una ruta visible muestra `España > CCAA > Provincia` y el nivel activo.
6. **Volver al nivel anterior** elimina solo la selección territorial más baja;
   **Restablecer territorio** elimina toda la ruta.
7. Cambiar de nivel sin seleccionar territorio no altera el conjunto global.

### Incomplete territorial resolution

- El nivel CCAA agrega cualquier fila con código autonómico, incluida una
  localización más específica.
- El nivel provincia agrega cualquier fila con código provincial, incluida una
  fila municipal.
- El nivel municipio usa solo códigos municipales reales.
- Un proyecto province-only o CCAA-only permanece en KPIs y resultados al
  visualizar un nivel inferior; se informa cuántos proyectos seleccionados no
  tienen resolución suficiente para pintarse en ese nivel.
- Seleccionar un municipio concreto sí restringe a proyectos asociados a ese
  municipio; nunca se fabrican municipios para filas menos precisas.

Hover, nivel visible, drill y retorno son REQUIRED. La selección territorial
debe ser coherente con los filtros; el click-to-cross-filter completo es
OPTIONAL y se elimina si no resulta estable y testeable.

## 13. Geometry requirements

Estado: **EXTERNAL REFERENCE DATA REQUIRED**.

Gate 3 debe investigar y validar una referencia que cumpla:

- polígonos de CCAA, provincias y municipios;
- códigos INE de dos, dos y cinco dígitos conservados como strings;
- fuente oficial o suficientemente autoritativa;
- versión o fecha de referencia reproducible;
- procedencia y licencia documentadas y compatibles con redistribución web;
- geometrías no vacías, válidas y con CRS declarado;
- un código único por feature y relaciones padre coherentes;
- cobertura de todos los códigos INE observados en el Final TFM corpus y
  diferencias frente al Gold desplegado;
- simplificación reproducible que preserve fronteras, códigos y validez;
- tamaño y tiempo de carga razonables para la aplicación pública;
- manifest o declaración que permita verificar bytes/identidad de la versión
  desplegada.

No se selecciona aquí una fuente concreta y no se descargan geometrías. Gate 3
debe fallar de forma cerrada ante códigos duplicados, joins inesperadamente
huérfanos, geometrías inválidas o licencia no apta.

## 14. Administrative situations chart

### Approved default design

El título REQUIRED es **Últimas situaciones publicadas por trámite** y el
default es **Todos los trámites**. El gráfico muestra una barra por situación
publicada:

- con un solo trámite seleccionado, la medida es proyectos distintos y cada
  proyecto aparece como máximo una vez;
- con Todos o varios trámites, la medida semántica es combinaciones distintas
  `project_id × action_type`; un proyecto puede contribuir a varias barras y
  las barras no son categorías exclusivas ni deben sumarse como proyectos.

El subtítulo y el eje cambian explícitamente entre **Proyectos** y
**Combinaciones proyecto–trámite**. No se oculta la granularidad.
Una ayuda breve explica que las barras no son grupos mutuamente exclusivos de
proyectos cuando se muestran todos o varios trámites.

### Temporal interpretation

- Default **Última decisión publicada por trámite**: una fila por
  `project_id × action_type` antes de filtros.
- **Cualquier publicación histórica**: el título cambia a **Situaciones
  publicadas históricamente** y deduplica cada combinación proyecto–trámite–
  decisión para que BOE repetidos no inflen la barra.

Una selección de situación global restringe las barras; una selección de
trámite cambia su grano como se describe. El click de barra es OPTIONAL porque
el mismo efecto siempre está disponible como filtro.

## 15. BOE timeline

- **Título:** Publicaciones BOE a lo largo del tiempo.
- **Medida:** `nunique(boe_id)` por periodo sobre las filas que respaldan la
  selección global.
- **Eje:** `publication_date`.
- **Default:** anual para ofrecer una lectura estable del corpus multianual.
- **Cambio aprobado de granularidad:** anual / trimestral mediante control
  local de selección única.
- **Mensual:** OPTIONAL / POST-TFM; no está requerido ni planificado en agosto.
- **Intervalo:** lo controla exclusivamente el filtro global desde/hasta.

Cambiar granularidad no cambia el conjunto filtrado ni los KPIs. No habrá
brush ni selección directa de fechas en el gráfico durante agosto.

## 16. Explore projects

La vista evoluciona la implementación actual sin cambiar sus reglas:

- sidebar con los mismos filtros globales;
- contador de resultados y resumen de filtros;
- una fila por `project_id`, orden inicial por nombre;
- orden interactivo de tabla sin alterar la selección analítica;
- selección de una única fila para abrir la ficha;
- acción visible **Ver ficha del proyecto**;
- columnas: Proyecto, Tecnología principal, Territorio asociado, Primera
  publicación, Última publicación, Publicaciones BOE, Actuaciones y, cuando
  proceda, Trámites coincidentes.

No muestra columnas NO-GO: promotor, potencia, componentes o relaciones.

## 17. Project detail

La ficha ignora los filtros de búsqueda para recuperar siempre la historia
completa del `project_id` seleccionado.

### Header

- nombre del proyecto;
- **Tecnología principal**;
- `project_id` como referencia secundaria copiable, no como título.

### Summary

- primera publicación;
- última publicación;
- Publicaciones BOE distintas;
- actuaciones administrativas únicas.

### Latest published situations

Sección **Últimas situaciones publicadas por trámite**, una fila por trámite,
con situación y fecha. Nunca se titula “Estado actual”.

### Territory

Sección **Ámbito territorial del proyecto** por municipios, provincias y CCAA.
Los códigos INE son secundarios. La procedencia BOE puede mostrarse bajo
demanda cuando aporte trazabilidad, sin sugerir coordenadas exactas.

### August exclusions

La ficha no incluye promotor, potencia, booleano híbrido, multi-tecnología
exhaustiva, componentes ni relaciones. Se documentan como limitaciones o
extensiones futuras en Metodología, sin crear huecos visuales ni afirmar que un
proyecto carece de esos elementos.

### Chronology and evidence

Cronología completa ordenada determinísticamente por fecha e índices:

- fecha;
- trámite;
- situación publicada;
- indicador de modificación;
- BOE con URL HTML canónica;
- evidencia bajo expander, no abierta por defecto.

## 18. Methodology

Vista breve, enlazada a la documentación en lugar de duplicarla:

- BOE como fuente oficial;
- planta de generación nombrada como raíz de proyecto;
- explicación de última decisión publicada por trámite;
- territorio asociado publicado, no coordenada exacta;
- límites: corpus, ausencia de estado jurídico, potencia/promotor excluidos y
  cobertura no exhaustiva;
- componentes, relaciones y modelado multi-tecnología exhaustivo diferidos;
- distinción entre development corpus, Final TFM corpus y deployment dataset;
- periodo realmente cubierto e identidad/versionado del Gold desplegado en
  lenguaje legible;
- correcciones humanas versionadas y regeneración;
- enlaces a [`USER_GUIDE.md`](USER_GUIDE.md),
  [`APP_DATA_CATALOG.md`](APP_DATA_CATALOG.md) y la
  [declaración del core freeze](freezes/core_data_freeze_2026-08-13.md).

No expone paths locales, hashes completos innecesarios ni instrucciones de
operación del pipeline.

## 19. Local Gold audit

La auditoría existente se conserva sin rediseño:

- controlada por `RENEWABLES_ENABLE_DATA_EXPLORER`;
- `false` por defecto;
- no visible ni enlazada en navegación pública;
- habilitable solo localmente para inspección;
- estrictamente read-only y sobre el Gold validado.

No forma parte del producto público ni de los wireframes de producción.

## 20. Error reporting

### Approved August decision

Usar un enlace **Reportar posible error** mediante correo preformateado
(`mailto`). El destinatario se configura de forma clara y segura durante la
implementación/deployment. No requiere backend, base de datos, autenticación ni
secrets en la aplicación.

El mensaje propone, sin enviar automáticamente:

- `project_id`;
- nombre del proyecto;
- vista y contexto;
- categoría de error;
- descripción acotada;
- BOE o entidad afectada, si aplica;
- ID de entidad, si aplica;
- valor esperado/sugerido opcional.

El correo del remitente actúa como contacto opcional. La UI debe pedir que no
se incluyan datos personales o sensibles y advertir que el reporte no modifica
el dataset. El canal debe probarse en el entorno desplegado y ofrecer una
dirección visible como fallback si el cliente de correo no se abre.

### Alternatives evaluated

| Opción | August decision | Motivo |
| --- | --- | --- |
| correo preformateado | APPROVED | mínimo, aislado y sin persistencia propia |
| formulario externo | POST-TFM | añade proveedor, privacidad, spam y disponibilidad |
| GitHub issue/form | REJECTED for public default | exige cuenta o expone públicamente contexto del reporte |
| almacenamiento propio | POST-TFM | requiere backend, seguridad, retención y operación |

### Post-TFM

Un formulario separado con validación, aviso de privacidad, protección anti-
spam, ticketing y trazabilidad. Nunca escribirá Gold ni aprobará correcciones.

## 21. Correction workflow boundary

```text
Usuario público
→ reporta un posible error

Administradora
→ revisa fuente y evidencia fuera de la app pública

VS Code + Codex
→ prepara el cambio o corrección versionada

Tests y revisión humana
→ validan la decisión

Pipeline
→ regenera Silver y Gold en un snapshot nuevo

Nueva versión validada
→ despliegue explícito
```

No se diseña una aplicación administrativa. Aprobación, autenticación,
corrección asistida y ejecución desde UI son POST-TFM.

## 22. Navigation

### Option A — Keep current query-param navigation

Pros: ya está implementada, probada, admite deep links de ficha, conserva el
explorador oculto y requiere cambios incrementales. Contras: hay que mantener
manualmente vistas, parámetros y estado compartido.

### Option B — `st.Page` + `st.navigation`

Pros: estructura multipágina nativa y mantenible a largo plazo. Contras:
refactor de entrada, páginas, tests, query params y estado en un periodo con
freeze cercano; la Ficha sigue necesitando navegación contextual.

### Approved decision

**KEEP CURRENT NAVIGATION FOR AUGUST.** Añadir `view=resumen` y conservar
`explorar`, `ficha`, `metodologia` y la auditoría local condicionada. Migrar a
`st.Page`/`st.navigation` es OPTIONAL/POST-TFM después de la entrega, no un
objetivo de modernización urgente.

## 23. Visual principles

- `layout="wide"` y desktop como prioridad;
- sidebar solo para navegación/filtros/metadatos breves;
- dashboard-first: mapa protagonista, dos KPIs y pocos gráficos;
- jerarquía por títulos, espacios y contenedores nativos con borde;
- fila KPI responsive; máximo dos columnas para gráficos principales;
- color con significado estable y nunca como única señal;
- etiquetas en sentence case y ayuda metodológica junto al objeto;
- tablas para exploración y cronología, no para sustituir gráficos;
- evidencia y procedencia bajo demanda mediante expanders;
- controles con etiquetas accesibles, estados de foco y alternativa textual;
- nada de CSS o HTML ad hoc salvo defecto demostrado;
- mobile no es prioridad si compromete claridad desktop, pero no se diseñan
  filas de más de cuatro columnas ni anchos rígidos innecesarios.

Los tabs no son navegación principal. Pueden separar contenido homogéneo solo
si no ocultan computación costosa. Los containers agrupan tarjetas; columns se
reservan para proporciones concretas; expanders contienen evidencia/ayuda.

## 24. Official UI terminology

| Concepto técnico | Etiqueta aprobada |
| --- | --- |
| Project | Proyecto |
| Technology | Tecnología principal |
| Decision | Situación publicada |
| Action type | Trámite |
| Latest | Última decisión publicada por trámite |
| Territory | Territorio asociado |
| Map | Distribución territorial de proyectos |
| BOE count | Publicaciones BOE |
| Project count | Proyectos |
| Timeline | Publicaciones BOE a lo largo del tiempo |
| Modification | Modificación |
| Evidence | Evidencia de la publicación |

No usar: **estado actual**, **densidad**, **ubicación exacta**, **producción
energética**, **potencia total**, ni **Híbrido: No** inferido de una ausencia.

## 25. Wireframes

### Dashboard — Resumen

```text
┌─────────────────────────────────────────────────────────────────────┐
│ HEADER — “¿Qué está ocurriendo?”                                   │
│ Contexto: actos publicados; no estado jurídico                     │
├───────────────┬─────────────────────────────────────────────────────┤
│ FILTERS       │ ACTIVE FILTERS + LIMPIAR                           │
│ Pregunta:     ├─────────────────────┬───────────────────────────────┤
│ ¿qué conjunto?│ KPI PROYECTOS       │ KPI PUBLICACIONES BOE         │
│ Dimensiones:  │ Medida: n proyectos │ Medida: n BOE soporte         │
│ nombre, tech, │ Interacción: global │ Interacción: global           │
│ territorio,   ├───────────────────────────────────┬─────────────────┤
│ admin, fecha  │ MAPA                              │ SITUACIONES     │
│ Interacción:  │ Pregunta: ¿dónde?                 │ ¿qué se publicó?│
│ explícita     │ Métrica: proyectos/territorio     │ Grano visible   │
│               │ Nivel/drill + click opcional      │ click opcional  │
│               ├───────────────────────────────────┴─────────────────┤
│               │ BOE OVER TIME                                      │
│               │ Pregunta: ¿cuándo? · BOE distintos · anual/trim.   │
│               ├─────────────────────────────────────────────────────┤
│               │ PROJECT SUMMARY / IR A EXPLORAR                    │
│               │ Una fila/proyecto · selección abre ficha           │
└───────────────┴─────────────────────────────────────────────────────┘
```

### Explore projects

```text
┌─────────────────────────────────────────────────────────────────────┐
│ EXPLORAR PROYECTOS                                                  │
├───────────────┬─────────────────────────────────────────────────────┤
│ FILTERS       │ N RESULTADOS · ACTIVE FILTERS · LIMPIAR            │
│ globales      ├─────────────────────────────────────────────────────┤
│ mismos que    │ TABLA — una fila por proyecto                       │
│ Resumen       │ Proyecto | Tecnología | Territorio | Fechas | BOE  │
│               │ Orden de tabla; selección única                     │
│               ├─────────────────────────────────────────────────────┤
│               │ [VER FICHA]                                        │
│               │ Interacción: project_id exacto → vista Ficha        │
└───────────────┴─────────────────────────────────────────────────────┘
```

### Project detail

```text
┌─────────────────────────────────────────────────────────────────────┐
│ PROJECT HEADER — nombre · Tecnología principal · project_id         │
├─────────────────────────────────────────────────────────────────────┤
│ RESUMEN — primera/última publicación · BOE · actuaciones            │
├───────────────────────────────┬─────────────────────────────────────┤
│ ÚLTIMAS SITUACIONES/TRÁMITE   │ TERRITORIO ASOCIADO                 │
│ Pregunta: ¿qué se publicó?    │ municipios · provincias · CCAA      │
├───────────────────────────────┴─────────────────────────────────────┤
│ CRONOLOGÍA COMPLETA                                                  │
│ fecha · trámite · situación · modificación · BOE                    │
│ [expandir evidencia de la publicación]                              │
└─────────────────────────────────────────────────────────────────────┘
```

Las regiones condicionales no aparecen como cajas vacías si Gate 3 no crea sus
contratos.

## 26. Empty and error states

| Estado | Mensaje/acción pública |
| --- | --- |
| filtros sin resultados | “No hay proyectos que cumplan todos los filtros.” + Limpiar filtros |
| mapa sin datos en nivel | “Los proyectos seleccionados no tienen resolución suficiente para este nivel.” Mantener KPI/tabla y permitir volver |
| proyecto inexistente | “No se ha encontrado el proyecto solicitado.” + Volver a Explorar |
| componentes/relaciones diferidos | no crear secciones en la ficha; explicar la limitación en Metodología y nunca afirmar ausencia material |
| dataset Gold inválido | “No se puede cargar la versión validada de los datos.” Detener contenido analítico |
| geometría ausente/inválida | “El mapa no está disponible en esta versión.” Mantener resto solo si Gold sigue válido |
| reporting no disponible | mostrar dirección/canal alternativo aprobado; no perder el resto de la app |

La UI registra el detalle técnico en servidor cuando corresponda, pero no
muestra tracebacks, paths locales, secrets ni hashes internos innecesarios.

## 27. Gate 3 data dependencies

### Already available

- cuatro tablas Gold validadas;
- loader contractual y downstream ID esperado;
- consultas de catálogo, latest/historical, same-row, any/all, detalle,
  cronología, localizaciones, linaje y URL BOE;
- navegación actual y auditoría local desactivada por defecto.

Desbloquean ambos KPIs, barras, serie, Explorar, Ficha y Metodología.

### External reference — REQUIRED

Geometrías administrativas versionadas. Desbloquean el mapa básico, que es
MUST SHIP. Gate 3 debe investigar fuente, licencia, join, simplificación,
integridad y tamaño antes de implementar.

### Deferred Gold concepts

| Candidato | Requisito visual que desbloquea | ¿REQUIRED? | Recomendación Gate 2 |
| --- | --- | --- | --- |
| `project_components` | futura extensión de ficha | No | POST-TFM / APPROVED CONCEPT BUT DEFERRED |
| `project_relationships` | futura extensión de ficha | No | POST-TFM / APPROVED CONCEPT BUT DEFERRED |

Gate 1 autorizó conceptualmente su modelado, pero Gate 2 los elimina del alcance
de agosto. No se diseñan ni implementan antes del TFM y la ficha final no
depende de ellos.

## 28. Acceptance criteria

### Dashboard

- los dos KPIs responden a todos los filtros y conservan su granularidad;
- Publicaciones BOE cuenta solo filas de soporte de proyectos elegibles;
- mapa deduplica proyecto–código y mantiene menos-resueltos fuera del polígono,
  no fuera del conjunto;
- barras latest/historical declaran y respetan su grano;
- serie temporal cuenta BOE únicos y coincide con el KPI para el intervalo;
- ningún join o filtro duplica proyectos en tabla o KPI;
- estados vacíos permiten recuperar la selección.

### Explore

- una fila por `project_id`;
- filtros OR/AND, same-row y any/all coherentes con las consultas validadas;
- tabla ordenable y selección única;
- navegación por ID exacto a la ficha;
- no muestra promotor ni potencia.

### Detail

- fechas y conteos coinciden con Gold;
- últimas situaciones tienen una fila por trámite;
- cronología completa no hereda filtros del buscador;
- cada BOE usa su ID, fecha y URL canónica correctos;
- territorio conserva todos los niveles disponibles sin inventar municipios;
- evidencia está bajo demanda y las secciones no implementadas no afirman
  ausencia;
- no aparecen promotor, potencia, booleano híbrido, multi-tecnología
  exhaustiva, componentes ni relaciones.

### Security and read-only boundary

- solo se carga Gold contractual con downstream ID esperado;
- Streamlit no lee Silver, pipeline, BOE ni modelo;
- explorador público desactivado y no enlazado;
- no hay edición, descargas derivadas ni correcciones desde la app;
- no se filtran paths, secrets, tracebacks o hashes innecesarios;
- reporting está aislado y no modifica datos.

### Deployment

- la aceptación no compara cardinalidades con el development corpus;
- manifest, downstream ID final, tablas, schemas, integridad, PK/FK y dominios
  corresponden al deployment dataset;
- artefacto Gold y geometrías están versionados/identificados y todos los
  códigos INE observados están cubiertos;
- downstream ID se verifica antes de renderizar;
- smoke tests cubren carga, filtros, charts, mapa, ficha, navegación, URLs BOE
  y reporte;
- tiempos de carga, filtros, mapa y charts, además del uso de memoria, son
  aceptables sobre el Final TFM corpus;
- existe procedimiento reproducible de despliegue y rollback;
- la versión pública conserva el explorador desactivado.

### Final-corpus operational revalidation

Antes de publicar se repiten row counts, domain values, null coverage, PK/FK,
grouping, project IDs, locations, latest actions, mappings, URLs, geometrías y
performance. Las decisiones estructurales de Gate 1 permanecen vigentes: no se
reabren automáticamente promotor, potencia ni hibridación exhaustiva por crecer
el corpus. Los tests de regresión del development corpus siguen siendo una
garantía separada.

La validación de performance mide carga de Gold, filtros, mapa, charts, memoria
y efecto de `st.cache_data`. No se introduce base de datos, DuckDB ni una
arquitectura de paginación sin evidencia de que pandas en memoria sea
insuficiente.

Estos son criterios funcionales; los tests concretos se diseñan durante cada
bloque de implementación.

## 29. Implementation priority after Gate 2

1. **Final corpus ingestion audit:** inspeccionar CLI/código en modo read-only y
   decidir la vía reproducible.
2. **Final corpus preflight:** medir alcance, coste, llamadas, espacio y tiempo.
3. **Final multi-year corpus:** construir el nuevo corpus.
4. **Review/corrections:** revisar y aplicar únicamente decisiones versionadas.
5. **Silver/Gold final:** materializar y validar sin alterar el core freeze.
6. **Geometrías:** investigar, aprobar, versionar y validar la referencia sobre
   todos los códigos INE del corpus final.
7. **Consultas y métricas:** definir funciones puras para KPIs, barras, serie y
   agregación territorial sin cambiar Gold.
8. **Dashboard:** añadir Resumen, estado global y filtros compartidos.
9. **Mapa:** nivel, drill explícito, menos-resueltos y estados de error.
10. **Gráficos:** situaciones y serie temporal.
11. **Explorar/Ficha/Metodología:** aplicar jerarquía visual sin cambiar
   semántica y sin secciones de componentes o relaciones.
12. **Reporting mínimo:** mailto aprobado, privacidad y aislamiento.
13. **Validación visual, seguridad y suite:** cerrar functional freeze.
14. **Deployment:** deployment dataset versionado, smoke test y rollback.
15. **Holdout/documentación:** cerrar la evidencia final.

No se inicia un bloque sin cerrar el gate humano anterior. El data-model freeze
del 24 de agosto y el functional freeze del 27 siguen vigentes.

## 30. Scope cuts

### MUST SHIP

- Final TFM corpus correcto, reproducible, revisado y validado;
- deployment dataset Gold con identidad y rollback propios;
- dos KPIs seguros;
- mapa administrativo básico con selección explícita de nivel/territorio;
- gráfico de últimas situaciones publicadas;
- serie temporal BOE;
- Explorar y Ficha con cronología/evidencia;
- Metodología;
- reporting mínimo aislado;
- despliegue read-only;
- tests, seguridad, reproducibilidad y documentación.

### CUT FIRST

1. `project_relationships`;
2. `project_components` y cualquier presentación enriquecida;
3. click de barras como filtro;
4. click de mapa y drill gráfico avanzado, conservando controles explícitos;
5. refinamientos visuales no esenciales;
6. reporting persistente o formulario complejo, conservando canal mínimo.

Si el Final Corpus Build consume más tiempo del previsto, se priorizan, en este
orden, corpus correcto y reproducible; extracción/revisión; Gold final;
dashboard MUST SHIP; deployment; y holdout/documentación. Nunca se recortan la
corrección de defectos materiales, tests, seguridad, despliegue,
reproducibilidad o documentación.

## 31. Human decisions approved

Decisiones humanas aprobadas el **2026-08-20**:

1. dos KPIs y ningún KPI 3;
2. mapa a tres niveles como MUST SHIP;
3. gráfico de situaciones con **Todos los trámites** por defecto y grano
   proyecto–trámite visible;
4. cross-filter REQUIRED limitado a filtros explícitos; clicks de mapa/barras
   opcionales y sin brush temporal;
5. **KEEP CURRENT NAVIGATION** durante agosto;
6. `project_components` diferido a POST-TFM;
7. `project_relationships` diferido a POST-TFM;
8. correo preformateado como reporting mínimo;
9. timeline anual por defecto, trimestral opcional y sin brush;
10. contenido MUST SHIP de Resumen, Explorar, Ficha y Metodología cerrado.

No quedan decisiones materiales de producto abiertas. Colores exactos,
microcopy menor y spacing se resuelven durante implementación sin reabrir el
gate.

## 32. Gate 2 decision

```text
PRODUCT GATE PASSED
```

**Human Gate 2 decision date:** 2026-08-20.

La especificación técnica está cerrada, no contradice Gate 1 y permanece
independiente del dataset. El design freeze entra en vigor después del commit
de Gate 2 con fecha 2026-08-20: no se añaden páginas, KPIs, gráficos, datos de
ficha ni funciones de reporting salvo defecto material aprobado humanamente.

La siguiente acción REQUIRED es **FINAL CORPUS INGESTION AUDIT**. No se inicia
Streamlit, el mapa ni Gold adicional antes de completar esa auditoría y el
preflight posterior.
