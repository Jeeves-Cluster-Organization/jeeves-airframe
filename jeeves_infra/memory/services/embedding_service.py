"""
Embedding generation service using sentence-transformers.

Provides:
- Single text embedding
- Batch embedding (more efficient)
- Similarity calculation
- LRU cache for performance

Note: This module requires sentence-transformers (1.5GB+ ML dependency).
      It is NOT eagerly imported by memory_module.services.
      Import directly when needed:
          from memory_module.services.embedding_service import EmbeddingService
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
import hashlib
import numpy as np
from functools import lru_cache

from shared import get_component_logger
from jeeves_infra.protocols import LoggerProtocol

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """Generate embeddings for text using sentence-transformers."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_size: int = 1000,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize embedding service.

        Args:
            model_name: Sentence-transformers model to use
            cache_size: Maximum number of cached embeddings
            logger: Optional logger instance (ADR-001 DI)
        """
        self._logger = get_component_logger("embedding_service", logger).bind(model=model_name)
        self.model_name = model_name
        self.cache_size = cache_size

        # Lazy import - only load heavy ML dep when actually instantiating
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            self._logger.info("embedding_service_initialized", model=model_name)
        except PermissionError as e:
            # P2: Fail loudly with specific actionable error
            error_msg = (
                f"PermissionError when downloading {model_name}. "
                f"Check that TRANSFORMERS_CACHE directory is writable. "
                f"Current cache location: {self._get_cache_location()}. "
                f"Original error: {str(e)}"
            )
            self._logger.error("embedding_service_init_failed", error=error_msg, cache_dir=self._get_cache_location())
            raise PermissionError(error_msg) from e
        except Exception as e:
            # P2: Fail loudly with context
            error_msg = f"Failed to initialize embedding model {model_name}: {str(e)}"
            self._logger.error("embedding_service_init_failed", error=error_msg, model=model_name)
            raise RuntimeError(error_msg) from e

        # Cache for embeddings
        self._cache: Dict[str, List[float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for single text with caching.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            self._logger.warning("empty_text_provided")
            return [0.0] * 384  # Return zero vector for empty text

        # Check cache
        cache_key = self._get_cache_key(text)
        if cache_key in self._cache:
            self._cache_hits += 1
            self._logger.debug("cache_hit", cache_hits=self._cache_hits)
            return self._cache[cache_key]

        # Generate embedding
        try:
            self._cache_misses += 1
            embedding = self.model.encode(text, convert_to_numpy=True)
            embedding_list = embedding.tolist()

            # Update cache (with simple LRU eviction)
            if len(self._cache) >= self.cache_size:
                # Remove oldest entry (first key)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

            self._cache[cache_key] = embedding_list

            self._logger.debug(
                "embedding_generated",
                text_length=len(text),
                embedding_dim=len(embedding_list),
                cache_misses=self._cache_misses
            )

            return embedding_list

        except Exception as e:
            self._logger.error("embedding_generation_failed", error=str(e), text_length=len(text))
            raise

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (more efficient than individual calls).

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter out empty texts and track indices
        non_empty_texts = []
        non_empty_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                non_empty_texts.append(text)
                non_empty_indices.append(i)

        if not non_empty_texts:
            self._logger.warning("all_texts_empty", count=len(texts))
            return [[0.0] * 384 for _ in texts]

        # Check cache for each text
        uncached_texts = []
        uncached_indices = []
        results = [None] * len(texts)

        for i, text in zip(non_empty_indices, non_empty_texts):
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                self._cache_hits += 1
                results[i] = self._cache[cache_key]
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                self._cache_misses += len(uncached_texts)
                embeddings = self.model.encode(uncached_texts, convert_to_numpy=True)

                for i, (text, embedding) in enumerate(zip(uncached_texts, embeddings)):
                    embedding_list = embedding.tolist()
                    cache_key = self._get_cache_key(text)

                    # Update cache
                    if len(self._cache) >= self.cache_size:
                        oldest_key = next(iter(self._cache))
                        del self._cache[oldest_key]

                    self._cache[cache_key] = embedding_list
                    results[uncached_indices[i]] = embedding_list

                self._logger.info(
                    "batch_embeddings_generated",
                    total=len(texts),
                    cached=self._cache_hits,
                    generated=len(uncached_texts)
                )

            except Exception as e:
                self._logger.error("batch_embedding_failed", error=str(e), count=len(uncached_texts))
                raise

        # Fill in zero vectors for empty texts
        for i in range(len(texts)):
            if results[i] is None:
                results[i] = [0.0] * 384

        return results

    def similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score between 0 and 1
        """
        try:
            emb1 = np.array(self.embed(text1))
            emb2 = np.array(self.embed(text2))

            # Cosine similarity
            dot_product = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            # Ensure result is in [0, 1] range (cosine similarity is in [-1, 1])
            # Convert to [0, 1] by: (similarity + 1) / 2
            normalized_similarity = (similarity + 1) / 2

            self._logger.debug(
                "similarity_calculated",
                text1_len=len(text1),
                text2_len=len(text2),
                similarity=normalized_similarity
            )

            return float(normalized_similarity)

        except Exception as e:
            self._logger.error("similarity_calculation_failed", error=str(e))
            raise

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache hit rate and size
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0

        return {
            "cache_size": len(self._cache),
            "cache_max_size": self.cache_size,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate
        }

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
        self._logger.info("cache_cleared")

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key from text.

        Args:
            text: Input text

        Returns:
            SHA-256 hash of the text
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _get_cache_location(self) -> str:
        """
        Get the current cache location for transformers.

        Returns:
            Path to cache directory
        """
        import os
        return os.environ.get('TRANSFORMERS_CACHE') or os.environ.get('HF_HOME') or '~/.cache/huggingface'
