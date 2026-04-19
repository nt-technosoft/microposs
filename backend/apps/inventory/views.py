"""
Inventory API views — locations, receipts, lots, stock, transfers.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsWarehouse
from apps.core.exceptions import DuplicateRequestError
from decimal import Decimal

from .models import (
    Warehouse, Receipt, ReceiptLine, ReceiptParticipant,
    Lot, StockMovement,
)
from .serializers import (
    WarehouseSerializer,
    ReceiptListSerializer, ReceiptDetailSerializer, ReceiptCreateSerializer,
    LotSerializer, StockMovementSerializer,
    TransferSerializer, StockSummarySerializer,
)
from .services import (
    transfer_lot_stock, get_stock_summary,
)


class WarehouseViewSet(viewsets.ModelViewSet):
    serializer_class = WarehouseSerializer
    search_fields = ['name']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsWarehouse()]
        return [IsOwner()]

    def get_queryset(self):
        return Warehouse.objects.filter(tenant_id=self.request.tenant_id)

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.soft_delete()


class ReceiptViewSet(viewsets.ModelViewSet):
    search_fields = ['notes']
    ordering = ['-date']

    def get_permissions(self):
        return [IsWarehouse()]

    def get_queryset(self):
        qs = Receipt.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('destination', 'supplier')

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'lines__product_variant',
                'participants',
                'lots__product_variant',
                'lots__stocks__warehouse',
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
        total_operation_amount = sum(
            Decimal(str(line_data['cost_per_unit'])) * int(line_data['quantity'])
            for line_data in data['lines']
        )
        receipt = Receipt.objects.create(
            tenant_id=request.tenant_id,
            receipt_type=data['receipt_type'],
            date=data['date'],
            destination_id=data['destination_id'],
            supplier_id=data.get('supplier_id'),
            investor_contract_id=data.get('investor_contract_id'),
            payable_terms=data.get('payable_terms'),
            consignment_rule=data.get('consignment_rule'),
            operation_currency='UZS',
            operation_amount=total_operation_amount,
            fx_rate_snapshot=Decimal('1'),
            functional_amount_uzs=total_operation_amount,
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


class LotViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only lot access. Lots are created via receipt confirmation."""

    serializer_class = LotSerializer
    ordering = ['-created_at']

    def get_permissions(self):
        return [IsWarehouse()]

    def get_queryset(self):
        qs = Lot.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('product_variant', 'receipt').prefetch_related('stocks__warehouse')

        variant_id = self.request.query_params.get('product_variant')
        if variant_id:
            qs = qs.filter(product_variant_id=variant_id)

        warehouse_id = self.request.query_params.get('warehouse')
        if warehouse_id:
            qs = qs.filter(
                stocks__warehouse_id=warehouse_id,
                stocks__quantity_remaining__gt=0,
            ).distinct()

        active_only = self.request.query_params.get('active', 'true')
        if active_only.lower() == 'true':
            qs = qs.filter(is_active=True)

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
        """Stock summary grouped by variant + warehouse (aggregated from LotStock)."""
        warehouse_id = request.query_params.get('warehouse')
        data = get_stock_summary(
            tenant_id=request.tenant_id,
            warehouse_id=warehouse_id,
        )
        serializer = StockSummarySerializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer(self, request):
        """Transfer lot stock between warehouses."""
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lot = Lot.objects.get(pk=data['lot_id'], tenant_id=request.tenant_id)
        from_warehouse = Warehouse.objects.get(
            pk=data['from_warehouse_id'], tenant_id=request.tenant_id,
        )
        to_warehouse = Warehouse.objects.get(
            pk=data['to_warehouse_id'], tenant_id=request.tenant_id,
        )
        stock = transfer_lot_stock(
            tenant_id=request.tenant_id,
            lot=lot,
            from_warehouse=from_warehouse,
            to_warehouse=to_warehouse,
            quantity=data['quantity'],
        )
        return Response(LotSerializer(stock.lot).data)
