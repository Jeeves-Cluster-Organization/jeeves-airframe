"""
Chunk Repository for L3 Semantic Memory.

Stores text chunks with embeddings for semantic retrieval.
Chunks are extracted from:
- Journal entries
- Task descriptions
- Conversation history
- Knowledge facts

Constitutional Alignment:
- M2: Append-only with soft-delete
- M3: Fixed embedding dimension (384)
- M4: Structured metadata with schema versioning
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from uuid import uuid4
import json

from shared import get_component_logger, parse_datetime
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class Chunk:
    """Represents a text chunk with embedding for semantic search."""

    def __init__(
        self,
        chunk_id: Optional[str] = None,
        user_id: str = "",
        source_type: str = "",  # 'journal', 'task', 'message', 'fact'
        source_id: str = "",
        content: str = "",
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_index: int = 0,  # Position within source document
        total_chunks: int = 1,  # Total chunks from source
        created_at: Optional[datetime] = None,
        deleted_at: Optional[datetime] = None
    ):
        """
        Initialize a chunk.

        Args:
            chunk_id: Unique chunk identifier
            user_id: Owner user ID
            source_type: Type of source document
            source_id: ID of source document
            content: Text content of the chunk
            embedding: Vector embedding (384 dimensions)
            metadata: Additional structured metadata
            chunk_index: Position within source document
            total_chunks: Total number of chunks from source
            created_at: Creation timestamp
            deleted_at: Soft delete timestamp
        """
        self.chunk_id = chunk_id or str(uuid4())
        self.user_id = user_id
        self.source_type = source_type
        self.source_id = source_id
        self.content = content
        self.embedding = embedding
        self.metadata = metadata or {}
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks
        self.created_at = created_at or datetime.now(timezone.utc)
        self.deleted_at = deleted_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "user_id": self.user_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "content": self.content,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chunk":
        """Create from dictionary."""
        embedding = data.get("embedding")
        if isinstance(embedding, str):
            embedding = json.loads(embedding)

        return cls(
            chunk_id=data.get("chunk_id"),
            user_id=data.get("user_id", ""),
            source_type=data.get("source_type", ""),
            source_id=data.get("source_id", ""),
            content=data.get("content", ""),
            embedding=embedding,
            metadata=data.get("metadata"),
            chunk_index=data.get("chunk_index", 0),
            total_chunks=data.get("total_chunks", 1),
            created_at=parse_datetime(data.get("created_at")),
            deleted_at=parse_datetime(data.get("deleted_at"))
        )


class ChunkRepository:
    """
    Repository for semantic chunk storage and retrieval.

    Uses PostgreSQL with pgvector for native vector similarity search.
    """

    # Embedding dimension (matches all-MiniLM-L6-v2)
    EMBEDDING_DIM = 384

    CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT,  -- JSON array or vector type
            metadata TEXT,  -- JSON
            chunk_index INTEGER DEFAULT 0,
            total_chunks INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
    """

    CREATE_INDICES_SQL = [
        "CREATE INDEX IF NOT EXISTS idx_chunks_user ON chunks(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type, source_id)",
        "CREATE INDEX IF NOT EXISTS idx_chunks_user_source ON chunks(user_id, source_type)"
    ]

    def __init__(self, db: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """Initialize repository."""
        self._logger = get_component_logger("ChunkRepository", logger)
        self.db = db

    async def ensure_table(self) -> None:
        """Ensure the chunks table exists."""
        await self.db.execute(self.CREATE_TABLE_SQL)
        for index_sql in self.CREATE_INDICES_SQL:
            await self.db.execute(index_sql)

    async def create(self, chunk: Chunk) -> Chunk:
        """
        Create a new chunk.

        Args:
            chunk: Chunk to create

        Returns:
            Created chunk
        """
        query = """
            INSERT INTO chunks
            (chunk_id, user_id, source_type, source_id, content, embedding,
             metadata, chunk_index, total_chunks, created_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            chunk.chunk_id,
            chunk.user_id,
            chunk.source_type,
            chunk.source_id,
            chunk.content,
            json.dumps(chunk.embedding) if chunk.embedding else None,
            json.dumps(chunk.metadata) if chunk.metadata else None,
            chunk.chunk_index,
            chunk.total_chunks,
            chunk.created_at.isoformat() if chunk.created_at else None,
            chunk.deleted_at.isoformat() if chunk.deleted_at else None
        )

        await self.db.execute(query, params)

        self._logger.debug(
            "chunk_created",
            chunk_id=chunk.chunk_id,
            source_type=chunk.source_type,
            content_length=len(chunk.content)
        )

        return chunk

    async def create_batch(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Create multiple chunks in a batch.

        Args:
            chunks: Chunks to create

        Returns:
            Created chunks
        """
        for chunk in chunks:
            await self.create(chunk)

        self._logger.info(
            "chunks_batch_created",
            count=len(chunks)
        )

        return chunks

    async def get(self, chunk_id: str) -> Optional[Chunk]:
        """
        Get a chunk by ID.

        Args:
            chunk_id: Chunk identifier

        Returns:
            Chunk or None if not found
        """
        query = """
            SELECT * FROM chunks
            WHERE chunk_id = ? AND deleted_at IS NULL
        """

        row = await self.db.fetch_one(query, (chunk_id,))
        if not row:
            return None

        return self._row_to_chunk(row)

    async def get_by_source(
        self,
        source_type: str,
        source_id: str
    ) -> List[Chunk]:
        """
        Get all chunks for a source document.

        Args:
            source_type: Type of source
            source_id: Source identifier

        Returns:
            List of chunks ordered by index
        """
        query = """
            SELECT * FROM chunks
            WHERE source_type = ? AND source_id = ? AND deleted_at IS NULL
            ORDER BY chunk_index
        """

        rows = await self.db.fetch_all(query, (source_type, source_id))
        return [self._row_to_chunk(row) for row in rows]

    async def search_similar(
        self,
        user_id: str,
        query_embedding: List[float],
        source_type: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Tuple[Chunk, float]]:
        """
        Search for similar chunks using cosine similarity.

        Note: This implementation uses Python-side computation for portability.
        Production should use pgvector native operators for better performance.

        Args:
            user_id: User to search for
            query_embedding: Query vector
            source_type: Filter by source type (optional)
            limit: Maximum results
            min_similarity: Minimum similarity threshold

        Returns:
            List of (Chunk, similarity_score) tuples
        """
        # Build query
        conditions = ["user_id = ?", "deleted_at IS NULL", "embedding IS NOT NULL"]
        params: List[Any] = [user_id]

        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)

        query = f"""
            SELECT * FROM chunks
            WHERE {' AND '.join(conditions)}
        """

        rows = await self.db.fetch_all(query, tuple(params))

        # Compute similarities in Python (portable implementation)
        results: List[Tuple[Chunk, float]] = []
        for row in rows:
            chunk = self._row_to_chunk(row)
            if chunk.embedding:
                similarity = self._cosine_similarity(query_embedding, chunk.embedding)
                if similarity >= min_similarity:
                    results.append((chunk, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: -x[1])

        return results[:limit]

    async def delete_by_source(
        self,
        source_type: str,
        source_id: str
    ) -> int:
        """
        Soft-delete all chunks for a source.

        Args:
            source_type: Type of source
            source_id: Source identifier

        Returns:
            Number of chunks deleted (approximate)
        """
        now = datetime.now(timezone.utc)

        query = """
            UPDATE chunks
            SET deleted_at = ?
            WHERE source_type = ? AND source_id = ? AND deleted_at IS NULL
        """

        await self.db.execute(query, (now, source_type, source_id))

        self._logger.info(
            "chunks_deleted_by_source",
            source_type=source_type,
            source_id=source_id
        )

        return 0  # Affected row count not tracked

    async def update_embedding(
        self,
        chunk_id: str,
        embedding: List[float]
    ) -> Optional[Chunk]:
        """
        Update the embedding for a chunk.

        Args:
            chunk_id: Chunk identifier
            embedding: New embedding vector

        Returns:
            Updated chunk or None if not found
        """
        if len(embedding) != self.EMBEDDING_DIM:
            raise ValueError(f"Embedding must have {self.EMBEDDING_DIM} dimensions")

        query = """
            UPDATE chunks
            SET embedding = ?
            WHERE chunk_id = ? AND deleted_at IS NULL
        """

        await self.db.execute(query, (json.dumps(embedding), chunk_id))

        return await self.get(chunk_id)

    async def count_by_user(self, user_id: str) -> int:
        """
        Count chunks for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of chunks
        """
        query = """
            SELECT COUNT(*) as count FROM chunks
            WHERE user_id = ? AND deleted_at IS NULL
        """

        row = await self.db.fetch_one(query, (user_id,))
        return row["count"] if row else 0

    def _row_to_chunk(self, row: Dict[str, Any]) -> Chunk:
        """Convert database row to Chunk."""
        embedding = row.get("embedding")
        if isinstance(embedding, str):
            embedding = json.loads(embedding) if embedding else None

        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}

        return Chunk(
            chunk_id=row["chunk_id"],
            user_id=row["user_id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            content=row["content"],
            embedding=embedding,
            metadata=metadata,
            chunk_index=row.get("chunk_index", 0),
            total_chunks=row.get("total_chunks", 1),
            created_at=parse_datetime(row.get("created_at")),
            deleted_at=parse_datetime(row.get("deleted_at"))
        )

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
