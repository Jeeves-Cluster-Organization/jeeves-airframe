"""Test Configuration Package.

Per Engineering Improvement Plan v4.3 - Unified Test Infrastructure.

This package provides centralized test configuration with clear separation:
- environment.py: CI detection, database config, performance settings
- markers.py: Pytest marker definitions and skip logic
- llm_config.py: LLM configuration (LLAMASERVER_ALWAYS policy)
- services.py: Service availability detection (NEW v4.3)
- endpoints.py: URLs, ports, hosts
- test_thresholds.py: Confidence values and thresholds
- timeouts.py: Timeout and delay values
- fixtures_data.py: Test data constants

Constitutional Compliance:
- P6: Testable, Observable, Repairable
- P2: Reliability - Fail fast on missing config
- M4: Observability - Clear service status reporting
- Amendment I: Repo Hygiene - Single source of truth
- Amendment V: Bootstrap Freedom - No backward compatibility pre-v1.0
"""

from mission_system.tests.config.environment import (
    # Environment Detection
    IS_CI,
    IS_GITHUB_ACTIONS,
    is_running_in_ci,
    # Database Configuration
    TEST_DATABASE_BACKEND,
    TEST_POSTGRES_HOST,
    TEST_POSTGRES_PORT,
    TEST_POSTGRES_USER,
    TEST_POSTGRES_PASSWORD,
    TEST_POSTGRES_DATABASE,
    get_test_postgres_url,
    # Feature Flags
    MEMORY_TESTS_ENABLED,
    PROD_TESTS_ENABLED,
    CONTRACT_TESTS_ENABLED,
    # Performance
    TEST_TIMEOUT,
    POSTGRES_CONTAINER_TIMEOUT,
    TEST_DB_SCOPE,
    should_skip_slow_tests,
    # Logging
    TEST_LOG_LEVEL,
    SILENCE_LIBRARY_LOGS,
)

from mission_system.tests.config.llm_config import (
    # LLM Configuration
    DEFAULT_LLM_PROVIDER,
    LLAMASERVER_HOST,
    DEFAULT_MODEL,
    MOCK_ALLOWED_ONLY_IN_CI,
    AZURE_AVAILABLE,
    get_llm_provider_type,
    is_llamaserver_available,
)

from mission_system.tests.config.services import (
    # Service Detection (v4.3)
    is_postgres_available,
    is_llama_server_available,
    is_api_available,
    are_all_services_available,
    get_cached_service_status,
    clear_service_cache,
    get_service_status_report,
)

from mission_system.tests.config.endpoints import (
    # LlamaServer
    TEST_LLAMASERVER_HOST,
    TEST_LLAMASERVER_PORT,
    TEST_LLAMASERVER_MULTI_NODE_PORTS,
    # API
    TEST_API_HOST,
    TEST_API_PORT,
    TEST_API_BASE_URL,
    # WebSocket
    TEST_WEBSOCKET_URL,
    # Helpers
    get_llamaserver_url,
    get_api_url,
)

from mission_system.tests.config.test_thresholds import (
    # Confidence Levels
    TEST_HIGH_CONFIDENCE,
    TEST_MEDIUM_HIGH_CONFIDENCE,
    TEST_MEDIUM_CONFIDENCE,
    TEST_LOW_CONFIDENCE,
    TEST_BELOW_THRESHOLD_CONFIDENCE,
    TEST_FAILURE_CONFIDENCE,
    # Agent Thresholds
    TEST_CRITIC_APPROVAL_THRESHOLD,
    TEST_CRITIC_RETRY_THRESHOLD,
    TEST_PLANNER_CLARIFICATION_THRESHOLD,
    TEST_META_VALIDATOR_PASS_THRESHOLD,
    # Fuzzy Matching
    TEST_FUZZY_MATCH_MIN_SCORE,
    TEST_FUZZY_MATCH_HIGH_SCORE,
    TEST_SEMANTIC_SEARCH_MIN_SIMILARITY,
    # Test Scenario Scores
    TEST_EXACT_MATCH_SCORE,
    TEST_SUBSTRING_MATCH_SCORE,
    TEST_PARTIAL_MATCH_SCORE,
    TEST_WEAK_MATCH_SCORE,
    # Embedding
    TEST_EMBEDDING_DIMENSION,
    TEST_COSINE_SIMILARITY_MIN,
    TEST_COSINE_SIMILARITY_HIGH,
    TEST_COSINE_SIMILARITY_IDENTITY,
)

from mission_system.tests.config.timeouts import (
    # Server Startup
    TEST_SERVER_STARTUP_TIMEOUT,
    TEST_POSTGRES_STARTUP_TIMEOUT,
    TEST_LLAMASERVER_STARTUP_TIMEOUT,
    # HTTP
    TEST_HTTP_REQUEST_TIMEOUT,
    TEST_HEALTH_CHECK_TIMEOUT,
    TEST_LLAMASERVER_CONNECTIVITY_TIMEOUT,
    TEST_LLM_REQUEST_TIMEOUT,
    # Circuit Breaker
    TEST_CIRCUIT_BREAKER_CALL_TIMEOUT,
    TEST_CIRCUIT_BREAKER_RESET_TIMEOUT,
    # Async Sleep
    TEST_ASYNC_SLEEP_TINY,
    TEST_ASYNC_SLEEP_SHORT,
    TEST_ASYNC_SLEEP_MEDIUM,
    TEST_ASYNC_SLEEP_LONG,
    TEST_ASYNC_SLEEP_EXTENDED,
    # Rate Limiter
    TEST_RATE_LIMITER_WINDOW,
    TEST_RATE_LIMITER_WAIT,
    # WebSocket
    TEST_WEBSOCKET_CONNECT_TIMEOUT,
    TEST_WEBSOCKET_IDLE_TIMEOUT,
    # Database
    TEST_DB_QUERY_TIMEOUT,
    TEST_DB_CONNECT_TIMEOUT,
    # Execution
    TEST_MAX_EXECUTION_TIME,
    TEST_RETRY_DELAY,
    TEST_MAX_RETRIES,
)

from mission_system.tests.config.fixtures_data import (
    # User IDs
    TEST_USER_ID,
    TEST_USER_ID_ALT,
    TEST_USER_ID_1,
    TEST_USER_ID_2,
    TEST_USER_ID_3,
    TEST_USER_ID_E2E,
    # Session IDs
    TEST_SESSION_ID,
    TEST_SESSION_ID_ALT,
    TEST_SESSION_ID_E2E,
    # Request IDs
    TEST_REQUEST_ID,
    TEST_REQUEST_ID_ALT,
    # Task Status
    TEST_STATUS_PENDING,
    TEST_STATUS_IN_PROGRESS,
    TEST_STATUS_COMPLETED,
    TEST_STATUS_CANCELLED,
    TEST_REQUEST_STATUS_PROCESSING,
    TEST_REQUEST_STATUS_COMPLETED,
    TEST_REQUEST_STATUS_ERROR,
    # Priority
    TEST_PRIORITY_HIGH,
    TEST_PRIORITY_MEDIUM,
    TEST_PRIORITY_LOW,
    TEST_PRIORITY_HIGH_STR,
    TEST_PRIORITY_MEDIUM_STR,
    TEST_PRIORITY_LOW_STR,
    # Content
    TEST_TASK_TITLE,
    TEST_TASK_TITLE_BUY_MILK,
    TEST_TASK_TITLE_CALL_MOM,
    TEST_TASK_TITLE_GROCERIES,
    TEST_TASK_DESCRIPTION,
    TEST_TASK_DESCRIPTION_LONG,
    TEST_JOURNAL_CONTENT,
    TEST_JOURNAL_CONTENT_LONG,
    TEST_USER_MESSAGE,
    TEST_USER_MESSAGE_ADD_TASK,
    TEST_USER_MESSAGE_SHOW_TASKS,
    # Tool Names
    TEST_TOOL_ADD_TASK,
    TEST_TOOL_LIST_TASKS,
    TEST_TOOL_UPDATE_TASK,
    TEST_TOOL_DELETE_TASK,
    TEST_TOOL_SEARCH_TASKS,
    # LLM Test Values
    TEST_MODEL_NAME,
    TEST_PROVIDER_NAME,
    # Helpers
    get_numbered_user_id,
    get_numbered_session_id,
    get_numbered_task_title,
)

# Markers module requires pytest - only import when available
try:
    from mission_system.tests.config.markers import (
        configure_markers,
        apply_skip_markers,
        setup_e2e_skip,
    )
    _MARKERS_AVAILABLE = True
except ImportError:
    # pytest not installed - provide stubs for non-test contexts
    def configure_markers(config): pass
    def apply_skip_markers(config, items): pass
    def setup_e2e_skip(item): pass
    _MARKERS_AVAILABLE = False


__all__ = [
    # Environment
    "IS_CI",
    "IS_GITHUB_ACTIONS",
    "is_running_in_ci",
    # Database
    "TEST_DATABASE_BACKEND",
    "TEST_POSTGRES_HOST",
    "TEST_POSTGRES_PORT",
    "TEST_POSTGRES_USER",
    "TEST_POSTGRES_PASSWORD",
    "TEST_POSTGRES_DATABASE",
    "get_test_postgres_url",
    # Feature Flags
    "MEMORY_TESTS_ENABLED",
    "PROD_TESTS_ENABLED",
    "CONTRACT_TESTS_ENABLED",
    # Performance
    "TEST_TIMEOUT",
    "POSTGRES_CONTAINER_TIMEOUT",
    "TEST_DB_SCOPE",
    "should_skip_slow_tests",
    # Logging
    "TEST_LOG_LEVEL",
    "SILENCE_LIBRARY_LOGS",
    # LLM
    "DEFAULT_LLM_PROVIDER",
    "LLAMASERVER_HOST",
    "DEFAULT_MODEL",
    "MOCK_ALLOWED_ONLY_IN_CI",
    "AZURE_AVAILABLE",
    "get_llm_provider_type",
    "is_llamaserver_available",
    # Service Detection (v4.3)
    "is_postgres_available",
    "is_llama_server_available",
    "is_api_available",
    "are_all_services_available",
    "get_cached_service_status",
    "clear_service_cache",
    "get_service_status_report",
    # Endpoints
    "TEST_LLAMASERVER_HOST",
    "TEST_LLAMASERVER_PORT",
    "TEST_LLAMASERVER_MULTI_NODE_PORTS",
    "TEST_API_HOST",
    "TEST_API_PORT",
    "TEST_API_BASE_URL",
    "TEST_WEBSOCKET_URL",
    "get_llamaserver_url",
    "get_api_url",
    # Thresholds (v4.2)
    "TEST_HIGH_CONFIDENCE",
    "TEST_MEDIUM_HIGH_CONFIDENCE",
    "TEST_MEDIUM_CONFIDENCE",
    "TEST_LOW_CONFIDENCE",
    "TEST_BELOW_THRESHOLD_CONFIDENCE",
    "TEST_FAILURE_CONFIDENCE",
    "TEST_CRITIC_APPROVAL_THRESHOLD",
    "TEST_CRITIC_RETRY_THRESHOLD",
    "TEST_PLANNER_CLARIFICATION_THRESHOLD",
    "TEST_META_VALIDATOR_PASS_THRESHOLD",
    "TEST_FUZZY_MATCH_MIN_SCORE",
    "TEST_FUZZY_MATCH_HIGH_SCORE",
    "TEST_SEMANTIC_SEARCH_MIN_SIMILARITY",
    "TEST_EXACT_MATCH_SCORE",
    "TEST_SUBSTRING_MATCH_SCORE",
    "TEST_PARTIAL_MATCH_SCORE",
    "TEST_WEAK_MATCH_SCORE",
    "TEST_EMBEDDING_DIMENSION",
    "TEST_COSINE_SIMILARITY_MIN",
    "TEST_COSINE_SIMILARITY_HIGH",
    "TEST_COSINE_SIMILARITY_IDENTITY",
    # Timeouts (v4.2)
    "TEST_SERVER_STARTUP_TIMEOUT",
    "TEST_POSTGRES_STARTUP_TIMEOUT",
    "TEST_LLAMASERVER_STARTUP_TIMEOUT",
    "TEST_HTTP_REQUEST_TIMEOUT",
    "TEST_HEALTH_CHECK_TIMEOUT",
    "TEST_LLAMASERVER_CONNECTIVITY_TIMEOUT",
    "TEST_LLM_REQUEST_TIMEOUT",
    "TEST_CIRCUIT_BREAKER_CALL_TIMEOUT",
    "TEST_CIRCUIT_BREAKER_RESET_TIMEOUT",
    "TEST_ASYNC_SLEEP_TINY",
    "TEST_ASYNC_SLEEP_SHORT",
    "TEST_ASYNC_SLEEP_MEDIUM",
    "TEST_ASYNC_SLEEP_LONG",
    "TEST_ASYNC_SLEEP_EXTENDED",
    "TEST_RATE_LIMITER_WINDOW",
    "TEST_RATE_LIMITER_WAIT",
    "TEST_WEBSOCKET_CONNECT_TIMEOUT",
    "TEST_WEBSOCKET_IDLE_TIMEOUT",
    "TEST_DB_QUERY_TIMEOUT",
    "TEST_DB_CONNECT_TIMEOUT",
    "TEST_MAX_EXECUTION_TIME",
    "TEST_RETRY_DELAY",
    "TEST_MAX_RETRIES",
    # Fixtures Data (v4.2)
    "TEST_USER_ID",
    "TEST_USER_ID_ALT",
    "TEST_USER_ID_1",
    "TEST_USER_ID_2",
    "TEST_USER_ID_3",
    "TEST_USER_ID_E2E",
    "TEST_SESSION_ID",
    "TEST_SESSION_ID_ALT",
    "TEST_SESSION_ID_E2E",
    "TEST_REQUEST_ID",
    "TEST_REQUEST_ID_ALT",
    "TEST_STATUS_PENDING",
    "TEST_STATUS_IN_PROGRESS",
    "TEST_STATUS_COMPLETED",
    "TEST_STATUS_CANCELLED",
    "TEST_REQUEST_STATUS_PROCESSING",
    "TEST_REQUEST_STATUS_COMPLETED",
    "TEST_REQUEST_STATUS_ERROR",
    "TEST_PRIORITY_HIGH",
    "TEST_PRIORITY_MEDIUM",
    "TEST_PRIORITY_LOW",
    "TEST_PRIORITY_HIGH_STR",
    "TEST_PRIORITY_MEDIUM_STR",
    "TEST_PRIORITY_LOW_STR",
    "TEST_TASK_TITLE",
    "TEST_TASK_TITLE_BUY_MILK",
    "TEST_TASK_TITLE_CALL_MOM",
    "TEST_TASK_TITLE_GROCERIES",
    "TEST_TASK_DESCRIPTION",
    "TEST_TASK_DESCRIPTION_LONG",
    "TEST_JOURNAL_CONTENT",
    "TEST_JOURNAL_CONTENT_LONG",
    "TEST_USER_MESSAGE",
    "TEST_USER_MESSAGE_ADD_TASK",
    "TEST_USER_MESSAGE_SHOW_TASKS",
    "TEST_TOOL_ADD_TASK",
    "TEST_TOOL_LIST_TASKS",
    "TEST_TOOL_UPDATE_TASK",
    "TEST_TOOL_DELETE_TASK",
    "TEST_TOOL_SEARCH_TASKS",
    "TEST_MODEL_NAME",
    "TEST_PROVIDER_NAME",
    "get_numbered_user_id",
    "get_numbered_session_id",
    "get_numbered_task_title",
    # Markers
    "configure_markers",
    "apply_skip_markers",
    "setup_e2e_skip",
]
