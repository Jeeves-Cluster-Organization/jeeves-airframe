"""
Response formatting utilities.

This module provides standardized formatting for agent responses,
reducing duplication across validator and other response-generating agents.
"""

from typing import List, Dict, Any, Optional
import json


class ResponseFormatter:
    """Formatter for standardized agent responses."""

    @staticmethod
    def format_success(
        action: str,
        details: Optional[Dict[str, Any]] = None,
        conversational: bool = True
    ) -> str:
        """Format success response.

        Args:
            action: Action that was performed
            details: Optional details dict
            conversational: Use conversational tone

        Returns:
            Formatted success message
        """
        if conversational:
            message = f"I've {action}."
        else:
            message = f"Successfully {action}."

        if details:
            message += f" {ResponseFormatter._format_details(details)}"

        return message

    @staticmethod
    def format_error(
        error_message: str,
        error_type: Optional[str] = None,
        suggestions: Optional[List[str]] = None
    ) -> str:
        """Format error response.

        Args:
            error_message: Error message
            error_type: Type of error
            suggestions: Optional suggestions for fixing

        Returns:
            Formatted error message
        """
        message = f"I couldn't complete that action"

        if error_type:
            message += f" ({error_type})"

        message += f": {error_message}"

        if suggestions:
            message += "\n\nSuggestions:\n"
            for idx, suggestion in enumerate(suggestions, 1):
                message += f"{idx}. {suggestion}\n"

        return message

    @staticmethod
    def format_tool_results(
        tool_results: List[Dict[str, Any]],
        include_errors: bool = True
    ) -> str:
        """Format tool results for display.

        Args:
            tool_results: List of tool result dicts
            include_errors: Include failed tools

        Returns:
            Formatted tool results
        """
        if not tool_results:
            return "No tools were executed."

        formatted = []
        for idx, result in enumerate(tool_results, 1):
            tool_name = result.get("tool", "unknown")
            status = result.get("status", "unknown")

            if status == "success":
                formatted.append(f"{idx}. {tool_name}: [OK]")
            elif include_errors:
                error = result.get("error", "Unknown error")
                formatted.append(f"{idx}. {tool_name}: [FAIL] ({error})")

        return "\n".join(formatted)

    @staticmethod
    def format_list(
        items: List[Any],
        title: Optional[str] = None,
        numbered: bool = True,
        item_formatter: Optional[callable] = None
    ) -> str:
        """Format list of items.

        Args:
            items: List of items to format
            title: Optional title for list
            numbered: Use numbered list
            item_formatter: Optional function to format each item

        Returns:
            Formatted list
        """
        if not items:
            return f"{title}: None" if title else "None"

        formatted = []
        if title:
            formatted.append(f"{title}:")

        for idx, item in enumerate(items, 1):
            item_str = item_formatter(item) if item_formatter else str(item)
            if numbered:
                formatted.append(f"{idx}. {item_str}")
            else:
                formatted.append(f"- {item_str}")

        return "\n".join(formatted)

    @staticmethod
    def format_task(task: Dict[str, Any]) -> str:
        """Format single task for display.

        Args:
            task: Task dict

        Returns:
            Formatted task string
        """
        title = task.get("title", "Untitled")
        task_id = task.get("task_id", "")
        status = task.get("status", "unknown")

        formatted = f"'{title}'"
        if task_id:
            formatted += f" (ID: {task_id})"
        if status and status != "pending":
            formatted += f" [{status}]"

        return formatted

    @staticmethod
    def format_journal_entry(entry: Dict[str, Any]) -> str:
        """Format single journal entry for display.

        Args:
            entry: Journal entry dict

        Returns:
            Formatted entry string
        """
        text = entry.get("content", entry.get("text", ""))
        entry_id = entry.get("entry_id", "")
        created_at = entry.get("created_at", "")

        formatted = text
        if entry_id:
            formatted += f" (ID: {entry_id})"
        if created_at:
            formatted += f" [created: {created_at}]"

        return formatted

    @staticmethod
    def format_multi_action(actions: List[str], conjunction: str = "and") -> str:
        """Format multiple actions into single sentence.

        Args:
            actions: List of action strings
            conjunction: Conjunction to use (e.g., "and", "then")

        Returns:
            Formatted multi-action string
        """
        if not actions:
            return ""
        if len(actions) == 1:
            return actions[0]
        if len(actions) == 2:
            return f"{actions[0]} {conjunction} {actions[1]}"

        # More than 2 actions
        return ", ".join(actions[:-1]) + f", {conjunction} {actions[-1]}"

    @staticmethod
    def format_count(count: int, singular: str, plural: Optional[str] = None) -> str:
        """Format count with proper singular/plural.

        Args:
            count: Count value
            singular: Singular form
            plural: Plural form (defaults to singular + 's')

        Returns:
            Formatted count string
        """
        if count == 1:
            return f"1 {singular}"

        plural_form = plural or f"{singular}s"
        return f"{count} {plural_form}"

    @staticmethod
    def _format_details(details: Dict[str, Any]) -> str:
        """Internal helper to format details dict.

        Args:
            details: Details dictionary

        Returns:
            Formatted details string
        """
        parts = []
        for key, value in details.items():
            if value is not None:
                parts.append(f"{key}: {value}")

        return " | ".join(parts) if parts else ""

    @staticmethod
    def truncate_text(
        text: str,
        max_length: int,
        suffix: str = "..."
    ) -> str:
        """Truncate text to max length.

        Args:
            text: Text to truncate
            max_length: Maximum length
            suffix: Suffix to add if truncated

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text

        return text[:max_length - len(suffix)] + suffix

    @staticmethod
    def enforce_word_limit(text: str, max_words: int) -> str:
        """Enforce word limit on text.

        Args:
            text: Text to limit
            max_words: Maximum words

        Returns:
            Text with word limit enforced
        """
        words = text.split()
        if len(words) <= max_words:
            return text

        return " ".join(words[:max_words]) + "..."
