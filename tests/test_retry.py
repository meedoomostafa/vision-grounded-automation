from unittest.mock import patch

from src.core.retry import retry


class _Counter:
    """Track call count for retry tests."""
    def __init__(self):
        self.count = 0


def test_retry_succeeds_on_first_attempt():
    counter = _Counter()

    @retry(max_attempts=3, backoff_base=0.01, exceptions=(ValueError,))
    def succeed():
        counter.count += 1
        return "ok"

    assert succeed() == "ok"
    assert counter.count == 1


def test_retry_succeeds_after_failures():
    counter = _Counter()

    @retry(max_attempts=3, backoff_base=0.01, exceptions=(ValueError,))
    def flaky():
        counter.count += 1
        if counter.count < 3:
            raise ValueError(f"fail #{counter.count}")
        return "recovered"

    assert flaky() == "recovered"
    assert counter.count == 3


def test_retry_exhaustion_raises():
    counter = _Counter()

    @retry(max_attempts=2, backoff_base=0.01, exceptions=(RuntimeError,))
    def always_fails():
        counter.count += 1
        raise RuntimeError("permanent failure")

    try:
        always_fails()
        assert False, "Should have raised"
    except RuntimeError as exc:
        assert "permanent failure" in str(exc)
    assert counter.count == 2


def test_retry_ignores_unexpected_exceptions():
    """Retry should only catch specified exception types."""
    counter = _Counter()

    @retry(max_attempts=3, backoff_base=0.01, exceptions=(ValueError,))
    def wrong_error():
        counter.count += 1
        raise TypeError("not a ValueError")

    try:
        wrong_error()
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
    # Only 1 attempt since TypeError is not in the exceptions tuple
    assert counter.count == 1


def test_retry_backoff_increases():
    """Verify delay increases with each attempt."""
    delays = []

    def mock_sleep(duration):
        delays.append(duration)
        # Don't actually sleep in tests

    counter = _Counter()

    @retry(max_attempts=3, backoff_base=2.0, exceptions=(ValueError,))
    def fail_twice():
        counter.count += 1
        if counter.count < 3:
            raise ValueError("fail")
        return "ok"

    with patch("src.core.retry._BACKOFF_EVENT.wait", side_effect=mock_sleep):
        result = fail_twice()

    assert result == "ok"
    assert len(delays) == 2
    # Second delay should be larger than first (exponential)
    assert delays[1] > delays[0]
