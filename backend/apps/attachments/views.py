"""Attachment API endpoints."""

from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwner
from .models import Attachment
from .services import attach_file, list_attachments, detach


class AttachmentListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsOwner]

    def get(self, request):
        attachable_type = request.query_params.get('attachable_type')
        attachable_id = request.query_params.get('attachable_id')
        if not attachable_type or not attachable_id:
            return Response(
                {'detail': 'attachable_type and attachable_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            content_type = ContentType.objects.get(model=attachable_type.lower())
        except ContentType.DoesNotExist:
            return Response({'detail': 'Unknown attachable_type.'}, status=status.HTTP_400_BAD_REQUEST)
        attachments = Attachment.objects.filter(
            tenant_id=request.tenant_id,
            content_type=content_type,
            object_id=int(attachable_id),
            deleted_at__isnull=True,
        )
        data = [_serialize(a) for a in attachments]
        return Response(data)

    def post(self, request):
        attachable_type = request.data.get('attachable_type')
        attachable_id = request.data.get('attachable_id')
        file = request.FILES.get('file')
        if not attachable_type or not attachable_id or not file:
            return Response(
                {'detail': 'attachable_type, attachable_id, and file are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            content_type = ContentType.objects.get(model=attachable_type.lower())
            model_class = content_type.model_class()
            attachable = get_object_or_404(model_class, pk=int(attachable_id))
        except ContentType.DoesNotExist:
            return Response({'detail': 'Unknown attachable_type.'}, status=status.HTTP_400_BAD_REQUEST)

        attachment = attach_file(
            tenant_id=request.tenant_id,
            attachable=attachable,
            file=file,
            kind=request.data.get('kind', Attachment.Kind.OTHER),
            caption=request.data.get('caption', ''),
            uploaded_by_id=request.user.id if request.user.is_authenticated else None,
        )
        return Response(_serialize(attachment), status=status.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    permission_classes = [IsOwner]

    def delete(self, request, pk):
        detach(
            attachment_id=int(pk),
            tenant_id=request.tenant_id,
            deleted_by_id=request.user.id if request.user.is_authenticated else None,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def _serialize(attachment: Attachment) -> dict:
    return {
        'id': attachment.pk,
        'kind': attachment.kind,
        'caption': attachment.caption,
        'file': attachment.file.url if attachment.file else None,
        'uploaded_at': attachment.uploaded_at.isoformat(),
        'uploaded_by': attachment.uploaded_by_id,
        'content_type': attachment.content_type.model,
        'object_id': attachment.object_id,
    }
