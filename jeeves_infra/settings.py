"""Infrastructure settings for jeeves_infra.

Constitutional Reference:
    - Infrastructure R3: No Domain Logic - infrastructure provides transport, not business logic
    - Infrastructure R2: Configuration Over Code - all behavior is configurable
    - docs/CONSTITUTION.md: PostgreSQL with pgvector is the ONLY supported backend

Per-Agent Configuration:
    Agent-specific LLM settings (model, temperature, server_url) are now owned by
    capabilities and registered via DomainLLMRegistry. This file contains
    only generic infrastructure configuration.

    See: jeeves-capability-*/config/llm_config.py (for capability registration)
"""

import re
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, TYPE_CHECKING

# URL pattern for HTTP/HTTPS endpoints
_URL_PATTERN = re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE)

if TYPE_CHECKING:
    from jeeves_infra.feature_flags import FeatureFlags
    from jeeves_infra.protocols import LoggerProtocol


class Settings(BaseSettings):
    """Infrastructure settings.

    Contains only generic infrastructure configuration. Agent-specific
    LLM settings are owned by capabilities via DomainLLMRegistry.

    Constitutional Reference:
        - Infrastructure R3: No Domain Logic
        - Capability Constitution R6: Domain Config Ownership
    """

    # =========================================================================
    # DEPLOYMENT CONFIGURATION
    # =========================================================================
    deployment_mode: str = "single_node"  # Options: single_node | distributed

    # =========================================================================
    # LLM PROVIDER CONFIGURATION (Generic defaults)
    # =========================================================================
    # Supported providers:
    #   "llamaserver" (local, llama.cpp server with OpenAI-compatible API)
    #   "llamacpp" (local, C++ high-performance, in-process)
    #   "openai" (GPT-4/3.5)
    #   "anthropic" (Claude)
    #   "azure" (Azure AI Foundry)
    #   "mock" (testing)
    llm_provider: str = "llamaserver"  # Default provider

    # llama-server default endpoint
    llamaserver_host: str = "http://localhost:8080"
    llamaserver_api_type: str = "native"  # "native" or "openai"

    # Default model (used when capability doesn't specify)
    default_model: str = "qwen2.5-7b-instruct-q4_k_m"

    # Default temperature (used when capability doesn't specify)
    default_temperature: Optional[float] = 0.3

    # Temperature feature toggle
    disable_temperature: bool = False

    # OpenAI API Configuration
    openai_api_key: Optional[str] = None

    # Anthropic API Configuration
    anthropic_api_key: Optional[str] = None

    # Azure AI Foundry Configuration
    azure_endpoint: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_deployment_name: Optional[str] = None
    azure_api_version: str = "2024-02-01"

    # llama.cpp Configuration (in-process)
    llamacpp_model_path: str = "./models/llama-3.1-8b-q4_0.gguf"
    llamacpp_n_ctx: int = 4096
    llamacpp_n_gpu_layers: int = 0
    llamacpp_n_threads: Optional[int] = None

    # =========================================================================
    # NEUTRAL LLM CONFIGURATION (preferred over legacy vars)
    # =========================================================================
    # These are the canonical environment variables for LLM configuration.
    # Legacy vars (LITELLM_*, LLAMASERVER_*) are still supported for
    # backwards compatibility but new deployments should use JEEVES_LLM_*.
    jeeves_llm_adapter: Optional[str] = Field(
        default=None,
        description="LLM adapter: openai_http, litellm, mock"
    )
    jeeves_llm_base_url: Optional[str] = Field(
        default=None,
        description="LLM API base URL (e.g., http://localhost:8080/v1)"
    )
    jeeves_llm_model: Optional[str] = Field(
        default=None,
        description="LLM model identifier"
    )
    jeeves_llm_api_key: Optional[str] = Field(
        default=None,
        description="LLM API key"
    )

    # =========================================================================
    # TIMEOUTS AND RETRIES
    # =========================================================================
    # LLM timeout increased to 300s (5 min) for large max_tokens generations
    # With max_tokens=8000, llama-server needs more time to generate responses
    llm_timeout: int = Field(default=300, ge=1, le=600)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    executor_timeout: int = Field(default=60, ge=1, le=600)

    # =========================================================================
    # MEMORY CONFIGURATION
    # =========================================================================
    memory_enabled: bool = True
    memory_intent_classification: bool = True
    memory_auto_crossref: bool = True

    # =========================================================================
    # VECTOR DB CONFIGURATION (pgvector only)
    # =========================================================================
    vector_db_enabled: bool = True
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_batch_size: int = 32
    embedding_cache_size: int = 1000

    # =========================================================================
    # SEARCH CONFIGURATION
    # =========================================================================
    search_default_limit: int = 10
    search_semantic_weight: float = 0.6
    search_min_similarity: float = 0.5

    # =========================================================================
    # CROSS-REFERENCE CONFIGURATION
    # =========================================================================
    crossref_auto_extract: bool = True
    crossref_min_confidence: float = 0.7

    # =========================================================================
    # API CONFIGURATION
    # =========================================================================
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_reload: bool = False

    # =========================================================================
    # RATE LIMITING
    # =========================================================================
    requests_per_minute: int = Field(default=60, ge=1, le=10000)
    rate_limit_interval_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)

    # =========================================================================
    # WEBSOCKET CONFIGURATION
    # =========================================================================
    websocket_auth_token: str = "local-dev-token"
    websocket_auth_required: bool = False
    websocket_heartbeat_interval: float = Field(default=30.0, ge=1.0, le=300.0)
    websocket_idle_timeout: float = Field(default=120.0, ge=10.0, le=3600.0)

    # =========================================================================
    # LOGGING
    # =========================================================================
    log_level: str = "INFO"

    # =========================================================================
    # CONFIRMATION FEATURE
    # =========================================================================
    enable_confirmations: bool = False
    confirmation_timeout_seconds: int = Field(default=300, ge=10, le=3600)
    confirmation_required_operations: Optional[List[str]] = None
    skip_confirmation_for_single_item: bool = False

    # =========================================================================
    # CHAT UI INTEGRATION
    # =========================================================================
    chat_enabled: bool = True

    # =========================================================================
    # POSTGRESQL CONFIGURATION (the ONLY supported backend)
    # =========================================================================
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_database: str = "assistant"
    postgres_user: str = "assistant"
    postgres_password: str = ""
    postgres_pool_size: int = Field(default=20, ge=1, le=100)
    postgres_max_overflow: int = Field(default=10, ge=0, le=100)
    postgres_pool_timeout: int = Field(default=30, ge=1, le=300)
    postgres_pool_recycle: int = Field(default=3600, ge=60, le=86400)

    # pgvector dimension
    pgvector_dimension: int = Field(default=384, ge=1, le=4096)

    # =========================================================================
    # REDIS CONFIGURATION (for distributed mode)
    # =========================================================================
    redis_url: str = "redis://localhost:6379"
    redis_pool_size: int = Field(default=10, ge=1, le=100)

    # =========================================================================
    # CHECKPOINT CONFIGURATION (Amendment XXIII)
    # =========================================================================
    checkpoint_enabled: bool = True
    checkpoint_retention_days: int = Field(default=7, ge=1, le=365)
    checkpoint_max_per_envelope: int = Field(default=100, ge=1, le=1000)

    # =========================================================================
    # DISTRIBUTED CONFIGURATION (Amendment XXIV)
    # =========================================================================
    distributed_enabled: bool = False
    worker_queues: Optional[List[str]] = None
    worker_max_concurrent: int = Field(default=5, ge=1, le=100)
    worker_heartbeat_seconds: int = Field(default=30, ge=5, le=300)
    worker_task_timeout: int = Field(default=300, ge=10, le=3600)

    # =========================================================================
    # MCP/A2A INTEROPERABILITY (Amendment XXV)
    # =========================================================================
    mcp_enabled: bool = False
    mcp_port: int = Field(default=8081, ge=1, le=65535)
    a2a_enabled: bool = False
    a2a_registry_url: Optional[str] = None
    a2a_agent_endpoint: Optional[str] = None

    # =========================================================================
    # VALIDATORS
    # =========================================================================
    @field_validator(
        'llamaserver_host',
        'azure_endpoint',
        'a2a_registry_url',
        'a2a_agent_endpoint',
        mode='after'
    )
    @classmethod
    def validate_http_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate that URL fields contain valid HTTP/HTTPS URLs."""
        if v is None:
            return v
        if not _URL_PATTERN.match(v):
            raise ValueError(f"Invalid URL format: {v}. Must be http:// or https://")
        return v

    @field_validator('redis_url', mode='after')
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate Redis URL format."""
        if not v.startswith(('redis://', 'rediss://')):
            raise ValueError(f"Invalid Redis URL: {v}. Must start with redis:// or rediss://")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    def get_feature_flags(self) -> 'FeatureFlags':
        """Get feature flags instance."""
        from jeeves_infra.feature_flags import get_feature_flags
        return get_feature_flags()

    def get_postgres_url(self) -> str:
        """Build PostgreSQL connection URL for asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )

    def get_database_url(self) -> str:
        """Get the database URL."""
        return self.get_postgres_url()

    def is_postgres(self) -> bool:
        return True

    def is_pgvector_enabled(self) -> bool:
        return True

    @property
    def database_backend(self) -> str:
        return "postgres"

    @property
    def vector_backend(self) -> str:
        return "pgvector"

    def log_llm_config(self, logger: "LoggerProtocol") -> None:
        """Log current LLM configuration.

        Note: Agent-specific configurations are logged by the capability
        registry, not here. This logs only infrastructure defaults.
        """
        logger.info(
            "llm_infrastructure_config",
            default_provider=self.llm_provider,
            default_host=self.llamaserver_host,
            default_model=self.default_model,
            default_temperature=self.default_temperature,
        )


# =============================================================================
# GLOBAL SETTINGS (Lazy Initialization)
# =============================================================================

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get global settings instance.

    Creates a new Settings instance lazily if none exists.
    Prefer dependency injection over this global getter for testability.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings_instance: Settings) -> None:
    """Set the global settings instance.

    Use at bootstrap time to inject a pre-configured Settings instance.
    Primarily for testing purposes.
    """
    global _settings
    _settings = settings_instance


def reset_settings() -> None:
    """Reset the global settings instance.

    Forces re-creation on next get_settings() call.
    Primarily for testing purposes.
    """
    global _settings
    _settings = None


def reload_settings() -> Settings:
    """Reload settings from environment.

    This creates a new Settings instance using current environment variables.
    """
    global _settings
    _settings = Settings()
    return _settings


# Singleton proxy for convenient access
class _SettingsProxy:
    """Lazy proxy for settings singleton."""

    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
