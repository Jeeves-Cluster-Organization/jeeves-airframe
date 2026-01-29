"""JSON repair utilities for handling malformed LLM outputs."""

import json
import re
from typing import Any, Optional


class JSONRepairKit:
    """Utilities for repairing malformed JSON from LLM outputs."""

    @staticmethod
    def extract_json(text: str) -> Optional[str]:
        """Extract JSON from text that may contain markdown or other content."""
        # Strip leading/trailing whitespace
        text = text.strip()

        # Try to find JSON in code blocks
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if code_block_match:
            return code_block_match.group(1).strip()

        # Try to find a balanced JSON object by tracking braces
        # This handles cases where LLM outputs multiple JSON objects
        start = text.find('{')
        if start == -1:
            start = text.find('[')
            if start == -1:
                return None
            open_char, close_char = '[', ']'
        else:
            array_start = text.find('[')
            if array_start != -1 and array_start < start:
                start = array_start
                open_char, close_char = '[', ']'
            else:
                open_char, close_char = '{', '}'

        # Track brace depth to find matching close
        depth = 0
        in_string = False
        escape_next = False
        for i, c in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if c == '\\':
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    return text[start:i+1]

        # Fallback to greedy match if balanced extraction fails
        json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if json_match:
            return json_match.group(1).strip()

        return None

    @staticmethod
    def repair_json(text: str) -> str:
        """Attempt to repair common JSON issues."""
        # Remove trailing commas before } or ]
        text = re.sub(r',\s*([}\]])', r'\1', text)

        # Fix single quotes to double quotes (simple cases)
        # Be careful not to break strings containing quotes
        if "'" in text and '"' not in text:
            text = text.replace("'", '"')

        # Fix unquoted keys
        text = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', text)

        return text

    @staticmethod
    def parse_lenient(text: str) -> Any:
        """Parse JSON leniently, attempting repairs if needed."""
        # First try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON
        extracted = JSONRepairKit.extract_json(text)
        if extracted:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                # Try repair
                repaired = JSONRepairKit.repair_json(extracted)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        # Try repair on original
        repaired = JSONRepairKit.repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        return None
