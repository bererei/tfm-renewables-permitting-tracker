# Reglas de redacción de la memoria

Reglas aportadas por la autora y aplicadas desde la corrección de 2026-09-14.
Ámbito: `docs/tfm_report/`. Leer junto a `MAPA_FUENTES.md` antes de continuar
la redacción. No modifica AGENTS.md ni autoriza trabajo sobre el sistema.

## Principio central

La memoria debe ser **sencilla, directa, completa y progresiva** a la vez.
Sencillez no significa omitir las explicaciones necesarias o resumir en exceso.
El lector puede tener formación técnica o ambiental sin conocer ciencia de
datos, informática o tramitación renovable. No empezar por archivos o librerías.

Para cada concepto relevante:

1. Explicar qué es con palabras sencillas.
2. Explicar para qué sirve y qué problema resuelve.
3. Explicar cómo se utiliza en este TFM.
4. Añadir un ejemplo cuando facilite la comprensión.
5. Introducir después el detalle técnico necesario.

Definir antes de usar: trámites y siglas administrativas, BOE, API, pipeline,
ETL si aparece, Bronze/Silver/Gold, LLM, Pydantic, ground truth, holdout,
matching, precision, recall, F1, Streamlit, pytest y CLI. Una definición en un
capítulo anterior permite avanzar; en Discusión conviene recordar el significado
de la medida antes de interpretarla. No repetir por sistema el mismo párrafo.

## Secciones reales frente a ejemplos de plantilla

Retirar del documento activo lipsum, tablas/ecuaciones demostrativas,
instrucciones de uso de la plantilla y ejemplos ajenos al TFM.

Conservar como TODO las secciones reales aún vacías: dedicatoria,
agradecimientos, resumen, abstract, contenido personal, capítulos planificados
y figuras pendientes. No inventar contenido personal. En caso de duda,
conservar como TODO e informar. Los archivos demostrativos históricos pueden
seguir en el repositorio sin incluirse.

La dedicatoria precede a la declaración de autoría, en la posición de la
plantilla original, con espacio vertical y alineación a la derecha. Se
mantienen portada, agradecimientos y declaración. Los índices pertinentes
se conservan; el índice de figuras está previsto y se activará al incorporar
figuras, mientras que algoritmos/listados se activarán si existen realmente.

## Narración y recursos pedagógicos

La prosa sigue siendo el elemento principal. Las listas sirven para objetivos,
pasos, condiciones o trabajo futuro. No convertir toda la memoria en listas
ni en una sucesión de párrafos sin apoyos cuando un esquema aclare el proceso.

- Ejemplos: concepto primero; después «Por ejemplo…». Preferir casos reales
  ya verificados, sin saturar de identificadores. Identificadores y procedencia
  pueden ir en una tabla, nota o caption. Un caso sintético se marca como tal.
- Analogías: breves, adultas y técnicamente correctas; siempre seguidas de
  la definición aplicada al proyecto. Materia prima → estructura → consulta
  puede introducir las capas, pero Silver no es una verdad semántica garantizada.
- Tablas: comparaciones pequeñas de siglas, capas, entidades, conjuntos,
  medidas o limitaciones. Tablas exhaustivas al anexo solo si son necesarias.
- Diagramas: definir antes mensaje, fuente y lugar. Una figura debe aclarar
  relaciones, orden o condiciones, sin duplicar párrafos ni inventar fases.
- Capturas: propósito, caption informativa, referencia en texto y resolución
  legible. Seleccionar resumen/filtros/mapa y ficha/publicaciones; metodología
  o anotación solo si añaden comprensión. No confundir las dos aplicaciones.
- Cajas/notas: usar los recursos existentes de LaTeX cuando una advertencia
  conceptual lo justifique; no introducir paquetes ni estilos por decoración.

## Acceso programático y candidatos

Destino: 2.2, concepto BOE/API; 3.1, adquisición comprobada; 3.3, selección
por título y decisión de relevancia. No confundir una consulta de sumario con
la descarga del documento completo ni con la extracción mediante IA.

Orden real confirmado en `pipeline.py::run_source_stage`:

```text
intervalo inclusivo → API de sumarios → metadatos de publicaciones
→ filtro de títulos → XML solo de candidatos → corpus fuente validado
→ reglas de alcance → descarte determinista o extracción Gemini + validación
```

No dibujar todos los XML antes del filtro. La relevancia no queda completamente
confirmada antes del modelo: las reglas resuelven ciertos negativos; los demás
requieren clasificación/extracción y validación. Las etapas son conceptualmente
distintas aunque una misma llamada al modelo produzca clasificación y entidades.

Describir direcciones, metadatos, errores y persistencia a partir del código.
La URL XML se toma del sumario. No inventar API de proyectos, caché, descarga
incremental o reanudación de adquisición. No extrapolar al estado actual una
limitación de un informe histórico sin comprobarla.

## Evaluación, discusión y uso de asistentes

Explicar TP, FP y FN antes de precisión, recall y F1; utilizar el ejemplo
10 esperados / 8 predichos / 6 correctos como ejercicio didáctico, separado de
las métricas del experimento. Explicar atributos condicionados y denominadores.

Separar fallo de extracción, alias, agrupación longitudinal, dependencia del
matching, canonicalización, regla estricta y atributo acertado tras emparejar.
El holdout no evalúa directamente la agrupación Gold. El ejemplo Hipódromo
ilustra la regla congelada, no autoriza asignar un nuevo TP.

`FINAL_HOLDOUT_V2_RESULTS.md` sigue siendo la única fuente numérica primaria.
Mantener PRIMARY RESULTS y POST-HOC DIAGNOSTIC — NOT PRIMARY SCORING separados.
No cambiar truth, evaluador, matching, denominadores, predicciones ni experimento.

Gemini forma parte del sistema evaluado. ChatGPT apoya razonamiento,
planificación, diseño metodológico, revisión y prompts. Codex desde VSCode
apoya inspección, tareas acotadas, tests, refactorización, documentación y LaTeX.
Explicar primero qué es un archivo de instrucciones persistentes para el agente
y después nombrar AGENTS.md. La autora decide y revisa; Codex propone e
implementa; pytest comprueba regresiones; la autora hace commits/push manuales.
La declaración de uso y la cronología de freezes se verifican antes de cerrarlas.
No atribuir autoría del TFM o decisiones metodológicas al asistente.

## Plan de apoyos visuales

| Destino | Recurso | Mensaje y condición previa |
| --- | --- | --- |
| 2.1 | Procedimiento administrativo | Distinguir trámites y decisiones; incluir variaciones/paralelismo y DUP cuando proceda. Verificar normativa; no imponer una cadena universal |
| 2.3 | Tabla de Don Rodrigo II, ya incluida | Abril anuncia información pública; agosto concede AAP/AAC y recuerda abril. Auditoría y correcciones W14 verificadas |
| 3.1 | Adquisición BOE/API | Sumario no es texto completo; filtrar títulos precede a descargar XML. Código actual; TODO de figura y lista de pasos incluidos |
| 4.2 | Arquitectura global | Fuente, extracción/validación, Silver, territorio/agrupación, Gold y consulta; rama experimental separada |
| 4.2 | Capas Bronze/Silver/Gold | Qué conserva y qué transforma cada capa; tabla o panel de la figura global para evitar duplicación |
| 4.4 | Extracción IA y validación | Distinguir salida generada, controles deterministas y revisión; validez no garantiza corrección |
| 4.5 | Agrupación | Varias menciones de la misma planta convergen; plantas independientes siguen separadas; no es matching experimental |
| 6 | Diseño experimental | Selección, anotación ciega, freezes y ejecución en su orden documentado |
| 6.6 | Ejemplo de métricas | Comprender qué denominador responde a cada pregunta antes de ver resultados |
| 8.2 | Cascada de matching | Activo sin match puede impedir evento y actuaciones/localizaciones; no atribuir todos los FP/FN a invenciones del modelo |
| 5 y, si aporta, 6.2 | Capturas seleccionadas | Enseñar una consulta del producto o explicar anotación ciega, sin saturar ni confundir finalidades |

Las figuras quedan planificadas: esta corrección no autoriza generarlas todas
ni redactar capítulos nuevos. Las tablas del corpus y Don Rodrigo II son
apoyos para comprender los capítulos ya redactados.

## Comprobación al cerrar un bloque

Revisar definiciones, progresión, ejemplos, trazabilidad, TODO-CITA y recursos
necesarios. Compilar; revisar referencias, citas, acentos y legibilidad. No
eliminar una sección pendiente para que parezca terminada. Informar del diff
y detenerse para revisión humana, sin commit/push ni siguiente bloque automático.
