"""
Partnerships services — ledger management, dividend payout, partner aggregates.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event
from apps.core.exceptions import ImmutableRecordError


_PARTNERSHIP_TYPES = ('PARTNERSHIP', 'MUSHARAKA')


def _q(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(Decimal('0.01'))


def _balance_get(balances: dict, currency: str) -> Decimal:
    return Decimal(str(balances.get(currency, '0')))


def _balance_set(balances: dict, currency: str, value: Decimal) -> None:
    balances[currency] = str(_q(value))


def open_procurement(
    *,
    tenant_id: int,
    procurement_type: str,
    opened_at=None,
    supplier_id: int | None = None,
    notes: str = '',
    client_request_id: str | None = None,
    contract: dict | None = None,
    items: list[dict] | None = None,
    expenses: list[dict] | None = None,
):
    """
    Create a Procurement (and, for partnership types, InvestmentContract + ContractPartner[]).

    contract (required for PARTNERSHIP/MUSHARAKA):
        {mudaraba_ratio, planned_budget, currency,
         partners: [{partner_id, role, planned_capital_share, profit_share?}]}
    items: [{product_variant_id, quantity, unit_purchase_price, currency, fx_rate}]
    expenses: [{expense_type, amount, currency, fx_rate, allocation_method, notes}]
    """
    from .models import (
        Procurement, ProcurementItem, ProcurementExpense,
        InvestmentContract, ContractPartner, ProcurementBalance,
    )

    if opened_at is None:
        opened_at = timezone.now()
    is_partnership = procurement_type in _PARTNERSHIP_TYPES

    if is_partnership and not contract:
        raise ValueError(
            f'contract payload required for procurement_type={procurement_type}'
        )
    if is_partnership:
        partners = contract.get('partners') or []
        if not partners:
            raise ValueError('At least one contract partner is required.')
        roles = {p.get('role') for p in partners}
        if 'OPERATOR' not in roles:
            raise ValueError('Contract must include an OPERATOR partner.')
        mudaraba_ratio = Decimal(str(contract.get('mudaraba_ratio', '0')))
        if mudaraba_ratio < 0 or mudaraba_ratio > 1:
            raise ValueError('mudaraba_ratio must be in [0, 1].')

    with transaction.atomic():
        if client_request_id:
            existing = Procurement.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        procurement = Procurement.objects.create(
            tenant_id=tenant_id,
            procurement_type=procurement_type,
            status=Procurement.Status.OPEN,
            opened_at=opened_at,
            supplier_id=supplier_id,
            notes=notes,
            client_request_id=client_request_id,
        )

        for item in items or []:
            ProcurementItem.objects.create(
                tenant_id=tenant_id,
                procurement=procurement,
                product_variant_id=item['product_variant_id'],
                quantity=Decimal(str(item['quantity'])),
                unit_purchase_price=Decimal(str(item['unit_purchase_price'])),
                currency=str(item.get('currency', 'UZS')).upper(),
                fx_rate=Decimal(str(item.get('fx_rate', '1'))),
            )

        for expense in expenses or []:
            ProcurementExpense.objects.create(
                tenant_id=tenant_id,
                procurement=procurement,
                expense_type=expense['expense_type'],
                amount=Decimal(str(expense['amount'])),
                currency=str(expense.get('currency', 'UZS')).upper(),
                fx_rate=Decimal(str(expense.get('fx_rate', '1'))),
                allocation_method=expense.get(
                    'allocation_method',
                    ProcurementExpense.AllocationMethod.BY_VALUE,
                ),
                notes=expense.get('notes', ''),
            )

        if is_partnership:
            inv_contract = InvestmentContract.objects.create(
                tenant_id=tenant_id,
                procurement=procurement,
                mudaraba_ratio=Decimal(str(contract['mudaraba_ratio'])),
                loss_rule=contract.get(
                    'loss_rule', InvestmentContract.LossRule.BY_CAPITAL,
                ),
                planned_budget=Decimal(str(contract['planned_budget'])),
                currency=str(contract.get('currency', 'UZS')).upper(),
            )
            for partner in contract['partners']:
                ContractPartner.objects.create(
                    tenant_id=tenant_id,
                    contract=inv_contract,
                    partner_id=partner['partner_id'],
                    role=partner['role'],
                    planned_capital_share=Decimal(
                        str(partner['planned_capital_share'])
                    ),
                    profit_share=Decimal(str(partner.get('profit_share', '0'))),
                )

        ProcurementBalance.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            balances={},
        )

        publish_event(
            event_type='procurement.opened',
            payload={
                'procurement_id': procurement.pk,
                'procurement_type': procurement_type,
                'is_partnership': is_partnership,
            },
            tenant_id=tenant_id,
        )

    return procurement


def add_contribution(
    *,
    tenant_id: int,
    procurement_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    date=None,
    notes: str = '',
):
    """
    Partner deposits capital into ProcurementBalance.
    → BalanceContribution + balances[currency] += amount + Ledger(CAPITAL_IN).
    """
    from .models import (
        Procurement, ProcurementBalance, BalanceContribution,
        PartnerLedgerEntry,
    )

    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Contribution amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status != Procurement.Status.OPEN:
            raise ValueError(
                f'Cannot contribute to procurement in status {procurement.status}.'
            )

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement, tenant_id=tenant_id,
        )

        contribution = BalanceContribution.objects.create(
            tenant_id=tenant_id,
            balance=balance,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            notes=notes,
        )

        balances = dict(balance.balances or {})
        _balance_set(balances, currency, _balance_get(balances, currency) + amount)
        balance.balances = balances
        balance.save(update_fields=['balances', 'updated_at'])

        ledger = get_or_create_ledger(
            procurement_id=procurement.pk,
            partner_id=partner_id,
            tenant_id=tenant_id,
        )
        append_ledger_entry(
            ledger=ledger,
            entry_type=PartnerLedgerEntry.EntryType.CAPITAL_IN,
            amount=amount,
            currency=currency,
            source_ref=f'contribution:{contribution.pk}',
            date=date,
        )

        publish_event(
            event_type='procurement.contribution_added',
            payload={
                'procurement_id': procurement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
                'contribution_id': contribution.pk,
            },
            tenant_id=tenant_id,
        )

    return contribution


def add_withdrawal(
    *,
    tenant_id: int,
    procurement_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    partner_id: int | None = None,
    date=None,
    reason: str = '',
):
    """
    Spend from the common pot. If partner_id given → CAPITAL_OUT ledger entry.
    """
    from .models import (
        Procurement, ProcurementBalance, BalanceWithdrawal,
        PartnerLedgerEntry,
    )

    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Withdrawal amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status != Procurement.Status.OPEN:
            raise ValueError(
                f'Cannot withdraw from procurement in status {procurement.status}.'
            )

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement, tenant_id=tenant_id,
        )
        balances = dict(balance.balances or {})
        current = _balance_get(balances, currency)
        if current < amount:
            raise ValueError(
                f'Insufficient balance for {currency}: have {current}, need {amount}.'
            )
        _balance_set(balances, currency, current - amount)
        balance.balances = balances
        balance.save(update_fields=['balances', 'updated_at'])

        withdrawal = BalanceWithdrawal.objects.create(
            tenant_id=tenant_id,
            balance=balance,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            reason=reason,
        )

        if partner_id is not None:
            ledger = get_or_create_ledger(
                procurement_id=procurement.pk,
                partner_id=partner_id,
                tenant_id=tenant_id,
            )
            append_ledger_entry(
                ledger=ledger,
                entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
                amount=amount,
                currency=currency,
                source_ref=f'withdrawal:{withdrawal.pk}',
                date=date,
            )

        publish_event(
            event_type='procurement.withdrawal_added',
            payload={
                'procurement_id': procurement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
                'withdrawal_id': withdrawal.pk,
            },
            tenant_id=tenant_id,
        )

    return withdrawal


def receive_procurement(
    *,
    tenant_id: int,
    procurement_id: int,
    destination_warehouse_id: int,
    received_at=None,
):
    """
    Finalize a procurement: validate balance == 0, allocate landed cost,
    create Lot + LotStock for every item with an immutable contract_snapshot.
    """
    from django.db.models import Sum
    from apps.inventory.models import Lot, LotStock, StockMovement
    from .models import (
        Procurement, ProcurementItem, ProcurementBalance,
        InvestmentContract, ContractPartner, PartnerLedgerEntry,
        ProcurementPartnerLedger,
    )

    if received_at is None:
        received_at = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status != Procurement.Status.OPEN:
            raise ValueError(
                f'Cannot receive procurement in status {procurement.status}.'
            )

        is_partnership = procurement.procurement_type in _PARTNERSHIP_TYPES

        # Balance must be zero (everything drawn out to pay for items/expenses).
        if is_partnership:
            balance = ProcurementBalance.objects.get(procurement=procurement)
            non_zero = [
                cur for cur, val in (balance.balances or {}).items()
                if Decimal(str(val)) != Decimal('0')
            ]
            if non_zero:
                raise ValueError(
                    f'Cannot receive: balance is non-zero for currencies {non_zero}.'
                )

        items = list(
            ProcurementItem.objects
            .filter(tenant_id=tenant_id, procurement=procurement)
            .select_for_update()
        )
        if not items:
            raise ValueError('Procurement has no items.')

        # Landed expenses total in UZS (convert by fx_rate to tenant functional UZS).
        expenses_total_uzs = Decimal('0')
        for exp in procurement.expenses.all():
            expenses_total_uzs += (
                Decimal(str(exp.amount)) * Decimal(str(exp.fx_rate))
            ).quantize(Decimal('0.01'))

        items_value_uzs = [
            (Decimal(str(item.quantity)) * Decimal(str(item.unit_purchase_price))
             * Decimal(str(item.fx_rate))).quantize(Decimal('0.01'))
            for item in items
        ]
        total_value_uzs = sum(items_value_uzs) or Decimal('1')

        # Build contract snapshot from actual CAPITAL_IN (not planned).
        contract_snapshot = {}
        if is_partnership:
            contract = InvestmentContract.objects.get(procurement=procurement)
            mudaraba_ratio = Decimal(str(contract.mudaraba_ratio))
            partners = list(ContractPartner.objects.filter(contract=contract))

            # Actual capital per partner from ledger CAPITAL_IN - CAPITAL_OUT in UZS.
            actual_capital: dict[int, Decimal] = {}
            ledgers = ProcurementPartnerLedger.objects.filter(
                procurement=procurement, tenant_id=tenant_id,
            )
            for ledger in ledgers:
                entries = PartnerLedgerEntry.objects.filter(ledger=ledger)
                capital_in = sum(
                    (Decimal(str(e.amount)) for e in entries
                     if e.entry_type == PartnerLedgerEntry.EntryType.CAPITAL_IN),
                    Decimal('0'),
                )
                capital_out = sum(
                    (Decimal(str(e.amount)) for e in entries
                     if e.entry_type == PartnerLedgerEntry.EntryType.CAPITAL_OUT),
                    Decimal('0'),
                )
                actual_capital[ledger.partner_id] = capital_in - capital_out

            total_capital = sum(actual_capital.values()) or Decimal('1')

            partners_meta = []
            for cp in partners:
                cap = actual_capital.get(cp.partner_id, Decimal('0'))
                capital_share = (cap / total_capital).quantize(Decimal('0.0001'))
                # Profit share from contract definition, not recomputed here.
                partners_meta.append({
                    'partner_id': cp.partner_id,
                    'role': cp.role,
                    'capital_share': str(capital_share),
                    'profit_share': str(
                        Decimal(str(cp.profit_share)).quantize(Decimal('0.000001'))
                    ),
                })

            contract_snapshot = {
                'mudaraba_ratio': str(mudaraba_ratio.quantize(Decimal('0.0001'))),
                'loss_rule': contract.loss_rule,
                'partners': partners_meta,
            }

        # Create Lot + LotStock per item.
        for item, item_value_uzs in zip(items, items_value_uzs):
            item_unit_price_uzs = (
                Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
            ).quantize(Decimal('0.01'))
            allocated_expense_uzs = (
                expenses_total_uzs * (item_value_uzs / total_value_uzs)
            ).quantize(Decimal('0.01'))
            qty = int(Decimal(str(item.quantity)))
            if qty <= 0:
                continue
            landed_per_unit = (
                item_unit_price_uzs + (allocated_expense_uzs / qty)
            ).quantize(Decimal('0.01'))

            lot = Lot.objects.create(
                tenant_id=tenant_id,
                procurement_item=item,
                product_variant_id=item.product_variant_id,
                quantity_initial=qty,
                unit_purchase_price=item_unit_price_uzs,
                landed_cost_per_unit=landed_per_unit,
                contract_snapshot=contract_snapshot,
                received_at=received_at,
                is_active=True,
            )
            LotStock.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                warehouse_id=destination_warehouse_id,
                quantity_remaining=qty,
            )
            StockMovement.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity=qty,
                to_location_id=destination_warehouse_id,
                reference_type='procurement',
                reference_id=procurement.pk,
            )

        procurement.status = Procurement.Status.RECEIVED
        procurement.received_at = received_at
        procurement.save(update_fields=['status', 'received_at', 'updated_at'])

        publish_event(
            event_type='procurement.received',
            payload={
                'procurement_id': procurement.pk,
                'destination_warehouse_id': destination_warehouse_id,
                'items_count': len(items),
            },
            tenant_id=tenant_id,
        )

    return procurement


# ─── Ledger ────────────────────────────────────────────────────────────────────

def get_or_create_ledger(
    *,
    procurement_id: int,
    partner_id: int,
    tenant_id: int,
):
    """Get (or lazily create) a ProcurementPartnerLedger."""
    from .models import ProcurementPartnerLedger
    ledger, _ = ProcurementPartnerLedger.objects.get_or_create(
        tenant_id=tenant_id,
        procurement_id=procurement_id,
        partner_id=partner_id,
    )
    return ledger


def append_ledger_entry(
    *,
    ledger,
    entry_type: str,
    amount: Decimal,
    currency: str = 'UZS',
    source_ref: str = '',
    date=None,
):
    """
    Append an immutable entry to a ProcurementPartnerLedger.
    Always call inside a transaction.atomic().
    """
    from .models import PartnerLedgerEntry
    if date is None:
        date = timezone.now()
    return PartnerLedgerEntry.objects.create(
        tenant_id=ledger.tenant_id,
        ledger=ledger,
        date=date,
        amount=amount,
        currency=currency,
        entry_type=entry_type,
        source_ref=source_ref,
    )


def get_partner_aggregate(partner_id: int, tenant_id: int) -> dict:
    """
    Compute partner summary across all procurements — replaces InvestorSummary.
    Returns:
    {
        capital_in, capital_out, profit_accrued, profit_reversed,
        dividends_paid, losses_incurred, profit_pending_payout
    }
    all in UZS (multi-currency not yet normalised — PR-7 brings FX rates).
    """
    from .models import PartnerLedgerEntry, ProcurementPartnerLedger

    ledger_ids = ProcurementPartnerLedger.objects.filter(
        partner_id=partner_id,
        tenant_id=tenant_id,
    ).values_list('id', flat=True)

    agg = (
        PartnerLedgerEntry.objects
        .filter(ledger_id__in=ledger_ids)
        .values('entry_type')
        .annotate(total=models.Sum('amount'))
    )
    totals = {row['entry_type']: row['total'] or Decimal('0') for row in agg}

    capital_in = totals.get('CAPITAL_IN', Decimal('0'))
    capital_out = totals.get('CAPITAL_OUT', Decimal('0'))
    profit_accrued = totals.get('PROFIT_ACCRUED', Decimal('0'))
    profit_reversed = totals.get('PROFIT_REVERSED', Decimal('0'))
    dividends_paid = totals.get('DIVIDEND_PAID', Decimal('0'))
    losses = totals.get('LOSS_INCURRED', Decimal('0'))

    profit_net = profit_accrued - profit_reversed - losses
    profit_pending_payout = max(Decimal('0'), profit_net - dividends_paid)

    return {
        'capital_in': capital_in,
        'capital_out': capital_out,
        'capital_net': capital_in - capital_out,
        'profit_accrued': profit_accrued,
        'profit_reversed': profit_reversed,
        'losses_incurred': losses,
        'dividends_paid': dividends_paid,
        'profit_pending_payout': profit_pending_payout,
    }


def pay_dividend(
    *,
    partner_id: int,
    procurement_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    from_account_id: int | None = None,
    tenant_id: int,
    date=None,
):
    """
    Record a dividend payout to a partner.
    Invariant: amount <= profit_pending_payout for this procurement.
    Raises ValueError if invariant violated.
    """
    from .models import DividendPayment, ProcurementPartnerLedger, PartnerLedgerEntry

    if date is None:
        date = timezone.now()

    with transaction.atomic():
        ledger = get_or_create_ledger(
            procurement_id=procurement_id,
            partner_id=partner_id,
            tenant_id=tenant_id,
        )

        # Compute pending payout for this specific procurement
        agg = (
            PartnerLedgerEntry.objects
            .filter(ledger=ledger)
            .values('entry_type')
            .annotate(total=models.Sum('amount'))
        )
        totals = {row['entry_type']: row['total'] or Decimal('0') for row in agg}

        profit_net = (
            totals.get('PROFIT_ACCRUED', Decimal('0'))
            - totals.get('PROFIT_REVERSED', Decimal('0'))
            - totals.get('LOSS_INCURRED', Decimal('0'))
        )
        already_paid = totals.get('DIVIDEND_PAID', Decimal('0'))
        pending = max(Decimal('0'), profit_net - already_paid)

        if amount > pending:
            raise ValueError(
                f'Dividend amount {amount} exceeds pending payout {pending} '
                f'for partner {partner_id}, procurement {procurement_id}.'
            )

        payment = DividendPayment.objects.create(
            tenant_id=tenant_id,
            partner_id=partner_id,
            procurement_id=procurement_id,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            paid_from_account_id=from_account_id,
            date=date,
        )

        append_ledger_entry(
            ledger=ledger,
            entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID,
            amount=amount,
            currency=currency,
            source_ref=f'dividend_payment:{payment.pk}',
            date=date,
        )

        publish_event(
            event_type='partnership.dividend_paid',
            payload={
                'payment_id': payment.pk,
                'partner_id': partner_id,
                'procurement_id': procurement_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )

    return payment
