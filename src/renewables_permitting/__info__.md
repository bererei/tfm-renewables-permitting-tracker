Ejecutar una vez para que funcione: pipenv install -e .

utils.py              → funciones pequeñas como as_list
boe.py                → carga y parseo de metadata.json / sumario.json
preprocessing.py      → limpieza de texto y normalización
candidates.py         → filtrado por keywords energéticas
extraction.py         → extracción de potencia, promotor, ubicación, proyecto
entity_resolution.py  → agrupación de documentos en proyectos
timeline.py           → evolución temporal del expediente