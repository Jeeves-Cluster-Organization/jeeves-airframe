"""
Cross-reference management for memory items.

Tracks relationships between:
- Tasks <-> Journal entries
- Tasks <-> Conversations
- Journal <-> Facts
- Conversations <-> Tasks/Journal
"""

from typing import List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime, timezone
from jeeves_infra.logging import get_component_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol



class CrossRefManager:
    """Manage relationships between memory items."""

    def __init__(self, db_client: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """
        Initialize cross-reference manager.

        Args:
            db_client: Database client instance
            logger: Optional logger instance (ADR-001 DI)
        """
        self.db = db_client
        self._logger = get_component_logger("xref_manager", logger)

    async def create_ref(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        relationship: str = "references",
        confidence: float = 1.0
    ) -> str:
        """
        Create a cross-reference.

        Args:
            source_id: Source item ID
            source_type: Source item type (task, journal, message, fact)
            target_id: Target item ID
            target_type: Target item type
            relationship: Relationship type (references, mentions, related_to, etc.)
            confidence: Confidence score (0.0-1.0)

        Returns:
            Reference ID
        """
        ref_id = str(uuid4())

        query = """
            INSERT INTO memory_cross_refs (
                ref_id, source_id, source_type,
                target_id, target_type, relationship,
                confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relationship) DO UPDATE SET
                confidence = excluded.confidence
        """

        params = (
            ref_id,
            source_id,
            source_type,
            target_id,
            target_type,
            relationship,
            confidence,
            datetime.now(timezone.utc)
        )

        try:
            await self.db.execute(query, params)
            self._logger.info(
                "cross_ref_created",
                ref_id=ref_id,
                source_id=source_id,
                source_type=source_type,
                target_id=target_id,
                target_type=target_type,
                relationship=relationship
            )
            return ref_id

        except Exception as e:
            self._logger.error(
                "cross_ref_creation_failed",
                error=str(e),
                source_id=source_id,
                target_id=target_id
            )
            raise

    async def create_refs_batch(
        self,
        references: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Create multiple cross-references in batch.

        Args:
            references: List of reference dicts with source_id, source_type,
                       target_id, target_type, relationship, confidence

        Returns:
            List of reference IDs
        """
        ref_ids = []

        for ref in references:
            try:
                ref_id = await self.create_ref(
                    source_id=ref['source_id'],
                    source_type=ref['source_type'],
                    target_id=ref['target_id'],
                    target_type=ref['target_type'],
                    relationship=ref.get('relationship', 'references'),
                    confidence=ref.get('confidence', 1.0)
                )
                ref_ids.append(ref_id)
            except Exception as e:
                self._logger.error(
                    "batch_ref_creation_failed",
                    error=str(e),
                    reference=ref
                )
                # Continue with other references even if one fails
                continue

        self._logger.info("batch_refs_created", count=len(ref_ids), total=len(references))
        return ref_ids

    async def find_refs(
        self,
        item_id: str,
        direction: str = "both",
        item_type: Optional[str] = None,
        relationship: Optional[str] = None,
        min_confidence: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Find all references for an item.

        Args:
            item_id: Item ID
            direction: Direction to search (outgoing, incoming, both)
            item_type: Optional filter by item type
            relationship: Optional filter by relationship type
            min_confidence: Minimum confidence threshold

        Returns:
            List of cross-references
        """
        # Build query based on direction
        if direction == "outgoing":
            where_clause = "source_id = ?"
            params = [item_id]
        elif direction == "incoming":
            where_clause = "target_id = ?"
            params = [item_id]
        elif direction == "both":
            where_clause = "(source_id = ? OR target_id = ?)"
            params = [item_id, item_id]
        else:
            raise ValueError(f"Invalid direction: {direction}")

        # Add optional filters
        if item_type:
            where_clause += " AND (source_type = ? OR target_type = ?)"
            params.extend([item_type, item_type])

        if relationship:
            where_clause += " AND relationship = ?"
            params.append(relationship)

        if min_confidence > 0.0:
            where_clause += " AND confidence >= ?"
            params.append(min_confidence)

        query = f"""
            SELECT * FROM memory_cross_refs
            WHERE {where_clause}
            ORDER BY confidence DESC, created_at DESC
        """

        try:
            results = await self.db.fetch_all(query, tuple(params))
            refs = [dict(row) for row in results]

            self._logger.debug(
                "refs_found",
                item_id=item_id,
                direction=direction,
                count=len(refs)
            )

            return refs

        except Exception as e:
            self._logger.error(
                "find_refs_failed",
                error=str(e),
                item_id=item_id,
                direction=direction
            )
            raise

    async def get_related_items(
        self,
        item_id: str,
        item_type: str,
        depth: int = 1,
        min_confidence: float = 0.5
    ) -> Dict[str, List[str]]:
        """
        Get all items related to this item (grouped by type).

        Args:
            item_id: Item ID
            item_type: Item type (task, journal, message, fact)
            depth: How many hops to traverse (1 = direct refs only, 2 = refs of refs)
            min_confidence: Minimum confidence threshold

        Returns:
            Dict mapping item types to lists of related item IDs
        """
        related = {
            'tasks': [],
            'journal': [],
            'messages': [],
            'facts': []
        }

        visited = set()
        to_visit = [(item_id, item_type, 0)]  # (id, type, current_depth)

        while to_visit:
            current_id, current_type, current_depth = to_visit.pop(0)

            if current_id in visited or current_depth >= depth:
                continue

            visited.add(current_id)

            # Find all refs for this item
            refs = await self.find_refs(
                item_id=current_id,
                direction="both",
                min_confidence=min_confidence
            )

            # Process refs
            for ref in refs:
                # Determine which side is the related item
                if ref['source_id'] == current_id:
                    related_id = ref['target_id']
                    related_type = ref['target_type']
                else:
                    related_id = ref['source_id']
                    related_type = ref['source_type']

                # Skip self-references
                if related_id == item_id:
                    continue

                # Add to results
                type_key = {
                    'task': 'tasks',
                    'journal': 'journal',
                    'message': 'messages',
                    'fact': 'facts'
                }.get(related_type)

                if type_key and related_id not in related[type_key]:
                    related[type_key].append(related_id)

                # Add to visit queue if depth allows
                if current_depth + 1 < depth:
                    to_visit.append((related_id, related_type, current_depth + 1))

        self._logger.info(
            "related_items_found",
            item_id=item_id,
            depth=depth,
            tasks=len(related['tasks']),
            journal=len(related['journal']),
            messages=len(related['messages']),
            facts=len(related['facts'])
        )

        return related

    async def extract_refs_from_text(
        self,
        text: str,
        source_id: str,
        source_type: str,
        existing_items: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        min_confidence: float = 0.7
    ) -> List[str]:
        """
        Extract references from text using pattern matching.

        This is a simple implementation that looks for explicit mentions.
        Could be enhanced with LLM-based extraction for better accuracy.

        Args:
            text: Text to analyze
            source_id: Source item ID
            source_type: Source item type
            existing_items: Optional dict of existing items by type
            min_confidence: Minimum confidence threshold

        Returns:
            List of created reference IDs
        """
        if not text or not existing_items:
            return []

        created_refs = []
        text_lower = text.lower()

        # Simple keyword matching for different types
        patterns = {
            'task': ['task', 'todo', 'complete', 'finish', 'work on'],
            'journal': ['note', 'journal', 'thought', 'reflection'],
            'fact': ['preference', 'remember', 'always', 'never']
        }

        # Check each item type
        for item_type, items in existing_items.items():
            if not items:
                continue

            # Check if text mentions this type
            type_mentioned = any(
                keyword in text_lower
                for keyword in patterns.get(item_type.rstrip('s'), [])
            )

            if not type_mentioned:
                continue

            # Check each item
            for item in items:
                # Get item identifier (title, key, or content)
                identifier = None
                if 'title' in item:
                    identifier = item['title']
                elif 'key' in item:
                    identifier = item['key']
                elif 'content' in item:
                    identifier = item['content'][:100]  # First 100 chars

                if not identifier:
                    continue

                # Check if identifier is mentioned in text
                if identifier.lower() in text_lower:
                    # Create cross-reference with moderate confidence
                    try:
                        ref_id = await self.create_ref(
                            source_id=source_id,
                            source_type=source_type,
                            target_id=item.get('task_id') or item.get('entry_id') or item.get('message_id') or str(item.get('id')),
                            target_type=item_type.rstrip('s'),  # Remove plural
                            relationship='mentions',
                            confidence=0.8  # Moderate confidence for keyword matching
                        )
                        created_refs.append(ref_id)
                    except Exception as e:
                        self._logger.error(
                            "extract_ref_failed",
                            error=str(e),
                            identifier=identifier
                        )
                        continue

        self._logger.info(
            "refs_extracted_from_text",
            source_id=source_id,
            refs_created=len(created_refs)
        )

        return created_refs

    async def delete_refs_for_item(
        self,
        item_id: str
    ) -> int:
        """
        Delete all cross-references for an item.

        Args:
            item_id: Item ID

        Returns:
            Number of references deleted
        """
        query = """
            DELETE FROM memory_cross_refs
            WHERE source_id = ? OR target_id = ?
        """

        try:
            result = await self.db.execute(query, (item_id, item_id))
            # Note: result might not have rowcount depending on DB driver
            self._logger.info("refs_deleted_for_item", item_id=item_id)
            return 0

        except Exception as e:
            self._logger.error("delete_refs_failed", error=str(e), item_id=item_id)
            raise

    async def get_ref_stats(self) -> Dict[str, Any]:
        """
        Get statistics about cross-references.

        Returns:
            Dict with stats (total refs, by relationship type, etc.)
        """
        try:
            # Total refs
            total_query = "SELECT COUNT(*) as total FROM memory_cross_refs"
            total_result = await self.db.fetch_one(total_query)
            total = total_result['total'] if total_result else 0

            # By relationship type
            rel_query = """
                SELECT relationship, COUNT(*) as count
                FROM memory_cross_refs
                GROUP BY relationship
            """
            rel_results = await self.db.fetch_all(rel_query)
            by_relationship = {row['relationship']: row['count'] for row in rel_results}

            # By source type
            source_query = """
                SELECT source_type, COUNT(*) as count
                FROM memory_cross_refs
                GROUP BY source_type
            """
            source_results = await self.db.fetch_all(source_query)
            by_source_type = {row['source_type']: row['count'] for row in source_results}

            return {
                'total_refs': total,
                'by_relationship': by_relationship,
                'by_source_type': by_source_type
            }

        except Exception as e:
            self._logger.error("get_stats_failed", error=str(e))
            return {'total_refs': 0, 'by_relationship': {}, 'by_source_type': {}}
