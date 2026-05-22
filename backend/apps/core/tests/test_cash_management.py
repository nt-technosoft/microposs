"""
Cash management service tests — OwnerDrawing and CashTransfer.
"""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount, Account, CashEntry, JournalEntry, OwnerDrawing, CashTransfer
from apps.finance.services import record_owner_contribution, record_owner_drawing, record_cash_transfer

from ._helpers import build_tenant


class OwnerDrawingTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.account = self.ctx['cash_account']

        record_owner_contribution(
            tenant_id=self.business.id,
            amount=Decimal('100000.00'),
            currency='UZS',
            to_account_id=self.account.id,
        )
        self.account.refresh_from_db()

    def test_drawing_decreases_balance_and_writes_journal(self):
        balance_before = self.account.balance
        drawing = record_owner_drawing(
            tenant_id=self.business.id,
            from_account_id=self.account.id,
            amount=Decimal('40000.00'),
            currency='UZS',
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, balance_before - Decimal('40000.00'))

        journal = JournalEntry.objects.filter(
            operation_type='owner_drawing', operation_id=drawing.pk,
        )
        self.assertEqual(journal.count(), 1)
        lines = journal.first().lines.all()
        dr_line = lines.get(debit=Decimal('40000.00'))
        cr_line = lines.get(credit=Decimal('40000.00'))
        self.assertEqual(dr_line.account.code, '3001')
        self.assertEqual(cr_line.account.code, '1000')

    def test_drawing_creates_cash_entry_out(self):
        record_owner_drawing(
            tenant_id=self.business.id,
            from_account_id=self.account.id,
            amount=Decimal('25000.00'),
        )
        entry = CashEntry.objects.filter(
            account=self.account,
            direction=CashEntry.Direction.OUT,
            source_ref_type='owner_drawing',
        ).last()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount, Decimal('25000.00'))

    def test_drawing_exceeding_balance_raises_and_does_not_change_balance(self):
        balance_before = self.account.balance
        with self.assertRaises(ValueError, msg='Insufficient balance'):
            record_owner_drawing(
                tenant_id=self.business.id,
                from_account_id=self.account.id,
                amount=balance_before + Decimal('1.00'),
            )
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, balance_before)

    def test_drawing_idempotency(self):
        rid = uuid.uuid4()
        d1 = record_owner_drawing(
            tenant_id=self.business.id,
            from_account_id=self.account.id,
            amount=Decimal('10000.00'),
            client_request_id=rid,
        )
        d2 = record_owner_drawing(
            tenant_id=self.business.id,
            from_account_id=self.account.id,
            amount=Decimal('10000.00'),
            client_request_id=rid,
        )
        self.assertEqual(d1.pk, d2.pk)
        self.assertEqual(OwnerDrawing.objects.filter(client_request_id=rid).count(), 1)


class CashTransferTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.account_a = self.ctx['cash_account']
        self.account_b = self.ctx['card_account']

        record_owner_contribution(
            tenant_id=self.business.id,
            amount=Decimal('200000.00'),
            currency='UZS',
            to_account_id=self.account_a.id,
        )
        self.account_a.refresh_from_db()
        self.account_b.refresh_from_db()

    def test_transfer_updates_both_balances(self):
        balance_a_before = self.account_a.balance
        balance_b_before = self.account_b.balance

        record_cash_transfer(
            tenant_id=self.business.id,
            from_account_id=self.account_a.id,
            to_account_id=self.account_b.id,
            amount=Decimal('80000.00'),
        )

        self.account_a.refresh_from_db()
        self.account_b.refresh_from_db()
        self.assertEqual(self.account_a.balance, balance_a_before - Decimal('80000.00'))
        self.assertEqual(self.account_b.balance, balance_b_before + Decimal('80000.00'))

    def test_transfer_writes_balanced_journal_entry(self):
        transfer = record_cash_transfer(
            tenant_id=self.business.id,
            from_account_id=self.account_a.id,
            to_account_id=self.account_b.id,
            amount=Decimal('50000.00'),
        )

        journal = JournalEntry.objects.filter(
            operation_type='cash_transfer', operation_id=transfer.pk,
        )
        self.assertEqual(journal.count(), 1)
        entry = journal.first()
        lines = entry.lines.all()
        total_debit = sum(l.debit for l in lines)
        total_credit = sum(l.credit for l in lines)
        self.assertEqual(total_debit, total_credit)
        self.assertEqual(total_debit, Decimal('50000.00'))

        to_code = self.account_b.linked_account.code
        from_code = self.account_a.linked_account.code
        dr_line = lines.get(account__code=to_code)
        cr_line = lines.get(account__code=from_code)
        self.assertEqual(dr_line.debit, Decimal('50000.00'))
        self.assertEqual(cr_line.credit, Decimal('50000.00'))

    def test_transfer_creates_two_cash_entries(self):
        transfer = record_cash_transfer(
            tenant_id=self.business.id,
            from_account_id=self.account_a.id,
            to_account_id=self.account_b.id,
            amount=Decimal('30000.00'),
        )
        entries = CashEntry.objects.filter(source_ref_type='cash_transfer', source_ref_id=transfer.pk)
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries.filter(direction=CashEntry.Direction.OUT).count(), 1)
        self.assertEqual(entries.filter(direction=CashEntry.Direction.IN).count(), 1)

    def test_transfer_different_currency_raises(self):
        usd_account = CashAccount.objects.create(
            tenant=self.business,
            name='USD Cash',
            currency='USD',
            kind=CashAccount.Kind.CASH,
            linked_account=Account.objects.get(tenant=self.business, code='1000'),
        )
        with self.assertRaises(ValueError, msg='same currency'):
            record_cash_transfer(
                tenant_id=self.business.id,
                from_account_id=self.account_a.id,
                to_account_id=usd_account.id,
                amount=Decimal('10000.00'),
            )

    def test_transfer_insufficient_balance_raises(self):
        balance_a = self.account_a.balance
        with self.assertRaises(ValueError, msg='Insufficient'):
            record_cash_transfer(
                tenant_id=self.business.id,
                from_account_id=self.account_a.id,
                to_account_id=self.account_b.id,
                amount=balance_a + Decimal('1.00'),
            )
        self.account_a.refresh_from_db()
        self.assertEqual(self.account_a.balance, balance_a)

    def test_transfer_idempotency(self):
        rid = uuid.uuid4()
        t1 = record_cash_transfer(
            tenant_id=self.business.id,
            from_account_id=self.account_a.id,
            to_account_id=self.account_b.id,
            amount=Decimal('20000.00'),
            client_request_id=rid,
        )
        t2 = record_cash_transfer(
            tenant_id=self.business.id,
            from_account_id=self.account_a.id,
            to_account_id=self.account_b.id,
            amount=Decimal('20000.00'),
            client_request_id=rid,
        )
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(CashTransfer.objects.filter(client_request_id=rid).count(), 1)
