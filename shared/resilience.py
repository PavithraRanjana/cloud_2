import pybreaker
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
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


service_call_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=0.5, max=10, jitter=2),
    retry=retry_if_exception_type((ConnectError, ReadTimeout)),
    reraise=True,
)
