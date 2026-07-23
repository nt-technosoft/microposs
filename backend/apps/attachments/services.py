"""Attachment service functions."""

from django.contrib.contenttypes.models import ContentType

from .models import Attachment


def attach_file(
    *,
    tenant_id: int,
    attachable,
    file,
    kind: str = Attachment.Kind.OTHER,
    caption: str = '',
    uploaded_by_id: int | None = None,
) -> Attachment:
    content_type = ContentType.objects.get_for_model(attachable.__class__)
    return Attachment.objects.create(
        tenant_id=tenant_id,
        content_type=content_type,
        object_id=attachable.pk,
        file=file,
        kind=kind,
        caption=caption,
        uploaded_by_id=uploaded_by_id,
    )


def list_attachments(*, attachable):
    content_type = ContentType.objects.get_for_model(attachable.__class__)
    return Attachment.objects.filter(
        content_type=content_type,
        object_id=attachable.pk,
        deleted_at__isnull=True,
    )


def detach(attachment_id: int, tenant_id: int, deleted_by_id: int | None = None) -> None:
    attachment = Attachment.objects.get(pk=attachment_id, tenant_id=tenant_id)
    attachment.soft_delete()
