"""
Centralized prompt registry for mission system agents.

Constitutional Alignment:
- P6: Observable (version tracking, logging)
- P5: Deterministic Spine (prompts are contracts at LLM boundary)
"""

from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from jeeves_infra.logging import get_current_logger


@dataclass
class PromptVersion:
    """A versioned prompt template."""
    name: str
    version: str
    template: str
    created_at: datetime
    description: str
    constitutional_compliance: str  # Which principles this prompt addresses


class PromptRegistry:
    """
    Central registry for all LLM prompts.

    Usage:
        registry = PromptRegistry.get_instance()
        prompt = registry.get("planner.tool_selection", version="1.0")
    """

    _instance: Optional['PromptRegistry'] = None
    _prompts: Dict[str, Dict[str, PromptVersion]] = {}

    @classmethod
    def get_instance(cls) -> 'PromptRegistry':
        if cls._instance is None:
            cls._instance = cls()
            # Auto-import GENERIC prompt versions (not capability-specific)
            # Capability-specific prompts are registered via CapabilityResourceRegistry
            # at application startup, not via hardcoded imports.
            generic_prompt_modules = [
                "mission_system.prompts.core.versions.intent",
                "mission_system.prompts.core.versions.planner",
                "mission_system.prompts.core.versions.confirmation",
                "mission_system.prompts.core.versions.critic",
            ]
            for module_name in generic_prompt_modules:
                try:
                    __import__(module_name)
                except (ImportError, FileNotFoundError) as e:
                    get_current_logger().warning(
                        "prompt_module_import_failed",
                        module=module_name,
                        error=str(e)
                    )
        return cls._instance

    def register(self, prompt_version: PromptVersion) -> None:
        """Register a prompt version."""
        _logger = get_current_logger()
        if prompt_version.name not in self._prompts:
            self._prompts[prompt_version.name] = {}

        self._prompts[prompt_version.name][prompt_version.version] = prompt_version

        _logger.info(
            "prompt_registered",
            name=prompt_version.name,
            version=prompt_version.version,
            compliance=prompt_version.constitutional_compliance
        )

    def get(
        self,
        name: str,
        version: str = "latest",
        context: Optional[Dict] = None
    ) -> str:
        """
        Get a prompt by name and version.

        Args:
            name: Prompt name (e.g., "planner.tool_selection")
            version: Version string or "latest"
            context: Variables to interpolate into template

        Returns:
            Rendered prompt string
        """
        if name not in self._prompts:
            raise ValueError(f"Prompt '{name}' not registered")

        versions = self._prompts[name]

        if version == "latest":
            # Get most recent version
            version = max(versions.keys())

        if version not in versions:
            raise ValueError(f"Version '{version}' not found for prompt '{name}'")

        prompt_version = versions[version]

        # Log usage for observability (P6)
        get_current_logger().debug(
            "prompt_retrieved",
            name=name,
            version=version,
            has_context=context is not None
        )

        # Render template with context
        if context:
            return prompt_version.template.format(**context)
        return prompt_version.template

    def list_prompts(self) -> Dict[str, list]:
        """List all registered prompts and their versions."""
        return {
            name: list(versions.keys())
            for name, versions in self._prompts.items()
        }


# Decorator for easy registration
def register_prompt(
    name: str,
    version: str,
    description: str,
    constitutional_compliance: str
):
    """Decorator to register a prompt."""
    def decorator(func: Callable[[], str]) -> Callable[[], str]:
        template = func()
        prompt_version = PromptVersion(
            name=name,
            version=version,
            template=template,
            created_at=datetime.now(),
            description=description,
            constitutional_compliance=constitutional_compliance
        )
        PromptRegistry.get_instance().register(prompt_version)
        return func
    return decorator
