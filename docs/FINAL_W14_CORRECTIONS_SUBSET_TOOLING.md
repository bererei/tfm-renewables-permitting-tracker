# W14 corrections-subset tooling

Fecha de validación: **26 de agosto de 2026**.

## Problema resuelto

El registro master de correcciones es acumulativo y puede contener decisiones
aprobadas para BOE que no pertenecen al snapshot de extracción que se está
materializando. El aplicador Silver, correctamente, exige que cada corrección
recibida encuentre exactamente una actuación y comprueba todos sus
discriminadores. Por tanto, pasar un master multi-corpus a un corpus aislado
produce un fallo de cero targets.

La operación `corrections-subset` proyecta el master al universo documental de
un snapshot de extracción validado antes de que Silver aplique las decisiones.
No modifica el master, la extracción ni el aplicador.

## Regla fail-closed

La pertenencia del BOE decide únicamente el scope:

- **OUT_OF_SCOPE:** el `boe_id` no pertenece al universo documental del
  snapshot. La corrección se excluye del artefacto derivado y queda registrada
  en su manifest.
- **INVALID_IN_SCOPE:** el `boe_id` sí pertenece al snapshot, pero la actuación
  no existe exactamente una vez o no coincide su ID, tipo, decisión o huella de
  evidencia. La operación aborta.

Un target in-scope ausente nunca se reclasifica como fuera de scope. El tooling
reutiliza `apply_administrative_action_corrections()` para validar las filas
seleccionadas, por lo que conserva la comprobación exact-one y la semántica
fail-closed vigente.

## Interfaz operativa

La operación es local, determinista y no llama al BOE ni a modelos:

```bash
uv run python -m renewables_permitting.pipeline corrections-subset \
  --corrections <MASTER_CORRECTIONS.csv> \
  --extraction-snapshot <EXTRACTION_SNAPSHOT_VALIDADO> \
  --output-dir <NUEVO_DIRECTORIO_SUBSET> \
  --expected-extraction-config-id <EXTRACTION_CONFIG_ID> \
  --dry-run
```

Después de revisar conteos e identidad, se repite sin `--dry-run`. El destino
debe ser nuevo.

## Contrato e identidad

El directorio publicado atómicamente contiene solo:

```text
administrative_action_corrections.csv
manifest.json
```

El CSV usa exactamente las 15 columnas y valores del contrato
`administrative_action_corrections_v1`; el subsetting no añade metadatos ni
reescribe decisiones. El manifest registra:

- tipo de artefacto y versión de operación;
- identidad semántica, SHA físico, ruta lógica y conteo del master;
- identidad, configuración y conteo documental del snapshot de extracción;
- IDs y conteos seleccionados y fuera de scope;
- huella de los IDs fuera de scope e identidad semántica de las filas
  seleccionadas;
- columnas, filas y SHA físico del CSV derivado;
- procedencia del código, identidad de materialización y timestamp UTC.

La versión de operación es `1`. La identidad se deriva del master, snapshot,
configuración, filas seleccionadas, versión de operación y huella conjunta de
la lógica de subsetting y del aplicador fail-closed. El timestamp no participa
en ella. Mismos inputs y código producen la misma identidad y los mismos bytes
del CSV.

La publicación usa staging, valida el artefacto completo con el loader
productivo y solo entonces renombra el directorio. Un fallo elimina únicamente
su staging y no publica un output parcial.

## Subset vacío

Un corpus sin correcciones aplicables produce un CSV con el header contractual
y cero filas, nunca una fila ficticia. El loader específico de
`corrections-subset` valida esta representación. El loader del registro master
continúa rechazando registros vacíos, por diseño.

Para materializar Silver cuando el subset validado está vacío se omite
`--corrections`, porque no existe ninguna decisión que aplicar. Cuando contiene
filas, su CSV tiene el mismo contrato no vacío que el master y puede pasarse
directamente a `pipeline silver --corrections` sin cambiar el aplicador.

## Preflight real W14

Inputs inspeccionados:

| Dato | Valor |
| --- | --- |
| Master | `config/corrections/administrative_action_corrections.csv` |
| Filas master | 5 |
| Identidad semántica master | `12a401d7594129e69a473a6d44f71dc89e05334f18493ddf65fbae15106b9dea` |
| SHA físico master | `51ac0cea06c02547e5ebfb20ee8a5239fca80519de9ee6bff3781bb511386411` |
| Snapshot W14 | `runs/final-w14-corpus-20220101-20260820-v1/extraction` |
| Snapshot ID | `dea0f79d9b743dccff23f19995da6ff470866c1d717a2ad1a3af7c415d06eae3` |
| Config ID | `4b54b89dbfe8640e` |
| Documentos/current/blockers | 104 / 104 / 0 |

El dry-run y la materialización real obtuvieron:

| Métrica | Resultado |
| --- | ---: |
| Correcciones master | 5 |
| Seleccionadas | 0 |
| Fuera de scope | 5 |
| Fallos | 0 |
| Identidad de materialización | `445867aade7074f7cad79dccfc6114102d5375f8e48408fbe2c26ce56395b86e` |

El artefacto de preflight está en
`/tmp/w14-corrections-subset-preflight`. El loader verificó el manifest y el
CSV header-only. Una segunda materialización independiente conservó la misma
identidad y produjo un CSV físicamente idéntico. El SHA físico y la identidad
semántica del master permanecieron intactos.

## Aplicación W14 cerrada

El bloque autorizado posterior amplió el master a 16 filas y ejecutó el gate
contractual:

```text
master 16
→ W14 selected 11
→ out-of-scope 5
→ Silver recibe solo el CSV derivado de 11 filas
```

La identidad del subset aplicado es
`764e76757d094034d9d8e079a2d493995a7e28e78655fae5ff83e36ffe995da6`.
El resultado corregido y sus regresiones se documentan en
`docs/FINAL_W14_ADMIN_ACTION_CORRECTIONS.md`.
