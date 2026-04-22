"""
Sales API views — POS sessions, sales, returns.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.db.models import Count, Q, Sum, DecimalField
from django.db.models.functions import Coalesce

from apps.core.permissions import IsOwner, IsCashier

from .models import Sale, SaleLine, Return, PosSession, SalePayment
from .serializers import (
    PosSessionSerializer, OpenSessionSerializer, CloseSessionSerializer,
    SaleListSerializer, SaleDetailSerializer, SaleCreateSerializer,
    ReturnSerializer, ReturnCreateSerializer,
)
from .services import (
    create_sale, process_return,
    open_pos_session, close_pos_session,
)


class PosSessionViewSet(viewsets.ReadOnlyModelViewSet):
    """POS session management — open, close, list."""

    serializer_class = PosSessionSerializer
    ordering = ['-opened_at']

    def get_permissions(self):
        return [IsCashier()]

    def get_queryset(self):
        qs = PosSession.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('location', 'opened_by', 'closed_by').annotate(
            sales_count=Count(
                'sales',
                filter=Q(sales__status=Sale.SaleStatus.COMPLETED),
                distinct=True,
            ),
            cash_sales_total=Coalesce(
                Sum(
                    'sales__payments__amount',
                    filter=Q(
                        sales__status=Sale.SaleStatus.COMPLETED,
                        sales__payments__role=SalePayment.Role.INCOMING,
                        sales__payments__method=SalePayment.Method.CASH,
                    ),
                ),
                0,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
            if status_filter == PosSession.SessionStatus.OPEN:
                qs = qs.filter(opened_by=self.request.user)

        location_id = self.request.query_params.get('location')
        if location_id:
            qs = qs.filter(location_id=location_id)

        return qs

    @action(detail=False, methods=['post'], url_path='open')
    def open_session(self, request):
        """Open a new POS session."""
        serializer = OpenSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            session = open_pos_session(
                tenant_id=request.tenant_id,
                location_id=data['location_id'],
                opened_by_id=request.user.pk,
                opening_cash=data['opening_cash'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(PosSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close')
    def close_session(self, request, pk=None):
        """Close a POS session with cash reconciliation."""
        session = self.get_object()
        serializer = CloseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session = close_pos_session(
                session=session,
                closed_by_id=request.user.pk,
                actual_cash=serializer.validated_data['actual_cash'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(PosSessionSerializer(session).data)


class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    """Sale CRUD — create via service, read via serializers."""

    ordering = ['-created_at']

    def get_permissions(self):
        return [IsCashier()]

    def get_queryset(self):
        qs = Sale.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related(
            'customer', 'pos_session', 'sold_by', 'location',
        ).prefetch_related('payments')

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'lines__product_variant',
                'lines__lot',
                'lines__discount_reason',
            )

        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(pos_session_id=session_id)

        location_id = self.request.query_params.get('location')
        if location_id:
            qs = qs.filter(location_id=location_id)

        sale_status = self.request.query_params.get('status')
        if sale_status:
            qs = qs.filter(status=sale_status)

        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SaleDetailSerializer
        if self.action == 'create':
            return SaleCreateSerializer
        return SaleListSerializer

    def create(self, request, *args, **kwargs):
        """Create a new sale via service layer."""
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            sale = create_sale(
                tenant_id=request.tenant_id,
                pos_session_id=data['pos_session_id'],
                location_id=data.get('location_id'),
                sold_by_id=request.user.pk,
                customer_id=data.get('customer_id'),
                lines=[dict(line) for line in data['lines']],
                payments=[dict(p) for p in data.get('payments', [])],
                client_request_id=str(data['client_request_id']) if data.get('client_request_id') else None,
                notes=data.get('notes', ''),
                date=data.get('date'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error

        return Response(SaleDetailSerializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='return')
    def process_return_action(self, request, pk=None):
        """Process a return for a completed sale."""
        sale = self.get_object()
        serializer = ReturnCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        return_doc = process_return(
            sale=sale,
            return_lines=[dict(line) for line in data['lines']],
            resolution=data['resolution'],
            reason=data.get('reason', Return.Reason.CLIENT_REFUSE),
            processed_by_id=request.user.pk,
            tenant_id=request.tenant_id,
            notes=data.get('notes', ''),
        )

        return Response(ReturnSerializer(return_doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='returns')
    def list_returns(self, request, pk=None):
        """List returns for a specific sale."""
        sale = self.get_object()
        returns = Return.objects.filter(
            sale=sale,
        ).prefetch_related('lines__sale_line')
        return Response(ReturnSerializer(returns, many=True).data)
