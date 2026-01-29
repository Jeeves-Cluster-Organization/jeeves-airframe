"""Tests for jeeves_infra.config module."""

import os
import pytest
from unittest.mock import patch

from jeeves_infra.config import KernelConfig, ResourceConfig


class TestKernelConfig:
    """Tests for KernelConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = KernelConfig()
        assert config.address == "localhost:50051"
        assert config.auto_connect is True
        assert config.connect_timeout_ms == 5000
        assert config.retry_attempts == 3
        assert config.default_user_id is None
        assert config.default_session_id is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = KernelConfig(
            address="192.168.1.100:9999",
            auto_connect=False,
            connect_timeout_ms=10000,
            retry_attempts=5,
            default_user_id="user-123",
            default_session_id="session-456",
        )
        assert config.address == "192.168.1.100:9999"
        assert config.auto_connect is False
        assert config.connect_timeout_ms == 10000
        assert config.retry_attempts == 5
        assert config.default_user_id == "user-123"
        assert config.default_session_id == "session-456"

    def test_immutability(self):
        """Test that config is frozen (immutable)."""
        config = KernelConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.address = "new-address"

    def test_from_env_defaults(self):
        """Test from_env with no environment variables set."""
        with patch.dict(os.environ, {}, clear=True):
            config = KernelConfig.from_env()
            assert config.address == "localhost:50051"
            assert config.auto_connect is True

    def test_from_env_custom(self):
        """Test from_env with environment variables."""
        env = {
            "KERNEL_GRPC_ADDRESS": "custom-host:12345",
            "KERNEL_AUTO_CONNECT": "false",
            "KERNEL_CONNECT_TIMEOUT_MS": "8000",
            "KERNEL_RETRY_ATTEMPTS": "7",
            "KERNEL_DEFAULT_USER_ID": "env-user",
            "KERNEL_DEFAULT_SESSION_ID": "env-session",
        }
        with patch.dict(os.environ, env, clear=True):
            config = KernelConfig.from_env()
            assert config.address == "custom-host:12345"
            assert config.auto_connect is False
            assert config.connect_timeout_ms == 8000
            assert config.retry_attempts == 7
            assert config.default_user_id == "env-user"
            assert config.default_session_id == "env-session"


class TestResourceConfig:
    """Tests for ResourceConfig dataclass."""

    def test_default_values(self):
        """Test default resource limits."""
        config = ResourceConfig.default()
        assert config.max_llm_calls == 100
        assert config.max_tool_calls == 200
        assert config.max_agent_hops == 21
        assert config.max_iterations == 50
        assert config.timeout_seconds == 300

    def test_custom_values(self):
        """Test custom resource limits."""
        config = ResourceConfig(
            max_llm_calls=50,
            max_tool_calls=100,
            max_agent_hops=10,
            max_iterations=25,
            timeout_seconds=600,
        )
        assert config.max_llm_calls == 50
        assert config.max_tool_calls == 100
        assert config.max_agent_hops == 10
        assert config.max_iterations == 25
        assert config.timeout_seconds == 600

    def test_immutability(self):
        """Test that config is frozen (immutable)."""
        config = ResourceConfig.default()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.max_llm_calls = 999

    def test_unlimited(self):
        """Test unlimited configuration."""
        config = ResourceConfig.unlimited()
        assert config.max_llm_calls == 999999
        assert config.max_tool_calls == 999999
        assert config.max_agent_hops == 999999
        assert config.max_iterations == 999999
        assert config.timeout_seconds == 86400

    def test_from_env_defaults(self):
        """Test from_env with no environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            config = ResourceConfig.from_env()
            assert config.max_llm_calls == 100
            assert config.max_tool_calls == 200

    def test_from_env_custom(self):
        """Test from_env with environment variables."""
        env = {
            "RESOURCE_MAX_LLM_CALLS": "25",
            "RESOURCE_MAX_TOOL_CALLS": "50",
            "RESOURCE_MAX_AGENT_HOPS": "5",
            "RESOURCE_MAX_ITERATIONS": "10",
            "RESOURCE_TIMEOUT_SECONDS": "120",
        }
        with patch.dict(os.environ, env, clear=True):
            config = ResourceConfig.from_env()
            assert config.max_llm_calls == 25
            assert config.max_tool_calls == 50
            assert config.max_agent_hops == 5
            assert config.max_iterations == 10
            assert config.timeout_seconds == 120

    def test_to_quota_dict(self):
        """Test conversion to quota dictionary."""
        config = ResourceConfig(
            max_llm_calls=10,
            max_tool_calls=20,
            max_agent_hops=3,
            max_iterations=5,
            timeout_seconds=60,
        )
        quota = config.to_quota_dict()
        assert quota == {
            "max_llm_calls": 10,
            "max_tool_calls": 20,
            "max_agent_hops": 3,
            "max_iterations": 5,
            "timeout_seconds": 60,
        }
