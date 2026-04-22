"""
Inventory serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import (
    Warehouse, Receipt, ReceiptLine, ReceiptParticipant,
    Lot, LotStock, StockMovement,
)


# === Warehouse ===

class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'kind', 'address', 'is_active']
        read_only_fields = ['id']


# === Receipt Participants ===

class ReceiptParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptParticipant
        fields = [
            'id', 'participant_type', 'entity_id',
            'capital_amount', 'capital_ratio', 'profit_ratio',
        ]
        read_only_fields = ['id', 'capital_ratio']


class ReceiptParticipantInputSerializer(serializers.Serializer):
    participant_type = serializers.ChoiceField(choices=['business', 'investor'])
    entity_id = serializers.IntegerField()
    capital_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    profit_ratio = serializers.DecimalField(max_digits=5, decimal_places=4)


# === Receipt Lines ===

class ReceiptLineSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(
        source='product_variant.__str__', read_only=True,
    )
    total_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
    )

    class Meta:
        model = ReceiptLine
        fields = [
            'id', 'product_variant', 'product_variant_name',
            'quantity', 'cost_per_unit', 'total_cost',
        ]
        read_only_fields = ['id']


class ReceiptLineInputSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    cost_per_unit = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.01'),
    )


# === Receipt ===

class ReceiptListSerializer(serializers.ModelSerializer):
    destination_name = serializers.CharField(
        source='destination.name', read_only=True,
    )
    lines_count = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_type', 'status', 'date',
            'destination', 'destination_name',
            'supplier', 'lines_count', 'total_amount',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_lines_count(self, obj):
        return obj.lines.count()

    def get_total_amount(self, obj):
        total = sum(
            line.cost_per_unit * line.quantity
            for line in obj.lines.all()
        )
        return str(total)


class ReceiptDetailSerializer(serializers.ModelSerializer):
    destination_name = serializers.CharField(
        source='destination.name', read_only=True,
    )
    lines = ReceiptLineSerializer(many=True, read_only=True)
    participants = ReceiptParticipantSerializer(many=True, read_only=True)
    lots = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_type', 'status', 'date',
            'destination', 'destination_name',
            'supplier', 'investor_contract',
            'payable_terms', 'consignment_rule',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'lines', 'participants', 'lots',
            'notes', 'client_request_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_lots(self, obj):
        if obj.status != Receipt.ReceiptStatus.CONFIRMED:
            return []
        lots = obj.lots.select_related('product_variant', 'receipt').prefetch_related('stocks__warehouse').all()
        return LotSerializer(lots, many=True).data


class ReceiptCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    receipt_type = serializers.ChoiceField(
        choices=[
            'BUSINESS_OWNED', 'MUDARABA', 'MUSHARAKA',
            'SUPPLIER_PURCHASE', 'CONSIGNMENT',
        ]
    )
    date = serializers.DateTimeField()
    destination_id = serializers.IntegerField()
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    investor_contract_id = serializers.IntegerField(required=False, allow_null=True)
    participants = ReceiptParticipantInputSerializer(many=True, required=False)
    payable_terms = serializers.JSONField(required=False, allow_null=True)
    consignment_rule = serializers.JSONField(required=False, allow_null=True)
    lines = ReceiptLineInputSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


# === Lot ===

class LotStockSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = LotStock
        fields = ['id', 'warehouse', 'warehouse_name', 'quantity_remaining']
        read_only_fields = ['id']


class LotSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(
        source='product_variant.__str__', read_only=True,
    )
    receipt_type = serializers.CharField(
        source='receipt.receipt_type', read_only=True, default=None,
    )
    stocks = LotStockSerializer(many=True, read_only=True)
    quantity_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Lot
        fields = [
            'id', 'receipt', 'procurement_item', 'product_variant', 'product_variant_name',
            'receipt_type', 'quantity_initial', 'quantity_remaining',
            'unit_purchase_price', 'landed_cost_per_unit',
            'contract_snapshot', 'received_at',
            'is_active', 'stocks', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_quantity_remaining(self, obj):
        return sum(s.quantity_remaining for s in obj.stocks.all())


# === Stock Movement ===

class StockMovementSerializer(serializers.ModelSerializer):
    from_location_name = serializers.CharField(
        source='from_location.name', read_only=True, default=None,
    )
    to_location_name = serializers.CharField(
        source='to_location.name', read_only=True, default=None,
    )

    class Meta:
        model = StockMovement
        fields = [
            'id', 'lot', 'movement_type', 'quantity',
            'from_location', 'from_location_name',
            'to_location', 'to_location_name',
            'reference_type', 'reference_id',
            'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# === Transfer ===

class TransferSerializer(serializers.Serializer):
    lot_id = serializers.IntegerField()
    from_warehouse_id = serializers.IntegerField()
    to_warehouse_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        if attrs['from_warehouse_id'] == attrs['to_warehouse_id']:
            raise serializers.ValidationError({
                'to_warehouse_id': 'Склад назначения должен отличаться от склада отправления.',
            })
        return attrs


# === Stock Summary ===

class StockSummarySerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField(source='lot__product_variant_id')
    product_name = serializers.CharField(source='lot__product_variant__product__name')
    warehouse_id = serializers.IntegerField()
    warehouse_name = serializers.CharField(source='warehouse__name')
    total_quantity = serializers.IntegerField()
    total_landed_cost = serializers.DecimalField(max_digits=20, decimal_places=2)
