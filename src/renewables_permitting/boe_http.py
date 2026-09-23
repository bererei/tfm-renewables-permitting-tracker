"""Política HTTP compartida para las lecturas oficiales del BOE."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import requests


SOURCE_MAX_RETRIES = 3
SOURCE_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
SOURCE_RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
SOURCE_RETRYABLE_REQUEST_EXCEPTIONS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

_LOGGER = logging.getLogger(__name__)
_ResponseT = TypeVar("_ResponseT")


def request_with_transient_retries(
    request: Callable[..., _ResponseT],
    url: str,
    *,
    operation: str,
    identifier: str,
    request_kwargs: Mapping[str, Any],
) -> _ResponseT:
    """Ejecuta una petición y reintenta únicamente fallos HTTP transitorios.

    ``SOURCE_MAX_RETRIES`` son reintentos adicionales: con la política actual
    se realizan como máximo cuatro peticiones (la inicial y tres reintentos).
    Las respuestas y excepciones finales se devuelven o propagan sin cambiar
    para que el consumidor conserve su contrato de errores.
    """

    max_attempts = SOURCE_MAX_RETRIES + 1
    for attempt in range(1, max_attempts + 1):
        try:
            response = request(url, **request_kwargs)
        except SOURCE_RETRYABLE_REQUEST_EXCEPTIONS as error:
            cause = f"{type(error).__name__}: {error}"
            if attempt == max_attempts:
                _LOGGER.error(
                    "BOE source retries exhausted: operation=%s "
                    "identifier=%s attempt=%d/%d cause=%s",
                    operation,
                    identifier,
                    attempt,
                    max_attempts,
                    cause,
                )
                raise
        else:
            status_code = int(response.status_code)
            if status_code not in SOURCE_RETRYABLE_HTTP_STATUS_CODES:
                if attempt > 1:
                    _LOGGER.info(
                        "BOE source recovered: operation=%s identifier=%s "
                        "attempt=%d/%d",
                        operation,
                        identifier,
                        attempt,
                        max_attempts,
                    )
                return response
            cause = f"HTTP {status_code}"
            if attempt == max_attempts:
                _LOGGER.error(
                    "BOE source retries exhausted: operation=%s "
                    "identifier=%s attempt=%d/%d cause=%s",
                    operation,
                    identifier,
                    attempt,
                    max_attempts,
                    cause,
                )
                return response

        delay = SOURCE_RETRY_BACKOFF_SECONDS[attempt - 1]
        _LOGGER.warning(
            "BOE source retry: operation=%s identifier=%s attempt=%d/%d "
            "cause=%s delay_seconds=%g",
            operation,
            identifier,
            attempt,
            max_attempts,
            cause,
            delay,
        )
        time.sleep(delay)

    raise AssertionError("unreachable retry state")
