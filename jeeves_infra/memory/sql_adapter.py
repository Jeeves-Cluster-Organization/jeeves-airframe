"""
SQL database adapter for memory operations.

Provides unified interface to all SQL tables for memory management.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import json
from shared import get_component_logger, convert_uuids_to_strings
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class SQLAdapter:
    """Handles SQL database operations for memory."""

    def __init__(self, db_client: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """
        Initialize SQL adapter.

        Args:
            db_client: Database client instance
            logger: Optional logger instance (ADR-001 DI)
        """
        self.db = db_client
        self._logger = get_component_logger("sql_adapter", logger)

    # ============================================================
    # WRITE OPERATIONS
    # ============================================================

    async def write_fact(self, user_id: str, data: Dict[str, Any]) -> str:
        """
        Write to knowledge_facts table.

        Args:
            user_id: User identifier
            data: Fact data (domain, key, value, confidence)

        Returns:
            Fact ID (UUID string)
        """
        fact_id = data.get('fact_id') or str(uuid4())
        domain = data.get('domain', 'preferences')
        key = data.get('key', '')
        value = data.get('value', '')
        confidence = data.get('confidence', 1.0)

        query = """
            INSERT INTO knowledge_facts (fact_id, user_id, domain, key, value, confidence, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, domain, key) DO UPDATE SET
                value = excluded.value,
                confidence = excluded.confidence,
                last_updated = excluded.last_updated
        """

        params = (
            fact_id,
            user_id,
            domain,
            key,
            value,
            confidence,
            datetime.now(timezone.utc)
        )

        try:
            await self.db.execute(query, params)
            self._logger.info("fact_written", fact_id=fact_id, domain=domain, key=key)
            return fact_id
        except Exception as e:
            self._logger.error("fact_write_failed", error=str(e), domain=domain, key=key)
            raise

    async def write_message(self, session_id: str, data: Dict[str, Any]) -> str:
        """
        Write to messages table.

        Args:
            session_id: Session identifier
            data: Message data (role, content, etc.)

        Returns:
            Message ID (as string)
        """
        # PostgreSQL messages table uses SERIAL for message_id (auto-generated)
        # Use RETURNING to get the generated ID
        query = """
            INSERT INTO messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            RETURNING message_id
        """

        params = (
            session_id,
            data.get('role', 'user'),
            data.get('content', ''),
            datetime.now(timezone.utc)
        )

        try:
            # Use commit=True for INSERT...RETURNING to persist the insert
            result = await self.db.fetch_one(query, params, commit=True)
            message_id = str(result['message_id']) if result else str(uuid4())
            self._logger.info("message_written", message_id=message_id, session_id=session_id)
            return message_id
        except Exception as e:
            self._logger.error("message_write_failed", error=str(e), session_id=session_id)
            raise

    # ============================================================
    # READ OPERATIONS
    # ============================================================

    async def read_by_id(
        self,
        item_id: str,
        item_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Read single item by ID.

        Args:
            item_id: Unique identifier
            item_type: Type (fact, message)

        Returns:
            Item data or None if not found
        """
        type_to_table = {
            'fact': 'knowledge_facts',
            'message': 'messages'
        }

        table = type_to_table.get(item_type)
        if not table:
            self._logger.error("invalid_item_type", item_type=item_type)
            raise ValueError(f"Invalid item type: {item_type}. Valid types: fact, message")

        # Determine ID column based on type
        id_column = {
            'knowledge_facts': 'fact_id',
            'messages': 'message_id'
        }.get(table)

        try:
            if table == 'messages':
                # messages.message_id is SERIAL (INTEGER), not UUID
                query = f"SELECT * FROM {table} WHERE {id_column} = ?"
                result = await self.db.fetch_one(query, (int(item_id),))
            else:
                # knowledge_facts.fact_id is UUID
                query = f"SELECT * FROM {table} WHERE {id_column} = ?"
                result = await self.db.fetch_one(query, (item_id,))

            if result:
                self._logger.debug("item_read", item_id=item_id, item_type=item_type)
                # Convert UUID objects to strings for consistency
                return convert_uuids_to_strings(dict(result))
            else:
                self._logger.debug("item_not_found", item_id=item_id, item_type=item_type)
                return None

        except Exception as e:
            self._logger.error("read_by_id_failed", error=str(e), item_id=item_id)
            raise

    async def read_by_filter(
        self,
        user_id: str,
        item_type: str,
        filters: Dict[str, Any],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query items with filters.

        Args:
            user_id: User identifier
            item_type: Type (fact, message)
            filters: Filter conditions
            limit: Maximum results

        Returns:
            List of matching items
        """
        type_to_table = {
            'fact': 'knowledge_facts',
            'message': 'messages'
        }

        table = type_to_table.get(item_type)
        if not table:
            self._logger.error("invalid_item_type", item_type=item_type)
            raise ValueError(f"Invalid item type: {item_type}. Valid types: fact, message")

        # Build WHERE clause
        # messages table doesn't have user_id column
        where_clauses = ["user_id = ?"] if table != 'messages' else []
        params = [user_id] if table != 'messages' else []

        for key, value in filters.items():
            if value is not None:
                where_clauses.append(f"{key} = ?")
                params.append(value)

        where_str = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Use appropriate timestamp column
        order_column = "last_updated" if table == 'knowledge_facts' else "created_at"

        query = f"""
            SELECT * FROM {table}
            WHERE {where_str}
            ORDER BY {order_column} DESC
            LIMIT ?
        """
        params.append(limit)

        try:
            results = await self.db.fetch_all(query, tuple(params))
            # Convert UUID objects to strings for consistency
            items = [convert_uuids_to_strings(dict(row)) for row in results]
            self._logger.debug(
                "items_read",
                user_id=user_id,
                item_type=item_type,
                count=len(items)
            )
            return items
        except Exception as e:
            self._logger.error("read_by_filter_failed", error=str(e), item_type=item_type)
            raise

    # ============================================================
    # UPDATE OPERATIONS
    # ============================================================

    async def update_item(
        self,
        item_id: str,
        item_type: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update item fields.

        Args:
            item_id: Unique identifier
            item_type: Type (fact, message)
            updates: Fields to update

        Returns:
            True if successful
        """
        type_to_table = {
            'fact': 'knowledge_facts',
            'message': 'messages'
        }

        table = type_to_table.get(item_type)
        if not table:
            raise ValueError(f"Invalid item type: {item_type}. Valid types: fact, message")

        # Build SET clause
        set_clauses = []
        params = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            params.append(value)

        # Add timestamp update
        if table == 'messages':
            set_clauses.append("edited_at = ?")
        else:
            set_clauses.append("last_updated = ?")
        params.append(datetime.now(timezone.utc))

        set_str = ", ".join(set_clauses)

        # Determine ID column
        id_column = {
            'knowledge_facts': 'fact_id',
            'messages': 'message_id'
        }.get(table)

        try:
            query = f"UPDATE {table} SET {set_str} WHERE {id_column} = ?"
            params.append(item_id)

            await self.db.execute(query, tuple(params))
            self._logger.info("item_updated", item_id=item_id, item_type=item_type)
            return True

        except Exception as e:
            self._logger.error("update_failed", error=str(e), item_id=item_id)
            raise

    # ============================================================
    # DELETE OPERATIONS
    # ============================================================

    async def delete_item(
        self,
        item_id: str,
        item_type: str,
        soft: bool = True
    ) -> bool:
        """
        Delete item (soft or hard).

        Args:
            item_id: Unique identifier
            item_type: Type (fact, message)
            soft: If True, mark as deleted; if False, remove from DB

        Returns:
            True if successful
        """
        type_to_table = {
            'fact': 'knowledge_facts',
            'message': 'messages'
        }

        table = type_to_table.get(item_type)
        if not table:
            raise ValueError(f"Invalid item type: {item_type}. Valid types: fact, message")

        id_column = {
            'knowledge_facts': 'fact_id',
            'messages': 'message_id'
        }.get(table)

        # Only messages table supports soft delete via deleted_at column
        soft_delete_tables = ['messages']

        try:
            # Convert IDs based on table type
            if table == 'messages':
                query_id = int(item_id)
            else:
                query_id = item_id

            if soft and table in soft_delete_tables:
                # Soft delete (mark as deleted with deleted_at timestamp)
                query = f"UPDATE {table} SET deleted_at = ? WHERE {id_column} = ?"
                await self.db.execute(query, (datetime.now(timezone.utc), query_id))
            else:
                # Hard delete
                query = f"DELETE FROM {table} WHERE {id_column} = ?"
                await self.db.execute(query, (query_id,))

            self._logger.info(
                "item_deleted",
                item_id=item_id,
                item_type=item_type,
                soft=soft
            )
            return True

        except Exception as e:
            self._logger.error("delete_failed", error=str(e), item_id=item_id)
            raise
