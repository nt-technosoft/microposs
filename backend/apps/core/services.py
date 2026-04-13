"""
Core services — outbox event publishing, tenant utilities.
"""

from .models import OutboxEvent


def publish_event(event_type: str, payload: dict, tenant_id: int) -> OutboxEvent:
    """Create an OutboxEvent for async processing by Celery."""
    return OutboxEvent.objects.create(
        event_type=event_type,
        payload=payload,
        tenant_id=tenant_id,
    )
