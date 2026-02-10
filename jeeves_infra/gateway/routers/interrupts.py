"""Unified Interrupts Router - Single endpoint for all interrupt types.

Replaces:
- POST /confirmations (chat.py)
- POST /clarifications (chat.py)

All interrupt responses now go through:
- POST /interrupts/{id}/respond

This follows the unified interrupt system design from interrupt_unification_plan.md.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import InterruptResponse, InterruptKind, InterruptServiceProtocol

router = APIRouter(prefix="/interrupts", tags=["interrupts"])


# =============================================================================
# Request/Response Models
# =============================================================================

class InterruptResponseRequest(BaseModel):
    """Request to respond to an interrupt.

    Exactly one of these fields should be provided based on interrupt kind:
    - text: For clarification interrupts
    - approved: For confirmation interrupts (true/false)
    - decision: For critic review interrupts (approve/reject/modify)
    """
    text: Optional[str] = Field(
        None,
        description="Text response for clarification interrupts",
        max_length=10000,
    )
    approved: Optional[bool] = Field(
        None,
        description="Approval response for confirmation interrupts",
    )
    decision: Optional[str] = Field(
        None,
        description="Decision for critic review interrupts (approve/reject/modify)",
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional extensible response data",
    )


class InterruptDetail(BaseModel):
    """Interrupt details returned by API."""
    id: str
    kind: str
    request_id: str
    user_id: str
    session_id: str
    envelope_id: Optional[str] = None
    question: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    status: str
    created_at: str
    expires_at: Optional[str] = None
    resolved_at: Optional[str] = None


class InterruptRespondResponse(BaseModel):
    """Response after responding to an interrupt."""
    success: bool
    interrupt: InterruptDetail
    request_can_resume: bool = True


class InterruptListResponse(BaseModel):
    """List of interrupts."""
    interrupts: list[InterruptDetail]
    total: int


# =============================================================================
# Dependency to get InterruptService
# =============================================================================

def get_interrupt_service(request: Request) -> InterruptServiceProtocol:
    """Get the interrupt service from the application state.

    The interrupt service must be registered in app.state.interrupt_service
    by the application bootstrap. This infrastructure layer does not create
    the service directly to maintain proper layer separation.

    Raises:
        HTTPException: If interrupt service is not configured
    """
    if hasattr(request.app.state, "interrupt_service"):
        return request.app.state.interrupt_service

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Interrupt service not configured",
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{interrupt_id}", response_model=InterruptDetail)
async def get_interrupt(
    interrupt_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    service=Depends(get_interrupt_service),
):
    """Get details of a specific interrupt.

    Args:
        interrupt_id: ID of the interrupt
        user_id: User ID for authorization
    """
    _logger = get_current_logger()

    interrupt = await service.get_interrupt(interrupt_id)
    if not interrupt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interrupt not found",
        )

    # Verify user owns this interrupt
    if interrupt.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this interrupt",
        )

    return InterruptDetail(**interrupt.to_dict())


@router.post("/{interrupt_id}/respond", response_model=InterruptRespondResponse)
async def respond_to_interrupt(
    interrupt_id: str,
    body: InterruptResponseRequest,
    user_id: str = Query(..., min_length=1, max_length=255),
    service=Depends(get_interrupt_service),
):
    """Respond to an interrupt.

    This is the unified endpoint for responding to all interrupt types:
    - Clarification: Provide `text` with the clarifying information
    - Confirmation: Provide `approved` (true/false)
    - Critic review: Provide `decision` (approve/reject/modify)

    The response type must match the interrupt kind.
    """
    _logger = get_current_logger()

    # Get the interrupt to validate it exists and check kind
    interrupt = await service.get_interrupt(interrupt_id)
    if not interrupt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interrupt not found",
        )

    # Verify user owns this interrupt
    if interrupt.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to respond to this interrupt",
        )

    # Check interrupt is still pending
    if interrupt.status.value != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interrupt is not pending (status: {interrupt.status.value})",
        )

    # Build response based on provided fields
    response = InterruptResponse(
        text=body.text,
        approved=body.approved,
        decision=body.decision,
        data=body.data,
    )

    # Validate response matches interrupt kind
    kind = interrupt.kind.value
    if kind == "clarification" and body.text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clarification interrupt requires 'text' field",
        )
    if kind == "confirmation" and body.approved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation interrupt requires 'approved' field",
        )
    if kind == "agent_review" and body.decision is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent review interrupt requires 'decision' field",
        )

    # Respond to the interrupt
    resolved = await service.respond(
        interrupt_id=interrupt_id,
        response=response,
        user_id=user_id,
    )

    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve interrupt",
        )

    _logger.info(
        "interrupt_responded",
        interrupt_id=interrupt_id,
        kind=kind,
        user_id=user_id,
    )

    return InterruptRespondResponse(
        success=True,
        interrupt=InterruptDetail(**resolved.to_dict()),
        request_can_resume=True,
    )


@router.get("/", response_model=InterruptListResponse)
async def list_interrupts(
    user_id: str = Query(..., min_length=1, max_length=255),
    session_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(
        "pending",
        description="Filter by status: pending, resolved, expired, cancelled, all",
    ),
    kind: Optional[str] = Query(
        None,
        description="Filter by kind: clarification, confirmation, agent_review, etc.",
    ),
    limit: int = Query(50, ge=1, le=200),
    service=Depends(get_interrupt_service),
):
    """List interrupts for a user.

    Can filter by session_id, status, and kind.
    """
    _logger = get_current_logger()

    # Get interrupts from service
    if session_id:
        # Filter by session
        kinds = None
        if kind:
            try:
                kinds = [InterruptKind(kind)]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid interrupt kind: {kind}",
                )

        interrupts = await service.get_pending_for_session(session_id, kinds=kinds)
    else:
        # For now, we don't have a user-based query in the service
        # Return empty list if no session_id
        interrupts = []

    # Filter by status if needed
    if status_filter and status_filter != "all":
        interrupts = [
            i for i in interrupts
            if i.status.value == status_filter
        ]

    # Apply limit
    interrupts = interrupts[:limit]

    return InterruptListResponse(
        interrupts=[InterruptDetail(**i.to_dict()) for i in interrupts],
        total=len(interrupts),
    )


@router.delete("/{interrupt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_interrupt(
    interrupt_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    reason: Optional[str] = Query(None, description="Cancellation reason"),
    service=Depends(get_interrupt_service),
):
    """Cancel a pending interrupt.

    Args:
        interrupt_id: ID of the interrupt to cancel
        user_id: User ID for authorization
        reason: Optional reason for cancellation
    """
    _logger = get_current_logger()

    # Get interrupt to verify ownership
    interrupt = await service.get_interrupt(interrupt_id)
    if not interrupt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interrupt not found",
        )

    if interrupt.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this interrupt",
        )

    # Cancel the interrupt
    cancelled = await service.cancel(interrupt_id, reason=reason)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot cancel interrupt (may already be resolved)",
        )

    _logger.info(
        "interrupt_cancelled",
        interrupt_id=interrupt_id,
        user_id=user_id,
        reason=reason,
    )

    return None
