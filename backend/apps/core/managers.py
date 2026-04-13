"""Custom managers for soft-delete and tenant filtering."""

from django.db import models


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that filters out soft-deleted records by default."""

    def delete(self):
        """Soft-delete all records in queryset."""
        from django.utils import timezone
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        """Actually delete from database. Use with extreme caution."""
        return super().delete()

    def alive(self):
        """Explicitly filter to non-deleted records."""
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        """Show only soft-deleted records."""
        return self.filter(deleted_at__isnull=False)

    def for_tenant(self, tenant_id):
        """Filter by tenant (if model has tenant_id)."""
        return self.filter(tenant_id=tenant_id)


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted records by default."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()
