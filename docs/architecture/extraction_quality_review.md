# Selección, revisión y calidad de la extracción

## Estados y selección vigente

Una salida válida cumple el contrato Pydantic; esto no implica que esté
clasificada ni que sea vigente. La selección automática exige conjuntamente
`extraction_status="ok"`, `document_validation_status="passed"` y
`classification_status="classified"`, además de la fuente, configuración y
versión de validación vigentes. Las revisiones manuales conservan su precedencia
actual.

Una salida válida con `classification_status="uncertain"` permanece en el
histórico de intentos, pero no cuenta como validada automáticamente ni se
selecciona por sí misma. Su último intento entra en revisión y conserva el JSON,
la razón de clasificación y el linaje disponibles. Una revisión manual validada
puede resolverla.

## Corpus objetivo y cola

`source_df` representa el corpus objetivo completo. Sus identificadores BOE y
hashes documentales son obligatorios, no nulos y los BOE no pueden repetirse.
Los intentos de otra fuente, configuración, versión o corpus se conservan en el
histórico, pero no cuentan para la selección, la cola ni las métricas de este
corpus. Un BOE objetivo sin intento vigente genera seguimiento sin inventar
`attempt_id` ni datos de intento. Como todavía no existe una extracción que
corregir, esa entrada no puede convertirse en un fichero de revisión manual:
el documento debe intentarse primero.

La política declarada en `review.py` es la fuente única de códigos, severidad y
explicación humana. Los códigos vigentes son:

- `classification_uncertain`: salida válida cuya clasificación necesita
  decisión manual;
- `source_not_attempted`: documento objetivo sin intento vigente;
- `extraction_error`: error de extracción o estado no elegible;
- `document_validation_failed`: intento que no superó la validación documental.

Todos son bloqueantes en esta fase. Para un intento con varios estados
problemáticos se emite un único motivo: el fallo documental prevalece sobre el
error genérico, y la incertidumbre solo se usa para intentos correctos que sí
superaron la validación. La cola se ordena por BOE y su identificador estable
incluye BOE, hash, intento —vacío si no existe— y código.

## Métricas y estado de calidad

Se reutilizan nombres históricos equivalentes para no duplicar semántica:
`n_source_documents` es el número de documentos objetivo,
`n_latest_attempts` el número intentado y `n_review_required` el número de BOE
con revisión bloqueante pendiente. `n_unattempted`, `coverage_rate`,
`n_classified` y `n_uncertain` completan la observabilidad.

`n_classified` y `n_uncertain` describen los últimos intentos que coinciden con
el BOE, hash, configuración y versión documental del corpus actual. No son
necesariamente las extracciones vigentes: pueden incluir el resultado de un
intento posterior que no haya terminado seleccionado. `n_auto_validated`
cuenta únicamente selecciones automáticas vigentes no sustituidas por una
decisión manual, mientras `n_manually_validated` cuenta decisiones manuales
vigentes. Ambas categorías son disjuntas; un rechazo manual tampoco cuenta
como automático ni como validación efectiva.

Una extracción automática válida anterior puede seguir vigente cuando el
último intento falla o queda `uncertain`. En ese caso coexisten la extracción
vigente y la incidencia bloqueante del último intento: las tasas reflejan el
resultado todavía disponible, pero el estado permanece `degraded` mientras la
incidencia siga pendiente.

Para un corpus no vacío:

```text
coverage_rate = n_latest_attempts / n_source_documents
automatic_validation_rate = n_auto_validated / n_source_documents
effective_validation_rate = extracciones auto o manualmente validadas
                            / n_source_documents
```

El umbral almacenado como `minimum_auto_validation_rate` se mantiene por
compatibilidad, pero el estado global lo aplica a `effective_validation_rate`.
`healthy` requiere cobertura completa, cero documentos no intentados, tasa
efectiva igual o superior al umbral y cero revisiones bloqueantes pendientes.
En otro caso el estado es `degraded`.

Para un corpus objetivo vacío, cobertura y ambas tasas valen `1.0`, los conteos
valen cero y el estado puede ser `healthy`. Esto lo distingue de un corpus no
vacío con cero intentos, cuya cobertura y tasas valen `0.0` y cuyo estado es
`degraded`.

## Compatibilidad histórica

Al anexar una métrica al Parquet histórico, las filas del esquema anterior se
normalizan incorporando `n_unattempted`, `coverage_rate`, `n_classified` y
`n_uncertain` con valores nulos. No se recalculan ni reciben backfill
automático, porque ya no se dispone necesariamente del corpus y las decisiones
vigentes de aquella ejecución.

La cola anterior no se conserva como historial ni se migra. Para obtener los
códigos, severidades y explicaciones actuales debe regenerarse desde el corpus,
los intentos y las revisiones vigentes.

## Persistencia coordinada

El cierre escribe, en este orden:

```text
extracciones vigentes
→ cola
→ métrica agregada
```

Cada fichero se publica atómicamente de forma individual, pero no existe una
transacción conjunta. Un fallo intermedio puede dejar artefactos pertenecientes
a ejecuciones diferentes. Un snapshot coordinado y el rollback conjunto
permanecen fuera del alcance actual.

## Límites actuales

Siguen pendientes los warnings para extracciones válidas pero sospechosas, la
trazabilidad reforzada de revisiones manuales, el tratamiento administrativo de
documentos no intentados más allá de exigir que se procesen, y la prioridad y
asignación de revisores. Esta política tampoco añade nuevos estados ni cambia
el contrato Pydantic, las etiquetas del piloto, el flattening o la
materialización Silver.
