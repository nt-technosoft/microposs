from decimal import Decimal
from pathlib import Path

from django.test import TestCase

from apps.finance.models import JournalEntry, Payment
from apps.partnerships.advances import settle_partner_capital
from apps.partnerships.agreement_services import pay_dividend
from apps.partnerships.journal_tags import backfill_partner_journal_line_tags
from apps.partnerships.read_models import canonical_partner_position_rows, legacy_partner_position_rows
from apps.partnerships.models import (
    AgreementContribution,
    AgreementAllocation,
    CapitalAdvanceSettlement,
    PartnerJournalLineTag,
    PartnerLedgerEntry,
    Procurement,
    ProcurementPartnerVentureDebtRepayment,
    ProcurementVentureSettlement,
)
from apps.partnerships.venture import create_venture_settlement, repay_partner_venture_debt
from apps.partnerships.workspace import apply_items_amendment, create_workspace, dispatch_workspace_action
from apps.partnerships.workspace_support import add_agreement_withdrawal
from apps.sales.models import PosSession, SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement
from .test_e14_settlement import _build_shortfall_with_profit


def _sell(ctx, procurement, *, quantity=5, unit_price='240000.00'):
    session = PosSession.objects.filter(
        tenant=ctx['business'],
        location=ctx['store'],
        status=PosSession.SessionStatus.OPEN,
    ).first() or open_session(ctx)
    return create_sale(
        tenant_id=ctx['business'].id,
        pos_session_id=session.id,
        location_id=ctx['store'].id,
        sold_by_id=ctx['cashier'].id,
        customer_id=ctx['customer'].id,
        lines=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': quantity,
            'unit_price': Decimal(unit_price),
        }],
        payments=[{
            'amount': Decimal(unit_price) * Decimal(quantity),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
            'method': SalePayment.Method.CASH,
            'account_id': ctx['cash_account'].id,
        }],
    )


def _tags_for_entry(entry):
    return PartnerJournalLineTag.objects.filter(journal_line__journal_entry=entry)


class PartnerJournalLineTagForwardTests(TestCase):
    def test_contribution_writes_capital_tags(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        agreement = procurement.agreement

        contribution = AgreementContribution.objects.get(
            agreement=agreement,
            partner=ctx['investor'],
        )
        contribution_payment = Payment.objects.get(
            tenant=ctx['business'],
            target_type=Payment.TargetType.CAPITAL_CONTRIBUTION,
            target_id=contribution.id,
        )
        contribution_tags = _tags_for_entry(contribution_payment.journal_entry).filter(
            partner=ctx['investor'],
            agreement=agreement,
            procurement__isnull=True,
            pocket=PartnerJournalLineTag.Pocket.CAPITAL,
            flow=PartnerJournalLineTag.Flow.CONTRIBUTION,
        )
        self.assertTrue(contribution_tags.exists())
        self.assertTrue(all(tag.journal_line_id for tag in contribution_tags))

    def test_withdrawal_and_profit_to_capital_write_tags(self):
        ctx = build_tenant()
        procurement = _build_shortfall_with_profit(ctx)
        agreement = procurement.agreement

        settle_partner_capital(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('4.00'),
            source=CapitalAdvanceSettlement.Source.FROM_PROFIT,
            from_account_id=ctx['cash_account'].id,
        )
        profit_entry = JournalEntry.objects.get(
            tenant=ctx['business'],
            operation_type='advance_settle',
            operation_id=agreement.id,
        )
        self.assertEqual(
            set(_tags_for_entry(profit_entry).values_list('pocket', flat=True)),
            {PartnerJournalLineTag.Pocket.CAPITAL, PartnerJournalLineTag.Pocket.DISTRIBUTION},
        )
        self.assertEqual(
            set(_tags_for_entry(profit_entry).values_list('flow', flat=True)),
            {PartnerJournalLineTag.Flow.PROFIT_TO_CAPITAL},
        )

        withdrawal = add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            procurement_id=procurement.id,
            from_account_id=ctx['cash_account'].id,
            partner_id=ctx['investor'].id,
            amount=Decimal('66.00'),
            currency='UZS',
        )
        withdrawal_entry = JournalEntry.objects.get(
            tenant=ctx['business'],
            operation_type='capital_return',
            operation_id=withdrawal.id,
        )
        self.assertTrue(_tags_for_entry(withdrawal_entry).filter(
            partner=ctx['investor'],
            agreement=agreement,
            procurement=procurement,
            pocket=PartnerJournalLineTag.Pocket.PROCEEDS,
            flow=PartnerJournalLineTag.Flow.CAPITAL_RETURN,
        ).exists())

    def test_dividend_and_repay_write_tags(self):
        dividend_ctx = build_tenant()
        dividend_procurement, _ = seed_received_procurement(dividend_ctx)
        _sell(dividend_ctx, dividend_procurement)
        create_venture_settlement(
            tenant_id=dividend_ctx['business'].id,
            procurement_id=dividend_procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        dividend = pay_dividend(
            partner_id=dividend_ctx['investor'].id,
            procurement_id=dividend_procurement.id,
            amount=Decimal('216000.00'),
            currency='UZS',
            from_account_id=dividend_ctx['cash_account'].id,
            tenant_id=dividend_ctx['business'].id,
        )
        dividend_entry = JournalEntry.objects.get(
            tenant=dividend_ctx['business'],
            operation_type='profit_distrib',
            operation_id=dividend.id,
        )
        self.assertTrue(_tags_for_entry(dividend_entry).filter(
            partner=dividend_ctx['investor'],
            agreement=dividend_procurement.agreement,
            procurement=dividend_procurement,
            pocket=PartnerJournalLineTag.Pocket.DISTRIBUTION,
            flow=PartnerJournalLineTag.Flow.DIVIDEND,
        ).exists())

        _sell(dividend_ctx, dividend_procurement, unit_price='100000.00')
        debt = PartnerJournalLineTag.objects.filter(
            agreement=dividend_procurement.agreement,
            procurement=dividend_procurement,
        ).count()
        self.assertGreater(debt, 0)
        from apps.partnerships.venture import procurement_venture_positions

        debt_amount = procurement_venture_positions(
            procurement=dividend_procurement,
        )[dividend_ctx['investor'].id]['negative_position_uzs']
        repayment = repay_partner_venture_debt(
            tenant_id=dividend_ctx['business'].id,
            procurement_id=dividend_procurement.id,
            partner_id=dividend_ctx['investor'].id,
            amount=debt_amount,
            currency='UZS',
            paid_to_account_id=dividend_ctx['cash_account'].id,
        )
        repay_entry = JournalEntry.objects.get(
            tenant=dividend_ctx['business'],
            operation_type='venture_debt_repay',
            operation_id=repayment.id,
        )
        self.assertTrue(_tags_for_entry(repay_entry).filter(
            partner=dividend_ctx['investor'],
            agreement=dividend_procurement.agreement,
            procurement=dividend_procurement,
        ).exists())
        self.assertTrue(_tags_for_entry(repay_entry).filter(
            flow__in={
                PartnerJournalLineTag.Flow.DEBT_REPAID_LIABILITY,
                PartnerJournalLineTag.Flow.DEBT_REPAID_CAPITAL,
                PartnerJournalLineTag.Flow.DEBT_REPAID_DIVIDEND,
            },
        ).exists())

    def test_overpayment_refund_writes_capital_tag_without_deploy_tags(self):
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
        deploy_payment = Payment.objects.get(
            tenant=ctx['business'],
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.id,
            source_type=Payment.SourceType.CAPITAL_POOL,
            reversed_payment__isnull=True,
        )
        self.assertEqual(_tags_for_entry(deploy_payment.journal_entry).count(), 0)

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
        self.assertEqual(allocation.partner_id, ctx['investor'].id)
        self.assertTrue(PartnerLedgerEntry.objects.filter(
            ledger__procurement=procurement,
            ledger__partner=ctx['investor'],
            entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
            source_ref=f'allocation:{allocation.id}',
        ).exists())

        refund_payment = Payment.objects.get(
            tenant=ctx['business'],
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.id,
            source_type=Payment.SourceType.CAPITAL_POOL,
            reversed_payment__isnull=False,
        )
        self.assertTrue(_tags_for_entry(refund_payment.journal_entry).filter(
            partner=ctx['investor'],
            agreement=procurement.agreement,
            procurement=procurement,
            pocket=PartnerJournalLineTag.Pocket.CAPITAL,
            flow=PartnerJournalLineTag.Flow.OVERPAYMENT_REFUND,
        ).exists())
        tag_rows = canonical_partner_position_rows(procurement.agreement)
        legacy_rows = legacy_partner_position_rows(procurement.agreement)
        key = (procurement.id, ctx['investor'].id, 'UZS')
        self.assertEqual(tag_rows[key], legacy_rows[key])
        self.assertEqual(tag_rows[key]['capital_returned_uzs'], Decimal('20.00'))


class PartnerJournalLineTagBackfillTests(TestCase):
    def test_backfill_restores_unambiguous_tags_idempotently(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        _sell(ctx, procurement)
        create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        dividend = pay_dividend(
            partner_id=ctx['investor'].id,
            procurement_id=procurement.id,
            amount=Decimal('216000.00'),
            currency='UZS',
            from_account_id=ctx['cash_account'].id,
            tenant_id=ctx['business'].id,
        )

        PartnerJournalLineTag.objects.all().hard_delete()
        self.assertEqual(PartnerJournalLineTag.objects.count(), 0)

        created = backfill_partner_journal_line_tags(tenant_id=ctx['business'].id)
        self.assertGreater(created, 0)
        self.assertEqual(backfill_partner_journal_line_tags(tenant_id=ctx['business'].id), 0)

        dividend_entry = JournalEntry.objects.get(
            tenant=ctx['business'],
            operation_type='profit_distrib',
            operation_id=dividend.id,
        )
        self.assertTrue(_tags_for_entry(dividend_entry).filter(
            partner=ctx['investor'],
            agreement=procurement.agreement,
            procurement=procurement,
            pocket=PartnerJournalLineTag.Pocket.DISTRIBUTION,
        ).exists())


class FinanceBoundaryTests(TestCase):
    def test_tag_layer_does_not_extend_finance_imports(self):
        finance_root = Path(__file__).resolve().parents[2] / 'finance'
        offenders = []
        for path in finance_root.rglob('*.py'):
            text = path.read_text()
            if 'PartnerJournalLineTag' in text or 'journal_tags' in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [])
