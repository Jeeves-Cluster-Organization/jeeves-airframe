"""Jeeves Infrastructure & Orchestration Framework.

This package provides infrastructure abstractions, orchestration framework,
and protocol-based plumbing for the jeeves-core microkernel. Concrete database
implementations are owned by capabilities and registered via the backend registry.

Sub-packages:
- gateway/       - HTTP/WebSocket/gRPC translation (FastAPI)
- llm/           - LLM providers (LiteLLM, OpenAI, Mock)
- database/      - Protocol-based database factory and registry
- redis/         - Distributed state backend
- memory/        - Memory handlers, messages, tool metrics/health
- runtime/       - Python agent/pipeline execution (LLM calls, tool execution)
- config/        - Agent profiles, registry, constants
- orchestrator/  - Event context, governance, flow, vertical service
- events/        - Event bridge for kernel <-> gateway
- services/      - Debug API
- verticals/     - Generic vertical registry
- utils/         - JSON repair, string helpers, prompt builder

Top-level modules:
- bootstrap      - AppContext creation, composition root
- health         - Kubernetes liveness/readiness probes
- capability_wiring - Registration, discovery, router mounting

Architecture:
    Capabilities (User Space) - own concrete DB, prompts, tools, agents
           |
           v
    jeeves-infra (Infrastructure + Orchestration)  <- THIS PACKAGE
           |
           v
    jeeves-core (Microkernel - Rust)

Usage:
    from jeeves_infra.protocols import PipelineConfig, AgentConfig, Envelope
    from jeeves_infra.wiring import create_llm_provider_factory, create_tool_executor
    from jeeves_infra.bootstrap import create_app_context
    from jeeves_infra.kernel_client import KernelClient
    from jeeves_infra.settings import get_settings
"""

__version__ = "1.0.0"

# Lazy imports for kernel client
def get_kernel_client():
    """Get the global kernel client for communicating with Rust kernel."""
    from jeeves_infra.kernel_client import get_kernel_client as _get
    return _get()
