"""Webhooks Module.

Provides webhook delivery and subscription management for async callbacks.

Components:
- WebhookSubscriber: Event subscriber that delivers to HTTP endpoints
- WebhookService: Manages webhook registrations and delivery queue
- WebhookConfig: Configuration for webhook endpoints

Usage:
    from jeeves_infra.webhooks import WebhookService, WebhookConfig

    # Register a webhook
    config = WebhookConfig(
        url="https://api.example.com/webhook",
        events=["request.completed", "agent.failed"],
        secret="shared-secret-for-hmac",
    )
    webhook_service.register(request_id, config)

    # Webhook will be called when matching events occur

Constitutional Reference: Infrastructure layer (jeeves_infra)
"""

from jeeves_infra.webhooks.service import (
    WebhookService,
    WebhookConfig,
    WebhookDeliveryResult,
    WebhookSubscriber,
)

__all__ = [
    "WebhookService",
    "WebhookConfig",
    "WebhookDeliveryResult",
    "WebhookSubscriber",
]
