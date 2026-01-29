"""Test intent-based prompts for P1 compliance.

Constitutional P1 (NLP-First, No Pattern-Gatekeeping):
- Prompts should focus on intent understanding, not pattern matching
- No keyword lists or regex enforcement
- Emphasize semantic understanding
"""

import pytest
from mission_system.prompts.core.registry import PromptRegistry


class TestIntentPrompts:
    """Validate intent-based prompts don't contain pattern matching."""

    def test_no_pattern_keywords_in_prompts(self):
        """Ensure prompts don't instruct pattern matching."""
        registry = PromptRegistry.get_instance()

        forbidden_phrases = [
            "use pattern matching",
            "pattern matching to",
            "if word in",
            "keyword list",
            "specific keyword",
            "use keyword",
            "keyword required",
            "must use format",
            "required format",
            "syntax:",
            "startswith",
            "use regex",
            "regex to match",
        ]

        for prompt_name, versions in registry.list_prompts().items():
            for version in versions:
                prompt = registry.get(prompt_name, version)

                for phrase in forbidden_phrases:
                    assert phrase.lower() not in prompt.lower(), (
                        f"Prompt {prompt_name} v{version} contains "
                        f"pattern matching phrase: '{phrase}'"
                    )

    def test_prompts_mention_intent(self):
        """Ensure prompts focus on intent understanding."""
        registry = PromptRegistry.get_instance()

        required_concepts = ["intent", "understand", "meaning", "purpose", "what", "accomplish"]

        key_prompts = [
            "planner.tool_selection",
            "planner.intent_analysis",
            "intent.analysis",
            "confirmation.detection",
            "confirmation.interpretation"
        ]

        for prompt_name in key_prompts:
            try:
                prompt = registry.get(prompt_name, version="1.0")

                has_intent_focus = any(
                    concept in prompt.lower()
                    for concept in required_concepts
                )

                assert has_intent_focus, (
                    f"Prompt {prompt_name} doesn't focus on intent understanding"
                )
            except ValueError:
                # Prompt might not be registered yet
                pass

    def test_prompt_registry_initialized(self):
        """Ensure prompt registry can be initialized."""
        registry = PromptRegistry.get_instance()
        assert registry is not None
        prompts = registry.list_prompts()
        assert isinstance(prompts, dict)

    def test_planner_prompts_registered(self):
        """Ensure planner prompts are properly registered."""
        registry = PromptRegistry.get_instance()
        prompts = registry.list_prompts()

        expected_prompts = [
            "planner.tool_selection",
            "planner.intent_analysis",
            "planner.plan_generation",
            "planner.context_section",
            "planner.retry_section",
            "confidence.guidance"
        ]

        for expected in expected_prompts:
            assert expected in prompts, f"Prompt '{expected}' not registered"
            assert "1.0" in prompts[expected], f"Version 1.0 not found for '{expected}'"

    def test_intent_prompts_registered(self):
        """Ensure intent prompts are properly registered."""
        registry = PromptRegistry.get_instance()
        prompts = registry.list_prompts()

        expected_prompts = [
            "intent.analysis",
            "intent.context_builder",
            "intent.clarification_guidance",
            "intent.common_patterns",
        ]

        for expected in expected_prompts:
            assert expected in prompts, f"Prompt '{expected}' not registered"
            assert "1.0" in prompts[expected], f"Version 1.0 not found for '{expected}'"

    def test_critic_prompts_registered(self):
        """Ensure critic prompts are properly registered."""
        registry = PromptRegistry.get_instance()
        prompts = registry.list_prompts()

        expected_prompts = [
            "critic.response_validation",
            "critic.full_validation",
            "critic.hallucination_detection",
            "critic.response_generation",
        ]

        for expected in expected_prompts:
            assert expected in prompts, f"Prompt '{expected}' not registered"
            assert "1.0" in prompts[expected], f"Version 1.0 not found for '{expected}'"

    def test_confirmation_prompts_registered(self):
        """Ensure confirmation prompts are properly registered."""
        registry = PromptRegistry.get_instance()
        prompts = registry.list_prompts()

        expected_prompts = [
            "confirmation.detection",
            "confirmation.interpretation"
        ]

        for expected in expected_prompts:
            assert expected in prompts, f"Prompt '{expected}' not registered"
            assert "1.0" in prompts[expected], f"Version 1.0 not found for '{expected}'"

    def test_prompts_have_no_empty_placeholders(self):
        """Ensure prompts don't have unhandled {placeholder} syntax."""
        registry = PromptRegistry.get_instance()

        for prompt_name, versions in registry.list_prompts().items():
            # Skip code_analysis prompts - capability-specific prompts define their own placeholders
            if prompt_name.startswith("code_analysis"):
                continue

            for version in versions:
                # Get raw template (without context)
                prompt_version = registry._prompts[prompt_name][version]
                template = prompt_version.template

                # Count expected placeholders
                import re
                placeholders = re.findall(r'\{(\w+)\}', template)

                # Ensure placeholders are documented or reasonable
                # NOTE: Only include placeholders actually used as {placeholder} in prompt templates
                # Verified against: prompts/versions/*.py and prompts/code_analysis/*.txt
                valid_placeholders = {
                    # Common placeholders (prompts/versions/*.py)
                    "user_message", "tool_registry", "context",
                    "intent_guidance", "confidence_guidance",
                    "confirmation_message", "user_response",
                    "original_request", "proposed_parameters",
                    "response_text", "retry_section", "retry_feedback",
                    "tool_results_json", "tool_list", "USER_ID",
                    # Centralized prompts
                    "context_section", "context_summary", "task_context_section",
                    "pending_clarification_section", "tools_list",
                    "task_context", "memory_context", "intent", "goals",
                    "steps_json", "results_json",
                    # Response templates (critic prompts)
                    "title", "count", "action", "error_reason",
                    # Code analysis prompts (inline in code_analysis.py)
                    "user_query", "session_state", "normalized_input",
                    "scope_path", "exploration_summary", "max_files",
                    "max_tokens", "tokens_used", "remaining_tokens",
                    "remaining_files", "files_explored", "files_examined",
                    "execution_results", "relevant_snippets",
                    "verdict", "validated_claims", "available_tools",
                    "suggested_response", "pipeline_overview",
                    # Core identity/style prompts
                    "system_identity", "role_description", "detected_languages",
                    "capabilities_summary", "previous_stages", "bounds_description",
                }

                for placeholder in placeholders:
                    assert placeholder in valid_placeholders, (
                        f"Unknown placeholder '{placeholder}' in {prompt_name} v{version}"
                    )


class TestPromptVersioning:
    """Test prompt versioning functionality."""

    def test_can_retrieve_latest_version(self):
        """Ensure 'latest' version retrieval works."""
        registry = PromptRegistry.get_instance()

        if "planner.tool_selection" in registry.list_prompts():
            prompt = registry.get("planner.tool_selection", version="latest")
            assert prompt is not None
            assert len(prompt) > 0

    def test_prompt_version_metadata(self):
        """Ensure prompt versions have proper metadata."""
        registry = PromptRegistry.get_instance()

        for prompt_name, versions in registry.list_prompts().items():
            for version in versions:
                prompt_version = registry._prompts[prompt_name][version]

                # Check metadata exists
                assert prompt_version.name == prompt_name
                assert prompt_version.version == version
                assert prompt_version.description is not None
                assert prompt_version.constitutional_compliance is not None
                assert len(prompt_version.constitutional_compliance) > 0

    def test_v2_prompts_have_v1_counterparts(self):
        """Ensure v2 prompts have corresponding v1 versions."""
        registry = PromptRegistry.get_instance()
        prompts = registry.list_prompts()

        v2_prompts = [
            "intent.analysis_v2",
            "planner.tool_selection_v2",
            "planner.plan_generation_v2",
            "critic.response_validation_v2",
        ]

        for v2_name in v2_prompts:
            if v2_name in prompts:
                v1_name = v2_name.replace("_v2", "")
                assert v1_name in prompts, (
                    f"v2 prompt '{v2_name}' missing v1 counterpart '{v1_name}'"
                )


class TestIntentAnalysisPrompt:
    """Test intent.analysis prompt specifically."""

    def test_intent_analysis_has_json_output_format(self):
        """Ensure intent.analysis requests JSON output."""
        registry = PromptRegistry.get_instance()
        prompt = registry.get("intent.analysis", version="1.0")

        assert "JSON" in prompt, "intent.analysis should request JSON output"
        assert "intent" in prompt.lower()
        assert "confidence" in prompt.lower()

    def test_intent_analysis_mentions_clarification(self):
        """Ensure intent.analysis handles clarification."""
        registry = PromptRegistry.get_instance()
        prompt = registry.get("intent.analysis", version="1.0")

        assert "clarification" in prompt.lower(), (
            "intent.analysis should handle clarification"
        )

    def test_intent_analysis_provides_examples(self):
        """Ensure intent.analysis includes examples."""
        registry = PromptRegistry.get_instance()
        prompt = registry.get("intent.analysis", version="1.0")

        assert "example" in prompt.lower(), (
            "intent.analysis should provide examples"
        )
