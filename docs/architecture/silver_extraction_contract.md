# Contrato Silver normalizado de extracción

## Capas y responsabilidad

La extracción canónica persistida es el objeto JSON validado por Pydantic que
conserva la semántica documental y la selección vigente de cada BOE. Es la
fuente desde la que se regeneran las tablas normalizadas.

Las tablas Silver normalizadas son una proyección relacional sin resolución de
entidades. Conservan menciones, evidencias, referencias locales e
identificadores posicionales. No añaden columnas de linaje: el linaje de una
ejecución se conserva en `manifest.json`.

Las futuras tablas Silver Curated podrán aplicar correcciones trazables,
resolver localizaciones o consolidar entidades. No existen todavía y no forman
parte de este contrato.

El flujo implementado es:

```text
extracción canónica
→ flattening
→ tipos contractuales
→ validación estructural y relacional
→ staging
→ escritura y relectura de los 13 Parquet
→ validación y comparación semántica
→ manifest
→ publicación del directorio completo
```

## Tipos y columnas comunes

El contrato vigente es `FLAT_CONTRACT_VERSION = "1"`. Todas las tablas tienen,
en este orden, las siguientes columnas de trazabilidad:

| Columna | pandas | Arrow | Nullable |
| --- | --- | --- | --- |
| `event_id` | `string` | `string` | no |
| `identificador_boe` | `string` | `string` | no |
| `fecha_publicacion` | `datetime64[ns]` | `timestamp[ns]` | no |

El resto de tipos se corresponden de forma directa:

- `string` de pandas con `string` de Arrow;
- `Int64` de pandas con `int64` de Arrow;
- `boolean` de pandas con `bool` de Arrow;
- `datetime64[ns]` de pandas con `timestamp[ns]` de Arrow.

Salvo las columnas marcadas expresamente como nullable, todas las columnas son
obligatorias. El orden completo y los esquemas ejecutables residen únicamente
en `FLAT_TABLE_SPECS`.

## Las 13 tablas

### `publication_events`

Una fila por evento de publicación extraído.

- Columnas adicionales: `event_index Int64`, `event_summary string`,
  `n_generation_assets Int64`, `n_associated_components Int64`,
  `n_administrative_actions Int64`.
- PK: `event_id`.
- FK: ninguna; es la raíz del conjunto normalizado.

### `generation_asset_mentions`

Una fila por mención de planta generadora dentro de un evento.

- Columnas adicionales: `generation_asset_mention_id string`,
  `local_generation_asset_ref string`, `generation_type string`,
  `evidence string`.
- PK: `generation_asset_mention_id`.
- FK: `event_id → publication_events.event_id`.

### `generation_asset_names`

Una fila por nombre observado de una mención de planta.

- Columnas adicionales: `generation_asset_mention_id string`,
  `name_index Int64`, `name_raw string`.
- PK: (`generation_asset_mention_id`, `name_index`).
- FK: evento y
  `generation_asset_mention_id → generation_asset_mentions`.

### `associated_components`

Una fila por componente de almacenamiento o evacuación asociado al evento.

- Columnas adicionales: `associated_component_id string`,
  `local_component_ref string`, `component_type string`,
  `description_raw string` nullable, `evidence string`.
- PK: `associated_component_id`.
- FK: evento.

### `associated_component_names`

Una fila por nombre observado de un componente asociado.

- Columnas adicionales: `associated_component_id string`,
  `name_index Int64`, `name_raw string`.
- PK: (`associated_component_id`, `name_index`).
- FK: evento y `associated_component_id → associated_components`.

### `associated_component_generation_links`

Una fila por vínculo declarado entre un componente y una planta del mismo
evento.

- Columnas adicionales: `associated_component_id string`, `link_index Int64`,
  `local_generation_asset_ref string`,
  `generation_asset_mention_id string`.
- PK: (`associated_component_id`, `link_index`).
- FK: evento, componente y mención de planta.

### `administrative_actions`

Una fila por actuación administrativa del evento.

- Columnas adicionales: `administrative_action_id string`,
  `action_index Int64`, `action_type string`, `decision string`,
  `is_modification boolean`, `evidence string`.
- PK: `administrative_action_id`.
- FK: evento.

### `administrative_action_targets`

Una fila por target de una actuación administrativa.

- Columnas adicionales: `administrative_action_id string`,
  `target_index Int64`, `target_ref string`, `target_entity_id string`,
  `target_kind string`.
- PK: (`administrative_action_id`, `target_index`).
- FK: evento y `administrative_action_id → administrative_actions`.
- Relación polimórfica: `target_kind` selecciona `publication_events`,
  `generation_asset_mentions` o `associated_components`.

### `participant_mentions`

Una fila por mención de participante administrativo.

- Columnas adicionales: `participant_mention_id string`,
  `participant_name_raw string`, `participant_role string`, `evidence string`.
- PK: `participant_mention_id`.
- FK: evento.

### `location_mentions`

Una fila por localización administrativa mencionada, todavía sin resolver.

- Columnas adicionales: `location_mention_id string`,
  `location_name_raw string`, `location_level string`,
  `province_hint_raw string` nullable,
  `autonomous_community_hint_raw string` nullable, `evidence string`.
- PK: `location_mention_id`.
- FK: evento.

### `generation_asset_relations`

Una fila por relación explícita entre dos plantas del mismo evento.

- Columnas adicionales: `generation_asset_relation_id string`,
  `source_generation_asset_ref string`,
  `source_generation_asset_mention_id string`,
  `target_generation_asset_ref string`,
  `target_generation_asset_mention_id string`, `relation_type string`,
  `evidence string`.
- PK: `generation_asset_relation_id`.
- FK: evento y dos FK hacia `generation_asset_mentions`.

### `technical_mentions`

Una fila por atributo técnico mencionado para una planta o componente.

- Columnas adicionales: `technical_mention_id string`, `owner_kind string`,
  `owner_ref string`, `generation_asset_mention_id string` nullable,
  `associated_component_id string` nullable, `attribute_type string`,
  `value_raw string`, `evidence string`.
- PK: `technical_mention_id`.
- FK: evento.
- Relación polimórfica: `owner_kind` exige exactamente uno de los dos IDs de
  propietario y lo relaciona con una planta o un componente del mismo evento.

### `case_file_references`

Una fila por referencia de expediente citada en el evento.

- Columnas adicionales: `case_file_reference_id string`,
  `reference_index Int64`, `case_file_reference_raw string`.
- PK: `case_file_reference_id`.
- FK: evento.

## Identificadores e independencia del orden

Los IDs del contrato v1 se construyen con BOE, evento, referencia local o
posición dentro de las listas canónicas. Son estables mientras no cambien esas
listas, pero no son identificadores de entidad consolidada: insertar o mover un
elemento en la extracción canónica puede cambiar IDs posteriores.

Los índices lógicos comienzan en uno y deben ser consecutivos dentro de su
padre. El orden físico de las filas de un DataFrame o Parquet no forma parte del
contrato. La validación y la equivalencia semántica ordenan copias por PK cuando
es necesario y nunca modifican las tablas recibidas.

## Tablas vacías y documentos sin eventos

Cada una de las 13 tablas puede materializarse vacía conservando columnas y
tipos. Un conjunto completamente vacío es válido. Los documentos sin eventos
no generan una tabla adicional: `manifest.json` registra el número de
extracciones de entrada con y sin eventos, mientras la extracción canónica, sus
intentos y revisiones siguen siendo la fuente de auditoría documental.

Las 13 tablas no permiten deducir cuántos documentos no produjeron eventos.
Por ello, `materialize_flat_tables()` exige que `manifest_context` proporcione
explícitamente `input_row_count`, `input_with_events_count` e
`input_without_events_count`, con valores no negativos cuya suma sea
coherente. Cuando se proporciona linaje, debe contener exactamente un registro
por fila de entrada; para una entrada vacía debe ser una lista vacía.

`materialize_current_extractions()` es la API principal del pipeline. Esta sí
calcula los tres conteos directamente desde los modelos Pydantic validados y
no los infiere a partir de las tablas hijas. También comprueba que el BOE
canónico de cada JSON sea único y que, si existe la columna
`identificador_boe`, sea no nula y coincida exactamente con ese BOE canónico.

## Directorio publicado y manifiesto

Cada llamada recibe un `output_dir` nuevo y explícito. La escritura usa un
staging temporal único y hermano del destino. Solo después de escribir, releer
y verificar todos los artefactos se renombra el staging al directorio final.
Un destino que exista antes de iniciar la materialización se rechaza y, ante
los fallos controlados durante escritura, relectura, validación, manifiesto o
renombrado, se elimina únicamente el staging creado por esa ejecución. Como en
cualquier operación de sistema de archivos, una imposibilidad externa de
eliminarlo —por ejemplo, permisos retirados durante la ejecución— puede impedir
el cleanup.

La publicación presupone un único proceso escritor por `output_dir` y no
ofrece exclusión entre escritores concurrentes. Existe una ventana entre la
comprobación final y `rename`: otro proceso podría crear en ella un directorio
vacío que la semántica POSIX de `rename` permita sustituir. Por tanto, esta fase
no garantiza «no reemplazar» bajo concurrencia. El futuro pipeline deberá
coordinar la selección y publicación de versiones; locking, catálogos y un
puntero `current` siguen fuera del alcance actual.

El directorio contiene exactamente 13 Parquet —con nombres derivados de
`FLAT_TABLE_SPECS`— y `manifest.json`. El manifiesto incluye:

- `materialization_id`, `flat_contract_version` y `created_at_utc`;
- conteos de entrada, entradas con/sin eventos y eventos materializados;
- número de tablas;
- resumen de linaje limitado a las columnas disponibles entre
  `identificador_boe`, `attempt_id`, `source_document_sha256`,
  `extraction_config_id` y `selection_source`;
- por tabla: nombre, fichero relativo, filas, columnas, PK, esquema Arrow y
  SHA-256 del Parquet.

No se incluyen prompts, texto del BOE, respuestas completas del modelo,
revisores, credenciales ni rutas absolutas.

## Reproducibilidad semántica

`materialization_id` es un SHA-256 determinístico de la versión contractual,
los conteos e identidad de entrada disponibles y el contenido semántico de las
13 tablas ordenado por PK. No incluye la fecha de creación ni el directorio
físico. Antes de escribir se ordenan copias de cada tabla por su PK; una
reordenación de filas o un índice pandas distinto no cambia el ID ni el orden
relacional publicado. Una extracción, selección o contenido tabular distinto
sí lo cambia.

Los Parquet no tienen que ser binariamente idénticos. Tras escribirlos se
comprueban el esquema Arrow, columnas, filas, tipos pandas, validación relacional
y equivalencia exacta de valores ordenados por PK.

## Versionado y compatibilidad temporal

Cada ejecución publica un directorio completo nuevo. Todavía no existe un
puntero `current`, un catálogo de versiones ni una actualización diaria; esas
responsabilidades, incluida la coordinación de un único escritor efectivo,
corresponderán al pipeline futuro.

`save_flattened_extractions()` se conserva sin cambios para los notebooks y
tests legacy. Escribe las rutas históricas y no se utiliza en la nueva API de
materialización. La migración de esos consumidores queda pendiente.

## Fuera de alcance

Este contrato no implementa:

- localizaciones resueltas;
- correcciones manuales posteriores sobre tablas derivadas;
- agrupación de proyectos;
- cronología;
- estado administrativo;
- tablas Gold.
