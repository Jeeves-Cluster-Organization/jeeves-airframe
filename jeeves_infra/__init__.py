"""Jeeves Infrastructure Layer - Adapters above the kernel.

This package provides infrastructure implementations for the jeeves-core
microkernel. It contains the "drivers" that implement kernel protocols:

- gateway/   - HTTP/WebSocket/gRPC translation (FastAPI)
- llm/       - LLM providers (LiteLLM, OpenAI, Mock)
- postgres/  - PostgreSQL + pgvector implementations
- redis/     - Distributed state backend
- memory/    - Memory service implementations (repositories, services)
- runtime/   - Python agent/pipeline execution (LLM calls, tool execution)
- utils/     - JSON repair, string helpers, datetime utilities

Architecture:
    Capabilities (User Space)
           │
           ↓
    jeeves-infra (Kernel Modules / Drivers)  <- THIS PACKAGE
           │
           ↓
    jeeves-core (Microkernel - Go)

Usage:
    from jeeves_infra.postgres import PostgreSQLClient
    from jeeves_infra.llm import OpenAIHTTPProvider
    from jeeves_infra.gateway import create_gateway_app
    from jeeves_infra.runtime import PipelineRunner, Agent
    from jeeves_infra.kernel_client import KernelClient
    from jeeves_infra.utils import JSONRepairKit, utc_now
"""

__version__ = "1.0.0"

# Lazy imports for kernel client
def get_kernel_client():
    """Get the global kernel client for communicating with Go kernel."""
    from jeeves_infra.kernel_client import get_kernel_client as _get
    return _get()
