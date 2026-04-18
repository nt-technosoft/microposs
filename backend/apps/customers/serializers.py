"""
Customers serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import Customer, CustomerPayment


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email',
            'outstanding_balance', 'is_active', 'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'outstanding_balance', 'created_at']


class CustomerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=50, required=False, default='')
    email = serializers.EmailField(required=False, default='')
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class CustomerPaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(
        source='customer.name', read_only=True,
    )

    class Meta:
        model = CustomerPayment
        fields = [
            'id', 'customer', 'customer_name',
            'operation_currency', 'operation_amount',
            'fx_rate_snapshot', 'functional_amount_uzs',
            'amount', 'payment_method', 'date', 'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CustomerPaymentCreateSerializer(serializers.Serializer):
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
