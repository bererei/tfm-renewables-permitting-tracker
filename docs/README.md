# Documentation

`docs/` reúne la documentación operativa vigente, los contratos técnicos, la
evaluación final, las declaraciones de congelación, el historial de ejecución y
las fuentes de la memoria del TFM. Este archivo es solo un mapa de navegación;
las fuentes enlazadas conservan el detalle y la autoridad de cada ámbito.

## Start here

- [Manual de usuario y operación](USER_GUIDE.md): comandos, flujos de trabajo,
  contratos operativos y resolución de problemas.
- [TFM Closeout](TFM_CLOSEOUT.md): estado vigente del cierre, prioridades,
  gates y pendientes hasta la entrega.

## Data and product

- [Application Data Catalog](APP_DATA_CATALOG.md): tablas, campos, identidades
  y disponibilidad de datos para el producto.
- [Application Product Specification](APP_PRODUCT_SPEC.md): alcance, preguntas,
  filtros, visualizaciones y criterios de aceptación.
- [Final Streamlit Product Alignment](FINAL_STREAMLIT_PRODUCT_ALIGNMENT.md):
  alineación final de la aplicación con el Gold validado.
- [Guía técnica de Streamlit](STREAMLIT_CODE_GUIDE.md): arquitectura, consultas
  y pautas de mantenimiento de la aplicación.

## Architecture

[architecture/](architecture/) contiene los contratos técnicos y las reglas
vigentes de selección, revisión, calidad y materialización Silver. La memoria
explica estas decisiones con finalidad académica, pero no sustituye esos
contratos técnicos.

## Evaluation

[evaluation/](evaluation/) contiene el protocolo y la evidencia reproducible de
la evaluación final. Los puntos de entrada principales son:

- [contrato V2](evaluation/FINAL_HOLDOUT_EVALUATION_CONTRACT_V2.md);
- [evaluador V2-B](evaluation/V2_B_EVALUATOR.md);
- [resultados finales V2](evaluation/FINAL_HOLDOUT_V2_RESULTS.md);
- [ejecución primaria](evaluation/PRIMARY_EXECUTION_V2.md).

El contrato V1 se conserva como precedente metodológico. Los documentos de
resultados y cierre identifican qué artefactos y estados son definitivos.

## Frozen state

[freezes/](freezes/) conserva las declaraciones versionadas de congelación y
sus identidades verificables. No deben consolidarse ni reescribirse como si
fueran documentación operativa mutable.

## Historical execution ledger

Los documentos `FINAL_*.md` situados directamente en `docs/` registran fases
fechadas de construcción del corpus, extracción, W14, correcciones humanas,
producto y gates de ejecución. Forman parte de la trazabilidad del TFM.

Algunos describen estados posteriormente supersedidos. Deben leerse como
evidencia de lo que ocurrió en cada fase, no como un conjunto de instrucciones
vigentes ni como alternativas al estado canónico de `TFM_CLOSEOUT.md`.

## TFM report

[tfm_report/](tfm_report/) contiene las fuentes de la memoria:

- [tfm_report_bgd.tex](tfm_report/tfm_report_bgd.tex): raíz LaTeX activa;
- [COMPILACION.md](tfm_report/COMPILACION.md): comando de compilación y política
  de artefactos;
- [MAPA_FUENTES.md](tfm_report/MAPA_FUENTES.md): trazabilidad entre afirmaciones,
  fuentes y evidencias;
- [REGLAS_REDACCION.md](tfm_report/REGLAS_REDACCION.md): criterios editoriales y
  de precisión;
- [tfm_report_bgd.pdf](tfm_report/tfm_report_bgd.pdf): PDF tracked reservado para
  hitos aceptados y la entrega final.

`tfm_report/build/` está ignorado, es regenerable y contiene exclusivamente
outputs de compilación. No es documentación canónica ni el destino permanente
del PDF de entrega.

## Historical documents

Los documentos identificados como auditorías, revisiones, planes, preflights,
failure reviews o disposiciones históricas deben conservar el estado que era
cierto en su fecha. Un estado posterior se documenta en el checkpoint vigente;
no se actualiza retrospectivamente el registro anterior para que parezca actual.
