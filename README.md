# tfm-renewables-permitting-tracker
Master Final Project focused on building an automated renewable energy permitting tracker. The project uses NLP, information extraction and entity resolution to reconstruct the administrative lifecycle of renewable energy projects from official public records (BOE, Boletín Oficial del Estado, España).

## Estado de la distribución pública

Este repositorio contiene la distribución pública preparada para la versión
académica final **`v1.0.0`** del TFM. Su rama pública principal es **`main`**.
La tag y la release `v1.0.0` todavía no existen; se crearán tras la revisión y
el primer commit público. El remoto previsto es
<https://github.com/bererei/tfm-renewables-permitting-tracker>, que tampoco se
presenta aquí como disponible hasta su creación.

La memoria describe conceptualmente `v1.0.0` y quedará congelada con esa
versión. Evoluciones posteriores podrán publicarse como `v1.1.0`, `v2.0.0` u
otras versiones sin alterar la memoria académica.


Datos de localizaciones INE: https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177031&menu=ultiDatos&idp=1254734710990

## Instalación y tests

Requiere Python **3.14** y [uv](https://docs.astral.sh/uv/). Desde la raíz del
checkout, instala las dependencias de ejecución fijadas en `uv.lock`:

```bash
uv sync --locked
```

Para desarrollo y testing, instala también el extra `dev` existente
(`ipykernel` y `pytest`) y ejecuta la suite:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest --version
uv run --locked --extra dev pytest
```

`--locked` comprueba que el manifiesto y el lockfile coinciden. Pytest se instala
en `.venv` desde las dependencias declaradas. Esta mejora del entorno de
desarrollo es posterior a la evaluación final del TFM; la trazabilidad y los
tests focales se detallan en [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).
El sistema evaluado permanece identificado por el ref privado histórico
`tfm-final` y su commit científico; estos identificadores no pertenecen a la
historia Git pública ni son resolubles desde ella. Python 3.14 corresponde
únicamente a la versión posterior de entrega y futuro despliegue.

## Pipeline ejecutable

La entrada operativa no requiere notebooks:

```bash
python -m renewables_permitting.pipeline --help
python -m renewables_permitting.pipeline <command> --help
```

`source` crea un snapshot documental run-scoped para un rango BOE y `run`
coordina el flujo completo desde ese origen o desde `--documents`. `extract` y
`silver` permiten reanudar por etapas. `build-reference-data` crea una referencia
INE candidata sin ejecutar downstream; `downstream` reutiliza Silver sin volver
a ejecutar la extracción, y `refresh-reference-data` compara referencias antes
de reconstruir el histórico. `recanonicalize` valida un freeze histórico
aprobado y reaplica únicamente la política determinista sobre sus payloads
precanónicos, conservando el linaje y sin llamar al modelo.

El refinamiento determinista de decisiones sustantivas IDAA está implementado.
La extracción canónica permanece inmutable: `silver --corrections` puede aplicar
el registro versionado de cinco exclusiones históricas antes del flattening y
publica su auditoría junto a Silver, de modo que Silver y Gold son
regenerables.

## Estado actual

El core data freeze fue validado el **2026-08-13** sobre 140 documentos BOE:
116 proyectos de generación, 165 actuaciones administrativas y 169 eventos de
proyecto. La declaración reproducible y sus identidades están en
[`docs/freezes/core_data_freeze_2026-08-13.md`](docs/freezes/core_data_freeze_2026-08-13.md).
La extensión Gold aditiva `project_locations` está materializada y validada
junto con `project_location_sources`, que conserva el linaje de cada territorio
hasta la mención, el evento y el BOE fuente. El producto final W14 usa un Gold
validado separado con 104 documentos analizados, 80 BOE relevantes y 86
proyectos agrupados en
`data/gold/final-w14-corpus-20220101-20260820-v2-316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86`,
con downstream ID
`316008e9bfce550c651d4f6377090243a180c6b5192666327fc1ba2ff8eeef86`. La aplicación
read-only de Streamlit consume exclusivamente sus cuatro tablas Gold:
`projects`, `project_events`, `project_locations` y
`project_location_sources`.

La interfaz utilizará **“Territorio”** como filtro y **“Ámbito territorial del
proyecto”** en la ficha. Nota metodológica aprobada:

> Incluye los territorios asociados en las publicaciones a la planta de
> generación o a otros componentes del proyecto, como sistemas de
> almacenamiento o infraestructuras de evacuación. Las publicaciones no
> siempre permiten determinar a qué componente concreto corresponde cada
> territorio.

Las nuevas llamadas al modelo requieren `--execute-model`; un cambio semántico
INE exige confirmación explícita antes del rebuild. Usa `--dry-run` para
inspeccionar el plan sin red, modelo, publicación ni downstream.

## Aplicación Streamlit local y preparada para despliegue

La aplicación de solo lectura fue desarrollada y validada localmente. Esta
distribución queda preparada para un futuro despliegue en Streamlit Community
Cloud desde `main`, con `streamlit_app.py`, Python 3.14 y las dependencias
fijadas en `uv.lock`; actualmente no se afirma que exista un despliegue público
operativo. Este runtime de entrega es posterior a la evaluación. El sistema
evaluado se identifica mediante el commit privado histórico
`282de815bea4e248bdcba2c655e3ee078cb58a49`, no resoluble desde este
repositorio público.

Ejecuta el MVP read-only desde la raíz del repositorio:

```bash
uv run streamlit run streamlit_app.py
```

La aplicación utiliza por defecto el Gold final W14 validado. El operador
puede configurar su ubicación e identidad esperada sin exponer paths en la UI:

```bash
RENEWABLES_GOLD_DIR=/path/to/gold \
RENEWABLES_EXPECTED_DOWNSTREAM_ID=<downstream-id> \
uv run streamlit run streamlit_app.py
```

El paquete Gold mínimo está versionado, por lo que un clon limpio puede iniciar
la aplicación sin `runs/`, artefactos de evaluación ni secrets obligatorios.

El MVP no escribe en Gold ni ejecuta el pipeline. El flujo administrativo de
correcciones sigue fuera de la aplicación de consulta.
El reporte mínimo de posibles errores abre un correo local y no persiste datos.
Para habilitarlo sin hardcodear una dirección:

```bash
RENEWABLES_REPORT_EMAIL="<CORREO_DE_REVISION>" \
uv run streamlit run streamlit_app.py
```

El resumen incluye dos KPIs en cards, mapa administrativo Folium/Leaflet a tres
niveles con geometría local IGN/CNIG y contexto de países Natural Earth local,
sin tiles externos ni API key, dos
gráficos temporales en paralelo, gráfico administrativo y el catálogo completo.
Los gráficos y el mapa actúan como filtros globales cuando representan una
dimensión filtrable. El catálogo mantiene una fila por proyecto, permite elegir
columnas visibles, filtrar mediante celdas de tecnología o territorio y abrir
la ficha desde una fila o la celda Proyecto. El control de reporte está justo
debajo de Metodología en la barra lateral y nunca modifica Gold. La ficha usa
mapa, resumen documental y cronología agrupada por
publicación. La procedencia cartográfica, el alcance del producto y la operación
completa se documentan en [`docs/APP_PRODUCT_SPEC.md`](docs/APP_PRODUCT_SPEC.md),
[`docs/STREAMLIT_CODE_GUIDE.md`](docs/STREAMLIT_CODE_GUIDE.md) y
[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

El explorador técnico de las tablas Gold está desactivado por defecto. Para
habilitarlo expresamente en una sesión local:

```bash
RENEWABLES_ENABLE_DATA_EXPLORER=true \
uv run streamlit run streamlit_app.py
```


## Versión validada del pipeline de extracción

La versión de referencia actualmente validada del subsistema de extracción del BOE es:

```text
extraction-v25.2
```

Esta versión marca el estado del pipeline tras la migración de la lógica de extracción desde el notebook a `src/renewables_permitting/extraction`.

La validación incluye:

* ejecución completa del notebook operativo sin efectos cuando los procesos de extracción están desactivados;
* construcción diferida del agente únicamente al activar el piloto o la extracción de producción;
* 443 pruebas automatizadas superadas;
* validación offline de 100 documentos;
* 100 hashes documentales coincidentes;
* canonicalización e idempotencia verificadas;
* 13 tablas normalizadas sin referencias huérfanas, duplicados estructurales ni identificadores obligatorios nulos;
* coincidencia exacta de las huellas SHA-256 de las extracciones y de las tablas de referencia.

Notebook de orquestación y auditoría, no requerido por la CLI:

```text
notebooks/07_extraccion_ia_v25_2.ipynb
```

El notebook histórico previo ya no forma parte del árbol activo. Sus garantías
relevantes se verifican directamente sobre `src/renewables_permitting/extraction`
mediante la suite `tests/extraction`, sin usar el notebook retirado como fixture.

`extraction-v25.2` es una etiqueta histórica del repositorio privado de
desarrollo, no un ref de esta nueva historia pública. El código de extracción
incluido se consulta directamente bajo
`src/renewables_permitting/extraction/`.

## Estructura esencial

- `src/renewables_permitting/`: pipeline, extracción, normalización y consultas.
- `evaluation/`: contratos y código del evaluador final.
- `streamlit_app.py`: punto de entrada de la aplicación local.
- `data/gold/`: paquete Gold contractual distribuido con la aplicación.
- `data/bronze/localizaciones_ine/`: dos referencias territoriales públicas.
- `docs/`: documentación técnica, evaluación y fuentes de la memoria.
- `tests/`: pruebas automatizadas.

## Evaluación y memoria del TFM

El holdout final contiene 48 publicaciones. Sus métricas, denominadores,
identidades y límites se documentan en los
[resultados finales V2](docs/evaluation/FINAL_HOLDOUT_V2_RESULTS.md). El código
del sistema evaluado y el evaluador conservan identificadores privados
históricos de provenance, descritos en [la documentación](docs/README.md); no
son commits de este repositorio público.

Las fuentes canónicas de la memoria están en `docs/tfm_report/`. Se compilan
sin firma privada siguiendo
[`docs/tfm_report/COMPILACION.md`](docs/tfm_report/COMPILACION.md). El PDF
histórico no forma parte de la distribución y el PDF público se generará para
la release `v1.0.0`.

Los directorios `runs/` no se distribuyen. Las rutas `runs/...` que aparecen en
informes científicos son identificadores históricos internos, no enlaces ni
dependencias necesarias para ejecutar la aplicación.

## Limitaciones esenciales

- El corpus tiene un alcance temporal y documental definido; no representa
  todo el BOE ni un registro administrativo completo.
- La interfaz muestra actos publicados y no certifica el estado jurídico o
  físico actual de una instalación.
- Las métricas del holdout son específicas de las tareas y denominadores
  publicados; no constituyen una métrica global del sistema.
- La aplicación distribuida es de consulta: no ejecuta extracción, no llama al
  modelo y no modifica Gold.
