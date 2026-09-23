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
- `document_validation_failed`: intento que no superó la validación documental;
- `possible_historical_antecedent`: una o más actuaciones de una extracción
  válida contienen señales documentales de que podrían proceder de antecedentes
  y requieren decisión humana.

Todos son bloqueantes en esta fase. Para un intento con varios estados
problemáticos se emite un único motivo: el fallo documental prevalece sobre el
error genérico, y la incertidumbre solo se usa para intentos correctos que sí
superaron la validación. La cola se ordena por BOE y su identificador estable
incluye BOE, hash, intento —vacío si no existe— y código.

## Safeguard de posibles antecedentes históricos

`possible_historical_antecedent` es un hallazgo de revisión, no una
clasificación automática `ANTECEDENT/CURRENT` ni una corrección. El detector
puro se ejecuta sobre la extracción canónica que ya superó la validación
documental y devuelve diagnósticos; no modifica, filtra, rechaza ni elimina
`administrative_actions`. La selección vigente conserva el mismo JSON. La
severidad `blocking` impide que un snapshot con un caso pendiente pase
silenciosamente a Silver, pero no tiene semántica de exclusión de datos.

Cada candidato exige conjuntamente:

1. al menos una señal temporal o estructural fuerte: ubicación en
   `Antecedentes de hecho`, referencia explícita a una resolución o publicación
   BOE anterior, o fecha anterior ligada sintácticamente a redacción
   retrospectiva;
2. al menos una señal contextual independiente: evidencia anterior al bloque
   resolutivo, separación explícita entre antecedentes y fundamentos/dispositivo
   o, en anuncios sin dispositivo, un acto actual distinto declarado por el
   título.

Un keyword, una fecha aislada, `Fundamentos de Derecho`, la ausencia en el
título o el tipo de actuación no bastan por sí solos. La evidencia se localiza
con normalización determinista de Unicode y espacios, conservando el texto
extraído original, posiciones, sección y un pasaje fuente. Los fragmentos
`[...]` solo se usan cuando todos pueden ordenarse en un intervalo acotado. Si
la cita no se localiza, tiene demasiadas posiciones o también aparece en el
dispositivo actual, el detector no emite una conclusión histórica.

La cola mantiene una fila documental por BOE y agrega los diagnósticos de cada
actuación en `validation_issues_json`, con `administrative_action_id`, tipo,
decisión, huella de evidencia, señales, posiciones, sección, fuente y versión
del detector. `source_attempt_id`, hash documental, configuración y JSON
propuesto conservan el linaje normal de la revisión.

La detección y la resolución son pasos separados y admiten dos resultados
humanos distintos. `ANTECEDENT` coincide exactamente por BOE,
`administrative_action_id`, tipo, decisión y SHA-256 de evidencia con una
corrección aprobada; solo esa corrección modifica la copia usada para Silver.
`CURRENT` coincide además por hash del documento, código de motivo y versión
del detector con una decisión aprobada en
`config/manual_reviews/historical_antecedent_reviews.csv`; no es una corrección
y deja la extracción semánticamente idéntica. Si ambos resultados intentan
resolver el mismo finding, la reconciliación falla por contradicción.
Una `manual_review` genérica marcada `manually_validated` no suprime estos
findings por BOE; un rechazo documental sí los cierra porque ninguna actuación
de ese documento entra en la selección para Silver.

La reconciliación se realiza por actuación antes de agregar la cola por BOE.
Por ello, si A está resuelta y B no, `validation_issues_json` conserva B y la
fila documental sigue bloqueando; una resolución de A nunca elimina B. La
métrica `n_review_required` cuenta BOE pendientes, mientras el inventario de
actuaciones se conserva y se cuenta en los diagnósticos, no en las filas
agregadas.

El snapshot copia los bytes de ambos registros validados como
`historical_antecedent_corrections.csv` y
`historical_antecedent_reviews.csv`, y declara sus hashes físicos e identidades
semánticas junto a la versión de política. Así, un cambio futuro de los masters
no altera retrospectivamente la cola publicada. Subsets conservan el input
versionado; unions y recanonicalizaciones rechazan un input objetivo que quite
o reescriba procedencia relevante del parent. Los snapshots anteriores a esta
política siguen cargando con su contrato histórico.

El replay versionado usa las actuaciones erróneas anteriores a la corrección:
detecta 11/11 antecedentes aprobados, marca 0/5 controles actuales y reconcilia
las once huellas contra sus correcciones aprobadas sin reabrir la cola.

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

## Linaje de las decisiones manuales

El flujo de una decisión queda registrado de forma reproducible:

```text
intento automático original
→ entrada en cola
→ fichero de decisión manual
→ validación de identidad y linaje
→ validación del JSON corregido
→ selección vigente
```

Los ficheros fuente viven en `config/manual_reviews/boe_ai/`, fuera de
`data/**`, y son entradas versionables del pipeline. Los Parquet consolidados
son derivados y no se editan manualmente. Una decisión final
`manually_validated` o `rejected` exige `reviewer`, `review_notes`, una fecha
válida en `reviewed_at_utc` y un `source_attempt_id`. El intento debe existir
una sola vez y coincidir con el BOE, el hash documental,
`extraction_config_id` y `document_validation_version` vigentes.

`manually_validated` incorpora el JSON corregido después de validarlo con el
contrato Pydantic, canonicalizarlo y contrastarlo con el documento. El intento
automático no se modifica ni se elimina: la extracción manual seleccionada
conserva `source_attempt_id` para enlazarlo. `rejected` mantiene la semántica
actual: retira la extracción automática, resuelve la cola y participa en las
métricas igual que antes; este cambio solo refuerza su trazabilidad.

La precedencia no depende del orden de filas ni de ficheros. Se elige la última
decisión por `reviewed_at_utc` y, si hay empate, por el identificador estable
derivado del contenido de la revisión. Una revisión de un hash anterior se
rechaza en vez de aplicarse al documento actual. Las revisiones antiguas que no
tengan revisor, motivo, fecha o intento válido deben actualizarse manualmente;
no reciben valores inventados ni backfill automático.

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

Siguen pendientes otros warnings para extracciones válidas pero sospechosas, el
tratamiento administrativo de documentos no intentados más allá de exigir que
se procesen, y la prioridad y asignación de revisores. También queda pendiente
revisar el significado funcional de `rejected`; aquí se conserva exactamente
su efecto actual sobre selección, cola, métricas y estado de calidad. Esta
política tampoco añade nuevos estados ni cambia el contrato Pydantic, las
etiquetas del piloto, el flattening o la materialización Silver.
