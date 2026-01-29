"""Test Fixture Data Constants.

Per Engineering Improvement Plan v4.2 - Phase C1: Test Config Centralization.

This module centralizes all test data constants used across test fixtures.
Instead of hardcoding values like "test-user", "user-123", "pending" throughout
test files, import from here.

Usage:
    from mission_system.tests.config.fixtures_data import TEST_USER_ID, TEST_STATUS_PENDING

Constitutional Compliance:
- Amendment I: Repo Hygiene - Single source of truth for test data
- P6: Testable - Consistent test data across all tests
"""

# =============================================================================
# User Identifiers
# =============================================================================

# Primary test user ID (use this by default)
TEST_USER_ID = "test-user"

# Alternative test user ID (for multi-user scenarios)
TEST_USER_ID_ALT = "test-user-2"

# Specific numbered user IDs (for iteration tests)
TEST_USER_ID_1 = "user-1"
TEST_USER_ID_2 = "user-2"
TEST_USER_ID_3 = "user-3"

# E2E test user ID
TEST_USER_ID_E2E = "e2e-user"


# =============================================================================
# Session Identifiers
# =============================================================================

# Primary test session ID
TEST_SESSION_ID = "test-session"

# Alternative test session ID
TEST_SESSION_ID_ALT = "test-session-2"

# E2E test session ID
TEST_SESSION_ID_E2E = "e2e-session"


# =============================================================================
# Request Identifiers
# =============================================================================

# Primary test request ID
TEST_REQUEST_ID = "test-request"

# Alternative test request ID
TEST_REQUEST_ID_ALT = "test-request-2"


# =============================================================================
# Task Status Values
# =============================================================================

# Standard task statuses
TEST_STATUS_PENDING = "pending"
TEST_STATUS_IN_PROGRESS = "in_progress"
TEST_STATUS_COMPLETED = "completed"
TEST_STATUS_CANCELLED = "cancelled"

# Request statuses
TEST_REQUEST_STATUS_PROCESSING = "processing"
TEST_REQUEST_STATUS_COMPLETED = "completed"
TEST_REQUEST_STATUS_ERROR = "error"


# =============================================================================
# Priority Values
# =============================================================================

# Task priorities
TEST_PRIORITY_HIGH = 0
TEST_PRIORITY_MEDIUM = 1
TEST_PRIORITY_LOW = 2

# String versions for API tests
TEST_PRIORITY_HIGH_STR = "high"
TEST_PRIORITY_MEDIUM_STR = "medium"
TEST_PRIORITY_LOW_STR = "low"


# =============================================================================
# Test Content
# =============================================================================

# Standard test task titles
TEST_TASK_TITLE = "Test task"
TEST_TASK_TITLE_BUY_MILK = "Buy milk"
TEST_TASK_TITLE_CALL_MOM = "Call mom"
TEST_TASK_TITLE_GROCERIES = "Get groceries"

# Standard test task descriptions
TEST_TASK_DESCRIPTION = "Test task description"
TEST_TASK_DESCRIPTION_LONG = "This is a longer test task description for testing purposes"

# Standard test journal entries
TEST_JOURNAL_CONTENT = "Test journal entry"
TEST_JOURNAL_CONTENT_LONG = "This is a longer test journal entry for testing purposes"

# Standard test user messages
TEST_USER_MESSAGE = "Test message"
TEST_USER_MESSAGE_ADD_TASK = "Add task: test task"
TEST_USER_MESSAGE_SHOW_TASKS = "Show my tasks"


# =============================================================================
# Test Tool Names
# =============================================================================

# Common tool names for testing
TEST_TOOL_ADD_TASK = "add_task"
TEST_TOOL_LIST_TASKS = "list_tasks"
TEST_TOOL_UPDATE_TASK = "update_task"
TEST_TOOL_DELETE_TASK = "delete_task"
TEST_TOOL_SEARCH_TASKS = "search_tasks"


# =============================================================================
# LLM Provider Test Values
# =============================================================================

# Test model name
TEST_MODEL_NAME = "test-model"

# Test provider name
TEST_PROVIDER_NAME = "test-provider"


# =============================================================================
# Helper Functions
# =============================================================================

def get_numbered_user_id(n: int) -> str:
    """Get a numbered user ID for iteration tests.

    Args:
        n: User number

    Returns:
        User ID string like "user-1", "user-2", etc.
    """
    return f"user-{n}"


def get_numbered_session_id(n: int) -> str:
    """Get a numbered session ID for iteration tests.

    Args:
        n: Session number

    Returns:
        Session ID string like "session-1", "session-2", etc.
    """
    return f"session-{n}"


def get_numbered_task_title(n: int) -> str:
    """Get a numbered task title for iteration tests.

    Args:
        n: Task number

    Returns:
        Task title string like "Task 1", "Task 2", etc.
    """
    return f"Task {n}"
