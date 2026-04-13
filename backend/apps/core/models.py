"""
Core models — foundation for all MicroPOS domain models.
"""

from django.db import models
from django.utils import timezone

from .managers import SoftDeleteManager
from .exceptions import ImmutableRecordError


class BaseModel(models.Model):
    """Abstract base with timestamps and soft-delete."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at', 'updated_at'])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=['deleted_at', 'updated_at'])

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class TenantModel(BaseModel):
    """Abstract base for all tenant-scoped business models."""

    tenant = models.ForeignKey(
        'core.Business',
        on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_set',
        db_index=True,
    )

    class Meta:
        abstract = True


IMMUTABLE_STATUSES = frozenset({'confirmed', 'completed', 'closed'})


class ImmutableMixin:
    """
    Mixin for models that become immutable after reaching certain statuses.
    Model must have a `status` field.
    """

    def save(self, *args, **kwargs):
        if self.pk:
            original = self.__class__.objects.get(pk=self.pk)
            if original.status in IMMUTABLE_STATUSES:
                raise ImmutableRecordError(
                    f"Cannot modify {self.__class__.__name__} "
                    f"in status '{original.status}'"
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if hasattr(self, 'status') and self.status in IMMUTABLE_STATUSES:
            raise ImmutableRecordError(
                f"Cannot delete {self.__class__.__name__} "
                f"in status '{self.status}'"
            )
        self.soft_delete()


class Business(BaseModel):
    """Tenant — represents a business entity."""

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='owned_businesses',
    )
    currency = models.CharField(max_length=3, default='UZS')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'core_business'
        verbose_name_plural = 'businesses'

    def __str__(self):
        return self.name


class OutboxEvent(BaseModel):
    """
    Outbox pattern — stores domain events for async processing.
    Celery workers poll for unprocessed events.
    """

    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True)
    tenant_id = models.IntegerField(db_index=True)

    class Meta:
        db_table = 'core_outbox_event'
        indexes = [
            models.Index(
                fields=['processed_at', 'tenant_id'],
                name='idx_outbox_unprocessed',
                condition=models.Q(processed_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.event_type} (tenant={self.tenant_id})"

    def mark_processed(self):
        self.processed_at = timezone.now()
        self.save(update_fields=['processed_at', 'updated_at'])
