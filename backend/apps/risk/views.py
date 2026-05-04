"""
Risk API views — risk events, writeoffs, inventory checks.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsWarehouse

from .models import RiskEvent, InventoryCheck, InventoryCheckLine
from .serializers import (
    RiskEventSerializer, WriteoffCreateSerializer, WriteoffPreviewSerializer,
    InventoryCheckSerializer, InventoryCheckCreateSerializer,
    InventoryCheckLineSerializer,
)
from .services import create_writeoff, complete_inventory_check, build_writeoff_preview


class RiskEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Risk event log — read-only. Created automatically by services."""

    serializer_class = RiskEventSerializer
    permission_classes = [IsOwner]
    ordering = ['-created_at']

    def get_queryset(self):
        qs = RiskEvent.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('lot', 'responsible_user')

        event_type = self.request.query_params.get('event_type')
        if event_type:
            qs = qs.filter(event_type=event_type)

        affects_investor = self.request.query_params.get('affects_investor')
        if affects_investor and affects_investor.lower() == 'true':
            qs = qs.filter(affects_investor=True)

        return qs

    @action(detail=False, methods=['post'], url_path='writeoff')
    def writeoff(self, request):
        """Create a writeoff risk event."""
        serializer = WriteoffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        risk_event = create_writeoff(
            tenant_id=request.tenant_id,
            lot_id=data['lot_id'],
            warehouse_id=data['warehouse_id'],
            quantity=data['quantity'],
            reason=data['reason'],
            responsible_user_id=request.user.pk,
            negligence=data.get('negligence', False),
        )
        output = RiskEventSerializer(risk_event)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='writeoff-preview')
    def writeoff_preview(self, request):
        """Preview stock writeoff loss before confirmation."""
        serializer = WriteoffPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            preview = build_writeoff_preview(
                tenant_id=request.tenant_id,
                lot_id=data['lot_id'],
                warehouse_id=data['warehouse_id'],
                quantity=data['quantity'],
                negligence=data.get('negligence', False),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(preview)


class InventoryCheckViewSet(viewsets.ModelViewSet):
    """Inventory checks (stocktaking)."""

    serializer_class = InventoryCheckSerializer
    permission_classes = [IsWarehouse]
    ordering = ['-created_at']

    def get_queryset(self):
        qs = InventoryCheck.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('location', 'checked_by')

        if self.action == 'retrieve':
            qs = qs.prefetch_related('lines__product_variant')

        check_status = self.request.query_params.get('status')
        if check_status:
            qs = qs.filter(status=check_status)

        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return InventoryCheckCreateSerializer
        return InventoryCheckSerializer

    def create(self, request, *args, **kwargs):
        serializer = InventoryCheckCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        check = InventoryCheck.objects.create(
            tenant_id=request.tenant_id,
            location_id=data['location_id'],
            checked_by=request.user,
            notes=data.get('notes', ''),
        )

        for line_data in data['lines']:
            expected = line_data['expected_quantity']
            actual = line_data['actual_quantity']
            InventoryCheckLine.objects.create(
                tenant_id=request.tenant_id,
                inventory_check=check,
                product_variant_id=line_data['product_variant_id'],
                expected_quantity=expected,
                actual_quantity=actual,
                difference=actual - expected,
            )

        output = InventoryCheckSerializer(check)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        """Complete an inventory check and create risk events for mismatches."""
        check = self.get_object()
        check = complete_inventory_check(
            tenant_id=request.tenant_id,
            check_id=check.pk,
        )
        output = InventoryCheckSerializer(check)
        return Response(output.data)
