"""
Sales serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import Sale, SaleLine, SalePayment, Return, ReturnLine, PosSession
from .currency import payment_functional_amount_uzs


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _currency_map(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for currency, amount in value.items():
        normalized = str(currency or '').upper()
        if not normalized:
            continue
        result[normalized] = str(_money(amount or '0'))
    return result


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal('0.00')
    return ((numerator / denominator) * Decimal('100')).quantize(Decimal('0.01'))


def _line_investor_profit(line: SaleLine) -> Decimal:
    snapshot = line.profit_distribution_snapshot or {}
    contract_snapshot = line.lot.contract_snapshot or {}
    partner_roles = {
        str(meta.get('partner_id')): meta.get('role')
        for meta in contract_snapshot.get('partners', []) or []
        if meta.get('partner_id') is not None
    }
    return sum(
        (
            Decimal(str(amount))
            for partner_id, amount in snapshot.items()
            if partner_roles.get(str(partner_id)) == 'INVESTOR'
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))


# === POS Session ===

class PosSessionSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(
        source='location.name', read_only=True,
    )
    sales_count = serializers.IntegerField(read_only=True, default=0)
    cash_sales_total = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        default='0.00',
    )
    cash_sales_by_currency = serializers.SerializerMethodField()

    class Meta:
        model = PosSession
        fields = [
            'id', 'location', 'location_name', 'status',
            'sales_count', 'cash_sales_total',
            'cash_sales_by_currency',
            'opening_cash', 'expected_cash', 'actual_cash',
            'cash_difference', 'opened_by', 'closed_by',
            'opening_cash_by_currency', 'expected_cash_by_currency',
            'actual_cash_by_currency', 'cash_difference_by_currency',
            'opened_at', 'closed_at',
        ]
        read_only_fields = [
            'id', 'expected_cash', 'cash_difference',
            'opened_at', 'closed_at',
        ]

    def get_cash_sales_by_currency(self, obj):
        totals: dict[str, Decimal] = {}
        for payment in SalePayment.objects.filter(
            sale__pos_session=obj,
            sale__status__in=[
                Sale.SaleStatus.COMPLETED,
                Sale.SaleStatus.PARTIALLY_RETURNED,
                Sale.SaleStatus.RETURNED,
            ],
            method=SalePayment.Method.CASH,
        ):
            currency = str(payment.currency or 'UZS').upper()
            amount = payment.amount
            if payment.role == SalePayment.Role.REFUND:
                amount *= Decimal('-1')
            totals[currency] = totals.get(currency, Decimal('0.00')) + amount
        return {currency: str(_money(amount)) for currency, amount in sorted(totals.items())}


class OpenSessionSerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    opening_cash = serializers.DecimalField(
        max_digits=14, decimal_places=2, default=0, min_value=Decimal('0'),
    )
    opening_cash_by_currency = serializers.DictField(
        child=serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0')),
        required=False,
        default=dict,
    )

    def validate_opening_cash_by_currency(self, value):
        return _currency_map(value)


class CloseSessionSerializer(serializers.Serializer):
    actual_cash = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0'))
    actual_cash_by_currency = serializers.DictField(
        child=serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0')),
        required=False,
        default=dict,
    )

    def validate_actual_cash_by_currency(self, value):
        return _currency_map(value)


# === SalePayment ===

class SalePaymentSerializer(serializers.ModelSerializer):
    functional_amount_uzs = serializers.SerializerMethodField()

    class Meta:
        model = SalePayment
        fields = [
            'id', 'date', 'amount', 'currency', 'fx_rate',
            'fx_rate_source', 'fx_rate_date',
            'functional_amount_uzs', 'method', 'role', 'account_id',
        ]
        read_only_fields = ['id']

    def get_functional_amount_uzs(self, obj):
        return payment_functional_amount_uzs(obj)


class SalePaymentInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, default='UZS')
    fx_rate = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, allow_null=True,
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
            'operation_currency', 'operation_unit_price',
            'fx_rate_snapshot', 'fx_rate_source', 'fx_rate_date',
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
    operation_currency = serializers.CharField(max_length=3, required=False, default='UZS')
    operation_unit_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    fx_rate = serializers.DecimalField(
        max_digits=14,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    discount_reason_id = serializers.IntegerField(required=False, allow_null=True)


# === Sale ===

class SalePresentationMixin(serializers.ModelSerializer):
    payment_method = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    operation_currency = serializers.SerializerMethodField()
    operation_amount = serializers.SerializerMethodField()
    fx_rate_snapshot = serializers.SerializerMethodField()
    functional_amount_uzs = serializers.SerializerMethodField()

    def _get_incoming_payments(self, obj):
        return [
            payment for payment in obj.payments.all()
            if payment.role == SalePayment.Role.INCOMING
        ]

    def _get_incoming_payment(self, obj):
        payments = self._get_incoming_payments(obj)
        return payments[0] if payments else None

    def get_payment_methods(self, obj):
        methods = []
        for payment in self._get_incoming_payments(obj):
            if payment.method not in methods:
                methods.append(payment.method)
        return methods

    def get_payment_method(self, obj):
        methods = self.get_payment_methods(obj)
        return methods[0] if methods else None

    def get_operation_currency(self, obj):
        currencies = {
            str(payment.currency or 'UZS').upper()
            for payment in self._get_incoming_payments(obj)
        }
        if len(currencies) > 1:
            return 'MIXED'
        payment = self._get_incoming_payment(obj)
        return payment.currency if payment else 'UZS'

    def get_operation_amount(self, obj):
        payments = self._get_incoming_payments(obj)
        currencies = {str(payment.currency or 'UZS').upper() for payment in payments}
        if len(currencies) == 1:
            return sum((payment.amount for payment in payments), Decimal('0.00'))
        return obj.total_amount

    def get_fx_rate_snapshot(self, obj):
        payment = self._get_incoming_payment(obj)
        if payment:
            return payment.fx_rate
        return Decimal('1')

    def get_functional_amount_uzs(self, obj):
        payments = self._get_incoming_payments(obj)
        if not payments:
            return obj.total_amount
        return sum((payment_functional_amount_uzs(payment) for payment in payments), Decimal('0.00'))


class SaleListSerializer(SalePresentationMixin, serializers.ModelSerializer):
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
            'payment_method', 'payment_methods',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'paid_total', 'lines_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_lines_count(self, obj):
        return obj.lines.count()

    def get_paid_total(self, obj):
        return str(sum(
            payment_functional_amount_uzs(p) for p in obj.payments.all()
            if p.role == SalePayment.Role.INCOMING
        ))


class SaleDetailSerializer(SalePresentationMixin, serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(
        source='customer.name', read_only=True, default=None,
    )
    location_name = serializers.CharField(
        source='location.name', read_only=True,
    )
    purchase_cost = serializers.SerializerMethodField()
    landed_cost = serializers.SerializerMethodField()
    gross_profit = serializers.SerializerMethodField()
    investor_profit = serializers.SerializerMethodField()
    business_profit = serializers.SerializerMethodField()
    margin_percent = serializers.SerializerMethodField()
    markup_percent = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            'id', 'status', 'date',
            'location', 'location_name',
            'customer', 'customer_name',
            'pos_session', 'sold_by',
            'payment_method', 'payment_methods',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'total_amount', 'total_cogs',
            'purchase_cost', 'landed_cost',
            'gross_profit', 'investor_profit', 'business_profit',
            'margin_percent', 'markup_percent',
            'lines', 'payments', 'notes',
            'client_request_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def _get_lines(self, obj) -> list[SaleLine]:
        cached_lines = getattr(obj, '_sale_profitability_lines_cache', None)
        if cached_lines is not None:
            return cached_lines

        prefetched = getattr(obj, '_prefetched_objects_cache', {}).get('lines')
        if prefetched is not None:
            cached_lines = list(prefetched)
        else:
            cached_lines = list(obj.lines.select_related('lot'))

        setattr(obj, '_sale_profitability_lines_cache', cached_lines)
        return cached_lines

    def get_purchase_cost(self, obj):
        total = sum(
            (
                Decimal(str(line.unit_purchase_price)) * Decimal(str(line.quantity))
                for line in self._get_lines(obj)
            ),
            Decimal('0.00'),
        )
        return _money(total)

    def get_landed_cost(self, obj):
        return _money(obj.total_cogs)

    def get_gross_profit(self, obj):
        return _money(Decimal(str(obj.total_amount)) - Decimal(str(obj.total_cogs)))

    def get_investor_profit(self, obj):
        total = sum(
            (_line_investor_profit(line) for line in self._get_lines(obj)),
            Decimal('0.00'),
        )
        return _money(total)

    def get_business_profit(self, obj):
        gross_profit = Decimal(str(self.get_gross_profit(obj)))
        investor_profit = Decimal(str(self.get_investor_profit(obj)))
        return _money(gross_profit - investor_profit)

    def get_margin_percent(self, obj):
        gross_profit = Decimal(str(self.get_gross_profit(obj)))
        revenue = _money(obj.total_amount)
        return _percent(gross_profit, revenue)

    def get_markup_percent(self, obj):
        gross_profit = Decimal(str(self.get_gross_profit(obj)))
        landed_cost = _money(obj.total_cogs)
        return _percent(gross_profit, landed_cost)


class SaleCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    pos_session_id = serializers.IntegerField()
    location_id = serializers.IntegerField(required=False, allow_null=True)
    date = serializers.DateTimeField(required=False)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    lines = SaleLineInputSerializer(many=True)
    payments = SalePaymentInputSerializer(many=True, required=False, default=list)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


# === Returns ===

class ReturnLineSerializer(serializers.ModelSerializer):
    sale_line_id = serializers.IntegerField(source='sale_line.id', read_only=True)
    product_name = serializers.CharField(source='sale_line.product_variant.product.name', read_only=True)

    class Meta:
        model = ReturnLine
        fields = ['id', 'sale_line', 'sale_line_id', 'product_name', 'quantity']
        read_only_fields = ['id']


class ReturnSerializer(serializers.ModelSerializer):
    lines = ReturnLineSerializer(many=True, read_only=True)
    refunds = serializers.SerializerMethodField()
    total_refund_amount = serializers.SerializerMethodField()

    class Meta:
        model = Return
        fields = [
            'id', 'sale', 'processed_by',
            'resolution', 'reason', 'date',
            'lines', 'refunds', 'total_refund_amount',
            'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_refunds(self, obj):
        return [
            {
                'id': refund.id,
                'amount': str(_money(refund.amount)),
                'currency': refund.currency,
                'fx_rate': str(refund.fx_rate),
                'method': refund.method,
                'account_id': refund.account_id,
            }
            for refund in obj.refunds.all()
        ]

    def get_total_refund_amount(self, obj):
        total = sum((refund.amount for refund in obj.refunds.all()), Decimal('0'))
        return str(_money(total))


class ReturnInputLineSerializer(serializers.Serializer):
    sale_line_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class ReturnRefundPaymentSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=[
        SalePayment.Method.CASH,
        SalePayment.Method.CARD,
        SalePayment.Method.TRANSFER,
        SalePayment.Method.CREDIT,
        'RECEIVABLE_OFFSET',
    ])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(required=False, default='UZS', max_length=3)
    fx_rate = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, allow_null=True,
    )
    account_id = serializers.IntegerField(required=False, allow_null=True)


class ReturnCreateSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=Return.Resolution.choices)
    reason = serializers.ChoiceField(
        choices=Return.Reason.choices,
        required=False,
        default=Return.Reason.CLIENT_REFUSE,
    )
    lines = ReturnInputLineSerializer(many=True, required=False, default=list)
    refund_payments = ReturnRefundPaymentSerializer(many=True, required=False, default=list)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
