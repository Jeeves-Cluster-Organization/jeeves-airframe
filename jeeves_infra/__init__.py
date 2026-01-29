"""Jeeves Infrastructure Layer (L1) - Adapters above the kernel.

This package provides infrastructure implementations for the jeeves-core
microkernel. It contains the "drivers" that implement kernel protocols:

- llm/           - LLM providers (LiteLLM, OpenAI, Mock)
- postgres/      - PostgreSQL + pgvector implementations
- redis/         - Distributed state backend
- memory/        - Memory service implementations (repositories, services)
- runtime/       - Python agent/pipeline execution (LLM calls, tool execution)
- kernel_client/ - gRPC client for Go kernel (CommBus, Process, Scheduler)
- utils/         - JSON repair, string helpers, datetime utilities

Note: gateway/ has moved to mission_system.gateway (L2 orchestration layer)

Architecture (Agentic OS):
    L3: Capabilities (User Space)
           │
           ↓
    L2: mission_system (Orchestration) - gateway, bootstrap, services
           │
           ↓
    L1: jeeves_infra (Infrastructure)  <- THIS PACKAGE
           │
           ↓
    L0: jeeves-core (Go Kernel)

Usage:
    from jeeves_infra.postgres import PostgreSQLClient
    from jeeves_infra.llm import OpenAIHTTPProvider
    from jeeves_infra.runtime import PipelineRunner, Agent
    from jeeves_infra.kernel_client import KernelClient, get_commbus
    from jeeves_infra.utils import JSONRepairKit, utc_now

    # Gateway moved to L2 orchestration layer:
    # >>> from mission_system.gateway import create_gateway_app
"""

__version__ = "1.0.0"

# Lazy imports for kernel client
def get_kernel_client():
    """Get the global kernel client for communicating with Go kernel."""
    from jeeves_infra.kernel_client import get_kernel_client as _get
    return _get()
