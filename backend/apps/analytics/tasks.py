"""
Celery tasks for background aggregation.
"""

import logging
from decimal import Decimal
from datetime import datetime

from celery import shared_task
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def process_outbox_events():
    """
    Poll unprocessed OutboxEvents and dispatch to appropriate handlers.
    Scheduled via Celery Beat (every 10s).
    """
    from apps.core.models import OutboxEvent

    with transaction.atomic():
        events = list(
            OutboxEvent.objects
            .select_for_update(skip_locked=True)
            .filter(processed_at__isnull=True)
            .order_by('created_at')[:100]
        )

    for event in events:
        try:
            handled = _dispatch_event(event)
        except Exception as exc:
            logger.exception('Failed processing outbox event %s', event.pk)
            event.mark_failed(str(exc))
            continue

        if not handled:
            event.mark_failed(f'Unhandled event type: {event.event_type}')
            continue

        event.mark_processed()


def _dispatch_event(event):
    """Route event to the correct aggregation task."""
    handlers = {
        'sale.completed': _handle_sale_completed,
        'sale.returned': _handle_sale_returned,
        'receipt.confirmed': _handle_receipt_confirmed,
        'risk.writeoff': _handle_risk_event,
        'risk_event.created': _handle_risk_event,
        'risk.inventory_check_completed': _handle_noop_retired,
        'customer.debt_accrued': _handle_financial_operation,
        'customer.payment': _handle_financial_operation,
        'supplier.payment': _handle_financial_operation,
        'expense.recorded': _handle_financial_operation,
        'pos_session.opened': _handle_session_event,
        'pos_session.closed': _handle_session_event,
        'lot.transfer': _handle_lot_transfer,
        'lot.transferred': _handle_lot_transfer,
        'investor.contract_closed': _handle_contract_closed,
        'investor.invite_created': _handle_noop_retired,
        'investor.invite_accepted': _handle_noop_retired,
        'procurement.opened': _handle_noop_retired,
        'procurement.updated': _handle_noop_retired,
        'procurement.contribution_added': _handle_noop_retired,
        'procurement.withdrawal_added': _handle_noop_retired,
        'procurement.balance_exchanged': _handle_noop_retired,
        'procurement.items_paid': _handle_noop_retired,
        'procurement.expenses_paid': _handle_noop_retired,
        'procurement.received': _handle_procurement_received,
        'partnership.dividend_paid': _handle_noop_retired,
        'finance.currency_exchange': _handle_noop_retired,
        'finance.refund': _handle_financial_operation,
        'finance.owner_contribution': _handle_noop_retired,
    }
    handler = handlers.get(event.event_type)
    if handler is None:
        return False
    handler(event.payload, event.tenant_id)
    return True


def _invalidate_profitability_cache(tenant_id: int) -> None:
    from django.core.cache import cache
    current = cache.get(f'profitability:v:{tenant_id}', 0)
    cache.set(f'profitability:v:{tenant_id}', current + 1, timeout=86400)


def _handle_sale_completed(payload, tenant_id):
    date_str = payload.get('date')
    aggregate_daily_pnl.delay(tenant_id, date_str)
    _invalidate_profitability_cache(tenant_id)


def _handle_sale_returned(payload, tenant_id):
    _handle_financial_operation(payload, tenant_id)
    _invalidate_profitability_cache(tenant_id)


def _handle_noop_retired(payload, tenant_id):
    logger.info(
        'Retired analytics handler skipped for tenant=%s payload=%s',
        tenant_id,
        payload,
    )


def _handle_receipt_confirmed(payload, tenant_id):
    aggregate_daily_pnl.delay(tenant_id, payload.get('date'))
    _invalidate_profitability_cache(tenant_id)


def _handle_procurement_received(payload, tenant_id):
    # Procurement receive changes stock/projection rows even without sale revenue.
    _invalidate_profitability_cache(tenant_id)


def _handle_risk_event(payload, tenant_id):
    aggregate_daily_pnl.delay(tenant_id, payload.get('date'))
    _invalidate_profitability_cache(tenant_id)


def _handle_financial_operation(payload, tenant_id):
    aggregate_daily_pnl.delay(tenant_id, payload.get('date'))


def _handle_session_event(payload, tenant_id):
    aggregate_daily_pnl.delay(tenant_id, payload.get('opened_at') or payload.get('closed_at'))


def _handle_lot_transfer(payload, tenant_id):
    # Transfer affects stock placement only; no P&L aggregation required.
    _ = payload, tenant_id


def _handle_contract_closed(payload, tenant_id):
    contract_id = payload.get('contract_id')
    if contract_id:
        from apps.investors.services import update_investor_summary
        update_investor_summary(tenant_id, contract_id)


@shared_task
def aggregate_daily_pnl(tenant_id, date_str=None):
    """
    Aggregate P&L for a specific day.
    Creates/updates DailySummary and CashFlowSummary.
    """
    from apps.finance.models import DailySummary, CashFlowSummary
    from apps.sales.models import Sale, Return as SaleReturn
    from apps.sales.services import SALE_ACCOUNTING_STATUSES, sale_financial_effect
    from apps.finance.models import Expense

    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
    else:
        target_date = timezone.localdate()

    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(target_date, datetime.min.time()), tz)
    day_end = timezone.make_aware(datetime.combine(target_date, datetime.max.time()), tz)

    # Sales aggregation
    sales = Sale.objects.filter(
        tenant_id=tenant_id,
        status__in=SALE_ACCOUNTING_STATUSES,
        date__range=(day_start, day_end),
    ).prefetch_related('lines__return_lines__return_doc', 'lines__lot')

    sale_effects = [sale_financial_effect(sale) for sale in sales]
    total_revenue = sum((effect['revenue'] for effect in sale_effects), Decimal('0'))
    total_cogs = sum((effect['cogs'] for effect in sale_effects), Decimal('0'))

    total_sales_count = sales.count()

    # Returns count
    total_returns_count = SaleReturn.objects.filter(
        tenant_id=tenant_id,
        date__range=(day_start, day_end),
    ).count()
    total_return_amount = sum((effect['returned_amount'] for effect in sale_effects), Decimal('0'))
    total_return_restock_cogs = sum((effect['restock_cogs'] for effect in sale_effects), Decimal('0'))
    total_return_disposal_loss = sum((effect['disposal_loss'] for effect in sale_effects), Decimal('0'))

    # Writeoffs
    from apps.risk.models import RiskEvent
    writeoffs = RiskEvent.objects.filter(
        tenant_id=tenant_id,
        event_type='writeoff',
        created_at__range=(day_start, day_end),
    ).aggregate(
        total=Sum('monetary_impact'),
    )['total'] or Decimal('0')

    operational_expenses = Expense.objects.filter(
        tenant_id=tenant_id,
        occurred_at__range=(day_start, day_end),
    ).aggregate(total=Sum('functional_amount_uzs'))['total'] or Decimal('0')

    gross_profit = total_revenue - total_cogs

    # Investor share is currently derived from partner ledger accruals.
    from apps.partnerships.models import PartnerLedgerEntry
    accrued_profit = PartnerLedgerEntry.objects.filter(
        tenant_id=tenant_id,
        entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
        date__range=(day_start, day_end),
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    reversed_profit = PartnerLedgerEntry.objects.filter(
        tenant_id=tenant_id,
        entry_type=PartnerLedgerEntry.EntryType.PROFIT_REVERSED,
        date__range=(day_start, day_end),
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    investor_share = accrued_profit - reversed_profit

    net_business_profit = gross_profit - investor_share - writeoffs - operational_expenses

    DailySummary.objects.update_or_create(
        tenant_id=tenant_id,
        date=target_date,
        defaults={
            'total_revenue': total_revenue,
            'total_cogs': total_cogs,
            'gross_profit': gross_profit,
            'investor_share': investor_share,
            'net_business_profit': net_business_profit,
            'total_sales_count': total_sales_count,
            'total_returns_count': total_returns_count,
            'total_return_amount': total_return_amount,
            'total_return_restock_cogs': total_return_restock_cogs,
            'total_return_disposal_loss': total_return_disposal_loss,
            'total_writeoffs': writeoffs,
        },
    )

    # Cash flow summary
    from apps.sales.models import SalePayment
    from apps.sales.currency import payment_functional_amount_uzs
    cash_sales = sum(
        (
            payment_functional_amount_uzs(payment)
            for payment in SalePayment.objects.filter(
                tenant_id=tenant_id,
                role=SalePayment.Role.INCOMING,
                method=SalePayment.Method.CASH,
                date__range=(day_start, day_end),
            )
        ),
        Decimal('0'),
    )
    cash_refunds = sum(
        (
            payment_functional_amount_uzs(payment)
            for payment in SalePayment.objects.filter(
                tenant_id=tenant_id,
                role=SalePayment.Role.REFUND,
                method=SalePayment.Method.CASH,
                date__range=(day_start, day_end),
            )
        ),
        Decimal('0'),
    )

    from apps.customers.models import CustomerPayment
    debt_payments = CustomerPayment.objects.filter(
        tenant_id=tenant_id,
        date__range=(day_start, day_end),
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    from apps.suppliers.models import SupplierPayment
    supplier_payments = SupplierPayment.objects.filter(
        tenant_id=tenant_id,
        date__range=(day_start, day_end),
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    expense_outflows = Expense.objects.filter(
        tenant_id=tenant_id,
        occurred_at__range=(day_start, day_end),
    ).aggregate(total=Sum('functional_amount_uzs'))['total'] or Decimal('0')

    net_cash = cash_sales + debt_payments - cash_refunds - supplier_payments - expense_outflows

    CashFlowSummary.objects.update_or_create(
        tenant_id=tenant_id,
        date=target_date,
        defaults={
            'cash_in_sales': cash_sales,
            'cash_in_debt_payments': debt_payments,
            'cash_in_investor': Decimal('0'),
            'cash_out_purchases': Decimal('0'),
            'cash_out_supplier_payments': supplier_payments,
            'cash_out_expenses': expense_outflows,
            'cash_out_refunds': cash_refunds,
            'cash_out_investor_payments': Decimal('0'),
            'net_cash_flow': net_cash,
        },
    )


@shared_task
def compute_aging_reports(tenant_id):
    """
    Recompute A/R and A/P aging buckets.
    Scheduled nightly via Celery Beat.
    """
    from apps.analytics.models import AgingReport
    from apps.customers.models import Customer
    from apps.suppliers.models import Supplier

    now = timezone.now()

    # Customer aging (A/R)
    # select_related avoids N+1 on customer.receivable per iteration;
    # exclude no-receivable rows at SQL level, then filter by balance in Python.
    customers = [
        customer
        for customer in Customer.objects.filter(
            tenant_id=tenant_id,
            receivable__isnull=False,
        ).select_related('receivable')
        if customer.outstanding_balance > 0
    ]

    for customer in customers:
        # Simple aging: all current balance in 0-30 bucket for MVP
        # Full implementation would analyze individual credit sale dates
        AgingReport.objects.update_or_create(
            tenant_id=tenant_id,
            report_type='customer',
            entity_id=customer.pk,
            defaults={
                'entity_name': customer.name,
                'bucket_0_30': customer.outstanding_balance,
                'bucket_31_60': Decimal('0'),
                'bucket_61_90': Decimal('0'),
                'bucket_90_plus': Decimal('0'),
                'total': customer.outstanding_balance,
            },
        )

    # Supplier aging (A/P)
    suppliers = Supplier.objects.filter(
        tenant_id=tenant_id,
        outstanding_balance__gt=0,
    )

    for supplier in suppliers:
        AgingReport.objects.update_or_create(
            tenant_id=tenant_id,
            report_type='supplier',
            entity_id=supplier.pk,
            defaults={
                'entity_name': supplier.name,
                'bucket_0_30': supplier.outstanding_balance,
                'bucket_31_60': Decimal('0'),
                'bucket_61_90': Decimal('0'),
                'bucket_90_plus': Decimal('0'),
                'total': supplier.outstanding_balance,
            },
        )

    # Clean up entries for entities that no longer have debt
    AgingReport.objects.filter(
        tenant_id=tenant_id,
        report_type='customer',
    ).exclude(
        entity_id__in=[customer.pk for customer in customers],
    ).delete()

    AgingReport.objects.filter(
        tenant_id=tenant_id,
        report_type='supplier',
    ).exclude(
        entity_id__in=suppliers.values_list('pk', flat=True),
    ).delete()
