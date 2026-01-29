"""Unit tests for thresholds.py - operational thresholds.

Per Avionics Constitution: thresholds.py provides operational thresholds
for confirmations, retries, and L7 governance.
"""

import pytest


class TestConfirmationThresholds:
    """Tests for confirmation system thresholds."""

    def test_confirmation_detection_confidence_range(self):
        """Confirm detection confidence is in valid range."""
        from jeeves_infra.thresholds import CONFIRMATION_DETECTION_CONFIDENCE

        assert 0.0 <= CONFIRMATION_DETECTION_CONFIDENCE <= 1.0
        assert CONFIRMATION_DETECTION_CONFIDENCE == 0.7  # Expected value

    def test_confirmation_interpretation_confidence_range(self):
        """Confirm interpretation confidence is in valid range."""
        from jeeves_infra.thresholds import CONFIRMATION_INTERPRETATION_CONFIDENCE

        assert 0.0 <= CONFIRMATION_INTERPRETATION_CONFIDENCE <= 1.0

    def test_confirmation_timeout_is_positive(self):
        """Confirm timeout is positive."""
        from jeeves_infra.thresholds import CONFIRMATION_TIMEOUT_SECONDS

        assert CONFIRMATION_TIMEOUT_SECONDS > 0


class TestPlanningThresholds:
    """Tests for planning & execution thresholds."""

    def test_plan_confidence_range(self):
        """Plan confidence thresholds are in valid range."""
        from jeeves_infra.thresholds import PLAN_MIN_CONFIDENCE, PLAN_HIGH_CONFIDENCE

        assert 0.0 <= PLAN_MIN_CONFIDENCE <= 1.0
        assert 0.0 <= PLAN_HIGH_CONFIDENCE <= 1.0
        assert PLAN_MIN_CONFIDENCE <= PLAN_HIGH_CONFIDENCE

    def test_max_retry_attempts_is_positive(self):
        """Max retry attempts is a positive integer."""
        from jeeves_infra.thresholds import MAX_RETRY_ATTEMPTS

        assert MAX_RETRY_ATTEMPTS > 0
        assert isinstance(MAX_RETRY_ATTEMPTS, int)


class TestCriticThresholds:
    """Tests for critic & validation thresholds."""

    def test_critic_thresholds_ordering(self):
        """Critic thresholds should be ordered correctly."""
        from jeeves_infra.thresholds import (
            CRITIC_APPROVAL_THRESHOLD,
            CRITIC_HIGH_CONFIDENCE,
            CRITIC_MEDIUM_CONFIDENCE,
            CRITIC_LOW_CONFIDENCE,
            CRITIC_DEFAULT_CONFIDENCE,
        )

        # All in valid range
        for threshold in [
            CRITIC_APPROVAL_THRESHOLD,
            CRITIC_HIGH_CONFIDENCE,
            CRITIC_MEDIUM_CONFIDENCE,
            CRITIC_LOW_CONFIDENCE,
            CRITIC_DEFAULT_CONFIDENCE,
        ]:
            assert 0.0 <= threshold <= 1.0

        # Ordering: high > medium > low > default
        assert CRITIC_HIGH_CONFIDENCE >= CRITIC_MEDIUM_CONFIDENCE
        assert CRITIC_MEDIUM_CONFIDENCE >= CRITIC_LOW_CONFIDENCE
        assert CRITIC_LOW_CONFIDENCE >= CRITIC_DEFAULT_CONFIDENCE

    def test_meta_validator_thresholds(self):
        """Meta-validator thresholds are in valid range."""
        from jeeves_infra.thresholds import (
            META_VALIDATOR_PASS_THRESHOLD,
            META_VALIDATOR_APPROVED_CONFIDENCE,
            META_VALIDATOR_REJECTED_CONFIDENCE,
        )

        assert 0.0 <= META_VALIDATOR_PASS_THRESHOLD <= 1.0
        assert 0.0 <= META_VALIDATOR_APPROVED_CONFIDENCE <= 1.0
        assert 0.0 <= META_VALIDATOR_REJECTED_CONFIDENCE <= 1.0

        # Approved should be higher than rejected
        assert META_VALIDATOR_APPROVED_CONFIDENCE > META_VALIDATOR_REJECTED_CONFIDENCE


class TestSearchThresholds:
    """Tests for search & matching thresholds."""

    def test_fuzzy_match_min_score(self):
        """Fuzzy match min score is in valid range."""
        from jeeves_infra.thresholds import FUZZY_MATCH_MIN_SCORE

        assert 0.0 <= FUZZY_MATCH_MIN_SCORE <= 1.0

    def test_semantic_search_min_similarity(self):
        """Semantic search min similarity is in valid range."""
        from jeeves_infra.thresholds import SEMANTIC_SEARCH_MIN_SIMILARITY

        assert 0.0 <= SEMANTIC_SEARCH_MIN_SIMILARITY <= 1.0

    def test_hybrid_search_weights_sum_to_one(self):
        """Hybrid search weights should sum to 1.0."""
        from jeeves_infra.thresholds import (
            HYBRID_SEARCH_FUZZY_WEIGHT,
            HYBRID_SEARCH_SEMANTIC_WEIGHT,
        )

        assert 0.0 <= HYBRID_SEARCH_FUZZY_WEIGHT <= 1.0
        assert 0.0 <= HYBRID_SEARCH_SEMANTIC_WEIGHT <= 1.0
        assert abs(HYBRID_SEARCH_FUZZY_WEIGHT + HYBRID_SEARCH_SEMANTIC_WEIGHT - 1.0) < 0.01


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


class TestWorkingMemoryThresholds:
    """Tests for working memory thresholds."""

    def test_session_thresholds_are_positive(self):
        """Session thresholds should be positive."""
        from jeeves_infra.thresholds import (
            SESSION_SUMMARIZATION_TURN_THRESHOLD,
            SESSION_TOKEN_BUDGET_THRESHOLD,
            SESSION_IDLE_TIMEOUT_MINUTES,
        )

        assert SESSION_SUMMARIZATION_TURN_THRESHOLD > 0
        assert SESSION_TOKEN_BUDGET_THRESHOLD > 0
        assert SESSION_IDLE_TIMEOUT_MINUTES > 0

    def test_open_loop_stale_days_is_positive(self):
        """Open loop stale days should be positive."""
        from jeeves_infra.thresholds import OPEN_LOOP_STALE_DAYS

        assert OPEN_LOOP_STALE_DAYS > 0


class TestLatencyBudgets:
    """Tests for latency budgets."""

    def test_max_request_latency_is_positive(self):
        """Max request latency should be positive."""
        from jeeves_infra.thresholds import MAX_REQUEST_LATENCY_MS

        assert MAX_REQUEST_LATENCY_MS > 0
        assert MAX_REQUEST_LATENCY_MS == 300000  # 5 minutes



