"""
Excel-to-domain alignment helpers for Iteration 1 import pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductCharacteristic
from apps.catalog.services import create_product_with_variants
from apps.core.models import Business, ExcelImportBatch, ExcelImportRow
from apps.core.services import publish_event
from apps.customers.models import Customer
from apps.customers.services import record_customer_payment
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.services import create_journal_entry, record_expense
from apps.inventory.models import Location, Lot, Receipt, ReceiptLine
from apps.inventory.services import confirm_receipt, transfer_lot
from apps.sales.models import PosSession, Sale
from apps.sales.services import create_sale, open_pos_session
from apps.suppliers.models import Supplier
from apps.suppliers.services import record_supplier_payment


PRIMARY_SHEETS_ORDER = [
    'SOTIB OLISH',
    'STOCK TRANSFER',
    'SOTUV',
    'TUSHUM',
    'XARAJAT',
    'PUL AYRIBOSHLASH',
]


@dataclass(slots=True)
class ImportContext:
    tenant: Business
    batch: ExcelImportBatch
    strict: bool
    seller_user_id: int
    default_store_location_id: int
    default_warehouse_location_id: int


def load_snapshot(path: str) -> dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def extract_sheets(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """
    Accepts either:
    1) canonical shape: {"sheets": {"SOTUV": [{...}]}}
    2) connector shape from get_spreadsheet_cells: {"sheets": [{properties, data}]}
    """
    sheets_obj = snapshot.get('sheets')
    if isinstance(sheets_obj, dict):
        return {
            name: _canonical_sheet_rows(payload)
            for name, payload in sheets_obj.items()
        }
    if isinstance(sheets_obj, list):
        return _connector_sheet_rows(sheets_obj)
    raise ValueError("Unsupported snapshot format: 'sheets' not found")


def _canonical_sheet_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows: list[dict[str, Any]] = []
        for idx, row in enumerate(payload, start=2):
            if isinstance(row, dict):
                normalized = dict(row)
                normalized.setdefault('_row_id', str(idx))
                rows.append(normalized)
        return rows

    if isinstance(payload, dict):
        headers = payload.get('headers')
        rows = payload.get('rows')
        if isinstance(headers, list) and isinstance(rows, list):
            result: list[dict[str, Any]] = []
            for idx, row in enumerate(rows, start=2):
                if not isinstance(row, list):
                    continue
                mapped: dict[str, Any] = {'_row_id': str(idx)}
                for col_idx, header in enumerate(headers):
                    mapped[str(header)] = row[col_idx] if col_idx < len(row) else ''
                result.append(mapped)
            return result
    return []


def _connector_sheet_rows(sheets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for sheet in sheets:
        title = (
            sheet.get('properties', {}).get('title')
            or 'UNKNOWN'
        )
        row_data = []
        for data_block in sheet.get('data', []):
            row_data.extend(data_block.get('rowData', []))
        if not row_data:
            result[title] = []
            continue

        header_cells = row_data[0].get('values', [])
        headers = [
            _normalize_header(_extract_cell_value(cell), idx)
            for idx, cell in enumerate(header_cells)
        ]

        rows: list[dict[str, Any]] = []
        for ridx, row in enumerate(row_data[1:], start=2):
            values = row.get('values', [])
            mapped: dict[str, Any] = {'_row_id': str(ridx)}
            nonempty = False
            for cidx, header in enumerate(headers):
                raw = values[cidx] if cidx < len(values) else {}
                value = _extract_cell_value(raw)
                mapped[header] = value
                if str(value).strip():
                    nonempty = True
            if nonempty:
                rows.append(mapped)
        result[title] = rows
    return result


def _normalize_header(value: Any, idx: int) -> str:
    text = str(value or '').strip()
    if not text:
        return f'__COL_{idx + 1}'
    return re.sub(r'\s+', ' ', text).strip()


def _extract_cell_value(cell: dict[str, Any]) -> Any:
    if not isinstance(cell, dict):
        return ''
    if 'formattedValue' in cell:
        return cell.get('formattedValue', '')
    user = cell.get('userEnteredValue') or {}
    if isinstance(user, dict):
        for key in ('stringValue', 'numberValue', 'boolValue'):
            if key in user:
                return user[key]
        if 'formulaValue' in user:
            return user['formulaValue']
    return ''


def normalize_row_keys(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key == '_row_id':
            normalized[key] = value
            continue
        up = re.sub(r'\s+', ' ', str(key or '').replace('\n', ' ').strip()).upper()
        normalized[up] = value
    return normalized


def row_fingerprint(sheet: str, row: dict[str, Any]) -> str:
    payload = {
        'sheet': sheet,
        'row': {k: row[k] for k in sorted(row.keys()) if k != '_row_id'},
    }
    dump = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(dump.encode('utf-8')).hexdigest()


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        nk = re.sub(r'\s+', ' ', key.replace('\n', ' ').strip()).upper()
        if nk in row:
            return row[nk]
    return ''


def parse_decimal(value: Any, *, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip()
    if not text:
        return default
    text = text.replace('ʼ', '').replace("'", '')
    text = text.replace('so‘m', '').replace('so\'m', '').replace('som', '')
    text = text.replace('$', '').replace('%', '')
    text = text.replace(' ', '').replace(',', '')
    text = re.sub(r'[^0-9.\-]', '', text)
    if text in ('', '-', '.', '-.'):
        return default
    try:
        return Decimal(text)
    except InvalidOperation:
        return default


def normalize_currency(value: Any) -> str:
    text = str(value or '').strip().upper()
    if text in {'USD', '$'}:
        return 'USD'
    if text in {'SOM', 'SO\'M', 'SO‘M', 'UZS'}:
        return 'UZS'
    return 'UZS'


def to_uzs(*, amount: Decimal, currency: str, fx_rate: Decimal | None) -> Decimal:
    if currency == 'USD':
        if not fx_rate or fx_rate <= 0:
            raise ValueError("USD amount requires fx_rate > 0")
        return (amount * fx_rate).quantize(Decimal('0.01'))
    return amount.quantize(Decimal('0.01'))


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    elif isinstance(value, (int, float)):
        dt = datetime(1899, 12, 30) + timedelta(days=float(value))
    else:
        text = str(value or '').strip()
        if not text:
            raise ValueError('Empty datetime value')
        formats = (
            '%d-%b-%y',
            '%d-%b-%Y',
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S%z',
        )
        parsed = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f'Unsupported date format: {text}')
        dt = parsed

    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def is_posted(row: dict[str, Any]) -> bool:
    value = pick(row, 'POSTED')
    if value is None:
        return True
    if str(value).strip() == '':
        return True
    text = str(value).strip().upper()
    return text in {'✅', 'TRUE', 'POSTED', '1', 'YES'}


class ExcelAlignmentImporter:
    def __init__(
        self,
        *,
        tenant_id: int,
        mode: str,
        source_ref: str,
        strict: bool = False,
        seller_user_id: int | None = None,
        notes: str = '',
    ) -> None:
        tenant = Business.objects.get(pk=tenant_id)
        batch = ExcelImportBatch.objects.create(
            tenant=tenant,
            mode=mode,
            source_kind='json',
            source_ref=source_ref,
            notes=notes,
            status=ExcelImportBatch.Status.RUNNING,
        )
        store = self._resolve_location(tenant.id, 'DOKON', location_type=Location.LocationType.STORE)
        wh = self._resolve_location(tenant.id, 'ASOSIY', location_type=Location.LocationType.WAREHOUSE)
        self.ctx = ImportContext(
            tenant=tenant,
            batch=batch,
            strict=strict,
            seller_user_id=seller_user_id or self._resolve_seller_user_id(tenant),
            default_store_location_id=store.id,
            default_warehouse_location_id=wh.id,
        )

    def run(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            sheets = extract_sheets(snapshot)
            staged_rows = self._stage_rows(sheets)

            mode = self.ctx.batch.mode
            if mode == ExcelImportBatch.Mode.DRY_RUN:
                summary = self._dry_validate(staged_rows)
            elif mode == ExcelImportBatch.Mode.LOAD_MASTER:
                setup_chart_of_accounts(self.ctx.tenant.id)
                summary = self._load_master(staged_rows.get('MALUMOTLAR', []))
            elif mode == ExcelImportBatch.Mode.LOAD_TRANSACTIONS:
                setup_chart_of_accounts(self.ctx.tenant.id)
                master_summary = self._load_master(staged_rows.get('MALUMOTLAR', []))
                opening_summary = self._apply_opening_balances(snapshot.get('opening_balances') or {})
                tx_summary = self._load_transactions(staged_rows)
                summary = {
                    'master': master_summary,
                    'opening_balances': opening_summary,
                    'transactions': tx_summary,
                }
            elif mode == ExcelImportBatch.Mode.RECONCILE:
                summary = self._reconcile(snapshot.get('expected') or {})
            else:
                raise ValueError(f'Unsupported mode: {mode}')

            self.ctx.batch.status = ExcelImportBatch.Status.COMPLETED
            self.ctx.batch.finished_at = timezone.now()
            self.ctx.batch.totals = summary
            self.ctx.batch.save(update_fields=['status', 'finished_at', 'totals', 'updated_at'])
            return summary
        except Exception as exc:  # noqa: BLE001 - command-level failure reporting
            self.ctx.batch.status = ExcelImportBatch.Status.FAILED
            self.ctx.batch.finished_at = timezone.now()
            self.ctx.batch.totals = {'error': str(exc)}
            self.ctx.batch.save(update_fields=['status', 'finished_at', 'totals', 'updated_at'])
            raise

    def _stage_rows(self, sheets: dict[str, list[dict[str, Any]]]) -> dict[str, list[tuple[ExcelImportRow, dict[str, Any]]]]:
        staged: dict[str, list[tuple[ExcelImportRow, dict[str, Any]]]] = {}
        for sheet_name, rows in sheets.items():
            staged[sheet_name] = []
            for idx, raw in enumerate(rows, start=2):
                normalized = normalize_row_keys(raw)
                if _is_empty_row(normalized):
                    continue

                source_row_id = str(raw.get('_row_id') or idx)
                fingerprint = row_fingerprint(sheet_name, normalized)
                row_obj, _ = ExcelImportRow.objects.update_or_create(
                    tenant=self.ctx.tenant,
                    batch=self.ctx.batch,
                    source_sheet=sheet_name,
                    source_row_id=source_row_id,
                    defaults={
                        'row_fingerprint': fingerprint,
                        'raw_payload': raw,
                        'normalized_payload': normalized,
                        'parse_errors': [],
                        'failure_category': '',
                        'status': ExcelImportRow.Status.STAGED,
                        'target_model': '',
                        'target_id': None,
                        'operation_currency': 'UZS',
                        'operation_amount': None,
                        'fx_rate_snapshot': None,
                        'functional_amount': None,
                    },
                )
                staged[sheet_name].append((row_obj, normalized))
        return staged

    def _dry_validate(self, staged_rows: dict[str, list[tuple[ExcelImportRow, dict[str, Any]]]]) -> dict[str, Any]:
        checked = 0
        failed = 0
        for _, rows in staged_rows.items():
            for row_obj, row in rows:
                checked += 1
                try:
                    self._basic_sheet_validation(row_obj.source_sheet, row)
                    self._mark_row(row_obj, status=ExcelImportRow.Status.PARSED)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    self._fail_row(
                        row_obj,
                        str(exc),
                        category=ExcelImportRow.FailureCategory.PARSE,
                    )
                    if self.ctx.strict:
                        raise
        return {'checked_rows': checked, 'failed_rows': failed}

    def _basic_sheet_validation(self, sheet_name: str, row: dict[str, Any]) -> None:
        if sheet_name in {'SOTIB OLISH', 'TUSHUM', 'XARAJAT', 'STOCK TRANSFER', 'PUL AYRIBOSHLASH'}:
            parse_datetime(pick(row, 'SANA'))
        if sheet_name == 'SOTUV':
            parse_datetime(pick(row, 'SOTUV SANASI', 'SANA'))

    def _load_master(self, rows: list[tuple[ExcelImportRow, dict[str, Any]]]) -> dict[str, int]:
        stats = {
            'rows': 0,
            'applied': 0,
            'skipped': 0,
            'failed': 0,
            'customers': 0,
            'suppliers': 0,
            'products': 0,
            'locations': 0,
        }
        for row_obj, row in rows:
            stats['rows'] += 1
            try:
                if self._was_applied_before(row_obj):
                    stats['skipped'] += 1
                    self._mark_row(row_obj, status=ExcelImportRow.Status.SKIPPED)
                    continue

                customer_name = str(pick(row, 'MIJOZLAR')).strip()
                supplier_name = str(pick(row, 'TRADE CREDITOR', 'CREDITOR')).strip()
                product_name = str(pick(row, 'MAHSULOTLAR', 'MAHSULOT')).strip()
                location_name = str(pick(row, 'OMBOR')).strip()

                if customer_name:
                    _, created = Customer.objects.get_or_create(
                        tenant=self.ctx.tenant,
                        name=customer_name,
                        defaults={'is_active': True},
                    )
                    stats['customers'] += int(created)

                if supplier_name:
                    _, created = Supplier.objects.get_or_create(
                        tenant=self.ctx.tenant,
                        name=supplier_name,
                        defaults={'is_active': True},
                    )
                    stats['suppliers'] += int(created)

                if location_name:
                    _, created = Location.objects.get_or_create(
                        tenant=self.ctx.tenant,
                        name=location_name,
                        defaults={
                            'is_active': True,
                            'location_type': (
                                Location.LocationType.STORE
                                if _is_store_name(location_name)
                                else Location.LocationType.WAREHOUSE
                            ),
                        },
                    )
                    stats['locations'] += int(created)

                if product_name:
                    _, created = self._resolve_product_variant(
                        product_name=product_name,
                        base_price=Decimal('0'),
                    )
                    stats['products'] += int(created)

                    photo_url = _extract_photo_url_from_row(row)
                    if photo_url:
                        product = Product.objects.filter(
                            tenant=self.ctx.tenant,
                            name__iexact=product_name,
                        ).first()
                        if product:
                            ProductCharacteristic.objects.update_or_create(
                                tenant=self.ctx.tenant,
                                product=product,
                                name='source_photo_url',
                                defaults={'value': photo_url},
                            )

                stats['applied'] += 1
                self._mark_row(
                    row_obj,
                    status=ExcelImportRow.Status.APPLIED,
                    target_model='core.master-row',
                )
            except Exception as exc:  # noqa: BLE001
                stats['failed'] += 1
                self._fail_row(
                    row_obj,
                    str(exc),
                    category=ExcelImportRow.FailureCategory.MAPPING,
                )
                if self.ctx.strict:
                    raise
        return stats

    def _apply_opening_balances(self, opening: dict[str, Any]) -> dict[str, int]:
        stats = {
            'cash_entries': 0,
            'customers': 0,
            'suppliers': 0,
            'inventory_receipts': 0,
        }
        if not opening:
            return stats

        for item in opening.get('cash', []):
            amount = parse_decimal(item.get('amount'), default=Decimal('0')) or Decimal('0')
            if amount <= 0:
                continue
            account_code = str(item.get('account_code') or '1000')
            create_journal_entry(
                tenant_id=self.ctx.tenant.id,
                operation_type='payment',
                operation_id=int(self.ctx.batch.id) * 1000 + stats['cash_entries'] + 1,
                lines=[
                    {
                        'account_code': account_code,
                        'debit': amount,
                        'credit': Decimal('0'),
                        'description': 'Opening cash balance',
                    },
                    {
                        'account_code': '3000',
                        'debit': Decimal('0'),
                        'credit': amount,
                        'description': 'Opening balance equity',
                    },
                ],
                description='Opening cash import',
                date=parse_datetime(item.get('date') or timezone.now()),
            )
            stats['cash_entries'] += 1

        for item in opening.get('customers', []):
            name = str(item.get('name', '')).strip()
            if not name:
                continue
            amount = parse_decimal(item.get('amount'), default=Decimal('0')) or Decimal('0')
            customer, _ = Customer.objects.get_or_create(
                tenant=self.ctx.tenant,
                name=name,
                defaults={'is_active': True},
            )
            customer.outstanding_balance = amount
            customer.save(update_fields=['outstanding_balance', 'updated_at'])
            stats['customers'] += 1

        for item in opening.get('suppliers', []):
            name = str(item.get('name', '')).strip()
            if not name:
                continue
            amount = parse_decimal(item.get('amount'), default=Decimal('0')) or Decimal('0')
            supplier, _ = Supplier.objects.get_or_create(
                tenant=self.ctx.tenant,
                name=name,
                defaults={'is_active': True},
            )
            supplier.outstanding_balance = amount
            supplier.save(update_fields=['outstanding_balance', 'updated_at'])
            stats['suppliers'] += 1

        for item in opening.get('inventory', []):
            product_name = str(item.get('product_name', '')).strip()
            if not product_name:
                continue
            qty = int(parse_decimal(item.get('quantity'), default=Decimal('0')) or Decimal('0'))
            cost = parse_decimal(item.get('cost_per_unit'), default=Decimal('0')) or Decimal('0')
            if qty <= 0 or cost <= 0:
                continue
            location_name = str(item.get('location') or 'ASOSIY').strip()
            location = self._resolve_location(self.ctx.tenant.id, location_name)
            variant, _ = self._resolve_product_variant(product_name=product_name, base_price=cost)
            receipt = Receipt.objects.create(
                tenant=self.ctx.tenant,
                receipt_type=Receipt.ReceiptType.BUSINESS_OWNED,
                status=Receipt.ReceiptStatus.DRAFT,
                date=parse_datetime(item.get('date') or timezone.now()),
                destination=location,
                notes=f'Opening inventory import [{self.ctx.batch.id}]',
            )
            ReceiptLine.objects.create(
                tenant=self.ctx.tenant,
                receipt=receipt,
                product_variant=variant,
                quantity=qty,
                cost_per_unit=cost,
            )
            confirm_receipt(receipt)
            stats['inventory_receipts'] += 1
        return stats

    def _load_transactions(
        self,
        staged_rows: dict[str, list[tuple[ExcelImportRow, dict[str, Any]]]],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for sheet_name in PRIMARY_SHEETS_ORDER:
            rows = staged_rows.get(sheet_name, [])
            sheet_stats = {'rows': 0, 'applied': 0, 'skipped': 0, 'failed': 0}
            for row_obj, row in rows:
                sheet_stats['rows'] += 1
                try:
                    if self._was_applied_before(row_obj):
                        sheet_stats['skipped'] += 1
                        self._mark_row(row_obj, status=ExcelImportRow.Status.SKIPPED)
                        continue
                    if not is_posted(row):
                        sheet_stats['skipped'] += 1
                        self._mark_row(row_obj, status=ExcelImportRow.Status.SKIPPED)
                        continue

                    if sheet_name == 'SOTIB OLISH':
                        self._apply_purchase_row(row_obj, row)
                    elif sheet_name == 'STOCK TRANSFER':
                        self._apply_transfer_row(row_obj, row)
                    elif sheet_name == 'SOTUV':
                        self._apply_sale_row(row_obj, row)
                    elif sheet_name == 'TUSHUM':
                        self._apply_customer_payment_row(row_obj, row)
                    elif sheet_name == 'XARAJAT':
                        self._apply_expense_row(row_obj, row)
                    elif sheet_name == 'PUL AYRIBOSHLASH':
                        self._apply_exchange_row(row_obj, row)
                    else:
                        self._mark_row(row_obj, status=ExcelImportRow.Status.SKIPPED)
                        sheet_stats['skipped'] += 1
                        continue

                    sheet_stats['applied'] += 1
                except Exception as exc:  # noqa: BLE001
                    sheet_stats['failed'] += 1
                    self._fail_row(
                        row_obj,
                        str(exc),
                        category=_classify_failure_category(exc),
                    )
                    if self.ctx.strict:
                        raise
            summary[sheet_name] = sheet_stats
        return summary

    def _apply_purchase_row(self, row_obj: ExcelImportRow, row: dict[str, Any]) -> None:
        dt = parse_datetime(pick(row, 'SANA'))
        supplier_name = str(pick(row, 'ISM')).strip()
        product_name = str(pick(row, 'MAHSULOT')).strip()
        qty = int(parse_decimal(pick(row, 'SONI'), default=Decimal('0')) or Decimal('0'))
        unit_price = parse_decimal(pick(row, 'MAHSULOT NARXI'), default=Decimal('0')) or Decimal('0')
        currency = normalize_currency(pick(row, 'PUL BIRLIGI'))
        fx_rate = parse_decimal(pick(row, 'KURS'), default=Decimal('1')) or Decimal('1')
        if qty <= 0 or unit_price <= 0 or not product_name:
            raise ValueError('Invalid purchase row: product/qty/price are required')

        unit_price_uzs = to_uzs(amount=unit_price, currency=currency, fx_rate=fx_rate)
        location = self._resolve_location(self.ctx.tenant.id, 'ASOSIY')
        supplier_id = None
        receipt_type = Receipt.ReceiptType.BUSINESS_OWNED
        payable_terms = None
        term = str(pick(row, "TO'LOV MUDDATI")).strip().upper()

        if supplier_name:
            supplier = self._resolve_supplier(supplier_name)
            supplier_id = supplier.id
            receipt_type = Receipt.ReceiptType.SUPPLIER_PURCHASE
            payable_terms = {
                'type': 'paid' if term in {'NAQD', ''} else 'credit',
                'term': term or 'NAQD',
            }

        variant, _ = self._resolve_product_variant(
            product_name=product_name,
            base_price=unit_price_uzs,
        )
        with transaction.atomic():
            receipt = Receipt.objects.create(
                tenant=self.ctx.tenant,
                receipt_type=receipt_type,
                status=Receipt.ReceiptStatus.DRAFT,
                date=dt,
                destination=location,
                supplier_id=supplier_id,
                payable_terms=payable_terms,
                operation_currency=currency,
                operation_amount=(unit_price * qty),
                fx_rate_snapshot=fx_rate,
                functional_amount_uzs=(unit_price_uzs * qty),
                notes=f'Excel import {row_obj.source_sheet}:{row_obj.source_row_id}',
            )
            ReceiptLine.objects.create(
                tenant=self.ctx.tenant,
                receipt=receipt,
                product_variant=variant,
                quantity=qty,
                cost_per_unit=unit_price_uzs,
            )
            confirm_receipt(receipt)

        self._mark_row(
            row_obj,
            status=ExcelImportRow.Status.APPLIED,
            target_model='inventory.Receipt',
            target_id=receipt.id,
            operation_currency=currency,
            operation_amount=(unit_price * qty),
            fx_rate_snapshot=fx_rate,
            functional_amount=(unit_price_uzs * qty),
        )

    def _apply_transfer_row(self, row_obj: ExcelImportRow, row: dict[str, Any]) -> None:
        product_name = str(pick(row, 'MAHSULOT')).strip()
        qty_to_move = int(parse_decimal(pick(row, 'SONI'), default=Decimal('0')) or Decimal('0'))
        if qty_to_move <= 0 or not product_name:
            raise ValueError('Invalid transfer row: product/quantity required')

        from_location = self._resolve_location(self.ctx.tenant.id, str(pick(row, 'CHIQIM') or 'ASOSIY'))
        to_location = self._resolve_location(self.ctx.tenant.id, str(pick(row, 'KIRIM') or 'DOKON'))
        variant, _ = self._resolve_product_variant(product_name=product_name, base_price=Decimal('0'))
        lots = (
            Lot.objects
            .filter(
                tenant=self.ctx.tenant,
                product_variant=variant,
                location=from_location,
                is_active=True,
                quantity_remaining__gt=0,
            )
            .order_by('receipt__date', 'id')
        )
        remaining = qty_to_move
        moved_lot_id = None
        for lot in lots:
            if remaining <= 0:
                break
            step = min(remaining, lot.quantity_remaining)
            transferred = transfer_lot(
                lot=lot,
                to_location=to_location,
                quantity=step,
                tenant_id=self.ctx.tenant.id,
            )
            moved_lot_id = transferred.id
            remaining -= step
        if remaining > 0:
            raise ValueError(f'Not enough stock to transfer {qty_to_move} of {product_name}')

        self._mark_row(
            row_obj,
            status=ExcelImportRow.Status.APPLIED,
            target_model='inventory.Lot',
            target_id=moved_lot_id,
            operation_currency='UZS',
            operation_amount=None,
            fx_rate_snapshot=None,
            functional_amount=None,
        )

    def _apply_sale_row(self, row_obj: ExcelImportRow, row: dict[str, Any]) -> None:
        dt = parse_datetime(pick(row, 'SOTUV SANASI', 'SANA'))
        customer_name = str(pick(row, 'MIJOZ')).strip() or 'IN HOUSE'
        product_name = str(pick(row, 'MAHSULOT')).strip()
        qty = int(parse_decimal(pick(row, 'JAMI DONA'), default=Decimal('0')) or Decimal('0'))
        unit_price = parse_decimal(pick(row, 'SOTUV NARXI'), default=Decimal('0')) or Decimal('0')
        currency = normalize_currency(pick(row, 'VALYUTA'))
        fx_rate = parse_decimal(pick(row, 'KURS'), default=Decimal('1')) or Decimal('1')
        location_name = str(pick(row, 'OMBOR') or 'DOKON').strip()
        payment_hint = str(pick(row, "TO'LOV MUDDATI")).strip()
        if qty <= 0 or unit_price <= 0 or not product_name:
            raise ValueError('Invalid sale row: product/qty/price required')

        unit_price_uzs = to_uzs(amount=unit_price, currency=currency, fx_rate=fx_rate)
        total_operation_amount = unit_price * qty
        total_uzs = unit_price_uzs * qty
        _, _ = self._resolve_product_variant(product_name=product_name, base_price=unit_price_uzs)
        variant = (
            Product.objects
            .filter(tenant=self.ctx.tenant, name__iexact=product_name)
            .first()
            .variants.filter(is_active=True)
            .order_by('id')
            .first()
        )
        if variant is None:
            raise ValueError(f'Variant not found for product: {product_name}')

        location = self._resolve_location(self.ctx.tenant.id, location_name)
        session = self._ensure_open_session(location.id)
        payment_method = _map_sale_payment_method(payment_hint)
        customer_id = None
        if payment_method == Sale.PaymentMethod.CREDIT:
            customer_id = self._resolve_customer(customer_name).id
        elif customer_name and customer_name.upper() not in {'IN HOUSE', 'CUSTOMER'}:
            customer_id = self._resolve_customer(customer_name).id

        sale = create_sale(
            tenant_id=self.ctx.tenant.id,
            pos_session_id=session.id,
            sold_by_id=self.ctx.seller_user_id,
            payment_method=payment_method,
            customer_id=customer_id,
            lines=[{
                'product_variant_id': variant.id,
                'quantity': qty,
                'unit_price': str(unit_price_uzs),
            }],
            notes=f'Excel import {row_obj.source_sheet}:{row_obj.source_row_id}',
            operation_date=dt,
            operation_currency=currency,
            operation_amount=total_operation_amount,
            fx_rate_snapshot=fx_rate,
            functional_amount_uzs=total_uzs,
        )

        self._mark_row(
            row_obj,
            status=ExcelImportRow.Status.APPLIED,
            target_model='sales.Sale',
            target_id=sale.id,
            operation_currency=currency,
            operation_amount=total_operation_amount,
            fx_rate_snapshot=fx_rate,
            functional_amount=total_uzs,
        )

    def _apply_customer_payment_row(self, row_obj: ExcelImportRow, row: dict[str, Any]) -> None:
        dt = parse_datetime(pick(row, 'SANA'))
        customer_name = str(pick(row, 'MIJOZ')).strip()
        amount = parse_decimal(pick(row, 'MIQDOR'), default=Decimal('0')) or Decimal('0')
        currency = normalize_currency(pick(row, 'VALYUTA'))
        fx_rate = parse_decimal(pick(row, 'KURS'), default=Decimal('1')) or Decimal('1')
        payment_type = str(pick(row, "TO'LOV TURI")).strip()
        if not customer_name or amount <= 0:
            raise ValueError('Invalid payment row: customer and amount required')

        amount_uzs = to_uzs(amount=amount, currency=currency, fx_rate=fx_rate)
        customer = self._resolve_customer(customer_name)
        payment = record_customer_payment(
            tenant_id=self.ctx.tenant.id,
            customer_id=customer.id,
            amount=amount_uzs,
            payment_method=_map_customer_payment_method(payment_type),
            notes=f'Excel import {row_obj.source_sheet}:{row_obj.source_row_id}',
            payment_date=dt,
            operation_currency=currency,
            operation_amount=amount,
            fx_rate_snapshot=fx_rate,
            functional_amount_uzs=amount_uzs,
        )
        self._mark_row(
            row_obj,
            status=ExcelImportRow.Status.APPLIED,
            target_model='customers.CustomerPayment',
            target_id=payment.id,
            operation_currency=currency,
            operation_amount=amount,
            fx_rate_snapshot=fx_rate,
            functional_amount=amount_uzs,
        )

    def _apply_expense_row(self, row_obj: ExcelImportRow, row: dict[str, Any]) -> None:
        dt = parse_datetime(pick(row, 'SANA'))
        creditor_name = str(pick(row, 'CREDITOR')).strip()
        amount = parse_decimal(pick(row, 'MIQDOR'), default=Decimal('0')) or Decimal('0')
        currency = normalize_currency(pick(row, 'VALYUTA'))
        fx_rate = parse_decimal(pick(row, 'KURS'), default=Decimal('1')) or Decimal('1')
        payment_source = str(pick(row, "QAYERDAN TO'LOV QILINDI")).strip()
        payment_type = str(pick(row, "TO'LOV TURI")).strip()
        if amount <= 0:
            raise ValueError('Invalid expense row: amount required')

        amount_uzs = to_uzs(amount=amount, currency=currency, fx_rate=fx_rate)
        supplier = Supplier.objects.filter(
            tenant=self.ctx.tenant,
            name__iexact=creditor_name,
            is_active=True,
        ).first()
        if supplier:
            payment = record_supplier_payment(
                tenant_id=self.ctx.tenant.id,
                supplier_id=supplier.id,
                amount=amount_uzs,
                payment_method=_map_supplier_payment_method(payment_type),
                notes=f'Excel import {row_obj.source_sheet}:{row_obj.source_row_id}',
                payment_date=dt,
                operation_currency=currency,
                operation_amount=amount,
                fx_rate_snapshot=fx_rate,
                functional_amount_uzs=amount_uzs,
            )
            self._mark_row(
                row_obj,
                status=ExcelImportRow.Status.APPLIED,
                target_model='suppliers.SupplierPayment',
                target_id=payment.id,
                operation_currency=currency,
                operation_amount=amount,
                fx_rate_snapshot=fx_rate,
                functional_amount=amount_uzs,
            )
            return

        expense = record_expense(
            tenant_id=self.ctx.tenant.id,
            title=creditor_name or 'Imported expense',
            category='excel-import',
            payment_method=_map_supplier_payment_method(payment_type),
            operation_currency=currency,
            operation_amount=amount,
            fx_rate_snapshot=fx_rate,
            functional_amount_uzs=amount_uzs,
            source_account_code=_map_cash_account_code(payment_source),
            occurred_at=dt,
            notes=f'Excel import {row_obj.source_sheet}:{row_obj.source_row_id}',
        )
        self._mark_row(
            row_obj,
            status=ExcelImportRow.Status.APPLIED,
            target_model='finance.Expense',
            target_id=expense.id,
            operation_currency=currency,
            operation_amount=amount,
            fx_rate_snapshot=fx_rate,
            functional_amount=amount_uzs,
        )

    def _apply_exchange_row(self, row_obj: ExcelImportRow, row: dict[str, Any]) -> None:
        dt = parse_datetime(pick(row, 'SANA'))
        incoming_account_name = str(pick(row, 'KIRIM')).strip()
        outgoing_account_name = str(pick(row, 'CHIQIM')).strip()
        incoming_amount = parse_decimal(pick(row, 'KIRIM MIQDORI'), default=Decimal('0')) or Decimal('0')
        outgoing_amount = parse_decimal(pick(row, 'CHIQIM MIQDORI'), default=Decimal('0')) or Decimal('0')
        outgoing_currency = normalize_currency(pick(row, 'VALYUTA (CHIQUVCHI)'))
        fx_rate = parse_decimal(pick(row, 'KURS'), default=Decimal('1')) or Decimal('1')
        if outgoing_amount <= 0:
            raise ValueError('Invalid exchange row: outgoing amount required')

        functional_amount = to_uzs(amount=outgoing_amount, currency=outgoing_currency, fx_rate=fx_rate)
        incoming_code = _map_cash_account_code(incoming_account_name)
        outgoing_code = _map_cash_account_code(outgoing_account_name)

        entry = create_journal_entry(
            tenant_id=self.ctx.tenant.id,
            operation_type='transfer',
            operation_id=int(row_obj.id),
            lines=[
                {
                    'account_code': incoming_code,
                    'debit': functional_amount,
                    'credit': Decimal('0'),
                    'description': f'Currency exchange incoming {incoming_amount}',
                },
                {
                    'account_code': outgoing_code,
                    'debit': Decimal('0'),
                    'credit': functional_amount,
                    'description': f'Currency exchange outgoing {outgoing_amount} {outgoing_currency}',
                },
            ],
            description=f'Imported currency exchange row {row_obj.source_row_id}',
            date=dt,
        )

        self._mark_row(
            row_obj,
            status=ExcelImportRow.Status.APPLIED,
            target_model='finance.JournalEntry',
            target_id=entry.id,
            operation_currency=outgoing_currency,
            operation_amount=outgoing_amount,
            fx_rate_snapshot=fx_rate,
            functional_amount=functional_amount,
        )

    def _reconcile(self, expected: dict[str, Any]) -> dict[str, Any]:
        tenant_id = self.ctx.tenant.id

        cash_by_account: dict[str, Decimal] = {}
        from apps.finance.models import JournalLine
        for code in ('1000', '1010'):
            row = JournalLine.objects.filter(
                tenant_id=tenant_id,
                account__code=code,
            ).aggregate(
                debit=models.Sum('debit') or Decimal('0'),
                credit=models.Sum('credit') or Decimal('0'),
            )
            debit = row.get('debit') or Decimal('0')
            credit = row.get('credit') or Decimal('0')
            cash_by_account[code] = (debit - credit).quantize(Decimal('0.01'))

        inventory_qs = (
            Lot.objects
            .filter(tenant_id=tenant_id, is_active=True, quantity_remaining__gt=0)
            .values('location__name')
            .annotate(
                total_qty=models.Sum('quantity_remaining'),
                total_value=models.Sum(
                    models.ExpressionWrapper(
                        models.F('quantity_remaining') * models.F('cost_per_unit'),
                        output_field=models.DecimalField(max_digits=18, decimal_places=2),
                    )
                ),
            )
            .order_by('location__name')
        )
        inventory_by_location = [
            {
                'location': item['location__name'],
                'quantity': int(item['total_qty'] or 0),
                'value_uzs': str((item['total_value'] or Decimal('0')).quantize(Decimal('0.01'))),
            }
            for item in inventory_qs
        ]

        sales_total = (
            Sale.objects
            .filter(tenant_id=tenant_id, status=Sale.SaleStatus.COMPLETED)
            .aggregate(
                revenue=models.Sum('total_amount'),
                cogs=models.Sum('total_cogs'),
            )
        )
        revenue = sales_total.get('revenue') or Decimal('0')
        cogs = sales_total.get('cogs') or Decimal('0')
        gross_profit = (revenue - cogs).quantize(Decimal('0.01'))

        receivables = Customer.objects.filter(tenant_id=tenant_id).aggregate(
            total=models.Sum('outstanding_balance')
        ).get('total') or Decimal('0')
        payables = Supplier.objects.filter(tenant_id=tenant_id).aggregate(
            total=models.Sum('outstanding_balance')
        ).get('total') or Decimal('0')

        computed = {
            'cash_balance': {k: str(v) for k, v in cash_by_account.items()},
            'inventory_by_location': inventory_by_location,
            'receivables_total_uzs': str(receivables.quantize(Decimal('0.01'))),
            'payables_total_uzs': str(payables.quantize(Decimal('0.01'))),
            'sales_revenue_uzs': str(revenue.quantize(Decimal('0.01'))),
            'sales_cogs_uzs': str(cogs.quantize(Decimal('0.01'))),
            'gross_profit_uzs': str(gross_profit),
        }

        deltas = _compute_deltas(expected, computed)
        return {
            'computed': computed,
            'expected': expected,
            'deltas': deltas,
        }

    def _resolve_seller_user_id(self, tenant: Business) -> int:
        user_model = get_user_model()
        cashier = (
            user_model.objects.filter(groups__name='cashier', is_active=True)
            .order_by('id')
            .first()
        )
        if cashier:
            return cashier.id
        return tenant.owner_id

    def _resolve_location(
        self,
        tenant_id: int,
        name: str,
        *,
        location_type: str | None = None,
    ) -> Location:
        clean = str(name or '').strip() or 'DEFAULT'
        location = Location.objects.filter(
            tenant_id=tenant_id,
            name__iexact=clean,
        ).first()
        if location:
            return location
        inferred_type = (
            location_type
            or (Location.LocationType.STORE if _is_store_name(clean) else Location.LocationType.WAREHOUSE)
        )
        return Location.objects.create(
            tenant_id=tenant_id,
            name=clean,
            location_type=inferred_type,
            is_active=True,
        )

    def _resolve_supplier(self, name: str) -> Supplier:
        supplier, _ = Supplier.objects.get_or_create(
            tenant=self.ctx.tenant,
            name=name,
            defaults={'is_active': True},
        )
        return supplier

    def _resolve_customer(self, name: str) -> Customer:
        customer, _ = Customer.objects.get_or_create(
            tenant=self.ctx.tenant,
            name=name,
            defaults={'is_active': True},
        )
        return customer

    def _resolve_product_variant(
        self,
        *,
        product_name: str,
        base_price: Decimal,
    ) -> tuple[Any, bool]:
        product = Product.objects.filter(
            tenant=self.ctx.tenant,
            name__iexact=product_name,
        ).first()
        created = False
        if product is None:
            category = self._import_category()
            product = create_product_with_variants(
                tenant_id=self.ctx.tenant.id,
                name=product_name,
                category_id=category.id,
                base_price=str(base_price.quantize(Decimal('0.01'))),
                pricing_mode='DEFAULT_EDITABLE',
                description='Imported from Excel alignment',
                variant_data=None,
            )
            created = True
        elif (product.base_price is None or product.base_price == 0) and base_price > 0:
            product.base_price = base_price.quantize(Decimal('0.01'))
            product.save(update_fields=['base_price', 'updated_at'])

        variant = product.variants.filter(is_active=True).order_by('id').first()
        if variant is None:
            from apps.catalog.models import ProductVariant
            variant = ProductVariant.objects.create(
                tenant=self.ctx.tenant,
                product=product,
                sku='',
            )
        return variant, created

    def _import_category(self) -> Category:
        category, _ = Category.objects.get_or_create(
            tenant=self.ctx.tenant,
            name='Imported',
            defaults={
                'default_pricing_mode': 'DEFAULT_EDITABLE',
                'sort_order': 999,
            },
        )
        return category

    def _ensure_open_session(self, location_id: int) -> PosSession:
        session = (
            PosSession.objects
            .filter(
                tenant=self.ctx.tenant,
                location_id=location_id,
                status=PosSession.SessionStatus.OPEN,
            )
            .order_by('-opened_at')
            .first()
        )
        if session:
            return session
        return open_pos_session(
            tenant_id=self.ctx.tenant.id,
            location_id=location_id,
            opened_by_id=self.ctx.seller_user_id,
            opening_cash=Decimal('0'),
        )

    def _was_applied_before(self, row_obj: ExcelImportRow) -> bool:
        return ExcelImportRow.objects.filter(
            tenant=self.ctx.tenant,
            source_sheet=row_obj.source_sheet,
            row_fingerprint=row_obj.row_fingerprint,
            status=ExcelImportRow.Status.APPLIED,
        ).exclude(batch=self.ctx.batch).exists()

    def _mark_row(
        self,
        row_obj: ExcelImportRow,
        *,
        status: str,
        target_model: str = '',
        target_id: int | None = None,
        operation_currency: str = 'UZS',
        operation_amount: Decimal | None = None,
        fx_rate_snapshot: Decimal | None = None,
        functional_amount: Decimal | None = None,
    ) -> None:
        row_obj.status = status
        row_obj.target_model = target_model
        row_obj.target_id = target_id
        row_obj.operation_currency = operation_currency
        row_obj.operation_amount = operation_amount
        row_obj.fx_rate_snapshot = fx_rate_snapshot
        row_obj.functional_amount = functional_amount
        row_obj.parse_errors = []
        row_obj.failure_category = ''
        row_obj.save(update_fields=[
            'status',
            'target_model',
            'target_id',
            'operation_currency',
            'operation_amount',
            'fx_rate_snapshot',
            'functional_amount',
            'parse_errors',
            'failure_category',
            'updated_at',
        ])

    def _fail_row(
        self,
        row_obj: ExcelImportRow,
        message: str,
        *,
        category: str = ExcelImportRow.FailureCategory.OTHER,
    ) -> None:
        row_obj.status = ExcelImportRow.Status.FAILED
        row_obj.parse_errors = [message]
        row_obj.failure_category = category
        row_obj.save(update_fields=['status', 'parse_errors', 'failure_category', 'updated_at'])


def _is_empty_row(row: dict[str, Any]) -> bool:
    for key, value in row.items():
        if key == '_row_id':
            continue
        if str(value).strip():
            return False
    return True


def _extract_photo_url_from_row(row: dict[str, Any]) -> str:
    for value in row.values():
        text = str(value or '').strip()
        if 'drive.google.com' in text or text.startswith('http://') or text.startswith('https://'):
            return text
    return ''


def _is_store_name(name: str) -> bool:
    text = str(name or '').strip().upper()
    return text in {'DOKON', 'STORE', 'SHOP'}


def _map_sale_payment_method(value: str) -> str:
    text = str(value or '').strip().upper()
    if 'QARZ' in text or 'CREDIT' in text:
        return Sale.PaymentMethod.CREDIT
    if any(token in text for token in ('KARTA', 'CARD', 'PLASTIK', 'BANK')):
        return Sale.PaymentMethod.CARD
    return Sale.PaymentMethod.CASH


def _map_customer_payment_method(value: str) -> str:
    text = str(value or '').strip().upper()
    if any(token in text for token in ('BANK', 'CARD', 'PLASTIK')):
        return 'bank'
    return 'cash'


def _map_supplier_payment_method(value: str) -> str:
    text = str(value or '').strip().upper()
    if any(token in text for token in ('BANK', 'CARD', 'PLASTIK')):
        return 'bank'
    return 'cash'


def _map_cash_account_code(account_name: str) -> str:
    text = str(account_name or '').strip().upper()
    if any(token in text for token in ('USD', 'DOLLAR', 'BANK', 'PLASTIK', 'CARD')):
        return '1010'
    return '1000'


def _classify_failure_category(exc: Exception) -> str:
    message = str(exc).lower()
    if any(token in message for token in (
        'date format',
        'datetime',
        'empty datetime',
        'unsupported date',
        'invalid date',
    )):
        return ExcelImportRow.FailureCategory.PARSE
    if any(token in message for token in (
        'not found',
        'invalid',
        'required',
        'missing',
        'unknown',
    )):
        return ExcelImportRow.FailureCategory.MAPPING
    if any(token in message for token in (
        'immutable',
        'insufficient',
        'pricing mode',
        'credit sale',
        'cannot',
    )):
        return ExcelImportRow.FailureCategory.DOMAIN
    return ExcelImportRow.FailureCategory.OTHER


def _compute_deltas(expected: dict[str, Any], computed: dict[str, Any]) -> dict[str, Any]:
    if not expected:
        return {}
    deltas: dict[str, Any] = {}
    for key, expected_value in expected.items():
        current = computed.get(key)
        if isinstance(expected_value, (int, float, str)) and isinstance(current, (int, float, str)):
            exp_dec = parse_decimal(expected_value, default=Decimal('0')) or Decimal('0')
            cur_dec = parse_decimal(current, default=Decimal('0')) or Decimal('0')
            deltas[key] = str((cur_dec - exp_dec).quantize(Decimal('0.01')))
        else:
            deltas[key] = {'expected': expected_value, 'computed': current}
    return deltas
