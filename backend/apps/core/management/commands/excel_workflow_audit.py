"""Replay the Excel case as a user workflow, not as report import."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.apps import apps as django_apps
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from apps.core.demo_constants import DEFAULT_DEMO_USD_UZS_RATE
from apps.core.management.safety import require_debug_or_confirmation


SNAPSHOT_DEFAULT = 'backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json'
IN_TRANSIT_PRODUCT = 'Набор (в пути)'
IN_TRANSIT_QTY = Decimal('100')
IN_TRANSIT_TOTAL_USD = Decimal('2175.50')
CONTRACT_PLANNED_TOTAL_USD = Decimal('15000.00')
CONTRACT_INVESTOR_CAPITAL_USD = Decimal('10152.00')
CONTRACT_OPERATOR_CAPITAL_USD = Decimal('4848.00')
CONTRACT_INVESTOR_PROFIT_SHARE = Decimal('0.40')
CONTRACT_OPERATOR_PROFIT_SHARE = Decimal('0.60')


def _money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _unit(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)


def _ratio(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)


def _dec(value, default='0') -> Decimal:
    if value is None or value == '':
        return Decimal(default)
    return Decimal(str(value))


def _parse_dt(raw):
    if raw is None:
        return timezone.now()
    if isinstance(raw, datetime):
        dt = raw
    else:
        text = str(raw).replace('T', ' ').split('.')[0]
        try:
            dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.strptime(text[:10], '%Y-%m-%d')
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def resolve_snapshot_path(raw_path: str) -> Path:
    """Resolve snapshot path from repo root or backend cwd."""
    snapshot_path = Path(raw_path).expanduser()
    if snapshot_path.is_absolute():
        return snapshot_path

    candidates = [
        Path.cwd() / snapshot_path,
        Path(__file__).resolve().parents[5] / snapshot_path,
        Path(__file__).resolve().parents[4] / snapshot_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


@dataclass(frozen=True)
class Scenario:
    key: str
    tenant_name: str
    owner_username: str
    investor_username: str
    investor_display: str
    use_targeted_customs: bool


SCENARIOS = (
    Scenario(
        key='real_cost',
        tenant_name='MicroPOS Real Cost Audit',
        owner_username='owner',
        investor_username='investor',
        investor_display='Устоз 1',
        use_targeted_customs=True,
    ),
    Scenario(
        key='excel_landed',
        tenant_name='MicroPOS Excel Landed Audit',
        owner_username='owner2',
        investor_username='investor2',
        investor_display='Устоз 2',
        use_targeted_customs=False,
    ),
)


class Command(BaseCommand):
    help = 'Replay the Excel audit case through domain services and UI-like payloads.'

    def add_arguments(self, parser):
        parser.add_argument('--snapshot', default=SNAPSHOT_DEFAULT)
        parser.add_argument('--dry-run', action='store_true', help='Print workflow plan without changing database.')
        parser.add_argument('--apply', action='store_true', help='Apply workflow to database.')
        parser.add_argument('--wipe', action='store_true', help='Hard reset business data before apply.')
        parser.add_argument('--strict-gaps', action='store_true', help='Fail if Excel lacks transfer rows required by sales.')
        parser.add_argument(
            '--confirm-production-wipe',
            action='store_true',
            help='Allow this destructive workflow when DEBUG=False.',
        )

    def handle(self, *args, **options):
        if bool(options['dry_run']) == bool(options['apply']):
            raise CommandError('Choose exactly one: --dry-run or --apply.')
        if options['apply'] and not options['wipe']:
            raise CommandError('--apply requires --wipe so the audit starts from a clean database.')
        if options['apply'] and options['wipe']:
            require_debug_or_confirmation(
                command_name='excel_workflow_audit',
                confirmed=options['confirm_production_wipe'],
                flag_name='--confirm-production-wipe',
                action='this command truncates business data and rebuilds the Excel audit workflow',
            )

        snapshot_path = resolve_snapshot_path(options['snapshot'])
        if not snapshot_path.exists():
            raise CommandError(f'Snapshot not found: {snapshot_path}')
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        sheets = snapshot.get('sheets') or {}

        plan = self._build_plan(sheets)
        self._print_plan(plan, strict_gaps=options['strict_gaps'])
        if plan['blockers']:
            raise CommandError('Workflow has blockers; fix them before apply.')
        if options['strict_gaps'] and plan['warnings']:
            raise CommandError('Workflow has warnings and --strict-gaps is enabled.')
        if options['dry_run']:
            return

        with transaction.atomic():
            self._wipe_database()
            users = self._create_users()
            for scenario in SCENARIOS:
                self._apply_scenario(
                    scenario=scenario,
                    sheets=sheets,
                    plan=plan,
                    users=users,
                )
        self._refresh_financial_aggregates()

        self.stdout.write(self.style.SUCCESS('Excel workflow audit seed applied.'))
        self.stdout.write('Manual checkpoints:')
        self.stdout.write('  1. /procurements — два частично оприходованных партнёрских прихода.')
        self.stdout.write('  2. /inventory/transfers — Excel transfers + explicit audit gap transfers.')
        self.stdout.write('  3. /sales/history — продажи по Excel строкам.')
        self.stdout.write('  4. /reports/reconciliation — сверка без новых расхождений.')
        self.stdout.write('  5. /investor — USD/UZS инвесторская картина.')

    # ─── plan ───────────────────────────────────────────────────────────

    def _build_plan(self, sheets: dict) -> dict:
        purchase_rows = [row for row in sheets.get('SOTIB OLISH', []) if row.get('MAHSULOT')]
        transfer_rows = [row for row in sheets.get('STOCK TRANSFER', []) if row.get('MAHSULOT')]
        sale_rows = [row for row in sheets.get('SOTUV', []) if row.get('MAHSULOT')]
        capital_rows = [
            row for row in sheets.get('TUSHUM', [])
            if str(row.get('TUSHUM TURI') or '').strip().upper() == 'CAPITAL'
        ]
        customs_rows = [
            row for row in sheets.get('XARAJAT', [])
            if str(row.get("TO'LOV TURI") or '').strip().upper() == 'SOTIB OLISH'
            and 'rastamoj' in str(row.get("TO'LOV TA'RIFI") or '').lower()
        ]

        blockers: list[str] = []
        warnings: list[str] = []
        if not purchase_rows:
            blockers.append('SOTIB OLISH has no purchase rows.')
        if not sale_rows:
            blockers.append('SOTUV has no sale rows.')
        if len(capital_rows) < 2:
            blockers.append('TUSHUM must contain investor and operator CAPITAL rows.')
        if not customs_rows:
            warnings.append('No customs row found; real_cost scenario will have no targeted customs expense.')

        received_products = {str(row['MAHSULOT']).strip() for row in purchase_rows}
        sale_products = {str(row['MAHSULOT']).strip() for row in sale_rows}
        missing_products = sorted(sale_products - received_products)
        missing_products = [name for name in missing_products if name != IN_TRANSIT_PRODUCT]
        if missing_products:
            blockers.append(f'Sales reference products missing from purchase rows: {missing_products}')

        transfer_qty = defaultdict(Decimal)
        for row in transfer_rows:
            src = str(row.get('CHIQIM') or '').strip().upper()
            dst = str(row.get('KIRIM') or '').strip().upper()
            if src == 'ASOSIY' and dst == 'DOKON':
                transfer_qty[str(row['MAHSULOT']).strip()] += _dec(row.get('SONI'))

        sale_qty_shop = defaultdict(Decimal)
        original_warehouse_counts = Counter()
        for row in sale_rows:
            name = str(row['MAHSULOT']).strip()
            original = str(row.get('OMBOR') or 'DOKON').strip().upper()
            original_warehouse_counts[original] += 1
            sale_qty_shop[name] += _dec(row.get('JAMI DONA'))
            if original != 'DOKON':
                warnings.append(
                    f'Sale row {row.get("_row_id")} uses {original}; platform will replay it through DOKON shop.'
                )

        extra_transfers = {}
        for product, sold_qty in sorted(sale_qty_shop.items()):
            planned = transfer_qty.get(product, Decimal('0'))
            if planned < sold_qty:
                gap = sold_qty - planned
                extra_transfers[product] = gap
                warnings.append(
                    f'Excel transfer shortage for {product}: transfers {planned}, sales {sold_qty}; '
                    f'will add explicit audit transfer {gap}.'
                )

        capital_total = sum((_dec(row.get('MIQDOR')) for row in capital_rows), Decimal('0'))
        landed_received_total = sum(
            (_dec(row.get('SONI')) * _dec(row.get('MAHSULOT NARXI')) for row in purchase_rows),
            Decimal('0'),
        )
        customs_total = sum((_dec(row.get('MIQDOR')) for row in customs_rows), Decimal('0'))
        base_received_total = _money(capital_total - IN_TRANSIT_TOTAL_USD - customs_total)
        if base_received_total <= 0:
            blockers.append('Real-cost purchase basis is <= 0.')

        return {
            'purchase_rows': purchase_rows,
            'transfer_rows': transfer_rows,
            'sale_rows': sale_rows,
            'capital_rows': capital_rows,
            'customs_rows': customs_rows,
            'extra_transfers': extra_transfers,
            'capital_total': _money(capital_total),
            'landed_received_total': _money(landed_received_total),
            'customs_total': _money(customs_total),
            'base_received_total': base_received_total,
            'original_warehouse_counts': dict(original_warehouse_counts),
            'warnings': warnings,
            'blockers': blockers,
        }

    def _print_plan(self, plan: dict, *, strict_gaps: bool) -> None:
        self.stdout.write(self.style.NOTICE('Excel workflow audit plan'))
        self.stdout.write(f"  scenarios: {len(SCENARIOS)}")
        self.stdout.write(f"  purchase rows: {len(plan['purchase_rows'])} + in transit row")
        self.stdout.write(f"  sale rows: {len(plan['sale_rows'])}")
        self.stdout.write(f"  capital total: {plan['capital_total']} USD")
        self.stdout.write(
            '  contract plan: '
            f'{CONTRACT_INVESTOR_CAPITAL_USD} / {CONTRACT_OPERATOR_CAPITAL_USD} USD, '
            f'profit {CONTRACT_INVESTOR_PROFIT_SHARE} / {CONTRACT_OPERATOR_PROFIT_SHARE}'
        )
        self.stdout.write(f"  received landed total: {plan['landed_received_total']} USD")
        self.stdout.write(f"  real-cost basis: {plan['base_received_total']} USD + customs {plan['customs_total']} USD")
        self.stdout.write(f"  original sale warehouses: {plan['original_warehouse_counts']}")
        if plan['extra_transfers']:
            self.stdout.write(f"  explicit audit transfer gaps: {plan['extra_transfers']}")
        if strict_gaps:
            self.stdout.write('  strict gaps: enabled')
        for warning in plan['warnings']:
            self.stdout.write(self.style.WARNING(f'  WARN: {warning}'))
        for blocker in plan['blockers']:
            self.stdout.write(self.style.ERROR(f'  BLOCKER: {blocker}'))

    # ─── apply ──────────────────────────────────────────────────────────

    def _wipe_database(self) -> None:
        cache.clear()
        keep = {'auth', 'admin', 'contenttypes', 'sessions', 'django_celery_beat'}
        tables = [
            model._meta.db_table
            for model in django_apps.get_models()
            if model._meta.app_label not in keep
        ]
        if tables:
            quoted = ', '.join(f'"{table}"' for table in tables)
            with connection.cursor() as cursor:
                cursor.execute(f'TRUNCATE {quoted} RESTART IDENTITY CASCADE;')
        User.objects.all().delete()

    def _refresh_financial_aggregates(self) -> None:
        from apps.analytics.tasks import aggregate_daily_pnl
        from apps.sales.models import Sale

        cache.clear()
        sale_days = (
            Sale.objects
            .filter(status='completed')
            .dates('date', 'day')
            .order_by('date')
        )
        tenant_ids = list(
            Sale.objects
            .filter(status='completed')
            .values_list('tenant_id', flat=True)
            .distinct()
        )
        for tenant_id in tenant_ids:
            for day in sale_days:
                aggregate_daily_pnl(tenant_id, day.isoformat())
        cache.clear()

    def _create_users(self) -> dict[str, User]:
        groups = {
            name: Group.objects.get_or_create(name=name)[0]
            for name in ('owner', 'cashier', 'warehouse', 'investor')
        }
        users = {
            'admin': self._create_user('admin', 'admin@local.dev', 'Admin123!', [groups['owner']], is_superuser=True),
            'owner': self._create_user('owner', 'owner@local.dev', 'Owner123!', [groups['owner']]),
            'owner2': self._create_user('owner2', 'owner2@local.dev', 'Owner123!', [groups['owner']]),
            'cashier': self._create_user('cashier', 'cashier@local.dev', 'Cashier123!', [groups['cashier']]),
            'warehouse': self._create_user('warehouse', 'warehouse@local.dev', 'Warehouse123!', [groups['warehouse']]),
            'investor': self._create_user('investor', 'investor@local.dev', 'Investor123!', [groups['investor']]),
            'investor2': self._create_user('investor2', 'investor2@local.dev', 'Investor123!', [groups['investor']]),
        }
        return users

    def _create_user(self, username, email, password, groups, *, is_superuser=False) -> User:
        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = True
        user.is_staff = is_superuser
        user.is_superuser = is_superuser
        user.save(update_fields=['is_active', 'is_staff', 'is_superuser'])
        user.groups.set(groups)
        return user

    def _apply_scenario(self, *, scenario: Scenario, sheets: dict, plan: dict, users: dict[str, User]) -> None:
        from apps.catalog.models import Category, DiscountReason
        from apps.catalog.services import create_product_with_variants
        from apps.core.models import Business, BusinessInvestorRelation, Partner
        from apps.customers.models import Customer
        from apps.finance.chart_of_accounts import setup_chart_of_accounts
        from apps.finance.models import Account, CashAccount, ExchangeRate
        from apps.inventory.models import Warehouse
        from apps.investors.models import Investor
        from apps.suppliers.models import Supplier

        owner = users[scenario.owner_username]
        investor_user = users[scenario.investor_username]
        business = Business.objects.create(
            owner=owner,
            name=scenario.tenant_name,
            currency='UZS',
            is_active=True,
        )
        tenant_id = business.id
        setup_chart_of_accounts(tenant_id)
        ExchangeRate.objects.create(
            tenant=business,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=DEFAULT_DEMO_USD_UZS_RATE,
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Excel workflow audit fallback rate',
            raw_payload={},
            fetched_at=timezone.now(),
        )

        cash_account = Account.objects.get(tenant_id=tenant_id, code='1000')
        bank_account = Account.objects.get(tenant_id=tenant_id, code='1010')
        warehouses = {
            'ASOSIY': Warehouse.objects.create(
                tenant=business, name='Основной склад',
                kind=Warehouse.WarehouseKind.STORAGE, is_active=True,
            ),
            'DOKON': Warehouse.objects.create(
                tenant=business, name='Основной магазин',
                kind=Warehouse.WarehouseKind.SHOP, is_active=True,
            ),
        }
        cash_accounts = {}
        for name, currency, kind, linked in (
            ('KASSA SOM', 'UZS', CashAccount.Kind.CASH, cash_account),
            ('KASSA DOLLAR', 'USD', CashAccount.Kind.CASH, bank_account),
            ('PLASTIK SOM', 'UZS', CashAccount.Kind.CARD_TERMINAL, bank_account),
        ):
            cash_accounts[name] = CashAccount.objects.create(
                tenant=business,
                name=name,
                currency=currency,
                kind=kind,
                balance=Decimal('0'),
                is_active=True,
                linked_account=linked,
            )

        operator = Partner.objects.create(
            tenant=business,
            role=Partner.Role.OPERATOR,
            display_name='Owner operator',
            user=owner,
            is_active=True,
        )
        investor = Partner.objects.create(
            tenant=business,
            role=Partner.Role.INVESTOR,
            display_name=scenario.investor_display,
            user=investor_user,
            is_active=True,
        )
        BusinessInvestorRelation.objects.create(
            tenant=business,
            partner=investor,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
            created_by=owner,
            notes='Excel workflow audit investor access',
        )
        Investor.objects.create(
            tenant=business,
            user=investor_user,
            name=scenario.investor_display,
            email=investor_user.email,
            is_active=True,
        )

        category = Category.objects.create(tenant=business, name='Ковры', sort_order=1)
        discount_reason = DiscountReason.objects.create(
            tenant=business, name='Торг', is_default=True, is_active=True,
        )
        supplier = Supplier.objects.create(tenant=business, name='Excel поставщик', is_active=True)
        customers = self._create_customers(tenant_id, sheets)
        variants = self._create_products(
            tenant_id=tenant_id,
            category_id=category.id,
            sheets=sheets,
            create_product_with_variants=create_product_with_variants,
        )
        procurement = self._create_procurement(
            scenario=scenario,
            tenant_id=tenant_id,
            supplier_id=supplier.id,
            operator=operator,
            investor=investor,
            sheets=sheets,
            plan=plan,
            variants=variants,
        )
        self._transfer_for_sales(
            tenant_id=tenant_id,
            procurement=procurement,
            warehouses=warehouses,
            sheets=sheets,
            plan=plan,
            variants=variants,
        )
        self._replay_sales(
            tenant_id=tenant_id,
            cashier=users['cashier'],
            shop=warehouses['DOKON'],
            cash_accounts=cash_accounts,
            customers=customers,
            variants=variants,
            discount_reason_id=discount_reason.id,
            sheets=sheets,
        )
        self.stdout.write(self.style.SUCCESS(f'  {scenario.tenant_name}: applied'))

    def _create_customers(self, tenant_id: int, sheets: dict):
        from apps.customers.models import Customer

        names = {
            str(row.get('MIJOZ') or '').strip()
            for row in sheets.get('SOTUV', [])
            if str(row.get('MIJOZ') or '').strip()
        }
        result = {}
        for name in sorted(names):
            result[name] = Customer.objects.create(
                tenant_id=tenant_id,
                name=name,
                is_active=True,
            )
        return result

    def _create_products(self, *, tenant_id: int, category_id: int, sheets: dict, create_product_with_variants):
        products = {
            str(row['MAHSULOT']).strip()
            for row in sheets.get('SOTIB OLISH', [])
            if row.get('MAHSULOT')
        }
        products.add(IN_TRANSIT_PRODUCT)
        sale_price_modes = defaultdict(Counter)
        for row in sheets.get('SOTUV', []):
            name = str(row.get('MAHSULOT') or '').strip()
            if not name:
                continue
            currency = str(row.get('VALYUTA') or 'SOM').strip().upper()
            raw = _dec(row.get('SOTUV NARXI'))
            fx = _dec(row.get('KURS'), '1')
            price_uzs = _money(raw if currency == 'SOM' else raw * fx)
            sale_price_modes[name][price_uzs] += 1
        variants = {}
        for name in sorted(products):
            mode = sale_price_modes[name].most_common(1)
            base_price = mode[0][0] if mode else Decimal('100000.00')
            product = create_product_with_variants(
                tenant_id=tenant_id,
                name=name,
                category_id=category_id,
                base_price=str(base_price),
                pricing_mode='EDITABLE',
                variant_data=None,
            )
            variants[name] = product.variants.filter(is_active=True).first()
        return variants

    def _create_procurement(
        self,
        *,
        scenario: Scenario,
        tenant_id: int,
        supplier_id: int,
        operator,
        investor,
        sheets: dict,
        plan: dict,
        variants: dict,
    ):
        from apps.partnerships.models import Procurement, ProcurementExpense
        from apps.partnerships.services import (
            add_contribution,
            get_procurement_receive_plan,
            open_procurement,
            pay_procurement_expenses,
            pay_procurement_items,
            receive_procurement,
            update_procurement_expense_targets,
        )

        purchase_rows = plan['purchase_rows']
        opened_at = _parse_dt(purchase_rows[0].get('SANA'))
        capital_by_name = self._capital_by_name(plan['capital_rows'])
        investor_capital = capital_by_name['USTOZ']
        operator_capital = capital_by_name['BEKZOD AKA']
        total_capital = _money(investor_capital + operator_capital)
        investor_capital_share = CONTRACT_INVESTOR_CAPITAL_USD / CONTRACT_PLANNED_TOTAL_USD
        mudaraba_ratio = _ratio(CONTRACT_INVESTOR_PROFIT_SHARE / investor_capital_share)

        unit_prices = self._purchase_unit_prices(
            scenario=scenario,
            purchase_rows=purchase_rows,
            plan=plan,
        )
        items_payload = []
        for row in purchase_rows:
            name = str(row['MAHSULOT']).strip()
            items_payload.append({
                'product_variant_id': variants[name].id,
                'quantity': _dec(row.get('SONI')),
                'unit_purchase_price': unit_prices[name],
                'currency': 'USD',
                'fx_rate': _dec(row.get('KURS'), '12150'),
            })
        items_payload.append({
            'product_variant_id': variants[IN_TRANSIT_PRODUCT].id,
            'quantity': IN_TRANSIT_QTY,
            'unit_purchase_price': _unit(IN_TRANSIT_TOTAL_USD / IN_TRANSIT_QTY),
            'currency': 'USD',
            'fx_rate': _dec(purchase_rows[0].get('KURS'), '12150'),
        })

        expenses_payload = []
        if scenario.use_targeted_customs and plan['customs_total'] > 0:
            expenses_payload.append({
                'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                'amount': plan['customs_total'],
                'currency': 'USD',
                'fx_rate': _dec(plan['customs_rows'][0].get('KURS'), '12150'),
                'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                'notes': 'Rastamojka — targeted to received items',
            })

        procurement = open_procurement(
            tenant_id=tenant_id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            opened_at=opened_at,
            supplier_id=supplier_id,
            notes=f'Excel workflow audit: {scenario.key}',
            contract={
                'mudaraba_ratio': mudaraba_ratio,
                'planned_budget': CONTRACT_PLANNED_TOTAL_USD,
                'currency': 'USD',
                'partners': [
                    {
                        'partner_id': investor.id,
                        'role': 'INVESTOR',
                        'planned_capital_share': CONTRACT_INVESTOR_CAPITAL_USD,
                        'profit_share': CONTRACT_INVESTOR_PROFIT_SHARE,
                    },
                    {
                        'partner_id': operator.id,
                        'role': 'OPERATOR',
                        'planned_capital_share': CONTRACT_OPERATOR_CAPITAL_USD,
                        'profit_share': CONTRACT_OPERATOR_PROFIT_SHARE,
                    },
                ],
            },
            items=items_payload,
            expenses=expenses_payload,
        )

        for row in plan['capital_rows']:
            raw_name = str(row.get('MIJOZ') or '').strip().upper()
            partner = investor if 'USTOZ' in raw_name else operator
            add_contribution(
                tenant_id=tenant_id,
                procurement_id=procurement.id,
                partner_id=partner.id,
                amount=_money(_dec(row.get('MIQDOR'))),
                currency='USD',
                fx_rate=_dec(row.get('KURS'), str(DEFAULT_DEMO_USD_UZS_RATE)),
                date=_parse_dt(row.get('SANA')),
                notes=f'Excel CAPITAL row {row.get("_row_id")}',
            )

        all_item_ids = list(procurement.items.order_by('id').values_list('id', flat=True))
        received_item_ids = list(
            procurement.items
            .exclude(product_variant=variants[IN_TRANSIT_PRODUCT])
            .order_by('id')
            .values_list('id', flat=True)
        )
        if scenario.use_targeted_customs:
            expense = procurement.expenses.get()
            update_procurement_expense_targets(
                tenant_id=tenant_id,
                procurement_id=procurement.id,
                expense_id=expense.id,
                target_item_ids=received_item_ids,
            )

        pay_procurement_items(
            tenant_id=tenant_id,
            procurement_id=procurement.id,
            item_ids=all_item_ids,
            reason='Excel workflow item payment',
        )
        if scenario.use_targeted_customs:
            pay_procurement_expenses(
                tenant_id=tenant_id,
                procurement_id=procurement.id,
                reason='Excel workflow targeted customs payment',
            )

        receive_plan = get_procurement_receive_plan(
            tenant_id=tenant_id,
            procurement_id=procurement.id,
            item_ids=received_item_ids,
        )
        preview = receive_plan.get('batch_capital_preview') or {}
        if preview.get('status') != 'READY':
            raise CommandError(f'Batch capital preview is not ready: {preview}')
        receive_procurement(
            tenant_id=tenant_id,
            procurement_id=procurement.id,
            destination_warehouse_id=self._warehouse_id(tenant_id, 'Основной склад'),
            item_ids=received_item_ids,
            capital_allocations=[
                {'partner_id': row['partner_id'], 'amount': row['amount']}
                for row in preview.get('partners', [])
            ],
            received_at=opened_at,
        )
        return procurement

    def _capital_by_name(self, rows: list[dict]) -> dict[str, Decimal]:
        result = {'USTOZ': Decimal('0'), 'BEKZOD AKA': Decimal('0')}
        for row in rows:
            name = str(row.get('MIJOZ') or '').strip().upper()
            amount = _dec(row.get('MIQDOR'))
            if 'USTOZ' in name:
                result['USTOZ'] += amount
            elif 'BEKZOD' in name:
                result['BEKZOD AKA'] += amount
        return result

    def _purchase_unit_prices(self, *, scenario: Scenario, purchase_rows: list[dict], plan: dict) -> dict[str, Decimal]:
        if not scenario.use_targeted_customs:
            return self._adjusted_units_to_total(
                rows=purchase_rows,
                target_total=plan['landed_received_total'],
                source_unit=lambda row: _dec(row.get('MAHSULOT NARXI')),
            )
        landed_total = plan['landed_received_total']
        base_total = plan['base_received_total']
        factor = base_total / landed_total
        return self._adjusted_units_to_total(
            rows=purchase_rows,
            target_total=base_total,
            source_unit=lambda row: _dec(row.get('MAHSULOT NARXI')) * factor,
        )

    def _adjusted_units_to_total(self, *, rows: list[dict], target_total: Decimal, source_unit) -> dict[str, Decimal]:
        result = {}
        running = Decimal('0')
        for row in rows[:-1]:
            name = str(row['MAHSULOT']).strip()
            qty = _dec(row.get('SONI'))
            unit_price = _unit(source_unit(row))
            result[name] = unit_price
            running += qty * unit_price
        last = rows[-1]
        last_name = str(last['MAHSULOT']).strip()
        last_qty = _dec(last.get('SONI'))
        result[last_name] = _unit((target_total - running) / last_qty)
        return result

    def _warehouse_id(self, tenant_id: int, name: str) -> int:
        from apps.inventory.models import Warehouse

        return Warehouse.objects.get(tenant_id=tenant_id, name=name).id

    def _transfer_for_sales(self, *, tenant_id: int, procurement, warehouses: dict, sheets: dict, plan: dict, variants: dict) -> None:
        from apps.inventory.models import LotStock
        from apps.inventory.services import transfer_lot_stock

        storage = warehouses['ASOSIY']
        shop = warehouses['DOKON']
        transfer_quantities = defaultdict(Decimal)
        for row in plan['transfer_rows']:
            src = str(row.get('CHIQIM') or '').strip().upper()
            dst = str(row.get('KIRIM') or '').strip().upper()
            if src == 'ASOSIY' and dst == 'DOKON':
                transfer_quantities[str(row['MAHSULOT']).strip()] += _dec(row.get('SONI'))
        for product, qty in plan['extra_transfers'].items():
            transfer_quantities[product] += qty

        for product, qty in sorted(transfer_quantities.items()):
            variant = variants[product]
            remaining = int(qty)
            stocks = (
                LotStock.objects
                .filter(
                    tenant_id=tenant_id,
                    warehouse=storage,
                    lot__product_variant=variant,
                    quantity_remaining__gt=0,
                )
                .select_related('lot')
                .order_by('lot__received_at', 'lot__id')
            )
            for stock in stocks:
                if remaining <= 0:
                    break
                take = min(int(stock.quantity_remaining), remaining)
                transfer_lot_stock(
                    tenant_id=tenant_id,
                    lot=stock.lot,
                    from_warehouse=storage,
                    to_warehouse=shop,
                    quantity=take,
                )
                remaining -= take
            if remaining > 0:
                raise CommandError(f'Cannot transfer {product}: shortage {remaining}.')

    def _replay_sales(
        self,
        *,
        tenant_id: int,
        cashier: User,
        shop,
        cash_accounts: dict,
        customers: dict,
        variants: dict,
        discount_reason_id: int,
        sheets: dict,
    ) -> None:
        from apps.sales.models import Sale, SalePayment
        from apps.sales.services import close_pos_session, create_sale, open_pos_session

        rows = sorted(
            [row for row in sheets.get('SOTUV', []) if row.get('MAHSULOT')],
            key=lambda row: (_parse_dt(row.get('SOTUV SANASI')), int(row.get('_row_id') or 0)),
        )
        rows_by_day = defaultdict(list)
        for row in rows:
            rows_by_day[_parse_dt(row.get('SOTUV SANASI')).date()].append(row)

        for day in sorted(rows_by_day):
            session = open_pos_session(
                tenant_id=tenant_id,
                location_id=shop.id,
                opened_by_id=cashier.id,
                opening_cash=Decimal('0'),
                opening_cash_by_currency={'UZS': '0.00', 'USD': '0.00'},
            )
            for row in rows_by_day[day]:
                name = str(row['MAHSULOT']).strip()
                qty = int(_dec(row.get('JAMI DONA')))
                currency_raw = str(row.get('VALYUTA') or 'SOM').strip().upper()
                currency = 'UZS' if currency_raw == 'SOM' else currency_raw
                unit_raw = _dec(row.get('SOTUV NARXI'))
                fx = _dec(row.get('KURS'), '1')
                unit_price_uzs = _money(unit_raw if currency == 'UZS' else unit_raw * fx)
                account = cash_accounts['KASSA DOLLAR'] if currency == 'USD' else cash_accounts['KASSA SOM']
                create_sale(
                    tenant_id=tenant_id,
                    pos_session_id=session.id,
                    location_id=shop.id,
                    sold_by_id=cashier.id,
                    customer_id=customers.get(str(row.get('MIJOZ') or '').strip()).id if str(row.get('MIJOZ') or '').strip() in customers else None,
                    lines=[{
                        'product_variant_id': variants[name].id,
                        'quantity': qty,
                        'unit_price': unit_price_uzs,
                        'operation_currency': currency,
                        'operation_unit_price': unit_raw if currency == 'USD' else unit_price_uzs,
                        'fx_rate': fx if currency == 'USD' else Decimal('1'),
                        'discount_reason_id': discount_reason_id,
                    }],
                    payments=[{
                        'amount': _money(unit_raw * qty if currency == 'USD' else unit_price_uzs * qty),
                        'currency': currency,
                        'fx_rate': fx if currency == 'USD' else Decimal('1'),
                        'method': SalePayment.Method.CASH,
                        'account_id': account.id,
                    }],
                    date=_parse_dt(row.get('SOTUV SANASI')),
                    notes=(
                        f"Excel SOTUV row {row.get('_row_id')}; "
                        f"original_warehouse={row.get('OMBOR') or 'DOKON'}; customer={row.get('MIJOZ') or ''}"
                    ),
                )
            cash_totals = defaultdict(Decimal)
            for payment in SalePayment.objects.filter(
                sale__tenant_id=tenant_id,
                sale__pos_session=session,
                sale__status=Sale.SaleStatus.COMPLETED,
                role=SalePayment.Role.INCOMING,
                method=SalePayment.Method.CASH,
            ):
                cash_totals[str(payment.currency or 'UZS').upper()] += Decimal(str(payment.amount))
            close_pos_session(
                session=session,
                closed_by_id=cashier.id,
                actual_cash=Decimal('0'),
                actual_cash_by_currency={currency: str(_money(amount)) for currency, amount in cash_totals.items()},
            )
