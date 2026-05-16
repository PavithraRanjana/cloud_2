import pybreaker
import structlog
from tenacity import (
    retry, AsyncRetrying,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)
from httpx import ConnectError, ReadTimeout

logger = structlog.get_logger()


def create_circuit_breaker(name: str, fail_max: int = 5, reset_timeout: int = 30):
    class LogListener(pybreaker.CircuitBreakerListener):
        def state_change(self, cb, old_state, new_state):
            logger.warning("circuit_breaker_state_change", breaker=name,
                           old=str(old_state), new=str(new_state))

        def failure(self, cb, exc):
            logger.warning("circuit_breaker_failure", breaker=name, error=str(exc))

    return pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        listeners=[LogListener()],
        name=name,
    )


# Sync decorator — apply with @service_call_retry on regular functions
service_call_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10, jitter=2),
    retry=retry_if_exception_type((ConnectError, ReadTimeout)),
    reraise=True,
)


def async_retry():
    """
    Returns an AsyncRetrying context manager for retrying async HTTP calls.

    Usage:
        async for attempt in async_retry():
            with attempt:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()

    Retries up to 3 times on ConnectError / ReadTimeout with exponential
    back-off. Reraises after all attempts are exhausted so the circuit breaker
    can count the failure.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.3, max=8, jitter=1),
        retry=retry_if_exception_type((ConnectError, ReadTimeout)),
        reraise=True,
    )
