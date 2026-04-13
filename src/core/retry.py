import functools
import random
from threading import Event

from src.core.logger import get_logger

logger = get_logger(__name__)
_BACKOFF_EVENT = Event()


def retry(max_attempts: int = 3, backoff_base: float = 2.0, exceptions: tuple = (Exception,)):

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_attempts:
                                                                        
                        delay = backoff_base ** (attempt - 1) + random.uniform(0, 1)
                        logger.warning(
                            "Attempt %d/%d for %s failed: %s. Retrying in %.1fs...",
                            attempt,
                            max_attempts,
                            func.__name__,
                            exc,
                            delay,
                        )
                        _BACKOFF_EVENT.wait(delay)
                    else:
                        logger.error(
                            "All %d attempts for %s exhausted. Last error: %s",
                            max_attempts,
                            func.__name__,
                            exc,
                        )
            raise last_exception

        return wrapper

    return decorator
