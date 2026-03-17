"""Error handling strategy — Dada Bhagwan's pratikraman.

Errors generate corrections, not silence.  This module provides:
- ``@resilient``: decorator for retrying transient failures with logging
- Error classification constants for triage decisions
- ``escalate``: structured error escalation with context
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from typing import Any, Callable, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

# Error classification
CRITICAL = logging.WARNING   # Escalate: subsystem init, coordination, task creation
EXPECTED = logging.DEBUG     # Keep quiet: optional feature unavailable, import fallback
TRANSIENT = logging.INFO     # Retry: network, rate-limit, file lock contention


def resilient(
    *,
    retries: int = 2,
    backoff: float = 1.0,
    level: int = logging.WARNING,
    label: str = "",
    swallow: bool = False,
) -> Callable[[_F], _F]:
    """Decorator for functions that may fail transiently.

    Dada Bhagwan's pratikraman: errors generate corrections, not silence.

    Args:
        retries: Number of retry attempts (0 = no retry, just log).
        backoff: Seconds between retries (doubles each attempt).
        level: Logging level for failures (WARNING for critical, DEBUG for expected).
        label: Human-readable label for log messages.
        swallow: If True, return None on final failure instead of raising.
    """

    def decorator(fn: _F) -> _F:
        fn_label = label or fn.__qualname__

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                logger = logging.getLogger(fn.__module__)
                last_exc: Exception | None = None
                delay = backoff

                for attempt in range(retries + 1):
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as exc:
                        last_exc = exc
                        if attempt < retries:
                            logger.log(
                                TRANSIENT,
                                "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                                fn_label, attempt + 1, retries + 1, exc, delay,
                            )
                            await asyncio.sleep(delay)
                            delay *= 2
                        else:
                            logger.log(
                                level,
                                "%s: all %d attempts exhausted: %s",
                                fn_label, retries + 1, exc,
                            )

                if swallow:
                    return None
                raise last_exc  # type: ignore[misc]

            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                logger = logging.getLogger(fn.__module__)
                last_exc: Exception | None = None
                delay = backoff

                for attempt in range(retries + 1):
                    try:
                        return fn(*args, **kwargs)
                    except Exception as exc:
                        last_exc = exc
                        if attempt < retries:
                            logger.log(
                                TRANSIENT,
                                "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                                fn_label, attempt + 1, retries + 1, exc, delay,
                            )
                            import time
                            time.sleep(delay)
                            delay *= 2
                        else:
                            logger.log(
                                level,
                                "%s: all %d attempts exhausted: %s",
                                fn_label, retries + 1, exc,
                            )

                if swallow:
                    return None
                raise last_exc  # type: ignore[misc]

            return sync_wrapper  # type: ignore[return-value]

    return decorator


def escalate(
    message: str,
    *,
    exc: Exception | None = None,
    level: int = CRITICAL,
    subsystem: str = "unknown",
    logger_name: str | None = None,
) -> None:
    """Structured error escalation with context.

    Use instead of bare ``logger.debug("failed: %s", e)`` to ensure
    errors are visible at the appropriate level.
    """
    log = logging.getLogger(logger_name or __name__)
    extra = f" [{subsystem}]" if subsystem != "unknown" else ""
    if exc:
        log.log(level, "%s%s: %s", message, extra, exc, exc_info=(level >= logging.WARNING))
    else:
        log.log(level, "%s%s", message, extra)
