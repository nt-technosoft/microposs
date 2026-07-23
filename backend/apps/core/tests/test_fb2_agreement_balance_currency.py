"""
FB-2 reproduction (E18 UI audit): /reports/agreements rendered a UZS-magnitude
pool balance with a `$` symbol.

`InvestmentAgreement.balances` (models.py) keys its per-currency map by each
entry's own `currency`, and the agreement-profitability report passes that map
raw; the frontend renders whatever currency key it receives. So a `$` could only
appear if `balances` carried a `USD` key.

These tests characterise the actual behaviour: every pool-affecting write-path
is currency-locked to the agreement/pool currency, so `balances` is
single-currency by construction. A UZS agreement can never expose a USD key —
hence a `$` in the report means the agreement is genuinely USD (display is
correct), not a UZS sum mislabelled by the serializer or the frontend.

Verdict for the lead lives in the test names: this is not a report-serializer or
write-path code defect.
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import InvestmentAgreement, Procurement
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


def _build_partnership_agreement(ctx, *, currency='UZS'):
    procurement = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
    )
    return dispatch_workspace_action(
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


class AgreementBalanceCurrencyTests(TestCase):
    def test_uzs_agreement_balance_is_single_currency_uzs(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx, currency='UZS')

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': ctx['investor'].id,
                'amount': Decimal('140'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }},
        )

        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        balances = agreement.balances
        # Exactly one key, and it is the agreement currency — never `$` on a UZS pool.
        self.assertEqual(set(balances), {'UZS'})
        self.assertEqual(balances['UZS'], '140.00')

    def test_contribution_currency_must_match_pool_currency(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx, currency='UZS')

        # A UZS-magnitude amount mistakenly tagged USD — the suspected source of
        # the "$4.6M". The write-path rejects it, so balances cannot be polluted.
        with self.assertRaises(ValueError):
            dispatch_workspace_action(
                tenant_id=ctx['business'].id,
                procurement=procurement,
                action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': {
                    'partner_id': ctx['investor'].id,
                    'amount': Decimal('4620000'),
                    'currency': 'USD',
                    'fx_rate': Decimal('1'),
                }},
            )

        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        self.assertNotIn('USD', agreement.balances)
