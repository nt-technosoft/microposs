"""
Finance API views — accounts, journal entries, summaries.
"""

from datetime import timedelta
from datetime import date as date_cls

from django.core.cache import cache
from django.db.models import Max, Min
from django.db.utils import OperationalError
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.analytics.tasks import aggregate_daily_pnl
from apps.core.permissions import IsOwner
from apps.customers.models import CustomerPayment
from apps.inventory.models import Receipt
from apps.sales.models import Sale
from apps.suppliers.models import SupplierPayment

from .models import (
    Account,
    JournalEntry,
    Expense,
    DailySummary,
    CashFlowSummary,
    ExchangeRate,
    CashAccount,
    CashEntry,
    CurrencyExchange,
    Refund,
    OwnerContribution,
)
from .serializers import (
    AccountSerializer, AccountCreateSerializer,
    JournalEntryListSerializer, JournalEntryDetailSerializer,
    ExpenseSerializer, ExpenseCreateSerializer,
    DailySummarySerializer, CashFlowSummarySerializer,
    TrialBalanceSerializer,
    ExchangeRateSerializer,
    ExchangeRateManualCreateSerializer,
    ExchangeRateRefreshSerializer,
    CashAccountSerializer, CashAccountCreateSerializer,
    CashEntrySerializer, CurrencyExchangeSerializer, CurrencyExchangeCreateSerializer,
    RefundSerializer, RefundCreateSerializer,
    OwnerContributionSerializer, OwnerContributionCreateSerializer,
)
from .services import (
    get_trial_balance,
    record_expense,
    upsert_exchange_rate,
    sync_official_exchange_rate,
    get_fx_rate_for_date,
    exchange_currency,
    refund_customer,
    record_owner_contribution,
)
from .chart_of_accounts import setup_chart_of_accounts


def _resolve_operation_window(
    tenant_id: int,
    *,
    date_from_raw: str | None,
    date_to_raw: str | None,
) -> tuple[timezone.datetime.date | None, timezone.datetime.date | None]:
    """Resolve requested window or fallback to full operation history."""
    parsed_from = parse_date(date_from_raw) if date_from_raw else None
    parsed_to = parse_date(date_to_raw) if date_to_raw else None

    if parsed_from and parsed_to and parsed_from > parsed_to:
        parsed_from, parsed_to = parsed_to, parsed_from

    if parsed_from and parsed_to:
        return parsed_from, parsed_to

    candidates: list[timezone.datetime.date] = []
    min_max = [
        Sale.objects.filter(tenant_id=tenant_id, status='completed').aggregate(
            min_dt=Min('created_at'),
            max_dt=Max('created_at'),
        ),
        Receipt.objects.filter(tenant_id=tenant_id, status='confirmed').aggregate(
            min_dt=Min('date'),
            max_dt=Max('date'),
        ),
        CustomerPayment.objects.filter(tenant_id=tenant_id).aggregate(
            min_dt=Min('date'),
            max_dt=Max('date'),
        ),
        SupplierPayment.objects.filter(tenant_id=tenant_id).aggregate(
            min_dt=Min('date'),
            max_dt=Max('date'),
        ),
        Expense.objects.filter(tenant_id=tenant_id).aggregate(
            min_dt=Min('occurred_at'),
            max_dt=Max('occurred_at'),
        ),
    ]

    for mm in min_max:
        if mm['min_dt']:
            candidates.append(mm['min_dt'].date())
        if mm['max_dt']:
            candidates.append(mm['max_dt'].date())

    if not candidates:
        return parsed_from, parsed_to

    data_min = min(candidates)
    data_max = max(candidates)
    return parsed_from or data_min, parsed_to or data_max


def _ensure_finance_aggregates(
    tenant_id: int,
    *,
    date_from_raw: str | None,
    date_to_raw: str | None,
) -> tuple[timezone.datetime.date | None, timezone.datetime.date | None]:
    """
    Ensure daily finance aggregates exist for requested date range.
    Runs synchronously in API request path for deterministic demo behavior.
    """
    date_from, date_to = _resolve_operation_window(
        tenant_id,
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
    )
    if not date_from or not date_to:
        return date_from, date_to

    span_days = (date_to - date_from).days
    if span_days > 1825:  # Safety cap: 5 years
        date_from = date_to - timedelta(days=1825)

    warmup_key = f'finance:agg:warm:{tenant_id}:{date_from.isoformat()}:{date_to.isoformat()}'
    if cache.get(warmup_key):
        return date_from, date_to

    lock_key = f'finance:agg:lock:{tenant_id}'
    lock_token = str(timezone.now().timestamp())
    lock_acquired = cache.add(lock_key, lock_token, timeout=45)
    if not lock_acquired:
        # Another request is already warming aggregates. Return current data instead of failing.
        return date_from, date_to

    try:
        cursor = date_from
        while cursor <= date_to:
            aggregate_daily_pnl.run(tenant_id, cursor.isoformat())
            cursor += timedelta(days=1)
        cache.set(warmup_key, True, timeout=30)
    except OperationalError:
        # SQLite in dev can briefly lock on parallel writes; fail-open for read APIs.
        return date_from, date_to
    finally:
        if cache.get(lock_key) == lock_token:
            cache.delete(lock_key)

    return date_from, date_to


class CashAccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    ordering = ['name']

    def get_queryset(self):
        return CashAccount.objects.filter(tenant_id=self.request.tenant_id)

    def get_serializer_class(self):
        if self.action == 'create':
            return CashAccountCreateSerializer
        return CashAccountSerializer

    def create(self, request, *args, **kwargs):
        serializer = CashAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = CashAccount.objects.create(
            tenant_id=request.tenant_id,
            name=data['name'],
            currency=data['currency'].upper(),
            kind=data['kind'],
            linked_account_id=data.get('linked_account_id'),
        )
        return Response(CashAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class CashEntryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CashEntrySerializer
    permission_classes = [IsOwner]
    ordering = ['-date', '-id']

    def get_queryset(self):
        queryset = CashEntry.objects.filter(tenant_id=self.request.tenant_id).select_related('account')
        account_id = self.request.query_params.get('account')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        return queryset


class CurrencyExchangeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    ordering = ['-date', '-id']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return CurrencyExchange.objects.filter(tenant_id=self.request.tenant_id).select_related('from_account', 'to_account')

    def get_serializer_class(self):
        if self.action == 'create':
            return CurrencyExchangeCreateSerializer
        return CurrencyExchangeSerializer

    def create(self, request, *args, **kwargs):
        serializer = CurrencyExchangeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        exchange = exchange_currency(
            tenant_id=request.tenant_id,
            from_account_id=data['from_account_id'],
            to_account_id=data['to_account_id'],
            from_amount=data['from_amount'],
            rate=data['rate'],
            notes=data.get('notes', ''),
        )
        return Response(CurrencyExchangeSerializer(exchange).data, status=status.HTTP_201_CREATED)


class RefundViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    ordering = ['-date', '-id']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return Refund.objects.filter(tenant_id=self.request.tenant_id).select_related('customer', 'account', 'return_ref')

    def get_serializer_class(self):
        if self.action == 'create':
            return RefundCreateSerializer
        return RefundSerializer

    def create(self, request, *args, **kwargs):
        serializer = RefundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refund = refund_customer(
            tenant_id=request.tenant_id,
            customer_id=data['customer_id'],
            sale_id=data['sale_id'],
            amount=data['amount'],
            currency=data['currency'],
            fx_rate=data['fx_rate'],
            method=data['method'],
            account_id=data.get('account_id'),
            return_ref_id=data.get('return_ref_id'),
        )
        return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


class OwnerContributionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    ordering = ['-date', '-id']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return OwnerContribution.objects.filter(tenant_id=self.request.tenant_id).select_related('to_account')

    def get_serializer_class(self):
        if self.action == 'create':
            return OwnerContributionCreateSerializer
        return OwnerContributionSerializer

    def create(self, request, *args, **kwargs):
        serializer = OwnerContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        contribution = record_owner_contribution(
            tenant_id=request.tenant_id,
            amount=data['amount'],
            currency=data['currency'],
            to_account_id=data['to_account_id'],
            notes=data.get('notes', ''),
        )
        return Response(OwnerContributionSerializer(contribution).data, status=status.HTTP_201_CREATED)


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


class ExpenseViewSet(viewsets.ModelViewSet):
    """Owner-managed non-supplier expense operations."""

    permission_classes = [IsOwner]
    ordering = ['-occurred_at', '-id']

    def get_queryset(self):
        qs = Expense.objects.filter(
            tenant_id=self.request.tenant_id,
        )
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return ExpenseCreateSerializer
        return ExpenseSerializer

    def create(self, request, *args, **kwargs):
        serializer = ExpenseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        expense = record_expense(
            tenant_id=request.tenant_id,
            title=data['title'],
            category=data.get('category', ''),
            payment_method=data['payment_method'],
            operation_currency=data.get('operation_currency', 'UZS'),
            operation_amount=data['operation_amount'],
            fx_rate_snapshot=data.get('fx_rate_snapshot'),
            functional_amount_uzs=data.get('functional_amount_uzs'),
            source_account_code=data.get('source_account_code') or None,
            occurred_at=data['occurred_at'],
            notes=data.get('notes', ''),
        )
        output = ExpenseSerializer(expense)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.soft_delete()


class DailySummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """Pre-aggregated daily P&L summaries."""

    serializer_class = DailySummarySerializer
    permission_classes = [IsOwner]
    pagination_class = None
    ordering = ['-date']

    def get_queryset(self):
        date_from_raw = self.request.query_params.get('date_from')
        date_to_raw = self.request.query_params.get('date_to')
        date_from, date_to = _ensure_finance_aggregates(
            self.request.tenant_id,
            date_from_raw=date_from_raw,
            date_to_raw=date_to_raw,
        )

        qs = DailySummary.objects.filter(
            tenant_id=self.request.tenant_id,
        )
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class CashFlowSummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """Pre-aggregated daily cash flow summaries."""

    serializer_class = CashFlowSummarySerializer
    permission_classes = [IsOwner]
    pagination_class = None
    ordering = ['-date']

    def get_queryset(self):
        date_from_raw = self.request.query_params.get('date_from')
        date_to_raw = self.request.query_params.get('date_to')
        date_from, date_to = _ensure_finance_aggregates(
            self.request.tenant_id,
            date_from_raw=date_from_raw,
            date_to_raw=date_to_raw,
        )

        qs = CashFlowSummary.objects.filter(
            tenant_id=self.request.tenant_id,
        )
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class ExchangeRateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Tenant FX history with manual override and official refresh action.
    """

    serializer_class = ExchangeRateSerializer
    permission_classes = [IsOwner]
    ordering = ['-rate_date', '-updated_at']

    def get_queryset(self):
        qs = ExchangeRate.objects.filter(tenant_id=self.request.tenant_id)
        base = self.request.query_params.get('base_currency')
        quote = self.request.query_params.get('quote_currency')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if base:
            qs = qs.filter(base_currency=base.upper())
        if quote:
            qs = qs.filter(quote_currency=quote.upper())
        if date_from:
            qs = qs.filter(rate_date__gte=date_from)
        if date_to:
            qs = qs.filter(rate_date__lte=date_to)
        return qs

    @action(detail=False, methods=['post'], url_path='manual')
    def manual(self, request):
        serializer = ExchangeRateManualCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rate, _ = upsert_exchange_rate(
            tenant_id=request.tenant_id,
            base_currency=data['base_currency'],
            quote_currency=data['quote_currency'],
            rate_date=data['rate_date'],
            rate=data['rate'],
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes=data.get('notes', ''),
            raw_payload={},
            overwrite_manual=True,
        )
        return Response(ExchangeRateSerializer(rate).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='refresh-official')
    def refresh_official(self, request):
        serializer = ExchangeRateRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target_date = data.get('rate_date') or timezone.localdate()
        rate, created = sync_official_exchange_rate(
            tenant_id=request.tenant_id,
            base_currency=data['base_currency'],
            quote_currency=data['quote_currency'],
            rate_date=target_date,
            overwrite_manual=bool(data.get('overwrite_manual', False)),
        )
        return Response(
            {
                'created': created,
                'rate': ExchangeRateSerializer(rate).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path='latest')
    def latest(self, request):
        base = str(request.query_params.get('base_currency') or 'USD').upper()
        quote = str(request.query_params.get('quote_currency') or 'UZS').upper()
        on_date_raw = request.query_params.get('on_date')
        target_date: date_cls | None = None
        if on_date_raw:
            parsed = parse_date(on_date_raw)
            if parsed is not None:
                target_date = parsed
        row = get_fx_rate_for_date(
            tenant_id=request.tenant_id,
            base_currency=base,
            quote_currency=quote,
            rate_date=target_date,
        )
        if row is None:
            return Response(
                {'detail': f'Rate not found for {base}/{quote}.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ExchangeRateSerializer(row).data)
