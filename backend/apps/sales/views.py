"""
Sales API views — POS sessions, sales, returns.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsCashier

from .models import Sale, SaleLine, SaleReturn, PosSession
from .serializers import (
    PosSessionSerializer, OpenSessionSerializer, CloseSessionSerializer,
    SaleListSerializer, SaleDetailSerializer, SaleCreateSerializer,
    SaleReturnSerializer, SaleReturnCreateSerializer,
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
        if self.action in ('list', 'retrieve'):
            return [IsCashier()]
        return [IsCashier()]

    def get_queryset(self):
        qs = PosSession.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('location', 'opened_by', 'closed_by')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

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

        session = open_pos_session(
            tenant_id=request.tenant_id,
            location_id=data['location_id'],
            opened_by_id=request.user.pk,
            opening_cash=data['opening_cash'],
        )
        output = PosSessionSerializer(session)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close')
    def close_session(self, request, pk=None):
        """Close a POS session with cash reconciliation."""
        session = self.get_object()
        serializer = CloseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = close_pos_session(
            session=session,
            closed_by_id=request.user.pk,
            actual_cash=serializer.validated_data['actual_cash'],
        )
        output = PosSessionSerializer(session)
        return Response(output.data)


class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    """Sale CRUD — create via service, read via serializers."""

    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashier()]
        return [IsCashier()]

    def get_queryset(self):
        qs = Sale.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('customer', 'pos_session', 'sold_by')

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'lines__product_variant',
                'lines__lot',
                'lines__discount_reason',
            )

        # Filters
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(pos_session_id=session_id)

        payment = self.request.query_params.get('payment_method')
        if payment:
            qs = qs.filter(payment_method=payment)

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

        sale = create_sale(
            tenant_id=request.tenant_id,
            pos_session_id=data['pos_session_id'],
            sold_by_id=request.user.pk,
            payment_method=data['payment_method'],
            customer_id=data.get('customer_id'),
            lines=[dict(line) for line in data['lines']],
            client_request_id=str(data['client_request_id']) if data.get('client_request_id') else None,
            notes=data.get('notes', ''),
            operation_currency=data.get('operation_currency', 'UZS'),
            operation_amount=data.get('operation_amount'),
            fx_rate_snapshot=data.get('fx_rate_snapshot'),
            functional_amount_uzs=data.get('functional_amount_uzs'),
        )

        output = SaleDetailSerializer(sale)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='return')
    def process_return(self, request, pk=None):
        """Process a return for a completed sale."""
        sale = self.get_object()
        serializer = SaleReturnCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sale_return = process_return(
            sale=sale,
            return_lines=[dict(line) for line in data['lines']],
            processed_by_id=request.user.pk,
            tenant_id=request.tenant_id,
            notes=data.get('notes', ''),
        )

        output = SaleReturnSerializer(sale_return)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='returns')
    def list_returns(self, request, pk=None):
        """List returns for a specific sale."""
        sale = self.get_object()
        returns = SaleReturn.objects.filter(
            sale=sale,
        ).prefetch_related('lines__sale_line')
        serializer = SaleReturnSerializer(returns, many=True)
        return Response(serializer.data)
