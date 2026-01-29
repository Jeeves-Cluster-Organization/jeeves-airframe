"""In-Memory Skill Storage Stub for L6 Skills/Patterns.

Provides a simple in-memory implementation of SkillStorageProtocol
for development and testing. Production implementations should persist
skills to a database.

Constitutional Reference:
- Memory Module CONSTITUTION: L6 Skills - Learned patterns (not yet implemented)
- protocols.SkillStorageProtocol: Extensible interface

Skills are learned patterns that help the system improve over time:
- Tool usage patterns (what worked before)
- Code generation templates
- User preference learning
- Successful prompt patterns

Extension Points:
- Subclass and override methods for different backends
- Replace with adapter for database persistence
- Add ML-based skill extraction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jeeves_infra.protocols import SkillStorageProtocol, LoggerProtocol
from jeeves_infra.logging import get_component_logger


@dataclass
class Skill:
    """In-memory skill representation."""
    skill_id: str
    skill_type: str
    pattern: Dict[str, Any]
    source_context: Optional[Dict[str, Any]] = None
    confidence: float = 0.5
    user_id: Optional[str] = None
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None


@dataclass
class SkillUsage:
    """Record of skill usage."""
    skill_id: str
    success: bool
    context: Optional[Dict[str, Any]]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class InMemorySkillStorage:
    """In-memory implementation of SkillStorageProtocol.

    This is a stub implementation for development and testing.
    For production, implement a proper database adapter.

    Extension Points:
    - Override _persist_skill() for custom persistence
    - Override _load_skills() for startup hydration
    - Override _match_context() for custom relevance matching
    """

    def __init__(
        self,
        logger: Optional[LoggerProtocol] = None,
        min_confidence_decay: float = 0.1,
        max_confidence: float = 1.0,
    ):
        """Initialize in-memory skill storage.

        Args:
            logger: Optional logger instance
            min_confidence_decay: Minimum confidence after decay
            max_confidence: Maximum confidence after boost
        """
        self._logger = get_component_logger("InMemorySkillStorage", logger)
        self._skills: Dict[str, Skill] = {}
        self._usage_history: List[SkillUsage] = []
        self._min_confidence_decay = min_confidence_decay
        self._max_confidence = max_confidence

    async def store_skill(
        self,
        skill_id: str,
        skill_type: str,
        pattern: Dict[str, Any],
        source_context: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        user_id: Optional[str] = None,
    ) -> str:
        """Store a learned skill/pattern."""
        if skill_id in self._skills:
            # Update existing skill
            skill = self._skills[skill_id]
            skill.pattern = pattern
            skill.confidence = confidence
            skill.updated_at = datetime.now(timezone.utc)
            self._logger.debug("skill_updated", skill_id=skill_id)
        else:
            # Create new skill
            skill = Skill(
                skill_id=skill_id,
                skill_type=skill_type,
                pattern=pattern,
                source_context=source_context,
                confidence=confidence,
                user_id=user_id,
            )
            self._skills[skill_id] = skill
            self._logger.debug("skill_created", skill_id=skill_id, skill_type=skill_type)

        # Extension point: persist to backend
        await self._persist_skill(skill)

        return skill_id

    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get a skill by ID."""
        skill = self._skills.get(skill_id)
        if skill is None:
            return None

        return self._skill_to_dict(skill)

    async def find_skills(
        self,
        skill_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find relevant skills."""
        results: List[Skill] = []

        for skill in self._skills.values():
            # Filter by type
            if skill_type and skill.skill_type != skill_type:
                continue

            # Filter by confidence
            if skill.confidence < min_confidence:
                continue

            # Filter by user
            if user_id and skill.user_id and skill.user_id != user_id:
                continue

            # Context matching (extension point)
            if context:
                relevance = await self._match_context(skill, context)
                if relevance <= 0:
                    continue

            results.append(skill)

        # Sort by confidence (descending)
        results.sort(key=lambda s: s.confidence, reverse=True)

        return [self._skill_to_dict(s) for s in results[:limit]]

    async def update_confidence(
        self,
        skill_id: str,
        delta: float,
        reason: Optional[str] = None,
    ) -> float:
        """Update skill confidence based on outcome."""
        skill = self._skills.get(skill_id)
        if skill is None:
            return 0.0

        old_confidence = skill.confidence
        new_confidence = max(
            self._min_confidence_decay,
            min(self._max_confidence, skill.confidence + delta),
        )
        skill.confidence = new_confidence
        skill.updated_at = datetime.now(timezone.utc)

        self._logger.debug(
            "skill_confidence_updated",
            skill_id=skill_id,
            old=old_confidence,
            new=new_confidence,
            delta=delta,
            reason=reason,
        )

        # Extension point: persist update
        await self._persist_skill(skill)

        return new_confidence

    async def record_usage(
        self,
        skill_id: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record skill usage for learning."""
        skill = self._skills.get(skill_id)
        if skill is None:
            return

        # Update usage stats
        skill.usage_count += 1
        if success:
            skill.success_count += 1
        else:
            skill.failure_count += 1
        skill.last_used_at = datetime.now(timezone.utc)

        # Adjust confidence based on outcome
        delta = 0.05 if success else -0.1
        await self.update_confidence(skill_id, delta, "usage_feedback")

        # Record in history
        usage = SkillUsage(
            skill_id=skill_id,
            success=success,
            context=context,
        )
        self._usage_history.append(usage)

        self._logger.debug(
            "skill_usage_recorded",
            skill_id=skill_id,
            success=success,
            usage_count=skill.usage_count,
        )

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill."""
        if skill_id not in self._skills:
            return False

        del self._skills[skill_id]
        self._logger.debug("skill_deleted", skill_id=skill_id)
        return True

    async def get_skill_stats(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get usage statistics for a skill."""
        skill = self._skills.get(skill_id)
        if skill is None:
            return None

        success_rate = (
            skill.success_count / skill.usage_count
            if skill.usage_count > 0
            else 0.0
        )

        return {
            "skill_id": skill_id,
            "usage_count": skill.usage_count,
            "success_count": skill.success_count,
            "failure_count": skill.failure_count,
            "success_rate": success_rate,
            "confidence": skill.confidence,
            "created_at": skill.created_at.isoformat(),
            "last_used_at": skill.last_used_at.isoformat() if skill.last_used_at else None,
        }

    # =========================================================================
    # Extension Points
    # =========================================================================

    async def _persist_skill(self, skill: Skill) -> None:
        """Extension point: persist skill to backend.

        Override this in subclasses to persist to database.
        """
        pass

    async def _load_skills(self) -> None:
        """Extension point: load skills from backend on startup.

        Override this in subclasses to hydrate from database.
        """
        pass

    async def _match_context(
        self,
        skill: Skill,
        context: Dict[str, Any],
    ) -> float:
        """Extension point: match skill to context.

        Override this for custom relevance matching (e.g., semantic similarity).

        Args:
            skill: The skill to match
            context: Current context

        Returns:
            Relevance score (0.0 to 1.0), 0 means no match
        """
        # Default: simple key overlap matching
        if skill.source_context is None:
            return 0.5  # Neutral relevance

        skill_keys = set(skill.source_context.keys())
        context_keys = set(context.keys())
        overlap = len(skill_keys & context_keys)
        total = len(skill_keys | context_keys)

        return overlap / total if total > 0 else 0.0

    # =========================================================================
    # Helpers
    # =========================================================================

    def _skill_to_dict(self, skill: Skill) -> Dict[str, Any]:
        """Convert skill to dictionary."""
        return {
            "skill_id": skill.skill_id,
            "skill_type": skill.skill_type,
            "pattern": skill.pattern,
            "source_context": skill.source_context,
            "confidence": skill.confidence,
            "user_id": skill.user_id,
            "usage_count": skill.usage_count,
            "success_count": skill.success_count,
            "failure_count": skill.failure_count,
            "created_at": skill.created_at.isoformat(),
            "updated_at": skill.updated_at.isoformat(),
            "last_used_at": skill.last_used_at.isoformat() if skill.last_used_at else None,
        }

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get skill storage statistics."""
        total_usage = sum(s.usage_count for s in self._skills.values())
        avg_confidence = (
            sum(s.confidence for s in self._skills.values()) / len(self._skills)
            if self._skills
            else 0.0
        )

        return {
            "skill_count": len(self._skills),
            "total_usage": total_usage,
            "average_confidence": avg_confidence,
            "usage_history_size": len(self._usage_history),
        }


# Verify protocol implementation
_: SkillStorageProtocol = InMemorySkillStorage()


__all__ = [
    "InMemorySkillStorage",
    "Skill",
    "SkillUsage",
]
