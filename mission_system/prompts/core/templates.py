"""
Prompt template utilities for mission system agents.

Constitutional Alignment:
- P1 (NLP-First): Intent-based guidance, not pattern rules
"""


def intent_based_tool_guidance(tools_description: str) -> str:
    """
    Standard intent-based tool selection guidance.

    Constitutional Alignment: P1 (NLP-First)
    - Focuses on intent, not keywords
    - Provides semantic context, not pattern rules
    """
    return f"""
**Tool Selection Guidance:**

Understand the user's intent and select appropriate tools based on what they want to accomplish.

{tools_description}

**Important:**
- Focus on user INTENT, not specific keywords
- These descriptions help you understand tool purposes
- Users can express intent in any natural phrasing
- Synonyms are acceptable (add/create/make, find/search/locate, etc.)
"""


def confidence_based_response(action_type: str) -> str:
    """Standard confidence-based decision guidance."""
    return f"""
Express your confidence (0.0-1.0) in this {action_type}.

Confidence guidelines:
- 0.9-1.0: Very confident, clear intent, all information present
- 0.7-0.89: Confident but minor ambiguity
- 0.5-0.69: Uncertain, multiple interpretations possible
- 0.0-0.49: Very uncertain, need clarification

Per Constitution P3, confirmations are confidence-based:
- Confidence >= 0.85: Execute without confirmation
- Confidence < 0.85: Request confirmation or clarification
"""
