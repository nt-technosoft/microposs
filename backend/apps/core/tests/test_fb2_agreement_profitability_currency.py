"""
FB-2 (re-opened): agreement-profitability report mixes currencies.

For a USD agreement with a UZS FROM_PROCEEDS recovery (proceeds are realised in
functional UZS), the per-partner balance/remaining was emitted as a raw UZS
magnitude under the USD label — `_to_agreement_currency` divided by the entry's
own fx_rate, which for a UZS entry is 1, so no conversion happened.

A UZS recovery of 4 620 000 (functional UZS) in a USD agreement at 12 500 UZS/USD
must read ~$369.60, never "$4 620 000". Every per-partner amount must flow through
functional UZS and the report fx model.

Не трогаем InvestmentAgreement.balances — он корректен (FROM_PROCEEDS не входит в пул).
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.fx_rates import upsert_exchange_rate
from apps.finance.services import get_agreement_profitability_detail
from apps.partnerships.models import (
    AgreementWithdrawal,
    InvestmentAgreement,
    Procurement,
)
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


def _build_partnership_agreement(ctx, *, currency='UZS'):
    procurement = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
    )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='CREATE_INVESTMENT_AGREEMENT',
        payload={'payload': {
            'mudaraba_ratio': Decimal('0.5'),
            'planned_budget': Decimal('200'),
            'currency': currency,
            'partners': [
                {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                 'planned_capital_share': Decimal('136'), 'profit_share': Decimal('0.34')},
                {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                 'planned_capital_share': Decimal('64'), 'profit_share': Decimal('0.66')},
            ],
        }},
    )
    return InvestmentAgreement.objects.get(pk=procurement.agreement_id)


class AgreementProfitabilityCurrencyTests(TestCase):
    def test_uzs_recovery_in_usd_agreement_is_converted_not_raw(self):
        ctx = build_tenant()
        upsert_exchange_rate(
            tenant_id=ctx['business'].id,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12500'),
            source='MANUAL',
            is_manual=True,
        )
        agreement = _build_partnership_agreement(ctx, currency='USD')

        # A proceeds recovery realised in functional UZS, attributed to the investor.
        AgreementWithdrawal.objects.create(
            tenant_id=ctx['business'].id,
            agreement=agreement,
            partner_id=ctx['investor'].id,
            amount=Decimal('4620000'),
            currency='UZS',
            fx_rate=Decimal('1'),
            return_kind=AgreementWithdrawal.ReturnKind.FROM_PROCEEDS,
            date=timezone.now(),
        )

        report = get_agreement_profitability_detail(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
        )
        investor_row = next(
            row for row in report['partners']
            if row['partner_id'] == ctx['investor'].id
        )

        # Label is the agreement currency; the value must be converted to it,
        # not the raw UZS magnitude.
        self.assertEqual(investor_row['agreement_currency'], 'USD')
        self.assertEqual(Decimal(investor_row['agreement_withdrawn']), Decimal('369.60'))
        self.assertEqual(Decimal(investor_row['agreement_available']), Decimal('-369.60'))
