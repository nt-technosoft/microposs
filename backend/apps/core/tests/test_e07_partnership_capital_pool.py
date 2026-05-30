from decimal import Decimal

from django.test import TestCase

from apps.finance.models import JournalEntry, Payment
from apps.partnerships.models import Procurement, ProcurementReceiveBatchCapitalAllocation
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


class PartnershipCapitalPoolTests(TestCase):
    def test_partial_receives_keep_independent_68_32_and_72_28_snapshots(self):
        ctx = build_tenant()
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
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('136'),
                        'profit_share': Decimal('0.34'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('64'),
                        'profit_share': Decimal('0.66'),
                    },
                ],
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [
                {
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
                {
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ]}},
        )
        for partner_id, amount in (
            (ctx['investor'].id, Decimal('140')),
            (ctx['operator'].id, Decimal('60')),
        ):
            dispatch_workspace_action(
                tenant_id=ctx['business'].id,
                procurement=procurement,
                action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': {
                    'partner_id': partner_id,
                    'amount': amount,
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'cash_account_id': ctx['cash_account'].id,
                }},
            )
        # E11: external contributions fund the agreement's capital pool, not the
        # operating cash register. Operating cash is untouched; the pool holds 200.
        ctx['cash_account'].refresh_from_db()
        self.assertEqual(ctx['cash_account'].balance, Decimal('0.00'))
        agreement = procurement.agreement
        agreement.capital_account.refresh_from_db()
        self.assertEqual(agreement.capital_account.balance, Decimal('200.00'))
        self.assertEqual(
            Payment.objects.filter(target_type=Payment.TargetType.CAPITAL_CONTRIBUTION).count(),
            2,
        )
        self.assertEqual(
            JournalEntry.objects.filter(operation_type='capital_contribution').count(),
            2,
        )
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {'allocations': [
                {'partner_id': ctx['investor'].id, 'amount': Decimal('140'), 'currency': 'UZS'},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('60'), 'currency': 'UZS'},
            ]}},
        )

        first_item, second_item = list(procurement.items.order_by('id'))
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': ctx['storage'].id,
                'item_ids': [first_item.id],
                'capital_allocations': [
                    {'partner_id': ctx['investor'].id, 'amount': Decimal('68')},
                    {'partner_id': ctx['operator'].id, 'amount': Decimal('32')},
                ],
            }},
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': ctx['storage'].id,
                'item_ids': [second_item.id],
                'capital_allocations': [
                    {'partner_id': ctx['investor'].id, 'amount': Decimal('72')},
                    {'partner_id': ctx['operator'].id, 'amount': Decimal('28')},
                ],
            }},
        )

        first_lot = first_item.lots.get()
        second_lot = second_item.lots.get()
        first_investor = next(
            row for row in first_lot.contract_snapshot['partners']
            if row['partner_id'] == ctx['investor'].id
        )
        second_investor = next(
            row for row in second_lot.contract_snapshot['partners']
            if row['partner_id'] == ctx['investor'].id
        )

        self.assertEqual(Decimal(first_investor['capital_share']), Decimal('0.680000'))
        self.assertEqual(Decimal(second_investor['capital_share']), Decimal('0.720000'))
        self.assertEqual(Decimal(first_investor['profit_share']), Decimal('0.340000'))
        self.assertEqual(Decimal(second_investor['profit_share']), Decimal('0.360000'))

        batch_rows = list(
            ProcurementReceiveBatchCapitalAllocation.objects
            .filter(batch__procurement=procurement, partner=ctx['investor'])
            .order_by('batch_id')
        )
        self.assertEqual([row.amount_contract_currency for row in batch_rows], [
            Decimal('68.00'),
            Decimal('72.00'),
        ])
