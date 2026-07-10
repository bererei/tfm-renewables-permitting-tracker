from collections.abc import Iterable

from renewables_permitting.utils import (
    is_null_like,
    normalize_text,
)


def text_tokens(
    text: str | None,
    *,
    stop_tokens: Iterable[str] | None = None,
) -> set[str]:
    """
    Devuelve los tokens normalizados de un texto.

    Puede excluir palabras poco informativas mediante `stop_tokens`.

    Examples
    --------
    >>> text_tokens(
    ...     "As Pontes de García Rodríguez",
    ...     stop_tokens={"as", "de"},
    ... )
    {'pontes', 'garcia', 'rodriguez'}
    """
    if is_null_like(text):
        return set()

    excluded = set(stop_tokens or ())

    return {
        token
        for token in normalize_text(text).split()
        if token and token not in excluded
    }


def token_overlap_score(
    query: str | None,
    candidate: str | None,
    *,
    stop_tokens: Iterable[str] | None = None,
) -> float:
    """
    Calcula la proporción de tokens de la consulta presentes en el candidato.

    El denominador es el número de tokens de `query`.

    Examples
    --------
    >>> token_overlap_score(
    ...     "Pontes García Rodríguez",
    ...     "As Pontes de García Rodríguez",
    ...     stop_tokens={"as", "de"},
    ... )
    1.0
    """
    query_tokens = text_tokens(
        query,
        stop_tokens=stop_tokens,
    )

    candidate_tokens = text_tokens(
        candidate,
        stop_tokens=stop_tokens,
    )

    if not query_tokens or not candidate_tokens:
        return 0.0

    return len(query_tokens & candidate_tokens) / len(query_tokens)