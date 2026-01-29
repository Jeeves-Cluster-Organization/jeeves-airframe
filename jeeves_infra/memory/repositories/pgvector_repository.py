"""
pgvector repository for embedding storage and semantic search.

Provides:
- Vector storage in PostgreSQL tables
- Semantic similarity search
- Metadata filtering
- Hybrid search (vector + SQL filters)
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import text
import numpy as np

from shared import get_component_logger
from jeeves_infra.protocols import LoggerProtocol


class PgVectorRepository:
    """Handles embedding storage and semantic search via pgvector."""

    def __init__(
        self,
        postgres_client: 'PostgreSQLClient',
        embedding_service: 'EmbeddingService',
        dimension: int = 384,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize pgvector repository.

        Args:
            postgres_client: PostgreSQL client instance
            embedding_service: Embedding service for generating vectors
            dimension: Vector dimension (default: 384 for all-MiniLM-L6-v2)
            logger: Optional logger instance
        """
        self._logger = get_component_logger("PgVectorRepository", logger)
        self.db = postgres_client
        self.embeddings = embedding_service
        self.dimension = dimension

        # Map collection names to table names and ID columns
        self.collection_config = {
            "tasks": {"table": "tasks", "id_col": "task_id", "content_col": "title"},
            "journal": {"table": "journal_entries", "id_col": "entry_id", "content_col": "content"},
            "facts": {"table": "knowledge_facts", "id_col": "fact_id", "content_col": "value"},
            "conversations": {"table": "messages", "id_col": "message_id", "content_col": "content"},
            "sessions": {"table": "sessions", "id_col": "session_id", "content_col": "title"},
        }

    def _validate_collection(self, collection: str) -> Dict[str, str]:
        """Validate collection name and return config.

        Args:
            collection: Collection name

        Returns:
            Collection configuration dictionary

        Raises:
            ValueError: If collection is invalid
        """
        if collection not in self.collection_config:
            self._logger.error("invalid_collection", collection=collection)
            raise ValueError(
                f"Invalid collection: {collection}. "
                f"Valid: {list(self.collection_config.keys())}"
            )
        return self.collection_config[collection]

    async def upsert(
        self,
        item_id: str,
        content: str,
        collection: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Generate embedding and store in PostgreSQL table.

        Args:
            item_id: Unique identifier for the item
            content: Text content to embed
            collection: Collection name (tasks, journal, facts, conversations, sessions)
            metadata: Optional metadata (not used in current implementation)

        Returns:
            True if successful, False otherwise
        """
        config = self._validate_collection(collection)
        table = config["table"]
        id_col = config["id_col"]

        try:
            # Generate embedding
            embedding = self.embeddings.embed(content)

            # Convert embedding to pgvector format (list of floats)
            if isinstance(embedding, np.ndarray):
                embedding_list = embedding.tolist()
            else:
                embedding_list = embedding

            # Format as PostgreSQL vector literal: '[0.1,0.2,...]'
            embedding_literal = '[' + ','.join(str(v) for v in embedding_list) + ']'

            # Update the embedding column for the item
            query = f"""
            UPDATE {table}
            SET embedding = CAST(:embedding AS vector)
            WHERE {id_col} = :item_id
            """

            async with self.db.session() as session:
                result = await session.execute(
                    text(query),
                    {
                        "embedding": embedding_literal,
                        "item_id": item_id
                    }
                )
                await session.commit()

                rows_updated = result.rowcount

            if rows_updated > 0:
                self._logger.info(
                    "vector_upserted",
                    item_id=item_id,
                    collection=collection,
                    table=table,
                    embedding_dim=len(embedding_list)
                )
                return True
            else:
                self._logger.warning(
                    "vector_upsert_no_match",
                    item_id=item_id,
                    collection=collection,
                    table=table
                )
                return False

        except Exception as e:
            self._logger.error(
                "vector_upsert_failed",
                item_id=item_id,
                collection=collection,
                error=str(e)
            )
            return False

    async def search(
        self,
        query: str,
        collections: List[str],
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across collections using pgvector.

        Args:
            query: Search query text
            collections: List of collection names to search
            filters: Optional filters (e.g., {"user_id": "123", "status": "pending"})
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of search results with scores
        """
        if not query or not query.strip():
            self._logger.warning("empty_search_query")
            return []

        # Validate collections
        for collection in collections:
            self._validate_collection(collection)

        try:
            # Generate query embedding
            query_embedding = self.embeddings.embed(query)

            # Convert to list if numpy array
            if isinstance(query_embedding, np.ndarray):
                embedding_list = query_embedding.tolist()
            else:
                embedding_list = query_embedding

            all_results = []

            # Search each collection
            for collection in collections:
                config = self.collection_config[collection]
                table = config["table"]
                id_col = config["id_col"]
                content_col = config["content_col"]

                # Format as PostgreSQL vector literal: '[0.1,0.2,...]'
                embedding_literal = '[' + ','.join(str(v) for v in embedding_list) + ']'

                # Build WHERE clause for filters
                where_clauses = ["embedding IS NOT NULL"]
                params = {
                    "embedding": embedding_literal,
                    "min_similarity": min_similarity,
                    "limit": limit
                }

                if filters:
                    for key, value in filters.items():
                        param_name = f"filter_{key}"
                        where_clauses.append(f"{key} = :{param_name}")
                        params[param_name] = value

                where_sql = " AND ".join(where_clauses)

                # Build search query
                query_sql = f"""
                SELECT
                    {id_col} AS item_id,
                    {content_col} AS content,
                    (1 - (embedding <=> CAST(:embedding AS vector))) AS score
                FROM {table}
                WHERE {where_sql}
                  AND (1 - (embedding <=> CAST(:embedding AS vector))) >= :min_similarity
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """

                # Execute search
                async with self.db.session() as session:
                    result = await session.execute(text(query_sql), params)
                    rows = result.fetchall()

                    for row in rows:
                        all_results.append({
                            "item_id": str(row.item_id),
                            "collection": collection,
                            "content": row.content,
                            "score": float(row.score),
                            "distance": 1.0 - float(row.score),
                            "metadata": {}  # Can be extended to include other columns
                        })

            # Sort by score (highest first)
            all_results.sort(key=lambda x: x['score'], reverse=True)

            # Limit results
            final_results = all_results[:limit]

            self._logger.info(
                "search_completed",
                query_length=len(query),
                collections=collections,
                results_count=len(final_results)
            )

            return final_results

        except Exception as e:
            self._logger.error(
                "search_failed",
                query=query[:100],
                collections=collections,
                error=str(e)
            )
            raise

    async def delete(
        self,
        item_id: str,
        collection: str
    ) -> bool:
        """
        Remove embedding from PostgreSQL table.

        Args:
            item_id: Unique identifier for the item
            collection: Collection name

        Returns:
            True if successful, False otherwise
        """
        config = self._validate_collection(collection)
        table = config["table"]
        id_col = config["id_col"]

        try:
            # Set embedding to NULL (doesn't delete the row)
            query = f"""
            UPDATE {table}
            SET embedding = NULL
            WHERE {id_col} = :item_id
            """

            async with self.db.session() as session:
                result = await session.execute(
                    text(query),
                    {"item_id": item_id}
                )
                await session.commit()

                rows_updated = result.rowcount

            if rows_updated > 0:
                self._logger.info("vector_deleted", item_id=item_id, collection=collection)
                return True
            else:
                self._logger.warning("vector_delete_no_match", item_id=item_id, collection=collection)
                return False

        except Exception as e:
            self._logger.error(
                "vector_delete_failed",
                item_id=item_id,
                collection=collection,
                error=str(e)
            )
            return False

    async def get(
        self,
        item_id: str,
        collection: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific item's embedding from PostgreSQL.

        Args:
            item_id: Unique identifier for the item
            collection: Collection name

        Returns:
            Item data or None if not found
        """
        config = self._validate_collection(collection)
        table = config["table"]
        id_col = config["id_col"]
        content_col = config["content_col"]

        try:
            query = f"""
            SELECT
                {id_col} AS item_id,
                {content_col} AS content,
                embedding
            FROM {table}
            WHERE {id_col} = :item_id
            """

            async with self.db.session() as session:
                result = await session.execute(
                    text(query),
                    {"item_id": item_id}
                )
                row = result.fetchone()

            if row is None:
                return None

            # Convert embedding from pgvector format if present
            embedding = None
            if row.embedding is not None:
                # pgvector returns as string, parse to list
                embedding = eval(row.embedding) if isinstance(row.embedding, str) else row.embedding

            return {
                "item_id": str(row.item_id),
                "content": row.content,
                "embedding": embedding,
                "metadata": {}
            }

        except Exception as e:
            self._logger.error(
                "vector_get_failed",
                item_id=item_id,
                collection=collection,
                error=str(e)
            )
            return None

    async def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        """
        Get statistics for a collection.

        Args:
            collection: Collection name

        Returns:
            Dictionary with collection statistics
        """
        config = self._validate_collection(collection)
        table = config["table"]

        try:
            query = f"""
            SELECT
                COUNT(*) AS total_count,
                COUNT(embedding) AS embedded_count,
                COUNT(*) - COUNT(embedding) AS missing_embeddings
            FROM {table}
            """

            async with self.db.session() as session:
                result = await session.execute(text(query))
                row = result.fetchone()

            return {
                "collection": collection,
                "table": table,
                "total_count": row.total_count,
                "embedded_count": row.embedded_count,
                "missing_embeddings": row.missing_embeddings
            }

        except Exception as e:
            self._logger.error("get_stats_failed", collection=collection, error=str(e))
            return {"collection": collection, "error": str(e)}

    async def rebuild_index(self, collection: str, lists: int = 100):
        """
        Rebuild the IVFFlat index for a collection.

        Args:
            collection: Collection name
            lists: Number of lists for IVFFlat index (tune based on data size)
        """
        config = self._validate_collection(collection)
        table = config["table"]

        try:
            # Drop existing index
            drop_query = f"""
            DROP INDEX IF EXISTS idx_{table}_embedding_cosine
            """

            # Recreate index
            create_query = f"""
            CREATE INDEX idx_{table}_embedding_cosine
            ON {table} USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {lists})
            """

            async with self.db.engine.begin() as conn:
                await conn.execute(text(drop_query))
                await conn.execute(text(create_query))

            self._logger.info("index_rebuilt", collection=collection, table=table, lists=lists)

        except Exception as e:
            self._logger.error("index_rebuild_failed", collection=collection, error=str(e))
            raise

    async def batch_upsert(
        self,
        items: List[Dict[str, Any]],
        collection: str
    ) -> int:
        """
        Batch upsert embeddings for multiple items.

        Args:
            items: List of items, each with 'item_id' and 'content' keys
            collection: Collection name

        Returns:
            Number of items successfully updated
        """
        config = self._validate_collection(collection)
        table = config["table"]
        id_col = config["id_col"]

        success_count = 0

        try:
            # Generate embeddings in batch
            contents = [item["content"] for item in items]
            embeddings = [self.embeddings.embed(content) for content in contents]

            # Update in transaction
            async with self.db.transaction() as session:
                for item, embedding in zip(items, embeddings):
                    # Convert to list if needed
                    if isinstance(embedding, np.ndarray):
                        embedding_list = embedding.tolist()
                    else:
                        embedding_list = embedding

                    # Format as PostgreSQL vector literal: '[0.1,0.2,...]'
                    embedding_literal = '[' + ','.join(str(v) for v in embedding_list) + ']'

                    query = f"""
                    UPDATE {table}
                    SET embedding = CAST(:embedding AS vector)
                    WHERE {id_col} = :item_id
                    """

                    result = await session.execute(
                        text(query),
                        {
                            "embedding": embedding_literal,
                            "item_id": item["item_id"]
                        }
                    )

                    if result.rowcount > 0:
                        success_count += 1

            self._logger.info(
                "batch_upsert_completed",
                collection=collection,
                total=len(items),
                success=success_count
            )

            return success_count

        except Exception as e:
            self._logger.error(
                "batch_upsert_failed",
                collection=collection,
                error=str(e)
            )
            return success_count
