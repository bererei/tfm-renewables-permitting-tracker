from typing import Any

def as_list(value: Any) -> list[Any]:
    """
    Normaliza un valor para tratarlo siempre como una lista.

    Se utiliza principalmente para manejar respuestas de la API del BOE
    donde un nodo puede aparecer como un único elemento o como una lista
    de elementos.

    Parámetros
    ----------
    value : Any
        Valor a normalizar.

    Retorna
    -------
    list[Any]
        - [] si value es None.
        - value si ya es una lista.
        - [value] en cualquier otro caso.
    """
    if value is None:
        return []

    return value if isinstance(value, list) else [value]