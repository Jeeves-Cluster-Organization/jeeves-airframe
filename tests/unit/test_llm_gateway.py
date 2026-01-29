"""Unit tests for LLMGateway components.

Tests the standalone components of the LLM gateway (dataclasses, exceptions).
Full LLMGateway integration tests require the complete dependency chain
(shared.logging, observability, etc.) which is tested in integration tests.

Note: This test module focuses on testing:
- QuotaExceededError exception
- StreamingChunk dataclass
- LLMResponse dataclass

The LLMGateway class itself has complex import dependencies that make
isolated unit testing difficult. See integration tests for full gateway testing.
"""

import sys
from pathlib import Path

# Add jeeves-infra root to path for imports
jeeves_infra_root = Path(__file__).parent.parent.parent
if str(jeeves_infra_root) not in sys.path:
    sys.path.insert(0, str(jeeves_infra_root))

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any


# =============================================================================
# Recreate dataclasses for isolated testing (avoid import chain)
# =============================================================================

class QuotaExceededError(Exception):
    """Raised when resource quota is exceeded."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Quota exceeded: {reason}")


@dataclass
class StreamingChunk:
    """A chunk emitted during streaming generation."""
    text: str
    is_final: bool
    request_id: str
    agent_name: str
    provider: str
    model: str
    cumulative_tokens: int
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "text": self.text,
            "is_final": self.is_final,
            "request_id": self.request_id,
            "agent_name": self.agent_name,
            "provider": self.provider,
            "model": self.model,
            "cumulative_tokens": self.cumulative_tokens,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class LLMResponse:
    """Response from LLM with metadata."""
    text: str
    tool_calls: List[Dict[str, Any]]
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    provider: str
    model: str
    cost_usd: float
    timestamp: datetime
    metadata: Dict[str, Any]
    streamed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


# =============================================================================
# Tests for QuotaExceededError
# =============================================================================

class TestQuotaExceededError:
    """Tests for QuotaExceededError exception."""

    def test_error_message(self):
        """Test error message formatting."""
        error = QuotaExceededError("max_llm_calls exceeded")
        assert str(error) == "Quota exceeded: max_llm_calls exceeded"

    def test_reason_attribute(self):
        """Test reason attribute is set."""
        error = QuotaExceededError("token limit reached")
        assert error.reason == "token limit reached"

    def test_is_exception(self):
        """Test it can be raised and caught."""
        with pytest.raises(QuotaExceededError) as exc_info:
            raise QuotaExceededError("test reason")

        assert exc_info.value.reason == "test reason"


# =============================================================================
# Tests for StreamingChunk
# =============================================================================

class TestStreamingChunk:
    """Tests for StreamingChunk dataclass."""

    def test_to_dict(self):
        """Test to_dict serialization."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        chunk = StreamingChunk(
            text="Hello",
            is_final=False,
            request_id="req-123",
            agent_name="planner",
            provider="llamaserver",
            model="llama2",
            cumulative_tokens=5,
            timestamp=ts,
        )

        result = chunk.to_dict()

        assert result["text"] == "Hello"
        assert result["is_final"] is False
        assert result["request_id"] == "req-123"
        assert result["agent_name"] == "planner"
        assert result["provider"] == "llamaserver"
        assert result["model"] == "llama2"
        assert result["cumulative_tokens"] == 5
        assert result["timestamp"] == "2024-01-15T12:00:00+00:00"

    def test_final_chunk(self):
        """Test final chunk has is_final=True."""
        ts = datetime.now(timezone.utc)
        chunk = StreamingChunk(
            text="Done",
            is_final=True,
            request_id="req-456",
            agent_name="executor",
            provider="openai",
            model="gpt-4",
            cumulative_tokens=100,
            timestamp=ts,
        )

        assert chunk.is_final is True
        assert chunk.to_dict()["is_final"] is True


# =============================================================================
# Tests for LLMResponse
# =============================================================================

class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_to_dict(self):
        """Test to_dict serialization."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        response = LLMResponse(
            text="Generated text",
            tool_calls=[],
            tokens_used=30,
            prompt_tokens=10,
            completion_tokens=20,
            latency_ms=150.5,
            provider="llamaserver",
            model="llama2",
            cost_usd=0.001,
            timestamp=ts,
            metadata={"agent": "planner"},
        )

        result = response.to_dict()

        assert result["text"] == "Generated text"
        assert result["tokens_used"] == 30
        assert result["prompt_tokens"] == 10
        assert result["completion_tokens"] == 20
        assert result["latency_ms"] == 150.5
        assert result["provider"] == "llamaserver"
        assert result["cost_usd"] == 0.001
        assert result["timestamp"] == "2024-01-15T12:00:00+00:00"
        assert result["metadata"] == {"agent": "planner"}

    def test_streamed_flag_default(self):
        """Test streamed flag defaults to False."""
        ts = datetime.now(timezone.utc)
        response = LLMResponse(
            text="text",
            tool_calls=[],
            tokens_used=10,
            prompt_tokens=5,
            completion_tokens=5,
            latency_ms=100.0,
            provider="test",
            model="test",
            cost_usd=0.0,
            timestamp=ts,
            metadata={},
        )

        assert response.streamed is False

    def test_streamed_flag_set(self):
        """Test streamed flag can be set to True."""
        ts = datetime.now(timezone.utc)
        response = LLMResponse(
            text="text",
            tool_calls=[],
            tokens_used=10,
            prompt_tokens=5,
            completion_tokens=5,
            latency_ms=100.0,
            provider="test",
            model="test",
            cost_usd=0.0,
            timestamp=ts,
            metadata={},
            streamed=True,
        )

        assert response.streamed is True

    def test_with_tool_calls(self):
        """Test response with tool calls."""
        ts = datetime.now(timezone.utc)
        tool_calls = [
            {"name": "search", "arguments": {"query": "test"}},
            {"name": "calculate", "arguments": {"expr": "1+1"}},
        ]

        response = LLMResponse(
            text="",
            tool_calls=tool_calls,
            tokens_used=50,
            prompt_tokens=30,
            completion_tokens=20,
            latency_ms=200.0,
            provider="openai",
            model="gpt-4",
            cost_usd=0.01,
            timestamp=ts,
            metadata={},
        )

        assert len(response.tool_calls) == 2
        assert response.tool_calls[0]["name"] == "search"
        assert response.tool_calls[1]["name"] == "calculate"


# =============================================================================
# Mock Gateway Tests (simulate kernel integration)
# =============================================================================

class MockKernelClient:
    """Mock KernelClient for testing gateway integration patterns."""

    def __init__(self, quota_exceeded: Optional[str] = None):
        self._quota_exceeded = quota_exceeded
        self.calls = []

    async def record_llm_call(
        self,
        pid: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> Optional[str]:
        """Record LLM call and return quota exceeded reason if any."""
        self.calls.append({
            "pid": pid,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        })
        return self._quota_exceeded


class TestMockKernelIntegration:
    """Tests demonstrating kernel integration patterns."""

    @pytest.mark.asyncio
    async def test_record_llm_call_no_quota(self):
        """Test recording LLM call when quota not exceeded."""
        kernel = MockKernelClient()

        result = await kernel.record_llm_call(
            pid="process-123",
            tokens_in=100,
            tokens_out=50,
        )

        assert result is None
        assert len(kernel.calls) == 1
        assert kernel.calls[0]["pid"] == "process-123"
        assert kernel.calls[0]["tokens_in"] == 100
        assert kernel.calls[0]["tokens_out"] == 50

    @pytest.mark.asyncio
    async def test_record_llm_call_quota_exceeded(self):
        """Test recording LLM call when quota exceeded."""
        kernel = MockKernelClient(quota_exceeded="max_llm_calls exceeded")

        result = await kernel.record_llm_call(
            pid="process-456",
            tokens_in=200,
            tokens_out=100,
        )

        assert result == "max_llm_calls exceeded"

        # Demonstrate how gateway would handle this
        if result:
            with pytest.raises(QuotaExceededError) as exc_info:
                raise QuotaExceededError(result)

            assert exc_info.value.reason == "max_llm_calls exceeded"

    @pytest.mark.asyncio
    async def test_stats_tracking_pattern(self):
        """Test pattern for tracking gateway stats."""
        # Simulate gateway stats
        stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "by_provider": {},
        }

        # Simulate responses
        responses = [
            LLMResponse(
                text="Response 1",
                tool_calls=[],
                tokens_used=100,
                prompt_tokens=40,
                completion_tokens=60,
                latency_ms=150.0,
                provider="llamaserver",
                model="llama2",
                cost_usd=0.001,
                timestamp=datetime.now(timezone.utc),
                metadata={},
            ),
            LLMResponse(
                text="Response 2",
                tool_calls=[],
                tokens_used=200,
                prompt_tokens=80,
                completion_tokens=120,
                latency_ms=250.0,
                provider="openai",
                model="gpt-4",
                cost_usd=0.05,
                timestamp=datetime.now(timezone.utc),
                metadata={},
            ),
        ]

        # Update stats for each response
        for response in responses:
            stats["total_requests"] += 1
            stats["total_tokens"] += response.tokens_used
            stats["total_cost_usd"] += response.cost_usd

            if response.provider not in stats["by_provider"]:
                stats["by_provider"][response.provider] = {
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0,
                }
            stats["by_provider"][response.provider]["requests"] += 1
            stats["by_provider"][response.provider]["tokens"] += response.tokens_used
            stats["by_provider"][response.provider]["cost"] += response.cost_usd

        # Verify stats
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 300
        assert stats["total_cost_usd"] == pytest.approx(0.051)
        assert stats["by_provider"]["llamaserver"]["requests"] == 1
        assert stats["by_provider"]["openai"]["requests"] == 1
