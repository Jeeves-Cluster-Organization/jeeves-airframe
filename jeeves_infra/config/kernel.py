"""Kernel connection configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class KernelConfig:
    """Configuration for Go kernel gRPC connection.

    Attributes:
        address: gRPC server address (host:port)
        auto_connect: Whether to auto-connect on bootstrap
        connect_timeout_ms: Connection timeout in milliseconds
        retry_attempts: Number of connection retry attempts
        default_user_id: Default user ID for auth context
        default_session_id: Default session ID for auth context
    """

    address: str = "localhost:50051"
    auto_connect: bool = True
    connect_timeout_ms: int = 5000
    retry_attempts: int = 3
    default_user_id: Optional[str] = None
    default_session_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> "KernelConfig":
        """Load configuration from environment variables.

        Environment variables:
            KERNEL_GRPC_ADDRESS: gRPC server address (default: localhost:50051)
            KERNEL_AUTO_CONNECT: Whether to auto-connect (default: true)
            KERNEL_CONNECT_TIMEOUT_MS: Connection timeout (default: 5000)
            KERNEL_RETRY_ATTEMPTS: Number of retries (default: 3)
            KERNEL_DEFAULT_USER_ID: Default user ID (optional)
            KERNEL_DEFAULT_SESSION_ID: Default session ID (optional)

        Returns:
            KernelConfig instance populated from environment
        """
        return cls(
            address=os.getenv("KERNEL_GRPC_ADDRESS", "localhost:50051"),
            auto_connect=os.getenv("KERNEL_AUTO_CONNECT", "true").lower() == "true",
            connect_timeout_ms=int(os.getenv("KERNEL_CONNECT_TIMEOUT_MS", "5000")),
            retry_attempts=int(os.getenv("KERNEL_RETRY_ATTEMPTS", "3")),
            default_user_id=os.getenv("KERNEL_DEFAULT_USER_ID"),
            default_session_id=os.getenv("KERNEL_DEFAULT_SESSION_ID"),
        )

    @classmethod
    def disabled(cls) -> "KernelConfig":
        """Create a config with auto-connect disabled.

        Useful for testing or when kernel is not available.
        """
        return cls(auto_connect=False)
