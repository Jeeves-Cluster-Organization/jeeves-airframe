"""Chain-of-Thought Proxy - Extract and strip reasoning from LLM output.

M7 Enhancement (v0.14): Capture LLM reasoning internally for debugging
but strip it from user-facing output. This supports better debugging
without exposing internal reasoning.

The module handles common CoT markers from various models:
- <thinking>...</thinking>
- <reasoning>...</reasoning>
- <scratchpad>...</scratchpad>
- Let me think... (step-by-step markers)
"""

import re
from typing import Tuple, Optional, List

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol


# Known CoT marker patterns
COT_BLOCK_PATTERNS = [
    (r'<thinking>(.*?)</thinking>', 'thinking'),
    (r'<reasoning>(.*?)</reasoning>', 'reasoning'),
    (r'<scratchpad>(.*?)</scratchpad>', 'scratchpad'),
    (r'<analysis>(.*?)</analysis>', 'analysis'),
    (r'<plan>(.*?)</plan>', 'plan'),
    (r'\[thinking\](.*?)\[/thinking\]', 'thinking_bracket'),
    (r'\[INTERNAL\](.*?)\[/INTERNAL\]', 'internal'),
]

# Line-based CoT patterns (less reliable, use with caution)
COT_LINE_PREFIXES = [
    "Let me think",
    "First, I'll",
    "Step 1:",
    "My analysis:",
    "Thinking through this:",
    "I need to consider",
]


def extract_and_strip_cot(llm_output: str) -> Tuple[str, Optional[str]]:
    """Extract CoT for logging, return clean output for user.

    M7 Enhancement: Separates reasoning from response so internal
    thought process can be logged for debugging without leaking
    to users.

    Args:
        llm_output: Raw LLM response text

    Returns:
        Tuple of (clean_output, cot_content)
        - clean_output: Response with CoT blocks removed
        - cot_content: Extracted reasoning (None if no CoT found)
    """
    _logger = get_current_logger()
    if not llm_output:
        return "", None

    cot_blocks: List[Tuple[str, str]] = []  # (type, content)
    clean_output = llm_output

    # Extract all block-based CoT patterns
    for pattern, cot_type in COT_BLOCK_PATTERNS:
        matches = re.findall(pattern, clean_output, re.DOTALL | re.IGNORECASE)
        for match in matches:
            cot_blocks.append((cot_type, match.strip()))

        # Strip the matched blocks from output
        clean_output = re.sub(pattern, '', clean_output, flags=re.DOTALL | re.IGNORECASE)

    # Clean up extra whitespace from removal
    clean_output = re.sub(r'\n{3,}', '\n\n', clean_output)
    clean_output = clean_output.strip()

    # Build CoT content string
    if cot_blocks:
        cot_content = "\n---\n".join(
            f"[{cot_type}]\n{content}"
            for cot_type, content in cot_blocks
        )

        _logger.debug(
            "cot_extracted",
            block_count=len(cot_blocks),
            types=[t for t, _ in cot_blocks],
            total_cot_chars=len(cot_content)
        )

        return clean_output, cot_content

    return clean_output, None


def extract_cot_only(llm_output: str) -> Optional[str]:
    """Extract only the CoT content, ignoring the final response.

    Useful for debugging/analysis when you only care about the reasoning.

    Args:
        llm_output: Raw LLM response text

    Returns:
        CoT content or None if no CoT found
    """
    _, cot = extract_and_strip_cot(llm_output)
    return cot


def strip_cot_only(llm_output: str) -> str:
    """Strip CoT, returning only the final response.

    Convenient wrapper when you don't need the CoT content.

    Args:
        llm_output: Raw LLM response text

    Returns:
        Clean response with CoT removed
    """
    clean, _ = extract_and_strip_cot(llm_output)
    return clean


def has_cot_markers(text: str) -> bool:
    """Check if text contains any CoT markers.

    Quick check without full extraction.

    Args:
        text: Text to check

    Returns:
        True if CoT markers found
    """
    text_lower = text.lower()

    for pattern, _ in COT_BLOCK_PATTERNS:
        # Check for opening tag
        opening_tag = pattern.split('(')[0].replace('\\', '')
        if opening_tag.replace('.', '').replace('*', '').replace('?', '') in text_lower:
            return True

    return False


def format_cot_for_logging(cot_content: Optional[str], max_length: int = 500) -> str:
    """Format CoT content for structured logging.

    Args:
        cot_content: Raw CoT content
        max_length: Maximum length for log output

    Returns:
        Formatted string suitable for logging
    """
    if not cot_content:
        return "(no CoT)"

    if len(cot_content) <= max_length:
        return cot_content

    return cot_content[:max_length] + f"... [{len(cot_content) - max_length} chars truncated]"


def inject_cot_instruction(prompt: str, cot_style: str = "thinking") -> str:
    """Inject CoT instruction into a prompt.

    Adds instruction for model to use tagged reasoning.

    Args:
        prompt: Original prompt
        cot_style: Style of CoT tags to request

    Returns:
        Prompt with CoT instruction added
    """
    cot_instruction = f"""
Before providing your answer, think through the problem step by step.
Place your reasoning inside <{cot_style}>...</{cot_style}> tags.
Your final answer should come after the closing tag.

Example format:
<{cot_style}>
[Your step-by-step reasoning here]
</{cot_style}>

[Your final answer here]
"""

    # Insert at the end of the prompt, before any final instructions
    return prompt + "\n" + cot_instruction


class CoTProcessor:
    """Processor class for managing CoT in agent responses.

    M7 Enhancement: Provides a stateful processor that can track
    CoT across multiple interactions and provide debugging info.
    """

    def __init__(self, agent_name: str = "unknown", logger: Optional[LoggerProtocol] = None):
        self._logger = logger or get_current_logger()
        self.agent_name = agent_name
        self.logger = self._logger.bind(
            component="cot_processor",
            agent=agent_name
        )
        self.cot_history: List[Tuple[str, str]] = []  # (timestamp-ish, cot)

    def process_response(self, raw_response: str) -> str:
        """Process an LLM response, extracting and logging CoT.

        Args:
            raw_response: Raw LLM response

        Returns:
            Clean response for user
        """
        clean, cot = extract_and_strip_cot(raw_response)

        if cot:
            # Store for debugging
            self.cot_history.append((self.agent_name, cot))
            # Keep only last 10
            self.cot_history = self.cot_history[-10:]

            self.logger.debug(
                "agent_cot_captured",
                cot_preview=cot[:200] if len(cot) > 200 else cot
            )

        return clean

    def get_recent_cot(self, count: int = 3) -> List[Tuple[str, str]]:
        """Get recent CoT history.

        Args:
            count: Number of recent entries

        Returns:
            List of (agent_name, cot) tuples
        """
        return self.cot_history[-count:]

    def clear_history(self):
        """Clear CoT history."""
        self.cot_history = []
