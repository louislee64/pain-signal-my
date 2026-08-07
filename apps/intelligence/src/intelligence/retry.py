import time
from collections.abc import Callable
from typing import TypeVar

from intelligence.observability import get_logger, log_event

logger = get_logger("intelligence.retry")

T = TypeVar("T")


def call_with_retry(
    func: Callable[[], T],
    *,
    max_attempts: int = 5,
    base_delay_seconds: float = 2.0,
    is_retryable: Callable[[Exception], bool] = lambda exc: True,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Call `func`, retrying with exponential backoff while `is_retryable`
    returns True for the raised exception. Re-raises once attempts run out
    or the exception isn't retryable."""

    sleep = sleep or time.sleep
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:
            if attempt >= max_attempts or not is_retryable(exc):
                raise

            delay = base_delay_seconds * (2 ** (attempt - 1))
            log_event(
                logger,
                "retry.attempt_failed",
                attempt=attempt,
                max_attempts=max_attempts,
                delay_seconds=delay,
                error=str(exc),
            )
            sleep(delay)
