"""
Excel-to-domain alignment importer — retired.

This module was a 1300-line historical importer built on the legacy
Receipt / InvestorContract / Sale.PaymentMethod stack. Under the vacuum model
(Phase D) those structures are gone: inventory now comes in through
`partnerships.open_procurement` → `receive_procurement`, and sales speak the
new `create_sale(location_id, payments=[…])` signature.

Re-enabling Excel import is scoped as a separate project after Phase D.
Until then, the public surface below exists so that historical management
commands (`excel_align_import`, `excel_align_pilot`) still import cleanly and
fail at invocation with a clear, actionable error instead of an opaque
AttributeError mid-run.
"""

from __future__ import annotations


_RETIRED_MESSAGE = (
    'excel_alignment is retired under the vacuum model (Phase D). '
    'Its pipeline targets removed models (Receipt, InvestorContract, '
    'Sale.PaymentMethod) and must be rewritten on top of '
    'partnerships.open_procurement / receive_procurement and the new '
    'sales.create_sale signature before it can be used again.'
)


class ExcelAlignmentImporter:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(_RETIRED_MESSAGE)


def load_snapshot(*args, **kwargs):
    raise NotImplementedError(_RETIRED_MESSAGE)


def extract_sheets(*args, **kwargs):
    raise NotImplementedError(_RETIRED_MESSAGE)


def normalize_row_keys(*args, **kwargs):
    raise NotImplementedError(_RETIRED_MESSAGE)


def parse_datetime(*args, **kwargs):
    raise NotImplementedError(_RETIRED_MESSAGE)


def pick(*args, **kwargs):
    raise NotImplementedError(_RETIRED_MESSAGE)
