"""
Inventory API views — locations, receipts, lots, stock, transfers.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsWarehouse
from apps.core.exceptions import DuplicateRequestError

from .models import (
    Location, Receipt, ReceiptLine, ReceiptParticipant,
    Lot, StockMovement,
)
from .serializers import (
    LocationSerializer,
    ReceiptListSerializer, ReceiptDetailSerializer, ReceiptCreateSerializer,
    LotSerializer, StockMovementSerializer,
    TransferSerializer, StockSummarySerializer,
)
from .services import (
    confirm_receipt, transfer_lot, get_stock_summary,
)


class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    permission_classes = [IsOwner]
    search_fields = ['name']
    ordering = ['name']

    def get_queryset(self):
        return Location.objects.filter(tenant_id=self.request.tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.soft_delete()


class ReceiptViewSet(viewsets.ModelViewSet):
    search_fields = ['notes']
    ordering = ['-date']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsWarehouse()]
        return [IsOwner()]

    def get_queryset(self):
        qs = Receipt.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('destination', 'supplier')

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'lines__product_variant',
                'participants',
                'lots__product_variant',
                'lots__location',
            )
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ReceiptDetailSerializer
        if self.action == 'create':
            return ReceiptCreateSerializer
        return ReceiptListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Idempotency check
        client_request_id = data.get('client_request_id')
        if client_request_id:
            existing = Receipt.objects.filter(
                tenant_id=request.tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                output = ReceiptDetailSerializer(existing)
                return Response(output.data, status=status.HTTP_200_OK)

        # Create receipt
        receipt = Receipt.objects.create(
            tenant_id=request.tenant_id,
            receipt_type=data['receipt_type'],
            date=data['date'],
            destination_id=data['destination_id'],
            supplier_id=data.get('supplier_id'),
            investor_contract_id=data.get('investor_contract_id'),
            payable_terms=data.get('payable_terms'),
            consignment_rule=data.get('consignment_rule'),
            notes=data.get('notes', ''),
            client_request_id=client_request_id,
            status=Receipt.ReceiptStatus.DRAFT,
        )

        # Create lines
        for line_data in data['lines']:
            ReceiptLine.objects.create(
                tenant_id=request.tenant_id,
                receipt=receipt,
                product_variant_id=line_data['product_variant_id'],
                quantity=line_data['quantity'],
                cost_per_unit=line_data['cost_per_unit'],
            )

        # Create participants
        for p_data in data.get('participants', []):
            ReceiptParticipant.objects.create(
                tenant_id=request.tenant_id,
                receipt=receipt,
                participant_type=p_data['participant_type'],
                entity_id=p_data['entity_id'],
                capital_amount=p_data['capital_amount'],
                capital_ratio=0,  # Will be calculated on confirm
                profit_ratio=p_data['profit_ratio'],
            )

        output = ReceiptDetailSerializer(receipt)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        """Confirm receipt — creates lots, makes receipt immutable."""
        receipt = self.get_object()
        receipt = confirm_receipt(receipt)
        output = ReceiptDetailSerializer(receipt)
        return Response(output.data)


class LotViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only lot access. Lots are created via receipt confirmation."""

    serializer_class = LotSerializer
    ordering = ['-created_at']

    def get_permissions(self):
        return [IsWarehouse()]

    def get_queryset(self):
        qs = Lot.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('product_variant', 'location', 'receipt')

        # Filter by product variant
        variant_id = self.request.query_params.get('product_variant')
        if variant_id:
            qs = qs.filter(product_variant_id=variant_id)

        # Filter by location
        location_id = self.request.query_params.get('location')
        if location_id:
            qs = qs.filter(location_id=location_id)

        # Only active lots
        active_only = self.request.query_params.get('active', 'true')
        if active_only.lower() == 'true':
            qs = qs.filter(is_active=True, quantity_remaining__gt=0)

        return qs


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only stock movement log."""

    serializer_class = StockMovementSerializer
    permission_classes = [IsWarehouse]
    ordering = ['-created_at']

    def get_queryset(self):
        return StockMovement.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('from_location', 'to_location', 'lot')


class StockView(viewsets.ViewSet):
    """Stock summary and transfer operations."""

    permission_classes = [IsWarehouse]

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Get stock summary grouped by variant and location."""
        location_id = request.query_params.get('location')
        data = get_stock_summary(
            tenant_id=request.tenant_id,
            location_id=location_id,
        )
        serializer = StockSummarySerializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer(self, request):
        """Transfer lot between locations."""
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lot = Lot.objects.get(
            pk=data['lot_id'],
            tenant_id=request.tenant_id,
        )
        to_location = Location.objects.get(
            pk=data['to_location_id'],
            tenant_id=request.tenant_id,
        )

        lot = transfer_lot(
            lot=lot,
            to_location=to_location,
            quantity=data.get('quantity'),
            tenant_id=request.tenant_id,
        )
        output = LotSerializer(lot)
        return Response(output.data)
