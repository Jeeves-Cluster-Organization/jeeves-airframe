"""Tests for M7: Chain-of-Thought Proxy utility.

Tests extraction and stripping of reasoning from LLM output,
enabling debugging without exposing internal reasoning to users.
"""

import pytest
from mission_system.common.cot_proxy import (
    extract_and_strip_cot,
    extract_cot_only,
    strip_cot_only,
    has_cot_markers,
    format_cot_for_logging,
    inject_cot_instruction,
    CoTProcessor,
)


class TestExtractAndStripCot:
    """Test suite for extract_and_strip_cot() function."""

    def test_no_cot_markers(self):
        """Text without CoT markers returned unchanged."""
        text = "This is a simple response."
        clean, cot = extract_and_strip_cot(text)
        assert clean == text
        assert cot is None

    def test_extracts_thinking_tags(self):
        """<thinking> tags extracted."""
        text = "<thinking>My analysis here</thinking>Final answer."
        clean, cot = extract_and_strip_cot(text)
        assert clean.strip() == "Final answer."
        assert "My analysis here" in cot
        assert "[thinking]" in cot

    def test_extracts_reasoning_tags(self):
        """<reasoning> tags extracted."""
        text = "<reasoning>Step by step</reasoning>The result is 42."
        clean, cot = extract_and_strip_cot(text)
        assert clean.strip() == "The result is 42."
        assert "Step by step" in cot

    def test_extracts_scratchpad_tags(self):
        """<scratchpad> tags extracted."""
        text = "<scratchpad>Working memory</scratchpad>Here's what I found."
        clean, cot = extract_and_strip_cot(text)
        assert clean.strip() == "Here's what I found."
        assert "Working memory" in cot

    def test_extracts_multiple_cot_blocks(self):
        """Multiple CoT blocks all extracted."""
        text = "<thinking>First thought</thinking>Middle.<reasoning>More analysis</reasoning>End."
        clean, cot = extract_and_strip_cot(text)
        assert clean.strip() == "Middle.End."
        assert "First thought" in cot
        assert "More analysis" in cot

    def test_handles_multiline_cot(self):
        """Multiline content in CoT blocks extracted."""
        text = """<thinking>
Line 1
Line 2
Line 3
</thinking>
Final answer."""
        clean, cot = extract_and_strip_cot(text)
        assert "Final answer" in clean
        assert "Line 1" in cot
        assert "Line 2" in cot
        assert "Line 3" in cot

    def test_cleans_extra_whitespace(self):
        """Extra whitespace from removal cleaned up."""
        text = "<thinking>x</thinking>\n\n\n\n\nFinal."
        clean, cot = extract_and_strip_cot(text)
        assert "\n\n\n" not in clean

    def test_empty_input(self):
        """Empty string handled."""
        clean, cot = extract_and_strip_cot("")
        assert clean == ""
        assert cot is None

    def test_bracket_style_tags(self):
        """[thinking]...[/thinking] style tags extracted."""
        text = "[thinking]My thoughts[/thinking]Answer here."
        clean, cot = extract_and_strip_cot(text)
        assert clean.strip() == "Answer here."
        assert "My thoughts" in cot


class TestExtractCotOnly:
    """Test suite for extract_cot_only() function."""

    def test_extracts_cot_content(self):
        """Returns only CoT content."""
        text = "<thinking>Important reasoning</thinking>Answer"
        cot = extract_cot_only(text)
        assert "Important reasoning" in cot
        assert "Answer" not in cot

    def test_returns_none_when_no_cot(self):
        """Returns None when no CoT found."""
        text = "Just a plain response"
        cot = extract_cot_only(text)
        assert cot is None


class TestStripCotOnly:
    """Test suite for strip_cot_only() function."""

    def test_strips_cot_returns_clean(self):
        """Returns text with CoT removed."""
        text = "<thinking>Hidden</thinking>Visible answer"
        clean = strip_cot_only(text)
        assert "Hidden" not in clean
        assert "Visible answer" in clean

    def test_unchanged_when_no_cot(self):
        """Text unchanged when no CoT present."""
        text = "Plain text response"
        clean = strip_cot_only(text)
        assert clean == text


class TestHasCotMarkers:
    """Test suite for has_cot_markers() function."""

    def test_detects_thinking_tag(self):
        """Detects <thinking> opening tag."""
        assert has_cot_markers("<thinking>content")
        assert has_cot_markers("prefix <THINKING> suffix")

    def test_detects_reasoning_tag(self):
        """Detects <reasoning> opening tag."""
        assert has_cot_markers("<reasoning>x")

    def test_returns_false_for_plain_text(self):
        """Returns False for plain text."""
        assert not has_cot_markers("Just regular text")
        assert not has_cot_markers("Even with < angle > brackets")


class TestFormatCotForLogging:
    """Test suite for format_cot_for_logging() function."""

    def test_none_input(self):
        """None input returns placeholder."""
        result = format_cot_for_logging(None)
        assert result == "(no CoT)"

    def test_short_cot_unchanged(self):
        """Short CoT returned unchanged."""
        cot = "Short reasoning"
        result = format_cot_for_logging(cot, max_length=100)
        assert result == cot

    def test_long_cot_truncated(self):
        """Long CoT truncated with indicator."""
        cot = "x" * 1000
        result = format_cot_for_logging(cot, max_length=100)
        assert len(result) < 150  # 100 + indicator
        assert "truncated" in result


class TestInjectCotInstruction:
    """Test suite for inject_cot_instruction() function."""

    def test_adds_instruction(self):
        """Adds CoT instruction to prompt."""
        prompt = "Original prompt here."
        result = inject_cot_instruction(prompt)
        assert "Original prompt here" in result
        assert "<thinking>" in result
        assert "</thinking>" in result
        assert "step by step" in result.lower()

    def test_custom_style(self):
        """Supports custom CoT style."""
        prompt = "Prompt"
        result = inject_cot_instruction(prompt, cot_style="analysis")
        assert "<analysis>" in result
        assert "</analysis>" in result


class TestCoTProcessor:
    """Test suite for CoTProcessor class."""

    def test_processes_response(self):
        """Processes response and extracts CoT."""
        processor = CoTProcessor(agent_name="test_agent")
        raw = "<thinking>Internal</thinking>External"
        clean = processor.process_response(raw)
        assert clean.strip() == "External"

    def test_tracks_history(self):
        """Keeps history of CoT extractions."""
        processor = CoTProcessor(agent_name="test")
        processor.process_response("<thinking>First</thinking>A")
        processor.process_response("<thinking>Second</thinking>B")

        history = processor.get_recent_cot(count=2)
        assert len(history) == 2
        assert "First" in history[0][1]
        assert "Second" in history[1][1]

    def test_limits_history_size(self):
        """History capped at 10 entries."""
        processor = CoTProcessor()
        for i in range(15):
            processor.process_response(f"<thinking>Entry {i}</thinking>Response")

        history = processor.get_recent_cot(count=20)
        assert len(history) <= 10

    def test_clears_history(self):
        """History can be cleared."""
        processor = CoTProcessor()
        processor.process_response("<thinking>x</thinking>y")
        processor.clear_history()
        assert len(processor.get_recent_cot()) == 0

    def test_no_cot_not_stored(self):
        """Responses without CoT don't add to history."""
        processor = CoTProcessor()
        processor.process_response("Plain response without CoT")
        assert len(processor.get_recent_cot()) == 0
