"""PostgreSQL Graph Adapter for L5 Entity Graph.

Implements GraphStorageProtocol using PostgreSQL with recursive CTEs.
This is the production adapter for L5 graph storage.

Constitutional Reference:
- Memory Module CONSTITUTION: L5 Graph - Entity relationships
- Avionics CONSTITUTION R4: Swappable Implementations
- Architecture: PostgreSQL-specific code lives in avionics (L3)

Schema Note:
    This adapter uses the rich schema defined in 001_postgres_schema.sql.
    It does NOT create tables - the SQL migration must run first.

    Schema features used:
    - Temporal validity (valid_from/valid_until) for bi-temporal queries
    - Provenance tracking (source_agent, source_event_id)
    - Edge weights and confidence scores
    - Foreign key enforcement for referential integrity

Usage:
    from avionics.database.postgres_graph import PostgresGraphAdapter

    adapter = PostgresGraphAdapter(db_client, logger)
    await adapter.ensure_tables()  # Verifies schema, creates indices

    await adapter.add_node("file:main.py", "file", {"path": "main.py"})
    await adapter.add_edge("file:main.py", "file:utils.py", "imports")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from jeeves_infra.protocols import DatabaseClientProtocol, GraphStorageProtocol, LoggerProtocol
from shared import get_component_logger


class PostgresGraphAdapter:
    """PostgreSQL adapter implementing GraphStorageProtocol.

    Uses PostgreSQL tables for nodes and edges, with recursive CTEs
    for path finding and subgraph queries.

    This adapter provides:
    - Node storage with type and properties
    - Edge storage with relationship types, weights, and confidence
    - BFS path finding via recursive CTEs
    - Subgraph expansion queries
    - Temporal validity (valid_from/valid_until) instead of soft-delete
    - Provenance tracking (source_agent, source_event_id)

    Schema Mapping:
        Protocol interface uses source_id/target_id for clarity.
        SQL schema uses from_node_id/to_node_id for graph semantics.
        This adapter maps between them transparently.
    """

    def __init__(
        self,
        db: DatabaseClientProtocol,
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize PostgreSQL graph adapter.

        Args:
            db: Database client implementing DatabaseClientProtocol
            logger: Optional logger instance
        """
        self._db = db
        self._logger = get_component_logger("PostgresGraphAdapter", logger)

    async def ensure_tables(self) -> None:
        """Verify tables exist (created by SQL migration).

        Does NOT create tables - expects 001_postgres_schema.sql to have run.
        Creates additional indices if needed for performance.
        """
        # Verify tables exist by checking for them
        try:
            await self._db.fetch_one(
                "SELECT 1 FROM graph_nodes LIMIT 1"
            )
            await self._db.fetch_one(
                "SELECT 1 FROM graph_edges LIMIT 1"
            )
        except Exception as e:
            self._logger.error(
                "graph_tables_missing",
                error=str(e),
                hint="Run 001_postgres_schema.sql migration first"
            )
            raise RuntimeError(
                "graph_nodes/graph_edges tables not found. "
                "Ensure 001_postgres_schema.sql migration has run."
            ) from e

        self._logger.info("graph_tables_verified")

    async def add_node(
        self,
        node_id: str,
        node_type: str,
        properties: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> bool:
        """Add a node to the graph.

        Args:
            node_id: Unique node identifier
            node_type: Type of node (e.g., "file", "function", "class")
            properties: Node properties/attributes (stored as label/description)
            user_id: Optional owner user ID

        Returns:
            True if created, False if already exists
        """
        # Check if node exists (not deleted)
        existing = await self._db.fetch_one(
            "SELECT node_id FROM graph_nodes WHERE node_id = $1 AND deleted_at IS NULL",
            {"node_id": node_id},
        )

        if existing:
            self._logger.debug("node_exists", node_id=node_id)
            return False

        # Extract label and description from properties if present
        label = properties.pop("label", None)
        description = properties.pop("description", None)
        ref_table = properties.pop("ref_table", None)
        ref_id = properties.pop("ref_id", None)

        # Insert or resurrect (if was soft-deleted)
        # Schema: node_id, node_type, ref_table, ref_id, label, description, user_id
        await self._db.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, ref_table, ref_id, label, description, user_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
            ON CONFLICT (node_id) DO UPDATE SET
                node_type = EXCLUDED.node_type,
                ref_table = EXCLUDED.ref_table,
                ref_id = EXCLUDED.ref_id,
                label = EXCLUDED.label,
                description = EXCLUDED.description,
                user_id = EXCLUDED.user_id,
                updated_at = NOW(),
                deleted_at = NULL
            """,
            {
                "node_id": node_id,
                "node_type": node_type,
                "ref_table": ref_table,
                "ref_id": ref_id,
                "label": label,
                "description": description,
                "user_id": user_id or "system",  # user_id is NOT NULL in schema
            },
        )

        self._logger.debug("node_added", node_id=node_id, node_type=node_type)
        return True

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an edge between nodes.

        Args:
            source_id: Source node ID (mapped to from_node_id in SQL)
            target_id: Target node ID (mapped to to_node_id in SQL)
            edge_type: Type of relationship (e.g., "imports", "calls", "inherits")
            properties: Optional edge properties including:
                - weight: Edge weight (default 1.0)
                - confidence: Confidence score (default 1.0)
                - source_agent: Agent that created the edge
                - source_event_id: Domain event that triggered creation
                - metadata: Additional JSON metadata

        Returns:
            True if created, False if already exists
        """
        props = properties or {}

        # Check if edge exists (valid_until IS NULL means currently active)
        existing = await self._db.fetch_one(
            """
            SELECT edge_id FROM graph_edges
            WHERE from_node_id = $1 AND to_node_id = $2 AND edge_type = $3 AND valid_until IS NULL
            """,
            {"from_node_id": source_id, "to_node_id": target_id, "edge_type": edge_type},
        )

        if existing:
            self._logger.debug("edge_exists", source=source_id, target=target_id)
            return False

        # Extract rich schema properties
        weight = props.pop("weight", 1.0)
        confidence = props.pop("confidence", 1.0)
        auto_generated = props.pop("auto_generated", False)
        source_agent = props.pop("source_agent", None)
        source_event_id = props.pop("source_event_id", None)
        metadata = props if props else None

        # Generate edge_id
        edge_id = f"edge_{uuid4().hex[:12]}"

        # Insert with rich schema
        # Note: UNIQUE constraint is (from_node_id, to_node_id, edge_type, valid_from)
        await self._db.execute(
            """
            INSERT INTO graph_edges (
                edge_id, from_node_id, to_node_id, edge_type,
                weight, confidence, auto_generated,
                source_agent, source_event_id,
                valid_from, metadata_json, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), $10, NOW())
            """,
            {
                "edge_id": edge_id,
                "from_node_id": source_id,
                "to_node_id": target_id,
                "edge_type": edge_type,
                "weight": weight,
                "confidence": confidence,
                "auto_generated": auto_generated,
                "source_agent": source_agent,
                "source_event_id": source_event_id,
                "metadata_json": json.dumps(metadata) if metadata else None,
            },
        )

        self._logger.debug("edge_added", source=source_id, target=target_id, edge_type=edge_type)
        return True

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a node by ID.

        Args:
            node_id: Node identifier

        Returns:
            Node data with properties, or None if not found
        """
        row = await self._db.fetch_one(
            """
            SELECT node_id, node_type, ref_table, ref_id, label, description,
                   user_id, created_at, updated_at
            FROM graph_nodes
            WHERE node_id = $1 AND deleted_at IS NULL
            """,
            {"node_id": node_id},
        )

        if not row:
            return None

        return self._row_to_node(row)

    async def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get neighboring nodes.

        Args:
            node_id: Center node ID
            edge_type: Optional filter by edge type
            direction: "in", "out", or "both"
            limit: Maximum neighbors to return

        Returns:
            List of neighbor nodes with edge information
        """
        neighbors = []

        # Outgoing neighbors (from_node_id -> to_node_id)
        if direction in ("out", "both"):
            edge_filter = "AND e.edge_type = $2" if edge_type else ""
            params = {"node_id": node_id, "edge_type": edge_type, "limit": limit} if edge_type else {"node_id": node_id, "limit": limit}

            query = f"""
                SELECT n.node_id, n.node_type, n.ref_table, n.ref_id, n.label, n.description,
                       n.user_id, n.created_at, n.updated_at,
                       e.edge_type, e.weight, e.confidence, 'out' as direction
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.to_node_id AND n.deleted_at IS NULL
                WHERE e.from_node_id = $1 AND e.valid_until IS NULL {edge_filter}
                LIMIT ${'3' if edge_type else '2'}
            """

            rows = await self._db.fetch_all(query, params)
            for row in rows:
                neighbors.append(self._row_to_neighbor(row))

        # Incoming neighbors (to_node_id <- from_node_id)
        if direction in ("in", "both"):
            edge_filter = "AND e.edge_type = $2" if edge_type else ""
            params = {"node_id": node_id, "edge_type": edge_type, "limit": limit} if edge_type else {"node_id": node_id, "limit": limit}

            query = f"""
                SELECT n.node_id, n.node_type, n.ref_table, n.ref_id, n.label, n.description,
                       n.user_id, n.created_at, n.updated_at,
                       e.edge_type, e.weight, e.confidence, 'in' as direction
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.from_node_id AND n.deleted_at IS NULL
                WHERE e.to_node_id = $1 AND e.valid_until IS NULL {edge_filter}
                LIMIT ${'3' if edge_type else '2'}
            """

            rows = await self._db.fetch_all(query, params)
            for row in rows:
                neighbors.append(self._row_to_neighbor(row))

        return neighbors[:limit]

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """Find path between two nodes using recursive CTE.

        Args:
            source_id: Start node
            target_id: End node
            max_depth: Maximum path length

        Returns:
            Path as list of nodes, or None if no path exists
        """
        # Recursive CTE for BFS path finding
        # Uses from_node_id/to_node_id from SQL schema, valid_until for temporal filtering
        query = """
            WITH RECURSIVE path_search AS (
                -- Base case: start from source
                SELECT
                    from_node_id,
                    to_node_id,
                    ARRAY[from_node_id] as path,
                    1 as depth
                FROM graph_edges
                WHERE from_node_id = $1 AND valid_until IS NULL

                UNION ALL

                -- Recursive case: expand from current frontier
                SELECT
                    e.from_node_id,
                    e.to_node_id,
                    ps.path || e.from_node_id,
                    ps.depth + 1
                FROM graph_edges e
                JOIN path_search ps ON e.from_node_id = ps.to_node_id
                WHERE e.valid_until IS NULL
                    AND e.from_node_id != ALL(ps.path)  -- Avoid cycles
                    AND ps.depth < $3
            )
            SELECT path || to_node_id as full_path
            FROM path_search
            WHERE to_node_id = $2
            ORDER BY array_length(path, 1)
            LIMIT 1
        """

        row = await self._db.fetch_one(
            query,
            {"from_node_id": source_id, "to_node_id": target_id, "max_depth": max_depth},
        )

        if not row or not row.get("full_path"):
            return None

        # Fetch full node data for each ID in path
        path = []
        for node_id in row["full_path"]:
            node = await self.get_node(node_id)
            if node:
                path.append(node)

        return path if path else None

    async def query_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        node_types: Optional[List[str]] = None,
        edge_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Query a subgraph around a center node.

        Args:
            center_id: Center node ID
            depth: Expansion depth
            node_types: Optional filter by node types
            edge_types: Optional filter by edge types

        Returns:
            Subgraph with nodes and edges
        """
        # Recursive CTE for subgraph expansion
        node_type_filter = ""
        edge_type_filter = ""

        if node_types:
            node_type_filter = f"AND n.node_type = ANY($4)"
        if edge_types:
            edge_type_filter = f"AND e.edge_type = ANY($5)"

        params: Dict[str, Any] = {
            "center_id": center_id,
            "depth": depth,
        }
        if node_types:
            params["node_types"] = node_types
        if edge_types:
            params["edge_types"] = edge_types

        # Get all reachable nodes within depth
        # Uses from_node_id/to_node_id from SQL schema, valid_until for temporal filtering
        query = f"""
            WITH RECURSIVE subgraph AS (
                -- Base case: center node
                SELECT node_id, 0 as depth
                FROM graph_nodes
                WHERE node_id = $1 AND deleted_at IS NULL

                UNION

                -- Recursive case: expand neighbors
                SELECT DISTINCT e.to_node_id as node_id, s.depth + 1
                FROM graph_edges e
                JOIN subgraph s ON e.from_node_id = s.node_id
                WHERE e.valid_until IS NULL
                    AND s.depth < $2
                    {edge_type_filter}
            )
            SELECT DISTINCT n.*
            FROM graph_nodes n
            JOIN subgraph s ON n.node_id = s.node_id
            WHERE n.deleted_at IS NULL
            {node_type_filter}
        """

        node_rows = await self._db.fetch_all(query, params)
        nodes = [self._row_to_node(row) for row in node_rows]

        # Get edges between the discovered nodes
        node_ids = [n["node_id"] for n in nodes]
        if node_ids:
            edge_params: Dict[str, Any] = {"node_ids": node_ids}
            if edge_types:
                edge_params["edge_types"] = edge_types

            edge_query = f"""
                SELECT edge_id, from_node_id, to_node_id, edge_type,
                       weight, confidence, source_agent, metadata_json
                FROM graph_edges
                WHERE from_node_id = ANY($1) AND to_node_id = ANY($1)
                    AND valid_until IS NULL
                    {edge_type_filter if edge_types else ''}
            """
            edge_rows = await self._db.fetch_all(edge_query, edge_params)
            edges = [
                {
                    "edge_id": row["edge_id"],
                    "source_id": row["from_node_id"],  # Map back to protocol naming
                    "target_id": row["to_node_id"],    # Map back to protocol naming
                    "edge_type": row["edge_type"],
                    "weight": row.get("weight", 1.0),
                    "confidence": row.get("confidence", 1.0),
                    "source_agent": row.get("source_agent"),
                    "properties": json.loads(row["metadata_json"]) if row.get("metadata_json") else {},
                }
                for row in edge_rows
            ]
        else:
            edges = []

        return {"nodes": nodes, "edges": edges}

    async def delete_node(self, node_id: str) -> bool:
        """Soft-delete a node and expire its edges.

        Args:
            node_id: Node to delete

        Returns:
            True if deleted, False if not found
        """
        now = datetime.now(timezone.utc)

        # Soft-delete the node
        result = await self._db.fetch_one(
            """
            UPDATE graph_nodes
            SET deleted_at = $2
            WHERE node_id = $1 AND deleted_at IS NULL
            RETURNING node_id
            """,
            {"node_id": node_id, "deleted_at": now},
        )

        if not result:
            return False

        # Expire all connected edges (set valid_until)
        await self._db.execute(
            """
            UPDATE graph_edges
            SET valid_until = $2
            WHERE (from_node_id = $1 OR to_node_id = $1) AND valid_until IS NULL
            """,
            {"node_id": node_id, "valid_until": now},
        )

        self._logger.info("node_deleted", node_id=node_id)
        return True

    def _row_to_node(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to node dictionary.

        Maps SQL schema columns to protocol-compatible format.
        """
        # Build properties from explicit columns
        properties = {}
        if row.get("label"):
            properties["label"] = row["label"]
        if row.get("description"):
            properties["description"] = row["description"]
        if row.get("ref_table"):
            properties["ref_table"] = row["ref_table"]
        if row.get("ref_id"):
            properties["ref_id"] = row["ref_id"]

        return {
            "node_id": row["node_id"],
            "node_type": row["node_type"],
            "properties": properties,
            "user_id": row.get("user_id"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
            "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        }

    def _row_to_neighbor(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to neighbor dictionary."""
        node = self._row_to_node(row)
        node["edge_type"] = row.get("edge_type")
        node["direction"] = row.get("direction")
        node["weight"] = row.get("weight", 1.0)
        node["confidence"] = row.get("confidence", 1.0)
        return node


# Verify protocol implementation at module load time
_: GraphStorageProtocol = PostgresGraphAdapter(None)  # type: ignore


__all__ = ["PostgresGraphAdapter"]
