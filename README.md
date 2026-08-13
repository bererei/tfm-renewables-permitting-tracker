# tfm-renewables-permitting-tracker
Master Final Project focused on building an automated renewable energy permitting tracker. The project uses NLP, information extraction and entity resolution to reconstruct the administrative lifecycle of renewable energy projects from official public records (BOE, Boletín Oficial del Estado, España).


Datos de localizaciones INE: https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177031&menu=ultiDatos&idp=1254734710990

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
regenerables. El run recanonicalizado y corregido final sigue pendiente; el
freeze de reemplazo aún no está cerrado. Una interfaz de revisión en Streamlit
es trabajo posterior.

Las nuevas llamadas al modelo requieren `--execute-model`; un cambio semántico
INE exige confirmación explícita antes del rebuild. Usa `--dry-run` para
inspeccionar el plan sin red, modelo, publicación ni downstream.


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
