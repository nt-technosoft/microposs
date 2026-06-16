"""workspace_payload.py — cluster A: read/payload layer (money-neutral).

build_workspace_payload and all _*_payload / _display / _flow_* helpers.
No money mutations, no @transaction.atomic, no OutboxEvent.

Audit reference: E18 Фаза 2 / T-2.4 (step b).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.finance.models import Payment
from apps.suppliers.models import SupplierPayable

from .models import (
    AgreementAllocation,
    Procurement,
    ProcurementExpense,
    ProcurementItem,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
)
from .policies import ProcurementPolicyContext, evaluate_procurement_policy
from .procurement_cost import procurement_cost_by_currency
from .workspace_common import (
    _agreement_available_by_partner,
    _has_capital_activity,
    _has_payment_activity,
    _landed_expense_allocations,
    _primary_currency,
    _received_quantity,
    _SUPPLIER_OPTIONAL_TYPES,
)

ACTION_MAP = {
    'edit_source': 'UPDATE_SOURCE',
    'edit_items': 'UPDATE_ITEMS',
    'pay': 'PAY_COSTS',
    'pay_from_capital_pool': 'PAY_COSTS',
    'resolve_overpayment': 'RESOLVE_OVERPAYMENT',
    'pay_supplier_payable': 'PAY_SUPPLIER_PAYABLE',
    'receive': 'RECEIVE_BATCH',
    'amend_terms': 'AMEND_SETTLEMENT',
    'view_history': 'VIEW_HISTORY',
    'cancel': 'CANCEL_PROCUREMENT',
    'reverse_batch': 'REVERSE_BATCH',
    'amend_items': 'AMEND_ITEMS',
    'amend_expenses': 'AMEND_EXPENSES',
}

ACTION_LABELS = {
    'UPDATE_SOURCE': 'Выбрать поставщика',
    'UPDATE_ITEMS': 'Добавить товары',
    'UPDATE_EXPENSES': 'Добавить расходы',
    'UPDATE_SETTLEMENT': 'Выбрать условия',
    'CREATE_INVESTMENT_AGREEMENT': 'Создать договор',
    'LINK_INVESTMENT_AGREEMENT': 'Привязать договор',
    'RECORD_CAPITAL_CONTRIBUTION': 'Внести капитал',
    'ALLOCATE_CAPITAL': 'Распределить капитал',
    'CONVERT_CAPITAL_POOL': 'Конвертировать валюту пула',
    'PAY_COSTS': 'Оплатить',
    'RESOLVE_OVERPAYMENT': 'Закрыть переплату',
    'PAY_SUPPLIER_PAYABLE': 'Оплатить поставщика',
    'GENERATE_INSTALLMENT_SCHEDULE': 'Сгенерировать график',
    'RECEIVE_BATCH': 'Принять товар',
    'AMEND_SETTLEMENT': 'Изменить условия',
    'AMEND_ITEMS': 'Изменить товары',
    'AMEND_EXPENSES': 'Изменить расходы',
    'RETURN_CONSIGNMENT': 'Вернуть консигнацию',
    'VIEW_HISTORY': 'Посмотреть историю',
    'CLOSE_WORKSPACE': 'Закрыть приход',
    'CANCEL_WORKSPACE': 'Отменить приход',
}

SECTION_TITLES = {
    'overview': 'Overview',
    'source': 'Source',
    'items_landed_cost': 'Items & Landed Cost',
    'settlement': 'Settlement',
    'capital': 'Capital',
    'receive': 'Receive',
    'history': 'History',
}

SECTION_KEY_MAP = {
    'items_landed_cost': 'items',
}

FLOW_TITLES = {
    'purchase_intent': 'Goods and landed costs',
    'supplier_settlement': 'Supplier and settlement',
    'funding': 'Money source',
    'payment_obligation': 'Payment / obligation',
    'goods_receipt': 'Goods receipt',
    'history': 'History and audit',
}


def build_workspace_payload(procurement: Procurement) -> dict:
    terms = getattr(procurement, 'terms', None)
    receive_batches = list(procurement.receive_batches.all())
    payables = list(SupplierPayable.objects.filter(procurement=procurement))
    has_items = procurement.items.exclude(
        lifecycle_state=ProcurementItem.LifecycleState.CANCELLED,
    ).exists()
    capital_activity = _has_capital_activity(procurement)
    context = ProcurementPolicyContext(
        funding_source=procurement.funding_source,
        settlement_type=getattr(terms, 'type', None),
        status=procurement.status,
        has_supplier=bool(procurement.supplier_id),
        has_investment_agreement=bool(procurement.agreement_id),
        has_items=has_items,
        has_partnership_capital_activity=(
            capital_activity
            and procurement.funding_source != Procurement.FundingSource.PARTNERSHIP
        ),
        has_capital_activity=capital_activity,
        has_payment_activity=_has_payment_activity(procurement, payables),
        has_receive_batches=bool(receive_batches),
        has_installment_schedule=bool(terms and terms.schedule_entries.exists()),
    )
    policy = evaluate_procurement_policy(context)

    return {
        'id': procurement.id,
        'status': procurement.status,
        'display': _display(procurement, policy),
        'flow': _flow_payload(procurement, policy, terms, payables, receive_batches, has_items),
        'policy': _policy_payload(policy, terms),
        'readiness': _readiness_payload(policy.readiness, policy.blocked_reasons),
        'sections': _sections_payload(policy),
        'documents': _documents_payload(
            procurement,
            terms,
            payables,
            receive_batches,
            _payments_for_procurement(procurement, payables),
        ),
        'summaries': _summaries_payload(procurement, payables),
        'history': _history_payload(procurement, receive_batches, payables),
    }


def _display(procurement: Procurement, policy) -> dict:
    next_action = None
    if policy.allowed_actions:
        next_action = ACTION_MAP.get(policy.allowed_actions[0], policy.allowed_actions[0])
    return {
        'title': f'Procurement #{procurement.id}',
        'subtitle': getattr(procurement.supplier, 'name', None),
        'created_at': procurement.opened_at.isoformat(),
        'updated_at': procurement.updated_at.isoformat(),
        'primary_currency': _primary_currency(procurement),
        'next_action': {
            'key': next_action,
            'label': ACTION_LABELS.get(next_action, next_action) if next_action else None,
            'reason': policy.blocked_reasons[0] if policy.blocked_reasons else None,
        },
    }


def _policy_payload(policy, terms) -> dict:
    allowed_actions = [
        ACTION_MAP.get(action, action)
        for action in policy.allowed_actions
    ]
    if policy.normalized_funding_source == Procurement.FundingSource.PARTNERSHIP:
        for action in (
            'CREATE_INVESTMENT_AGREEMENT',
            'LINK_INVESTMENT_AGREEMENT',
            'RECORD_CAPITAL_CONTRIBUTION',
            'ALLOCATE_CAPITAL',
        ):
            if action not in allowed_actions:
                allowed_actions.append(action)
    if 'UPDATE_ITEMS' in allowed_actions and 'SPLIT_ITEM' not in allowed_actions:
        allowed_actions.append('SPLIT_ITEM')
    if getattr(terms, 'type', None) == ProcurementTerms.Type.INSTALLMENT and 'GENERATE_INSTALLMENT_SCHEDULE' not in allowed_actions:
        allowed_actions.append('GENERATE_INSTALLMENT_SCHEDULE')
    return {
        'funding_source': policy.normalized_funding_source,
        'settlement_type': getattr(terms, 'type', None),
        'allowed_settlements': list(policy.allowed_settlements),
        'visible_sections': [_section_key(section) for section in policy.visible_sections],
        'locked_sections': {},
        'allowed_actions': allowed_actions,
        'blocked_reasons': [
            {'code': f'BLOCKED_{index + 1}', 'message': reason}
            for index, reason in enumerate(policy.blocked_reasons)
        ],
    }


def _flow_payload(
    procurement: Procurement,
    policy,
    terms,
    payables,
    receive_batches,
    has_items: bool,
) -> dict:
    readiness = policy.readiness
    purchase_complete = has_items
    settlement_complete = bool(terms and readiness.get('settlement_ready'))
    funding_complete = _funding_flow_complete(procurement)
    payment_complete = _payment_obligation_complete(procurement, terms, payables)
    receipt_complete = procurement.status in (
        Procurement.Status.RECEIVED,
        Procurement.Status.CLOSED,
    )

    steps = [
        _flow_step(
            key='purchase_intent',
            complete=purchase_complete,
            previous_complete=True,
            readiness_keys=['items_ready', 'expenses_ready'],
            primary_actions=['UPDATE_ITEMS', 'UPDATE_EXPENSES', 'SPLIT_ITEM'],
            blocked_reason=None,
        ),
        _flow_step(
            key='supplier_settlement',
            complete=settlement_complete,
            previous_complete=purchase_complete,
            readiness_keys=['source_ready', 'settlement_ready'],
            primary_actions=['UPDATE_SETTLEMENT', 'AMEND_SETTLEMENT', 'GENERATE_INSTALLMENT_SCHEDULE'],
            blocked_reason='Add at least one item before supplier settlement.' if not purchase_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='funding',
            complete=funding_complete,
            previous_complete=purchase_complete and settlement_complete,
            readiness_keys=['source_ready', 'capital_ready'],
            primary_actions=['UPDATE_SOURCE', 'CREATE_INVESTMENT_AGREEMENT', 'LINK_INVESTMENT_AGREEMENT'],
            blocked_reason='Complete supplier settlement before funding.' if not settlement_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='payment_obligation',
            complete=payment_complete,
            previous_complete=purchase_complete and settlement_complete and funding_complete,
            readiness_keys=['payment_ready', 'capital_ready'],
            primary_actions=[
                'PAY_COSTS',
                'PAY_SUPPLIER_PAYABLE',
                'RECORD_CAPITAL_CONTRIBUTION',
                'ALLOCATE_CAPITAL',
                'GENERATE_INSTALLMENT_SCHEDULE',
            ],
            blocked_reason='Complete funding before payment or obligation.' if not funding_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='goods_receipt',
            complete=receipt_complete,
            previous_complete=(
                purchase_complete
                and settlement_complete
                and funding_complete
                and payment_complete
            ),
            readiness_keys=['receive_ready'],
            primary_actions=['RECEIVE_BATCH'],
            blocked_reason='Complete payment/obligation facts before receive.' if not payment_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='history',
            complete=bool(receive_batches) or receipt_complete,
            previous_complete=True,
            readiness_keys=[],
            primary_actions=['VIEW_HISTORY'],
            blocked_reason=None,
        ),
    ]
    current = next((step for step in steps if step['key'] != 'history' and step['status'] != 'complete'), steps[-1])
    allowed = set(_allowed_action_keys(policy, terms))
    next_action = next((action for action in current['primary_actions'] if action in allowed), None)
    return {
        'current_step': current['key'],
        'steps': steps,
        'next_action': next_action,
    }


def _flow_step(
    *,
    key: str,
    complete: bool,
    previous_complete: bool,
    readiness_keys: list[str],
    primary_actions: list[str],
    blocked_reason: str | None,
) -> dict:
    if complete:
        status = 'complete'
        reason = None
    elif previous_complete:
        status = 'ready'
        reason = None
    else:
        status = 'blocked'
        reason = blocked_reason
    return {
        'key': key,
        'title': FLOW_TITLES[key],
        'status': status,
        'readiness_keys': readiness_keys,
        'primary_actions': primary_actions,
        'blocked_reason': reason,
    }


def _funding_flow_complete(procurement: Procurement) -> bool:
    if procurement.funding_source == Procurement.FundingSource.OWN_FUNDS:
        return True
    return bool(procurement.agreement_id)


def _payment_obligation_complete(procurement: Procurement, terms, payables) -> bool:
    if procurement.status in (Procurement.Status.RECEIVED, Procurement.Status.CLOSED):
        return True
    if not terms:
        return False
    if terms.type in (
        ProcurementTerms.Type.DEFERRED,
        ProcurementTerms.Type.INSTALLMENT,
        ProcurementTerms.Type.ON_SALE,
    ):
        return True
    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        payment_status = _payment_status_block(
            terms,
            [],
            items=list(procurement.items.all()),
            expenses=list(procurement.expenses.all()),
            capital_allocations=list(AgreementAllocation.objects.filter(
                tenant_id=procurement.tenant_id,
                procurement=procurement,
            )),
        )
        return payment_status['state'] in ('paid_full', 'overpaid')
    payment_status = _payment_status_block(
        terms,
        list(Payment.objects.filter(
            tenant_id=procurement.tenant_id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.pk,
            status=Payment.Status.POSTED,
        )),
        items=list(procurement.items.all()),
        expenses=list(procurement.expenses.all()),
    )
    return payment_status['state'] in ('paid_full', 'overpaid') or _has_payment_activity(procurement, payables)


def _terms_status_for_paid_amount(total_amount_due: Decimal, paid_amount: Decimal) -> str:
    total = Decimal(str(total_amount_due or 0)).quantize(Decimal('0.01'))
    paid = Decimal(str(paid_amount or 0)).quantize(Decimal('0.01'))
    if total > 0 and paid >= total:
        return ProcurementTerms.Status.FULLY_PAID
    if paid > 0:
        return ProcurementTerms.Status.PARTIALLY_PAID
    return ProcurementTerms.Status.OPEN


def _allowed_action_keys(policy, terms) -> list[str]:
    actions = [ACTION_MAP.get(action, action) for action in policy.allowed_actions]
    if policy.normalized_funding_source == Procurement.FundingSource.PARTNERSHIP:
        actions.extend([
            'CREATE_INVESTMENT_AGREEMENT',
            'LINK_INVESTMENT_AGREEMENT',
            'RECORD_CAPITAL_CONTRIBUTION',
            'ALLOCATE_CAPITAL',
        ])
    if getattr(terms, 'type', None) == ProcurementTerms.Type.INSTALLMENT:
        actions.append('GENERATE_INSTALLMENT_SCHEDULE')
    return list(dict.fromkeys(actions))


def _first_blocker(policy) -> str | None:
    return policy.blocked_reasons[0] if policy.blocked_reasons else None


def _readiness_payload(readiness: dict[str, bool], blocked_reasons: tuple[str, ...]) -> dict:
    payload = {}
    for key in (
        'source_ready',
        'items_ready',
        'expenses_ready',
        'settlement_ready',
        'capital_ready',
        'payment_ready',
        'receive_ready',
    ):
        ok = bool(readiness.get(key, key == 'expenses_ready'))
        payload[key] = {
            'ok': ok,
            'severity': 'ok' if ok else 'blocked',
            'message': None if ok else (blocked_reasons[0] if blocked_reasons else 'Not ready.'),
            'missing': [] if ok else [key],
        }
    return payload


def _sections_payload(policy) -> list[dict]:
    visible = {_section_key(section) for section in policy.visible_sections}
    sections = []
    for key in ('overview', 'source', 'items', 'settlement', 'capital', 'receive', 'history'):
        sections.append({
            'key': key,
            'title': SECTION_TITLES.get(key, key.title()),
            'visible': key in visible,
            'locked': False,
            'locked_reason': None,
            'readiness_key': f'{key}_ready' if key in ('source', 'settlement', 'capital', 'receive') else None,
        })
    return sections


def _documents_payload(procurement: Procurement, terms, payables, receive_batches, payments) -> dict:
    items_for_display = [
        item for item in procurement.items.all()
        if item.lifecycle_state != ProcurementItem.LifecycleState.CANCELLED
    ]
    expenses_for_display = [
        expense for expense in procurement.expenses.all()
        if expense.lifecycle_state != ProcurementExpense.LifecycleState.CANCELLED
    ]
    item_cost_preview = _item_cost_preview(procurement)

    return {
        'procurement': {
            'id': procurement.id,
            'status': procurement.status,
            'supplier_id': procurement.supplier_id,
            'supplier_name': getattr(procurement.supplier, 'name', None),
            'primary_currency': procurement.primary_currency,
            'notes': procurement.notes,
            'opened_at': procurement.opened_at.isoformat(),
            'closed_at': procurement.closed_at.isoformat() if procurement.closed_at else None,
        },
        'source': {
            'funding_source': procurement.funding_source,
            'supplier_required': bool(terms and terms.type not in _SUPPLIER_OPTIONAL_TYPES),
            'supplier_id': procurement.supplier_id,
            'investment_agreement_required': procurement.funding_source == Procurement.FundingSource.PARTNERSHIP,
            'investment_agreement_id': procurement.agreement_id,
        },
        # Display lists exclude soft-deleted (CANCELLED) lines at the source, so no
        # frontend consumer (items / expenses / payment selection) can leak them.
        # Cancelled lines remain available via amendments/history, not here.
        'items': [
            _item_payload(item, item_cost_preview.get(item.id)) for item in items_for_display
        ],
        'expenses': [
            _expense_payload(expense) for expense in expenses_for_display
        ],
        'settlement': _settlement_payload(terms),
        'payables': [_payable_payload(payable) for payable in payables],
        'payments': [_payment_payload(payment) for payment in payments],
        'investment': _investment_payload(procurement),
        'receive_batches': [_receive_batch_payload(batch) for batch in receive_batches],
        'lots_preview': [],
        'payment_status': _payment_status_block(
            terms, payments,
            items=list(procurement.items.all()),
            expenses=list(procurement.expenses.all()),
            capital_allocations=list(
                AgreementAllocation.objects.filter(
                    tenant_id=procurement.tenant_id,
                    procurement=procurement,
                )
            ),
        ),
    }


def _item_payload(item, cost_preview: dict | None = None) -> dict:
    return {
        'id': item.id,
        'product_variant_id': item.product_variant_id,
        'product_variant_name': str(item.product_variant),
        'quantity': str(item.quantity),
        'unit_purchase_price': str(item.unit_purchase_price),
        'currency': item.currency,
        'fx_rate': str(item.fx_rate),
        'goods_ownership': item.goods_ownership,
        'lifecycle_state': item.lifecycle_state,
        'payment_state': _legacy_payment_state(item.lifecycle_state),
        'received_quantity': str(_received_quantity(item)),
        'remaining_quantity': str(Decimal(str(item.quantity)) - _received_quantity(item)),
        'locked_reason': None if item.lifecycle_state == item.LifecycleState.DRAFT else 'Line already has facts.',
        **(cost_preview or {}),
    }


def _expense_payload(expense) -> dict:
    return {
        'id': expense.id,
        'expense_type': expense.expense_type,
        'amount': str(expense.amount),
        'currency': expense.currency,
        'fx_rate': str(expense.fx_rate),
        'allocation_method': expense.allocation_method,
        'target_item_ids': list(expense.targets.values_list('item_id', flat=True)),
        'lifecycle_state': expense.lifecycle_state,
        'payment_state': _legacy_payment_state(expense.lifecycle_state),
        'locked_reason': None if expense.lifecycle_state == expense.LifecycleState.DRAFT else 'Expense already has facts.',
    }


def _payment_status_block(terms, payments: list, items=None, expenses=None, capital_allocations=None) -> dict:
    """obligation vs paid, PER CURRENCY. Single source = procurement_cost_by_currency.

    Supports mixed-currency procurement (e.g. USD goods + UZS local logistics):
    obligation/paid/remaining are grouped by currency, never collapsed with × fx.
    Backward-compat single fields are populated only when there's one currency.
    """
    if items is not None:
        active_items = [i for i in items if i.lifecycle_state != 'CANCELLED']
        active_expenses = [e for e in (expenses or []) if e.lifecycle_state != 'CANCELLED']
        obligation_by_currency = procurement_cost_by_currency(active_items, active_expenses)
        paid_by_currency: dict[str, Decimal] = {}
        if capital_allocations:
            for allocation in capital_allocations:
                cur = str(getattr(allocation, 'currency', 'UZS') or 'UZS').upper()
                delta = Decimal(str(allocation.amount))
                if allocation.direction != AgreementAllocation.Direction.TO_PROCUREMENT:
                    delta = -delta
                paid_by_currency[cur] = paid_by_currency.get(cur, Decimal('0')) + delta
        else:
            for payment in (payments or []):
                if getattr(payment, 'status', Payment.Status.POSTED) != Payment.Status.POSTED:
                    continue
                cur = str(getattr(payment, 'currency', 'UZS') or 'UZS').upper()
                delta = Decimal(str(payment.amount))
                if getattr(payment, 'reversed_payment_id', None):
                    delta = -delta
                paid_by_currency[cur] = paid_by_currency.get(cur, Decimal('0')) + delta
    else:
        cur = str(getattr(terms, 'currency_of_obligation', 'UZS') or 'UZS').upper()
        amt = Decimal(str(getattr(terms, 'total_amount_due', 0) or 0)).quantize(Decimal('0.01'))
        obligation_by_currency = {cur: amt} if amt else {}

        paid_by_currency: dict[str, Decimal] = {}
        for p in (payments or []):
            cur = str(getattr(p, 'currency', 'UZS') or 'UZS').upper()
            delta = Decimal(str(p.amount))
            if getattr(p, 'reversed_payment_id', None):
                delta = -delta
            paid_by_currency[cur] = paid_by_currency.get(cur, Decimal('0')) + delta
    paid_by_currency = {c: Decimal(str(v)).quantize(Decimal('0.01')) for c, v in paid_by_currency.items()}

    currencies = set(obligation_by_currency) | set(paid_by_currency)
    remaining_by_currency: dict[str, Decimal] = {}
    any_remaining = False
    any_overpaid = False
    for c in currencies:
        rem = (obligation_by_currency.get(c, Decimal('0')) - paid_by_currency.get(c, Decimal('0'))).quantize(Decimal('0.01'))
        remaining_by_currency[c] = rem
        if rem > 0:
            any_remaining = True
        if rem < 0:
            any_overpaid = True

    any_paid = bool(paid_by_currency)
    total_obligation = sum(obligation_by_currency.values(), Decimal('0'))
    if total_obligation == 0 and not any_paid:
        state = 'unpaid'
    elif not any_paid:
        state = 'unpaid'
    elif any_remaining:
        state = 'underpaid'
    elif any_overpaid:
        state = 'overpaid'
    else:
        state = 'paid_full'

    # Backward-compat single fields — meaningful only for single-currency obligation.
    if len(obligation_by_currency) == 1:
        cur = next(iter(obligation_by_currency))
        obligation_amount = str(obligation_by_currency[cur])
        paid_amount = str(paid_by_currency.get(cur, Decimal('0')))
        delta = str((paid_by_currency.get(cur, Decimal('0')) - obligation_by_currency[cur]).quantize(Decimal('0.01')))
        single_currency = cur
    else:
        obligation_amount = paid_amount = delta = None
        single_currency = None

    return {
        'obligation_by_currency': {c: str(v) for c, v in obligation_by_currency.items()},
        'paid_by_currency': {c: str(v) for c, v in paid_by_currency.items()},
        'remaining_by_currency': {c: str(v) for c, v in remaining_by_currency.items()},
        'state': state,
        'obligation_amount': obligation_amount,
        'paid_amount': paid_amount,
        'delta': delta,
        'currency': single_currency,
    }


def _settlement_payload(terms) -> dict | None:
    if not terms:
        return None
    return {
        'id': terms.id,
        'type': terms.type,
        'currency_of_obligation': terms.currency_of_obligation,
        'fx_rate_at_obligation': str(terms.fx_rate_at_obligation),
        'total_amount_due': str(terms.total_amount_due),
        'paid_amount': str(terms.paid_amount),
        'remaining_amount': str(terms.remaining_amount),
        'deadline_date': terms.deadline_date.isoformat() if terms.deadline_date else None,
        'consignment_mode': None,
        'notes': terms.notes,
        'schedule': [
            {
                'id': row.id,
                'sequence_number': row.sequence_number,
                'due_date': row.due_date.isoformat(),
                'amount': str(row.amount),
                'currency': row.currency,
                'status': row.status,
                'paid_at': row.paid_at.isoformat() if row.paid_at else None,
                'paid_amount': str(row.paid_amount),
            }
            for row in terms.schedule_entries.order_by('sequence_number')
        ],
    }


def _payable_payload(payable) -> dict:
    return {
        'id': payable.id,
        'supplier_id': payable.supplier_id,
        'supplier_name': getattr(payable.supplier, 'name', None),
        'original_amount': str(payable.original_amount),
        'paid_amount': str(payable.paid_amount),
        'remaining_amount': str(payable.remaining_amount),
        'currency': payable.currency_of_obligation,
        'status': payable.status,
        'due_date': payable.deadline_date.isoformat() if payable.deadline_date else None,
    }


def _payment_payload(payment: Payment) -> dict:
    return {
        'id': payment.id,
        'target_type': payment.target_type,
        'target_id': payment.target_id,
        'source_type': payment.source_type,
        'source_id': payment.source_id,
        'amount': str(payment.amount),
        'currency': payment.currency,
        'fx_rate': str(payment.fx_rate),
        'status': payment.status,
        'paid_at': payment.paid_at.isoformat(),
        'journal_entry_id': payment.journal_entry_id,
    }


def _investment_payload(procurement: Procurement) -> dict | None:
    agreement = procurement.agreement
    if not agreement:
        return None
    available = _agreement_available_by_partner(agreement)
    pool_account = agreement.capital_account
    return {
        'agreement_id': agreement.id,
        'agreement_label': f'Investment agreement #{agreement.id}',
        'opened_at': agreement.opened_at.isoformat(),
        'legal_mode': agreement.legal_mode,
        'reconciliation_mode': agreement.reconciliation_mode,
        'currency': agreement.currency,
        'planned_budget': str(agreement.planned_budget),
        'pool': ({
            'cash_account_id': pool_account.id,
            'currency': pool_account.currency,
            'balance': str(pool_account.balance),
        } if pool_account else None),
        # E12: all physical currency sub-pools of the agreement (base + converted).
        'currency_pools': [
            {
                'currency': sub.cash_account.currency,
                'cash_account_id': sub.cash_account_id,
                'balance': str(sub.cash_account.balance),
                'is_base': sub.cash_account.currency.upper() == str(agreement.currency or 'UZS').upper(),
            }
            for sub in agreement.currency_pools.select_related('cash_account').all()
        ],
        'partners': [
            {
                'partner_id': member.partner_id,
                'partner_name': getattr(member.partner, 'display_name', str(member.partner_id)),
                'role': member.role,
                'planned_capital_share': str(member.planned_capital_share),
                'profit_share': str(member.profit_share),
            }
            for member in agreement.partners.select_related('partner').all()
        ],
        'commitments': [
            {
                'id': commitment.id,
                'partner_id': commitment.partner_id,
                'partner_name': getattr(commitment.partner, 'display_name', str(commitment.partner_id)),
                'amount': str(commitment.amount),
                'currency': commitment.currency,
                'fx_rate': str(commitment.fx_rate),
                'date': commitment.date.isoformat(),
                'source': commitment.source,
                'confirmation_status': commitment.confirmation_status,
                'notes': commitment.notes,
            }
            for commitment in agreement.commitments.select_related('partner').all()
        ],
        'contributions': [
            {
                'id': contribution.id,
                'partner_id': contribution.partner_id,
                'partner_name': getattr(contribution.partner, 'display_name', str(contribution.partner_id)),
                'amount': str(contribution.amount),
                'currency': contribution.currency,
                'fx_rate': str(contribution.fx_rate),
                'date': contribution.date.isoformat(),
                'source': contribution.source,
                'confirmation_status': contribution.confirmation_status,
                'notes': contribution.notes,
            }
            for contribution in agreement.contributions.select_related('partner').all()
        ],
        'allocations': [
            {
                'id': allocation.id,
                'procurement_id': allocation.procurement_id,
                'partner_id': allocation.partner_id,
                'partner_name': getattr(allocation.partner, 'display_name', str(allocation.partner_id)),
                'direction': allocation.direction,
                'amount': str(allocation.amount),
                'currency': allocation.currency,
                'fx_rate': str(allocation.fx_rate),
                'date': allocation.date.isoformat(),
                'source': allocation.source,
                'confirmation_status': allocation.confirmation_status,
                'notes': allocation.notes,
            }
            for allocation in agreement.allocations.select_related('partner').filter(procurement=procurement)
        ],
        'events': [
            {
                'id': event.id,
                'event_type': event.event_type,
                'occurred_at': event.occurred_at.isoformat(),
                'source': event.source,
                'actor_user_id': event.actor_user_id,
                'actor_partner_id': event.actor_partner_id,
                'actor_partner_name': getattr(event.actor_partner, 'display_name', None),
                'related_model': event.related_model,
                'related_id': event.related_id,
                'payload': event.payload,
            }
            for event in agreement.events.select_related('actor_user', 'actor_partner').all()[:30]
        ],
        'available_by_partner': {
            str(partner_id): {
                currency: str(amount)
                for currency, amount in amounts.items()
            }
            for partner_id, amounts in available.items()
        },
    }


def _receive_batch_payload(batch) -> dict:
    capital_rows = list(batch.capital_allocations.select_related('partner').all())
    return {
        'id': batch.id,
        'received_at': batch.received_at.isoformat(),
        'warehouse_id': batch.warehouse_id,
        'warehouse_name': getattr(batch.warehouse, 'name', ''),
        'status': 'POSTED',
        'inventory_total_uzs': str(batch.total_inventory_uzs),
        'lines': [
            {
                'id': line.id,
                'item_id': line.item_id,
                'lot_id': line.lot_id,
                'product_variant_id': line.item.product_variant_id,
                'product_variant_name': str(line.item.product_variant),
                'quantity_planned': str(line.quantity_planned),
                'quantity_received': str(line.quantity_received),
                'quantity': str(line.quantity_received),
                'discrepancy_reason': line.discrepancy_reason,
                'unit_purchase_price_uzs': str(line.unit_purchase_price_uzs),
                'allocated_expense_uzs': str(line.allocated_expense_uzs),
                'landed_cost_per_unit_uzs': str(line.landed_cost_per_unit_uzs),
            }
            for line in batch.lines.select_related('item__product_variant', 'lot').all()
        ],
        'expenses': [
            {
                'id': row.id,
                'expense_id': row.expense_id,
                'expense_type': row.expense.expense_type,
                'allocated_amount_uzs': str(row.allocated_amount_uzs),
            }
            for row in batch.expenses.select_related('expense').all()
        ],
        'capital_snapshot': (
            {
                'currency': getattr(batch.procurement.agreement, 'currency', 'UZS'),
                'required_amount': str(sum(
                    (Decimal(str(row.amount_contract_currency)) for row in capital_rows),
                    Decimal('0'),
                ).quantize(Decimal('0.01'))),
                'partners': [
                    {
                        'partner_id': row.partner_id,
                        'partner_name': getattr(row.partner, 'display_name', str(row.partner_id)),
                        'capital_amount': str(row.amount_contract_currency),
                        'capital_share': str(row.capital_share),
                        'profit_share': str(row.profit_share),
                    }
                    for row in capital_rows
                ],
            }
            if capital_rows else None
        ),
        'journal_entry_id': None,
    }


def _summaries_payload(procurement: Procurement, payables) -> dict:
    item_total = sum(
        (
            Decimal(str(item.quantity))
            * Decimal(str(item.unit_purchase_price))
            * Decimal(str(item.fx_rate))
            for item in procurement.items.all()
        ),
        Decimal('0'),
    )
    expense_total = sum(
        (
            Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate))
            for expense in procurement.expenses.all()
        ),
        Decimal('0'),
    )
    payable_total = sum(
        (Decimal(str(payable.remaining_amount)) for payable in payables),
        Decimal('0'),
    )
    return {
        'items_total_uzs': str(item_total.quantize(Decimal('0.01'))),
        'expenses_total_uzs': str(expense_total.quantize(Decimal('0.01'))),
        'payables_total': str(payable_total.quantize(Decimal('0.01'))),
        'receive_batches_count': procurement.receive_batches.count(),
    }


def _history_payload(procurement: Procurement, receive_batches, payables) -> list[dict]:
    from apps.partnerships.models import ProcurementAmendment

    history = [{
        'kind': 'WORKSPACE_OPENED',
        'date': procurement.opened_at.isoformat(),
        'title': 'Workspace opened',
        'document_id': procurement.id,
    }]
    history.extend({
        'kind': 'RECEIVE_BATCH_POSTED',
        'date': batch.received_at.isoformat(),
        'title': f'Receive batch #{batch.id}',
        'document_id': batch.id,
    } for batch in receive_batches)
    history.extend({
        'kind': 'SUPPLIER_PAYABLE_CREATED',
        'date': payable.created_at.isoformat(),
        'title': f'Supplier payable #{payable.id}',
        'document_id': payable.id,
    } for payable in payables)
    history.extend({
        'kind': 'PROCUREMENT_AMENDMENT',
        'date': amendment.amended_at.isoformat(),
        'title': (
            'Корректировка товаров'
            if amendment.target_type == ProcurementAmendment.TargetType.ITEMS
            else 'Корректировка расходов'
            if amendment.target_type == ProcurementAmendment.TargetType.EXPENSES
            else 'Корректировка'
        ),
        'document_id': amendment.id,
        'reason': amendment.reason,
    } for amendment in procurement.amendments.all())
    return sorted(history, key=lambda item: item['date'], reverse=True)


def _section_key(section: str) -> str:
    return SECTION_KEY_MAP.get(section, section)


def _legacy_payment_state(lifecycle_state: str) -> str:
    if lifecycle_state == 'READY_FOR_RECEIVE':
        return 'PAID'
    if lifecycle_state == 'RECEIVED':
        return 'PAID'
    return 'UNPAID'


def _item_cost_preview(procurement: Procurement) -> dict[int, dict]:
    previews: dict[int, dict] = {}
    active_items = list(
        procurement.items
        .filter(lifecycle_state__in=[
            ProcurementItem.LifecycleState.DRAFT,
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        ])
        .select_related('product_variant')
    )
    active_expenses = list(
        procurement.expenses
        .filter(lifecycle_state__in=[
            ProcurementExpense.LifecycleState.DRAFT,
            ProcurementExpense.LifecycleState.READY_FOR_RECEIVE,
        ])
        .prefetch_related('targets')
    )
    allocations, _expense_values = _landed_expense_allocations(active_items, active_expenses)
    for item, allocated_expense_uzs in zip(active_items, allocations):
        remaining_qty = Decimal(str(item.quantity)) - _received_quantity(item)
        if remaining_qty <= 0:
            continue
        unit_purchase_uzs = (
            Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate or '1'))
        ).quantize(Decimal('0.01'))
        landed_uzs = (
            unit_purchase_uzs + (Decimal(str(allocated_expense_uzs)) / remaining_qty)
        ).quantize(Decimal('0.01'))
        fx_rate = Decimal(str(item.fx_rate or '1'))
        previews[item.id] = {
            'estimated_allocated_expense_uzs': str(Decimal(str(allocated_expense_uzs)).quantize(Decimal('0.01'))),
            'estimated_landed_cost_per_unit_uzs': str(landed_uzs),
            'estimated_landed_cost_per_unit': str((landed_uzs / fx_rate if fx_rate else landed_uzs).quantize(Decimal('0.000001'))),
        }

    actual_rows = (
        ProcurementReceiveBatchLine.objects
        .filter(tenant_id=procurement.tenant_id, item__procurement=procurement, batch__is_reversal=False)
        .values('item_id')
        .annotate(
            qty=models.Sum('quantity_received'),
            allocated=models.Sum('allocated_expense_uzs'),
            total_landed=models.Sum(models.F('landed_cost_per_unit_uzs') * models.F('quantity_received')),
        )
    )
    fx_by_item = {
        item.id: Decimal(str(item.fx_rate or '1'))
        for item in procurement.items.all()
    }
    for row in actual_rows:
        item_id = row['item_id']
        qty = Decimal(str(row['qty'] or '0'))
        if qty <= 0:
            continue
        landed_uzs = (Decimal(str(row['total_landed'] or '0')) / qty).quantize(Decimal('0.01'))
        allocated_uzs = Decimal(str(row['allocated'] or '0')).quantize(Decimal('0.01'))
        fx_rate = fx_by_item.get(item_id, Decimal('1'))
        previews.setdefault(item_id, {}).update({
            'actual_allocated_expense_uzs': str(allocated_uzs),
            'actual_landed_cost_per_unit_uzs': str(landed_uzs),
            'actual_landed_cost_per_unit': str((landed_uzs / fx_rate if fx_rate else landed_uzs).quantize(Decimal('0.000001'))),
        })
    return previews


def _payments_for_procurement(procurement: Procurement, payables) -> list[Payment]:
    payable_ids = [payable.id for payable in payables]
    target_filter = (
        models.Q(target_type=Payment.TargetType.PROCUREMENT_COST, target_id=procurement.id)
        | models.Q(target_type=Payment.TargetType.SUPPLIER_PAYABLE, target_id__in=payable_ids)
    )
    return list(
        Payment.objects
        .filter(tenant_id=procurement.tenant_id)
        .filter(target_filter)
        .order_by('-paid_at', '-id')
    )
