"""
Celery tasks for background aggregation.
"""

from decimal import Decimal
from datetime import datetime, timedelta

from celery import shared_task
from django.db.models import Sum, F
from django.utils import timezone


@shared_task
def process_outbox_events():
    """
    Poll unprocessed OutboxEvents and dispatch to appropriate handlers.
    Scheduled via Celery Beat (every 10s).
    """
    from apps.core.models import OutboxEvent

    events = OutboxEvent.objects.filter(
        processed_at__isnull=True,
    ).order_by('created_at')[:100]

    for event in events:
        _dispatch_event(event)
        event.mark_processed()


def _dispatch_event(event):
    """Route event to the correct aggregation task."""
    handlers = {
        'sale.completed': _handle_sale_completed,
        'receipt.confirmed': _handle_receipt_confirmed,
        'risk_event.created': _handle_risk_event,
        'investor.contract_closed': _handle_contract_closed,
    }
    handler = handlers.get(event.event_type)
    if handler:
        handler(event.payload, event.tenant_id)


def _handle_sale_completed(payload, tenant_id):
    date_str = payload.get('date')
    aggregate_daily_pnl.delay(tenant_id, date_str)
    sale_id = payload.get('sale_id')
    if sale_id:
        aggregate_investor_summary_for_sale.delay(sale_id)


def _handle_receipt_confirmed(payload, tenant_id):
    aggregate_daily_pnl.delay(tenant_id, payload.get('date'))


def _handle_risk_event(payload, tenant_id):
    aggregate_daily_pnl.delay(tenant_id, payload.get('date'))


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
    from apps.sales.models import Sale, SaleReturn

    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
    else:
        target_date = timezone.now().date()

    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = datetime.combine(target_date, datetime.max.time())

    # Sales aggregation
    sales = Sale.objects.filter(
        tenant_id=tenant_id,
        status='completed',
        created_at__range=(day_start, day_end),
    )

    total_revenue = sales.aggregate(
        total=Sum('total_amount'),
    )['total'] or Decimal('0')

    total_cogs = sales.aggregate(
        total=Sum('total_cogs'),
    )['total'] or Decimal('0')

    total_sales_count = sales.count()

    # Returns count
    total_returns_count = SaleReturn.objects.filter(
        tenant_id=tenant_id,
        created_at__range=(day_start, day_end),
    ).count()

    # Writeoffs
    from apps.risk.models import RiskEvent
    writeoffs = RiskEvent.objects.filter(
        tenant_id=tenant_id,
        event_type='writeoff',
        created_at__range=(day_start, day_end),
    ).aggregate(
        total=Sum('monetary_impact'),
    )['total'] or Decimal('0')

    gross_profit = total_revenue - total_cogs

    # Investor share (from profit records for the day)
    from apps.investors.models import InvestorProfitRecord
    investor_share = InvestorProfitRecord.objects.filter(
        tenant_id=tenant_id,
        record_type='profit',
        created_at__range=(day_start, day_end),
    ).aggregate(
        total=Sum('amount'),
    )['total'] or Decimal('0')

    net_business_profit = gross_profit - investor_share - writeoffs

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
            'total_writeoffs': writeoffs,
        },
    )

    # Cash flow summary
    cash_sales = sales.filter(
        payment_method='cash',
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

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

    net_cash = cash_sales + debt_payments - supplier_payments

    CashFlowSummary.objects.update_or_create(
        tenant_id=tenant_id,
        date=target_date,
        defaults={
            'cash_in_sales': cash_sales,
            'cash_in_debt_payments': debt_payments,
            'cash_in_investor': Decimal('0'),
            'cash_out_purchases': Decimal('0'),
            'cash_out_supplier_payments': supplier_payments,
            'cash_out_investor_payments': Decimal('0'),
            'net_cash_flow': net_cash,
        },
    )


@shared_task
def aggregate_investor_summary_for_sale(sale_id):
    """
    Update InvestorSummary after a sale involving investor lots.
    """
    from apps.sales.models import Sale, SaleLine
    from apps.inventory.models import ReceiptParticipant
    from apps.investors.models import InvestorContract
    from apps.investors.services import update_investor_summary
    from apps.sales.services import calculate_profit_distribution
    from apps.investors.services import record_investor_profit

    sale = Sale.objects.get(pk=sale_id)

    for line in sale.lines.select_related('lot__receipt'):
        lot = line.lot
        receipt = lot.receipt

        if receipt.receipt_type not in ('MUDARABA', 'MUSHARAKA'):
            continue

        # Calculate profit distribution for this line
        distributions = calculate_profit_distribution(lot, line)

        for dist in distributions:
            if dist['entity_type'] == 'investor':
                # Find active contract for this investor
                contract = InvestorContract.objects.filter(
                    investor_id=dist['entity_id'],
                    status='active',
                    tenant_id=sale.tenant_id,
                ).first()

                if contract:
                    record_investor_profit(
                        tenant_id=sale.tenant_id,
                        contract_id=contract.pk,
                        investor_id=dist['entity_id'],
                        record_type='profit',
                        amount=dist['amount'],
                        source_type='sale_line',
                        source_id=line.pk,
                        lot_id=lot.pk,
                        description=f'Profit from sale #{sale.pk}',
                    )
                    update_investor_summary(
                        tenant_id=sale.tenant_id,
                        contract_id=contract.pk,
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
    customers = Customer.objects.filter(
        tenant_id=tenant_id,
        outstanding_balance__gt=0,
    )

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
        entity_id__in=customers.values_list('pk', flat=True),
    ).delete()

    AgingReport.objects.filter(
        tenant_id=tenant_id,
        report_type='supplier',
    ).exclude(
        entity_id__in=suppliers.values_list('pk', flat=True),
    ).delete()
