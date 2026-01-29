"""Webhook Service for async event delivery.

Provides webhook subscription and delivery for the event system.
Webhooks are delivered asynchronously with retry logic.

Features:
- HMAC signature for payload verification
- Exponential backoff retry
- Delivery queue for reliability
- Scoped subscriptions (per-request or global)

Usage:
    service = WebhookService(logger)

    # Register webhook for a request
    config = WebhookConfig(
        url="https://example.com/webhook",
        events=["request.completed"],
        secret="hmac-secret",
    )
    service.register("request-123", config)

    # Emit event (will trigger webhook delivery)
    await service.emit_event("request.completed", {
        "request_id": "request-123",
        "status": "success",
    })

Constitutional Reference: Avionics layer (infrastructure)
"""

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import threading

from jeeves_infra.protocols import LoggerProtocol

# Optional aiohttp for HTTP delivery
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class DeliveryStatus(str, Enum):
    """Webhook delivery status."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookConfig:
    """Configuration for a webhook endpoint.

    Attributes:
        url: HTTP(S) endpoint URL
        events: List of event types to subscribe to (e.g., ["request.completed"])
        secret: Optional HMAC secret for signature verification
        headers: Additional headers to include in requests
        timeout_seconds: Request timeout
        max_retries: Maximum delivery attempts
        retry_delay_seconds: Base delay between retries (exponential backoff)
    """
    url: str
    events: List[str]
    secret: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 1.0

    def matches_event(self, event_type: str) -> bool:
        """Check if this config subscribes to an event type.

        Supports wildcards:
        - "request.*" matches "request.completed", "request.failed"
        - "*" matches all events
        """
        for pattern in self.events:
            if pattern == "*":
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event_type.startswith(prefix):
                    return True
            if pattern == event_type:
                return True
        return False


@dataclass
class WebhookDeliveryResult:
    """Result of a webhook delivery attempt."""
    webhook_id: str
    event_type: str
    status: DeliveryStatus
    attempt: int
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    delivered_at: Optional[datetime] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "webhook_id": self.webhook_id,
            "event_type": self.event_type,
            "status": self.status.value,
            "attempt": self.attempt,
            "response_status": self.response_status,
            "response_body": self.response_body,
            "error": self.error,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "duration_ms": self.duration_ms,
        }


@dataclass
class WebhookPayload:
    """Payload for webhook delivery."""
    event_type: str
    event_id: str
    timestamp: datetime
    data: Dict[str, Any]
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "request_id": self.request_id,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str, sort_keys=True)


class WebhookSubscriber:
    """Event subscriber that delivers events to webhook endpoints.

    Can be attached to EventEmitter to automatically deliver events.
    """

    def __init__(
        self,
        service: "WebhookService",
        scope: Optional[str] = None,
    ):
        """Initialize subscriber.

        Args:
            service: Parent webhook service
            scope: Optional scope (e.g., request_id) for filtering
        """
        self._service = service
        self._scope = scope

    async def on_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        request_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Handle an event by delivering to webhooks.

        Args:
            event_type: Type of event
            payload: Event payload
            request_id: Optional request ID for scoping
            **kwargs: Additional event metadata
        """
        # Filter by scope if set
        if self._scope and request_id != self._scope:
            return

        await self._service.emit_event(
            event_type=event_type,
            data=payload,
            request_id=request_id,
        )


class WebhookService:
    """Service for managing webhook subscriptions and delivery.

    Thread-safe implementation supporting:
    - Global webhooks (receive all events)
    - Scoped webhooks (receive events for specific requests)
    - Async delivery with retry
    - HMAC signature verification

    Architecture:
    - Registrations stored in memory (can be extended with persistence)
    - Delivery via aiohttp (or stubbed if not available)
    - Retry with exponential backoff
    """

    def __init__(
        self,
        logger: Optional[LoggerProtocol] = None,
        delivery_queue_size: int = 1000,
    ):
        """Initialize webhook service.

        Args:
            logger: Optional logger
            delivery_queue_size: Max pending deliveries
        """
        self._logger = logger
        self._delivery_queue_size = delivery_queue_size

        # Registrations: scope -> list of configs
        # scope="" for global webhooks
        self._registrations: Dict[str, List[WebhookConfig]] = {}
        self._lock = threading.RLock()

        # Delivery tracking
        self._pending_deliveries: asyncio.Queue = asyncio.Queue(maxsize=delivery_queue_size)
        self._delivery_results: Dict[str, List[WebhookDeliveryResult]] = {}

        # Background delivery task
        self._delivery_task: Optional[asyncio.Task] = None
        self._running = False

    def register(
        self,
        config: WebhookConfig,
        scope: Optional[str] = None,
    ) -> str:
        """Register a webhook.

        Args:
            config: Webhook configuration
            scope: Optional scope (e.g., request_id) for filtering

        Returns:
            Webhook ID for reference
        """
        scope_key = scope or ""
        webhook_id = f"wh_{scope_key}_{len(self._registrations.get(scope_key, []))}"

        with self._lock:
            if scope_key not in self._registrations:
                self._registrations[scope_key] = []
            self._registrations[scope_key].append(config)

        if self._logger:
            self._logger.info(
                "webhook_registered",
                webhook_id=webhook_id,
                url=config.url,
                events=config.events,
                scope=scope,
            )

        return webhook_id

    def unregister(self, scope: Optional[str] = None, url: Optional[str] = None) -> int:
        """Unregister webhooks.

        Args:
            scope: Scope to unregister (None for global)
            url: Optional URL filter (unregisters all if None)

        Returns:
            Number of webhooks unregistered
        """
        scope_key = scope or ""
        removed = 0

        with self._lock:
            if scope_key not in self._registrations:
                return 0

            if url is None:
                removed = len(self._registrations[scope_key])
                del self._registrations[scope_key]
            else:
                original = self._registrations[scope_key]
                self._registrations[scope_key] = [
                    c for c in original if c.url != url
                ]
                removed = len(original) - len(self._registrations[scope_key])

        if self._logger:
            self._logger.info(
                "webhooks_unregistered",
                scope=scope,
                url=url,
                count=removed,
            )

        return removed

    def get_webhooks(self, scope: Optional[str] = None) -> List[WebhookConfig]:
        """Get registered webhooks.

        Args:
            scope: Scope to query (None for global)

        Returns:
            List of webhook configs
        """
        scope_key = scope or ""
        with self._lock:
            return list(self._registrations.get(scope_key, []))

    async def emit_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        request_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> int:
        """Emit an event to matching webhooks.

        Args:
            event_type: Type of event (e.g., "request.completed")
            data: Event data
            request_id: Optional request ID for scoped delivery
            event_id: Optional event ID (generated if not provided)

        Returns:
            Number of webhooks queued for delivery
        """
        import uuid

        payload = WebhookPayload(
            event_type=event_type,
            event_id=event_id or str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            data=data,
            request_id=request_id,
        )

        # Find matching webhooks
        matching_configs: List[WebhookConfig] = []

        with self._lock:
            # Check global webhooks
            for config in self._registrations.get("", []):
                if config.matches_event(event_type):
                    matching_configs.append(config)

            # Check scoped webhooks
            if request_id:
                for config in self._registrations.get(request_id, []):
                    if config.matches_event(event_type):
                        matching_configs.append(config)

        # Queue for delivery
        for config in matching_configs:
            try:
                await self._pending_deliveries.put((config, payload))
            except asyncio.QueueFull:
                if self._logger:
                    self._logger.warning(
                        "webhook_queue_full",
                        event_type=event_type,
                        url=config.url,
                    )

        return len(matching_configs)

    async def start_delivery_worker(self) -> None:
        """Start the background delivery worker."""
        if self._running:
            return

        self._running = True
        self._delivery_task = asyncio.create_task(self._delivery_loop())

        if self._logger:
            self._logger.info("webhook_delivery_worker_started")

    async def stop_delivery_worker(self) -> None:
        """Stop the background delivery worker."""
        self._running = False
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass

        if self._logger:
            self._logger.info("webhook_delivery_worker_stopped")

    async def _delivery_loop(self) -> None:
        """Background loop for processing deliveries."""
        while self._running:
            try:
                # Get next delivery with timeout
                try:
                    config, payload = await asyncio.wait_for(
                        self._pending_deliveries.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Deliver with retry
                result = await self._deliver_with_retry(config, payload)

                # Store result
                key = payload.request_id or "global"
                if key not in self._delivery_results:
                    self._delivery_results[key] = []
                self._delivery_results[key].append(result)

                # Limit stored results
                if len(self._delivery_results[key]) > 100:
                    self._delivery_results[key] = self._delivery_results[key][-100:]

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._logger:
                    self._logger.error(
                        "webhook_delivery_error",
                        error=str(e),
                    )

    async def _deliver_with_retry(
        self,
        config: WebhookConfig,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Deliver webhook with retry logic.

        Args:
            config: Webhook configuration
            payload: Payload to deliver

        Returns:
            Delivery result
        """
        webhook_id = f"wh_{config.url[:50]}"

        for attempt in range(1, config.max_retries + 1):
            start_time = time.time()

            try:
                result = await self._deliver_once(config, payload)
                result.webhook_id = webhook_id
                result.attempt = attempt
                result.duration_ms = (time.time() - start_time) * 1000

                if result.status == DeliveryStatus.DELIVERED:
                    return result

                # Check if retryable
                if result.response_status and result.response_status >= 400 and result.response_status < 500:
                    # Client error, don't retry
                    result.status = DeliveryStatus.FAILED
                    return result

            except Exception as e:
                result = WebhookDeliveryResult(
                    webhook_id=webhook_id,
                    event_type=payload.event_type,
                    status=DeliveryStatus.RETRYING,
                    attempt=attempt,
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # Exponential backoff before retry
            if attempt < config.max_retries:
                delay = config.retry_delay_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

                if self._logger:
                    self._logger.info(
                        "webhook_retry",
                        url=config.url,
                        attempt=attempt + 1,
                        delay=delay,
                    )

        # All retries exhausted
        return WebhookDeliveryResult(
            webhook_id=webhook_id,
            event_type=payload.event_type,
            status=DeliveryStatus.FAILED,
            attempt=config.max_retries,
            error="Max retries exhausted",
        )

    async def _deliver_once(
        self,
        config: WebhookConfig,
        payload: WebhookPayload,
    ) -> WebhookDeliveryResult:
        """Deliver webhook once (no retry).

        Args:
            config: Webhook configuration
            payload: Payload to deliver

        Returns:
            Delivery result
        """
        json_body = payload.to_json()

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": payload.event_type,
            "X-Webhook-ID": payload.event_id,
            "X-Webhook-Timestamp": payload.timestamp.isoformat(),
            **config.headers,
        }

        # Add HMAC signature if secret configured
        if config.secret:
            signature = self._compute_signature(json_body, config.secret)
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        if not AIOHTTP_AVAILABLE:
            # Stub for testing without aiohttp
            if self._logger:
                self._logger.info(
                    "webhook_delivery_stub",
                    url=config.url,
                    event_type=payload.event_type,
                )
            return WebhookDeliveryResult(
                webhook_id="",
                event_type=payload.event_type,
                status=DeliveryStatus.DELIVERED,
                attempt=1,
                response_status=200,
                delivered_at=datetime.now(timezone.utc),
            )

        # Actual HTTP delivery
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.url,
                data=json_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
            ) as response:
                response_body = await response.text()

                status = (
                    DeliveryStatus.DELIVERED
                    if 200 <= response.status < 300
                    else DeliveryStatus.FAILED
                )

                return WebhookDeliveryResult(
                    webhook_id="",
                    event_type=payload.event_type,
                    status=status,
                    attempt=1,
                    response_status=response.status,
                    response_body=response_body[:500] if response_body else None,
                    delivered_at=datetime.now(timezone.utc),
                )

    def _compute_signature(self, payload: str, secret: str) -> str:
        """Compute HMAC-SHA256 signature.

        Args:
            payload: JSON payload string
            secret: HMAC secret

        Returns:
            Hex-encoded signature
        """
        return hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def get_delivery_results(
        self,
        scope: Optional[str] = None,
        limit: int = 100,
    ) -> List[WebhookDeliveryResult]:
        """Get recent delivery results.

        Args:
            scope: Scope to query (None for global)
            limit: Max results to return

        Returns:
            List of delivery results
        """
        key = scope or "global"
        results = self._delivery_results.get(key, [])
        return results[-limit:]

    def create_subscriber(self, scope: Optional[str] = None) -> WebhookSubscriber:
        """Create an event subscriber for this service.

        Args:
            scope: Optional scope for filtering events

        Returns:
            WebhookSubscriber instance
        """
        return WebhookSubscriber(self, scope)


# Global instance for convenience
_global_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> Optional[WebhookService]:
    """Get the global webhook service."""
    return _global_webhook_service


def init_webhook_service(logger: Optional[LoggerProtocol] = None) -> WebhookService:
    """Initialize the global webhook service.

    Args:
        logger: Optional logger

    Returns:
        Initialized service
    """
    global _global_webhook_service
    _global_webhook_service = WebhookService(logger)
    return _global_webhook_service
