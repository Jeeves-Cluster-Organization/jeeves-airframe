"""Prompt Compression - Heuristic compression for LLM prompts.

M6 Enhancement (v0.14): Apply simple compression rules to reduce
token count without losing meaning. Essential for local models
with limited context windows (3B-14B on consumer hardware).

This module provides fast, deterministic compression that helps
fit more context into local model limits and reduces token costs
on cloud fallback.
"""

import re
from typing import Optional

from jeeves_infra.logging import get_current_logger


def compress_for_prompt(text: str, max_chars: int = 2000) -> str:
    """Apply heuristic compression to fit context bounds.

    M6 Enhancement: Progressively applies compression rules
    until text fits within max_chars limit.

    Args:
        text: Input text to compress
        max_chars: Maximum character limit (default 2000 ~= 500 tokens)

    Returns:
        Compressed text fitting within limit
    """
    _logger = get_current_logger()
    original_len = len(text)

    # Rule 1: Always collapse multiple newlines (normalization)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Rule 2: Always collapse multiple spaces (normalization)
    text = re.sub(r' {2,}', ' ', text)

    # If ORIGINAL text was within limit, normalization is sufficient
    # (don't apply aggressive compression for text that was already short)
    if original_len <= max_chars:
        if len(text) < original_len:
            _logger.debug(
                "prompt_compressed",
                rule="normalize_whitespace",
                original=original_len,
                compressed=len(text)
            )
        return text

    # Original exceeded limit - apply all aggressive compression rules
    # (don't return early even if normalization brings it under limit)

    # Rule 3: Remove markdown formatting
    # Remove bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove italic
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove heading markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    if len(text) <= max_chars:
        _logger.debug(
            "prompt_compressed",
            rule="strip_markdown",
            original=original_len,
            compressed=len(text)
        )
        return text

    # Rule 4: Shorten common verbose phrases
    if len(text) > max_chars:
        substitutions = [
            (r'\bin order to\b', 'to'),
            (r'\bfor the purpose of\b', 'for'),
            (r'\bdue to the fact that\b', 'because'),
            (r'\bat this point in time\b', 'now'),
            (r'\bin the event that\b', 'if'),
            (r'\bwith regard to\b', 'about'),
            (r'\bplease note that\b', ''),
            (r'\bit is important to note that\b', ''),
        ]
        for pattern, replacement in substitutions:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    if len(text) <= max_chars:
        _logger.debug(
            "prompt_compressed",
            rule="verbose_phrases",
            original=original_len,
            compressed=len(text)
        )
        return text

    # Rule 5: Truncate with ellipsis at boundary
    if len(text) > max_chars:
        # Try to find a good truncation point (sentence or paragraph)
        truncation_point = max_chars - 50
        truncated = text[:truncation_point]

        # Look for last complete sentence
        last_sentence = max(
            truncated.rfind('. '),
            truncated.rfind('.\n'),
            truncated.rfind('! '),
            truncated.rfind('? ')
        )

        if last_sentence > truncation_point * 0.7:
            truncated = text[:last_sentence + 1]

        text = truncated + "\n\n[... truncated for context limits]"

        _logger.debug(
            "prompt_compressed",
            rule="truncate",
            original=original_len,
            compressed=len(text)
        )

    return text


def compress_json_for_prompt(json_str: str, max_chars: int = 1000) -> str:
    """Compress JSON string for prompt inclusion.

    Applies JSON-specific compression rules. Always removes unnecessary
    whitespace as JSON semantics are preserved.

    Args:
        json_str: JSON string to compress
        max_chars: Maximum character limit

    Returns:
        Compressed JSON string
    """
    # Always remove unnecessary whitespace in JSON (semantically safe)
    # Be careful to preserve string contents
    compressed = re.sub(r'(?<=[{,\[])\s+', '', json_str)
    compressed = re.sub(r'\s+(?=[}\],])', '', compressed)
    compressed = re.sub(r':\s+', ':', compressed)
    compressed = re.sub(r',\s+', ',', compressed)

    if len(compressed) <= max_chars:
        return compressed

    # If still too long, truncate with indicator
    return compressed[:max_chars - 30] + '...[truncated]}'


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Simple heuristic: ~4 characters per token on average.
    More accurate would require actual tokenizer, but this
    is fast and good enough for budgeting.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    return len(text) // 4


def compress_to_token_budget(
    text: str,
    token_budget: int,
    preserve_start_chars: int = 200
) -> str:
    """Compress text to fit within token budget.

    Args:
        text: Input text
        token_budget: Maximum tokens allowed
        preserve_start_chars: Always preserve first N chars

    Returns:
        Compressed text fitting within token budget
    """
    max_chars = token_budget * 4  # ~4 chars per token

    if len(text) <= max_chars:
        return text

    # Preserve the start (usually most important)
    preserved = text[:preserve_start_chars]
    remaining = text[preserve_start_chars:]

    # Compress the rest
    remaining_budget = max_chars - preserve_start_chars
    compressed_remaining = compress_for_prompt(remaining, remaining_budget)

    return preserved + compressed_remaining


def get_compression_stats(original: str, compressed: str) -> dict:
    """Get statistics about compression.

    Args:
        original: Original text
        compressed: Compressed text

    Returns:
        Dictionary with compression statistics
    """
    original_len = len(original)
    compressed_len = len(compressed)
    saved = original_len - compressed_len
    ratio = compressed_len / original_len if original_len > 0 else 1.0

    return {
        "original_chars": original_len,
        "compressed_chars": compressed_len,
        "chars_saved": saved,
        "compression_ratio": round(ratio, 3),
        "estimated_tokens_saved": saved // 4,
    }
