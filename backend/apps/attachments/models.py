"""
Generic attachment model — file attached to any domain model via ContentType GenericFK.

MVP attach-points: Procurement, ProcurementReceiveBatch.
Extends without new tables via GenericForeignKey.
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TenantModel


class Attachment(TenantModel):
    class Kind(models.TextChoices):
        INVOICE = 'INVOICE', 'Накладная'
        RECEIPT_PHOTO = 'RECEIPT_PHOTO', 'Фото приёма'
        DOCUMENT = 'DOCUMENT', 'Документ'
        OTHER = 'OTHER', 'Другое'

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    attachable = GenericForeignKey('content_type', 'object_id')

    file = models.FileField(upload_to='attachments/%Y/%m/')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    caption = models.CharField(max_length=255, blank=True, default='')
    uploaded_by = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT, null=True, blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'attachments_attachment'
        indexes = [
            models.Index(fields=['tenant', 'content_type', 'object_id']),
            models.Index(fields=['tenant', 'kind']),
        ]

    def __str__(self):
        return f'Attachment#{self.pk} {self.kind} → {self.content_type}/{self.object_id}'
