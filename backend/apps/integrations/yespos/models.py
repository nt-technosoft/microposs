"""YesPos vendor — raw inbound event store."""

import uuid

from django.db import models


class YesposRawEvent(models.Model):
    """Append-only log of all inbound YesPos webhook payloads."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    slug = models.CharField(max_length=64)
    body = models.JSONField()
    headers = models.JSONField(default=dict)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    tenant = models.ForeignKey(
        'core.Business',
        on_delete=models.PROTECT,
        related_name='yespos_raw_events',
    )
    processed = models.BooleanField(default=False)
    source_request_id = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        db_table = 'integrations_yespos_raw_event'
        indexes = [
            models.Index(fields=['received_at']),
            models.Index(fields=['slug', 'received_at']),
            models.Index(fields=['tenant', 'received_at']),
        ]
        constraints = [
            # Idempotency: dedup by (tenant, source_request_id) when header present
            models.UniqueConstraint(
                fields=['tenant', 'source_request_id'],
                condition=models.Q(source_request_id__isnull=False),
                name='uq_yespos_event_request_id',
            ),
        ]

    def __str__(self) -> str:
        return f"YesposRawEvent/{self.slug} @ {self.received_at}"
