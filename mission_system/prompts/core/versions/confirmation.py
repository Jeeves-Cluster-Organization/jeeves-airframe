"""
Confirmation flow prompts - Version 1.0 (Intent-based, P1 compliant)

Constitutional Compliance:
- P1 (NLP-First): Intent understanding, not keyword matching
- P5 (Deterministic Spine): Strict validation at LLM boundaries
"""

from mission_system.prompts.core.registry import register_prompt


@register_prompt(
    name="confirmation.detection",
    version="1.0",
    description="Detect if user message is a confirmation response",
    constitutional_compliance="P1 (NLP-First)"
)
def confirmation_detection_v1() -> str:
    return """You are analyzing whether a user message is a response to a confirmation request.

**Context:**
- System asked: "{confirmation_message}"
- User responded: "{user_response}"

**Your Task:**
Determine if the user's response is:
1. **Affirmative** - User agrees to proceed (yes, ok, sure, go ahead, etc.)
2. **Negative** - User declines (no, cancel, stop, never mind, etc.)
3. **Modification** - User agrees but wants to change parameters (yes but..., sure with..., ok make it...)
4. **Unrelated** - User's response is a new request, not a confirmation response

**Important (Constitutional P1):**
- Understand the user's INTENT through semantic meaning
- Accept any natural phrasing
- Affirmative examples: "yes", "ok", "sure", "yeah", "yep", "go for it", "proceed", "confirm", "do it", "make it so", "make it happen", "affirmative", "absolutely", "definitely", "approved", "sounds good", "let's do it", "execute", "engage"
- Negative examples: "no", "nope", "nah", "cancel", "stop", "never mind", "don't", "abort", "negative"
- Modification examples: "yes but change...", "sure with different...", "ok but make it...", "change it to...", "yes but use..." (note: must include parameter change)
- "nah" = negative (casual "no")
- "yeah" = affirmative (casual "yes")
- "yes but X" = modification ONLY if X changes parameters (e.g., "yes but make it high priority")
- "make it so" = affirmative (Star Trek reference meaning "proceed")

**CRITICAL: Output ONLY valid JSON, no explanations or other text.**

**Output Format:**
{{
  "is_confirmation_response": true,
  "type": "affirmative",
  "confidence": 0.95
}}

Your response must be pure JSON only. Do not include any explanatory text before or after the JSON."""


@register_prompt(
    name="confirmation.interpretation",
    version="1.0",
    description="Interpret confirmation response and extract modifications",
    constitutional_compliance="P1 (NLP-First), P5 (Deterministic Spine)"
)
def confirmation_interpretation_v1() -> str:
    return """You are interpreting a confirmation response to extract user intent.

**Original Request:** "{original_request}"
**System Confirmation:** "{confirmation_message}"
**User Response:** "{user_response}"
**Proposed Parameters:** {proposed_parameters}

**Your Task:**
1. Determine user's decision (yes/no/modify)
2. Extract any parameter updates from natural language

**Decision Rules:**
- **YES**: User confirms/affirms the action (with or without parameter tweaks)
  Examples: "yes", "sure", "ok", "proceed", "yes with high priority", "yes please, but set the priority to high"
  -> decision: "yes", parameter_updates: {{"priority": "high"}}

- **NO**: User declines/cancels the action
  Examples: "no", "cancel", "nah", "stop", "never mind"
  -> decision: "no"

- **MODIFY**: User wants to fundamentally change the action (not just tweak parameters)
  Examples: "change the title to quarterly report", "make it about something else"
  -> decision: "modify", modification_description: "..."

**CRITICAL: "yes but..." or "yes with..." is still YES (with parameter_updates), NOT modify!**
- "yes but make it high priority" -> decision: "yes", parameter_updates: {{"priority": "high"}}
- "sure, set status to in progress" -> decision: "yes", parameter_updates: {{"status": "in_progress"}}
- "ok but tomorrow" -> decision: "yes", parameter_updates: {{"due_date": "tomorrow"}}
- "yes please, but set the priority to high" -> decision: "yes", parameter_updates: {{"priority": "high"}}

**Important (Constitutional P1):**
- "yes" with conditions = still YES (just populate parameter_updates)
- "no" or "nah" or "cancel" = NO
- Only use MODIFY if user wants to change what the action does entirely
- Understand natural language: "make it urgent" = "high priority" = "priority high" = all mean priority:high

**Output (JSON only, no other text):**
{{
  "decision": "yes",
  "confidence": 0.95,
  "parameter_updates": {{
    "priority": "high"
  }},
  "modification_description": null
}}"""
