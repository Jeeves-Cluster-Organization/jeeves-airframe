"""Unit tests for the bootstrap module.

Tests:
- _parse_bool helper
- create_core_config_from_env (env var parsing, defaults)
- create_orchestration_flags_from_env (env var parsing, defaults)
- Request PID context management (set, get, clear, context manager)
- create_app_context composition root (dependency wiring, injection overrides)
- sync_quota_defaults_to_kernel (happy path, failure handling)
- create_tool_executor_with_access factory
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jeeves_infra.bootstrap import (
    _parse_bool,
    create_core_config_from_env,
    create_orchestration_flags_from_env,
    create_app_context,
    set_request_pid,
    get_request_pid,
    clear_request_pid,
    request_pid_context,
    sync_quota_defaults_to_kernel,
)
from jeeves_infra.protocols import ExecutionConfig, ContextBounds, OrchestrationFlags


# =============================================================================
# _parse_bool
# =============================================================================


class TestParseBool:
    def test_true_string(self):
        assert _parse_bool("true") is True

    def test_True_string(self):
        assert _parse_bool("True") is True

    def test_TRUE_string(self):
        assert _parse_bool("TRUE") is True

    def test_false_string(self):
        assert _parse_bool("false") is False

    def test_False_string(self):
        assert _parse_bool("False") is False

    def test_empty_string_uses_default_true(self):
        assert _parse_bool("", default=True) is True

    def test_empty_string_uses_default_false(self):
        assert _parse_bool("", default=False) is False

    def test_arbitrary_string_is_false(self):
        assert _parse_bool("yes") is False
        assert _parse_bool("1") is False
        assert _parse_bool("on") is False


# =============================================================================
# create_core_config_from_env
# =============================================================================


class TestCreateCoreConfigFromEnv:
    def test_defaults_when_no_env_vars(self):
        with patch.dict(os.environ, {}, clear=True):
            config = create_core_config_from_env()

        assert isinstance(config, ExecutionConfig)
        assert config.max_iterations == 3
        assert config.max_llm_calls == 10
        assert config.max_agent_hops == 21
        assert config.enable_telemetry is True
        assert config.enable_checkpoints is False
        assert config.debug_mode is False

        assert isinstance(config.context_bounds, ContextBounds)
        assert config.context_bounds.max_input_tokens == 4096
        assert config.context_bounds.max_output_tokens == 2048
        assert config.context_bounds.max_context_tokens == 16384
        assert config.context_bounds.reserved_tokens == 512

    def test_custom_env_vars(self):
        env = {
            "CORE_MAX_ITERATIONS": "5",
            "CORE_MAX_LLM_CALLS": "20",
            "CORE_MAX_AGENT_HOPS": "10",
            "CORE_ENABLE_TELEMETRY": "false",
            "CORE_ENABLE_CHECKPOINTS": "true",
            "CORE_DEBUG_MODE": "true",
            "CORE_MAX_INPUT_TOKENS": "8192",
            "CORE_MAX_OUTPUT_TOKENS": "4096",
            "CORE_MAX_CONTEXT_TOKENS": "32768",
            "CORE_RESERVED_TOKENS": "1024",
        }
        with patch.dict(os.environ, env, clear=True):
            config = create_core_config_from_env()

        assert config.max_iterations == 5
        assert config.max_llm_calls == 20
        assert config.max_agent_hops == 10
        assert config.enable_telemetry is False
        assert config.enable_checkpoints is True
        assert config.debug_mode is True
        assert config.context_bounds.max_input_tokens == 8192
        assert config.context_bounds.max_output_tokens == 4096
        assert config.context_bounds.max_context_tokens == 32768
        assert config.context_bounds.reserved_tokens == 1024

    def test_partial_env_vars(self):
        env = {
            "CORE_MAX_LLM_CALLS": "50",
        }
        with patch.dict(os.environ, env, clear=True):
            config = create_core_config_from_env()

        assert config.max_llm_calls == 50
        # Other fields use defaults
        assert config.max_iterations == 3
        assert config.max_agent_hops == 21

    def test_invalid_integer_raises(self):
        env = {"CORE_MAX_ITERATIONS": "not_a_number"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError):
                create_core_config_from_env()

    def test_returns_execution_config_type(self):
        with patch.dict(os.environ, {}, clear=True):
            config = create_core_config_from_env()
        assert isinstance(config, ExecutionConfig)

    def test_context_bounds_embedded(self):
        env = {
            "CORE_MAX_INPUT_TOKENS": "1000",
            "CORE_MAX_OUTPUT_TOKENS": "500",
            "CORE_MAX_CONTEXT_TOKENS": "2000",
            "CORE_RESERVED_TOKENS": "100",
        }
        with patch.dict(os.environ, env, clear=True):
            config = create_core_config_from_env()

        bounds = config.context_bounds
        assert bounds.max_input_tokens == 1000
        assert bounds.max_output_tokens == 500
        assert bounds.max_context_tokens == 2000
        assert bounds.reserved_tokens == 100

    def test_boolean_telemetry_default_true(self):
        """CORE_ENABLE_TELEMETRY defaults to true when not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = create_core_config_from_env()
        assert config.enable_telemetry is True

    def test_boolean_checkpoints_default_false(self):
        """CORE_ENABLE_CHECKPOINTS defaults to false when not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = create_core_config_from_env()
        assert config.enable_checkpoints is False

    def test_boolean_debug_mode_default_false(self):
        """CORE_DEBUG_MODE defaults to false when not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = create_core_config_from_env()
        assert config.debug_mode is False


# =============================================================================
# create_orchestration_flags_from_env
# =============================================================================


class TestCreateOrchestrationFlagsFromEnv:
    def test_defaults_when_no_env_vars(self):
        with patch.dict(os.environ, {}, clear=True):
            flags = create_orchestration_flags_from_env()

        assert isinstance(flags, OrchestrationFlags)
        assert flags.enable_parallel_agents is False
        assert flags.enable_checkpoints is False
        assert flags.enable_distributed is False
        assert flags.enable_telemetry is True
        assert flags.max_concurrent_agents == 4
        assert flags.checkpoint_interval_seconds == 30

    def test_custom_env_vars(self):
        env = {
            "ORCH_ENABLE_PARALLEL_AGENTS": "true",
            "ORCH_ENABLE_CHECKPOINTS": "true",
            "ORCH_ENABLE_DISTRIBUTED": "true",
            "ORCH_ENABLE_TELEMETRY": "false",
            "ORCH_MAX_CONCURRENT_AGENTS": "8",
            "ORCH_CHECKPOINT_INTERVAL": "60",
        }
        with patch.dict(os.environ, env, clear=True):
            flags = create_orchestration_flags_from_env()

        assert flags.enable_parallel_agents is True
        assert flags.enable_checkpoints is True
        assert flags.enable_distributed is True
        assert flags.enable_telemetry is False
        assert flags.max_concurrent_agents == 8
        assert flags.checkpoint_interval_seconds == 60

    def test_partial_env_vars(self):
        env = {
            "ORCH_ENABLE_PARALLEL_AGENTS": "true",
            "ORCH_MAX_CONCURRENT_AGENTS": "16",
        }
        with patch.dict(os.environ, env, clear=True):
            flags = create_orchestration_flags_from_env()

        assert flags.enable_parallel_agents is True
        assert flags.max_concurrent_agents == 16
        # Other fields use defaults
        assert flags.enable_checkpoints is False
        assert flags.checkpoint_interval_seconds == 30

    def test_invalid_integer_raises(self):
        env = {"ORCH_MAX_CONCURRENT_AGENTS": "not_a_number"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError):
                create_orchestration_flags_from_env()

    def test_returns_orchestration_flags_type(self):
        with patch.dict(os.environ, {}, clear=True):
            flags = create_orchestration_flags_from_env()
        assert isinstance(flags, OrchestrationFlags)


# =============================================================================
# Request PID Context
# =============================================================================


class TestRequestPidContext:
    def setup_method(self):
        """Ensure clean state before each test."""
        clear_request_pid()

    def test_set_and_get(self):
        set_request_pid("pid-123")
        assert get_request_pid() == "pid-123"

    def test_clear(self):
        set_request_pid("pid-456")
        clear_request_pid()
        assert get_request_pid() is None

    def test_default_is_none(self):
        assert get_request_pid() is None

    def test_overwrite(self):
        set_request_pid("pid-1")
        set_request_pid("pid-2")
        assert get_request_pid() == "pid-2"

    def test_context_manager_sets_and_restores(self):
        assert get_request_pid() is None

        with request_pid_context("pid-789") as pid:
            assert pid == "pid-789"
            assert get_request_pid() == "pid-789"

        # After exiting context, should be reset
        assert get_request_pid() is None

    def test_nested_context_managers(self):
        with request_pid_context("outer"):
            assert get_request_pid() == "outer"

            with request_pid_context("inner"):
                assert get_request_pid() == "inner"

            # After inner context exits, outer is restored
            assert get_request_pid() == "outer"

        assert get_request_pid() is None

    def test_context_manager_returns_pid(self):
        with request_pid_context("test-pid") as pid:
            assert pid == "test-pid"


# =============================================================================
# create_app_context (composition root)
# =============================================================================


class TestCreateAppContext:
    """Test the composition root via its public injection interface.

    Instead of deeply patching all local imports inside create_app_context
    (which is fragile), we test the injection override paths where
    pre-configured objects are passed in, and test the env-var-driven
    config builders separately above.
    """

    def test_accepts_injected_core_config(self):
        """Verify that passing core_config skips env parsing."""
        custom_config = ExecutionConfig(max_iterations=42, max_llm_calls=99)

        # We still need to mock the heavy deps inside create_app_context.
        # Use a single large mock context that patches the whole function body.
        mock_logger = MagicMock()
        mock_logger.bind = MagicMock(return_value=mock_logger)
        mock_logger.info = MagicMock()

        mock_settings = MagicMock()
        mock_settings.log_level = "INFO"
        mock_settings.jeeves_llm_adapter = "mock"

        mock_flags = MagicMock()
        mock_flags.enable_tracing = False
        mock_flags.use_redis_state = False
        mock_flags.enable_distributed_mode = False

        mock_registry = MagicMock()
        mock_registry.get_default_service.return_value = "test"

        with patch("jeeves_infra.bootstrap.get_settings", return_value=mock_settings), \
             patch("jeeves_infra.bootstrap.get_feature_flags", return_value=mock_flags), \
             patch("jeeves_infra.bootstrap.configure_logging"), \
             patch("jeeves_infra.logging.create_logger", return_value=mock_logger), \
             patch("jeeves_infra.bootstrap.get_capability_resource_registry", return_value=mock_registry), \
             patch("jeeves_infra.llm.factory.create_llm_provider_factory", return_value=MagicMock()), \
             patch("jeeves_infra.ipc.IpcTransport", return_value=MagicMock()), \
             patch("jeeves_infra.bootstrap.KernelClient", return_value=MagicMock()), \
             patch("jeeves_infra.config.registry.ConfigRegistry", return_value=MagicMock()), \
             patch("jeeves_infra.redis.connection_manager.InMemoryStateBackend", return_value=MagicMock()):

            ctx = create_app_context(core_config=custom_config)

        assert ctx.core_config is custom_config
        assert ctx.core_config.max_iterations == 42
        assert ctx.core_config.max_llm_calls == 99

    def test_accepts_injected_orchestration_flags(self):
        """Verify that passing orchestration_flags skips env parsing."""
        custom_flags = OrchestrationFlags(enable_parallel_agents=True, max_concurrent_agents=16)

        mock_logger = MagicMock()
        mock_logger.bind = MagicMock(return_value=mock_logger)
        mock_logger.info = MagicMock()

        mock_settings = MagicMock()
        mock_settings.log_level = "INFO"
        mock_settings.jeeves_llm_adapter = "mock"

        mock_ff = MagicMock()
        mock_ff.enable_tracing = False
        mock_ff.use_redis_state = False
        mock_ff.enable_distributed_mode = False

        mock_registry = MagicMock()
        mock_registry.get_default_service.return_value = "test"

        with patch("jeeves_infra.bootstrap.get_settings", return_value=mock_settings), \
             patch("jeeves_infra.bootstrap.get_feature_flags", return_value=mock_ff), \
             patch("jeeves_infra.bootstrap.configure_logging"), \
             patch("jeeves_infra.logging.create_logger", return_value=mock_logger), \
             patch("jeeves_infra.bootstrap.get_capability_resource_registry", return_value=mock_registry), \
             patch("jeeves_infra.llm.factory.create_llm_provider_factory", return_value=MagicMock()), \
             patch("jeeves_infra.ipc.IpcTransport", return_value=MagicMock()), \
             patch("jeeves_infra.bootstrap.KernelClient", return_value=MagicMock()), \
             patch("jeeves_infra.config.registry.ConfigRegistry", return_value=MagicMock()), \
             patch("jeeves_infra.redis.connection_manager.InMemoryStateBackend", return_value=MagicMock()):

            ctx = create_app_context(orchestration_flags=custom_flags)

        assert ctx.orchestration_flags is custom_flags
        assert ctx.orchestration_flags.enable_parallel_agents is True
        assert ctx.orchestration_flags.max_concurrent_agents == 16

    def test_configures_logging_with_settings(self):
        """Verify that configure_logging is called with settings-derived args."""
        mock_logger = MagicMock()
        mock_logger.bind = MagicMock(return_value=mock_logger)
        mock_logger.info = MagicMock()

        mock_settings = MagicMock()
        mock_settings.log_level = "DEBUG"
        mock_settings.jeeves_llm_adapter = "mock"

        mock_ff = MagicMock()
        mock_ff.enable_tracing = True
        mock_ff.use_redis_state = False
        mock_ff.enable_distributed_mode = False

        mock_registry = MagicMock()
        mock_registry.get_default_service.return_value = "test"

        with patch("jeeves_infra.bootstrap.get_settings", return_value=mock_settings), \
             patch("jeeves_infra.bootstrap.get_feature_flags", return_value=mock_ff), \
             patch("jeeves_infra.bootstrap.configure_logging") as mock_configure_logging, \
             patch("jeeves_infra.logging.create_logger", return_value=mock_logger), \
             patch("jeeves_infra.bootstrap.get_capability_resource_registry", return_value=mock_registry), \
             patch("jeeves_infra.llm.factory.create_llm_provider_factory", return_value=MagicMock()), \
             patch("jeeves_infra.ipc.IpcTransport", return_value=MagicMock()), \
             patch("jeeves_infra.bootstrap.KernelClient", return_value=MagicMock()), \
             patch("jeeves_infra.config.registry.ConfigRegistry", return_value=MagicMock()), \
             patch("jeeves_infra.redis.connection_manager.InMemoryStateBackend", return_value=MagicMock()), \
             patch("jeeves_infra.observability.otel_adapter.init_global_otel"), \
             patch("jeeves_infra.observability.otel_adapter.get_global_otel_adapter", return_value=MagicMock(enabled=True)):

            create_app_context()

        mock_configure_logging.assert_called_once_with(
            level="DEBUG",
            json_output=True,
            enable_otel=True,
        )

    def test_returns_app_context_with_all_fields(self):
        """Verify the returned AppContext has all expected fields populated."""
        from jeeves_infra.context import AppContext

        mock_logger = MagicMock()
        mock_logger.bind = MagicMock(return_value=mock_logger)
        mock_logger.info = MagicMock()

        mock_settings = MagicMock()
        mock_settings.log_level = "INFO"
        mock_settings.jeeves_llm_adapter = "mock"

        mock_ff = MagicMock()
        mock_ff.enable_tracing = False
        mock_ff.use_redis_state = False
        mock_ff.enable_distributed_mode = False

        mock_registry = MagicMock()
        mock_registry.get_default_service.return_value = "test"

        with patch("jeeves_infra.bootstrap.get_settings", return_value=mock_settings), \
             patch("jeeves_infra.bootstrap.get_feature_flags", return_value=mock_ff), \
             patch("jeeves_infra.bootstrap.configure_logging"), \
             patch("jeeves_infra.logging.create_logger", return_value=mock_logger), \
             patch("jeeves_infra.bootstrap.get_capability_resource_registry", return_value=mock_registry), \
             patch("jeeves_infra.llm.factory.create_llm_provider_factory", return_value=MagicMock()), \
             patch("jeeves_infra.ipc.IpcTransport", return_value=MagicMock()), \
             patch("jeeves_infra.bootstrap.KernelClient", return_value=MagicMock()), \
             patch("jeeves_infra.config.registry.ConfigRegistry", return_value=MagicMock()), \
             patch("jeeves_infra.redis.connection_manager.InMemoryStateBackend", return_value=MagicMock()):

            ctx = create_app_context()

        assert isinstance(ctx, AppContext)
        assert ctx.settings is mock_settings
        assert ctx.feature_flags is mock_ff
        assert ctx.kernel_client is not None
        assert ctx.core_config is not None
        assert ctx.orchestration_flags is not None
        assert ctx.state_backend is not None


# =============================================================================
# sync_quota_defaults_to_kernel
# =============================================================================


class TestSyncQuotaDefaultsToKernel:
    @pytest.mark.asyncio
    async def test_happy_path_syncs_config(self):
        mock_kernel_client = MagicMock()
        mock_kernel_client.set_quota_defaults = AsyncMock()

        mock_logger = MagicMock()
        mock_logger.info = MagicMock()

        core_config = ExecutionConfig(
            max_llm_calls=20,
            max_agent_hops=15,
            context_bounds=ContextBounds(
                max_input_tokens=8192,
                max_output_tokens=4096,
                max_context_tokens=32768,
            ),
        )

        mock_app_context = MagicMock()
        mock_app_context.core_config = core_config
        mock_app_context.kernel_client = mock_kernel_client
        mock_app_context.logger = mock_logger

        await sync_quota_defaults_to_kernel(mock_app_context)

        mock_kernel_client.set_quota_defaults.assert_called_once_with(
            max_llm_calls=20,
            max_iterations=8192,  # Note: code uses context_bounds.max_input_tokens
            max_input_tokens=8192,
            max_output_tokens=4096,
            max_context_tokens=32768,
            max_agent_hops=15,
        )
        mock_logger.info.assert_called_once_with("quota_defaults_synced_to_kernel")

    @pytest.mark.asyncio
    async def test_uses_default_config_values(self):
        mock_kernel_client = MagicMock()
        mock_kernel_client.set_quota_defaults = AsyncMock()

        mock_logger = MagicMock()
        mock_logger.info = MagicMock()

        # Default ExecutionConfig
        core_config = ExecutionConfig()

        mock_app_context = MagicMock()
        mock_app_context.core_config = core_config
        mock_app_context.kernel_client = mock_kernel_client
        mock_app_context.logger = mock_logger

        await sync_quota_defaults_to_kernel(mock_app_context)

        call_kwargs = mock_kernel_client.set_quota_defaults.call_args[1]
        assert call_kwargs["max_llm_calls"] == 10
        assert call_kwargs["max_agent_hops"] == 21
        assert call_kwargs["max_input_tokens"] == 4096
        assert call_kwargs["max_output_tokens"] == 2048
        assert call_kwargs["max_context_tokens"] == 16384

    @pytest.mark.asyncio
    async def test_failure_logs_warning_does_not_raise(self):
        mock_kernel_client = MagicMock()
        mock_kernel_client.set_quota_defaults = AsyncMock(
            side_effect=ConnectionError("kernel unavailable")
        )

        mock_logger = MagicMock()
        mock_logger.warning = MagicMock()

        core_config = ExecutionConfig()

        mock_app_context = MagicMock()
        mock_app_context.core_config = core_config
        mock_app_context.kernel_client = mock_kernel_client
        mock_app_context.logger = mock_logger

        # Should NOT raise
        await sync_quota_defaults_to_kernel(mock_app_context)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "quota_defaults_sync_failed"
        assert "kernel unavailable" in call_args[1]["error"]

    @pytest.mark.asyncio
    async def test_failure_includes_detail_message(self):
        mock_kernel_client = MagicMock()
        mock_kernel_client.set_quota_defaults = AsyncMock(
            side_effect=TimeoutError("connection timed out")
        )

        mock_logger = MagicMock()
        mock_logger.warning = MagicMock()

        mock_app_context = MagicMock()
        mock_app_context.core_config = ExecutionConfig()
        mock_app_context.kernel_client = mock_kernel_client
        mock_app_context.logger = mock_logger

        await sync_quota_defaults_to_kernel(mock_app_context)

        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs["detail"] == "Kernel will use its built-in defaults"


# =============================================================================
# create_tool_executor_with_access
# =============================================================================


class TestCreateToolExecutorWithAccess:
    def test_creates_tool_executor(self):
        from jeeves_infra.bootstrap import create_tool_executor_with_access

        mock_registry = MagicMock()
        mock_app_context = MagicMock()
        mock_app_context.get_bound_logger = MagicMock(return_value=MagicMock())
        mock_access_checker = MagicMock()

        mock_tool_executor = MagicMock()

        with patch("jeeves_infra.wiring.ToolExecutor", return_value=mock_tool_executor) as mock_cls:
            result = create_tool_executor_with_access(
                tool_registry=mock_registry,
                app_context=mock_app_context,
                access_checker=mock_access_checker,
            )

        assert result is mock_tool_executor
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["registry"] is mock_registry
        assert call_kwargs["access_checker"] is mock_access_checker

    def test_creates_tool_executor_without_access_checker(self):
        from jeeves_infra.bootstrap import create_tool_executor_with_access

        mock_registry = MagicMock()
        mock_app_context = MagicMock()
        mock_app_context.get_bound_logger = MagicMock(return_value=MagicMock())

        mock_tool_executor = MagicMock()

        with patch("jeeves_infra.wiring.ToolExecutor", return_value=mock_tool_executor) as mock_cls:
            result = create_tool_executor_with_access(
                tool_registry=mock_registry,
                app_context=mock_app_context,
            )

        assert result is mock_tool_executor
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["access_checker"] is None
