"""Tests for M6: Prompt Compression utility.

Tests the heuristic compression for LLM prompts, essential for local
models with limited context windows (3B-14B on consumer hardware).
"""

import pytest
from mission_system.common.prompt_compression import (
    compress_for_prompt,
    compress_json_for_prompt,
    estimate_tokens,
    compress_to_token_budget,
    get_compression_stats,
)


class TestCompressForPrompt:
    """Test suite for compress_for_prompt() function."""

    def test_short_text_unchanged(self):
        """Text under limit is returned unchanged."""
        text = "This is short."
        result = compress_for_prompt(text, max_chars=100)
        assert result == text

    def test_collapses_multiple_newlines(self):
        """Multiple newlines collapsed to double."""
        text = "Line 1\n\n\n\n\nLine 2"
        result = compress_for_prompt(text, max_chars=50)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_collapses_multiple_spaces(self):
        """Multiple spaces collapsed to single."""
        text = "Word    with     many    spaces"
        result = compress_for_prompt(text, max_chars=50)
        assert "    " not in result
        assert "with" in result

    def test_strips_markdown_bold(self):
        """Bold markdown removed when needed."""
        text = "**Bold text** and **more bold**" + " " * 100
        result = compress_for_prompt(text, max_chars=50)
        assert "**" not in result
        assert "Bold text" in result

    def test_strips_markdown_code_backticks(self):
        """Inline code backticks removed when needed."""
        text = "`code` and `more code`" + " " * 100
        result = compress_for_prompt(text, max_chars=50)
        assert "`" not in result
        assert "code" in result

    def test_shortens_verbose_phrases(self):
        """Common verbose phrases shortened."""
        text = "In order to complete this task due to the fact that it is important" + " " * 100
        result = compress_for_prompt(text, max_chars=80)
        # "In order to" -> "to", "due to the fact that" -> "because"
        assert len(result) < len(text)

    def test_truncates_with_indicator(self):
        """Very long text truncated with indicator."""
        text = "Word " * 500  # Very long
        result = compress_for_prompt(text, max_chars=100)
        assert "[... truncated" in result
        assert len(result) <= 150  # Allow for indicator

    def test_finds_sentence_boundary_for_truncation(self):
        """Truncation tries to break at sentence end."""
        text = "First sentence. Second sentence. Third sentence. " * 10
        result = compress_for_prompt(text, max_chars=60)
        # Should end at a sentence boundary
        assert result.endswith("[... truncated for context limits]") or result.endswith(".")


class TestCompressJsonForPrompt:
    """Test suite for compress_json_for_prompt() function."""

    def test_short_json_minified(self):
        """Short JSON has whitespace removed (semantically safe)."""
        json_str = '{"key": "value"}'
        result = compress_json_for_prompt(json_str, max_chars=100)
        # Whitespace after colon is removed
        assert result == '{"key":"value"}'

    def test_removes_json_whitespace(self):
        """Whitespace in JSON removed."""
        json_str = '{\n    "key": "value",\n    "key2": "value2"\n}'
        result = compress_json_for_prompt(json_str, max_chars=50)
        assert "    " not in result or "...[truncated]" in result

    def test_truncates_long_json(self):
        """Very long JSON truncated."""
        json_str = '{"data": "' + "x" * 2000 + '"}'
        result = compress_json_for_prompt(json_str, max_chars=100)
        assert "...[truncated]}" in result
        assert len(result) <= 100


class TestEstimateTokens:
    """Test suite for estimate_tokens() function."""

    def test_empty_string(self):
        """Empty string = 0 tokens."""
        assert estimate_tokens("") == 0

    def test_short_text(self):
        """Short text estimation."""
        # ~4 chars per token
        text = "Hello world!"  # 12 chars
        tokens = estimate_tokens(text)
        assert tokens == 3  # 12 // 4

    def test_longer_text(self):
        """Longer text estimation."""
        text = "a" * 400  # 400 chars
        tokens = estimate_tokens(text)
        assert tokens == 100  # 400 // 4


class TestCompressToTokenBudget:
    """Test suite for compress_to_token_budget() function."""

    def test_text_within_budget_unchanged(self):
        """Text within budget unchanged."""
        text = "Short text"
        result = compress_to_token_budget(text, token_budget=100)
        assert result == text

    def test_preserves_start(self):
        """Start of text preserved."""
        text = "Important start. " + "filler " * 100
        result = compress_to_token_budget(text, token_budget=50, preserve_start_chars=50)
        assert result.startswith("Important start.")

    def test_compresses_rest(self):
        """Rest of text compressed to fit budget."""
        text = "Start. " + "x" * 1000
        result = compress_to_token_budget(text, token_budget=50)  # ~200 chars
        assert len(result) < len(text)


class TestGetCompressionStats:
    """Test suite for get_compression_stats() function."""

    def test_stats_calculated_correctly(self):
        """Compression stats are accurate."""
        original = "x" * 100
        compressed = "x" * 50

        stats = get_compression_stats(original, compressed)

        assert stats["original_chars"] == 100
        assert stats["compressed_chars"] == 50
        assert stats["chars_saved"] == 50
        assert stats["compression_ratio"] == 0.5
        assert stats["estimated_tokens_saved"] == 12  # 50 // 4

    def test_no_compression_needed(self):
        """Stats when no compression occurred."""
        text = "same"
        stats = get_compression_stats(text, text)

        assert stats["chars_saved"] == 0
        assert stats["compression_ratio"] == 1.0

    def test_empty_original(self):
        """Stats handle empty original."""
        stats = get_compression_stats("", "")
        assert stats["compression_ratio"] == 1.0
