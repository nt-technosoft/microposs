"""
Finance API views — accounts, journal entries, summaries.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .models import Account, JournalEntry, DailySummary, CashFlowSummary
from .serializers import (
    AccountSerializer, AccountCreateSerializer,
    JournalEntryListSerializer, JournalEntryDetailSerializer,
    DailySummarySerializer, CashFlowSummarySerializer,
    TrialBalanceSerializer,
)
from .services import get_trial_balance
from .chart_of_accounts import setup_chart_of_accounts


class AccountViewSet(viewsets.ModelViewSet):
    """Chart of Accounts management."""

    serializer_class = AccountSerializer
    permission_classes = [IsOwner]
    ordering = ['code']

    def get_queryset(self):
        qs = Account.objects.filter(
            tenant_id=self.request.tenant_id,
        )
        account_type = self.request.query_params.get('type')
        if account_type:
            qs = qs.filter(account_type=account_type)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return AccountCreateSerializer
        return AccountSerializer

    def create(self, request, *args, **kwargs):
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        account = Account.objects.create(
            tenant_id=request.tenant_id,
            code=data['code'],
            name=data['name'],
            account_type=data['account_type'],
            parent_id=data.get('parent_id'),
        )
        output = AccountSerializer(account)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.is_system:
            return Response(
                {'detail': 'System accounts cannot be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.soft_delete()

    @action(detail=False, methods=['post'], url_path='setup-default')
    def setup_default(self, request):
        """Initialize default chart of accounts for tenant."""
        created = setup_chart_of_accounts(request.tenant_id)
        return Response({
            'created_count': len(created),
            'message': f'{len(created)} accounts created.',
        })

    @action(detail=False, methods=['get'], url_path='trial-balance')
    def trial_balance(self, request):
        """Get trial balance for all active accounts."""
        data = get_trial_balance(request.tenant_id)
        serializer = TrialBalanceSerializer(data, many=True)
        return Response(serializer.data)


class JournalEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only journal entries. Created automatically by services."""

    permission_classes = [IsOwner]
    ordering = ['-date']

    def get_queryset(self):
        qs = JournalEntry.objects.filter(
            tenant_id=self.request.tenant_id,
        )

        if self.action == 'retrieve':
            qs = qs.prefetch_related('lines__account')

        op_type = self.request.query_params.get('operation_type')
        if op_type:
            qs = qs.filter(operation_type=op_type)

        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return JournalEntryDetailSerializer
        return JournalEntryListSerializer


class DailySummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """Pre-aggregated daily P&L summaries."""

    serializer_class = DailySummarySerializer
    permission_classes = [IsOwner]
    ordering = ['-date']

    def get_queryset(self):
        qs = DailySummary.objects.filter(
            tenant_id=self.request.tenant_id,
        )

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class CashFlowSummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """Pre-aggregated daily cash flow summaries."""

    serializer_class = CashFlowSummarySerializer
    permission_classes = [IsOwner]
    ordering = ['-date']

    def get_queryset(self):
        qs = CashFlowSummary.objects.filter(
            tenant_id=self.request.tenant_id,
        )

        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs
