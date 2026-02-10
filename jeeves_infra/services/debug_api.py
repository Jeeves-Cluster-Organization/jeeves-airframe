"""Debug API service for time-travel debugging.

Constitutional Amendment XXIII: Time-Travel Debugging Support.
Provides inspection and replay capabilities for pipeline execution.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from jeeves_infra.protocols import (
    CheckpointProtocol,
    CheckpointRecord,
    Envelope,
    PipelineConfig,
    OptionalCheckpoint,
    LoggerProtocol,
)
from jeeves_infra.logging import get_current_logger


@dataclass
class ExecutionTimeline:
    """Timeline of execution checkpoints for a request."""

    envelope_id: str
    checkpoints: List[CheckpointRecord]
    current_stage: int
    is_terminal: bool
    terminal_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "envelope_id": self.envelope_id,
            "checkpoints": [
                {
                    "checkpoint_id": c.checkpoint_id,
                    "agent_name": c.agent_name,
                    "stage_order": c.stage_order,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "metadata": c.metadata,
                }
                for c in self.checkpoints
            ],
            "current_stage": self.current_stage,
            "is_terminal": self.is_terminal,
            "terminal_reason": self.terminal_reason,
        }


@dataclass
class InspectionResult:
    """Result of inspecting a checkpoint."""

    checkpoint_id: str
    envelope_state: Dict[str, Any]
    agent_name: str
    stage_order: int
    outputs: Dict[str, Any]
    processing_records: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "envelope_state": self.envelope_state,
            "agent_name": self.agent_name,
            "stage_order": self.stage_order,
            "outputs": self.outputs,
            "processing_records": self.processing_records,
        }


@dataclass
class ReplayResult:
    """Result of replaying from a checkpoint."""

    original_checkpoint_id: str
    forked_envelope_id: str
    new_checkpoint_id: str
    envelope: Optional[Envelope] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "original_checkpoint_id": self.original_checkpoint_id,
            "forked_envelope_id": self.forked_envelope_id,
            "new_checkpoint_id": self.new_checkpoint_id,
            "envelope_state": self.envelope.to_state_dict() if self.envelope else None,
        }


class DebugAPIService:
    """Service providing debug inspection and replay capabilities.

    Usage:
        debug = DebugService(checkpoint_adapter)

        # Get execution timeline
        timeline = await debug.get_timeline("env_123")

        # Inspect specific checkpoint
        result = await debug.inspect_checkpoint("ckpt_abc")

        # Replay from checkpoint
        replay = await debug.replay_from_checkpoint(
            "ckpt_abc",
            modifications={"user_message": "different input"},
        )
    """

    def __init__(
        self,
        checkpoint_adapter: CheckpointProtocol,
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize debug service.

        Args:
            checkpoint_adapter: CheckpointProtocol implementation
            logger: Logger for DI
        """
        self._checkpoints = checkpoint_adapter
        self._logger = logger or get_current_logger()

    async def get_timeline(
        self,
        envelope_id: str,
        limit: int = 100,
    ) -> ExecutionTimeline:
        """Get execution timeline for a request.

        Args:
            envelope_id: Request envelope to inspect
            limit: Maximum checkpoints to return

        Returns:
            ExecutionTimeline with checkpoint history
        """
        checkpoints = await self._checkpoints.list_checkpoints(
            envelope_id,
            limit=limit,
        )

        # Determine current state from latest checkpoint
        current_stage = 0
        is_terminal = False
        terminal_reason = None

        if checkpoints:
            latest = checkpoints[-1]
            current_stage = latest.stage_order

            # Check if execution completed
            if latest.metadata:
                is_terminal = latest.metadata.get("is_terminal", False)
                terminal_reason = latest.metadata.get("terminal_reason")

        self._logger.debug(
            "debug_timeline_fetched",
            envelope_id=envelope_id,
            checkpoint_count=len(checkpoints),
        )

        return ExecutionTimeline(
            envelope_id=envelope_id,
            checkpoints=checkpoints,
            current_stage=current_stage,
            is_terminal=is_terminal,
            terminal_reason=terminal_reason,
        )

    async def inspect_checkpoint(
        self,
        checkpoint_id: str,
    ) -> Optional[InspectionResult]:
        """Inspect a specific checkpoint's state.

        Args:
            checkpoint_id: Checkpoint to inspect

        Returns:
            InspectionResult with full state, or None if not found
        """
        state = await self._checkpoints.load_checkpoint(checkpoint_id)

        if not state:
            return None

        # Extract key information from state
        outputs = state.get("outputs", {})
        processing = state.get("processing_records", [])

        # Get checkpoint metadata
        checkpoints = await self._checkpoints.list_checkpoints(
            state.get("envelope_id", ""),
            limit=1000,
        )
        checkpoint = next(
            (c for c in checkpoints if c.checkpoint_id == checkpoint_id),
            None,
        )

        self._logger.debug(
            "debug_checkpoint_inspected",
            checkpoint_id=checkpoint_id,
        )

        return InspectionResult(
            checkpoint_id=checkpoint_id,
            envelope_state=state,
            agent_name=checkpoint.agent_name if checkpoint else "unknown",
            stage_order=checkpoint.stage_order if checkpoint else 0,
            outputs=outputs,
            processing_records=processing,
        )

    async def replay_from_checkpoint(
        self,
        checkpoint_id: str,
        new_envelope_id: Optional[str] = None,
        modifications: Optional[Dict[str, Any]] = None,
    ) -> ReplayResult:
        """Create replay branch from checkpoint.

        Args:
            checkpoint_id: Source checkpoint for replay
            new_envelope_id: New envelope ID (generated if not provided)
            modifications: State modifications for replay

        Returns:
            ReplayResult with forked envelope
        """
        import uuid

        # Generate new envelope ID if not provided
        if not new_envelope_id:
            new_envelope_id = f"replay_{uuid.uuid4().hex[:12]}"

        # Fork checkpoint
        new_checkpoint_id = await self._checkpoints.fork_from_checkpoint(
            checkpoint_id,
            new_envelope_id,
        )

        # Load forked state
        state = await self._checkpoints.load_checkpoint(new_checkpoint_id)

        # Apply modifications
        if modifications and state:
            state.update(modifications)
            # Re-save with modifications (in production, use update method)

        # Create envelope from state
        envelope = None
        if state:
            try:
                envelope = Envelope.from_dict(state)
            except Exception as e:
                self._logger.warning(
                    "debug_envelope_restore_failed",
                    checkpoint_id=checkpoint_id,
                    error=str(e),
                )

        self._logger.info(
            "debug_replay_created",
            original_checkpoint=checkpoint_id,
            new_envelope=new_envelope_id,
            new_checkpoint=new_checkpoint_id,
        )

        return ReplayResult(
            original_checkpoint_id=checkpoint_id,
            forked_envelope_id=new_envelope_id,
            new_checkpoint_id=new_checkpoint_id,
            envelope=envelope,
        )

    async def compare_executions(
        self,
        envelope_id_a: str,
        envelope_id_b: str,
    ) -> Dict[str, Any]:
        """Compare two execution timelines.

        Args:
            envelope_id_a: First execution
            envelope_id_b: Second execution

        Returns:
            Comparison result with differences
        """
        timeline_a = await self.get_timeline(envelope_id_a)
        timeline_b = await self.get_timeline(envelope_id_b)

        # Build comparison
        comparison = {
            "envelope_a": envelope_id_a,
            "envelope_b": envelope_id_b,
            "checkpoint_count_a": len(timeline_a.checkpoints),
            "checkpoint_count_b": len(timeline_b.checkpoints),
            "terminal_a": timeline_a.is_terminal,
            "terminal_b": timeline_b.is_terminal,
            "differences": [],
        }

        # Compare checkpoints at each stage
        max_stages = max(
            len(timeline_a.checkpoints),
            len(timeline_b.checkpoints),
        )

        for i in range(max_stages):
            ckpt_a = timeline_a.checkpoints[i] if i < len(timeline_a.checkpoints) else None
            ckpt_b = timeline_b.checkpoints[i] if i < len(timeline_b.checkpoints) else None

            if ckpt_a and ckpt_b:
                if ckpt_a.agent_name != ckpt_b.agent_name:
                    comparison["differences"].append({
                        "stage": i,
                        "type": "agent_name",
                        "value_a": ckpt_a.agent_name,
                        "value_b": ckpt_b.agent_name,
                    })
            elif ckpt_a and not ckpt_b:
                comparison["differences"].append({
                    "stage": i,
                    "type": "missing_in_b",
                    "agent": ckpt_a.agent_name,
                })
            elif ckpt_b and not ckpt_a:
                comparison["differences"].append({
                    "stage": i,
                    "type": "missing_in_a",
                    "agent": ckpt_b.agent_name,
                })

        self._logger.debug(
            "debug_comparison_completed",
            envelope_a=envelope_id_a,
            envelope_b=envelope_id_b,
            differences=len(comparison["differences"]),
        )

        return comparison

    async def cleanup_old_checkpoints(
        self,
        envelope_id: str,
        keep_last_n: int = 10,
    ) -> int:
        """Clean up old checkpoints for an envelope.

        Args:
            envelope_id: Envelope to clean up
            keep_last_n: Number of recent checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        checkpoints = await self._checkpoints.list_checkpoints(
            envelope_id,
            limit=1000,
        )

        if len(checkpoints) <= keep_last_n:
            return 0

        # Find boundary checkpoint to delete before
        boundary_idx = len(checkpoints) - keep_last_n
        boundary_checkpoint = checkpoints[boundary_idx].checkpoint_id

        deleted = await self._checkpoints.delete_checkpoints(
            envelope_id,
            before_checkpoint_id=boundary_checkpoint,
        )

        self._logger.info(
            "debug_checkpoints_cleaned",
            envelope_id=envelope_id,
            deleted=deleted,
            kept=keep_last_n,
        )

        return deleted
