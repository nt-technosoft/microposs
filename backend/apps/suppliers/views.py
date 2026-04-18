"""
Suppliers API views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .models import Supplier, SupplierPayment, ConsignmentAgreement
from .serializers import (
    SupplierSerializer, SupplierCreateSerializer,
    SupplierPaymentSerializer, SupplierPaymentCreateSerializer,
    ConsignmentAgreementSerializer,
)
from .services import record_supplier_payment, get_supplier_payables_summary


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsOwner]
    search_fields = ['name', 'contact_person', 'phone']
    ordering = ['name']

    def get_queryset(self):
        qs = Supplier.objects.filter(tenant_id=self.request.tenant_id)

        active_only = self.request.query_params.get('active', 'true')
        if active_only.lower() == 'true':
            qs = qs.filter(is_active=True)

        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return SupplierCreateSerializer
        return SupplierSerializer

    def create(self, request, *args, **kwargs):
        serializer = SupplierCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        supplier = Supplier.objects.create(
            tenant_id=request.tenant_id,
            **serializer.validated_data,
        )
        output = SupplierSerializer(supplier)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """Record a payment to this supplier."""
        supplier = self.get_object()
        serializer = SupplierPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = record_supplier_payment(
            tenant_id=request.tenant_id,
            supplier_id=supplier.pk,
            amount=data['amount'],
            payment_method=data['payment_method'],
            operation_currency=data.get('operation_currency', 'UZS'),
            operation_amount=data.get('operation_amount'),
            fx_rate_snapshot=data.get('fx_rate_snapshot'),
            functional_amount_uzs=data.get('functional_amount_uzs'),
            notes=data.get('notes', ''),
        )
        output = SupplierPaymentSerializer(payment)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='payments')
    def payments(self, request, pk=None):
        """List all payments to this supplier."""
        supplier = self.get_object()
        payments = SupplierPayment.objects.filter(
            supplier=supplier,
        ).order_by('-date')
        serializer = SupplierPaymentSerializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='payables-summary')
    def payables_summary(self, request):
        """Get all suppliers with outstanding payables."""
        data = get_supplier_payables_summary(request.tenant_id)
        return Response(data)


class ConsignmentAgreementViewSet(viewsets.ModelViewSet):
    serializer_class = ConsignmentAgreementSerializer
    permission_classes = [IsOwner]
    ordering = ['-created_at']

    def get_queryset(self):
        qs = ConsignmentAgreement.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('supplier')

        supplier_id = self.request.query_params.get('supplier')
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)

        return qs

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)
