"""
E09 Wave A — Slice 4: Generic Attachment model tests.

Tests cover:
  * attach_file to Procurement works
  * attach_file to ProcurementReceiveBatch works
  * list_attachments filters by attachable correctly
  * soft_delete (detach) makes attachment invisible in list
"""

import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.attachments.models import Attachment
from apps.attachments.services import attach_file, list_attachments, detach
from apps.finance.models import CashAccount
from apps.partnerships.models import Procurement
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
)

from ._helpers import build_tenant


def _make_file(name='invoice.pdf', content=b'PDF_DATA'):
    return SimpleUploadedFile(name, content, content_type='application/pdf')


def _build_received_procurement(ctx):
    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_SETTLEMENT',
        payload={'payload': {'type': 'PREPAID', 'total_amount_due': '5000',
                             'currency_of_obligation': 'UZS'}},
    )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {'items': [{
            'product_variant_id': ctx['variant'].id,
            'quantity': 5, 'unit_purchase_price': '1000',
            'currency': 'UZS', 'fx_rate': '1',
        }]}},
    )
    CashAccount.objects.filter(pk=ctx['cash_account'].pk).update(balance=Decimal('20000'))
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='PAY_COSTS',
        payload={'payload': {'cash_account_id': ctx['cash_account'].id,
                             'amount': '5000', 'currency': 'UZS'}},
    )
    proc.refresh_from_db()
    batch = receive_workspace_batch(
        tenant_id=ctx['business'].id,
        procurement=proc,
        payload={'warehouse_id': ctx['store'].id},
    )
    return proc, batch


class AttachFileToProcurementTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_attach_file_to_procurement(self):
        proc, _ = _build_received_procurement(self.ctx)
        attachment = attach_file(
            tenant_id=self.ctx['business'].id,
            attachable=proc,
            file=_make_file('invoice.pdf'),
            kind=Attachment.Kind.INVOICE,
            caption='Supplier invoice',
        )
        self.assertIsNotNone(attachment.pk)
        self.assertEqual(attachment.kind, Attachment.Kind.INVOICE)
        self.assertEqual(attachment.content_type.model, 'procurement')
        self.assertEqual(attachment.object_id, proc.pk)

    def test_attach_file_to_receive_batch(self):
        _, batch = _build_received_procurement(self.ctx)
        attachment = attach_file(
            tenant_id=self.ctx['business'].id,
            attachable=batch,
            file=_make_file('photo.jpg'),
            kind=Attachment.Kind.RECEIPT_PHOTO,
        )
        self.assertIsNotNone(attachment.pk)
        self.assertEqual(attachment.content_type.model, 'procurementreceivebatch')
        self.assertEqual(attachment.object_id, batch.pk)

    def test_list_attachments_filtered_by_attachable(self):
        proc, batch = _build_received_procurement(self.ctx)
        attach_file(tenant_id=self.ctx['business'].id, attachable=proc,
                    file=_make_file('invoice.pdf'), kind=Attachment.Kind.INVOICE)
        attach_file(tenant_id=self.ctx['business'].id, attachable=batch,
                    file=_make_file('photo.jpg'), kind=Attachment.Kind.RECEIPT_PHOTO)

        proc_attachments = list(list_attachments(attachable=proc))
        batch_attachments = list(list_attachments(attachable=batch))

        self.assertEqual(len(proc_attachments), 1)
        self.assertEqual(proc_attachments[0].kind, Attachment.Kind.INVOICE)
        self.assertEqual(len(batch_attachments), 1)
        self.assertEqual(batch_attachments[0].kind, Attachment.Kind.RECEIPT_PHOTO)

    def test_detach_soft_delete(self):
        proc, _ = _build_received_procurement(self.ctx)
        attachment = attach_file(
            tenant_id=self.ctx['business'].id,
            attachable=proc,
            file=_make_file('doc.pdf'),
        )
        self.assertEqual(list_attachments(attachable=proc).count(), 1)

        detach(attachment_id=attachment.pk, tenant_id=self.ctx['business'].id)

        # Soft-deleted: not visible in queryset, but file record still exists
        self.assertEqual(list_attachments(attachable=proc).count(), 0)
        attachment.refresh_from_db()
        self.assertIsNotNone(attachment.deleted_at)
