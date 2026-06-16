from decimal import Decimal

from django.test import TestCase

from apps.finance.models import JournalEntry
from apps.partnerships.advances import partner_capital_positions
from apps.partnerships.agreement_services import agreement_pool_reconciliation_residual
from apps.partnerships.models import AgreementWithdrawal, PartnerJournalLineTag
from apps.partnerships.workspace import dispatch_workspace_action
from apps.partnerships.workspace_support import add_agreement_withdrawal
from apps.sales.models import PosSession, SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement
from .test_e11_capital_pool_reconciliation import _build_partnership_agreement


def _fund(ctx, procurement, investor_amt, operator_amt):
    for partner_id, amount in (
        (ctx['investor'].id, investor_amt),
        (ctx['operator'].id, operator_amt),
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


def _sell(ctx, procurement):
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
            'quantity': 5,
            'unit_price': Decimal('240000.00'),
        }],
        payments=[{
            'amount': Decimal('1200000.00'),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
            'method': SalePayment.Method.CASH,
            'account_id': ctx['cash_account'].id,
        }],
    )


def _tags_for_entry(entry):
    return PartnerJournalLineTag.objects.filter(journal_line__journal_entry=entry)


class AgreementWithdrawalReturnKindTests(TestCase):
    def test_pool_withdrawal_sets_from_pool_and_readers_use_return_kind(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx, currency='UZS')
        _fund(ctx, procurement, Decimal('140'), Decimal('60'))
        agreement = procurement.agreement

        withdrawal = add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('40.00'),
            currency='UZS',
        )
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.return_kind, AgreementWithdrawal.ReturnKind.FROM_POOL)

        entry = JournalEntry.objects.get(
            tenant=ctx['business'],
            operation_type='capital_return',
            operation_id=withdrawal.id,
        )
        self.assertTrue(_tags_for_entry(entry).filter(
            partner=ctx['investor'],
            agreement=agreement,
            pocket=PartnerJournalLineTag.Pocket.CAPITAL,
        ).exists())

        agreement.refresh_from_db()
        self.assertEqual(agreement.balances['UZS'], '160.00')
        self.assertEqual(agreement_pool_reconciliation_residual(agreement), Decimal('0.00'))
        self.assertEqual(
            partner_capital_positions(agreement)[ctx['investor'].id]['paid_in'],
            Decimal('100.00'),
        )

        AgreementWithdrawal.objects.filter(pk=withdrawal.pk).update(
            return_kind=AgreementWithdrawal.ReturnKind.FROM_PROCEEDS,
        )
        agreement.refresh_from_db()
        self.assertEqual(agreement.balances['UZS'], '200.00')
        self.assertEqual(agreement_pool_reconciliation_residual(agreement), Decimal('-40.00'))
        self.assertEqual(
            partner_capital_positions(agreement)[ctx['investor'].id]['paid_in'],
            Decimal('140.00'),
        )

    def test_recovered_capital_withdrawal_sets_from_proceeds_and_proceeds_tag(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        _sell(ctx, procurement)

        withdrawal = add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=procurement.agreement_id,
            procurement_id=procurement.id,
            from_account_id=ctx['cash_account'].id,
            partner_id=ctx['investor'].id,
            amount=Decimal('100000.00'),
            currency='UZS',
        )
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.return_kind, AgreementWithdrawal.ReturnKind.FROM_PROCEEDS)

        entry = JournalEntry.objects.get(
            tenant=ctx['business'],
            operation_type='capital_return',
            operation_id=withdrawal.id,
        )
        self.assertTrue(_tags_for_entry(entry).filter(
            partner=ctx['investor'],
            agreement=procurement.agreement,
            procurement=procurement,
            pocket=PartnerJournalLineTag.Pocket.PROCEEDS,
        ).exists())
