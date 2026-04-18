"""
Sales serializers.
"""

from rest_framework import serializers
from .models import Sale, SaleLine, SaleReturn, SaleReturnLine, PosSession


# === POS Session ===

class PosSessionSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(
        source='location.name', read_only=True,
    )

    class Meta:
        model = PosSession
        fields = [
            'id', 'location', 'location_name', 'status',
            'opening_cash', 'expected_cash', 'actual_cash',
            'cash_difference', 'opened_by', 'closed_by',
            'opened_at', 'closed_at',
        ]
        read_only_fields = [
            'id', 'expected_cash', 'cash_difference',
            'opened_at', 'closed_at',
        ]


class OpenSessionSerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    opening_cash = serializers.DecimalField(
        max_digits=14, decimal_places=2, default=0,
    )


class CloseSessionSerializer(serializers.Serializer):
    actual_cash = serializers.DecimalField(max_digits=14, decimal_places=2)


# === Sale Lines ===

class SaleLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='product_variant.__str__', read_only=True,
    )
    total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
    )
    gross_profit = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
    )

    class Meta:
        model = SaleLine
        fields = [
            'id', 'lot', 'product_variant', 'product_name',
            'quantity', 'unit_price', 'base_price',
            'price_changed', 'discount_reason',
            'cost_per_unit', 'total', 'gross_profit',
        ]
        read_only_fields = ['id']


class SaleLineInputSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    lot_id = serializers.IntegerField(required=False, allow_null=True)
    discount_reason_id = serializers.IntegerField(required=False, allow_null=True)


# === Sale ===

class SaleListSerializer(serializers.ModelSerializer):
    lines_count = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            'id', 'status', 'payment_method', 'customer',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'total_amount', 'lines_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_lines_count(self, obj):
        return obj.lines.count()


class SaleDetailSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(
        source='customer.name', read_only=True, default=None,
    )

    class Meta:
        model = Sale
        fields = [
            'id', 'status', 'payment_method',
            'customer', 'customer_name',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'total_amount', 'total_cogs',
            'customer_has_existing_debt',
            'pos_session', 'sold_by',
            'lines', 'notes',
            'client_request_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SaleCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    pos_session_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=['cash', 'card', 'credit'])
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    operation_currency = serializers.CharField(max_length=3, required=False, default='UZS')
    operation_amount = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    fx_rate_snapshot = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    functional_amount_uzs = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    lines = SaleLineInputSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


# === Returns ===

class SaleReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleReturnLine
        fields = ['id', 'sale_line', 'quantity', 'condition']
        read_only_fields = ['id']


class SaleReturnSerializer(serializers.ModelSerializer):
    lines = SaleReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = SaleReturn
        fields = ['id', 'sale', 'processed_by', 'lines', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']


class SaleReturnInputLineSerializer(serializers.Serializer):
    sale_line_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    condition = serializers.ChoiceField(choices=['good', 'damaged'])


class SaleReturnCreateSerializer(serializers.Serializer):
    lines = SaleReturnInputLineSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
