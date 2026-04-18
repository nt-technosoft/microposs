"""
Sales serializers.
"""

from rest_framework import serializers
from .models import Sale, SaleLine, SalePayment, Return, ReturnLine, PosSession


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


# === SalePayment ===

class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment
        fields = [
            'id', 'date', 'amount', 'currency', 'fx_rate',
            'method', 'role', 'account_id',
        ]
        read_only_fields = ['id']


class SalePaymentInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, default='UZS')
    fx_rate = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, default='1',
    )
    method = serializers.ChoiceField(choices=SalePayment.Method.choices)
    account_id = serializers.IntegerField(required=False, allow_null=True)


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
            'unit_purchase_price', 'unit_landed_cost',
            'profit_distribution_snapshot',
            'total', 'gross_profit',
        ]
        read_only_fields = ['id']


class SaleLineInputSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_reason_id = serializers.IntegerField(required=False, allow_null=True)


# === Sale ===

class SaleListSerializer(serializers.ModelSerializer):
    lines_count = serializers.SerializerMethodField()
    location_name = serializers.CharField(
        source='location.name', read_only=True,
    )
    paid_total = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            'id', 'status', 'date',
            'location', 'location_name',
            'customer', 'total_amount',
            'paid_total', 'lines_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_lines_count(self, obj):
        return obj.lines.count()

    def get_paid_total(self, obj):
        from decimal import Decimal
        return str(sum(
            p.amount for p in obj.payments.all()
            if p.role == SalePayment.Role.INCOMING
        ))


class SaleDetailSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(
        source='customer.name', read_only=True, default=None,
    )
    location_name = serializers.CharField(
        source='location.name', read_only=True,
    )

    class Meta:
        model = Sale
        fields = [
            'id', 'status', 'date',
            'location', 'location_name',
            'customer', 'customer_name',
            'pos_session', 'sold_by',
            'total_amount', 'total_cogs',
            'lines', 'payments', 'notes',
            'client_request_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SaleCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    pos_session_id = serializers.IntegerField()
    location_id = serializers.IntegerField()
    date = serializers.DateTimeField(required=False)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    lines = SaleLineInputSerializer(many=True)
    payments = SalePaymentInputSerializer(many=True, required=False, default=list)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


# === Returns ===

class ReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnLine
        fields = ['id', 'sale_line', 'quantity']
        read_only_fields = ['id']


class ReturnSerializer(serializers.ModelSerializer):
    lines = ReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = Return
        fields = [
            'id', 'sale', 'processed_by',
            'resolution', 'reason', 'date',
            'lines', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ReturnInputLineSerializer(serializers.Serializer):
    sale_line_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnCreateSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=Return.Resolution.choices)
    reason = serializers.ChoiceField(
        choices=Return.Reason.choices,
        required=False,
        default=Return.Reason.CLIENT_REFUSE,
    )
    lines = ReturnInputLineSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
