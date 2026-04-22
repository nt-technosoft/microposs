"""
Investors business logic — contracts, settlement.

InvestorProfitRecord and InvestorSummary dropped in PR-5.
Profit tracking now lives in partnerships.PartnerLedgerEntry.
Aggregate view: partnerships.services.get_partner_aggregate().
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event
from apps.core.exceptions import ContractCloseError

from .models import Investor, InvestorContract


def _q(amount: Decimal | int | float | str) -> Decimal:
    return Decimal(str(amount)).quantize(Decimal('0.01'))


def _extract_partner_capital_share(contract_snapshot: dict | None, partner_id: int) -> Decimal:
    snapshot = contract_snapshot or {}
    for meta in snapshot.get('partners', []) or []:
        try:
            if int(meta.get('partner_id')) == int(partner_id):
                return Decimal(str(meta.get('capital_share', '0')))
        except (TypeError, ValueError):
            continue
    return Decimal('0')


def get_partner_capital_state(
    *,
    tenant_id: int,
    partner_id: int,
    procurement_id: int | None = None,
) -> dict:
    """
    Capital transparency read-model for a partner in the procurement-based flow.

    Values are functional UZS and are tracked at cost basis:
    - sold_cost_uzs: partner's capital already sold at landed cost
    - in_stock_cost_uzs: partner's capital still tied in remaining stock
    - tracked_cost_uzs: sold + in-stock cost basis
    - sold_revenue_uzs: informational weighted share of realized revenue
    - projected_revenue_uzs: informational weighted share of current retail value of remaining stock
    - projected_partner_profit_uzs: partner's expected profit share if remaining stock sells at current retail price
    """
    from apps.inventory.models import Lot
    from apps.partnerships.models import ProcurementPartnerLedger
    from apps.sales.models import SaleLine
    from apps.sales.services import calculate_profit_distribution

    ledger_qs = ProcurementPartnerLedger.objects.filter(
        tenant_id=tenant_id,
        partner_id=partner_id,
    )
    if procurement_id is not None:
        ledger_qs = ledger_qs.filter(procurement_id=procurement_id)

    procurement_ids = list(ledger_qs.values_list('procurement_id', flat=True))
    if not procurement_ids:
        return {
            'sold_cost_uzs': Decimal('0.00'),
            'in_stock_cost_uzs': Decimal('0.00'),
            'tracked_cost_uzs': Decimal('0.00'),
            'sold_revenue_uzs': Decimal('0.00'),
            'projected_revenue_uzs': Decimal('0.00'),
            'projected_partner_profit_uzs': Decimal('0.00'),
        }

    lots = list(
        Lot.objects.filter(
            tenant_id=tenant_id,
            procurement_item__procurement_id__in=procurement_ids,
        ).prefetch_related('stocks').select_related('product_variant__product')
    )

    lot_shares: dict[int, Decimal] = {}
    in_stock_cost = Decimal('0.00')
    projected_revenue = Decimal('0.00')
    projected_partner_profit = Decimal('0.00')
    for lot in lots:
        capital_share = _extract_partner_capital_share(lot.contract_snapshot, partner_id)
        if capital_share <= 0:
            continue
        remaining_qty = sum(stock.quantity_remaining for stock in lot.stocks.all())
        if remaining_qty > 0:
            in_stock_cost += (
                Decimal(str(lot.landed_cost_per_unit))
                * Decimal(str(remaining_qty))
                * capital_share
            )
            current_price = Decimal(str(lot.product_variant.effective_price or '0'))
            projected_revenue += current_price * Decimal(str(remaining_qty)) * capital_share
            projected_distribution = calculate_profit_distribution(
                lot=lot,
                unit_price=current_price,
                quantity=remaining_qty,
                unit_landed_cost=Decimal(str(lot.landed_cost_per_unit)),
            )
            projected_partner_profit += Decimal(
                str(projected_distribution.get(str(partner_id), '0')),
            )
        lot_shares[lot.id] = capital_share

    sold_cost = Decimal('0.00')
    sold_revenue = Decimal('0.00')
    if lot_shares:
        sale_lines = SaleLine.objects.filter(
            tenant_id=tenant_id,
            lot_id__in=list(lot_shares.keys()),
        )
        for line in sale_lines:
            capital_share = lot_shares.get(line.lot_id, Decimal('0'))
            if capital_share <= 0:
                continue
            quantity = Decimal(str(line.quantity))
            sold_cost += Decimal(str(line.unit_landed_cost)) * quantity * capital_share
            sold_revenue += Decimal(str(line.unit_price)) * quantity * capital_share

    return {
        'sold_cost_uzs': _q(sold_cost),
        'in_stock_cost_uzs': _q(in_stock_cost),
        'tracked_cost_uzs': _q(sold_cost + in_stock_cost),
        'sold_revenue_uzs': _q(sold_revenue),
        'projected_revenue_uzs': _q(projected_revenue),
        'projected_partner_profit_uzs': _q(projected_partner_profit),
    }


def _resolve_contract_receipt_ids(contract: InvestorContract) -> list[int]:
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
            receipt__investor_contract__isnull=True,
            participant_type='investor',
            entity_id=contract.investor_id,
        ).values_list('receipt_id', flat=True)
    )


def close_investor_contract(
    tenant_id: int,
    contract_id: int,
) -> InvestorContract:
    """
    Close an investor contract.
    Only allowed if no active LotStock rows remain for this contract.
    Final settlement computed from PartnerLedgerEntry aggregates.
    """
    with transaction.atomic():
        contract = InvestorContract.objects.select_for_update().get(
            pk=contract_id,
            tenant_id=tenant_id,
        )

        if contract.status == 'closed':
            raise ContractCloseError('Contract is already closed.')

        from apps.inventory.models import LotStock
        receipt_ids = _resolve_contract_receipt_ids(contract)

        active_lots = LotStock.objects.filter(
            lot__receipt_id__in=receipt_ids,
            lot__is_active=True,
            quantity_remaining__gt=0,
            tenant_id=tenant_id,
        ).exists()

        if active_lots:
            raise ContractCloseError('Cannot close contract: active lots still exist.')

        # Final settlement from ledger aggregate (investor's Partner record)
        from apps.core.models import Partner
        partner = Partner.objects.filter(
            tenant_id=tenant_id,
            user_id=contract.investor.user_id,
        ).first()

        if partner:
            from apps.partnerships.services import get_partner_aggregate
            agg = get_partner_aggregate(partner_id=partner.pk, tenant_id=tenant_id)
            final_settlement = agg['capital_net'] + agg['profit_pending_payout']
        else:
            final_settlement = Decimal('0')

        contract.status = 'closed'
        contract.closed_at = timezone.now()
        contract.final_settlement = final_settlement
        contract.save(update_fields=['status', 'closed_at', 'final_settlement', 'updated_at'])

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


def update_investor_summary(tenant_id: int, contract_id: int) -> dict:
    """
    Returns computed summary for an investor contract.
    Replaces the old denormalized InvestorSummary — backed by PartnerLedgerEntry.
    Called by Celery after relevant events; now returns dict, not a model instance.
    """
    contract = InvestorContract.objects.get(pk=contract_id, tenant_id=tenant_id)
    receipt_ids = _resolve_contract_receipt_ids(contract)

    from apps.inventory.models import LotStock
    in_stock_value = LotStock.objects.filter(
        lot__receipt_id__in=receipt_ids,
        lot__is_active=True,
        quantity_remaining__gt=0,
        tenant_id=tenant_id,
    ).aggregate(
        value=models.Sum(
            models.F('lot__landed_cost_per_unit') * models.F('quantity_remaining'),
        ),
    )['value'] or Decimal('0')

    from apps.sales.models import SaleLine
    total_sold = SaleLine.objects.filter(
        tenant_id=tenant_id,
        lot__receipt_id__in=receipt_ids,
    ).aggregate(
        total=models.Sum(models.F('unit_price') * models.F('quantity')),
    )['total'] or Decimal('0')

    from apps.core.models import Partner
    partner = Partner.objects.filter(
        tenant_id=tenant_id,
        user_id=contract.investor.user_id,
    ).first()

    ledger_agg = {}
    if partner:
        from apps.partnerships.services import get_partner_aggregate
        ledger_agg = get_partner_aggregate(partner_id=partner.pk, tenant_id=tenant_id)

    capital_net = ledger_agg.get('capital_net', Decimal('0'))
    total_profit = ledger_agg.get('profit_accrued', Decimal('0'))
    total_losses = ledger_agg.get('losses_incurred', Decimal('0'))
    pending = ledger_agg.get('profit_pending_payout', Decimal('0'))

    turnover = (total_sold / capital_net * 100) if capital_net > 0 else Decimal('0')

    return {
        'contract_id': contract_id,
        'investor_id': contract.investor_id,
        'capital_net': capital_net,
        'in_stock_value': in_stock_value,
        'total_sold_revenue': total_sold,
        'total_profit': total_profit,
        'total_losses': total_losses,
        'turnover_ratio': turnover,
        'profit_pending_payout': pending,
    }
