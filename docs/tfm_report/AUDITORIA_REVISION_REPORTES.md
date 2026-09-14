# Auditoría de revisión humana y reportes — 2026-09-14

**REQUIRED — precisión de la memoria. READY FOR HUMAN REVIEW.**
Inspección del código y de evidencias existentes en
`tfm-evaluation@a7eadca9564df9d982f1145c22b3e39f4c0dc6fd`.
No se desarrollan funcionalidades ni se alteran código, tests, configuración
productiva, datos o resultados. Los cambios previos de la memoria se conservan.

## Conclusión y clasificación

**NO existe una cola persistente unificada** de extracción, territorio, P0 y
reportes públicos. Extracción y P0 comparten una cola por snapshot; territorio
tiene estados independientes; Streamlit construye un correo sin persistencia.
Existen revisión administrativa acotada, decisiones trazables y regeneración
por etapas, pero no una gestión integrada de cualquier incidencia.

Los estados califican el alcance descrito en cada fila; IMPLEMENTED no implica
cobertura de todo error posible ni validación semántica exhaustiva.

| Flujo | Estado | Implementación | Persistencia |
| --- | --- | --- | --- |
| 1. Detección automática | IMPLEMENTED | Errores/validación de extracción, clasificación incierta, ausencia de intento, P0 y estados territoriales | Intentos, diagnósticos y resultados territoriales, según etapa |
| 2. Cola de revisión | PARTIAL | `build_review_queue`: extracción y P0; no territorio ni reportes | `review_queue.parquet` en el snapshot de extracción |
| 3. Listado/visualización | PARTIAL | Admin `list`/`show` para extracción/P0; territorio se inspecciona por separado | Lectura del snapshot completo; no bandeja pública de incidencias |
| 4. Decisión humana | IMPLEMENTED | Aprobación/rechazo genéricos y CURRENT/ANTECEDENT acotados | JSON por BOE y dos registros CSV |
| 5. Generación de corrección versionable | PARTIAL | La CLI genera exclusiones históricas; una extracción estructural corregida se prepara fuera de esa interfaz | CSV de exclusiones o JSON revisado, versionables en Git; la CLI no hace commit |
| 6. Aplicación | IMPLEMENTED | Selección manual validada; exclusión sobre una copia antes de Silver, con coincidencia exacta | Linaje de selección y `applied_corrections.parquet` |
| 7. Regeneración | IMPLEMENTED | Comandos por etapas ejecutados por el operador; no automática al registrar una decisión | Nuevos snapshots y manifests; Silver y Gold regenerados |
| 8. Reporte público Streamlit | PARTIAL | Control `mailto:` implementado; requiere destino válido y cliente de correo | La aplicación no almacena ni envía el mensaje |
| 9. Persistencia de reportes | NOT IMPLEMENTED | No receptor/backend de incidencias en este mecanismo; propuesta POST-TFM | Ninguna tabla o registro de reportes del sistema |
| 10. Integración de reportes con la cola | NOT IMPLEMENTED | No llamada al circuito administrativo ni creación de filas; propuesta POST-TFM | Ninguna |

## Extracción: detección, cola y bloqueo

Fuentes: [`review.py`](../../src/renewables_permitting/extraction/review.py),
`REVIEW_QUEUE_COLUMNS`, `_REVIEW_REASON_POLICIES`, `_review_reason_code`,
`build_review_queue`; [`runner.py`](../../src/renewables_permitting/extraction/runner.py),
`build_error_record`; [`validation.py`](../../src/renewables_permitting/extraction/validation.py),
`validate_extraction_against_document`;
[`pipeline.py`](../../src/renewables_permitting/pipeline.py),
`run_extraction_stage`, `load_extraction_snapshot`, `run_silver_stage`.

Los cinco motivos actuales son `source_not_attempted`, `extraction_error`,
`document_validation_failed`, `classification_uncertain` y
`possible_historical_antecedent`. Todos tienen severidad `blocking`.
El fallo documental tiene prioridad sobre el error genérico; la incertidumbre
se utiliza cuando el intento es correcto y supera la validación documental.
Los errores de ejecución conservan tipo, mensaje, fase y propuesta si existe.
La validación documental comprueba, entre otros aspectos, alcance, BOE/fecha,
literalidad y relaciones/referencias válidas. Los errores de contrato o de
ejecución no se convierten artificialmente en un diagnóstico documental.

La cola contiene como máximo una fila pendiente por BOE objetivo, con
`queue_status=pending`. No contiene un historial mutable de estados
«abierto/asignado/resuelto». Guarda `review_queue_id`, BOE/fecha/título,
`source_document_sha256`, `source_attempt_id`, configuración y versión de
validación, motivo/severidad, error/fase, `validation_issues_json`,
`proposed_extraction_json` y fecha de encolado. Su ID se calcula con SHA-256
sobre BOE, hash de fuente, intento y motivo, truncado a 24 caracteres.

El snapshot persiste `attempts.parquet`, `manual_reviews.parquet`,
`current_extractions.parquet`, `review_queue.parquet` y manifest, junto a sus
entradas documentales y, con la política P0, copias de los registros
históricos. El cargador verifica artefactos y recalcula selección/cola.
Una decisión se refleja al crear un nuevo snapshot con las entradas revisadas;
no se edita el Parquet de la cola ya publicada. Un intento posterior fallido
puede coexistir con una selección válida anterior, pero su bloqueo permanece.
Silver exige cero filas bloqueantes (`ReviewRequired`; salida CLI 4).
Los errores posteriores de tablas, agrupación o materialización detienen su
etapa; no todos los validadores escriben en esta cola de extracción.

## P0: detección y resolución independientes

Fuentes: [`historical_antecedents.py`](../../src/renewables_permitting/extraction/historical_antecedents.py),
`detect_possible_historical_antecedents` y `reconcile_historical_antecedent_findings`;
[`historical_antecedent_reviews.py`](../../src/renewables_permitting/extraction/historical_antecedent_reviews.py);
[guía de calidad](../architecture/extraction_quality_review.md).

El detector es puro y no elimina actuaciones. Requiere una señal temporal o
estructural y otra contextual independiente, localizadas en la fuente. Una
fecha aislada no basta; evidencia no localizable o también presente en el
dispositivo no produce esa conclusión automática. No garantiza detectar todo
antecedente. El pipeline actual activa la salvaguarda; los helpers de revisión
permiten desactivarla y los snapshots antiguos conservan su política original.

Los hallazgos por actuación se agregan en `validation_issues_json` de la misma
cola documental. La CLI los despliega por actuación. La reconciliación produce
hallazgos pendientes o resueltos, con dos decisiones humanas posibles:

- **CURRENT**: una validación actual exacta, no una corrección. CSV
  `config/manual_reviews/historical_antecedent_reviews.csv`, versión 1,
  `status=approved`, `outcome=current`. Incluye BOE/actuación, hash documental,
  tipo/decisión/huella de evidencia, motivo, versión del detector, razón,
  fuente de decisión, fecha y reviewer. El ID se deriva del registro; no hay
  una columna `review_id` introducida manualmente en este CSV.
- **ANTECEDENT**: exclusión histórica aprobada en
  `config/corrections/administrative_action_corrections.csv`; se aplica después
  a la copia usada para Silver. Resolver un hallazgo no resuelve otros del BOE.
  CURRENT y ANTECEDENT contradictorios fallan; una validación genérica no
  elimina automáticamente un hallazgo P0 pendiente.

El CSV CURRENT contiene actualmente **cero decisiones**. Su funcionalidad
existe en código y tests; no se presenta como uso real de un registro poblado.
Tampoco se confunde P0 con la recuperación retrospectiva de publicaciones.

## Revisión humana, corrección y regeneración

Fuentes: [`admin.py`](../../src/renewables_permitting/admin.py),
`prepare_*_decision`, `persist_*_decision`, `_print_next_steps`;
[`corrections.py`](../../src/renewables_permitting/extraction/corrections.py),
`validate_administrative_action_corrections`, `apply_administrative_action_corrections`;
`review.py::_validate_manual_reviews` y `select_best_valid_extractions`;
[User Guide §§11–13](../USER_GUIDE.md).

Comandos reales: `list`, `show`, `current`, `antecedent`,
`validate-extraction`, `reject-extraction`, `list-decisions`.
`list`/`show` cargan el snapshot completo, no un Parquet aislado.
`validate-extraction` solo aprueba la propuesta exacta existente tras volver a
validarla; `reject-extraction` rechaza la extracción completa. Ambos excluyen
casos sin intento y hallazgos P0, que tienen tratamiento específico. No permiten
editar campos, añadir actuaciones, corregir INE ni fusionar/separar proyectos.

Las revisiones genéricas se guardan en `config/manual_reviews/boe_ai/<BOE>.json`.
Su contrato contempla `pending`, `manually_validated`, `rejected`. La CLI crea
o promueve una decisión pendiente; no sobrescribe una ya decisiva. El código
deriva `manual_review_id`, verifica intento/hash/configuración/versión y añade
el hash del esquema al registro consolidado. El JSON puede contener una
extracción estructural completa preparada técnicamente fuera de la CLI; esta
posibilidad no convierte la CLI en un editor. Los cuatro JSON existentes
contienen tres decisiones `manually_validated` y una `rejected`.

El CSV de exclusiones tiene un contrato cerrado v1: `status=approved`,
`entity_type=administrative_action`, `operation=exclude`,
`reason_code=historical_antecedent_misattributed`. La CLI deriva los nuevos
IDs como `historical-action-exclusion-v1-<sha256[:24]>` y obtiene las huellas
del hallazgo validado. Los registros históricos conservan otros IDs válidos;
no se afirma que todos procedan de la CLI actual. La persona aporta el juicio,
motivo, reviewer y referencia. Se guardan versión y fecha. Los CSV se validan
completos, se preparan temporalmente, se comprueba que el original no cambió,
se reemplazan atómicamente y se recargan; los JSON también se validan antes
de instalarse. La persistencia en un archivo versionable no hace commit.

La aplicación exige un objetivo único y tipo, decisión y hash de evidencia
coincidentes; falla ante discrepancias. Trabaja sobre una copia y registra
corrección, versión, motivo, objetivo y huellas de registro/extracción en
`applied_corrections.parquet`, auxiliar de Silver, no una decimocuarta tabla
del contrato relacional. No edita intentos originales. La revisión genérica
válida tiene precedencia en la selección; el rechazo evita seleccionar ese BOE.

Tras guardar una decisión, la CLI **solo imprime** los pasos posteriores:
el operador revisa y ejecuta `extract` reutilizando intentos compatibles,
`corrections-subset`, `silver --corrections` y `downstream` en destinos nuevos.
No implica una nueva llamada al modelo para aplicar la decisión ni una
regeneración automática. Un documento sin intento requiere su extracción;
un reintento de error exige selección explícita. Estos comandos no se han
ejecutado durante esta auditoría.

## Ejemplo real comprobado

Registro maestro: **16 exclusiones**, identidad
`6cd1893c1cc75b239b29e88b7aa04cb407503f9a56b6063e152e9e8cbcef0318`,
SHA-256 físico `1d757237cd203dae096dcc36b7af5f041bc7f1d0e31fd9bfdce6e1add4c050b0`.
Se leyeron, sin regenerar, la extracción W14 v1 y el sidecar y tablas Silver v2.
Hay **11 exclusiones aplicadas** en W14; las otras cinco están fuera de ese
corpus. Fuente complementaria: [correcciones W14](../FINAL_W14_ADMIN_ACTION_CORRECTIONS.md).

La corrección `historical-action-exclusion-v1-17939-public-information`
afecta a `BOE-A-2026-17939_event_1_action_4`, información pública histórica.
La huella calculada sobre la evidencia original coincide con el CSV y el
sidecar: `9b39305621d4b75738ad56cb51b94e5097c2396c66bff6b4547094a22cb7877d`.
La decisión registra aprobación humana de 2026-08-27. Agosto conserva las
autorizaciones actuales de Don Rodrigo II; abril conserva la información
pública de `BOE-B-2026-12663`. No se movieron ni inventaron actuaciones.
Este caso acredita una corrección aplicada, no que se usase entonces la CLI
actual ni que el detector tomase la decisión humana.

## Localizaciones

Fuentes: [`location_resolution.py`](../../src/renewables_permitting/location_resolution.py),
enums, `_aggregate_status`, `resolve_locations`;
[`project_grouping.py`](../../src/renewables_permitting/project_grouping.py),
`_validate_inputs`; [`downstream.py`](../../src/renewables_permitting/downstream.py),
`run_downstream`.

Estados por nivel: `resolved`, `ambiguous`, `conflict`, `not_found`,
`not_provided`. El agregado añade `partially_resolved`: resuelto algún nivel
pero no los tres, sin ambigüedad/conflicto, que tienen prioridad. Resolver solo
provincia o comunidad puede ser correcto y suficiente para esa mención.
Se conservan texto, identificadores, códigos, método y razón por nivel.
No existe estado territorial `review_required` ni escritura a `review_queue`.

`resolve_locations` devuelve un DataFrame sin escribir. En downstream,
`ambiguous`/`conflict` en provincia o comunidad abortan la agrupación con
`requires_inspection` en el mensaje; ese texto no es un estado persistido.
La misma condición solo municipal no activa ese gate. La tabla
`resolved_locations.parquet` se publica con el downstream validado; si falla
antes, no se publica una tabla parcial de incidencias territoriales. Por tanto,
no equivale a una segunda cola persistente de casos bloqueados. La inspección
técnica es independiente y la Admin CLI no corrige territorios. El W14 v2
existente contiene 624 resultados `resolved` y 204 `partially_resolved`;
estos conteos describen el artefacto, no métricas nuevas de exactitud.

## Reporte público

Fuentes: [`streamlit_app.py`](../../streamlit_app.py), `_report_destination`
y `_render_report_channel`;
[`app_reporting.py`](../../src/renewables_permitting/app_reporting.py).

**PARTIAL respecto al circuito de reportes propuesto; el control mailto está
IMPLEMENTED.** En la barra lateral, «Reportar posible error» abre un borrador
de correo con vista/filtros y, en la ficha, proyecto y última publicación.
El usuario completa y envía el mensaje desde su cliente. Streamlit no envía
correo, no tiene backend receptor de incidencias, no almacena el mensaje, no
crea filas ni llama a Admin CLI o `review_queue`. Un eventual buzón externo no
es persistencia del sistema ni prueba de recepción o resolución.

El destino procede de `RENEWABLES_REPORT_EMAIL` o, si la variable no existe,
del secret `report_email`. Un valor explícito inválido deshabilita el canal;
no cambia silenciosamente al secret. El control deshabilitado muestra
«Canal de reporte no configurado en esta instalación».

Comprobación local sin mostrar direcciones: variable ausente en el entorno de
esta sesión; `.env` sin esa entrada; no existen secrets de Streamlit del
repositorio ni del usuario. No se encontró un proceso Streamlit de este
repositorio en ejecución con los argumentos inspeccionados. **No hay destino
local acreditado; no se ha comprobado un despliegue remoto ni enviado correo.**
La capacidad implementada y la configuración de una instalación se distinguen.
Si se recibe un correo por un canal configurado, trasladarlo a una revisión
técnica es una intervención externa, sin integración automática existente.

## Flujo actual implementado

```text
Fuentes + intentos conservados
  -> selección, validación y detector P0
     ├─ sin pendientes ------------------------------┐
     └─ review_queue.parquet (por BOE; bloqueante)    │
          -> Admin CLI: list/show -> revisión humana │
             ├─ genérica: validar propuesta/rechazar  │
             │    -> JSON de decisión                │
             ├─ CURRENT -> CSV; conserva actuación   │
             └─ ANTECEDENT -> CSV de exclusión        │
          -> operador: nuevo snapshot reconciliado   │
          -> cero pendientes ------------------------┤
                                                     v
                        subconjunto de correcciones aplicables
                          -> aplicar sobre copia -> Silver
                          -> resolución territorial
                             ├─ provincia/CCAA insegura: detener
                             │  e inspeccionar; sin cola común
                             └─ control superado: agrupación -> Gold

Streamlit -> mailto (si configurado) -> cliente de correo del usuario
            Sin enlace automático al circuito anterior.
```

El caso sin intento necesita primero extracción; no admite decisión genérica.
No toda revisión produce una corrección del contenido. La cola anterior
permanece intacta: las decisiones producen una nueva salida reconciliada.

## Flujo conceptual FUTURE / POST-TFM

```text
Incidencias automáticas de extracción/P0 ─┐
Incidencias territoriales ────────────────┼─> cola unificada persistente
Reportes Streamlit -> recepción/registro ─┘       -> administración/revisión humana
                                                   ├─ descartar o confirmar
                                                   └─ corrección versionada
                                                        -> regenerar/validar
                                                        -> publicar nuevo Gold
                  Historial: incidencia -> evidencia -> decisión -> versión
                  Conservar último Gold válido mientras existan bloqueos.
```

No implementado como circuito integrado. Reutilizaría decisiones, validación
y materialización actuales, y añadiría recepción, persistencia y coordinación.

## Memoria, figura y límites

Capítulo 4: estados territoriales independientes; motivo de revisión humana;
decisiones frente a correcciones; regeneración del operador; P0 y ejemplo real.
Capítulo 5: mailto y falta de persistencia/integración.
Capítulo 9: «Cola unificada de incidencias y reportes de usuarios», POST-TFM.

**Figura: opción A, solo flujo real**, con el título «Flujo de revisión y
corrección humana implementado» (F06). La propuesta se integra en F09,
«Arquitectura propuesta para una futura operación diaria». Se actualizan los
TODO existentes; no se dibujan dos figuras redundantes ni se añade una rama
futura a la figura actual. La memoria explica conceptos; `docs/USER_GUIDE.md`
conserva los procedimientos y no se modifica.

Hallazgo **importante pero no bloqueante para esta corrección documental**:
el destino de correo local no está configurado y la entrega pública requiere
su comprobación. La ausencia de una cola unificada es una limitación explícita
POST-TFM, no un motivo para desarrollar ahora. No se declara completada toda
la memoria ni la aceptación pública del producto.

## Verificación e impacto documental

Se inspeccionaron los tests existentes de revisión, revisión/IO, P0,
correcciones, Admin CLI, resolución territorial, grouping y reporting
(`tests/extraction/test_review*.py`, `test_historical_antecedents.py`,
`test_corrections.py`; `tests/test_admin.py`, `test_location_resolution.py`,
`test_project_grouping.py`, `test_app_reporting.py`, `test_streamlit_app.py`).
Se comprobaron las aserciones de cola, preservación del original, resolución
exacta, límites de CLI y fallback/mailto. **No se ejecutó pytest**: no hay
cambio funcional ni nueva evaluación, conforme al cierre documental.

Diagnósticos ejecutados: búsquedas `rg` y lecturas acotadas de código/tests;
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m renewables_permitting.admin --help`
(exit 0); cargadores contractuales de ambos CSV; lectura de cuatro JSON,
selecciones del Parquet de extracción, sidecar/Silver y estados territoriales;
cálculo de la huella de evidencia del ejemplo; comprobación de presencia y
validez del correo sin imprimir datos de configuración. No se llama al modelo,
BOE, evaluación, regeneración productiva ni cliente de correo.

- **Documentation impact:** precisión conceptual de la memoria y trazabilidad de la auditoría.
- **Documents reviewed:** cierre TFM, reglas/mapa/plan de la memoria, User Guide §§11–13 y reporting, guía de calidad, informes de auditoría temporal/correcciones W14; código, contratos y tests citados.
- **Documents updated:** este informe, capítulos 4/5/9, `MAPA_FUENTES.md`, `PLAN_FIGURAS.md` y el inventario de `COMPILACION.md`.
- **Reason:** separar capacidades implementadas, límites de operación y propuesta futura sin modificar el sistema.

La compilación, páginas afectadas y comprobaciones finales se registran al
cierre de esta auditoría en `PLAN_FIGURAS.md`.
