"""
Customers serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import Customer, CustomerPayment, Receivable, ReceivableEntry


class ReceivableEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceivableEntry
        fields = [
            'id', 'date', 'amount', 'currency',
            'fx_rate', 'fx_rate_source', 'fx_rate_date',
            'entry_type', 'due_date', 'source_ref',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ReceivableSerializer(serializers.ModelSerializer):
    balance_uzs = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
    )

    class Meta:
        model = Receivable
        fields = ['id', 'customer', 'balances', 'balance_uzs']
        read_only_fields = ['id']


class CustomerSerializer(serializers.ModelSerializer):
    outstanding_balance = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True,
    )

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
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = CustomerPayment
        fields = [
            'id', 'customer', 'customer_name',
            'amount', 'currency', 'fx_rate', 'fx_rate_source', 'fx_rate_date',
            'payment_method', 'date', 'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CustomerPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.01'),
    )
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(
        max_digits=14, decimal_places=6, required=False, allow_null=True,
    )
    payment_method = serializers.ChoiceField(choices=['cash', 'bank'])
    account_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
