"""Run sandbox pilot flow for Excel alignment."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.excel_alignment import (
    ExcelAlignmentImporter,
    extract_sheets,
    load_snapshot,
    normalize_row_keys,
    parse_datetime,
    pick,
)
from apps.core.models import Business, ExcelImportBatch, ExcelImportRow


class Command(BaseCommand):
    help = (
        'Run sandbox pilot workflow: dry-run -> load-master -> '
        'load-transactions (sliced period) -> reconcile.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source-file', type=str, required=True)
        parser.add_argument('--tenant-id', type=int, required=False)
        parser.add_argument('--tenant-name', type=str, default='MicroPOS Sandbox Pilot')
        parser.add_argument('--owner-username', type=str, default='owner')
        parser.add_argument('--days', type=int, default=14)
        parser.add_argument('--strict', action='store_true')
        parser.add_argument('--seller-user-id', type=int, required=False)

    def handle(self, *args, **options):
        source_file = options['source_file']
        tenant_id = options.get('tenant_id')
        tenant_name = options.get('tenant_name') or 'MicroPOS Sandbox Pilot'
        owner_username = options.get('owner_username') or 'owner'
        days = max(1, int(options.get('days') or 14))
        strict = bool(options.get('strict'))
        seller_user_id = options.get('seller_user_id')

        try:
            snapshot = load_snapshot(source_file)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f'Unable to load source file: {exc}') from exc

        tenant = self._resolve_or_create_tenant(
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            owner_username=owner_username,
        )
        self.stdout.write(self.style.NOTICE(f'Pilot tenant: #{tenant.id} {tenant.name}'))

        tx_slice_snapshot = _slice_transaction_period(snapshot, days=days)

        with transaction.atomic():
            batches = []
            batches.append(self._run_mode(
                tenant_id=tenant.id,
                mode=ExcelImportBatch.Mode.DRY_RUN,
                snapshot=snapshot,
                source_ref=source_file,
                strict=strict,
                seller_user_id=seller_user_id,
                notes=f'sandbox-pilot dry-run ({days}d slice configured)',
            ))
            batches.append(self._run_mode(
                tenant_id=tenant.id,
                mode=ExcelImportBatch.Mode.LOAD_MASTER,
                snapshot=snapshot,
                source_ref=source_file,
                strict=strict,
                seller_user_id=seller_user_id,
                notes='sandbox-pilot load-master',
            ))
            batches.append(self._run_mode(
                tenant_id=tenant.id,
                mode=ExcelImportBatch.Mode.LOAD_TRANSACTIONS,
                snapshot=tx_slice_snapshot,
                source_ref=source_file,
                strict=strict,
                seller_user_id=seller_user_id,
                notes=f'sandbox-pilot load-transactions ({days}d slice)',
            ))
            batches.append(self._run_mode(
                tenant_id=tenant.id,
                mode=ExcelImportBatch.Mode.RECONCILE,
                snapshot=snapshot,
                source_ref=source_file,
                strict=strict,
                seller_user_id=seller_user_id,
                notes='sandbox-pilot reconcile',
            ))

        failed_rows = ExcelImportRow.objects.filter(
            tenant=tenant,
            batch_id__in=[b.id for b in batches],
            status=ExcelImportRow.Status.FAILED,
        )
        grouped = (
            failed_rows.values('failure_category')
            .order_by('failure_category')
        )
        grouped_map = {row['failure_category'] or 'other': 0 for row in grouped}
        for row in failed_rows:
            key = row.failure_category or 'other'
            grouped_map[key] = grouped_map.get(key, 0) + 1

        self.stdout.write(self.style.SUCCESS('Sandbox pilot completed.'))
        for batch in batches:
            self.stdout.write(
                f'  - batch #{batch.id} mode={batch.mode} status={batch.status}'
            )
        self.stdout.write(f'Failed rows by category: {grouped_map}')

    def _run_mode(
        self,
        *,
        tenant_id: int,
        mode: str,
        snapshot: dict,
        source_ref: str,
        strict: bool,
        seller_user_id: int | None,
        notes: str,
    ) -> ExcelImportBatch:
        importer = ExcelAlignmentImporter(
            tenant_id=tenant_id,
            mode=mode,
            source_ref=source_ref,
            strict=strict,
            seller_user_id=seller_user_id,
            notes=notes,
        )
        importer.run(snapshot)
        return importer.ctx.batch

    def _resolve_or_create_tenant(
        self,
        *,
        tenant_id: int | None,
        tenant_name: str,
        owner_username: str,
    ) -> Business:
        if tenant_id:
            return Business.objects.get(pk=tenant_id)

        user_model = get_user_model()
        owner = user_model.objects.filter(username=owner_username).first()
        if owner is None:
            raise CommandError(
                f'Owner user "{owner_username}" not found. '
                'Pass --tenant-id or create owner first.'
            )

        tenant, _ = Business.objects.get_or_create(
            name=tenant_name,
            defaults={
                'owner': owner,
                'currency': 'UZS',
                'is_active': True,
            },
        )
        return tenant


def _slice_transaction_period(snapshot: dict, *, days: int) -> dict:
    sheets = extract_sheets(snapshot)
    tx_sheet_names = {
        'SOTIB OLISH',
        'STOCK TRANSFER',
        'SOTUV',
        'TUSHUM',
        'XARAJAT',
        'PUL AYRIBOSHLASH',
    }
    all_dates = []
    parsed_cache: dict[tuple[str, int], object] = {}

    for sheet_name, rows in sheets.items():
        if sheet_name not in tx_sheet_names:
            continue
        for idx, row in enumerate(rows):
            normalized = normalize_row_keys(row)
            try:
                if sheet_name == 'SOTUV':
                    dt = parse_datetime(pick(normalized, 'SOTUV SANASI', 'SANA'))
                else:
                    dt = parse_datetime(pick(normalized, 'SANA'))
                parsed_cache[(sheet_name, idx)] = dt
                all_dates.append(dt)
            except Exception:  # noqa: BLE001
                parsed_cache[(sheet_name, idx)] = None

    if not all_dates:
        return snapshot

    max_date = max(all_dates)
    cutoff = max_date - timedelta(days=days - 1)

    sliced_sheets: dict[str, list[dict]] = {}
    for sheet_name, rows in sheets.items():
        if sheet_name not in tx_sheet_names:
            sliced_sheets[sheet_name] = rows
            continue
        filtered = []
        for idx, row in enumerate(rows):
            dt = parsed_cache.get((sheet_name, idx))
            if dt is None:
                filtered.append(row)
                continue
            if cutoff <= dt <= max_date:
                filtered.append(row)
        sliced_sheets[sheet_name] = filtered

    return {
        'sheets': sliced_sheets,
        'opening_balances': snapshot.get('opening_balances') or {},
        'expected': snapshot.get('expected') or {},
    }
