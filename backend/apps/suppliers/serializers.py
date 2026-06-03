"""
Suppliers serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import (
    Supplier,
    SupplierPayment,
    SupplierPayable,
    PaymentSchedule,
    ConsignmentAgreement,
)


class SupplierSerializer(serializers.ModelSerializer):
    outstanding_balance = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
    )

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'phone', 'email',
            'address', 'outstanding_balance', 'is_active', 'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'outstanding_balance', 'created_at']


class SupplierCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    contact_person = serializers.CharField(max_length=255, required=False, default='')
    phone = serializers.CharField(max_length=50, required=False, default='')
    email = serializers.EmailField(required=False, default='')
    address = serializers.CharField(required=False, default='', allow_blank=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(
        source='supplier.name', read_only=True,
    )

    class Meta:
        model = SupplierPayment
        fields = [
            'id', 'supplier', 'supplier_name',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'fx_rate_source', 'fx_rate_date',
            'functional_amount_uzs',
            'amount', 'payment_method', 'date', 'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class SupplierPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )
    payment_method = serializers.ChoiceField(choices=['cash', 'bank'])
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
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ConsignmentAgreementSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(
        source='supplier.name', read_only=True,
    )

    class Meta:
        model = ConsignmentAgreement
        fields = [
            'id', 'supplier', 'supplier_name',
            'rule_type', 'rule_value',
            'damage_liability_on_business',
            'is_active', 'notes',
        ]
        read_only_fields = ['id']


# =========================================================================
# E01 — Payable, PaymentSchedule, multi-cash payment serializers
# =========================================================================


class PaymentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSchedule
        fields = [
            'id', 'procurement_terms', 'sequence_number',
            'due_date', 'amount', 'currency',
            'status', 'paid_at', 'paid_amount',
        ]
        read_only_fields = ['id', 'paid_at', 'paid_amount', 'status']


class SupplierPayableSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    schedule = serializers.SerializerMethodField()
    paid_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
    )
    remaining_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
    )

    class Meta:
        model = SupplierPayable
        fields = [
            'id', 'supplier', 'supplier_name', 'procurement',
            'original_amount', 'paid_amount', 'remaining_amount',
            'currency_of_obligation', 'fx_rate_at_obligation',
            'status', 'reason', 'deadline_date', 'notes',
            'schedule', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'paid_amount', 'remaining_amount',
        ]

    def get_schedule(self, obj):
        terms = getattr(getattr(obj, 'procurement', None), 'terms', None)
        if terms is None:
            return []
        entries = terms.schedule_entries.all().order_by('sequence_number')
        return PaymentScheduleSerializer(entries, many=True).data


class PaymentAllocationSerializer(serializers.Serializer):
    """One slice of a multi-cash supplier payment."""
    cash_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'))
    currency = serializers.CharField(max_length=3, default='UZS')


class PayablePaymentCreateSerializer(serializers.Serializer):
    allocations = PaymentAllocationSerializer(many=True)
    payment_date = serializers.DateTimeField(required=False, allow_null=True)
    schedule_entry_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_allocations(self, value):
        if not value:
            raise serializers.ValidationError('At least one allocation is required.')
        return value
