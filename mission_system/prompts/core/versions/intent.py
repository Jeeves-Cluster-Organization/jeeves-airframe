"""
Intent Framer prompts - Version 1.0 (Intent analysis, P1 compliant)

Constitutional Compliance:
- P1 (NLP-First): Intent understanding, not pattern matching
- P3 (Friction Reduction): Confidence-based clarification

These prompts are used by IntentFramerAgent (Agent 2) to analyze user
messages and extract intent, goals, constraints, and ambiguities.
"""

from mission_system.prompts.core.registry import register_prompt
from mission_system.prompts.core import IDENTITY_BLOCK, STYLE_BLOCK, ROLE_INVARIANTS


@register_prompt(
    name="intent.analysis",
    version="1.0",
    description="Intent analysis prompt for extracting user intent from messages",
    constitutional_compliance="P1 (NLP-First), P3 (Friction Reduction)"
)
def intent_analysis_v1() -> str:
    """Core intent analysis prompt for IntentFramerAgent."""
    return """Analyze this user message and determine their intent.

USER: {user_message}
{context_section}
Return a JSON object with these fields:
- intent: What does the user want to do? Use a short action phrase.
- goals: List of specific things to achieve. Empty list if none.
- constraints: Any requirements or limitations. Empty list if none.
- ambiguities: Unclear parts. Empty list if clear.
- confidence: How certain are you? Number from 0.0 to 1.0.
- clarification_needed: true if you need more info, false if clear.
- clarification_question: Question to ask user, or null if not needed.

Common intents for this assistant:
- Add task: User wants to create a new task or reminder
- Complete task: User wants to mark a task as done
- List tasks: User wants to see their tasks
- Delete task: User wants to remove a task
- Add journal: User wants to log a note or thought
- Search: User wants to find something

Example for clear request "add a task to buy groceries":
{{"intent": "Add task", "goals": ["Create task: buy groceries"], "constraints": [], "ambiguities": [], "confidence": 0.95, "clarification_needed": false, "clarification_question": null}}

Example for unclear request "do the thing":
{{"intent": "Unknown", "goals": [], "constraints": [], "ambiguities": ["What thing?"], "confidence": 0.1, "clarification_needed": true, "clarification_question": "What would you like me to do?"}}

Respond with ONLY the JSON object, no other text."""


@register_prompt(
    name="intent.context_builder",
    version="1.0",
    description="Build context section for intent analysis",
    constitutional_compliance="P1 (NLP-First)"
)
def intent_context_builder_v1() -> str:
    """Template for context section in intent analysis."""
    return """
AVAILABLE CONTEXT:
{context_summary}

{task_context_section}

{pending_clarification_section}
"""


@register_prompt(
    name="intent.clarification_guidance",
    version="1.0",
    description="Guidance for when to request clarification",
    constitutional_compliance="P3 (Friction Reduction)"
)
def intent_clarification_guidance_v1() -> str:
    """Guidance for clarification decisions."""
    return """
CLARIFICATION GUIDELINES:

**When to request clarification:**
- Message is too vague to determine intent (e.g., "help", "do something")
- Critical information is missing for the intended action
- Multiple interpretations are equally likely
- Confidence score is below 0.4

**When NOT to request clarification:**
- Intent is reasonably clear even if details are missing
- Context provides sufficient disambiguation
- User has provided enough information to proceed
- Confidence score is 0.7 or higher

**Good clarification questions:**
- Specific: "What task would you like to complete?"
- Non-leading: "What would you like me to do?"
- Actionable: Answers should enable next step

**Avoid:**
- Asking about information you don't need
- Asking multiple questions at once
- Repeating clarification requests unnecessarily
"""


@register_prompt(
    name="intent.common_patterns",
    version="1.0",
    description="Common intent patterns for reference",
    constitutional_compliance="P1 (NLP-First)"
)
def intent_common_patterns_v1() -> str:
    """Reference for common intent patterns - NOT for pattern matching."""
    return """
COMMON USER INTENTS (for understanding, not pattern matching):

**Task Management:**
- Creating tasks: "add task", "remind me to", "I need to", "don't forget"
- Completing tasks: "mark done", "finished", "completed", "I did"
- Viewing tasks: "what tasks", "show me", "list my", "what do I have"
- Updating tasks: "change", "update", "reschedule", "move to"
- Deleting tasks: "remove", "delete", "cancel"

**Journal/Notes:**
- Adding entries: "note that", "remember", "log", "journal"
- Searching: "find", "search for", "when did I"

**Information:**
- Queries: "what is", "how do I", "explain"
- Status: "how many", "what's my", "status"

**Meta:**
- Help: "help", "what can you", "how to use"
- Greetings: "hi", "hello", casual conversation

IMPORTANT: Focus on UNDERSTANDING INTENT, not keyword matching.
The same intent can be expressed in many different ways.
"""


@register_prompt(
    name="intent.analysis_v2",
    version="2.0",
    description="Intent analysis with shared spine",
    constitutional_compliance="P1, P3, Amendment X"
)
def intent_analysis_v2() -> str:
    """Version 2.0: Uses shared prompt spine for consistency."""
    return f"""{IDENTITY_BLOCK}

**Your Role:** Intent Framer Agent - Understand what the user wants.

{STYLE_BLOCK}

{ROLE_INVARIANTS}

**Analysis Task:**

USER MESSAGE: "{{user_message}}"

{{context_section}}

**Required Analysis:**

1. **Intent Identification:**
   - What is the user trying to accomplish?
   - Express as a clear action phrase

2. **Goal Extraction:**
   - What specific outcomes does the user want?
   - List concrete, achievable goals

3. **Constraint Detection:**
   - Any limitations or requirements mentioned?
   - Time constraints, preferences, conditions

4. **Ambiguity Check:**
   - What aspects are unclear?
   - What would help clarify?

5. **Confidence Assessment:**
   - 0.8-1.0: Very confident, proceed
   - 0.6-0.79: Moderately confident, may clarify
   - 0.4-0.59: Uncertain, should clarify
   - 0.0-0.39: Very uncertain, must clarify

**Output (JSON only):**
{{{{"intent": "...", "goals": [...], "constraints": [...], "ambiguities": [...], "confidence": 0.0-1.0, "clarification_needed": true/false, "clarification_question": "..." or null}}}}"""
