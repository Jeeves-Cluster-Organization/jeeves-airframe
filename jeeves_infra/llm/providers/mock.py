"""Mock LLM Provider for testing.

Split from provider.py per Module Bloat Audit (2025-12-09).
Constitutional Reference: Infrastructure R4 (Swappable Implementations)
"""

import json
import re
from typing import Any, Dict, Optional

from .base import LLMProvider


class MockProvider(LLMProvider):
    """Mock provider for testing without actual LLM calls.

    Returns deterministic responses based on simple heuristics.
    Useful for unit tests and CI/CD pipelines.
    """

    def __init__(self):
        """Initialize mock provider."""
        self.call_count = 0
        self.call_history = []

    async def generate(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate mock response based on prompt content.

        This implementation provides simple pattern matching to simulate
        realistic responses for common agent tasks.
        """
        self.call_count += 1
        self.call_history.append({
            'method': 'generate',
            'model': model,
            'prompt': prompt,
            'options': options
        })

        prompt_lower = prompt.lower()

        # Mock intent classification responses
        if "classify its intent" in prompt_lower or "is_task" in prompt_lower:
            return self._mock_intent_classification(prompt, prompt_lower)

        # Mock planner responses
        if self._is_planner_prompt(prompt_lower):
            return self._mock_planner_response(prompt, prompt_lower)

        # Mock validator responses
        if "generate natural" in prompt_lower or "tools:" in prompt_lower:
            return self._mock_validator_response(prompt_lower)

        # Mock meta-validator responses
        if "fact-checking" in prompt_lower or "validation rules" in prompt_lower:
            return self._mock_meta_validator_response()

        # Mock confirmation detection responses (v0.14 Phase 4)
        if self._is_confirmation_detection_prompt(prompt_lower):
            return self._mock_confirmation_detection(prompt, prompt_lower)

        # Mock confirmation interpretation responses (v0.14 Phase 4)
        if "interpret" in prompt_lower and ("confirmation" in prompt_lower or "user response" in prompt_lower):
            return self._mock_confirmation_interpretation(prompt, prompt_lower)

        # Default response
        return "Mock response"

    async def health_check(self) -> bool:
        """Mock provider is always healthy."""
        return True

    def _is_planner_prompt(self, prompt_lower: str) -> bool:
        """Check if prompt is a planner prompt."""
        return (
            ("planner agent" in prompt_lower and
             ("execution_plan" in prompt_lower or "user request" in prompt_lower)) or
            "generate json execution plan" in prompt_lower or
            "generate a json execution plan" in prompt_lower
        )

    def _is_confirmation_detection_prompt(self, prompt_lower: str) -> bool:
        """Check if prompt is a confirmation detection prompt."""
        return (
            "is_confirmation_response" in prompt_lower or
            "user responded" in prompt_lower or
            "confirmation request" in prompt_lower
        )

    def _mock_intent_classification(self, prompt: str, prompt_lower: str) -> str:
        """Generate mock intent classification response."""
        # Parse the input content from the prompt
        content = ""
        if '"' in prompt and "Input:" in prompt:
            try:
                start = prompt.find('Input: "') + 8
                end = prompt.find('"', start)
                content = prompt[start:end].lower()
            except (IndexError, ValueError):
                content = ""

        # Determine classification based on content
        if any(word in content for word in ["buy", "finish", "complete", "do ", "task"]):
            return json.dumps({
                "is_task": 0.95,
                "is_journal": 0.1,
                "is_fact": 0.05,
                "is_message": 0.0,
                "task_attributes": {
                    "title": content[:50] if content else "Task",
                    "priority": "medium"
                },
                "journal_attributes": {},
                "fact_attributes": {}
            })
        elif any(word in content for word in ["feeling", "today", "thought", "note", "journal"]):
            return json.dumps({
                "is_task": 0.1,
                "is_journal": 0.9,
                "is_fact": 0.0,
                "is_message": 0.0,
                "task_attributes": {},
                "journal_attributes": {
                    "category": "thought",
                    "sentiment": "neutral"
                },
                "fact_attributes": {}
            })
        elif any(word in content for word in ["prefer", "like", "my ", "is ", "fact"]):
            return json.dumps({
                "is_task": 0.0,
                "is_journal": 0.1,
                "is_fact": 0.95,
                "is_message": 0.0,
                "task_attributes": {},
                "journal_attributes": {},
                "fact_attributes": {
                    "key": "preference",
                    "value": content[:100] if content else "fact",
                    "domain": "general"
                }
            })
        else:
            return json.dumps({
                "is_task": 0.0,
                "is_journal": 0.0,
                "is_fact": 0.0,
                "is_message": 1.0,
                "task_attributes": {},
                "journal_attributes": {},
                "fact_attributes": {}
            })

    def _mock_planner_response(self, prompt: str, prompt_lower: str) -> str:
        """Generate mock planner response."""
        # Try to extract the user request from the prompt
        user_message = ""
        user_match = re.search(r'\*?\*?user request\*?\*?[:\s*]+["\']?([^"\'\n]+)', prompt, re.IGNORECASE)
        if user_match:
            user_message = user_match.group(1).strip().lower()
        else:
            user_match = re.search(r'user[:\s]+([^\n]+)', prompt, re.IGNORECASE)
            if user_match:
                user_message = user_match.group(1).strip().lower()
            else:
                user_message = prompt_lower

        task_title = "Test task"

        # Check delete FIRST (more specific) before add
        if "delete" in user_message or "remove" in user_message:
            return self._mock_delete_plan(user_message)
        elif "add task" in user_message or "create task" in user_message:
            return self._mock_add_task_plan(prompt, prompt_lower)
        elif "search" in prompt_lower:
            return self._mock_search_plan(prompt)
        elif "show tasks" in prompt_lower or "list tasks" in prompt_lower or "get tasks" in prompt_lower:
            return self._mock_get_tasks_plan()
        elif "update task" in user_message or "update" in user_message:
            return self._mock_update_task_plan(user_message)
        else:
            return json.dumps({
                "intent": "Unclear request",
                "confidence": 0.3,
                "requires_context": False,
                "context_query": None,
                "clarification_needed": True,
                "clarification_question": "I'm not sure what you want me to do. Could you clarify?",
                "execution_plan": []
            })

    def _mock_delete_plan(self, user_message: str) -> str:
        """Generate mock delete task plan."""
        task_id = None
        title_pattern = None
        id_match = re.search(r'(?:task[- ]?id|id)[:\s]*([a-f0-9-]{36})', user_message, re.IGNORECASE)
        if id_match:
            task_id = id_match.group(1)
        else:
            title_match = re.search(r'delete\s+(?:the\s+)?([^\n"]+?)(?:\s*\?|$)', user_message, re.IGNORECASE)
            if title_match:
                title_pattern = title_match.group(1).strip()
            elif "test task" in user_message:
                title_pattern = "test task"

        return json.dumps({
            "intent": "Delete a task",
            "confidence": 0.9,
            "requires_context": False,
            "context_query": None,
            "clarification_needed": False,
            "clarification_question": None,
            "execution_plan": [
                {
                    "tool": "delete_task",
                    "parameters": {
                        "user_id": "{{USER_ID}}",
                        "title_pattern": title_pattern if title_pattern else "task"
                    } if not task_id else {
                        "user_id": "{{USER_ID}}",
                        "task_id": task_id
                    },
                    "reasoning": "User wants to delete a task"
                }
            ]
        })

    def _mock_add_task_plan(self, prompt: str, prompt_lower: str) -> str:
        """Generate mock add task plan."""
        task_title = "Test task"
        match = re.search(r'(?:add task|create task)[:\s]+([^\n"]+)', prompt, re.IGNORECASE)
        if match:
            task_title = match.group(1).strip().strip('"\'')
        elif "buy " in prompt_lower:
            match = re.search(r'buy\s+(\w+)', prompt_lower)
            if match:
                task_title = f"buy {match.group(1)}"

        return json.dumps({
            "intent": "Add a new task",
            "confidence": 0.9,
            "requires_context": False,
            "context_query": None,
            "clarification_needed": False,
            "clarification_question": None,
            "execution_plan": [
                {
                    "tool": "add_task",
                    "parameters": {"user_id": "{{USER_ID}}", "title": task_title},
                    "reasoning": "User wants to add a new task"
                }
            ]
        })

    def _mock_search_plan(self, prompt: str) -> str:
        """Generate mock search plan."""
        search_query = "search"
        match = re.search(r'search\s+(?:for\s+)?([^\n"]+)', prompt, re.IGNORECASE)
        if match:
            search_query = match.group(1).strip().strip('"\'')

        return json.dumps({
            "intent": "Search tasks",
            "confidence": 0.9,
            "requires_context": False,
            "context_query": None,
            "clarification_needed": False,
            "clarification_question": None,
            "execution_plan": [
                {
                    "tool": "search_tasks",
                    "parameters": {"user_id": "{{USER_ID}}", "query": search_query},
                    "reasoning": "User wants to search for tasks"
                }
            ]
        })

    def _mock_get_tasks_plan(self) -> str:
        """Generate mock get tasks plan."""
        return json.dumps({
            "intent": "Show all tasks",
            "confidence": 0.95,
            "requires_context": False,
            "context_query": None,
            "clarification_needed": False,
            "clarification_question": None,
            "execution_plan": [
                {
                    "tool": "get_tasks",
                    "parameters": {"user_id": "{{USER_ID}}"},
                    "reasoning": "User wants to see their tasks"
                }
            ]
        })

    def _mock_update_task_plan(self, user_message: str) -> str:
        """Generate mock update task plan."""
        task_id = "missing"
        id_match = re.search(r'(?:task\s+)?(\d+|[a-f0-9-]{36})', user_message, re.IGNORECASE)
        if id_match:
            task_id = id_match.group(1)

        return json.dumps({
            "intent": "update_task",
            "confidence": 0.9,
            "requires_context": False,
            "context_query": None,
            "clarification_needed": False,
            "clarification_question": None,
            "execution_plan": [
                {
                    "tool": "update_task",
                    "parameters": {"user_id": "{{USER_ID}}", "task_id": task_id},
                    "reasoning": "User wants to update a task"
                }
            ]
        })

    def _mock_validator_response(self, prompt_lower: str) -> str:
        """Generate mock validator response."""
        if '"status":"success"' in prompt_lower or '"status": "success"' in prompt_lower:
            return "I've completed your request successfully."
        elif '"status":"error"' in prompt_lower or '"status": "error"' in prompt_lower:
            return "I encountered an error while processing your request."
        else:
            return "Request processed."

    def _mock_meta_validator_response(self) -> str:
        """Generate mock meta-validator response."""
        return json.dumps({
            "approved": True,
            "confidence": 0.95,
            "issues": [],
            "suggested_correction": None,
            "requires_user_notification": False
        })

    def _extract_user_response(self, prompt: str, prompt_lower: str) -> str:
        """Extract user response from prompt."""
        user_response = ""
        markers = [
            "**user responded:**", "user responded:",
            "**user's response:**", "user's response:",
            "**user response:**", "user response:"
        ]
        for marker in markers:
            if marker in prompt_lower:
                try:
                    start = prompt_lower.find(marker) + len(marker)
                    while start < len(prompt_lower) and prompt_lower[start] in ' *\t':
                        start += 1
                    if start < len(prompt_lower) and prompt_lower[start] == '"':
                        quote_start = start
                        quote_end = prompt_lower.find('"', quote_start + 1)
                        if quote_end != -1:
                            user_response = prompt_lower[quote_start + 1:quote_end].strip()
                            break
                    end = prompt_lower.find("\n", start)
                    if end == -1:
                        end = len(prompt_lower)
                    user_response = prompt_lower[start:end].strip().strip('"\'')
                    break
                except (IndexError, ValueError):
                    pass
        return user_response

    def _mock_confirmation_detection(self, prompt: str, prompt_lower: str) -> str:
        """Generate mock confirmation detection response."""
        user_response = self._extract_user_response(prompt, prompt_lower)

        affirmative_words = [
            "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "proceed",
            "go ahead", "do it", "absolutely", "confirm", "confirmed",
            "affirmative", "agreed", "accept", "approve", "fine", "alright",
            "correct", "right"
        ]
        negative_words = [
            "no", "nope", "nah", "cancel", "stop", "abort", "never mind",
            "nevermind", "don't", "decline", "reject", "negative"
        ]
        modification_words = ["change", "modify", "instead", "but ", " but", "with "]

        if any(word in user_response for word in affirmative_words):
            if any(word in user_response for word in modification_words):
                return json.dumps({
                    "is_confirmation_response": True,
                    "type": "modification",
                    "confidence": 0.90
                })
            return json.dumps({
                "is_confirmation_response": True,
                "type": "affirmative",
                "confidence": 0.95
            })
        elif any(word in user_response for word in negative_words):
            return json.dumps({
                "is_confirmation_response": True,
                "type": "negative",
                "confidence": 0.95
            })
        elif any(word in user_response for word in modification_words):
            return json.dumps({
                "is_confirmation_response": True,
                "type": "modification",
                "confidence": 0.85
            })
        else:
            return json.dumps({
                "is_confirmation_response": False,
                "type": "unrelated",
                "confidence": 0.7
            })

    def _mock_confirmation_interpretation(self, prompt: str, prompt_lower: str) -> str:
        """Generate mock confirmation interpretation response."""
        user_response = self._extract_user_response(prompt, prompt_lower)

        affirmative_words = [
            "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "proceed",
            "go ahead", "do it", "absolutely", "confirm", "confirmed",
            "affirmative", "agreed", "accept", "approve", "fine", "alright"
        ]
        negative_words = [
            "no", "nope", "nah", "cancel", "stop", "abort", "never mind",
            "nevermind", "don't", "decline", "reject", "negative"
        ]
        modification_words = ["change", "modify", "instead", "but ", " but"]

        if any(word in user_response for word in affirmative_words):
            if any(word in user_response for word in modification_words):
                return json.dumps({
                    "decision": "modify",
                    "parameter_updates": {},
                    "modification_description": "User requested modification",
                    "confidence": 0.90
                })
            return json.dumps({
                "decision": "yes",
                "parameter_updates": None,
                "modification_description": None,
                "confidence": 0.95
            })
        elif any(word in user_response for word in negative_words):
            return json.dumps({
                "decision": "no",
                "parameter_updates": None,
                "modification_description": None,
                "confidence": 0.95
            })
        elif any(word in user_response for word in modification_words):
            return json.dumps({
                "decision": "modify",
                "parameter_updates": {},
                "modification_description": "User requested modification",
                "confidence": 0.85
            })
        else:
            return json.dumps({
                "decision": "no",
                "parameter_updates": None,
                "modification_description": None,
                "confidence": 0.6
            })


__all__ = ["MockProvider"]
