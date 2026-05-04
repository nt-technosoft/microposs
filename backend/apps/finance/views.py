"""
Finance API views — accounts, journal entries, summaries.
"""

from datetime import timedelta
from datetime import date as date_cls

from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
from django.db.utils import OperationalError
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.tasks import aggregate_daily_pnl
from apps.core.permissions import IsOwner, IsInvestor
from apps.customers.models import CustomerPayment
from apps.inventory.models import Receipt
from apps.partnerships.models import Procurement
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
    SaleProfitabilitySerializer, ProductProfitabilitySerializer,
    ProcurementProfitabilitySerializer, ProcurementProfitabilityDetailSerializer,
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
    exchange_currency,
    refund_customer,
    record_owner_contribution,
    get_sales_profitability_rows,
    get_product_profitability_rows,
    get_procurement_profitability_rows,
    get_procurement_profitability_detail,
    get_agreement_profitability_detail,
)
from .fx_rates import get_fx_rate_for_date, sync_official_exchange_rate, upsert_exchange_rate
from .report_currency import ReportCurrencyError
from .chart_of_accounts import setup_chart_of_accounts


def _resolve_operation_window(
    tenant_id: int,
    *,
    date_from_raw: str | None,
    date_to_raw: str | None,
) -> tuple[date_cls | None, date_cls | None]:
    """Resolve requested window or fallback to full operation history (single UNION query)."""
    from django.db import connection

    parsed_from = parse_date(date_from_raw) if date_from_raw else None
    parsed_to = parse_date(date_to_raw) if date_to_raw else None

    if parsed_from and parsed_to and parsed_from > parsed_to:
        parsed_from, parsed_to = parsed_to, parsed_from

    if parsed_from and parsed_to:
        return parsed_from, parsed_to

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT MIN(dt), MAX(dt) FROM (
                    SELECT DATE(date) AS dt
                      FROM sales_sale
                     WHERE tenant_id = %s AND deleted_at IS NULL AND status = 'completed'
                    UNION ALL
                    SELECT DATE(date) AS dt
                      FROM inventory_receipt
                     WHERE tenant_id = %s AND deleted_at IS NULL AND status = 'confirmed'
                    UNION ALL
                    SELECT DATE(date) AS dt
                      FROM customers_payment
                     WHERE tenant_id = %s AND deleted_at IS NULL
                    UNION ALL
                    SELECT DATE(date) AS dt
                      FROM suppliers_payment
                     WHERE tenant_id = %s AND deleted_at IS NULL
                    UNION ALL
                    SELECT DATE(occurred_at) AS dt
                      FROM finance_expense
                     WHERE tenant_id = %s AND deleted_at IS NULL
                ) combined
                """,
                [tenant_id] * 5,
            )
            row = cursor.fetchone()
    except Exception:
        return parsed_from, parsed_to

    if not row or row[0] is None:
        return parsed_from, parsed_to

    data_min = row[0] if isinstance(row[0], date_cls) else date_cls.fromisoformat(str(row[0]))
    data_max = row[1] if isinstance(row[1], date_cls) else date_cls.fromisoformat(str(row[1]))
    return parsed_from or data_min, parsed_to or data_max


def _ensure_finance_aggregates(
    tenant_id: int,
    *,
    date_from_raw: str | None,
    date_to_raw: str | None,
) -> tuple[date_cls | None, date_cls | None, bool]:
    """
    Ensure daily finance aggregates are being computed for the requested range.
    Returns (date_from, date_to, is_computing) immediately without blocking.
    is_computing=True means background tasks were dispatched and data is incomplete.
    If records are already present in DB → no-op (fast path).
    If records are missing → dispatch Celery tasks for missing dates asynchronously.
    """
    date_from, date_to = _resolve_operation_window(
        tenant_id,
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
    )
    if not date_from or not date_to:
        return date_from, date_to, False

    span_days = (date_to - date_from).days
    if span_days > 1825:  # Safety cap: 5 years
        date_from = date_to - timedelta(days=1825)

    # Check which dates already have aggregated records in the DB.
    existing_dates = set(
        DailySummary.objects.filter(
            tenant_id=tenant_id,
            date__gte=date_from,
            date__lte=date_to,
        ).values_list('date', flat=True)
    )

    missing: list[date_cls] = []
    cursor = date_from
    while cursor <= date_to:
        if cursor not in existing_dates:
            missing.append(cursor)
        cursor += timedelta(days=1)

    warmup_key = f'finance:agg:warm:{tenant_id}:{date_from.isoformat()}:{date_to.isoformat()}'
    if not missing:
        # All dates present — mark as warm and return.
        cache.set(warmup_key, True, timeout=3600)
        return date_from, date_to, False

    # Dispatch async tasks for missing dates; do NOT block the request.
    lock_key = f'finance:agg:lock:{tenant_id}'
    lock_token = str(timezone.now().timestamp())
    if cache.add(lock_key, lock_token, timeout=60):
        try:
            for d in missing:
                aggregate_daily_pnl.delay(tenant_id, d.isoformat())
            if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                cache.set(warmup_key, True, timeout=3600)
                return date_from, date_to, False
        except Exception:
            pass
        finally:
            if cache.get(lock_key) == lock_token:
                cache.delete(lock_key)

    return date_from, date_to, True


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
            customer_id=data.get('customer_id'),
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
        date_from, date_to, _ = _ensure_finance_aggregates(
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
        date_from, date_to, _ = _ensure_finance_aggregates(
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


class SaleProfitabilityView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        date_from = parse_date(request.query_params.get('date_from')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to')) if request.query_params.get('date_to') else None
        location_id = request.query_params.get('location')
        report_currency = request.query_params.get('report_currency')
        cache_key = _profitability_cache_key(request.tenant_id, {
            'view': 'sales',
            'date_from': str(date_from),
            'date_to': str(date_to),
            'location': location_id,
            'currency': report_currency,
        })
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        try:
            rows = get_sales_profitability_rows(
                tenant_id=request.tenant_id,
                date_from=date_from,
                date_to=date_to,
                location_id=int(location_id) if location_id else None,
                report_currency=report_currency,
            )
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})
        data = SaleProfitabilitySerializer(rows, many=True).data
        cache.set(cache_key, data, timeout=300)
        return Response(data)


class ProductProfitabilityView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        date_from = parse_date(request.query_params.get('date_from')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to')) if request.query_params.get('date_to') else None
        location_id = request.query_params.get('location')
        warehouse_id = request.query_params.get('warehouse')
        report_currency = request.query_params.get('report_currency')
        cache_key = _profitability_cache_key(request.tenant_id, {
            'view': 'products',
            'date_from': str(date_from),
            'date_to': str(date_to),
            'location': location_id,
            'warehouse': warehouse_id,
            'currency': report_currency,
        })
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        try:
            rows = get_product_profitability_rows(
                tenant_id=request.tenant_id,
                date_from=date_from,
                date_to=date_to,
                location_id=int(location_id) if location_id else None,
                warehouse_id=int(warehouse_id) if warehouse_id else None,
                report_currency=report_currency,
            )
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})
        data = ProductProfitabilitySerializer(rows, many=True).data
        cache.set(cache_key, data, timeout=300)
        return Response(data)


class ProcurementProfitabilityView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        date_from = parse_date(request.query_params.get('date_from')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to')) if request.query_params.get('date_to') else None
        report_currency = request.query_params.get('report_currency')
        cache_key = _profitability_cache_key(request.tenant_id, {
            'view': 'procurements',
            'date_from': str(date_from),
            'date_to': str(date_to),
            'currency': report_currency,
        })
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        try:
            rows = get_procurement_profitability_rows(
                tenant_id=request.tenant_id,
                date_from=date_from,
                date_to=date_to,
                report_currency=report_currency,
            )
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})
        data = ProcurementProfitabilitySerializer(rows, many=True).data
        cache.set(cache_key, data, timeout=300)
        return Response(data)


class ProcurementProfitabilityDetailView(APIView):
    permission_classes = [IsOwner]

    def get(self, request, procurement_id: int):
        try:
            payload = get_procurement_profitability_detail(
                tenant_id=request.tenant_id,
                procurement_id=procurement_id,
                report_currency=request.query_params.get('report_currency'),
            )
        except Procurement.DoesNotExist:
            raise NotFound('Закупка не найдена')
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})
        return Response(ProcurementProfitabilityDetailSerializer(payload).data)


class AgreementProfitabilityDetailView(APIView):
    permission_classes = [IsOwner]

    def get(self, request, agreement_id: int):
        from apps.partnerships.models import InvestmentAgreement

        try:
            payload = get_agreement_profitability_detail(
                tenant_id=request.tenant_id,
                agreement_id=agreement_id,
                report_currency=request.query_params.get('report_currency'),
            )
        except InvestmentAgreement.DoesNotExist:
            raise NotFound('Инвестдоговор не найден')
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})
        return Response(payload)


def _profitability_cache_key(tenant_id: int, params: dict) -> str:
    import hashlib, json
    version = cache.get(f'profitability:v:{tenant_id}', 0)
    raw = json.dumps({'tenant': tenant_id, 'v': version, **params}, sort_keys=True, default=str)
    return f'profitability:{hashlib.md5(raw.encode()).hexdigest()}'


class ReportAnalyticsView(APIView):
    """
    Combined profitability endpoint: sales + products + procurements in one request.
    Replaces 3 separate profitability API calls on the dashboard.
    Cached in Redis for 5 minutes per (tenant, date range, currency).
    """
    permission_classes = [IsOwner]

    def get(self, request):
        date_from = parse_date(request.query_params.get('date_from')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to')) if request.query_params.get('date_to') else None
        location_id = request.query_params.get('location')
        report_currency = request.query_params.get('report_currency')

        cache_key = _profitability_cache_key(request.tenant_id, {
            'date_from': str(date_from),
            'date_to': str(date_to),
            'location': location_id,
            'currency': report_currency,
            'view': 'analytics',
        })
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            sales_rows = get_sales_profitability_rows(
                tenant_id=request.tenant_id,
                date_from=date_from,
                date_to=date_to,
                location_id=int(location_id) if location_id else None,
                report_currency=report_currency,
            )
            product_rows = get_product_profitability_rows(
                tenant_id=request.tenant_id,
                date_from=date_from,
                date_to=date_to,
                location_id=int(location_id) if location_id else None,
                report_currency=report_currency,
            )
            procurement_rows = get_procurement_profitability_rows(
                tenant_id=request.tenant_id,
                date_from=date_from,
                date_to=date_to,
                report_currency=report_currency,
            )
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})

        data = {
            'sales': SaleProfitabilitySerializer(sales_rows, many=True).data,
            'products': ProductProfitabilitySerializer(product_rows, many=True).data,
            'procurements': ProcurementProfitabilitySerializer(procurement_rows, many=True).data,
        }
        cache.set(cache_key, data, timeout=300)
        return Response(data)


class ReportSummaryView(APIView):
    """
    Combined summary endpoint: daily P&L + cash flow + debt + parity in one request.
    Replaces 5+ separate API calls on the dashboard.
    """
    permission_classes = [IsOwner]

    def get(self, request):
        from apps.customers.services import get_customer_debt_summary
        from apps.suppliers.services import get_supplier_payables_summary
        from apps.inventory.services import get_stock_summary

        date_from_raw = request.query_params.get('date_from')
        date_to_raw = request.query_params.get('date_to')

        date_from, date_to, is_computing = _ensure_finance_aggregates(
            request.tenant_id,
            date_from_raw=date_from_raw,
            date_to_raw=date_to_raw,
        )

        daily_qs = DailySummary.objects.filter(tenant_id=request.tenant_id)
        if date_from:
            daily_qs = daily_qs.filter(date__gte=date_from)
        if date_to:
            daily_qs = daily_qs.filter(date__lte=date_to)

        cash_qs = CashFlowSummary.objects.filter(tenant_id=request.tenant_id)
        if date_from:
            cash_qs = cash_qs.filter(date__gte=date_from)
        if date_to:
            cash_qs = cash_qs.filter(date__lte=date_to)

        trial_balance = get_trial_balance(request.tenant_id)
        cash_accounts = CashAccount.objects.filter(tenant_id=request.tenant_id)

        return Response({
            'is_computing': is_computing,
            'daily_summary': DailySummarySerializer(daily_qs.order_by('-date'), many=True).data,
            'cash_flow': CashFlowSummarySerializer(cash_qs.order_by('-date'), many=True).data,
            'debt': get_customer_debt_summary(request.tenant_id),
            'parity': {
                'payables': get_supplier_payables_summary(request.tenant_id),
                'stock': get_stock_summary(request.tenant_id),
                'trial_balance': TrialBalanceSerializer(trial_balance, many=True).data,
                'cash_accounts': CashAccountSerializer(cash_accounts, many=True).data,
            },
        })


class ExchangeRateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Tenant FX history with manual override and official refresh action.
    """

    serializer_class = ExchangeRateSerializer
    permission_classes = [IsOwner]
    ordering = ['-rate_date', '-updated_at']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'latest'}:
            return [(IsOwner | IsInvestor)()]
        return [IsOwner()]

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
                {
                    'detail': (
                        f'Rate not found for {base}/{quote}. '
                        'Create a manual rate or run official sync.'
                    ),
                    'code': 'fx_rate_missing',
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ExchangeRateSerializer(row).data)
