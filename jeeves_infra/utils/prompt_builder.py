"""
Reusable prompt construction utilities.

This module extracts common prompt building patterns from agents
to reduce duplication and improve maintainability.
"""

from typing import Dict, List, Optional, Any


class PromptBuilder:
    """Builder for constructing structured LLM prompts."""

    @staticmethod
    def build_context_section(
        recent_task_ids: Optional[List[str]] = None,
        recent_task_titles: Optional[List[str]] = None,
        additional_context: Optional[str] = None
    ) -> str:
        """Build context section with recent task IDs and titles.

        Args:
            recent_task_ids: List of recent task IDs
            recent_task_titles: List of recent task titles
            additional_context: Additional context text

        Returns:
            Formatted context section
        """
        context_section = ""

        if recent_task_ids:
            context_section = "\nCONTEXT - Recent task IDs:\n"
            for idx, task_id in enumerate(recent_task_ids, 1):
                context_section += f"  [{idx}] {task_id}\n"

        if recent_task_titles:
            if not context_section:
                context_section = "\nCONTEXT:\n"
            context_section += "Recent task titles:\n"
            for idx, title in enumerate(recent_task_titles, 1):
                context_section += f"  [{idx}] {title}\n"

        if additional_context:
            if not context_section:
                context_section = "\nCONTEXT:\n"
            context_section += additional_context + "\n"

        return context_section

    @staticmethod
    def build_retry_section(retry_feedback: Optional[str], feedback_type: str = "CRITIC") -> str:
        """Build retry feedback section.

        Args:
            retry_feedback: Feedback text from critic/validator
            feedback_type: Type of feedback (e.g., "CRITIC", "VALIDATOR")

        Returns:
            Formatted retry section or empty string
        """
        if not retry_feedback:
            return ""

        return (
            f"\n[WARNING] {feedback_type} FEEDBACK (Previous attempt had issues):\n"
            f"{retry_feedback}\n\n"
            f"Please address this feedback in your new {'plan' if feedback_type == 'CRITIC' else 'response'}.\n"
        )

    @staticmethod
    def build_tool_definitions_section(tool_definitions: str) -> str:
        """Build tool definitions section.

        Args:
            tool_definitions: Tool definitions from registry

        Returns:
            Formatted tool definitions section
        """
        return f"\nAvailable Tools:\n{tool_definitions}\n"

    @staticmethod
    def build_examples_section(examples: List[Dict[str, str]]) -> str:
        """Build examples section from list of example dicts.

        Args:
            examples: List of dicts with 'input' and 'output' keys

        Returns:
            Formatted examples section
        """
        if not examples:
            return ""

        examples_text = "\nEXAMPLES:\n\n"
        for idx, example in enumerate(examples, 1):
            examples_text += f"{idx}. {example.get('title', 'Example')}:\n"
            examples_text += f"   {example['input']}\n"
            examples_text += f"   {example['output']}\n\n"

        return examples_text

    @staticmethod
    def build_rules_section(rules: List[str], title: str = "CRITICAL RULES") -> str:
        """Build rules section from list of rules.

        Args:
            rules: List of rule strings
            title: Section title

        Returns:
            Formatted rules section
        """
        if not rules:
            return ""

        rules_text = f"\n{title}:\n"
        for idx, rule in enumerate(rules, 1):
            rules_text += f"{idx}. {rule}\n"

        return rules_text

    @staticmethod
    def wrap_prompt(
        header: str,
        user_input: str,
        sections: Dict[str, str],
        footer: Optional[str] = None
    ) -> str:
        """Wrap prompt with standard structure.

        Args:
            header: Prompt header/instruction
            user_input: User's input/request
            sections: Dict of section names to content
            footer: Optional footer text

        Returns:
            Complete formatted prompt
        """
        prompt_parts = [header]

        # Add user input
        prompt_parts.append(f"\nUser Request: {user_input}\n")

        # Add sections in order
        for section_content in sections.values():
            if section_content:
                prompt_parts.append(section_content)

        # Add footer
        if footer:
            prompt_parts.append(f"\n{footer}")

        return "\n".join(prompt_parts)

    @staticmethod
    def format_json_structure(structure: Dict[str, Any], indent: int = 2) -> str:
        """Format JSON structure for prompt display.

        Args:
            structure: Dict representing JSON structure
            indent: Indentation spaces

        Returns:
            Formatted JSON string
        """
        import json
        return json.dumps(structure, indent=indent)
