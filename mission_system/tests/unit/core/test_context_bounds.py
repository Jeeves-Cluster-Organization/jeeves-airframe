"""Unit tests for ContextBoundsConfig.

N.2 - Phase 4 unit tests for context boundary configuration.

Tests:
- ContextBoundsConfig limits and defaults
- get_context_bounds() accessor
- Validation that bounds prevent context explosion

Constitutional Import Boundary Note:
- Mission system layer tests the jeeves_infra layer functionality
- Direct jeeves_infra imports are acceptable here for testing
- App layer tests must use mission_system.adapters instead
"""

import pytest
# Mission system tests jeeves_infra functionality - direct import acceptable
from jeeves_infra.feature_flags import ContextBoundsConfig, context_bounds, get_context_bounds


class TestDefaults:
    """Tests for ContextBoundsConfig default values."""

    def test_l1_task_context_default(self):
        """L1 task context should have reasonable default."""
        config = ContextBoundsConfig()
        assert config.max_task_context_chars == 2000

    def test_l3_semantic_defaults(self):
        """L3 semantic memory should have reasonable defaults."""
        config = ContextBoundsConfig()
        assert config.max_semantic_snippets == 5
        assert config.max_semantic_chars_per_snippet == 400  # ~100 tokens each
        assert config.max_semantic_chars_total == 1500

    def test_l4_working_memory_defaults(self):
        """L4 working memory should have reasonable defaults."""
        config = ContextBoundsConfig()
        assert config.max_open_loops == 5
        assert config.max_conversation_turns == 10
        assert config.max_conversation_chars == 3000

    def test_l5_graph_context_default(self):
        """L5 graph context should have reasonable default."""
        config = ContextBoundsConfig()
        assert config.max_graph_relationships == 4

    def test_execution_history_defaults(self):
        """Execution history should have reasonable defaults."""
        config = ContextBoundsConfig()
        assert config.max_prior_plans == 2
        assert config.max_prior_tool_results == 10

    def test_total_context_budget(self):
        """Total context budget should be set."""
        config = ContextBoundsConfig()
        assert config.max_total_context_chars == 10000  # ~2500 tokens for context


class TestCustomization:
    """Tests for ContextBoundsConfig customization."""

    def test_custom_l1_bounds(self):
        """L1 bounds should be customizable."""
        config = ContextBoundsConfig(max_task_context_chars=5000)
        assert config.max_task_context_chars == 5000

    def test_custom_l3_bounds(self):
        """L3 bounds should be customizable."""
        config = ContextBoundsConfig(
            max_semantic_snippets=10,
            max_semantic_chars_per_snippet=500,
            max_semantic_chars_total=3000
        )
        assert config.max_semantic_snippets == 10
        assert config.max_semantic_chars_per_snippet == 500
        assert config.max_semantic_chars_total == 3000

    def test_custom_l4_bounds(self):
        """L4 bounds should be customizable."""
        config = ContextBoundsConfig(
            max_open_loops=10,
            max_conversation_turns=20,
            max_conversation_chars=5000
        )
        assert config.max_open_loops == 10
        assert config.max_conversation_turns == 20
        assert config.max_conversation_chars == 5000

    def test_custom_l5_bounds(self):
        """L5 bounds should be customizable."""
        config = ContextBoundsConfig(max_graph_relationships=5)
        assert config.max_graph_relationships == 5

    def test_custom_execution_bounds(self):
        """Execution history bounds should be customizable."""
        config = ContextBoundsConfig(
            max_prior_plans=5,
            max_prior_tool_results=20
        )
        assert config.max_prior_plans == 5
        assert config.max_prior_tool_results == 20

    def test_custom_total_budget(self):
        """Total context budget should be customizable."""
        config = ContextBoundsConfig(max_total_context_chars=16000)
        assert config.max_total_context_chars == 16000


class TestGlobalInstance:
    """Tests for global context_bounds instance and accessor."""

    def test_global_instance_exists(self):
        """Global context_bounds instance should exist."""
        assert context_bounds is not None
        assert isinstance(context_bounds, ContextBoundsConfig)

    def test_get_context_bounds_returns_global(self):
        """get_context_bounds() should return global instance."""
        result = get_context_bounds()
        assert result is context_bounds

    def test_global_has_defaults(self):
        """Global instance should have default values."""
        assert context_bounds.max_task_context_chars == 2000
        assert context_bounds.max_semantic_snippets == 5
        assert context_bounds.max_open_loops == 5


class TestPurpose:
    """Tests for bounds preventing context explosion."""

    def test_semantic_snippet_bound_reasonable(self):
        """Semantic snippet bound should prevent large context."""
        config = ContextBoundsConfig()
        # 5 snippets * 400 chars = 2000 chars max theoretical
        # Total is capped at 1500 chars anyway, so this is fine
        max_possible = config.max_semantic_snippets * config.max_semantic_chars_per_snippet
        # Theoretical max may exceed total (truncation handles this)
        # Just verify it's bounded reasonably (< 3x total)
        assert max_possible <= config.max_semantic_chars_total * 3

    def test_conversation_bound_reasonable(self):
        """Conversation bound should fit in total budget."""
        config = ContextBoundsConfig()
        # Conversation should not exceed total budget alone
        assert config.max_conversation_chars < config.max_total_context_chars

    def test_total_components_fit_budget(self):
        """Sum of component maximums should be manageable."""
        config = ContextBoundsConfig()

        # Approximate worst-case for each component
        task_max = config.max_task_context_chars
        semantic_max = config.max_semantic_chars_total
        conversation_max = config.max_conversation_chars
        # Open loops and graph are small (just metadata)
        open_loops_est = config.max_open_loops * 100  # ~100 chars per loop
        graph_est = config.max_graph_relationships * 100  # ~100 chars per relationship

        total_estimate = task_max + semantic_max + conversation_max + open_loops_est + graph_est

        # Total should be within 2x the budget (some overlap expected)
        assert total_estimate < config.max_total_context_chars * 2

    def test_bounds_are_positive(self):
        """All bounds should be positive integers."""
        config = ContextBoundsConfig()
        assert config.max_task_context_chars > 0
        assert config.max_semantic_snippets > 0
        assert config.max_semantic_chars_per_snippet > 0
        assert config.max_semantic_chars_total > 0
        assert config.max_open_loops > 0
        assert config.max_conversation_turns > 0
        assert config.max_conversation_chars > 0
        assert config.max_graph_relationships > 0
        assert config.max_prior_plans > 0
        assert config.max_prior_tool_results > 0
        assert config.max_total_context_chars > 0


class TestLocalModelFit:
    """Tests for bounds suitable for local models."""

    def test_fits_4k_context_window(self):
        """Default bounds should fit a 4K token context window."""
        config = ContextBoundsConfig()

        # Rough estimate: 1 token ~= 4 characters
        # 4K tokens = 16K characters, but we want ~60% for input
        # So ~10K characters is reasonable max input

        assert config.max_total_context_chars <= 10000

    def test_leaves_room_for_response(self):
        """Bounds should leave room for LLM response generation."""
        config = ContextBoundsConfig()

        # If context is 10K chars, that's ~2.5K tokens
        # With 18-24K context window (qwen2.5-7b), this leaves ample room
        # for system prompt (~1K), code content (~12K), and response (~2-3K)

        assert config.max_total_context_chars <= 12000  # ~3K tokens max for context

    def test_semantic_snippets_bounded(self):
        """Semantic snippets should not dominate context."""
        config = ContextBoundsConfig()

        # Semantic memory should be < 25% of total budget
        semantic_ratio = config.max_semantic_chars_total / config.max_total_context_chars
        assert semantic_ratio < 0.25

    def test_conversation_bounded(self):
        """Conversation history should not dominate context."""
        config = ContextBoundsConfig()

        # Conversation should be < 50% of total budget
        conversation_ratio = config.max_conversation_chars / config.max_total_context_chars
        assert conversation_ratio < 0.50
