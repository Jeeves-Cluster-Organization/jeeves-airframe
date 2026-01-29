"""Unit tests for utility functions.

Tests JSONRepairKit, string normalization, and truncation utilities.
"""

import pytest


class TestJSONRepairKit:
    """Tests for JSONRepairKit utility."""

    def test_extract_json_from_code_block(self):
        """Test extracting JSON from code block."""
        from jeeves_infra.utils import JSONRepairKit

        text = '```json\n{"key": "value"}\n```'
        extracted = JSONRepairKit.extract_json(text)

        assert extracted == '{"key": "value"}'

    def test_extract_json_from_text(self):
        """Test extracting JSON from surrounding text."""
        from jeeves_infra.utils import JSONRepairKit

        text = 'Here is the result: {"key": "value"} and some more text'
        extracted = JSONRepairKit.extract_json(text)

        import json
        parsed = json.loads(extracted)
        assert parsed["key"] == "value"

    def test_repair_trailing_comma(self):
        """Test repairing JSON with trailing comma."""
        from jeeves_infra.utils import JSONRepairKit

        broken = '{"a": 1, "b": 2,}'
        repaired = JSONRepairKit.repair_json(broken)

        import json
        parsed = json.loads(repaired)
        assert parsed["a"] == 1
        assert parsed["b"] == 2

    def test_repair_single_quotes(self):
        """Test repairing JSON with single quotes."""
        from jeeves_infra.utils import JSONRepairKit

        broken = "{'key': 'value'}"
        repaired = JSONRepairKit.repair_json(broken)

        import json
        parsed = json.loads(repaired)
        assert parsed["key"] == "value"

    def test_parse_lenient_valid_json(self):
        """Test parsing valid JSON."""
        from jeeves_infra.utils import JSONRepairKit

        valid = '{"key": "value", "number": 42}'
        parsed = JSONRepairKit.parse_lenient(valid)

        assert parsed["key"] == "value"
        assert parsed["number"] == 42

    def test_parse_lenient_broken_json(self):
        """Test parsing broken JSON with repair."""
        from jeeves_infra.utils import JSONRepairKit

        broken = '{"items": [1, 2, 3,]}'
        parsed = JSONRepairKit.parse_lenient(broken)

        assert parsed is not None
        assert parsed["items"] == [1, 2, 3]


class TestNormalizeStringList:
    """Tests for normalize_string_list utility."""

    def test_normalize_simple_list(self):
        """Test normalizing a simple string list."""
        from jeeves_infra.utils import normalize_string_list

        items = ["  item1  ", "item2", "  item3"]
        normalized = normalize_string_list(items)

        assert "item1" in normalized
        assert "item2" in normalized
        assert "item3" in normalized

    def test_normalize_from_comma_string(self):
        """Test normalizing comma-separated string."""
        from jeeves_infra.utils import normalize_string_list

        text = "item1, item2, item3"
        normalized = normalize_string_list(text)

        assert normalized == ["item1", "item2", "item3"]

    def test_normalize_from_newline_string(self):
        """Test normalizing newline-separated string."""
        from jeeves_infra.utils import normalize_string_list

        text = "item1\nitem2\nitem3"
        normalized = normalize_string_list(text)

        assert normalized == ["item1", "item2", "item3"]

    def test_normalize_none(self):
        """Test normalizing None."""
        from jeeves_infra.utils import normalize_string_list

        normalized = normalize_string_list(None)

        assert normalized == []

    def test_normalize_empty_list(self):
        """Test normalizing empty list."""
        from jeeves_infra.utils import normalize_string_list

        normalized = normalize_string_list([])

        assert normalized == []


class TestTruncateString:
    """Tests for truncate_string utility."""

    def test_truncate_long_string(self):
        """Test truncating a long string."""
        from jeeves_infra.utils import truncate_string

        long_string = "a" * 10000
        truncated = truncate_string(long_string, max_length=100)

        assert len(truncated) <= 100
        assert truncated.endswith("...")

    def test_truncate_short_string(self):
        """Test that short strings are not truncated."""
        from jeeves_infra.utils import truncate_string

        short = "Hello, world!"
        truncated = truncate_string(short, max_length=100)

        assert truncated == short

    def test_truncate_exact_length(self):
        """Test string at exact max length."""
        from jeeves_infra.utils import truncate_string

        text = "a" * 100
        truncated = truncate_string(text, max_length=100)

        assert truncated == text

    def test_truncate_with_custom_suffix(self):
        """Test truncation with custom suffix."""
        from jeeves_infra.utils import truncate_string

        text = "a" * 200
        truncated = truncate_string(text, max_length=100, suffix=" [truncated]")

        assert truncated.endswith(" [truncated]")
        assert len(truncated) <= 100

    def test_truncate_empty_string(self):
        """Test truncating empty string."""
        from jeeves_infra.utils import truncate_string

        truncated = truncate_string("", max_length=100)

        assert truncated == ""
