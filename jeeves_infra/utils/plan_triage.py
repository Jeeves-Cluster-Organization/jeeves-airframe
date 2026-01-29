"""Plan Triage - Heuristic pre-validation for execution plans.

M5 Enhancement (v0.14): Fast heuristic checks before sending plans
to Executor, catching obviously problematic plans without LLM calls.

This module provides lightweight validation that runs in <1ms,
saving LLM calls on obvious errors.
"""

from typing import Dict, Any, List, Tuple, Optional

from jeeves_infra.logging import get_current_logger


# Known tool names - should be kept in sync with tool registry
# But this is a fast heuristic, not authoritative validation
KNOWN_TOOLS = {
    "add_task", "get_tasks", "update_task", "delete_task",
    "task_complete", "task_complete_by_id", "search_tasks",
    "add_journal_entry", "journal_ingest", "get_journal_entries",
    "journal_list", "search_journal", "update_journal_entry",
    "memory_search", "get_user_context",
}


def triage_plan(plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Fast heuristic check before execution.

    M5 Enhancement: Apply simple heuristics to catch obviously
    problematic plans without burning LLM calls.

    Args:
        plan: Plan dictionary with 'execution_plan' key containing steps

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if plan passes heuristics
        - error_message: Description of issue if invalid, None if valid
    """
    _logger = get_current_logger()
    steps = plan.get("execution_plan", plan.get("steps", []))

    # Heuristic 1: Empty plan
    if not steps:
        return False, "Plan has no steps"

    # Heuristic 2: Too many steps for simple request
    if len(steps) > 10:
        _logger.warning("plan_triage_many_steps", step_count=len(steps))
        return False, f"Plan has {len(steps)} steps - consider simplifying"

    # Heuristic 3: Unknown tool references
    for i, step in enumerate(steps):
        tool = step.get("tool", "").lower()
        if tool and tool not in KNOWN_TOOLS:
            # Log but don't fail - tool registry is authoritative
            _logger.debug(
                "plan_triage_unknown_tool",
                tool=tool,
                step_index=i
            )

    # Heuristic 4: Circular dependencies (simplified)
    step_ids = []
    for step in steps:
        step_id = step.get("id") or step.get("tool")
        step_ids.append(step_id)

    for step in steps:
        deps = step.get("depends_on", [])
        step_id = step.get("id") or step.get("tool")
        if step_id and step_id in deps:
            return False, f"Step {step_id} depends on itself"

    # Heuristic 5: Missing required parameters
    for i, step in enumerate(steps):
        tool = step.get("tool", "")
        params = step.get("parameters", {})

        # user_id is required for most tools
        if tool in {"add_task", "get_tasks", "search_tasks"} and not params.get("user_id"):
            # Allow placeholder
            if "{{USER_ID}}" not in str(params):
                _logger.debug(
                    "plan_triage_missing_user_id",
                    tool=tool,
                    step_index=i
                )

    # Heuristic 6: Duplicate consecutive tools (possible mistake)
    if len(steps) >= 2:
        for i in range(len(steps) - 1):
            if steps[i].get("tool") == steps[i + 1].get("tool"):
                params_same = steps[i].get("parameters") == steps[i + 1].get("parameters")
                if params_same:
                    tool = steps[i].get("tool")
                    _logger.warning(
                        "plan_triage_duplicate_steps",
                        tool=tool,
                        step_index=i
                    )
                    # Don't fail, just warn

    return True, None


def get_plan_complexity_score(plan: Dict[str, Any]) -> int:
    """Calculate a complexity score for the plan.

    M5 Enhancement: Quick complexity assessment for logging/monitoring.

    Args:
        plan: Plan dictionary

    Returns:
        Complexity score (higher = more complex)
        - 1-3: Simple (1-2 tools, basic operations)
        - 4-6: Medium (3-5 tools, some dependencies)
        - 7-10: Complex (6+ tools, multiple dependencies)
    """
    steps = plan.get("execution_plan", plan.get("steps", []))
    score = 0

    # Base score from step count
    step_count = len(steps)
    if step_count <= 2:
        score += 1
    elif step_count <= 5:
        score += 3
    else:
        score += 5

    # Add for dependencies
    total_deps = sum(len(s.get("depends_on", [])) for s in steps)
    if total_deps > 0:
        score += min(3, total_deps)

    # Add for unique tool types
    unique_tools = len(set(s.get("tool", "") for s in steps))
    if unique_tools > 3:
        score += 2

    return min(10, score)


def summarize_plan_for_logging(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Create a concise summary of plan for logging.

    Args:
        plan: Plan dictionary

    Returns:
        Summary dictionary suitable for structured logging
    """
    steps = plan.get("execution_plan", plan.get("steps", []))

    return {
        "step_count": len(steps),
        "tools": [s.get("tool") for s in steps],
        "complexity": get_plan_complexity_score(plan),
        "intent": plan.get("intent", "unknown")[:50],
        "confidence": plan.get("confidence", 0.0),
    }
