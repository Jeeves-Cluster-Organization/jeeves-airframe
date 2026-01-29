"""Unit tests for bootstrap.py composition root.

Tests the application wiring and dependency injection.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock


class TestExecutionConfigFromEnv:
    """Tests for create_core_config_from_env function."""

    def test_default_values(self):
        """Test that ExecutionConfig has sensible defaults."""
        from mission_system.bootstrap import create_core_config_from_env

        with patch.dict("os.environ", {}, clear=True):
            config = create_core_config_from_env()

            assert config is not None
            assert config.context_bounds is not None
            # Check defaults are applied (on ExecutionConfig directly)
            assert config.max_iterations >= 1

    def test_respects_env_vars(self):
        """Test that environment variables are respected."""
        from mission_system.bootstrap import create_core_config_from_env

        env = {
            "CORE_MAX_ITERATIONS": "10",
            "CORE_MAX_LLM_CALLS": "50",
            "CORE_MAX_AGENT_HOPS": "20",
        }
        with patch.dict("os.environ", env, clear=True):
            config = create_core_config_from_env()

            # These are on ExecutionConfig directly, not context_bounds
            assert config.max_iterations == 10
            assert config.max_llm_calls == 50
            assert config.max_agent_hops == 20


class TestOrchestrationFlagsFromEnv:
    """Tests for create_orchestration_flags_from_env function."""

    def test_default_values(self):
        """Test that OrchestrationFlags has sensible defaults."""
        from mission_system.bootstrap import create_orchestration_flags_from_env

        with patch.dict("os.environ", {}, clear=True):
            flags = create_orchestration_flags_from_env()

            assert flags is not None

    def test_respects_env_vars(self):
        """Test that environment variables are respected."""
        from mission_system.bootstrap import create_orchestration_flags_from_env

        env = {
            "ORCH_ENABLE_PARALLEL_AGENTS": "true",
            "ORCH_ENABLE_DISTRIBUTED": "true",
        }
        with patch.dict("os.environ", env, clear=True):
            flags = create_orchestration_flags_from_env()

            # Check flags are set (actual attribute names from OrchestrationFlags)
            assert flags.enable_parallel_agents is True
            assert flags.enable_distributed is True


class TestAppContextCreation:
    """Tests for create_app_context function."""

    def test_creates_app_context(self):
        """Test that AppContext is created successfully."""
        from mission_system.bootstrap import create_app_context

        with patch.dict("os.environ", {}, clear=True):
            context = create_app_context()

            assert context is not None
            assert context.settings is not None
            assert context.feature_flags is not None
            assert context.logger is not None
            assert context.clock is not None
            assert context.control_tower is not None

    def test_respects_injected_dependencies(self):
        """Test that injected dependencies are used."""
        from mission_system.bootstrap import create_app_context
        from jeeves_infra.protocols import ExecutionConfig

        # max_iterations is on ExecutionConfig directly, not ContextBounds
        custom_config = ExecutionConfig(
            max_iterations=5,
            max_llm_calls=25,
            max_agent_hops=10,
        )

        with patch.dict("os.environ", {}, clear=True):
            context = create_app_context(core_config=custom_config)

            assert context.core_config == custom_config
            assert context.core_config.max_iterations == 5


class TestRequestPidContext:
    """Tests for per-request PID tracking."""

    def test_set_and_get_pid(self):
        """Test setting and getting request PID."""
        from mission_system.bootstrap import (
            set_request_pid,
            get_request_pid,
            clear_request_pid,
        )

        # Initially None
        clear_request_pid()
        assert get_request_pid() is None

        # Set PID
        set_request_pid("test-pid-123")
        assert get_request_pid() == "test-pid-123"

        # Clear PID
        clear_request_pid()
        assert get_request_pid() is None


class TestExecutionConfigToResourceQuota:
    """Tests for core_config_to_resource_quota conversion."""

    def test_converts_correctly(self):
        """Test conversion from ExecutionConfig to ResourceQuota."""
        from mission_system.bootstrap import core_config_to_resource_quota
        from jeeves_infra.protocols import ExecutionConfig

        # max_iterations etc are on ExecutionConfig directly
        config = ExecutionConfig(
            max_iterations=10,
            max_llm_calls=100,
            max_agent_hops=15,
        )

        quota = core_config_to_resource_quota(config)

        assert quota.max_iterations == 10
        assert quota.max_llm_calls == 100
        assert quota.max_agent_hops == 15


class TestCreateMemoryManager:
    """Tests for create_memory_manager async factory."""

    @pytest.mark.asyncio
    async def test_returns_none_without_postgres(self):
        """Test that None is returned when postgres_client is not provided."""
        from mission_system.bootstrap import create_app_context, create_memory_manager

        with patch.dict("os.environ", {}, clear=True):
            context = create_app_context()
            manager = await create_memory_manager(context, postgres_client=None)

            assert manager is None

    @pytest.mark.asyncio
    async def test_creates_manager_with_dependencies(self):
        """Test that MemoryManager is created when dependencies are provided."""
        from mission_system.bootstrap import create_app_context, create_memory_manager

        mock_postgres = Mock()
        mock_postgres.execute = AsyncMock()
        mock_postgres.fetch_one = AsyncMock()
        mock_postgres.fetch_all = AsyncMock()

        mock_vector = Mock()
        mock_vector.upsert = AsyncMock()
        mock_vector.search = AsyncMock()
        mock_vector.close = Mock()

        with patch.dict("os.environ", {}, clear=True):
            context = create_app_context()
            manager = await create_memory_manager(
                context,
                postgres_client=mock_postgres,
                vector_adapter=mock_vector,
            )

            assert manager is not None
            assert manager.sql is not None
            assert manager.vector is not None


class TestAvionicsDependencies:
    """Tests for create_avionics_dependencies function."""

    def test_creates_llm_factory(self):
        """Test that LLM factory is created."""
        from mission_system.bootstrap import (
            create_app_context,
            create_avionics_dependencies,
        )

        with patch.dict("os.environ", {}, clear=True):
            context = create_app_context()
            deps = create_avionics_dependencies(context)

            assert "llm_factory" in deps
            assert deps["llm_factory"] is not None

    def test_injects_node_profiles(self):
        """Test that node profiles are injected."""
        from mission_system.bootstrap import (
            create_app_context,
            create_avionics_dependencies,
        )

        mock_profiles = Mock()

        with patch.dict("os.environ", {}, clear=True):
            context = create_app_context()
            deps = create_avionics_dependencies(context, node_profiles=mock_profiles)

            assert deps["node_profiles"] == mock_profiles

