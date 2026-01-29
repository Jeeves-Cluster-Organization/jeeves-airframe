"""In-Memory Graph Storage Stub for L5 Entity Graph.

Provides a simple in-memory implementation of GraphStorageProtocol
for development and testing. Production implementations should use
a proper graph database (Neo4j, etc.) or PostgreSQL with recursive CTEs.

Constitutional Reference:
- Memory Module CONSTITUTION: L5 Graph - Entity relationships
- protocols.GraphStorageProtocol: Extensible interface

Extension Points:
- Subclass and override methods for different backends
- Replace with adapter for graph databases
- Use factory pattern for backend selection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from jeeves_infra.protocols import GraphStorageProtocol, LoggerProtocol
from shared import get_component_logger


@dataclass
class GraphNode:
    """In-memory graph node."""
    node_id: str
    node_type: str
    properties: Dict[str, Any]
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GraphEdge:
    """In-memory graph edge."""
    source_id: str
    target_id: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    confidence: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemoryGraphStorage:
    """In-memory implementation of GraphStorageProtocol.

    This is a stub implementation for development and testing.
    For production, implement a proper adapter for your graph database.

    Extension Points:
    - Override _persist_node() for custom persistence
    - Override _persist_edge() for custom persistence
    - Override _load_graph() for startup hydration
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        """Initialize in-memory graph storage.

        Args:
            logger: Optional logger instance
        """
        self._logger = get_component_logger("InMemoryGraphStorage", logger)
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}  # (source, target, type)
        self._outgoing: Dict[str, Set[Tuple[str, str]]] = {}  # node_id -> [(target, type)]
        self._incoming: Dict[str, Set[Tuple[str, str]]] = {}  # node_id -> [(source, type)]

    async def add_node(
        self,
        node_id: str,
        node_type: str,
        properties: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> bool:
        """Add a node to the graph."""
        if node_id in self._nodes:
            self._logger.debug("node_exists", node_id=node_id)
            return False

        node = GraphNode(
            node_id=node_id,
            node_type=node_type,
            properties=properties,
            user_id=user_id,
        )
        self._nodes[node_id] = node

        # Initialize edge sets
        self._outgoing[node_id] = set()
        self._incoming[node_id] = set()

        # Extension point: persist to backend
        await self._persist_node(node)

        self._logger.debug(
            "node_added",
            node_id=node_id,
            node_type=node_type,
        )
        return True

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an edge between nodes."""
        key = (source_id, target_id, edge_type)
        if key in self._edges:
            self._logger.debug("edge_exists", source=source_id, target=target_id)
            return False

        # Verify nodes exist
        if source_id not in self._nodes or target_id not in self._nodes:
            self._logger.warning(
                "edge_missing_node",
                source=source_id,
                target=target_id,
            )
            return False

        # Extract weight/confidence from properties if present
        props = dict(properties) if properties else {}
        weight = props.pop("weight", 1.0)
        confidence = props.pop("confidence", 1.0)

        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=props,
            weight=weight,
            confidence=confidence,
        )
        self._edges[key] = edge

        # Update adjacency
        self._outgoing[source_id].add((target_id, edge_type))
        self._incoming[target_id].add((source_id, edge_type))

        # Extension point: persist to backend
        await self._persist_edge(edge)

        self._logger.debug(
            "edge_added",
            source=source_id,
            target=target_id,
            edge_type=edge_type,
        )
        return True

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a node by ID."""
        node = self._nodes.get(node_id)
        if node is None:
            return None

        return {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "properties": node.properties,
            "user_id": node.user_id,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
        }

    async def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get neighboring nodes."""
        if node_id not in self._nodes:
            return []

        neighbors: List[Dict[str, Any]] = []

        # Outgoing neighbors
        if direction in ("out", "both"):
            for target_id, etype in self._outgoing.get(node_id, set()):
                if edge_type and etype != edge_type:
                    continue
                node = await self.get_node(target_id)
                if node:
                    edge = self._edges.get((node_id, target_id, etype))
                    neighbors.append({
                        **node,
                        "edge_type": etype,
                        "direction": "out",
                        "weight": edge.weight if edge else 1.0,
                        "confidence": edge.confidence if edge else 1.0,
                    })

        # Incoming neighbors
        if direction in ("in", "both"):
            for source_id, etype in self._incoming.get(node_id, set()):
                if edge_type and etype != edge_type:
                    continue
                node = await self.get_node(source_id)
                if node:
                    edge = self._edges.get((source_id, node_id, etype))
                    neighbors.append({
                        **node,
                        "edge_type": etype,
                        "direction": "in",
                        "weight": edge.weight if edge else 1.0,
                        "confidence": edge.confidence if edge else 1.0,
                    })

        return neighbors[:limit]

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """Find path between two nodes using BFS."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        if source_id == target_id:
            node = await self.get_node(source_id)
            return [node] if node else None

        # BFS
        visited: Set[str] = {source_id}
        queue: List[Tuple[str, List[str]]] = [(source_id, [source_id])]

        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue

            for neighbor_id, _ in self._outgoing.get(current, set()):
                if neighbor_id == target_id:
                    # Found path
                    full_path = path + [neighbor_id]
                    result = []
                    for nid in full_path:
                        node = await self.get_node(nid)
                        if node:
                            result.append(node)
                    return result

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_id]))

        return None

    async def query_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        node_types: Optional[List[str]] = None,
        edge_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Query a subgraph around a center node."""
        if center_id not in self._nodes:
            return {"nodes": [], "edges": []}

        visited: Set[str] = set()
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        # BFS expansion
        queue: List[Tuple[str, int]] = [(center_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)

            if current_id in visited:
                continue
            visited.add(current_id)

            node = self._nodes.get(current_id)
            if node is None:
                continue

            # Filter by node type
            if node_types and node.node_type not in node_types:
                continue

            nodes.append(await self.get_node(current_id))

            if current_depth >= depth:
                continue

            # Expand neighbors
            for neighbor_id, etype in self._outgoing.get(current_id, set()):
                if edge_types and etype not in edge_types:
                    continue
                edge = self._edges.get((current_id, neighbor_id, etype))
                edges.append({
                    "source_id": current_id,
                    "target_id": neighbor_id,
                    "edge_type": etype,
                    "weight": edge.weight if edge else 1.0,
                    "confidence": edge.confidence if edge else 1.0,
                })
                if neighbor_id not in visited:
                    queue.append((neighbor_id, current_depth + 1))

        return {"nodes": nodes, "edges": edges}

    async def delete_node(self, node_id: str) -> bool:
        """Delete a node and its edges."""
        if node_id not in self._nodes:
            return False

        # Remove all edges involving this node
        edges_to_remove = []
        for key in self._edges:
            if key[0] == node_id or key[1] == node_id:
                edges_to_remove.append(key)

        for key in edges_to_remove:
            del self._edges[key]

        # Update adjacency
        for target_id, _ in self._outgoing.get(node_id, set()):
            self._incoming[target_id].discard((node_id, _))
        for source_id, _ in self._incoming.get(node_id, set()):
            self._outgoing[source_id].discard((node_id, _))

        del self._nodes[node_id]
        del self._outgoing[node_id]
        del self._incoming[node_id]

        self._logger.debug("node_deleted", node_id=node_id)
        return True

    # =========================================================================
    # Extension Points
    # =========================================================================

    async def _persist_node(self, node: GraphNode) -> None:
        """Extension point: persist node to backend.

        Override this in subclasses to persist to database.
        """
        pass

    async def _persist_edge(self, edge: GraphEdge) -> None:
        """Extension point: persist edge to backend.

        Override this in subclasses to persist to database.
        """
        pass

    async def _load_graph(self) -> None:
        """Extension point: load graph from backend on startup.

        Override this in subclasses to hydrate from database.
        """
        pass

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, int]:
        """Get graph statistics."""
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
        }


# Verify protocol implementation
_: GraphStorageProtocol = InMemoryGraphStorage()


__all__ = [
    "InMemoryGraphStorage",
    "GraphNode",
    "GraphEdge",
]
