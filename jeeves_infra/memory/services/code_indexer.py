"""
Code indexer service for RAG-based semantic search.

Provides:
- Full repository file indexing
- Embedding generation for code files
- Storage in code_index table with pgvector
- Simple content-based indexing (no AST chunking)
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from sqlalchemy import text

from jeeves_infra.protocols import LanguageConfigProtocol, LoggerProtocol, DatabaseClientProtocol
from jeeves_infra.logging import get_component_logger

if TYPE_CHECKING:
    from jeeves_infra.memory.services.embedding_service import EmbeddingService


class CodeIndexer:
    """
    Index code files for RAG-based semantic search.

    Simple approach: embed entire files (or truncated content for large files).
    No AST chunking - just straightforward file content embedding.
    """

    # Maximum content length to embed (chars) - keeps embeddings focused
    MAX_CONTENT_LENGTH = 8000

    # File extensions to index
    INDEXABLE_EXTENSIONS = {
        '.py', '.js', '.ts', '.tsx', '.jsx',
        '.java', '.go', '.rs', '.rb', '.php',
        '.c', '.cpp', '.h', '.hpp', '.cs',
        '.sql', '.sh', '.bash', '.zsh',
        '.yaml', '.yml', '.json', '.toml',
        '.md', '.txt', '.rst',
        '.html', '.css', '.scss', '.less',
    }

    # Directories to skip
    SKIP_DIRS = {
        '.git', '.svn', '.hg',
        'node_modules', '__pycache__', '.pytest_cache',
        'venv', '.venv', 'env', '.env',
        'dist', 'build', 'target', 'out',
        '.idea', '.vscode', '.eclipse',
        'coverage', '.coverage', 'htmlcov',
        '.tox', '.nox', '.mypy_cache',
    }

    def __init__(
        self,
        postgres_client: DatabaseClientProtocol,
        embedding_service: 'EmbeddingService',
        language_config: Optional[LanguageConfigProtocol] = None,
        logger: Optional[LoggerProtocol] = None,
    ):
        """
        Initialize code indexer.

        Args:
            postgres_client: PostgreSQL client for database operations
            embedding_service: Service for generating embeddings
            language_config: Optional language configuration protocol (ADR-001 DI)
            logger: Optional logger instance (ADR-001 DI)
        """
        self._logger = get_component_logger("code_indexer", logger)
        self.db = postgres_client
        self.embeddings = embedding_service
        self._language_config = language_config

        # Use injected language config for additional exclusions if provided
        if language_config is not None:
            try:
                # Get exclude_dirs if available on the protocol implementation
                exclude_dirs = getattr(language_config, 'exclude_dirs', [])
                self.skip_dirs = self.SKIP_DIRS | set(exclude_dirs)
            except Exception:
                self.skip_dirs = self.SKIP_DIRS
        else:
            self.skip_dirs = self.SKIP_DIRS

    def _should_index_file(self, path: Path) -> bool:
        """Check if a file should be indexed."""
        # Check extension
        if path.suffix.lower() not in self.INDEXABLE_EXTENSIONS:
            return False

        # Check if any parent dir should be skipped
        for part in path.parts:
            if part in self.skip_dirs:
                return False

        # Skip hidden files
        if path.name.startswith('.'):
            return False

        return True

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _detect_language(self, path: Path) -> str:
        """Detect programming language from file extension."""
        ext_to_lang = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.jsx': 'javascript',
            '.java': 'java',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.hpp': 'cpp',
            '.cs': 'csharp',
            '.sql': 'sql',
            '.sh': 'shell',
            '.bash': 'shell',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.toml': 'toml',
            '.md': 'markdown',
            '.html': 'html',
            '.css': 'css',
        }
        return ext_to_lang.get(path.suffix.lower(), 'unknown')

    def _prepare_content_for_embedding(self, path: Path, content: str) -> str:
        """
        Prepare file content for embedding.

        Includes file path context and truncates if too long.
        """
        # Add file path as context prefix
        prefix = f"File: {path}\n\n"

        # Truncate content if needed
        max_content = self.MAX_CONTENT_LENGTH - len(prefix)
        if len(content) > max_content:
            content = content[:max_content] + "\n... [truncated]"

        return prefix + content

    async def discover_files(self, repo_path: str) -> List[Path]:
        """
        Discover all indexable files in repository.

        Args:
            repo_path: Path to repository root

        Returns:
            List of file paths to index
        """
        repo = Path(repo_path)
        if not repo.exists():
            self._logger.error("repo_path_not_found", path=repo_path)
            return []

        files = []
        for root, dirs, filenames in os.walk(repo):
            # Prune directories to skip
            dirs[:] = [d for d in dirs if d not in self.skip_dirs]

            for filename in filenames:
                filepath = Path(root) / filename
                rel_path = filepath.relative_to(repo)

                if self._should_index_file(rel_path):
                    files.append(rel_path)

        self._logger.info("files_discovered", count=len(files), repo=repo_path)
        return files

    async def get_indexed_hashes(self) -> Dict[str, str]:
        """
        Get currently indexed file paths and their content hashes.

        Returns:
            Dict mapping file_path -> content_hash
        """
        try:
            query = "SELECT file_path, content_hash FROM code_index"
            async with self.db.session() as session:
                result = await session.execute(text(query))
                rows = result.fetchall()

            return {row.file_path: row.content_hash for row in rows}
        except Exception as e:
            self._logger.error("get_indexed_hashes_failed", error=str(e))
            return {}

    async def index_file(
        self,
        repo_path: str,
        file_path: Path,
        force: bool = False,
    ) -> bool:
        """
        Index a single file.

        Args:
            repo_path: Repository root path
            file_path: Relative path to file
            force: Force re-indexing even if hash matches

        Returns:
            True if file was indexed/updated, False if skipped or failed
        """
        full_path = Path(repo_path) / file_path

        if not full_path.exists():
            self._logger.warning("file_not_found", path=str(file_path))
            return False

        try:
            # Read file content
            content = full_path.read_text(encoding='utf-8', errors='replace')
            content_hash = self._compute_hash(content)

            # Check if already indexed with same hash
            if not force:
                existing = await self._get_existing_hash(str(file_path))
                if existing == content_hash:
                    self._logger.debug("file_unchanged", path=str(file_path))
                    return False

            # Prepare content and generate embedding
            embed_content = self._prepare_content_for_embedding(file_path, content)
            embedding = self.embeddings.embed(embed_content)

            # Detect language
            language = self._detect_language(file_path)

            # Calculate stats
            size_bytes = len(content.encode('utf-8'))
            line_count = content.count('\n') + 1

            # Upsert to database
            await self._upsert_file_index(
                file_path=str(file_path),
                content_hash=content_hash,
                language=language,
                size_bytes=size_bytes,
                line_count=line_count,
                embedding=embedding,
            )

            self._logger.debug(
                "file_indexed",
                path=str(file_path),
                language=language,
                size=size_bytes,
            )
            return True

        except Exception as e:
            self._logger.error("index_file_failed", path=str(file_path), error=str(e))
            return False

    async def _get_existing_hash(self, file_path: str) -> Optional[str]:
        """Get existing content hash for a file."""
        try:
            query = "SELECT content_hash FROM code_index WHERE file_path = :path"
            async with self.db.session() as session:
                result = await session.execute(text(query), {"path": file_path})
                row = result.fetchone()
            return row.content_hash if row else None
        except Exception:
            return None

    async def _upsert_file_index(
        self,
        file_path: str,
        content_hash: str,
        language: str,
        size_bytes: int,
        line_count: int,
        embedding: List[float],
    ) -> None:
        """Upsert file index entry."""
        # Format embedding as PostgreSQL vector literal: '[0.1,0.2,...]'
        embedding_literal = '[' + ','.join(str(v) for v in embedding) + ']'

        query = """
        INSERT INTO code_index (
            file_path, content_hash, language, size_bytes, line_count,
            embedding, last_indexed
        ) VALUES (
            :file_path, :content_hash, :language, :size_bytes, :line_count,
            CAST(:embedding AS vector), NOW()
        )
        ON CONFLICT (file_path) DO UPDATE SET
            content_hash = EXCLUDED.content_hash,
            language = EXCLUDED.language,
            size_bytes = EXCLUDED.size_bytes,
            line_count = EXCLUDED.line_count,
            embedding = EXCLUDED.embedding,
            last_indexed = NOW()
        """

        async with self.db.session() as session:
            await session.execute(text(query), {
                "file_path": file_path,
                "content_hash": content_hash,
                "language": language,
                "size_bytes": size_bytes,
                "line_count": line_count,
                "embedding": embedding_literal,
            })
            await session.commit()

    async def index_repository(
        self,
        repo_path: str,
        force: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Index all files in a repository.

        Args:
            repo_path: Path to repository root
            force: Force re-indexing all files
            progress_callback: Optional callback(current, total, file_path)

        Returns:
            Dict with indexing statistics
        """
        self._logger.info("starting_repository_index", repo=repo_path, force=force)

        # Discover files
        files = await self.discover_files(repo_path)
        total = len(files)

        if total == 0:
            self._logger.warning("no_files_to_index", repo=repo_path)
            return {
                "status": "completed",
                "total_files": 0,
                "indexed": 0,
                "skipped": 0,
                "failed": 0,
            }

        indexed = 0
        skipped = 0
        failed = 0

        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(i + 1, total, str(file_path))

            try:
                result = await self.index_file(repo_path, file_path, force=force)
                if result:
                    indexed += 1
                else:
                    skipped += 1
            except Exception as e:
                self._logger.error("index_file_error", path=str(file_path), error=str(e))
                failed += 1

        stats = {
            "status": "completed",
            "total_files": total,
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
        }

        self._logger.info("repository_index_completed", **stats)
        return stats

    async def search(
        self,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.3,
        languages: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search indexed code files by semantic similarity.

        Args:
            query: Search query text
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)
            languages: Optional list of languages to filter by

        Returns:
            List of search results with file_path, language, score
        """
        if not query or not query.strip():
            return []

        try:
            # Transform query to match the indexed embedding space
            # Files are indexed with "File: {path}\n\n{content}" format
            # For raw queries, we add context to bridge the semantic gap
            if not query.startswith("File:"):
                # Add search context prefix for raw queries
                # This helps match the semantic space of indexed file content
                query_for_embedding = f"Code file containing: {query}"
            else:
                # Query already has file context (e.g., from find_similar_files)
                query_for_embedding = query

            # Generate query embedding and format as PostgreSQL vector literal
            query_embedding = self.embeddings.embed(query_for_embedding)
            embedding_literal = '[' + ','.join(str(v) for v in query_embedding) + ']'

            # Build query
            where_clauses = ["embedding IS NOT NULL"]
            params = {
                "embedding": embedding_literal,
                "min_similarity": min_similarity,
                "limit": limit,
            }

            if languages:
                where_clauses.append("language = ANY(:languages)")
                params["languages"] = languages

            where_sql = " AND ".join(where_clauses)

            query_sql = f"""
            SELECT
                file_path,
                language,
                size_bytes,
                line_count,
                (1 - (embedding <=> CAST(:embedding AS vector))) AS score
            FROM code_index
            WHERE {where_sql}
              AND (1 - (embedding <=> CAST(:embedding AS vector))) >= :min_similarity
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """

            async with self.db.session() as session:
                result = await session.execute(text(query_sql), params)
                rows = result.fetchall()

            results = [
                {
                    "file_path": row.file_path,
                    "language": row.language,
                    "size_bytes": row.size_bytes,
                    "line_count": row.line_count,
                    "score": float(row.score),
                }
                for row in rows
            ]

            self._logger.info(
                "search_completed",
                query_length=len(query),
                query_transformed=not query.startswith("File:"),
                results_count=len(results),
            )

            return results

        except Exception as e:
            self._logger.error("search_failed", query=query[:100], error=str(e))
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """Get indexing statistics."""
        try:
            query = """
            SELECT
                COUNT(*) AS total_files,
                COUNT(embedding) AS embedded_files,
                COUNT(DISTINCT language) AS languages,
                SUM(size_bytes) AS total_bytes,
                SUM(line_count) AS total_lines,
                MAX(last_indexed) AS last_indexed
            FROM code_index
            """

            async with self.db.session() as session:
                result = await session.execute(text(query))
                row = result.fetchone()

            # Get language breakdown
            lang_query = """
            SELECT language, COUNT(*) AS count
            FROM code_index
            GROUP BY language
            ORDER BY count DESC
            """

            async with self.db.session() as session:
                lang_result = await session.execute(text(lang_query))
                lang_rows = lang_result.fetchall()

            return {
                "total_files": row.total_files or 0,
                "embedded_files": row.embedded_files or 0,
                "languages": row.languages or 0,
                "total_bytes": row.total_bytes or 0,
                "total_lines": row.total_lines or 0,
                "last_indexed": row.last_indexed.isoformat() if row.last_indexed else None,
                "by_language": {r.language: r.count for r in lang_rows},
            }

        except Exception as e:
            self._logger.error("get_stats_failed", error=str(e))
            return {"error": str(e)}

    async def remove_stale_entries(self, repo_path: str) -> int:
        """
        Remove index entries for files that no longer exist.

        Args:
            repo_path: Repository root path

        Returns:
            Number of entries removed
        """
        try:
            # Get all indexed paths
            indexed = await self.get_indexed_hashes()

            # Check which files still exist
            repo = Path(repo_path)
            stale_paths = []

            for file_path in indexed.keys():
                full_path = repo / file_path
                if not full_path.exists():
                    stale_paths.append(file_path)

            if not stale_paths:
                return 0

            # Remove stale entries
            query = "DELETE FROM code_index WHERE file_path = ANY(:paths)"
            async with self.db.session() as session:
                await session.execute(text(query), {"paths": stale_paths})
                await session.commit()

            self._logger.info("stale_entries_removed", count=len(stale_paths))
            return len(stale_paths)

        except Exception as e:
            self._logger.error("remove_stale_failed", error=str(e))
            return 0
