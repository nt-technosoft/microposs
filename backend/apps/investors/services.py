"""
Investors business logic — contracts, profit records, settlement.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event
from apps.core.exceptions import ContractCloseError

from .models import (
    Investor, InvestorContract, InvestorProfitRecord, InvestorSummary,
)


def _resolve_contract_receipt_ids(contract: InvestorContract) -> list[int]:
    """
    Resolve receipt IDs tied to a contract.

    Primary source is Receipt.investor_contract.
    Fallback keeps legacy compatibility for historic receipts without explicit
    contract link.
    """
    from apps.inventory.models import Receipt, ReceiptParticipant

    direct_ids = list(
        Receipt.objects.filter(
            tenant_id=contract.tenant_id,
            investor_contract_id=contract.pk,
        ).values_list('id', flat=True)
    )
    if direct_ids:
        return direct_ids

    return list(
        ReceiptParticipant.objects.filter(
            tenant_id=contract.tenant_id,
            receipt__tenant_id=contract.tenant_id,
            receipt__investor_contract__isnull=True,
            participant_type='investor',
            entity_id=contract.investor_id,
        ).values_list('receipt_id', flat=True)
    )


def record_investor_profit(
    tenant_id: int,
    contract_id: int,
    investor_id: int,
    record_type: str,
    amount: Decimal,
    source_type: str,
    source_id: int,
    lot_id: int | None = None,
    description: str = '',
) -> InvestorProfitRecord:
    """Record a profit/loss event for an investor."""
    record = InvestorProfitRecord.objects.create(
        tenant_id=tenant_id,
        contract_id=contract_id,
        investor_id=investor_id,
        record_type=record_type,
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        lot_id=lot_id,
        description=description,
    )

    publish_event(
        event_type='investor.profit_recorded',
        payload={
            'record_id': record.pk,
            'contract_id': contract_id,
            'investor_id': investor_id,
            'record_type': record_type,
            'amount': str(amount),
        },
        tenant_id=tenant_id,
    )

    return record


def close_investor_contract(
    tenant_id: int,
    contract_id: int,
) -> InvestorContract:
    """
    Close an investor contract.
    Only allowed if no active lots remain for this contract.
    Calculates final settlement.
    """
    with transaction.atomic():
        contract = InvestorContract.objects.select_for_update().get(
            pk=contract_id,
            tenant_id=tenant_id,
        )

        if contract.status == 'closed':
            raise ContractCloseError('Contract is already closed.')

        # Check for active lots linked to this contract
        from apps.inventory.models import Lot, LotStock
        receipt_ids = _resolve_contract_receipt_ids(contract)

        active_lots = LotStock.objects.filter(
            lot__receipt_id__in=receipt_ids,
            lot__is_active=True,
            quantity_remaining__gt=0,
            tenant_id=tenant_id,
        ).exists()

        if active_lots:
            raise ContractCloseError(
                'Cannot close contract: active lots still exist.'
            )

        # Calculate final settlement
        profit_sum = InvestorProfitRecord.objects.filter(
            contract=contract,
            record_type='profit',
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

        loss_sum = InvestorProfitRecord.objects.filter(
            contract=contract,
            record_type='loss',
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

        capital_returned = InvestorProfitRecord.objects.filter(
            contract=contract,
            record_type='capital_return',
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

        # Get total invested from summary
        summary = InvestorSummary.objects.filter(
            contract=contract,
        ).first()
        total_invested = summary.total_invested if summary else Decimal('0')

        # Final settlement = remaining capital + net profit
        remaining_capital = total_invested - capital_returned
        net_profit = profit_sum - loss_sum
        final_settlement = remaining_capital + net_profit

        contract.status = 'closed'
        contract.closed_at = timezone.now()
        contract.final_settlement = final_settlement
        contract.save(update_fields=[
            'status', 'closed_at', 'final_settlement', 'updated_at',
        ])

        publish_event(
            event_type='investor.contract_closed',
            payload={
                'contract_id': contract.pk,
                'investor_id': contract.investor_id,
                'final_settlement': str(final_settlement),
            },
            tenant_id=tenant_id,
        )

    return contract


def update_investor_summary(
    tenant_id: int,
    contract_id: int,
) -> InvestorSummary:
    """
    Recalculate and update denormalized investor summary.
    Called by Celery after relevant events.
    """
    contract = InvestorContract.objects.get(
        pk=contract_id,
        tenant_id=tenant_id,
    )
    receipt_ids = _resolve_contract_receipt_ids(contract)

    # Total invested — contract-scoped participant capital
    from apps.inventory.models import ReceiptParticipant
    total_invested = ReceiptParticipant.objects.filter(
        receipt_id__in=receipt_ids,
        entity_id=contract.investor_id,
        participant_type='investor',
        tenant_id=tenant_id,
    ).aggregate(
        total=models.Sum('capital_amount'),
    )['total'] or Decimal('0')

    # In-stock value — contract-scoped lots (aggregated across warehouses)
    from apps.inventory.models import LotStock
    in_stock = LotStock.objects.filter(
        lot__receipt_id__in=receipt_ids,
        lot__is_active=True,
        quantity_remaining__gt=0,
        tenant_id=tenant_id,
    ).aggregate(
        value=models.Sum(
            models.F('lot__landed_cost_per_unit') * models.F('quantity_remaining'),
        ),
    )['value'] or Decimal('0')

    # Profit and loss records
    records = InvestorProfitRecord.objects.filter(contract=contract)

    total_profit = records.filter(
        record_type='profit',
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    total_losses = records.filter(
        record_type='loss',
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')

    # Sold revenue linked to this contract's lots
    from apps.sales.models import SaleLine
    total_sold = SaleLine.objects.filter(
        tenant_id=tenant_id,
        lot__receipt_id__in=receipt_ids,
    ).aggregate(
        total=models.Sum(models.F('unit_price') * models.F('quantity')),
    )['total'] or Decimal('0')

    # Turnover ratio
    turnover = (total_sold / total_invested * 100) if total_invested > 0 else Decimal('0')

    # Business owes = remaining capital + net profit
    capital_returned = records.filter(
        record_type='capital_return',
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
    business_owes = (total_invested - capital_returned) + (total_profit - total_losses)

    summary, _ = InvestorSummary.objects.update_or_create(
        investor=contract.investor,
        contract=contract,
        defaults={
            'tenant_id': tenant_id,
            'total_invested': total_invested,
            'in_stock_value': in_stock,
            'total_sold_revenue': total_sold,
            'total_profit': total_profit,
            'total_losses': total_losses,
            'turnover_ratio': turnover,
            'business_owes': business_owes,
        },
    )

    return summary
