"""
Suppliers serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import Supplier, SupplierPayment, ConsignmentAgreement


class SupplierSerializer(serializers.ModelSerializer):
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
            'fx_rate_snapshot', 'functional_amount_uzs',
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
