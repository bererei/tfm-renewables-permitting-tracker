# tfm-renewables-permitting-tracker
Master Final Project focused on building an automated renewable energy permitting tracker. The project uses NLP, information extraction and entity resolution to reconstruct the administrative lifecycle of renewable energy projects from official public records (BOE, Boletín Oficial del Estado, España).


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
El sistema evaluado permanece congelado en `tfm-final`; Python 3.14 corresponde
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
`runs/final-w14-corpus-20220101-20260820-v2/downstream/gold`, con downstream ID
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

## Aplicación Streamlit local

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

El MVP no escribe en Gold ni ejecuta el pipeline. El despliegue público y el
flujo administrativo de correcciones siguen fuera de la aplicación pública.
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
publicación. La procedencia cartográfica y la operación completa se documentan en
[`docs/FINAL_STREAMLIT_PRODUCT_ALIGNMENT.md`](docs/FINAL_STREAMLIT_PRODUCT_ALIGNMENT.md)
y [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).

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

Para consultar el código correspondiente a esta versión:

```bash
git switch --detach extraction-v25.2
```

Para regresar posteriormente a la rama de trabajo:

```bash
git switch tfm-final
```
