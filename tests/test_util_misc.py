"""
Tests for scitrera_app_framework.util.misc module.
"""
import time
import pytest
from scitrera_app_framework.util.misc import no_op, now_ms


class TestNoOp:
    """Tests for no_op function."""

    def test_no_op_returns_none(self):
        result = no_op()
        assert result is None

    def test_no_op_accepts_args(self):
        result = no_op(1, 2, 3)
        assert result is None

    def test_no_op_accepts_kwargs(self):
        result = no_op(a=1, b=2, c=3)
        assert result is None

    def test_no_op_accepts_mixed_args(self):
        result = no_op(1, 2, a=3, b=4)
        assert result is None


class TestNowMs:
    """Tests for now_ms function."""

    def test_returns_integer(self):
        result = now_ms()
        assert isinstance(result, int)

    def test_returns_milliseconds(self):
        before = time.time_ns() // 1_000_000
        result = now_ms()
        after = time.time_ns() // 1_000_000

        assert before <= result <= after

    def test_increases_over_time(self):
        first = now_ms()
        time.sleep(0.01)  # Sleep 10ms
        second = now_ms()

        assert second > first

    def test_reasonable_magnitude(self):
        result = now_ms()
        # Should be roughly current unix time in milliseconds
        # As of 2024, this should be around 1.7e12
        assert result > 1_000_000_000_000  # Greater than year 2001 in ms
        assert result < 3_000_000_000_000  # Less than year 2065 in ms
