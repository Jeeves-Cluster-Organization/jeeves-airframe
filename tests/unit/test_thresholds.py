"""Unit tests for thresholds.py — infrastructure operational thresholds.

Agent-specific thresholds have been moved to capability config.
This file tests only the infrastructure thresholds that remain.
"""

import pytest


class TestL7GovernanceThresholds:
    """Tests for L7 governance / tool health thresholds."""

    def test_error_rate_ordering(self):
        """Degraded threshold should be lower than quarantine."""
        from jeeves_infra.thresholds import (
            TOOL_DEGRADED_ERROR_RATE,
            TOOL_QUARANTINE_ERROR_RATE,
        )

        assert 0.0 <= TOOL_DEGRADED_ERROR_RATE <= 1.0
        assert 0.0 <= TOOL_QUARANTINE_ERROR_RATE <= 1.0
        assert TOOL_DEGRADED_ERROR_RATE < TOOL_QUARANTINE_ERROR_RATE

    def test_min_invocations_is_positive(self):
        """Minimum invocations for stats should be positive."""
        from jeeves_infra.thresholds import TOOL_MIN_INVOCATIONS_FOR_STATS

        assert TOOL_MIN_INVOCATIONS_FOR_STATS > 0

    def test_quarantine_duration_is_positive(self):
        """Quarantine duration should be positive."""
        from jeeves_infra.thresholds import TOOL_QUARANTINE_DURATION_HOURS

        assert TOOL_QUARANTINE_DURATION_HOURS > 0


class TestOperationalLimits:
    """Tests for operational limit thresholds."""

    def test_max_retry_attempts_is_positive(self):
        """Max retry attempts is a positive integer."""
        from jeeves_infra.thresholds import MAX_RETRY_ATTEMPTS

        assert MAX_RETRY_ATTEMPTS > 0
        assert isinstance(MAX_RETRY_ATTEMPTS, int)

    def test_confirmation_timeout_is_positive(self):
        """Confirm timeout is positive."""
        from jeeves_infra.thresholds import CONFIRMATION_TIMEOUT_SECONDS

        assert CONFIRMATION_TIMEOUT_SECONDS > 0

    def test_max_request_latency_is_positive(self):
        """Max request latency should be positive."""
        from jeeves_infra.thresholds import MAX_REQUEST_LATENCY_MS

        assert MAX_REQUEST_LATENCY_MS > 0
        assert MAX_REQUEST_LATENCY_MS == 300000  # 5 minutes
