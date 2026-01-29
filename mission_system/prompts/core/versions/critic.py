"""
Critic prompts - Version 1.0 and 2.0 (Intent-based validation, P1 compliant)

Constitutional Compliance:
- P1 (NLP-First): Semantic relevance, not keyword matching
- P2 (Reliability): Honest validation, fail loudly

Version 2.0 uses the shared prompt spine (prompts/core/).

This module contains ALL prompts used by CriticAgent (Agent 6):
- critic.response_validation: Primary response validation prompt
- critic.full_validation: Complete validation prompt with examples
- critic.hallucination_detection: Hallucination detection guidance
- critic.response_generation: Response generation guidance
"""

from mission_system.prompts.core.registry import register_prompt
from mission_system.prompts.core import IDENTITY_BLOCK, STYLE_BLOCK, ROLE_INVARIANTS, SAFETY_BLOCK


@register_prompt(
    name="critic.response_validation",
    version="1.0",
    description="Validate response quality and relevance (Amendment X compliant)",
    constitutional_compliance="P1 (NLP-First), P2 (Reliability), Amendment X"
)
def critic_response_validation_v1() -> str:
    """Full validation prompt externalized per Amendment X."""
    return """Review this response for hallucinations.

USER: "{user_message}"
TOOLS THAT RAN: {tool_list}
TOOL RESULTS: {tool_results_json}
RESPONSE: "{response_text}"

CHECK FOR HALLUCINATIONS:
- "added task" requires add_task in tools list
- "completed/marked done" requires task_complete in tools list
- "updated" requires update_task in tools list
- Claims success but tool status=error -> hallucination

DECISION:
- If response only mentions actions that DID execute -> accept
- If response claims action that DIDN'T execute -> retry_validator
- If all tools failed but response claims success -> retry_validator
- If search returned count=0 but response says "here are your X" -> retry_validator

Output ONE JSON object:
{{"action": "accept|retry_validator|retry_planner|clarify", "confidence": 0.8, "issue": null, "feedback": null, "clarification_question": null}}"""


@register_prompt(
    name="critic.response_validation_v2",
    version="2.0",
    description="Validate response quality with shared spine",
    constitutional_compliance="P1, P2, P6, Amendment X"
)
def critic_response_validation_v2() -> str:
    """Version 2.0: Uses shared prompt spine for consistency."""
    return f"""{IDENTITY_BLOCK}

**Your Role:** Critic Agent - Validate execution results against user intent.

{STYLE_BLOCK}

{ROLE_INVARIANTS}

{SAFETY_BLOCK}

**Validation Task:**

USER REQUEST: "{{user_message}}"
TOOLS EXECUTED: {{tool_list}}
TOOL RESULTS: {{tool_results_json}}
PROPOSED RESPONSE: "{{response_text}}"

**Validation Checks:**

1. **Hallucination Detection:**
   - Claims of "added task" require add_task in tools list
   - Claims of "completed" require task_complete in tools list
   - Claims of success when tool status=error is a hallucination

2. **Intent Alignment:**
   - Does the response address what the user asked for?
   - Are the actions performed aligned with the intent?

3. **Accuracy:**
   - Does the response match the actual tool results?
   - No fabricated data or invented details?

**Decision Rules:**
- Response matches reality -> accept
- Response claims unexecuted action -> retry_validator
- All tools failed but claims success -> retry_validator
- Search returned 0 but claims results -> retry_validator
- Intent unclear or unaddressed -> clarify

**Output (JSON only):**
{{{{"action": "accept|retry_validator|retry_planner|clarify", "confidence": 0.8, "issue": null, "feedback": null, "clarification_question": null}}}}"""


@register_prompt(
    name="critic.full_validation",
    version="1.0",
    description="Complete validation prompt with execution context",
    constitutional_compliance="P1 (NLP-First), P2 (Reliability)"
)
def critic_full_validation_v1() -> str:
    """Full validation prompt with complete execution context."""
    return """Validate this execution and generate a response.

USER REQUEST: {user_message}
INTENT: {intent}
GOALS: {goals}

PLAN STEPS: {steps_json}

EXECUTION RESULTS: {results_json}

Return a JSON object:
- verdict: "approved" if successful, "replan" if failed and should retry, "clarify" if need user input
- intent_alignment: 0.0-1.0 how well results match intent
- plan_match: true if plan executed correctly
- issues: array of problems found, each with type, severity (critical/warning/info), description
- suggested_response: Friendly message to user if approved. Be specific about what was done.
- replan_feedback: Advice for planner if verdict is replan
- clarification_question: Question to ask if verdict is clarify

If all tools succeeded, approve and write a clear response telling the user what was accomplished.

Example for successful task creation:
{{"verdict": "approved", "intent_alignment": 0.95, "plan_match": true, "issues": [], "suggested_response": "I've added 'Buy groceries' to your task list."}}

Example for failed execution:
{{"verdict": "replan", "intent_alignment": 0.3, "plan_match": false, "issues": [{{"type": "error", "severity": "critical", "description": "Tool returned error"}}], "replan_feedback": "Try a different approach"}}

Respond with ONLY the JSON object."""


@register_prompt(
    name="critic.hallucination_detection",
    version="1.0",
    description="Guidance for detecting hallucinations in responses",
    constitutional_compliance="P2 (Reliability)"
)
def critic_hallucination_detection_v1() -> str:
    """Hallucination detection guidance."""
    return """
HALLUCINATION DETECTION GUIDELINES:

A hallucination occurs when the response claims something that didn't happen.

**Common Hallucination Patterns:**

1. **Tool Execution Claims:**
   - Saying "I added the task" when add_task wasn't called
   - Saying "marked as complete" when task_complete wasn't called
   - Claiming success when all tools returned errors

2. **Data Fabrication:**
   - Inventing task titles not in the results
   - Claiming counts that don't match actual results
   - Adding details not present in tool outputs

3. **Status Misrepresentation:**
   - Claiming success when status="error"
   - Saying "found X items" when count=0
   - Partial success reported as full success

**Validation Rules:**

- Every claim in response must trace to actual tool output
- Numbers and counts must match exactly
- Status claims must match tool status
- If uncertain, mark as requiring validation
"""


@register_prompt(
    name="critic.response_generation",
    version="1.0",
    description="Guidance for generating user-facing responses",
    constitutional_compliance="P1 (NLP-First), P3 (Friction Reduction)"
)
def critic_response_generation_v1() -> str:
    """Response generation guidance."""
    return """
RESPONSE GENERATION GUIDELINES:

**Good Response Characteristics:**

1. **Specific:** Reference actual data from results
   - Good: "I've added 'Buy groceries' to your task list"
   - Bad: "Done!" or "Task added"

2. **Accurate:** Only claim what actually happened
   - If 2 of 3 tasks succeeded, say "I completed 2 tasks"
   - If search found 0 results, say "I didn't find any matching tasks"

3. **Helpful:** Provide actionable information
   - Include counts when relevant
   - Suggest next steps if appropriate
   - Acknowledge partial successes

4. **Concise:** Don't over-explain
   - One or two sentences is usually enough
   - Don't repeat the user's request back

**Response Templates by Action:**

- Task Created: "I've added '{title}' to your task list."
- Task Completed: "I've marked '{title}' as complete."
- Task Deleted: "The task has been deleted."
- Tasks Listed: "You have {count} tasks." / "You don't have any tasks."
- Search Results: "Found {count} matching items."
- No Results: "I didn't find anything matching that."
- Error: "I wasn't able to {action}. {error_reason}"
"""
