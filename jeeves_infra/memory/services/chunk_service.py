"""
Chunk Service for L3 Semantic Memory.

High-level service for managing semantic chunks:
- Text chunking with overlap
- Embedding generation
- Semantic retrieval
- Source document management

Constitutional Alignment:
- P1: Uses LLM for semantic understanding
- M3: Fixed embedding dimension (384)
- M5: Uses repository abstraction
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

from jeeves_infra.memory.repositories.chunk_repository import ChunkRepository, Chunk
from jeeves_infra.logging import get_component_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class ChunkService:
    """
    Service for managing semantic chunks.

    Provides:
    - Text chunking with configurable size and overlap
    - Embedding generation via EmbeddingService
    - Semantic similarity search
    - Source document lifecycle management
    """

    # Default chunking parameters
    DEFAULT_CHUNK_SIZE = 512  # Characters per chunk
    DEFAULT_CHUNK_OVERLAP = 50  # Overlap between chunks

    def __init__(
        self,
        db: DatabaseClientProtocol,
        embedding_service: Optional[Any] = None,  # EmbeddingService
        repository: Optional[ChunkRepository] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize service.

        Args:
            db: Database client instance
            embedding_service: Service for generating embeddings
            repository: Optional pre-configured repository
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between adjacent chunks
            logger: Optional logger instance (ADR-001 DI)
        """
        self._logger = get_component_logger("ChunkService", logger)
        self.db = db
        self.embedding_service = embedding_service
        self.repository = repository or ChunkRepository(db)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def ensure_initialized(self) -> None:
        """Ensure the repository table exists."""
        await self.repository.ensure_table()

    async def chunk_and_store(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        generate_embeddings: bool = True
    ) -> List[Chunk]:
        """
        Chunk text and store with embeddings.

        Args:
            user_id: Owner user ID
            source_type: Type of source ('journal', 'task', 'message', 'fact')
            source_id: Source document ID
            content: Text content to chunk
            metadata: Additional metadata for chunks
            generate_embeddings: Whether to generate embeddings

        Returns:
            List of created chunks
        """
        # First, delete any existing chunks for this source
        await self.repository.delete_by_source(source_type, source_id)

        # Split into chunks
        text_chunks = self._split_text(content)

        if not text_chunks:
            self._logger.warning(
                "no_chunks_created",
                source_type=source_type,
                source_id=source_id,
                content_length=len(content)
            )
            return []

        # Create chunk objects
        chunks = []
        for i, text in enumerate(text_chunks):
            chunk = Chunk(
                user_id=user_id,
                source_type=source_type,
                source_id=source_id,
                content=text,
                metadata=metadata or {},
                chunk_index=i,
                total_chunks=len(text_chunks)
            )
            chunks.append(chunk)

        # Generate embeddings if requested and service available
        if generate_embeddings and self.embedding_service:
            chunks = await self._generate_embeddings(chunks)

        # Store chunks
        await self.repository.create_batch(chunks)

        self._logger.info(
            "chunks_created",
            source_type=source_type,
            source_id=source_id,
            chunk_count=len(chunks)
        )

        return chunks

    async def search(
        self,
        user_id: str,
        query: str,
        source_type: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search for semantically similar chunks.

        Args:
            user_id: User to search for
            query: Search query text
            source_type: Filter by source type (optional)
            limit: Maximum results
            min_similarity: Minimum similarity threshold

        Returns:
            List of search results with chunk and similarity
        """
        if not self.embedding_service:
            self._logger.warning("search_without_embedding_service")
            return []

        # Generate query embedding
        query_embedding = await self.embedding_service.embed_text(query)

        if not query_embedding:
            return []

        # Search repository
        results = await self.repository.search_similar(
            user_id=user_id,
            query_embedding=query_embedding,
            source_type=source_type,
            limit=limit,
            min_similarity=min_similarity
        )

        return [
            {
                "chunk_id": chunk.chunk_id,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "content": chunk.content,
                "similarity": similarity,
                "metadata": chunk.metadata
            }
            for chunk, similarity in results
        ]

    async def get_context_for_query(
        self,
        user_id: str,
        query: str,
        max_context_length: int = 2000,
        source_type: Optional[str] = None
    ) -> str:
        """
        Get relevant context for a query.

        Retrieves and concatenates relevant chunks for inclusion
        in LLM prompts.

        Args:
            user_id: User to search for
            query: Query to get context for
            max_context_length: Maximum total context length
            source_type: Filter by source type (optional)

        Returns:
            Concatenated relevant context
        """
        results = await self.search(
            user_id=user_id,
            query=query,
            source_type=source_type,
            limit=10,
            min_similarity=0.5
        )

        if not results:
            return ""

        # Build context within length limit
        context_parts = []
        total_length = 0

        for result in results:
            content = result["content"]
            if total_length + len(content) > max_context_length:
                # Truncate if needed
                remaining = max_context_length - total_length
                if remaining > 100:  # Worth including
                    context_parts.append(content[:remaining] + "...")
                break

            context_parts.append(content)
            total_length += len(content)

        return "\n---\n".join(context_parts)

    async def update_source(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        new_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """
        Update chunks for a source document.

        Replaces existing chunks with new ones.

        Args:
            user_id: Owner user ID
            source_type: Type of source
            source_id: Source document ID
            new_content: New text content
            metadata: New metadata

        Returns:
            List of new chunks
        """
        return await self.chunk_and_store(
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            content=new_content,
            metadata=metadata,
            generate_embeddings=True
        )

    async def delete_source(
        self,
        source_type: str,
        source_id: str
    ) -> None:
        """
        Delete all chunks for a source.

        Args:
            source_type: Type of source
            source_id: Source document ID
        """
        await self.repository.delete_by_source(source_type, source_id)

        self._logger.info(
            "source_chunks_deleted",
            source_type=source_type,
            source_id=source_id
        )

    async def get_source_chunks(
        self,
        source_type: str,
        source_id: str
    ) -> List[Chunk]:
        """
        Get all chunks for a source.

        Args:
            source_type: Type of source
            source_id: Source document ID

        Returns:
            List of chunks in order
        """
        return await self.repository.get_by_source(source_type, source_id)

    async def reconstruct_source(
        self,
        source_type: str,
        source_id: str
    ) -> str:
        """
        Reconstruct original text from chunks.

        Note: Due to overlap, this won't be exact but close.

        Args:
            source_type: Type of source
            source_id: Source document ID

        Returns:
            Reconstructed text
        """
        chunks = await self.get_source_chunks(source_type, source_id)

        if not chunks:
            return ""

        # Simple reconstruction (overlap handling would make this more accurate)
        return " ".join(chunk.content for chunk in chunks)

    def _split_text(self, text: str) -> List[str]:
        """
        Split text into chunks with overlap.

        Uses sentence-aware splitting when possible.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        if not text or len(text) <= self.chunk_size:
            return [text] if text else []

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # If not at the end, try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings
                search_start = max(start + self.chunk_size - 100, start)
                best_break = end

                for i in range(end, search_start, -1):
                    if text[i-1] in '.!?':
                        best_break = i
                        break
                    elif text[i-1] == ' ' and best_break == end:
                        best_break = i  # Fall back to word boundary

                end = best_break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start with overlap
            start = end - self.chunk_overlap
            if start >= len(text) - self.chunk_overlap:
                break

        return chunks

    async def _generate_embeddings(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Generate embeddings for chunks.

        Args:
            chunks: Chunks to embed

        Returns:
            Chunks with embeddings
        """
        if not self.embedding_service:
            return chunks

        texts = [chunk.content for chunk in chunks]

        try:
            embeddings = await self.embedding_service.embed_batch(texts)

            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

        except Exception as e:
            self._logger.error(
                "embedding_generation_failed",
                error=str(e),
                chunk_count=len(chunks)
            )

        return chunks

    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get chunk statistics for a user.

        Args:
            user_id: User identifier

        Returns:
            Statistics dictionary
        """
        total_chunks = await self.repository.count_by_user(user_id)

        return {
            "user_id": user_id,
            "total_chunks": total_chunks,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap
        }
