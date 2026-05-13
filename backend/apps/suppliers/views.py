"""
Suppliers API views.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .models import (
    Supplier,
    SupplierPayment,
    SupplierPayable,
    ConsignmentAgreement,
)
from .serializers import (
    SupplierSerializer, SupplierCreateSerializer,
    SupplierPaymentSerializer, SupplierPaymentCreateSerializer,
    SupplierPayableSerializer, PayablePaymentCreateSerializer,
    ConsignmentAgreementSerializer,
)
from .services import (
    record_supplier_payment,
    record_payable_payment,
    get_supplier_payables_summary,
)


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

    @action(detail=True, methods=['get'], url_path='products')
    def products(self, request, pk=None):
        """E02 — list product variants that have been received from this supplier."""
        from apps.catalog.models import ProductSupplier
        supplier = self.get_object()
        links = (
            ProductSupplier.objects
            .filter(tenant_id=request.tenant_id, supplier=supplier)
            .select_related('product_variant', 'product_variant__product')
            .order_by('-last_received_at')
        )
        data = [
            {
                'product_variant_id': link.product_variant_id,
                'product_id': link.product_variant.product_id,
                'product_name': link.product_variant.product.name,
                'variant_sku': link.product_variant.sku,
                'last_received_at': link.last_received_at,
                'last_unit_price': str(link.last_unit_price),
                'last_currency': link.last_currency,
                'total_received_quantity': str(link.total_received_quantity),
                'total_received_value_uzs': str(link.total_received_value_uzs),
                'total_procurements_count': link.total_procurements_count,
            }
            for link in links
        ]
        return Response(data)


class SupplierPayableViewSet(viewsets.ReadOnlyModelViewSet):
    """
    E01 — Read-only listing of supplier payables.

    Filters:
      - status: comma-separated list (OPEN,PARTIALLY_PAID,FULLY_PAID,CANCELLED)
      - supplier: supplier_id
      - burning_in: integer days — payables with deadline within N days from now
      - overdue: 'true' — only payables whose deadline_date < today
    """

    serializer_class = SupplierPayableSerializer
    permission_classes = [IsOwner]
    ordering = ['deadline_date', '-created_at']

    def get_queryset(self):
        qs = (
            SupplierPayable.objects
            .filter(tenant_id=self.request.tenant_id)
            .select_related('supplier', 'procurement', 'procurement__terms')
            .prefetch_related('procurement__terms__schedule_entries')
        )

        statuses = self.request.query_params.get('status')
        if statuses:
            qs = qs.filter(status__in=[s.strip() for s in statuses.split(',') if s.strip()])
        else:
            # Default: open payables only (anything except cancelled+fully_paid)
            qs = qs.exclude(status__in=[
                SupplierPayable.Status.CANCELLED,
                SupplierPayable.Status.FULLY_PAID,
            ])

        supplier_id = self.request.query_params.get('supplier')
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)

        burning_in = self.request.query_params.get('burning_in')
        if burning_in:
            try:
                days = int(burning_in)
                cutoff = timezone.now().date() + timedelta(days=days)
                qs = qs.filter(deadline_date__lte=cutoff)
            except (ValueError, TypeError):
                pass

        if (self.request.query_params.get('overdue', '').lower() == 'true'):
            today = timezone.now().date()
            qs = qs.filter(deadline_date__lt=today)

        return qs

    @action(detail=True, methods=['post'], url_path='pay')
    def pay(self, request, pk=None):
        """Record a multi-cash payment against this payable."""
        payable = self.get_object()
        serializer = PayablePaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payment = record_payable_payment(
                tenant_id=request.tenant_id,
                payable_id=payable.pk,
                allocations=[dict(a) for a in data['allocations']],
                payment_date=data.get('payment_date'),
                schedule_entry_id=data.get('schedule_entry_id'),
                notes=data.get('notes', ''),
                client_request_id=data.get('client_request_id'),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        output = SupplierPaymentSerializer(payment)
        return Response(output.data, status=status.HTTP_201_CREATED)


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
