"""
Seed the database from the Excel JSON snapshot under the vacuum model.

Pipeline (all through service layer, not raw ORM writes):
    1. Optional --wipe: hard-delete all tenant data.
    2. Upsert users, groups, Business, Chart of Accounts.
    3. Warehouses (ASOSIY/DOKON), CashAccounts (KASSA SOM / KASSA DOLLAR / PLASTIK SOM),
       Partners (USTOZ=INVESTOR, BEKZOD AKA=OPERATOR), Category + DiscountReason.
    4. MALUMOTLAR → Suppliers, Customers, Products (one variant each).
    5. SOTIB OLISH → single PARTNERSHIP Procurement (contract #1)
       - contributions from TUSHUM CAPITAL rows
       - contract capital follows actual Excel contribution ratio
       - withdrawals to drain the pot
       - receive_procurement into ASOSIY
    6. STOCK TRANSFER → transfer_lot_stock (with rough FIFO mapping).
    7. SOTUV → create_sale one per row (POS sessions per (day, location)).
    8. PUL AYRIBOSHLASH → exchange_currency after priming the source account.
    9. XARAJAT DIVIDEND → pay_dividend (bounded by pending payout).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone


SNAPSHOT_DEFAULT = 'backend/import_snapshots/client_snapshot_full_from_xlsx.json'


def _q2(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _to_decimal(value, default='0') -> Decimal:
    if value is None or value == '':
        return Decimal(default)
    return Decimal(str(value))


def _parse_dt(raw):
    if raw is None:
        return timezone.now()
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw).replace('T', ' ').split('.')[0]
        try:
            dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.strptime(s[:10], '%Y-%m-%d')
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class Command(BaseCommand):
    help = 'Wipe business data and seed database from the Excel JSON snapshot.'

    def add_arguments(self, parser):
        parser.add_argument('--snapshot', default=SNAPSHOT_DEFAULT)
        parser.add_argument('--wipe', action='store_true')
        parser.add_argument('--tenant-name', default='MicroPOS Demo')
        parser.add_argument('--verbose-seed', action='store_true')

    # ─── entry point ──────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.verbose = options['verbose_seed']
        snapshot_path = Path(options['snapshot'])
        if not snapshot_path.is_absolute():
            snapshot_path = Path.cwd() / snapshot_path
        if not snapshot_path.exists():
            raise CommandError(f'Snapshot not found: {snapshot_path}')
        with snapshot_path.open(encoding='utf-8') as fh:
            snapshot = json.load(fh)
        sheets = snapshot.get('sheets') or {}

        if options['wipe']:
            self._wipe()

        ctx = self._bootstrap_core(options['tenant_name'])
        self._seed_masters(ctx, sheets)
        self._seed_procurement(ctx, sheets)
        self._seed_transfers(ctx, sheets)
        self._seed_sales(ctx, sheets)
        self._seed_currency_exchanges(ctx, sheets)
        self._seed_dividends(ctx, sheets)
        self._report(ctx)

    # ─── wipe ─────────────────────────────────────────────────────────────

    def _wipe(self):
        """
        Hard-truncate all business tables. Keeps auth/admin/contenttypes/sessions.
        """
        from django.apps import apps as django_apps

        keep = {'auth', 'admin', 'contenttypes', 'sessions', 'django_celery_beat'}
        tables = []
        for model in django_apps.get_models():
            if model._meta.app_label in keep:
                continue
            tables.append(model._meta.db_table)
        if not tables:
            return

        self.stdout.write(f'Wiping {len(tables)} business tables…')
        with connection.cursor() as cursor:
            quoted = ', '.join(f'"{t}"' for t in tables)
            cursor.execute(f'TRUNCATE {quoted} RESTART IDENTITY CASCADE;')

        # Also drop demo-tier users so bootstrap can recreate cleanly.
        User.objects.filter(
            username__in=['admin', 'owner', 'cashier', 'warehouse', 'investor'],
        ).delete()

    # ─── bootstrap: users, tenant, partners, warehouses, cash ────────────

    def _bootstrap_core(self, tenant_name: str) -> dict:
        from apps.catalog.models import Category, DiscountReason
        from apps.core.models import Business, Partner
        from apps.finance.chart_of_accounts import setup_chart_of_accounts
        from apps.finance.models import Account, CashAccount
        from apps.inventory.models import Warehouse

        groups = {
            name: Group.objects.get_or_create(name=name)[0]
            for name in ('owner', 'cashier', 'warehouse', 'investor')
        }

        admin_user = self._upsert_user(
            'admin', 'admin@local.dev', 'Admin123!',
            groups=[groups['owner']], is_superuser=True,
        )
        owner_user = self._upsert_user(
            'owner', 'owner@local.dev', 'Owner123!',
            groups=[groups['owner']],
        )
        cashier_user = self._upsert_user(
            'cashier', 'cashier@local.dev', 'Cashier123!',
            groups=[groups['cashier']],
        )
        warehouse_user = self._upsert_user(
            'warehouse', 'warehouse@local.dev', 'Warehouse123!',
            groups=[groups['warehouse']],
        )
        investor_user = self._upsert_user(
            'investor', 'investor@local.dev', 'Investor123!',
            groups=[groups['investor']],
        )

        business, _ = Business.objects.get_or_create(
            owner=owner_user,
            name=tenant_name,
            defaults={'currency': 'UZS', 'is_active': True},
        )
        if not business.is_active:
            business.is_active = True
            business.save(update_fields=['is_active', 'updated_at'])

        setup_chart_of_accounts(business.id)
        acct_cash = Account.objects.get(tenant_id=business.id, code='1000')
        acct_bank = Account.objects.get(tenant_id=business.id, code='1010')

        warehouses = {
            'ASOSIY': Warehouse.objects.get_or_create(
                tenant=business, name='ASOSIY',
                defaults={'kind': Warehouse.WarehouseKind.STORAGE, 'is_active': True},
            )[0],
            'DOKON': Warehouse.objects.get_or_create(
                tenant=business, name='DOKON',
                defaults={'kind': Warehouse.WarehouseKind.SHOP, 'is_active': True},
            )[0],
        }

        cash_accounts = {}
        for name, currency, kind, coa in [
            ('KASSA SOM', 'UZS', CashAccount.Kind.CASH, acct_cash),
            ('KASSA DOLLAR', 'USD', CashAccount.Kind.CASH, acct_bank),
            ('PLASTIK SOM', 'UZS', CashAccount.Kind.CARD_TERMINAL, acct_bank),
        ]:
            acc, _ = CashAccount.objects.get_or_create(
                tenant=business, name=name,
                defaults={
                    'currency': currency, 'kind': kind,
                    'balance': Decimal('0'), 'is_active': True,
                    'linked_account': coa,
                },
            )
            if acc.linked_account_id != coa.id:
                acc.linked_account = coa
                acc.save(update_fields=['linked_account', 'updated_at'])
            cash_accounts[name] = acc

        operator, _ = Partner.objects.get_or_create(
            tenant=business, role=Partner.Role.OPERATOR, display_name='BEKZOD AKA',
            defaults={'user': owner_user, 'is_active': True},
        )
        investor_partner, _ = Partner.objects.get_or_create(
            tenant=business, role=Partner.Role.INVESTOR, display_name='USTOZ',
            defaults={'user': investor_user, 'is_active': True},
        )

        category, _ = Category.objects.get_or_create(
            tenant=business, name='Ковры', defaults={'sort_order': 1},
        )
        discount_reason, _ = DiscountReason.objects.get_or_create(
            tenant=business, name='Торг',
            defaults={'is_default': True, 'is_active': True},
        )

        return {
            'business': business,
            'users': {
                'admin': admin_user, 'owner': owner_user, 'cashier': cashier_user,
                'warehouse': warehouse_user, 'investor': investor_user,
            },
            'warehouses': warehouses,
            'cash_accounts': cash_accounts,
            'operator': operator,
            'investor': investor_partner,
            'category': category,
            'discount_reason': discount_reason,
            'customers': {},
            'suppliers': {},
            'products': {},      # product_name → Product
            'variants': {},      # product_name → ProductVariant
            'procurement': None, # set in _seed_procurement
            'pos_sessions': {},  # (date_key, warehouse_id) → PosSession
            'stats': defaultdict(int),
        }

    def _upsert_user(self, username, email, password, *, groups, is_superuser=False):
        user, _ = User.objects.get_or_create(
            username=username, defaults={'email': email},
        )
        user.email = email
        user.is_active = True
        user.is_staff = is_superuser
        user.is_superuser = is_superuser
        user.set_password(password)
        user.save()
        user.groups.clear()
        for g in groups:
            user.groups.add(g)
        return user

    # ─── masters: customers, suppliers, products ─────────────────────────

    def _seed_masters(self, ctx, sheets):
        from apps.catalog.services import create_product_with_variants
        from apps.customers.models import Customer
        from apps.suppliers.models import Supplier

        # Collect unique names across sheets.
        customers_set, suppliers_set, products_set = set(), set(), set()
        for row in sheets.get('MALUMOTLAR', []):
            if row.get('MIJOZLAR'):
                customers_set.add(row['MIJOZLAR'].strip())
            if row.get('MAHSULOTLAR'):
                products_set.add(row['MAHSULOTLAR'].strip())
            if row.get('TRADE\nCREDITOR'):
                suppliers_set.add(row['TRADE\nCREDITOR'].strip())
        for row in sheets.get('SOTIB OLISH', []):
            if row.get('MAHSULOT'):
                products_set.add(str(row['MAHSULOT']).strip())
            if row.get('ISM'):
                suppliers_set.add(str(row['ISM']).strip())
        for row in sheets.get('SOTUV', []):
            if row.get('MIJOZ'):
                customers_set.add(str(row['MIJOZ']).strip())
            if row.get('MAHSULOT'):
                products_set.add(str(row['MAHSULOT']).strip())

        biz_id = ctx['business'].id
        for name in sorted(suppliers_set):
            s, _ = Supplier.objects.get_or_create(
                tenant_id=biz_id, name=name,
                defaults={'is_active': True},
            )
            ctx['suppliers'][name] = s
        for name in sorted(customers_set):
            c, _ = Customer.objects.get_or_create(
                tenant_id=biz_id, name=name,
                defaults={'is_active': True},
            )
            ctx['customers'][name] = c

        # Price hint: average of sale prices in UZS for each product (fallback 100k).
        price_hint: dict[str, Decimal] = defaultdict(lambda: Decimal('0'))
        price_count: dict[str, int] = defaultdict(int)
        for row in sheets.get('SOTUV', []):
            name = str(row.get('MAHSULOT') or '').strip()
            if not name:
                continue
            currency = str(row.get('VALYUTA') or 'SOM').strip().upper()
            price_raw = _to_decimal(row.get('SOTUV NARXI'))
            fx = _to_decimal(row.get('KURS'), '1')
            price_uzs = price_raw if currency == 'SOM' else (price_raw * fx)
            price_hint[name] += price_uzs
            price_count[name] += 1

        cat_id = ctx['category'].id
        for name in sorted(products_set):
            avg = (
                (price_hint[name] / Decimal(price_count[name])).quantize(Decimal('0.01'))
                if price_count[name] else Decimal('100000.00')
            )
            product = create_product_with_variants(
                tenant_id=biz_id, name=name, category_id=cat_id,
                base_price=str(avg), pricing_mode='EDITABLE', variant_data=None,
            )
            variant = product.variants.filter(is_active=True).first()
            ctx['products'][name] = product
            ctx['variants'][name] = variant

        ctx['stats']['customers'] = len(ctx['customers'])
        ctx['stats']['suppliers'] = len(ctx['suppliers'])
        ctx['stats']['products'] = len(ctx['products'])
        if self.verbose:
            self.stdout.write(
                f"  masters: {len(ctx['suppliers'])} suppliers, "
                f"{len(ctx['customers'])} customers, {len(ctx['products'])} products"
            )

    # ─── procurement: one PARTNERSHIP contract for all SOTIB OLISH ───────

    def _seed_procurement(self, ctx, sheets):
        from apps.partnerships.models import Procurement
        from apps.partnerships.services import (
            add_contribution, add_withdrawal, open_procurement,
            receive_procurement,
        )

        items_raw = [r for r in sheets.get('SOTIB OLISH', []) if r.get('MAHSULOT')]
        if not items_raw:
            self.stdout.write('  no SOTIB OLISH rows, skipping procurement')
            return

        biz_id = ctx['business'].id
        # Pick supplier: first non-empty ISM, fallback CHINA.
        supplier_name = next(
            (str(r['ISM']).strip() for r in items_raw if r.get('ISM')),
            'CHINA',
        )
        supplier = ctx['suppliers'].get(supplier_name) or next(
            iter(ctx['suppliers'].values()), None,
        )
        opened_at = _parse_dt(items_raw[0].get('SANA'))

        items_payload = []
        total_items_usd = Decimal('0')
        for row in items_raw:
            name = str(row['MAHSULOT']).strip()
            variant = ctx['variants'].get(name)
            if variant is None:
                continue
            qty = _to_decimal(row.get('SONI'))
            unit_usd = _to_decimal(row.get('MAHSULOT NARXI'))
            fx = _to_decimal(row.get('KURS'), '12150')
            items_payload.append({
                'product_variant_id': variant.id,
                'quantity': qty,
                'unit_purchase_price': unit_usd,
                'currency': 'USD',
                'fx_rate': fx,
            })
            total_items_usd += (qty * unit_usd)

        # Current bulk seed keeps customs outside landed cost because this Excel
        # snapshot has unpaid procurement cost if customs is included. The
        # workflow test will exercise customs as ProcurementExpense once the
        # supplier-credit path is modelled explicitly.
        expenses_payload: list[dict] = []

        # Contributions from TUSHUM CAPITAL (real Excel amounts, USD).
        capital_rows = [
            r for r in sheets.get('TUSHUM', [])
            if str(r.get('TUSHUM TURI') or '').strip().upper() == 'CAPITAL'
        ]
        contrib_investor_usd = Decimal('0')
        contrib_operator_usd = Decimal('0')
        for row in capital_rows:
            name = str(row.get('MIJOZ') or '').strip().upper()
            amount = _to_decimal(row.get('MIQDOR'))
            currency = str(row.get('VALYUTA') or 'USD').strip().upper()
            fx = _to_decimal(row.get('KURS'), '12100')
            if currency == 'SOM':
                currency = 'UZS'
            if currency != 'USD':
                amount = amount / fx
            if 'USTOZ' in name:
                contrib_investor_usd += amount
            elif 'BEKZOD' in name:
                contrib_operator_usd += amount

        total_contrib_usd = _q2(contrib_investor_usd + contrib_operator_usd)
        investor_capital_share = (
            contrib_investor_usd / total_contrib_usd
            if total_contrib_usd > 0 else Decimal('0.7')
        )
        mudaraba_ratio = _q_ratio(
            Decimal('0.4') / investor_capital_share
            if investor_capital_share > 0 else Decimal('0.571429')
        )

        # Contract follows this case's actual capital agreement and 40/60 profit,
        # not the earlier demo example of exact 70/30 capital.
        planned_budget_usd = total_contrib_usd or _q2(total_items_usd)
        contract = {
            'mudaraba_ratio': mudaraba_ratio,
            'planned_budget': planned_budget_usd,
            'currency': 'USD',
            'partners': [
                {
                    'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                    'planned_capital_share': _q2(contrib_investor_usd),
                    'profit_share': Decimal('0.4'),
                },
                {
                    'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                    'planned_capital_share': _q2(contrib_operator_usd),
                    'profit_share': Decimal('0.6'),
                },
            ],
        }
        fx_default = _to_decimal(items_raw[0].get('KURS'), '12150')

        procurement = open_procurement(
            tenant_id=biz_id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            opened_at=opened_at,
            supplier_id=supplier.id if supplier else None,
            notes='Seeded from Excel — единый приход контракт #1',
            contract=contract,
            items=items_payload,
            expenses=expenses_payload,
        )
        ctx['procurement'] = procurement

        for row in capital_rows:
            name = str(row.get('MIJOZ') or '').strip().upper()
            amount = _to_decimal(row.get('MIQDOR'))
            currency = str(row.get('VALYUTA') or 'USD').strip().upper()
            fx = _to_decimal(row.get('KURS'), '12100')
            if currency == 'SOM':
                currency = 'UZS'
            if currency != 'USD':
                amount = amount / fx
                currency = 'USD'
                fx = _to_decimal(row.get('KURS'), '12100')
            date = _parse_dt(row.get('SANA'))

            if 'USTOZ' in name:
                partner = ctx['investor']
            elif 'BEKZOD' in name:
                partner = ctx['operator']
            else:
                continue
            add_contribution(
                tenant_id=biz_id, procurement_id=procurement.id,
                partner_id=partner.id, amount=_q2(amount),
                currency='USD', fx_rate=fx, date=date,
            )

        capital_out_usd = Decimal('0')

        # Drain any remaining balance via an aggregated supplier payment so the
        # pot hits exactly zero at receive time. No partner CAPITAL_OUT is
        # invented here; partner capital ratio comes from real contributions.
        net_pot_usd = _q2(
            contrib_investor_usd + contrib_operator_usd - capital_out_usd
        )
        if net_pot_usd > 0:
            add_withdrawal(
                tenant_id=biz_id, procurement_id=procurement.id,
                amount=net_pot_usd, currency='USD', fx_rate=fx_default,
                reason='Aggregated supplier payment',
            )

        # If contributions net of capital withdrawals fell short of the items
        # budget, we need the items to still be receivable — but receive checks
        # items × unit_price as carrying cost, not the pot. The pot just has to
        # be zero. So this top-up only matters if we underpaid the supplier.
        # In practice for this snapshot contributions ≥ budget, so no-op.
        if net_pot_usd < 0:
            self.stderr.write(
                f'  WARN: capital withdrawals exceeded contributions by '
                f'{abs(net_pot_usd)} USD — pot cannot drain cleanly.'
            )

        receive_procurement(
            tenant_id=biz_id, procurement_id=procurement.id,
            destination_warehouse_id=ctx['warehouses']['ASOSIY'].id,
            received_at=opened_at,
        )
        ctx['stats']['procurement_items'] = len(items_payload)

        # Record customs (Rastamojka) as a standalone operational expense
        # paid from KASSA DOLLAR. This hits cash + expense account but does
        # NOT touch COGS, so sale margins reconcile against Excel's MARJA.
        from apps.finance.services import record_expense
        for row in sheets.get('XARAJAT', []):
            if str(row.get("TO'LOV TURI") or '').strip().upper() != 'SOTIB OLISH':
                continue
            tarif = str(row.get("TO'LOV TA'RIFI") or '').strip().lower()
            if 'rastamoj' not in tarif and 'customs' not in tarif:
                continue
            amount = _to_decimal(row.get('MIQDOR'))
            currency = str(row.get('VALYUTA') or 'USD').strip().upper()
            if currency == 'SOM':
                currency = 'UZS'
            fx = _to_decimal(row.get('KURS'), '12150')
            date = _parse_dt(row.get('SANA'))
            account_name = str(row.get("QAYERDAN TO'LOV QILINDI") or '').strip().upper()
            source_code = '1010' if 'DOLLAR' in account_name else '1000'
            account = ctx['cash_accounts'].get(account_name)
            # Prime cash account if short.
            if account is not None:
                account.refresh_from_db()
                if account.balance < amount:
                    from apps.finance.services import record_owner_contribution
                    record_owner_contribution(
                        tenant_id=biz_id, to_account_id=account.id,
                        amount=_q2(amount - account.balance),
                        currency=account.currency,
                        date=date,
                        notes='Prime KASSA DOLLAR for customs payment',
                    )
            record_expense(
                tenant_id=biz_id,
                title=f'Растаможка — {row.get("TO\'LOV TA\'RIFI") or "Customs"}',
                operation_amount=_q2(amount),
                payment_method='cash' if source_code == '1000' else 'bank',
                occurred_at=date,
                category='customs',
                notes=f"Excel XARAJAT row {row.get('_row_id')}",
                operation_currency='USD' if currency == 'USD' else 'UZS',
                fx_rate_snapshot=fx,
                source_account_code=source_code,
            )

        if self.verbose:
            self.stdout.write(
                f"  procurement #{procurement.id} received: "
                f"{len(items_payload)} items, budget {_q2(planned_budget_usd)} USD "
                f"(contrib {_q2(contrib_investor_usd + contrib_operator_usd)}, "
                f"capital_out {_q2(capital_out_usd)}, net_drain {net_pot_usd})"
            )

    # ─── stock transfers ──────────────────────────────────────────────────

    def _seed_transfers(self, ctx, sheets):
        from apps.inventory.models import Lot, LotStock
        from apps.inventory.services import transfer_lot_stock

        biz_id = ctx['business'].id
        asosiy = ctx['warehouses']['ASOSIY']
        dokon = ctx['warehouses']['DOKON']
        by_name = {w.name.upper(): w for w in (asosiy, dokon)}

        moved = 0
        for row in sheets.get('STOCK TRANSFER', []):
            name = str(row.get('MAHSULOT') or '').strip()
            variant = ctx['variants'].get(name)
            if variant is None:
                continue
            qty = int(_to_decimal(row.get('SONI')))
            if qty <= 0:
                continue
            src = by_name.get(str(row.get('CHIQIM') or '').strip().upper())
            dst = by_name.get(str(row.get('KIRIM') or '').strip().upper())
            if not src or not dst or src.id == dst.id:
                continue

            # FIFO across lots at src for this variant.
            stocks = (
                LotStock.objects
                .filter(tenant_id=biz_id, warehouse=src, quantity_remaining__gt=0,
                        lot__product_variant=variant, lot__is_active=True)
                .select_related('lot').order_by('lot__received_at', 'lot__id')
            )
            remaining = qty
            for stock in stocks:
                if remaining <= 0:
                    break
                take = min(stock.quantity_remaining, remaining)
                transfer_lot_stock(
                    tenant_id=biz_id, lot=stock.lot,
                    from_warehouse=src, to_warehouse=dst, quantity=take,
                )
                remaining -= take
            moved += qty - remaining

        # Pre-stage DOKON with some stock for products that sell there but didn't
        # appear in STOCK TRANSFER sheet — 50% of the lot quantity.
        sotuv_dokon = {
            str(r['MAHSULOT']).strip()
            for r in sheets.get('SOTUV', [])
            if str(r.get('OMBOR') or '').upper() == 'DOKON' and r.get('MAHSULOT')
        }
        for name in sotuv_dokon:
            variant = ctx['variants'].get(name)
            if variant is None:
                continue
            dokon_qty = (
                LotStock.objects.filter(
                    tenant_id=biz_id, warehouse=dokon,
                    lot__product_variant=variant, quantity_remaining__gt=0,
                ).count()
            )
            if dokon_qty > 0:
                continue
            lot_stocks = (
                LotStock.objects
                .filter(tenant_id=biz_id, warehouse=asosiy, quantity_remaining__gt=0,
                        lot__product_variant=variant, lot__is_active=True)
                .select_related('lot').order_by('lot__received_at', 'lot__id')
            )
            for stock in lot_stocks:
                half = stock.quantity_remaining // 2 or stock.quantity_remaining
                if half <= 0:
                    continue
                transfer_lot_stock(
                    tenant_id=biz_id, lot=stock.lot,
                    from_warehouse=asosiy, to_warehouse=dokon, quantity=half,
                )
                moved += half
                break

        ctx['stats']['transfers_qty'] = moved
        if self.verbose:
            self.stdout.write(f'  transfers: {moved} units moved')

    # ─── sales ────────────────────────────────────────────────────────────

    def _seed_sales(self, ctx, sheets):
        from apps.catalog.models import ProductVariant
        from apps.core.exceptions import InsufficientStockError
        from apps.inventory.models import LotStock
        from apps.sales.models import SalePayment
        from apps.sales.services import close_pos_session, create_sale, open_pos_session

        biz_id = ctx['business'].id
        cashier = ctx['users']['cashier']

        def _session_for(date, warehouse):
            key = (date.date(), warehouse.id)
            session = ctx['pos_sessions'].get(key)
            if session is None:
                session = open_pos_session(
                    tenant_id=biz_id, location_id=warehouse.id,
                    opened_by_id=cashier.id, opening_cash=Decimal('0'),
                )
                ctx['pos_sessions'][key] = session
            return session

        method_cash = SalePayment.Method.CASH
        sold = 0; skipped = 0
        for row in sheets.get('SOTUV', []):
            name = str(row.get('MAHSULOT') or '').strip()
            variant = ctx['variants'].get(name)
            if variant is None:
                skipped += 1
                continue
            qty = int(_to_decimal(row.get('JAMI DONA')))
            if qty <= 0:
                skipped += 1
                continue
            currency = str(row.get('VALYUTA') or 'SOM').strip().upper()
            unit_raw = _to_decimal(row.get('SOTUV NARXI'))
            fx = _to_decimal(row.get('KURS'), '12200')
            unit_price_uzs = unit_raw if currency == 'SOM' else _q2(unit_raw * fx)
            warehouse_name = str(row.get('OMBOR') or 'DOKON').strip().upper()
            warehouse = ctx['warehouses'].get(warehouse_name, ctx['warehouses']['DOKON'])
            customer_name = str(row.get('MIJOZ') or '').strip()
            customer = ctx['customers'].get(customer_name)
            date = _parse_dt(row.get('SOTUV SANASI'))

            # Ensure stock is available at warehouse; fall back to the other one.
            available = (
                LotStock.objects.filter(
                    tenant_id=biz_id, warehouse=warehouse,
                    lot__product_variant=variant, quantity_remaining__gt=0,
                ).values_list('quantity_remaining', flat=True)
            )
            if sum(available) < qty:
                other = (
                    ctx['warehouses']['ASOSIY']
                    if warehouse.name.upper() == 'DOKON'
                    else ctx['warehouses']['DOKON']
                )
                available_other = (
                    LotStock.objects.filter(
                        tenant_id=biz_id, warehouse=other,
                        lot__product_variant=variant, quantity_remaining__gt=0,
                    ).values_list('quantity_remaining', flat=True)
                )
                if sum(available_other) >= qty:
                    warehouse = other
                else:
                    skipped += 1
                    continue

            session = _session_for(date, warehouse)

            if currency == 'USD':
                account = ctx['cash_accounts']['KASSA DOLLAR']
                payment_currency = 'USD'
                payment_amount = unit_raw * qty
            else:
                account = ctx['cash_accounts']['KASSA SOM']
                payment_currency = 'UZS'
                payment_amount = unit_price_uzs * qty

            try:
                create_sale(
                    tenant_id=biz_id,
                    pos_session_id=session.id,
                    location_id=warehouse.id,
                    sold_by_id=cashier.id,
                    customer_id=customer.id if customer else None,
                    lines=[{
                        'product_variant_id': variant.id,
                        'quantity': qty,
                        'unit_price': unit_price_uzs,
                    }],
                    payments=[{
                        'amount': payment_amount,
                        'currency': payment_currency,
                        'fx_rate': fx if payment_currency == 'USD' else Decimal('1'),
                        'method': method_cash,
                        'account_id': account.id,
                    }],
                    date=date,
                    notes=f"Excel SOTUV row {row.get('_row_id')}",
                )
                sold += 1
            except InsufficientStockError:
                skipped += 1
                continue
            except Exception as exc:
                self.stderr.write(f'  sale skipped ({name} qty={qty}): {exc}')
                skipped += 1
                continue

        # Close all sessions with their expected cash so reporting is clean.
        for session in ctx['pos_sessions'].values():
            cash_in = Decimal('0')
            from apps.sales.models import Sale
            from django.db.models import Sum
            cash_in = (
                SalePayment.objects.filter(
                    sale__pos_session=session,
                    sale__status=Sale.SaleStatus.COMPLETED,
                    role=SalePayment.Role.INCOMING,
                    method=SalePayment.Method.CASH,
                    currency='UZS',
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            )
            close_pos_session(
                session=session, closed_by_id=cashier.id,
                actual_cash=session.opening_cash + cash_in,
            )

        ctx['stats']['sales'] = sold
        ctx['stats']['sales_skipped'] = skipped
        if self.verbose:
            self.stdout.write(f'  sales: {sold} completed, {skipped} skipped')

    # ─── currency exchanges ───────────────────────────────────────────────

    def _seed_currency_exchanges(self, ctx, sheets):
        from apps.finance.services import exchange_currency, record_owner_contribution

        biz_id = ctx['business'].id
        accts_by_name = {name.upper(): a for name, a in ctx['cash_accounts'].items()}
        converted = 0
        for row in sheets.get('PUL AYRIBOSHLASH', []):
            from_name = str(row.get('CHIQIM') or '').strip().upper()
            to_name = str(row.get('KIRIM') or '').strip().upper()
            from_amount = _to_decimal(row.get('CHIQIM MIQDORI'))
            to_amount = _to_decimal(row.get('KIRIM MIQDORI'))
            if from_amount <= 0 or to_amount <= 0:
                continue
            src = accts_by_name.get(from_name)
            dst = accts_by_name.get(to_name)
            if not src or not dst or src.id == dst.id:
                continue
            # Ensure source has funds — top up via OwnerContribution if short.
            src.refresh_from_db()
            if src.balance < from_amount:
                deficit = from_amount - src.balance
                record_owner_contribution(
                    tenant_id=biz_id,
                    to_account_id=src.id,
                    amount=deficit,
                    currency=src.currency,
                    date=_parse_dt(row.get('SANA')),
                    notes='Prime source account for currency exchange',
                )
            rate = (to_amount / from_amount).quantize(Decimal('0.000001'))
            try:
                exchange_currency(
                    tenant_id=biz_id,
                    from_account_id=src.id, to_account_id=dst.id,
                    from_amount=from_amount, rate=rate,
                    date=_parse_dt(row.get('SANA')),
                    notes=f"Excel PUL AYRIBOSHLASH row {row.get('_row_id')}",
                )
                converted += 1
            except Exception as exc:
                self.stderr.write(f'  exchange skipped: {exc}')
        ctx['stats']['exchanges'] = converted
        if self.verbose:
            self.stdout.write(f'  currency exchanges: {converted}')

    # ─── dividend payments ────────────────────────────────────────────────

    def _seed_dividends(self, ctx, sheets):
        from apps.finance.services import record_owner_contribution
        from apps.partnerships.models import PartnerLedgerEntry, ProcurementPartnerLedger
        from apps.partnerships.services import pay_dividend
        from django.db.models import Sum

        procurement = ctx['procurement']
        if procurement is None:
            return
        biz_id = ctx['business'].id
        paid = 0
        dividend_rows = [
            r for r in sheets.get('XARAJAT', [])
            if str(r.get("TO'LOV TURI") or '').strip().upper() == 'DIVIDEND'
        ]
        for row in dividend_rows:
            name = str(row.get('CREDITOR') or '').strip().upper()
            if 'USTOZ' in name:
                partner = ctx['investor']
            elif 'BEKZOD' in name:
                partner = ctx['operator']
            else:
                continue
            amount = _to_decimal(row.get('MIQDOR'))
            currency = str(row.get('VALYUTA') or 'USD').strip().upper()
            if currency == 'SOM':
                currency = 'UZS'
            fx = _to_decimal(row.get('KURS'), '12200')
            account_name = str(row.get("QAYERDAN TO'LOV QILINDI") or '').strip().upper()
            account = ctx['cash_accounts'].get(account_name)
            date = _parse_dt(row.get('SANA'))

            # Bound dividend by pending payout (to not violate invariant).
            ledger = ProcurementPartnerLedger.objects.filter(
                procurement=procurement, partner=partner, tenant_id=biz_id,
            ).first()
            pending = Decimal('0')
            if ledger:
                agg = PartnerLedgerEntry.objects.filter(ledger=ledger) \
                    .values('entry_type').annotate(total=Sum('functional_amount_uzs'))
                totals = {r['entry_type']: r['total'] or Decimal('0') for r in agg}
                pending = (
                    totals.get('PROFIT_ACCRUED', Decimal('0'))
                    - totals.get('PROFIT_REVERSED', Decimal('0'))
                    - totals.get('LOSS_INCURRED', Decimal('0'))
                    - totals.get('DIVIDEND_PAID', Decimal('0'))
                )
            if pending <= 0:
                continue
            pay_amount_native = min(amount, pending if currency == 'UZS' else pending / fx)
            pay_amount_native = _q2(pay_amount_native)
            if pay_amount_native <= 0:
                continue

            # Prime cash account if needed.
            if account is not None:
                account.refresh_from_db()
                if account.balance < pay_amount_native:
                    deficit = pay_amount_native - account.balance
                    record_owner_contribution(
                        tenant_id=biz_id, to_account_id=account.id,
                        amount=deficit,
                        currency=account.currency,
                        date=date,
                        notes='Prime account for dividend payout',
                    )

            try:
                pay_dividend(
                    partner_id=partner.id, procurement_id=procurement.id,
                    amount=pay_amount_native,
                    currency=currency, fx_rate=fx,
                    from_account_id=account.id if account else None,
                    tenant_id=biz_id, date=date,
                )
                paid += 1
            except Exception as exc:
                self.stderr.write(f'  dividend skipped: {exc}')
        ctx['stats']['dividends'] = paid
        if self.verbose:
            self.stdout.write(f'  dividends paid: {paid}')

    # ─── final report ─────────────────────────────────────────────────────

    def _report(self, ctx):
        stats = ctx['stats']
        self.stdout.write(self.style.SUCCESS('\nSeed complete.'))
        self.stdout.write(f"  Tenant: {ctx['business'].name} (#{ctx['business'].id})")
        self.stdout.write(
            f"  Masters: {stats['suppliers']} suppliers, "
            f"{stats['customers']} customers, {stats['products']} products"
        )
        if ctx['procurement']:
            self.stdout.write(
                f"  Procurement: #{ctx['procurement'].id} "
                f"({stats['procurement_items']} items)"
            )
        self.stdout.write(f"  Transfers: {stats['transfers_qty']} units")
        self.stdout.write(
            f"  Sales: {stats['sales']} completed "
            f"({stats['sales_skipped']} skipped)"
        )
        self.stdout.write(f"  Currency exchanges: {stats['exchanges']}")
        self.stdout.write(f"  Dividend payments: {stats['dividends']}")
        self.stdout.write('\nUsers:')
        self.stdout.write('  admin / Admin123!     (superuser)')
        self.stdout.write('  owner / Owner123!     (owner role)')
        self.stdout.write('  cashier / Cashier123! (cashier role)')
        self.stdout.write('  warehouse / Warehouse123! (warehouse role)')
        self.stdout.write('  investor / Investor123! (investor role)')
