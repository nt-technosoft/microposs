from decimal import Decimal

from django.test import TestCase

from apps.partnerships.advances import settle_partner_capital
from apps.partnerships.models import (
    AgreementAllocation,
    CapitalAdvanceSettlement,
    InvestmentAgreement,
    PartnerJournalLineTag,
    PartnerLedgerEntry,
    Procurement,
    PartnerPositionReadModel,
    ProcurementVentureSettlement,
)
from apps.partnerships.read_models import (
    canonical_partner_position_rows,
    legacy_partner_position_rows,
    rebuild_agreement_positions,
)
from apps.partnerships.venture import (
    create_venture_settlement,
    repay_partner_venture_debt,
)
from apps.partnerships.workspace import apply_items_amendment, create_workspace, dispatch_workspace_action
from apps.partnerships.workspace_support import add_agreement_withdrawal
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement
from .test_e14_capital_advances import _build_funded, _receive
from .test_e14_settlement import _build_shortfall_with_profit


def _read_model_snapshot(agreement):
    rows = PartnerPositionReadModel.objects.filter(agreement=agreement).order_by(
        'procurement_id',
        'partner_id',
        'currency',
    )
    return {row.identity_key: row.money_payload for row in rows}


def _canonical_snapshot(agreement):
    return {
        key: payload
        for key, payload in canonical_partner_position_rows(agreement).items()
    }


def _legacy_snapshot(agreement):
    return {
        key: payload
        for key, payload in legacy_partner_position_rows(agreement).items()
    }


def _assert_current(test, agreement):
    canonical = _canonical_snapshot(agreement)
    test.assertEqual(canonical, _legacy_snapshot(agreement))
    test.assertEqual(_read_model_snapshot(agreement), canonical)


class PartnerPositionReadModelHookTests(TestCase):
    def test_hooks_keep_rows_current_across_money_operations(self):
        ctx = build_tenant()
        procurement = _build_funded(
            ctx,
            planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        _assert_current(self, agreement)

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': ctx['investor'].id,
                'amount': Decimal('4'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }},
        )
        _assert_current(self, agreement)

        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        _assert_current(self, agreement)

        session = open_session(ctx)
        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('15'),
            }],
            payments=[{
                'amount': Decimal('75'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )
        _assert_current(self, agreement)

        create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        _assert_current(self, agreement)

    def test_withdrawal_repay_and_profit_to_capital_hooks(self):
        ctx = build_tenant()
        procurement = _build_shortfall_with_profit(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        _assert_current(self, agreement)

        settle_partner_capital(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('4.00'),
            source=CapitalAdvanceSettlement.Source.FROM_PROFIT,
            from_account_id=ctx['cash_account'].id,
        )
        _assert_current(self, agreement)

        add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            procurement_id=procurement.id,
            from_account_id=ctx['cash_account'].id,
            partner_id=ctx['investor'].id,
            amount=Decimal('66.00'),
            currency='UZS',
        )
        _assert_current(self, agreement)

    def test_dividend_and_repay_hooks(self):
        repay_ctx = build_tenant()
        repayment_procurement, _ = seed_received_procurement(repay_ctx)
        repayment_agreement = InvestmentAgreement.objects.get(pk=repayment_procurement.agreement_id)
        session = open_session(repay_ctx)
        create_sale(
            tenant_id=repay_ctx['business'].id,
            pos_session_id=session.id,
            location_id=repay_ctx['store'].id,
            sold_by_id=repay_ctx['cashier'].id,
            customer_id=repay_ctx['customer'].id,
            lines=[{
                'product_variant_id': repay_ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': repay_ctx['cash_account'].id,
            }],
        )
        create_venture_settlement(
            tenant_id=repay_ctx['business'].id,
            procurement_id=repayment_procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        from apps.partnerships.agreement_services import pay_dividend

        pay_dividend(
            partner_id=repay_ctx['investor'].id,
            procurement_id=repayment_procurement.id,
            amount=Decimal('216000.00'),
            currency='UZS',
            from_account_id=repay_ctx['cash_account'].id,
            tenant_id=repay_ctx['business'].id,
        )
        _assert_current(self, repayment_agreement)

        create_sale(
            tenant_id=repay_ctx['business'].id,
            pos_session_id=session.id,
            location_id=repay_ctx['store'].id,
            sold_by_id=repay_ctx['cashier'].id,
            customer_id=repay_ctx['customer'].id,
            lines=[{
                'product_variant_id': repay_ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('100000.00'),
            }],
            payments=[{
                'amount': Decimal('500000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': repay_ctx['cash_account'].id,
            }],
        )
        _assert_current(self, repayment_agreement)

        debt_row = _canonical_snapshot(repayment_agreement)[
            (repayment_procurement.id, repay_ctx['investor'].id, 'UZS')
        ]
        repay_partner_venture_debt(
            tenant_id=repay_ctx['business'].id,
            procurement_id=repayment_procurement.id,
            partner_id=repay_ctx['investor'].id,
            amount=debt_row['negative_position_uzs'],
            currency='UZS',
            paid_to_account_id=repay_ctx['cash_account'].id,
        )
        _assert_current(self, repayment_agreement)

    def test_overpayment_refund_hook_and_tag_equivalence(self):
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
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RESOLVE_OVERPAYMENT',
            payload={'payload': {'amount': Decimal('20'), 'currency': 'UZS'}},
        )

        allocation = AgreementAllocation.objects.get(
            tenant=ctx['business'],
            procurement=procurement,
            direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
            amount=Decimal('20.00'),
        )
        self.assertTrue(PartnerLedgerEntry.objects.filter(
            ledger__procurement=procurement,
            ledger__partner=ctx['investor'],
            entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
            source_ref=f'allocation:{allocation.id}',
        ).exists())
        self.assertTrue(PartnerJournalLineTag.objects.filter(
            agreement=procurement.agreement,
            procurement=procurement,
            partner=ctx['investor'],
            flow=PartnerJournalLineTag.Flow.OVERPAYMENT_REFUND,
        ).exists())

        key = (procurement.id, ctx['investor'].id, 'UZS')
        self.assertEqual(_canonical_snapshot(procurement.agreement)[key]['capital_returned_uzs'], Decimal('20.00'))
        self.assertEqual(_legacy_snapshot(procurement.agreement)[key]['capital_returned_uzs'], Decimal('20.00'))
        _assert_current(self, procurement.agreement)


class PartnerPositionReadModelReplayTests(TestCase):
    def test_full_rebuild_matches_incremental_rows(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        incremental = _read_model_snapshot(agreement)

        PartnerPositionReadModel.all_objects.filter(agreement=agreement).delete()
        self.assertEqual(PartnerPositionReadModel.objects.filter(agreement=agreement).count(), 0)

        rebuild_agreement_positions(agreement)
        self.assertEqual(_read_model_snapshot(agreement), incremental)
