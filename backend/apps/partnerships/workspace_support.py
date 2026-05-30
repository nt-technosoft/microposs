from __future__ import annotations

from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils.dateparse import parse_date
from django.utils import timezone

from apps.core.models import BusinessInvestorRelation, Partner
from apps.core.services import publish_event
from apps.partnerships.formulas import profit_shares_from_capital
from apps.partnerships.procurement_cost import procurement_cost_by_currency

from .models import (
    AgreementContribution,
    AgreementActionSource,
    AgreementConfirmationStatus,
    AgreementEvent,
    AgreementAllocation,
    AgreementPartner,
    AgreementWithdrawal,
    CapitalCommitment,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
    ProcurementItem,
    ProcurementTerms,
    ProcurementTermsAmendment,
    ProcurementPartnerLedger,
)


ZERO = Decimal('0')
CENT = Decimal('0.01')
RATIO_Q = Decimal('0.000001')


def money(amount) -> Decimal:
    return Decimal(str(amount)).quantize(CENT)


def ratio(amount) -> Decimal:
    return Decimal(str(amount)).quantize(RATIO_Q)


def functional_uzs(amount: Decimal, currency: str = 'UZS', fx_rate: Decimal = Decimal('1')) -> Decimal:
    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    fx_rate = Decimal(str(fx_rate or Decimal('1')))
    return money(amount if currency == 'UZS' else amount * fx_rate)


def get_or_create_agreement_capital_account(*, tenant_id: int, agreement: InvestmentAgreement):
    """E11: return the agreement's capital pool CashAccount, creating it if absent.

    The pool is a real CashAccount (kind=AGREEMENT_CAPITAL, linked to COA 1300,
    in the agreement currency). It is the single source of truth for partnership
    money: contributions move cash in, partnership supplier payments draw cash
    out, and the balance is read straight off the account.
    """
    from apps.finance.models import Account, CashAccount

    if agreement.capital_account_id:
        return agreement.capital_account

    coa = Account.objects.get(tenant_id=tenant_id, code='1300')
    account = CashAccount.objects.create(
        tenant_id=tenant_id,
        name=f'Капитал договора #{agreement.pk}',
        currency=str(agreement.currency or 'UZS').upper(),
        kind=CashAccount.Kind.AGREEMENT_CAPITAL,
        linked_account=coa,
        balance=ZERO,
        is_active=True,
    )
    agreement.capital_account = account
    agreement.save(update_fields=['capital_account', 'updated_at'])
    return account


def _capital_equity_account_code(*, role: str, legal_mode: str | None) -> str:
    """Role-correct equity COA for an external capital contribution.

    Investor capital is partnership equity (3110 Musharaka, else 3100 Mudaraba).
    Operator capital is the business owner's own equity (3000) — the operator is
    the owner, so it must not be booked as investor capital.
    """
    if role == AgreementPartner.Role.INVESTOR:
        if str(legal_mode) == InvestmentAgreement.LegalMode.MUSHARAKA:
            return '3110'
        return '3100'
    return '3000'


def create_investment_agreement(
    *,
    tenant_id: int,
    opened_at=None,
    supplier_id: int | None = None,
    mudaraba_ratio: Decimal,
    planned_budget: Decimal,
    currency: str = 'UZS',
    notes: str = '',
    client_request_id: str | None = None,
    created_by_id: int | None = None,
    actor_partner_id: int | None = None,
    source: str = AgreementActionSource.BUSINESS_RECORDED,
    confirmation_status: str = AgreementConfirmationStatus.CONFIRMED,
    partners: list[dict],
) -> InvestmentAgreement:
    if opened_at is None:
        opened_at = timezone.now()
    currency = str(currency or 'UZS').upper()
    mudaraba_ratio = Decimal(str(mudaraba_ratio))
    planned_budget = money(planned_budget)
    _validate_investment_agreement_payload(
        tenant_id=tenant_id,
        mudaraba_ratio=mudaraba_ratio,
        planned_budget=planned_budget,
        partners=partners,
    )

    with transaction.atomic():
        if client_request_id:
            existing = InvestmentAgreement.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        agreement = InvestmentAgreement.objects.create(
            tenant_id=tenant_id,
            status=InvestmentAgreement.Status.OPEN,
            opened_at=opened_at,
            supplier_id=supplier_id,
            mudaraba_ratio=mudaraba_ratio,
            planned_budget=planned_budget,
            currency=currency,
            notes=notes,
            client_request_id=client_request_id,
        )
        get_or_create_agreement_capital_account(tenant_id=tenant_id, agreement=agreement)
        for partner in partners:
            member = AgreementPartner.objects.create(
                tenant_id=tenant_id,
                agreement=agreement,
                partner_id=partner['partner_id'],
                role=partner['role'],
                planned_capital_share=money(partner['planned_capital_share']),
                profit_share=ratio(partner.get('profit_share', '0')),
            )
            CapitalCommitment.objects.create(
                tenant_id=tenant_id,
                agreement=agreement,
                partner_id=member.partner_id,
                amount=member.planned_capital_share,
                currency=currency,
                fx_rate=Decimal('1'),
                date=opened_at,
                source=source,
                confirmation_status=confirmation_status,
                created_by_id=created_by_id,
                actor_partner_id=actor_partner_id,
                notes='initial_agreement_plan',
                client_request_id=None,
            )
        record_agreement_event(
            tenant_id=tenant_id,
            agreement=agreement,
            event_type='agreement.opened',
            source=source,
            actor_user_id=created_by_id,
            actor_partner_id=actor_partner_id,
            related_model='InvestmentAgreement',
            related_id=agreement.pk,
            payload={
                'planned_budget': str(agreement.planned_budget),
                'currency': agreement.currency,
                'partners_count': len(partners),
            },
        )
        publish_event(
            event_type='investment_agreement.opened',
            payload={'agreement_id': agreement.pk},
            tenant_id=tenant_id,
        )
    return agreement


def add_agreement_contribution(
    *,
    tenant_id: int,
    agreement_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal | None = None,
    date=None,
    notes: str = '',
    client_request_id: str | None = None,
    created_by_id: int | None = None,
    actor_partner_id: int | None = None,
    from_cash_account_id: int | None = None,
    source: str = AgreementActionSource.BUSINESS_RECORDED,
    confirmation_status: str = AgreementConfirmationStatus.CONFIRMED,
) -> AgreementContribution:
    amount = money(amount)
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Contribution amount must be > 0.')
    if date is None:
        date = timezone.now()

    # fx_rate is the to-UZS rate for functional GL. When the caller does not
    # supply one (the UI shouldn't have to know today's rate), resolve the
    # official snapshot for non-UZS contributions so the GL is correct.
    if fx_rate in (None, '', 0, '0'):
        if currency == 'UZS':
            fx_rate = Decimal('1')
        else:
            from apps.finance.fx_rates import resolve_fx_rate_snapshot
            fx_rate = resolve_fx_rate_snapshot(
                tenant_id=tenant_id, operation_currency=currency, operation_at=date,
            )
    fx_rate = Decimal(str(fx_rate))

    with transaction.atomic():
        if client_request_id:
            existing = AgreementContribution.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id,
            tenant_id=tenant_id,
        )
        if agreement.status not in (InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE):
            raise ValueError('Cannot contribute to closed agreement.')
        member = (
            AgreementPartner.objects
            .filter(agreement=agreement, partner_id=partner_id)
            .first()
        )
        if member is None:
            raise ValueError('Selected partner is not part of this agreement.')

        contribution = AgreementContribution.objects.create(
            tenant_id=tenant_id,
            agreement=agreement,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            source=source,
            confirmation_status=confirmation_status,
            created_by_id=created_by_id,
            actor_partner_id=actor_partner_id,
            notes=notes,
            client_request_id=client_request_id,
        )

        # E11: a contribution always moves real cash into the agreement's
        # capital pool. There is no ledger-only contribution path.
        from apps.finance.services import record_capital_pool_contribution

        pool = get_or_create_agreement_capital_account(
            tenant_id=tenant_id, agreement=agreement,
        )
        record_capital_pool_contribution(
            tenant_id=tenant_id,
            pool_account_id=pool.pk,
            partner_id=partner_id,
            contribution_id=contribution.pk,
            amount=amount,
            equity_account_code=_capital_equity_account_code(
                role=member.role, legal_mode=agreement.legal_mode,
            ),
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            paid_at=date,
            from_cash_account_id=from_cash_account_id,
            client_request_id=client_request_id,
            notes=notes,
        )

        if agreement.status == InvestmentAgreement.Status.OPEN:
            agreement.status = InvestmentAgreement.Status.ACTIVE
            agreement.save(update_fields=['status', 'updated_at'])
        record_agreement_event(
            tenant_id=tenant_id,
            agreement=agreement,
            event_type='contribution.recorded',
            source=source,
            actor_user_id=created_by_id,
            actor_partner_id=actor_partner_id or partner_id,
            related_model='AgreementContribution',
            related_id=contribution.pk,
            payload={
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
                'confirmation_status': confirmation_status,
            },
        )
        publish_event(
            event_type='investment_agreement.contribution_added',
            payload={
                'agreement_id': agreement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )
    return contribution


def add_agreement_withdrawal(
    *,
    tenant_id: int,
    agreement_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    date=None,
    reason: str = '',
    client_request_id: str | None = None,
    created_by_id: int | None = None,
    actor_partner_id: int | None = None,
    source: str = AgreementActionSource.BUSINESS_RECORDED,
    confirmation_status: str = AgreementConfirmationStatus.CONFIRMED,
) -> AgreementWithdrawal:
    amount = money(amount)
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Withdrawal amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        if client_request_id:
            existing = AgreementWithdrawal.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id,
            tenant_id=tenant_id,
        )
        if agreement.status not in (InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE):
            raise ValueError('Cannot withdraw from closed agreement.')
        if not AgreementPartner.objects.filter(agreement=agreement, partner_id=partner_id).exists():
            raise ValueError('Selected partner is not part of this agreement.')

        available = _agreement_partner_available(
            agreement=agreement,
            partner_id=partner_id,
            currency=currency,
        )
        if available < amount:
            raise ValueError(
                f'Нельзя вернуть {money(amount)} {currency}: '
                f'у выбранной стороны доступно только {money(available)} {currency}.'
            )

        withdrawal = AgreementWithdrawal.objects.create(
            tenant_id=tenant_id,
            agreement=agreement,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            source=source,
            confirmation_status=confirmation_status,
            created_by_id=created_by_id,
            actor_partner_id=actor_partner_id,
            reason=reason,
            client_request_id=client_request_id,
        )
        record_agreement_event(
            tenant_id=tenant_id,
            agreement=agreement,
            event_type='withdrawal.recorded',
            source=source,
            actor_user_id=created_by_id,
            actor_partner_id=actor_partner_id or partner_id,
            related_model='AgreementWithdrawal',
            related_id=withdrawal.pk,
            payload={
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
                'confirmation_status': confirmation_status,
            },
        )
        publish_event(
            event_type='investment_agreement.withdrawal_added',
            payload={
                'agreement_id': agreement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )
    return withdrawal


def record_agreement_event(
    *,
    tenant_id: int,
    agreement: InvestmentAgreement,
    event_type: str,
    source: str = AgreementActionSource.BUSINESS_RECORDED,
    actor_user_id: int | None = None,
    actor_partner_id: int | None = None,
    related_model: str = '',
    related_id: int | None = None,
    payload: dict | None = None,
    occurred_at=None,
) -> AgreementEvent:
    if occurred_at is None:
        occurred_at = timezone.now()
    return AgreementEvent.objects.create(
        tenant_id=tenant_id,
        agreement=agreement,
        event_type=event_type,
        occurred_at=occurred_at,
        actor_user_id=actor_user_id,
        actor_partner_id=actor_partner_id,
        source=source,
        related_model=related_model,
        related_id=related_id,
        payload=payload or {},
    )


def upsert_procurement_terms_draft(tenant_id, procurement, terms_payload, schedule_payload):
    if procurement.receive_batches.exists():
        raise ValueError('Нельзя менять условия поставщика после оприходования; используйте изменение условий.')

    _validate_terms_payload_supplier(procurement, terms_payload)
    # Merge with existing terms so partial UI updates (e.g. just `type`)
    # preserve currency_of_obligation, fx_rate, deadline_date, etc.
    existing = getattr(procurement, 'terms', None)
    values = _normalize_terms_values(terms_payload, existing=existing, procurement=procurement)

    # goods_ownership is derived from timing (ON_SALE → CONSIGNED, else → OWNED).
    # Validate the resulting combination so backend stays the canonical guard.
    new_timing = values['type']
    derived_ownership = (
        Procurement.GoodsOwnership.CONSIGNED
        if new_timing == ProcurementTerms.Type.ON_SALE
        else Procurement.GoodsOwnership.OWNED
    )
    from .policies import validate_procurement_combination
    validate_procurement_combination(
        funding_source=procurement.funding_source,
        payment_timing=new_timing,
        goods_ownership=derived_ownership,
    )

    terms, _created = ProcurementTerms.objects.update_or_create(
        tenant_id=tenant_id,
        procurement=procurement,
        defaults=values,
    )

    # Cascade derived ownership onto existing draft items so the denormalized
    # copy (used at receive-time to set Lot.is_owned) stays consistent with
    # the settlement type. Only DRAFT items are touched — READY/RECEIVED items
    # are immutable.
    procurement.items.filter(
        lifecycle_state=ProcurementItem.LifecycleState.DRAFT,
    ).exclude(goods_ownership=derived_ownership).update(
        goods_ownership=derived_ownership,
    )

    if values['type'] == ProcurementTerms.Type.INSTALLMENT:
        if schedule_payload:
            _replace_payment_schedule(tenant_id, terms, schedule_payload)
    elif terms.schedule_entries.exists():
        _replace_payment_schedule(tenant_id, terms, [])

    return terms


def generate_installment_schedule(*, tenant_id: int, procurement, payload: dict):
    terms = getattr(procurement, 'terms', None)
    if terms is None:
        raise ValueError('Installment schedule requires supplier settlement first.')
    if terms.type != ProcurementTerms.Type.INSTALLMENT:
        raise ValueError('Installment schedule can be generated only for INSTALLMENT terms.')
    if procurement.receive_batches.exists():
        raise ValueError('Cannot regenerate installment schedule after receive batches exist.')

    installments_count = int(payload.get('installments_count') or payload.get('count') or 0)
    if installments_count <= 0:
        raise ValueError('installments_count must be positive.')
    first_due_date = _coerce_date(payload.get('first_due_date'))
    if first_due_date is None:
        raise ValueError('first_due_date is required.')
    interval = str(payload.get('interval') or 'MONTHLY').upper()
    if interval not in {'MONTHLY', 'WEEKLY', 'CUSTOM'}:
        raise ValueError('Unsupported installment interval.')
    interval_days = 0
    if interval == 'CUSTOM':
        interval_days = int(payload.get('interval_days') or 0)
        if interval_days <= 0:
            raise ValueError('interval_days must be positive for CUSTOM interval.')

    total = money(payload.get('total_amount') or terms.remaining_amount)
    if total <= 0:
        raise ValueError('Installment total must be positive.')

    base_amount = (total / Decimal(installments_count)).quantize(CENT)
    rows = []
    accumulated = ZERO
    for index in range(1, installments_count + 1):
        if index == installments_count:
            amount = money(total - accumulated)
        else:
            amount = base_amount
            accumulated += amount
        rows.append({
            'sequence_number': index,
            'due_date': _next_due_date(first_due_date, interval, index - 1, interval_days),
            'amount': amount,
            'currency': terms.currency_of_obligation,
        })

    return _replace_payment_schedule(tenant_id, terms, rows)


def apply_terms_amendment(
    *,
    tenant_id: int,
    terms_id: int,
    new_fields: dict,
    reason: str = '',
    user_id: int | None = None,
) -> ProcurementTermsAmendment:
    allowed = {'deadline_date', 'total_amount_due', 'notes'}
    bad = set(new_fields) - allowed
    if bad:
        raise ValueError(f'Cannot amend fields: {bad}. Allowed: {allowed}.')

    with transaction.atomic():
        terms = ProcurementTerms.objects.select_for_update().get(pk=terms_id, tenant_id=tenant_id)
        before = {key: str(getattr(terms, key)) for key in allowed}
        after = dict(before)

        for key, value in new_fields.items():
            setattr(terms, key, value)
            after[key] = str(value)
        terms.save(update_fields=[*new_fields.keys(), 'updated_at'])

        amendment = ProcurementTermsAmendment.objects.create(
            tenant_id=tenant_id,
            terms=terms,
            amended_at=timezone.now(),
            changed_by_user_id=user_id,
            change_payload={'before': before, 'after': after},
            reason=reason,
        )

        if 'deadline_date' in new_fields:
            from apps.suppliers.models import SupplierPayable

            SupplierPayable.objects.filter(
                tenant_id=tenant_id,
                procurement=terms.procurement,
                status__in=[
                    SupplierPayable.Status.OPEN,
                    SupplierPayable.Status.PARTIALLY_PAID,
                ],
            ).update(
                deadline_date=new_fields['deadline_date'],
                updated_at=timezone.now(),
            )

        publish_event(
            event_type='procurement.terms.amended',
            payload={
                'terms_id': terms.pk,
                'procurement_id': terms.procurement_id,
                'amendment_id': amendment.pk,
                'changed_fields': list(new_fields.keys()),
            },
            tenant_id=tenant_id,
        )
    return amendment


def upsert_supplier_links_for_items(tenant_id, procurement, items, received_at) -> None:
    if procurement.supplier_id is None:
        return
    from apps.catalog.services import upsert_product_supplier_link

    for item in items:
        if not item.quantity or Decimal(str(item.quantity)) <= 0:
            continue
        upsert_product_supplier_link(
            tenant_id=tenant_id,
            product_variant_id=item.product_variant_id,
            supplier_id=procurement.supplier_id,
            unit_price=Decimal(str(item.unit_purchase_price)),
            currency=item.currency,
            quantity=Decimal(str(item.quantity)),
            received_at=received_at,
            fx_rate=Decimal(str(item.fx_rate or 1)),
        )


def get_or_create_ledger(*, procurement_id: int, partner_id: int, tenant_id: int) -> ProcurementPartnerLedger:
    ledger, _created = ProcurementPartnerLedger.objects.get_or_create(
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
    fx_rate: Decimal = Decimal('1'),
    source_ref: str = '',
    date=None,
) -> PartnerLedgerEntry:
    if date is None:
        date = timezone.now()
    currency = str(currency or 'UZS').upper()
    fx_rate = Decimal(str(fx_rate or Decimal('1')))
    return PartnerLedgerEntry.objects.create(
        tenant_id=ledger.tenant_id,
        ledger=ledger,
        date=date,
        amount=amount,
        currency=currency,
        fx_rate=fx_rate,
        functional_amount_uzs=functional_uzs(amount, currency, fx_rate),
        entry_type=entry_type,
        source_ref=source_ref,
    )


def _validate_investment_agreement_payload(
    *,
    tenant_id: int,
    mudaraba_ratio: Decimal,
    planned_budget: Decimal,
    partners: list[dict],
) -> None:
    if not partners:
        raise ValueError('At least one contract partner is required.')
    roles = {partner.get('role') for partner in partners}
    if AgreementPartner.Role.OPERATOR not in roles:
        raise ValueError('Contract must include an OPERATOR partner.')
    if mudaraba_ratio < 0 or mudaraba_ratio > 1:
        raise ValueError('mudaraba_ratio must be in [0, 1].')
    if planned_budget <= 0:
        raise ValueError('planned_budget must be positive.')
    profit_share_sum = sum(
        (Decimal(str(partner.get('profit_share', '0'))) for partner in partners),
        ZERO,
    )
    if abs(profit_share_sum - Decimal('1')) > Decimal('0.000001'):
        raise ValueError('Sum of partner profit_share must equal 1.0.')
    _validate_agreement_partner_access(tenant_id=tenant_id, partners=partners)
    _validate_agreement_formula(partners, mudaraba_ratio)


def _validate_agreement_partner_access(*, tenant_id: int, partners: list[dict]) -> None:
    partner_ids = [partner['partner_id'] for partner in partners]
    db_partners = {
        partner.id: partner
        for partner in Partner.objects.filter(
            tenant_id=tenant_id,
            id__in=partner_ids,
            is_active=True,
        )
    }
    for partner in partners:
        partner_id = int(partner['partner_id'])
        expected_role = partner.get('role')
        db_partner = db_partners.get(partner_id)
        if db_partner is None:
            raise ValueError('Contract partner is not available for this business.')
        if db_partner.role != expected_role:
            raise ValueError('Contract partner role does not match partner profile.')
        if expected_role == Partner.Role.INVESTOR and not BusinessInvestorRelation.objects.filter(
            tenant_id=tenant_id,
            partner_id=partner_id,
            status=BusinessInvestorRelation.Status.ACTIVE,
        ).exists():
            raise ValueError('Investor is not related to this business.')


def _validate_agreement_formula(partners: list[dict], mudaraba_ratio: Decimal) -> None:
    operator_count = sum(1 for partner in partners if partner.get('role') == AgreementPartner.Role.OPERATOR)
    if operator_count != 1:
        raise ValueError('Contract must include exactly one OPERATOR partner.')

    total_planned = sum(
        (Decimal(str(partner.get('planned_capital_share', '0'))) for partner in partners),
        ZERO,
    )
    if total_planned <= 0:
        raise ValueError('Total planned capital must be positive.')

    partners_meta = []
    for partner in partners:
        capital_share = Decimal(str(partner.get('planned_capital_share', '0'))) / total_planned
        partners_meta.append({
            'partner_id': partner['partner_id'],
            'role': partner['role'],
            'capital_share': ratio(capital_share),
        })

    expected = profit_shares_from_capital(partners_meta, mudaraba_ratio)
    for partner in partners:
        partner_id = int(partner['partner_id'])
        provided = ratio(partner.get('profit_share', '0'))
        if abs(expected[partner_id] - provided) > Decimal('0.0001'):
            raise ValueError(
                'Partner profit_share does not match planned capital shares and mudaraba_ratio.'
            )


def _agreement_partner_available(
    *,
    agreement: InvestmentAgreement,
    partner_id: int,
    currency: str,
) -> Decimal:
    currency = str(currency or 'UZS').upper()
    available = ZERO
    for contribution in agreement.contributions.filter(partner_id=partner_id, currency=currency):
        available += Decimal(str(contribution.amount))
    for withdrawal in agreement.withdrawals.filter(partner_id=partner_id, currency=currency):
        available -= Decimal(str(withdrawal.amount))
    for allocation in agreement.allocations.filter(partner_id=partner_id, currency=currency):
        amount = Decimal(str(allocation.amount))
        if allocation.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
            available -= amount
        else:
            available += amount
    return money(available)


def _validate_terms_payload_supplier(procurement, terms_payload) -> None:
    if terms_payload is None:
        return

    from .policies import allowed_settlements_for_funding

    settlement_type = (terms_payload.get('type') or '').upper()
    allowed_settlements = allowed_settlements_for_funding(procurement.funding_source)
    if settlement_type and settlement_type not in allowed_settlements:
        raise ValueError(f'{procurement.funding_source} does not allow {settlement_type} terms in MVP.')
    if settlement_type and settlement_type != ProcurementTerms.Type.PREPAID and procurement.supplier_id is None:
        raise ValueError(
            f'Supplier is required for {settlement_type} terms; supplier_id is None on procurement #{procurement.pk}.'
        )


def _terms_status_for_amounts(total_amount_due: Decimal, paid_amount: Decimal):
    total = money(total_amount_due or 0)
    paid = money(paid_amount or 0)
    if paid >= total and total > 0:
        return ProcurementTerms.Status.FULLY_PAID
    if paid > 0:
        return ProcurementTerms.Status.PARTIALLY_PAID
    return ProcurementTerms.Status.OPEN


def _normalize_terms_values(terms_payload: dict, *, existing=None, procurement=None) -> dict:
    """
    Normalize terms payload. Lenient to partial updates:
      - If `type` missing, takes from existing.
      - If `total_amount_due` missing, derives from procurement.items (Σ qty × price × fx)
        — single source of truth, UI doesn't need to recompute.
      - Other fields (currency, fx, deadline, notes) fall back to existing then defaults.
    """
    settlement_type = (
        terms_payload.get('type')
        or (existing.type if existing else None)
        or ''
    ).upper()
    if not settlement_type:
        raise ValueError('terms.type is required.')

    # Source-of-truth for total: items × prices (NO fx_rate — fx is for UZS
    # reporting only, not for obligation amounts).  For DRAFT terms (the OPEN
    # edit window) we always re-derive — terms.total_amount_due is a
    # denormalized cache.  Explicit payload override still wins (amendment
    # flows).  All items MUST share one currency; that currency becomes
    # currency_of_obligation.
    if 'total_amount_due' in terms_payload:
        total_amount_due = money(terms_payload['total_amount_due'])
        # currency_of_obligation resolved below from payload/existing
        _items_currency = None
    elif procurement is not None and (
        existing is None
        or existing.lifecycle_state != ProcurementTerms.LifecycleState.ACTIVE
    ):
        active_items = [
            i for i in procurement.items.all()
            if i.lifecycle_state not in ('CANCELLED', 'RECEIVED')
        ]
        cost_map = procurement_cost_by_currency(active_items, [])
        if len(cost_map) > 1:
            raise ValueError(
                'Все товары прихода должны быть в одной валюте. '
                f'Найдено: {", ".join(sorted(cost_map))}.'
            )
        _items_currency = next(iter(cost_map)) if cost_map else None
        total_amount_due = money(next(iter(cost_map.values())) if cost_map else Decimal('0'))
    elif existing is not None:
        total_amount_due = money(existing.total_amount_due)
        _items_currency = None
    else:
        raise ValueError('terms.total_amount_due is required (no existing terms and no procurement context).')

    _payload_cob = terms_payload.get('currency_of_obligation')
    _existing_cob = existing.currency_of_obligation if existing else None
    if _items_currency:
        # Items unambiguously set the currency. Payload may confirm but not override.
        if _payload_cob and str(_payload_cob).upper() != _items_currency:
            raise ValueError(
                f'currency_of_obligation "{_payload_cob}" does not match items currency "{_items_currency}".'
            )
        currency_of_obligation = _items_currency
    else:
        currency_of_obligation = _payload_cob or _existing_cob or 'UZS'
    fx_rate_at_obligation = (
        terms_payload.get('fx_rate_at_obligation')
        if 'fx_rate_at_obligation' in terms_payload
        else (existing.fx_rate_at_obligation if existing else 1)
    )
    deadline_date = (
        terms_payload.get('deadline_date')
        if 'deadline_date' in terms_payload
        else (existing.deadline_date if existing else None)
    )
    consignment_agreement_id = (
        terms_payload.get('consignment_agreement_id')
        if 'consignment_agreement_id' in terms_payload
        else (existing.consignment_agreement_id if existing else None)
    )
    notes = (
        terms_payload.get('notes')
        if 'notes' in terms_payload
        else (existing.notes if existing else '')
    )

    # Preserve existing status/lifecycle when terms already exist (partial
    # UI updates). For brand-new terms — always start as OPEN/DRAFT regardless
    # of timing type. Status/lifecycle transitions happen explicitly on the
    # first Payment / ReceiveBatch event (see pay_workspace_costs and
    # receive_workspace_batch which call terms.activate()).
    #
    # Previous version eagerly set PREPAID → FULLY_PAID/ACTIVE on creation,
    # but that broke UI flow: user picks PREPAID first, then can't change
    # timing because ACTIVE terms reject field mutations via ImmutableMixin.
    if existing is not None:
        initial_status = existing.status
        initial_lifecycle = existing.lifecycle_state
    else:
        initial_status = ProcurementTerms.Status.OPEN
        initial_lifecycle = ProcurementTerms.LifecycleState.DRAFT

    return {
        'type': settlement_type,
        'currency_of_obligation': str(currency_of_obligation).upper(),
        'fx_rate_at_obligation': Decimal(str(fx_rate_at_obligation or 1)),
        'total_amount_due': total_amount_due,
        'status': initial_status,
        'lifecycle_state': initial_lifecycle,
        'deadline_date': deadline_date,
        'consignment_agreement_id': consignment_agreement_id,
        'notes': str(notes or ''),
    }


def _replace_payment_schedule(tenant_id, terms, schedule_payload):
    from apps.suppliers.models import PaymentSchedule

    if terms.schedule_entries.exclude(status=PaymentSchedule.Status.PENDING).exists():
        raise ValueError('Cannot replace payment schedule after schedule payments started.')
    terms.schedule_entries.all().delete()
    return _create_payment_schedule(tenant_id, terms, schedule_payload)


def _create_payment_schedule(tenant_id, terms, schedule_payload):
    from apps.suppliers.models import PaymentSchedule

    created = []
    for index, entry in enumerate(schedule_payload or [], start=1):
        created.append(PaymentSchedule.objects.create(
            tenant_id=tenant_id,
            procurement_terms=terms,
            sequence_number=entry.get('sequence_number', index),
            due_date=entry['due_date'],
            amount=Decimal(str(entry['amount'])),
            currency=str(entry.get('currency') or terms.currency_of_obligation).upper(),
        ))
    return created


def _coerce_date(value):
    if not value:
        return None
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
        return value
    parsed = parse_date(str(value))
    if parsed is None:
        raise ValueError('Invalid date value.')
    return parsed


def _next_due_date(first_due_date, interval: str, offset: int, interval_days: int = 0):
    if offset == 0:
        return first_due_date
    if interval == 'WEEKLY':
        return first_due_date + timedelta(days=7 * offset)
    if interval == 'CUSTOM':
        return first_due_date + timedelta(days=interval_days * offset)

    month_index = first_due_date.month - 1 + offset
    year = first_due_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(first_due_date.day, monthrange(year, month)[1])
    return first_due_date.replace(year=year, month=month, day=day)
