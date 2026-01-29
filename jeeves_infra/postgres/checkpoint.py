"""PostgreSQL checkpoint adapter for time-travel debugging.

Constitutional Amendment XXIII: Time-Travel Debugging Support.
Implements CheckpointProtocol using PostgreSQL JSONB storage.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jeeves_infra.protocols import (
    CheckpointProtocol,
    CheckpointRecord,
)
from jeeves_infra.protocols import LoggerProtocol
from jeeves_infra.logging import get_current_logger


class PostgresCheckpointAdapter:
    """PostgreSQL implementation of CheckpointProtocol.

    Stores execution checkpoints in a PostgreSQL table with JSONB state.
    Supports efficient querying by envelope_id and checkpoint ordering.

    Usage:
        adapter = PostgresCheckpointAdapter(postgres_client)
        await adapter.initialize_schema()

        # Save checkpoint after agent completion
        record = await adapter.save_checkpoint(
            envelope_id="env_123",
            checkpoint_id="ckpt_abc",
            agent_name="planner",
            state=envelope.to_state_dict(),
        )

        # Load checkpoint for replay
        state = await adapter.load_checkpoint("ckpt_abc")
        envelope = Envelope.from_dict(state)
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS execution_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        envelope_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        stage_order INTEGER NOT NULL,
        state_json JSONB NOT NULL,
        metadata_json JSONB,
        parent_checkpoint_id TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),

        CONSTRAINT fk_parent_checkpoint
            FOREIGN KEY (parent_checkpoint_id)
            REFERENCES execution_checkpoints(checkpoint_id)
            ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_checkpoints_envelope
        ON execution_checkpoints(envelope_id, stage_order);
    CREATE INDEX IF NOT EXISTS idx_checkpoints_created
        ON execution_checkpoints(created_at);
    """

    def __init__(
        self,
        postgres_client: Any,
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize checkpoint adapter.

        Args:
            postgres_client: PostgreSQLClient instance
            logger: Logger for DI (uses context logger if not provided)
        """
        self._db = postgres_client
        self._logger = logger or get_current_logger()
        self._stage_counter: Dict[str, int] = {}

    async def initialize_schema(self) -> None:
        """Create checkpoint table if not exists."""
        await self._db.execute_script(self.SCHEMA_SQL)
        self._logger.info("checkpoint_schema_initialized")

    async def save_checkpoint(
        self,
        envelope_id: str,
        checkpoint_id: str,
        agent_name: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord:
        """Save execution checkpoint after agent completion.

        Args:
            envelope_id: Request envelope identifier
            checkpoint_id: Unique checkpoint identifier
            agent_name: Agent that just completed
            state: Full serialized state (envelope.to_state_dict())
            metadata: Optional debug metadata (duration, memory, etc.)

        Returns:
            CheckpointRecord with storage confirmation
        """
        # Track stage order per envelope
        stage_order = self._stage_counter.get(envelope_id, 0)
        self._stage_counter[envelope_id] = stage_order + 1

        # Find parent checkpoint (previous in this envelope)
        parent_id = None
        if stage_order > 0:
            result = await self._db.fetch_one(
                """
                SELECT checkpoint_id FROM execution_checkpoints
                WHERE envelope_id = :envelope_id
                ORDER BY stage_order DESC LIMIT 1
                """,
                {"envelope_id": envelope_id},
            )
            if result:
                parent_id = result["checkpoint_id"]

        created_at = datetime.now(timezone.utc)

        await self._db.insert(
            "execution_checkpoints",
            {
                "checkpoint_id": checkpoint_id,
                "envelope_id": envelope_id,
                "agent_name": agent_name,
                "stage_order": stage_order,
                "state_json": state,
                "metadata_json": metadata,
                "parent_checkpoint_id": parent_id,
                "created_at": created_at,
            },
        )

        self._logger.debug(
            "checkpoint_saved",
            checkpoint_id=checkpoint_id,
            envelope_id=envelope_id,
            agent_name=agent_name,
            stage_order=stage_order,
        )

        return CheckpointRecord(
            checkpoint_id=checkpoint_id,
            envelope_id=envelope_id,
            agent_name=agent_name,
            stage_order=stage_order,
            created_at=created_at,
            parent_checkpoint_id=parent_id,
            metadata=metadata,
        )

    async def load_checkpoint(
        self,
        checkpoint_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load checkpoint state for restoration.

        Args:
            checkpoint_id: Checkpoint to load

        Returns:
            Serialized state dict, or None if not found
        """
        result = await self._db.fetch_one(
            """
            SELECT state_json FROM execution_checkpoints
            WHERE checkpoint_id = :checkpoint_id
            """,
            {"checkpoint_id": checkpoint_id},
        )

        if result:
            self._logger.debug("checkpoint_loaded", checkpoint_id=checkpoint_id)
            return result["state_json"]

        self._logger.warning("checkpoint_not_found", checkpoint_id=checkpoint_id)
        return None

    async def list_checkpoints(
        self,
        envelope_id: str,
        limit: int = 100,
    ) -> List[CheckpointRecord]:
        """List all checkpoints for an envelope (execution timeline).

        Args:
            envelope_id: Request envelope to query
            limit: Maximum checkpoints to return

        Returns:
            Ordered list of checkpoints (oldest first)
        """
        results = await self._db.fetch_all(
            """
            SELECT checkpoint_id, envelope_id, agent_name, stage_order,
                   created_at, parent_checkpoint_id, metadata_json
            FROM execution_checkpoints
            WHERE envelope_id = :envelope_id
            ORDER BY stage_order ASC
            LIMIT :limit
            """,
            {"envelope_id": envelope_id, "limit": limit},
        )

        return [
            CheckpointRecord(
                checkpoint_id=r["checkpoint_id"],
                envelope_id=r["envelope_id"],
                agent_name=r["agent_name"],
                stage_order=r["stage_order"],
                created_at=r["created_at"],
                parent_checkpoint_id=r["parent_checkpoint_id"],
                metadata=r["metadata_json"],
            )
            for r in results
        ]

    async def delete_checkpoints(
        self,
        envelope_id: str,
        before_checkpoint_id: Optional[str] = None,
    ) -> int:
        """Delete checkpoints for cleanup.

        Args:
            envelope_id: Request envelope
            before_checkpoint_id: Delete only checkpoints before this one

        Returns:
            Number of checkpoints deleted
        """
        if before_checkpoint_id:
            # Get stage order of the boundary checkpoint
            boundary = await self._db.fetch_one(
                """
                SELECT stage_order FROM execution_checkpoints
                WHERE checkpoint_id = :checkpoint_id
                """,
                {"checkpoint_id": before_checkpoint_id},
            )
            if not boundary:
                return 0

            result = await self._db.execute(
                """
                DELETE FROM execution_checkpoints
                WHERE envelope_id = :envelope_id
                  AND stage_order < :boundary_stage
                """,
                {
                    "envelope_id": envelope_id,
                    "boundary_stage": boundary["stage_order"],
                },
            )
        else:
            result = await self._db.execute(
                """
                DELETE FROM execution_checkpoints
                WHERE envelope_id = :envelope_id
                """,
                {"envelope_id": envelope_id},
            )

        # Clear stage counter for this envelope
        self._stage_counter.pop(envelope_id, None)

        deleted = result.rowcount if hasattr(result, "rowcount") else 0
        self._logger.info(
            "checkpoints_deleted",
            envelope_id=envelope_id,
            count=deleted,
        )
        return deleted

    async def fork_from_checkpoint(
        self,
        checkpoint_id: str,
        new_envelope_id: str,
    ) -> str:
        """Create new execution branch from checkpoint (time-travel replay).

        Args:
            checkpoint_id: Source checkpoint
            new_envelope_id: New envelope ID for forked execution

        Returns:
            New checkpoint_id for forked branch root
        """
        # Load source checkpoint
        source = await self._db.fetch_one(
            """
            SELECT * FROM execution_checkpoints
            WHERE checkpoint_id = :checkpoint_id
            """,
            {"checkpoint_id": checkpoint_id},
        )

        if not source:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        # Create forked checkpoint with new envelope_id
        new_checkpoint_id = f"ckpt_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc)

        # Update state with new envelope_id
        forked_state = dict(source["state_json"])
        forked_state["envelope_id"] = new_envelope_id

        await self._db.insert(
            "execution_checkpoints",
            {
                "checkpoint_id": new_checkpoint_id,
                "envelope_id": new_envelope_id,
                "agent_name": source["agent_name"],
                "stage_order": 0,  # Start of new branch
                "state_json": forked_state,
                "metadata_json": {
                    "forked_from": checkpoint_id,
                    "original_envelope_id": source["envelope_id"],
                },
                "parent_checkpoint_id": checkpoint_id,
                "created_at": created_at,
            },
        )

        # Initialize stage counter for new envelope
        self._stage_counter[new_envelope_id] = 1

        self._logger.info(
            "checkpoint_forked",
            source_checkpoint=checkpoint_id,
            new_checkpoint=new_checkpoint_id,
            new_envelope_id=new_envelope_id,
        )

        return new_checkpoint_id
