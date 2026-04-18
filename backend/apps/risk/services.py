"""
Risk business logic — risk events, inventory checks, writeoffs.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event

from .models import RiskEvent, InventoryCheck, InventoryCheckLine


def create_writeoff(
    tenant_id: int,
    lot_id: int,
    quantity: int,
    reason: str,
    responsible_user_id: int | None = None,
    negligence: bool = False,
) -> RiskEvent:
    """
    Write off inventory (damaged, expired, lost).
    Deducts lot quantity and creates RiskEvent.
    """
    raise NotImplementedError(
        'create_writeoff awaits PR-8 (LotStock-aware writeoff + PartnerLedger.LOSS_INCURRED).'
    )
    from apps.inventory.models import Lot, StockMovement
    from apps.inventory.services import deduct_lot_quantity

    with transaction.atomic():
        lot = Lot.objects.select_for_update().get(
            pk=lot_id,
            tenant_id=tenant_id,
        )

        monetary_impact = lot.cost_per_unit * quantity

        # Determine if this affects investors
        receipt = lot.receipt
        affects_investor = receipt.receipt_type in ('MUDARABA', 'MUSHARAKA')

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

        # Deduct from lot
        deduct_lot_quantity(lot, quantity)

        # Record stock movement
        StockMovement.objects.create(
            tenant_id=tenant_id,
            lot=lot,
            movement_type=StockMovement.MovementType.WRITEOFF,
            quantity=-quantity,
            from_location=lot.location,
            reference_type='risk_event',
            reference_id=risk_event.pk,
        )

        # Record investor loss if applicable
        if affects_investor:
            _record_investor_loss(
                tenant_id=tenant_id,
                lot=lot,
                risk_event=risk_event,
                amount=monetary_impact,
            )

        # Create journal entry for writeoff
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
                    'description': f'Writeoff: inventory reduction',
                },
            ],
            description=f'Writeoff of {quantity} units from lot #{lot.pk}',
        )

        publish_event(
            event_type='risk.writeoff',
            payload={
                'risk_event_id': risk_event.pk,
                'lot_id': lot.pk,
                'quantity': quantity,
                'monetary_impact': str(monetary_impact),
                'affects_investor': affects_investor,
            },
            tenant_id=tenant_id,
        )

    return risk_event


def _record_investor_loss(
    tenant_id: int,
    lot,
    risk_event: RiskEvent,
    amount: Decimal,
) -> None:
    """Record loss for investors linked to this lot's receipt."""
    from apps.investors.services import record_investor_profit
    from apps.inventory.models import ReceiptParticipant
    from apps.investors.models import InvestorContract

    participants = ReceiptParticipant.objects.filter(
        receipt=lot.receipt,
        participant_type='investor',
    )

    for participant in participants:
        contract = None
        if lot.receipt.investor_contract_id:
            contract = InvestorContract.objects.filter(
                pk=lot.receipt.investor_contract_id,
                status='active',
                tenant_id=tenant_id,
            ).first()

        if contract is None:
            contract = InvestorContract.objects.filter(
                investor_id=participant.entity_id,
                status='active',
                tenant_id=tenant_id,
            ).first()

        if contract and contract.investor_id == participant.entity_id:
            loss_amount = amount * participant.capital_ratio
            record_investor_profit(
                tenant_id=tenant_id,
                contract_id=contract.pk,
                investor_id=participant.entity_id,
                record_type='loss',
                amount=loss_amount,
                source_type='risk_event',
                source_id=risk_event.pk,
                lot_id=lot.pk,
                description=f'Loss from writeoff: {risk_event.reason}',
            )


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
