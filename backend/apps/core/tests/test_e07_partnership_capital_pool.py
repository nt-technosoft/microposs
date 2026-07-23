from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashEntry, JournalEntry, Payment
from apps.partnerships.models import AgreementAllocation, Procurement, ProcurementReceiveBatchCapitalAllocation
from apps.partnerships.workspace import apply_items_amendment, build_workspace_payload, create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


class PartnershipCapitalPoolTests(TestCase):
    def test_resolve_partnership_overpayment_returns_money_to_agreement_pool(self):
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
                'planned_budget': Decimal('150'),
                'currency': 'UZS',
                'partners': [
                    {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                     'planned_capital_share': Decimal('100'), 'profit_share': Decimal('0.333333')},
                    {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                     'planned_capital_share': Decimal('50'), 'profit_share': Decimal('0.666667')},
                ],
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }]}},
        )
        for partner_id, amount in (
            (ctx['investor'].id, Decimal('100')),
            (ctx['operator'].id, Decimal('50')),
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
                }},
            )

        item = procurement.items.get()
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {'allocations': [
                {'partner_id': ctx['investor'].id, 'amount': Decimal('80'), 'currency': 'UZS'},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('20'), 'currency': 'UZS'},
            ], 'item_ids': [item.id]}},
        )
        procurement.agreement.capital_account.refresh_from_db()
        self.assertEqual(procurement.agreement.capital_account.balance, Decimal('50.00'))

        apply_items_amendment(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            new_items_payload=[{
                'id': item.id,
                'product_variant_id': item.product_variant_id,
                'quantity': Decimal('8'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
            reason='supplier removed two units after prepayment',
        )
        self.assertEqual(
            build_workspace_payload(procurement)['documents']['payment_status']['state'],
            'overpaid',
        )

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RESOLVE_OVERPAYMENT',
            payload={'payload': {'amount': Decimal('20'), 'currency': 'UZS'}},
        )

        procurement.agreement.capital_account.refresh_from_db()
        self.assertEqual(procurement.agreement.capital_account.balance, Decimal('70.00'))
        self.assertTrue(AgreementAllocation.objects.filter(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
            amount=Decimal('20.00'),
        ).exists())
        self.assertTrue(CashEntry.objects.filter(
            tenant_id=ctx['business'].id,
            account=procurement.agreement.capital_account,
            direction=CashEntry.Direction.IN,
            amount=Decimal('20.00'),
        ).exists())
        payment_status = build_workspace_payload(procurement)['documents']['payment_status']
        self.assertEqual(payment_status['state'], 'paid_full')
        self.assertEqual(payment_status['paid_by_currency']['UZS'], '80.00')

    def test_paid_unreceived_partnership_procurement_can_allocate_correction_delta(self):
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
                'planned_budget': Decimal('150'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('100'),
                        'profit_share': Decimal('0.333333'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('50'),
                        'profit_share': Decimal('0.666667'),
                    },
                ],
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }]}},
        )
        for partner_id, amount in (
            (ctx['investor'].id, Decimal('120')),
            (ctx['operator'].id, Decimal('30')),
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
                }},
            )

        item = procurement.items.get()
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {'allocations': [
                {'partner_id': ctx['investor'].id, 'amount': Decimal('80'), 'currency': 'UZS'},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('20'), 'currency': 'UZS'},
            ], 'item_ids': [item.id]}},
        )

        apply_items_amendment(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            new_items_payload=[{
                'id': item.id,
                'product_variant_id': item.product_variant_id,
                'quantity': Decimal('12'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
            reason='Supplier added two units before receipt.',
        )
        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['documents']['payment_status']['state'], 'underpaid')
        self.assertEqual(payload['documents']['payment_status']['remaining_by_currency']['UZS'], '20.00')

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {'allocations': [
                {'partner_id': ctx['investor'].id, 'amount': Decimal('20'), 'currency': 'UZS'},
            ]}},
        )
        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['documents']['payment_status']['state'], 'paid_full')
        self.assertEqual(payload['documents']['payment_status']['paid_by_currency']['UZS'], '120.00')

    def _two_item_partnership_procurement(self, *, reconciliation_mode='FACTUAL'):
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
                'reconciliation_mode': reconciliation_mode,
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
        first_item, second_item = list(procurement.items.order_by('id'))
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {'allocations': [
                {'partner_id': ctx['investor'].id, 'amount': Decimal('140'), 'currency': 'UZS'},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('60'), 'currency': 'UZS'},
            ], 'item_ids': [first_item.id, second_item.id]}},
        )
        self.assertEqual(
            set(procurement.items.values_list('lifecycle_state', flat=True)),
            {procurement.items.model.LifecycleState.READY_FOR_RECEIVE},
        )
        return ctx, procurement

    def test_factual_partial_receive_is_blocked_to_avoid_share_profile_tranches(self):
        ctx, procurement = self._two_item_partnership_procurement(reconciliation_mode='FACTUAL')
        first_item, _second_item = list(procurement.items.order_by('id'))

        with self.assertRaisesMessage(
            ValueError,
            'FACTUAL reconciliation requires full receive because shares are derived from final factual funding.',
        ):
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

    def test_factual_full_receive_is_allowed_and_uses_one_final_snapshot(self):
        ctx, procurement = self._two_item_partnership_procurement(reconciliation_mode='FACTUAL')
        first_item, second_item = list(procurement.items.order_by('id'))

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': ctx['storage'].id,
                'item_ids': [first_item.id, second_item.id],
                'capital_allocations': [
                    {'partner_id': ctx['investor'].id, 'amount': Decimal('140')},
                    {'partner_id': ctx['operator'].id, 'amount': Decimal('60')},
                ],
            }},
        )

        first_lot = first_item.lots.get()
        second_lot = second_item.lots.get()
        for lot in (first_lot, second_lot):
            investor = next(
                row for row in lot.contract_snapshot['partners']
                if row['partner_id'] == ctx['investor'].id
            )
            self.assertEqual(Decimal(investor['capital_share']), Decimal('0.700000'))
            self.assertEqual(Decimal(investor['profit_share']), Decimal('0.350000'))

    def test_agreed_partial_receive_stays_allowed_and_pins_contract_shares(self):
        ctx, procurement = self._two_item_partnership_procurement(reconciliation_mode='AGREED')

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
        self.assertEqual(Decimal(second_investor['capital_share']), Decimal('0.680000'))
        self.assertEqual(Decimal(first_investor['profit_share']), Decimal('0.340000'))
        self.assertEqual(Decimal(second_investor['profit_share']), Decimal('0.340000'))

        batch_rows = list(
            ProcurementReceiveBatchCapitalAllocation.objects
            .filter(batch__procurement=procurement, partner=ctx['investor'])
            .order_by('batch_id')
        )
        self.assertEqual([row.amount_contract_currency for row in batch_rows], [
            Decimal('68.00'),
            Decimal('72.00'),
        ])
