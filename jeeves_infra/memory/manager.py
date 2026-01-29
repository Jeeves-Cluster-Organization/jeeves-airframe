"""
Unified memory management orchestration.

Core responsibilities:
- Route writes to appropriate storage
- Coordinate SQL + Vector updates
- Manage cross-references
- Orchestrate hybrid search

Code Analysis Agent v3.0:
- Supports message and fact types only
- Task and Journal types removed (Constitution v3.0)

Memory Module Audit (2025-12-09):
- Consolidated in jeeves_infra/memory/
- Uses MemoryItem from jeeves_core_engine.memory (removed duplicate)
"""

from typing import Dict, Any, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    # Type hints only - implementations injected at runtime
    from jeeves_infra.memory.sql_adapter import SQLAdapter
    from jeeves_infra.memory.services.xref_manager import CrossRefManager
import asyncio
from jeeves_infra.logging import get_component_logger
from jeeves_infra.protocols import LoggerProtocol, VectorStorageProtocol


class MemoryManager:
    """Unified memory management interface.

    Code Analysis Agent v3.0: Supports message and fact types only.
    """

    # Valid item types for Code Analysis Agent v3.0
    VALID_TYPES = {'message', 'fact'}

    def __init__(
        self,
        sql_adapter: "SQLAdapter",
        vector_adapter: VectorStorageProtocol,
        xref_manager: "CrossRefManager",
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize memory manager.

        Args:
            sql_adapter: SQL database adapter
            vector_adapter: Vector database adapter (pgvector)
            xref_manager: Cross-reference manager
            logger: Optional logger instance (ADR-001 DI)
        """
        self.sql = sql_adapter
        self.vector = vector_adapter
        self.xref = xref_manager
        self._logger = get_component_logger("memory_manager", logger)
        self._background_tasks: Set[asyncio.Task] = set()

    async def write_message(
        self,
        session_id: str,
        content: str,
        role: str = "user",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Write a message to memory.

        Args:
            session_id: Session identifier
            content: Message content
            role: Message role (user, assistant, system)
            metadata: Additional metadata

        Returns:
            Result dict with item_id and status
        """
        self._logger.info("write_message_started", session_id=session_id, role=role)

        metadata = metadata or {}

        data = {
            'session_id': session_id,
            'role': role,
            'content': content,
            'metadata': metadata
        }

        try:
            item_id = await self.sql.write_message(session_id, data)
            self._logger.info("message_written", item_id=item_id, session_id=session_id)

            # Write to vector DB in background (tracked)
            task = asyncio.create_task(
                self._write_to_vector(item_id, content, 'conversations', metadata, session_id)
            )
            self._track_task(task)

            return {
                'status': 'success',
                'item_id': item_id,
                'item_type': 'message'
            }

        except Exception as e:
            self._logger.error("write_message_failed", error=str(e), session_id=session_id)
            raise

    async def write_fact(
        self,
        user_id: str,
        key: str,
        value: str,
        domain: str = "preferences",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Write a fact to memory.

        Args:
            user_id: User identifier
            key: Fact key
            value: Fact value
            domain: Fact domain/category
            confidence: Confidence score (0.0-1.0)
            metadata: Additional metadata

        Returns:
            Result dict with item_id and status
        """
        self._logger.info("write_fact_started", user_id=user_id, domain=domain, key=key)

        data = {
            'domain': domain,
            'key': key,
            'value': value,
            'confidence': confidence,
            **(metadata or {})
        }

        try:
            item_id = await self.sql.write_fact(user_id, data)
            self._logger.info("fact_written", item_id=item_id, domain=domain, key=key)

            # Write to vector DB in background (tracked)
            task = asyncio.create_task(
                self._write_to_vector(item_id, value, 'facts', {'domain': domain, 'key': key}, user_id)
            )
            self._track_task(task)

            return {
                'status': 'success',
                'item_id': item_id,
                'item_type': 'fact'
            }

        except Exception as e:
            self._logger.error("write_fact_failed", error=str(e), domain=domain, key=key)
            raise

    def _track_task(self, task: asyncio.Task) -> None:
        """Track a background task and clean up when done."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _write_to_vector(
        self,
        item_id: str,
        content: str,
        collection: str,
        metadata: Dict[str, Any],
        context_id: str
    ) -> None:
        """
        Write to vector database (background task).

        Args:
            item_id: Item ID
            content: Content to embed
            collection: Collection name
            metadata: Metadata
            context_id: User ID or session ID for context
        """
        try:
            meta = {**metadata, 'context_id': context_id}

            await self.vector.upsert(
                item_id=item_id,
                content=content,
                collection=collection,
                metadata=meta
            )

            self._logger.info("vector_write_complete", item_id=item_id, collection=collection)

        except Exception as e:
            self._logger.error("vector_write_failed", error=str(e), item_id=item_id)
            raise  # Re-raise so background task is marked failed

    async def read(
        self,
        user_id: str,
        query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        mode: str = "hybrid",
        types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Read from memory with hybrid search.

        Modes:
        - semantic: Vector search only
        - sql: SQL queries only
        - hybrid: Both, merged by relevance

        Args:
            user_id: User identifier
            query: Search query (semantic if provided)
            filters: SQL filters
            mode: Search mode (semantic, sql, hybrid)
            types: Item types to search (message, fact)
            limit: Maximum results

        Returns:
            List of matching items with scores
        """
        self._logger.info(
            "read_started",
            user_id=user_id,
            mode=mode,
            has_query=bool(query),
            types=types
        )

        filters = filters or {}
        # Filter to valid types only
        requested_types = set(types or ['message', 'fact'])
        valid_types = list(requested_types & self.VALID_TYPES)

        if not valid_types:
            self._logger.warning("no_valid_types", requested=types)
            return []

        results = []

        try:
            if mode in ['hybrid', 'sql']:
                for item_type in valid_types:
                    sql_results = await self.sql.read_by_filter(
                        user_id=user_id,
                        item_type=item_type,
                        filters=filters,
                        limit=limit
                    )
                    for item in sql_results:
                        results.append({
                            **item,
                            'source': 'sql',
                            'score': 0.5
                        })

            if mode in ['hybrid', 'semantic'] and query:
                # Map types to collections
                collections = []
                for t in valid_types:
                    if t == 'fact':
                        collections.append('facts')
                    elif t == 'message':
                        collections.append('conversations')

                vector_results = await self.vector.search(
                    query=query,
                    collections=collections,
                    filters={'user_id': user_id},
                    limit=limit
                )

                for item in vector_results:
                    results.append({
                        **item,
                        'source': 'vector',
                        'score': item.get('score', 0.5)
                    })

            # Merge and sort results
            if mode == 'hybrid':
                merged = {}
                for item in results:
                    item_id = item.get('item_id') or item.get('fact_id') or item.get('message_id')
                    if item_id in merged:
                        # Combine scores: 40% SQL + 60% vector
                        if item['source'] == 'sql':
                            merged[item_id]['score'] = merged[item_id].get('score', 0) * 0.6 + item['score'] * 0.4
                        else:
                            merged[item_id]['score'] = merged[item_id].get('score', 0) * 0.4 + item['score'] * 0.6
                    else:
                        merged[item_id] = item

                results = list(merged.values())

            results.sort(key=lambda x: x.get('score', 0), reverse=True)
            results = results[:limit]

            self._logger.info("read_complete", user_id=user_id, results_count=len(results))
            return results

        except Exception as e:
            self._logger.error("read_failed", error=str(e), user_id=user_id)
            raise

    async def update(
        self,
        user_id: str,
        item_id: str,
        item_type: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update existing memory item.

        Args:
            user_id: User identifier
            item_id: Item ID
            item_type: Item type (message, fact)
            updates: Fields to update

        Returns:
            Result dict
        """
        if item_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid item type: {item_type}. Valid types: {self.VALID_TYPES}")

        try:
            await self.sql.update_item(item_id, item_type, updates)

            # If content changed, re-embed
            if 'content' in updates or 'value' in updates:
                new_content = updates.get('content') or updates.get('value')
                collection = 'facts' if item_type == 'fact' else 'conversations'

                task = asyncio.create_task(
                    self.vector.upsert(
                        item_id=item_id,
                        content=new_content,
                        collection=collection,
                        metadata={'user_id': user_id}
                    )
                )
                self._track_task(task)

            self._logger.info("update_complete", item_id=item_id, item_type=item_type)

            return {
                'status': 'success',
                'item_id': item_id,
                'item_type': item_type
            }

        except Exception as e:
            self._logger.error("update_failed", error=str(e), item_id=item_id)
            raise

    async def delete(
        self,
        user_id: str,
        item_id: str,
        item_type: str,
        soft: bool = True
    ) -> bool:
        """
        Delete memory item.

        Args:
            user_id: User identifier
            item_id: Item ID
            item_type: Item type (message, fact)
            soft: If True, soft delete; if False, hard delete

        Returns:
            True if successful
        """
        if item_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid item type: {item_type}. Valid types: {self.VALID_TYPES}")

        try:
            await self.sql.delete_item(item_id, item_type, soft=soft)

            if not soft:
                collection = 'facts' if item_type == 'fact' else 'conversations'
                await self.vector.delete(item_id, collection)
                await self.xref.delete_refs_for_item(item_id)

            self._logger.info("delete_complete", item_id=item_id, soft=soft)
            return True

        except Exception as e:
            self._logger.error("delete_failed", error=str(e), item_id=item_id)
            raise

    async def wait_for_background_tasks(self, timeout: Optional[float] = None) -> None:
        """Wait for all background tasks to complete.

        Args:
            timeout: Optional timeout in seconds
        """
        if self._background_tasks:
            await asyncio.wait(
                self._background_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED
            )

    async def close(self) -> None:
        """Clean up resources."""
        try:
            # Wait for pending background tasks
            await self.wait_for_background_tasks(timeout=5.0)
            self.vector.close()
            self._logger.info("memory_manager_closed")
        except Exception as e:
            self._logger.error("memory_manager_close_failed", error=str(e))
