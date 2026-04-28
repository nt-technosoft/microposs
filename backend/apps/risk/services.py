"""
Risk business logic — risk events, inventory checks, writeoffs.
"""

from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.partnerships.formulas import distribute_loss_by_capital_from_snapshot

from .models import RiskEvent, InventoryCheck, InventoryCheckLine


def create_writeoff(
    tenant_id: int,
    lot_id: int,
    warehouse_id: int,
    quantity: int,
    reason: str,
    responsible_user_id: int | None = None,
    negligence: bool = False,
) -> RiskEvent:
    """
    Write off inventory (damaged, expired, lost) — no prior sale.
    Flow:
      1. Decrement LotStock at the chosen warehouse (source of stock loss).
      2. Create RiskEvent + StockDisposal(reason=WRITEOFF).
      3. For each partner on the lot → PartnerLedgerEntry(LOSS_INCURRED, amount × capital_share).
    """
    from apps.inventory.models import Lot, LotStock, StockDisposal, StockMovement
    from apps.partnerships.models import PartnerLedgerEntry
    from apps.partnerships.services import append_ledger_entry, get_or_create_ledger

    if quantity < 1:
        raise ValueError('Writeoff quantity must be >= 1.')

    with transaction.atomic():
        lot = Lot.objects.select_for_update().get(
            pk=lot_id,
            tenant_id=tenant_id,
        )

        stock = LotStock.objects.select_for_update().get(
            tenant_id=tenant_id,
            lot=lot,
            warehouse_id=warehouse_id,
        )
        if stock.quantity_remaining < quantity:
            raise ValueError(
                f'Insufficient stock in warehouse {warehouse_id} for lot #{lot.pk}: '
                f'have {stock.quantity_remaining}, need {quantity}.'
            )

        monetary_impact = (lot.landed_cost_per_unit * quantity).quantize(Decimal('0.01'))

        contract_snapshot = lot.contract_snapshot or {}
        partners_meta = contract_snapshot.get('partners', []) or []
        affects_investor = any(
            p.get('role') == 'INVESTOR' for p in partners_meta
        )

        risk_event = RiskEvent.objects.create(
            tenant_id=tenant_id,
            event_type=RiskEvent.EventType.WRITEOFF,
            lot=lot,
            quantity=quantity,
            monetary_impact=monetary_impact,
            affects_investor=affects_investor,
            negligence=negligence,
            responsible_user_id=responsible_user_id,
            reason=reason,
        )

        disposal = StockDisposal.objects.create(
            tenant_id=tenant_id,
            lot=lot,
            warehouse_id=warehouse_id,
            quantity=quantity,
            reason=StockDisposal.Reason.WRITEOFF,
            loss_amount=monetary_impact,
            risk_event_ref=risk_event,
            notes=reason,
        )

        stock.quantity_remaining = stock.quantity_remaining - quantity
        stock.save(update_fields=['quantity_remaining', 'updated_at'])

        Lot.objects.filter(pk=lot.pk).update(
            quantity_initial=models.F('quantity_initial') - quantity,
        )
        if LotStock.objects.filter(lot=lot).aggregate(
            total=models.Sum('quantity_remaining'),
        )['total'] in (0, None):
            Lot.objects.filter(pk=lot.pk).update(is_active=False)

        StockMovement.objects.create(
            tenant_id=tenant_id,
            lot=lot,
            movement_type=StockMovement.MovementType.WRITEOFF,
            quantity=-quantity,
            from_location_id=warehouse_id,
            reference_type='risk_event',
            reference_id=risk_event.pk,
        )

        # Partner loss via PartnerLedger
        procurement_id = None
        if lot.procurement_item_id:
            procurement_id = lot.procurement_item.procurement_id

        if procurement_id and partners_meta:
            loss_distribution = distribute_loss_by_capital_from_snapshot(
                contract_snapshot=contract_snapshot,
                loss_amount=monetary_impact,
            )
            for partner_id_str, loss_str in loss_distribution.items():
                partner_id = int(partner_id_str)
                loss_share = Decimal(str(loss_str))
                if loss_share <= 0:
                    continue
                ledger = get_or_create_ledger(
                    procurement_id=procurement_id,
                    partner_id=int(partner_id),
                    tenant_id=tenant_id,
                )
                append_ledger_entry(
                    ledger=ledger,
                    entry_type=PartnerLedgerEntry.EntryType.LOSS_INCURRED,
                    amount=loss_share,
                    currency='UZS',
                    source_ref=f'writeoff:{risk_event.pk}',
                )

        # Journal entry (bookkeeping)
        from apps.finance.services import create_journal_entry
        create_journal_entry(
            tenant_id=tenant_id,
            operation_type='writeoff',
            operation_id=risk_event.pk,
            lines=[
                {
                    'account_code': '5100',
                    'debit': monetary_impact,
                    'credit': Decimal('0'),
                    'description': f'Writeoff: {reason}',
                },
                {
                    'account_code': '1100',
                    'debit': Decimal('0'),
                    'credit': monetary_impact,
                    'description': 'Writeoff: inventory reduction',
                },
            ],
            description=f'Writeoff of {quantity} units from lot #{lot.pk}',
        )

        publish_event(
            event_type='risk.writeoff',
            payload={
                'risk_event_id': risk_event.pk,
                'disposal_id': disposal.pk,
                'lot_id': lot.pk,
                'quantity': quantity,
                'monetary_impact': str(monetary_impact),
                'affects_investor': affects_investor,
            },
            tenant_id=tenant_id,
        )

    return risk_event


def complete_inventory_check(
    tenant_id: int,
    check_id: int,
) -> InventoryCheck:
    """
    Complete an inventory check.
    Creates RiskEvents for any mismatches found.
    """
    with transaction.atomic():
        check = InventoryCheck.objects.select_for_update().get(
            pk=check_id,
            tenant_id=tenant_id,
        )

        check.status = InventoryCheck.CheckStatus.COMPLETED
        check.completed_at = timezone.now()
        check.save(update_fields=['status', 'completed_at', 'updated_at'])

        # Create risk events for mismatches
        for line in check.lines.filter(difference__lt=0):
            RiskEvent.objects.create(
                tenant_id=tenant_id,
                event_type=RiskEvent.EventType.STOCK_MISMATCH,
                quantity=abs(line.difference),
                monetary_impact=Decimal('0'),  # Will be calculated separately
                reason=(
                    f'Inventory check #{check.pk}: '
                    f'{line.product_variant} expected {line.expected_quantity}, '
                    f'found {line.actual_quantity}'
                ),
            )

        publish_event(
            event_type='risk.inventory_check_completed',
            payload={
                'check_id': check.pk,
                'location_id': check.location_id,
                'lines_count': check.lines.count(),
                'mismatches': check.lines.filter(difference__lt=0).count(),
            },
            tenant_id=tenant_id,
        )

    return check
