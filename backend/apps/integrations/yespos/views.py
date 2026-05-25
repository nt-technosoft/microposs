"""YesPos inbound webhook + query endpoints."""

import re

from django.db import IntegrityError
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from apps.integrations.auth import IntegrationKeyAuthentication
from apps.partnerships.models import InvestmentAgreement, AgreementPartner
from .models import YesposRawEvent

_SLUG_RE = re.compile(r'^[a-z0-9-]{1,64}$')

_INTEGRATION_AUTH = [IntegrationKeyAuthentication]
_NO_PERM = [AllowAny]


def _get_client_ip(request: Request) -> str | None:
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _store_event(request: Request, slug: str) -> Response:
    """Persist raw inbound event; idempotent via X-Request-Id."""
    source_request_id = request.META.get('HTTP_X_REQUEST_ID') or None
    headers_snapshot = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ('x-integration-key',)  # strip credential header
    }
    try:
        event = YesposRawEvent.objects.create(
            slug=slug,
            body=request.data if isinstance(request.data, dict) else {},
            headers=headers_snapshot,
            source_ip=_get_client_ip(request),
            tenant_id=request.tenant_id,
            source_request_id=source_request_id,
        )
    except IntegrityError:
        # Duplicate X-Request-Id — return 200 (idempotent)
        return Response({'status': 'duplicate'}, status=status.HTTP_200_OK)

    return Response({'id': str(event.id), 'status': 'received'}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes(_INTEGRATION_AUTH)
@permission_classes(_NO_PERM)
def agreement_link(request: Request) -> Response:
    return _store_event(request, 'agreement-link')


@api_view(['POST'])
@authentication_classes(_INTEGRATION_AUTH)
@permission_classes(_NO_PERM)
def sale(request: Request) -> Response:
    return _store_event(request, 'sale')


@api_view(['POST'])
@authentication_classes(_INTEGRATION_AUTH)
@permission_classes(_NO_PERM)
def inventory(request: Request) -> Response:
    return _store_event(request, 'inventory')


@api_view(['POST'])
@authentication_classes(_INTEGRATION_AUTH)
@permission_classes(_NO_PERM)
def catchall(request: Request, slug: str) -> Response:
    if not _SLUG_RE.match(slug):
        return Response(
            {'detail': 'Invalid slug. Use [a-z0-9-]{1,64}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return _store_event(request, slug)


@api_view(['GET'])
@authentication_classes(_INTEGRATION_AUTH)
@permission_classes(_NO_PERM)
def agreements(request: Request) -> Response:
    """List active investment agreements for the authenticated tenant."""
    qs = (
        InvestmentAgreement.objects
        .filter(tenant_id=request.tenant_id, status=InvestmentAgreement.Status.ACTIVE)
        .prefetch_related('partners__partner')
        .order_by('opened_at')
    )
    results = []
    for ag in qs:
        investor_partner = next(
            (p for p in ag.partners.all() if p.role == AgreementPartner.Role.INVESTOR),
            None,
        )
        results.append({
            'id': ag.pk,
            'title': f"Agreement #{ag.pk}",
            'investor_name': investor_partner.partner.display_name if investor_partner else None,
            'profit_ratio': str(investor_partner.profit_share) if investor_partner else None,
            'capital_amount': str(ag.planned_budget),
            'currency': ag.currency,
            'status': ag.status,
        })
    return Response(results)
