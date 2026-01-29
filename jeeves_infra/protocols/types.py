"""Python type wrappers for proto-generated messages.

These dataclasses provide backward compatibility with the original
jeeves_core.types module, adding convenience methods while the
proto messages serve as the source of truth.

Session 10: Types moved from jeeves-core/jeeves_core/types/
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from jeeves_infra.protocols.interfaces import RequestContext

# Import proto enums for compatibility
from jeeves_infra.protocols.engine_pb2 import (
    TerminalReason as ProtoTerminalReason,
    InterruptKind as ProtoInterruptKind,
    InterruptStatus as ProtoInterruptStatus,
    RiskLevel as ProtoRiskLevel,
    ToolCategory as ProtoToolCategory,
    ToolAccess as ProtoToolAccess,
    HealthStatus as ProtoHealthStatus,
    LoopVerdict as ProtoLoopVerdict,
    RiskApproval as ProtoRiskApproval,
    OperationStatus as ProtoOperationStatus,
    RunMode as ProtoRunMode,
    JoinStrategy as ProtoJoinStrategy,
    AgentOutputMode as ProtoAgentOutputMode,
    TokenStreamMode as ProtoTokenStreamMode,
    AgentCapability as ProtoAgentCapability,
    # Enum values
    CLARIFICATION, CONFIRMATION, CHECKPOINT, RESOURCE_EXHAUSTED,
    TIMEOUT, SYSTEM_ERROR, AGENT_REVIEW, INTERRUPT_KIND_UNSPECIFIED,
    INTERRUPT_PENDING, INTERRUPT_RESOLVED, INTERRUPT_EXPIRED, INTERRUPT_CANCELLED,
)


# =============================================================================
# PYTHON ENUMS (backward compatible with string values)
# =============================================================================

class TerminalReason(str, Enum):
    """Terminal reason enum - mirrors Go TerminalReason."""
    UNSPECIFIED = "unspecified"
    MAX_ITERATIONS_EXCEEDED = "max_iterations_exceeded"
    MAX_LLM_CALLS_EXCEEDED = "max_llm_calls_exceeded"
    MAX_AGENT_HOPS_EXCEEDED = "max_agent_hops_exceeded"
    USER_CANCELLED = "user_cancelled"
    TOOL_FAILED_FATALLY = "tool_failed_fatally"
    LLM_FAILED_FATALLY = "llm_failed_fatally"
    COMPLETED = "completed"
    POLICY_VIOLATION = "policy_violation"


class InterruptKind(str, Enum):
    """Interrupt kind enum - mirrors Go InterruptKind."""
    UNSPECIFIED = "unspecified"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"
    CHECKPOINT = "checkpoint"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    TIMEOUT = "timeout"
    SYSTEM_ERROR = "system_error"
    AGENT_REVIEW = "agent_review"


class InterruptStatus(str, Enum):
    """Interrupt status enum."""
    UNSPECIFIED = "unspecified"
    PENDING = "pending"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """Risk level for tool operations."""
    UNSPECIFIED = "unspecified"
    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolCategory(str, Enum):
    """Tool category classification."""
    UNSPECIFIED = "unspecified"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    SYSTEM = "system"
    UNIFIED = "unified"
    COMPOSITE = "composite"
    RESILIENT = "resilient"
    STANDALONE = "standalone"
    INTERNAL = "internal"


class HealthStatus(str, Enum):
    """Health status for service monitoring."""
    UNSPECIFIED = "unspecified"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class LoopVerdict(str, Enum):
    """Loop control verdict."""
    UNSPECIFIED = "unspecified"
    PROCEED = "proceed"
    BACK = "back"
    ADVANCE = "advance"
    ESCALATE = "escalate"


class RiskApproval(str, Enum):
    """Risk approval status."""
    UNSPECIFIED = "unspecified"
    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"


class ToolAccess(str, Enum):
    """Tool access level."""
    UNSPECIFIED = "unspecified"
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ALL = "all"


class OperationStatus(str, Enum):
    """Operation result status."""
    UNSPECIFIED = "unspecified"
    SUCCESS = "success"
    ERROR = "error"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    PARTIAL = "partial"
    INVALID_PARAMETERS = "invalid_parameters"


class RunMode(str, Enum):
    """Pipeline run mode."""
    UNSPECIFIED = "unspecified"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class JoinStrategy(str, Enum):
    """Join strategy for dependencies."""
    UNSPECIFIED = "unspecified"
    ALL = "all"
    ANY = "any"


class AgentOutputMode(str, Enum):
    """Agent output mode."""
    UNSPECIFIED = "unspecified"
    STRUCTURED = "structured"
    TEXT = "text"


class TokenStreamMode(str, Enum):
    """Token streaming mode."""
    UNSPECIFIED = "unspecified"
    OFF = "off"
    DEBUG = "debug"
    AUTHORITATIVE = "authoritative"


class AgentCapability(str, Enum):
    """Agent capability flags."""
    UNSPECIFIED = "unspecified"
    LLM = "llm"
    TOOLS = "tools"
    POLICIES = "policies"
    SERVICE = "service"


# =============================================================================
# OPERATION RESULT
# =============================================================================

@dataclass
class OperationResult:
    """Result of an operation."""
    status: OperationStatus = OperationStatus.SUCCESS
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)


# =============================================================================
# INTERRUPT TYPES
# =============================================================================

@dataclass
class InterruptResponse:
    """Response to an interrupt."""
    text: str = ""
    approved: bool = False
    decision: str = ""
    data: Optional[Dict[str, Any]] = None
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "approved": self.approved,
            "decision": self.decision,
            "data": self.data,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class FlowInterrupt:
    """Flow interrupt for user interaction."""
    id: str = ""
    kind: InterruptKind = InterruptKind.UNSPECIFIED
    request_id: str = ""
    user_id: str = ""
    session_id: str = ""
    envelope_id: str = ""
    question: str = ""
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    response: Optional[InterruptResponse] = None
    status: InterruptStatus = InterruptStatus.PENDING
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    trace_id: str = ""
    span_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value if isinstance(self.kind, Enum) else self.kind,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "envelope_id": self.envelope_id,
            "question": self.question,
            "message": self.message,
            "data": self.data,
            "response": self.response.to_dict() if self.response else None,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "FlowInterrupt":
        """Create FlowInterrupt from database row."""
        kind_value = row.get("kind", "unspecified")
        if isinstance(kind_value, str):
            try:
                kind = InterruptKind(kind_value)
            except ValueError:
                kind = InterruptKind.UNSPECIFIED
        else:
            kind = kind_value

        status_value = row.get("status", "pending")
        if isinstance(status_value, str):
            try:
                status = InterruptStatus(status_value)
            except ValueError:
                status = InterruptStatus.PENDING
        else:
            status = status_value

        response_data = row.get("response")
        response = None
        if response_data and isinstance(response_data, dict):
            response = InterruptResponse(**response_data)

        return cls(
            id=row.get("id", ""),
            kind=kind,
            request_id=row.get("request_id", ""),
            user_id=row.get("user_id", ""),
            session_id=row.get("session_id", ""),
            envelope_id=row.get("envelope_id", ""),
            question=row.get("question", ""),
            message=row.get("message", ""),
            data=row.get("data"),
            response=response,
            status=status,
            trace_id=row.get("trace_id", ""),
            span_id=row.get("span_id", ""),
        )


# =============================================================================
# RATE LIMITING
# =============================================================================

@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_size: int = 10


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool = True
    exceeded: bool = False
    reason: str = ""
    limit_type: str = ""
    current_count: int = 0
    limit: int = 0
    retry_after_seconds: float = 0.0
    remaining: int = 0


# =============================================================================
# PROCESSING RECORD
# =============================================================================

@dataclass
class ProcessingRecord:
    """Record of agent processing step."""
    agent: str
    stage_order: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    status: str = "running"
    error: Optional[str] = None
    llm_calls: int = 0


# =============================================================================
# PIPELINE EVENT
# =============================================================================

@dataclass
class PipelineEvent:
    """Event from pipeline execution."""
    type: str
    stage: str
    data: Dict[str, Any]
    debug: bool = False


# =============================================================================
# CONFIG TYPES
# =============================================================================

@dataclass
class RoutingRule:
    """Routing rule for conditional transitions."""
    condition: str
    value: Any
    target: str


@dataclass
class EdgeLimit:
    """Per-edge transition limit."""
    from_stage: str
    to_stage: str
    max_count: int


@dataclass
class GenerationParams:
    """Generation control parameters."""
    stop: Optional[List[str]] = None
    repeat_penalty: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    seed: Optional[int] = None

    def __post_init__(self):
        if self.top_p is not None and not (0 < self.top_p <= 1):
            raise ValueError(f"top_p must be in (0, 1], got {self.top_p}")
        if self.top_k is not None and self.top_k < 0:
            raise ValueError(f"top_k must be >= 0, got {self.top_k}")
        if self.repeat_penalty is not None and self.repeat_penalty < 1.0:
            raise ValueError(f"repeat_penalty must be >= 1.0, got {self.repeat_penalty}")

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in {
            "stop": self.stop,
            "repeat_penalty": self.repeat_penalty,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "seed": self.seed,
        }.items() if v is not None}


@dataclass
class AgentConfig:
    """Declarative agent configuration."""
    name: str
    stage_order: int = 0
    requires: List[str] = field(default_factory=list)
    after: List[str] = field(default_factory=list)
    join_strategy: JoinStrategy = JoinStrategy.ALL
    has_llm: bool = False
    has_tools: bool = False
    has_policies: bool = False
    tool_access: ToolAccess = ToolAccess.NONE
    allowed_tools: Optional[Set[str]] = None
    model_role: Optional[str] = None
    prompt_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    generation: Optional[GenerationParams] = None
    output_key: str = ""
    required_output_fields: List[str] = field(default_factory=list)
    output_mode: AgentOutputMode = AgentOutputMode.STRUCTURED
    token_stream: TokenStreamMode = TokenStreamMode.OFF
    streaming_prompt_key: Optional[str] = None
    routing_rules: List[RoutingRule] = field(default_factory=list)
    default_next: Optional[str] = None
    error_next: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: int = 0
    pre_process: Optional[Callable] = None
    post_process: Optional[Callable] = None
    mock_handler: Optional[Callable] = None


@dataclass
class PipelineConfig:
    """Pipeline configuration."""
    name: str
    agents: List[AgentConfig] = field(default_factory=list)
    default_run_mode: RunMode = RunMode.SEQUENTIAL
    max_iterations: int = 3
    max_llm_calls: int = 10
    max_agent_hops: int = 21
    default_timeout_seconds: int = 300
    edge_limits: List[EdgeLimit] = field(default_factory=list)
    clarification_resume_stage: Optional[str] = None
    confirmation_resume_stage: Optional[str] = None
    agent_review_resume_stage: Optional[str] = None

    def get_stage_order(self) -> List[str]:
        return [a.name for a in sorted(self.agents, key=lambda x: x.stage_order)]

    def get_edge_limit(self, from_stage: str, to_stage: str) -> int:
        for limit in self.edge_limits:
            if limit.from_stage == from_stage and limit.to_stage == to_stage:
                return limit.max_count
        return 0

    def get_ready_stages(self, completed: Dict[str, bool]) -> List[str]:
        ready = []
        for agent in self.agents:
            if completed.get(agent.name):
                continue
            requires_ok = all(completed.get(r) for r in agent.requires)
            after_ok = all(completed.get(a) for a in agent.after)
            if agent.join_strategy == JoinStrategy.ANY and agent.requires:
                requires_ok = any(completed.get(r) for r in agent.requires)
            if requires_ok and after_ok:
                ready.append(agent.name)
        return ready

    def get_clarification_resume_stage(self) -> str:
        return self.clarification_resume_stage or "intent"

    def get_confirmation_resume_stage(self) -> str:
        return self.confirmation_resume_stage or "execution"

    def get_agent_review_resume_stage(self) -> str:
        return self.agent_review_resume_stage or "planner"


@dataclass
class ContextBounds:
    """Context window bounds."""
    max_input_tokens: int = 4096
    max_output_tokens: int = 2048
    max_context_tokens: int = 16384
    reserved_tokens: int = 512


@dataclass
class ExecutionConfig:
    """Core runtime configuration."""
    max_iterations: int = 3
    max_llm_calls: int = 10
    max_agent_hops: int = 21
    context_bounds: ContextBounds = field(default_factory=ContextBounds)
    enable_telemetry: bool = True
    enable_checkpoints: bool = False
    debug_mode: bool = False


@dataclass
class OrchestrationFlags:
    """Runtime orchestration flags."""
    enable_parallel_agents: bool = False
    enable_checkpoints: bool = False
    enable_distributed: bool = False
    enable_telemetry: bool = True
    max_concurrent_agents: int = 4
    checkpoint_interval_seconds: int = 30


# =============================================================================
# ENVELOPE
# =============================================================================

@dataclass
class Envelope:
    """Envelope with dynamic output slots - mirrors Go Envelope."""
    request_context: RequestContext
    envelope_id: str = ""
    request_id: str = ""
    user_id: str = ""
    session_id: str = ""
    raw_input: str = ""
    received_at: Optional[datetime] = None
    outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    current_stage: str = "start"
    stage_order: List[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3
    llm_call_count: int = 0
    max_llm_calls: int = 10
    agent_hop_count: int = 0
    max_agent_hops: int = 21
    terminal_reason: Optional[TerminalReason] = None
    terminated: bool = False
    termination_reason: Optional[str] = None
    interrupt_pending: bool = False
    interrupt: Optional[FlowInterrupt] = None
    active_stages: Dict[str, bool] = field(default_factory=dict)
    completed_stage_set: Dict[str, bool] = field(default_factory=dict)
    failed_stages: Dict[str, str] = field(default_factory=dict)
    parallel_mode: bool = False
    completed_stages: List[Dict[str, Any]] = field(default_factory=list)
    current_stage_number: int = 1
    max_stages: int = 5
    all_goals: List[str] = field(default_factory=list)
    remaining_goals: List[str] = field(default_factory=list)
    goal_completion_status: Dict[str, str] = field(default_factory=dict)
    prior_plans: List[Dict[str, Any]] = field(default_factory=list)
    loop_feedback: List[str] = field(default_factory=list)
    processing_history: List[ProcessingRecord] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.request_context is None:
            raise ValueError("request_context is required for Envelope")
        ctx = self.request_context
        if not self.request_id:
            self.request_id = ctx.request_id
        if not self.user_id and ctx.user_id:
            self.user_id = ctx.user_id
        if not self.session_id and ctx.session_id:
            self.session_id = ctx.session_id

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Envelope":
        """Create envelope from dictionary."""
        ctx_data = data.get("request_context")
        if ctx_data is None:
            raise ValueError("request_context missing in envelope data")
        if isinstance(ctx_data, RequestContext):
            ctx = ctx_data
        elif isinstance(ctx_data, dict):
            ctx = RequestContext(**ctx_data)
        else:
            raise TypeError("request_context must be a dict or RequestContext")

        terminal_reason = data.get("terminal_reason")
        if terminal_reason and isinstance(terminal_reason, str):
            try:
                terminal_reason = TerminalReason(terminal_reason)
            except ValueError:
                terminal_reason = None

        interrupt_data = data.get("interrupt")
        interrupt = None
        if interrupt_data and isinstance(interrupt_data, dict):
            interrupt = FlowInterrupt.from_db_row(interrupt_data)

        return cls(
            request_context=ctx,
            envelope_id=data.get("envelope_id", ""),
            request_id=data.get("request_id", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            raw_input=data.get("raw_input", ""),
            outputs=data.get("outputs", {}),
            current_stage=data.get("current_stage", "start"),
            stage_order=data.get("stage_order", []),
            iteration=data.get("iteration", 0),
            max_iterations=data.get("max_iterations", 3),
            llm_call_count=data.get("llm_call_count", 0),
            max_llm_calls=data.get("max_llm_calls", 10),
            agent_hop_count=data.get("agent_hop_count", 0),
            max_agent_hops=data.get("max_agent_hops", 21),
            terminal_reason=terminal_reason,
            terminated=data.get("terminated", False),
            termination_reason=data.get("termination_reason"),
            interrupt_pending=data.get("interrupt_pending", False),
            interrupt=interrupt,
            active_stages=data.get("active_stages", {}),
            completed_stage_set=data.get("completed_stage_set", {}),
            failed_stages=data.get("failed_stages", {}),
            parallel_mode=data.get("parallel_mode", False),
            current_stage_number=data.get("current_stage_number", 1),
            max_stages=data.get("max_stages", 5),
            all_goals=data.get("all_goals", []),
            remaining_goals=data.get("remaining_goals", []),
            goal_completion_status=data.get("goal_completion_status", {}),
            metadata=data.get("metadata", {}),
        )

    def initialize_goals(self, goals: List[str]) -> None:
        self.all_goals = list(goals)
        self.remaining_goals = list(goals)
        self.goal_completion_status = {goal: "pending" for goal in goals}

    def mark_goal_complete(self, goal: str) -> None:
        if goal in self.goal_completion_status:
            self.goal_completion_status[goal] = "complete"
        if goal in self.remaining_goals:
            self.remaining_goals.remove(goal)

    def advance_stage(self) -> None:
        self.current_stage_number += 1

    def get_stage_context(self) -> Dict[str, Any]:
        return {
            "current_stage_number": self.current_stage_number,
            "max_stages": self.max_stages,
            "all_goals": self.all_goals,
            "remaining_goals": self.remaining_goals,
            "goal_completion_status": self.goal_completion_status,
            "completed_stages": self.completed_stages,
        }

    def is_stuck(self, min_progress_stages: int = 2) -> bool:
        if self.current_stage_number < min_progress_stages:
            return False
        completed_count = sum(
            1 for status in self.goal_completion_status.values()
            if status == "complete"
        )
        return completed_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_context": self.request_context.to_dict(),
            "envelope_id": self.envelope_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "raw_input": self.raw_input,
            "outputs": self.outputs,
            "current_stage": self.current_stage,
            "stage_order": self.stage_order,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "llm_call_count": self.llm_call_count,
            "max_llm_calls": self.max_llm_calls,
            "agent_hop_count": self.agent_hop_count,
            "max_agent_hops": self.max_agent_hops,
            "terminal_reason": self.terminal_reason.value if self.terminal_reason else None,
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
            "interrupt_pending": self.interrupt_pending,
            "interrupt": self.interrupt.to_dict() if self.interrupt else None,
            "active_stages": self.active_stages,
            "completed_stage_set": self.completed_stage_set,
            "failed_stages": self.failed_stages,
            "parallel_mode": self.parallel_mode,
            "current_stage_number": self.current_stage_number,
            "max_stages": self.max_stages,
            "all_goals": self.all_goals,
            "remaining_goals": self.remaining_goals,
            "goal_completion_status": self.goal_completion_status,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    def to_state_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ALL fields for complete state serialization."""
        serialized_history = []
        for record in self.processing_history:
            serialized_history.append({
                "agent": record.agent,
                "stage_order": record.stage_order,
                "started_at": record.started_at.isoformat() if record.started_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                "duration_ms": record.duration_ms,
                "status": record.status,
                "error": record.error,
                "llm_calls": record.llm_calls,
            })

        return {
            "request_context": self.request_context.to_dict(),
            "envelope_id": self.envelope_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "raw_input": self.raw_input,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "outputs": self.outputs,
            "current_stage": self.current_stage,
            "stage_order": self.stage_order,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "llm_call_count": self.llm_call_count,
            "max_llm_calls": self.max_llm_calls,
            "agent_hop_count": self.agent_hop_count,
            "max_agent_hops": self.max_agent_hops,
            "terminal_reason": self.terminal_reason.value if self.terminal_reason else None,
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
            "interrupt_pending": self.interrupt_pending,
            "interrupt": self.interrupt.to_dict() if self.interrupt else None,
            "active_stages": self.active_stages,
            "completed_stage_set": self.completed_stage_set,
            "failed_stages": self.failed_stages,
            "parallel_mode": self.parallel_mode,
            "completed_stages": self.completed_stages,
            "current_stage_number": self.current_stage_number,
            "max_stages": self.max_stages,
            "all_goals": self.all_goals,
            "remaining_goals": self.remaining_goals,
            "goal_completion_status": self.goal_completion_status,
            "prior_plans": self.prior_plans,
            "loop_feedback": self.loop_feedback,
            "processing_history": serialized_history,
            "errors": self.errors,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }


# =============================================================================
# PROTOCOL FOR INTERRUPT SERVICE (from jeeves_core.types.interrupts)
# =============================================================================

from typing import Protocol, runtime_checkable


@runtime_checkable
class InterruptServiceProtocol(Protocol):
    """Interrupt service interface."""

    async def create_interrupt(
        self,
        kind: InterruptKind,
        envelope_id: str,
        question: str = "",
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> FlowInterrupt: ...

    async def resolve_interrupt(
        self,
        interrupt_id: str,
        response: InterruptResponse,
    ) -> FlowInterrupt: ...

    async def get_interrupt(self, interrupt_id: str) -> Optional[FlowInterrupt]: ...
    async def list_pending(self, envelope_id: str) -> List[FlowInterrupt]: ...


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Rate limiter interface."""

    def check(self, key: str) -> RateLimitResult: ...
    def record(self, key: str) -> None: ...
    def reset(self, key: str) -> None: ...


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "TerminalReason",
    "InterruptKind",
    "InterruptStatus",
    "RiskLevel",
    "ToolCategory",
    "HealthStatus",
    "LoopVerdict",
    "RiskApproval",
    "ToolAccess",
    "OperationStatus",
    "RunMode",
    "JoinStrategy",
    "AgentOutputMode",
    "TokenStreamMode",
    "AgentCapability",
    # Operation result
    "OperationResult",
    # Interrupt types
    "InterruptResponse",
    "FlowInterrupt",
    "InterruptServiceProtocol",
    # Rate limiting
    "RateLimitConfig",
    "RateLimitResult",
    "RateLimiterProtocol",
    # Processing
    "ProcessingRecord",
    "PipelineEvent",
    # Config types
    "RoutingRule",
    "EdgeLimit",
    "GenerationParams",
    "AgentConfig",
    "PipelineConfig",
    "ContextBounds",
    "ExecutionConfig",
    "OrchestrationFlags",
    # Envelope
    "Envelope",
]
