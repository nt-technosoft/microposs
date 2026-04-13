"""
Customers API views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsCashier

from .models import Customer, CustomerPayment
from .serializers import (
    CustomerSerializer, CustomerCreateSerializer,
    CustomerPaymentSerializer, CustomerPaymentCreateSerializer,
)
from .services import record_customer_payment, get_customer_debt_summary


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    search_fields = ['name', 'phone']
    ordering = ['name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashier()]
        return [IsOwner()]

    def get_queryset(self):
        qs = Customer.objects.filter(tenant_id=self.request.tenant_id)

        active_only = self.request.query_params.get('active', 'true')
        if active_only.lower() == 'true':
            qs = qs.filter(is_active=True)

        has_debt = self.request.query_params.get('has_debt')
        if has_debt and has_debt.lower() == 'true':
            qs = qs.filter(outstanding_balance__gt=0)

        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return CustomerCreateSerializer
        return CustomerSerializer

    def create(self, request, *args, **kwargs):
        serializer = CustomerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = Customer.objects.create(
            tenant_id=request.tenant_id,
            **data,
        )
        output = CustomerSerializer(customer)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """Record a debt payment for this customer."""
        customer = self.get_object()
        serializer = CustomerPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = record_customer_payment(
            tenant_id=request.tenant_id,
            customer_id=customer.pk,
            amount=data['amount'],
            payment_method=data['payment_method'],
            notes=data.get('notes', ''),
        )
        output = CustomerPaymentSerializer(payment)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='payments')
    def payments(self, request, pk=None):
        """List all payments for this customer."""
        customer = self.get_object()
        payments = CustomerPayment.objects.filter(
            customer=customer,
        ).order_by('-date')
        serializer = CustomerPaymentSerializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='debt-summary')
    def debt_summary(self, request):
        """Get all customers with outstanding debt."""
        data = get_customer_debt_summary(request.tenant_id)
        return Response(data)
