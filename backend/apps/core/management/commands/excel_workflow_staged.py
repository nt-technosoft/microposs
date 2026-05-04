"""Run the Excel workflow audit in explicit manual-check stages."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.management.safety import require_debug_or_confirmation
from apps.core.management.commands.excel_workflow_audit import (
    Command as WorkflowEngine,
    SCENARIOS,
    SNAPSHOT_DEFAULT,
    IN_TRANSIT_PRODUCT,
)


class Command(BaseCommand):
    help = 'Stage-by-stage Excel workflow replay for manual audit checkpoints.'

    def add_arguments(self, parser):
        parser.add_argument('--snapshot', default=SNAPSHOT_DEFAULT)
        parser.add_argument(
            '--stage',
            required=True,
            choices=['baseline', 'procurements', 'transfers', 'sales', 'final', 'all'],
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--wipe', action='store_true')
        parser.add_argument('--strict-gaps', action='store_true')
        parser.add_argument(
            '--confirm-production-apply',
            action='store_true',
            help='Allow staged Excel workflow mutations when DEBUG=False.',
        )

    def handle(self, *args, **options):
        if bool(options['dry_run']) == bool(options['apply']):
            raise CommandError('Choose exactly one: --dry-run or --apply.')
        if options['apply']:
            require_debug_or_confirmation(
                command_name='excel_workflow_staged',
                confirmed=options['confirm_production_apply'],
                flag_name='--confirm-production-apply',
                action='this command mutates the staged Excel workflow data',
            )

        stage = options['stage']
        if options['apply'] and stage in {'baseline', 'all'} and not options['wipe']:
            raise CommandError(f'--stage {stage} requires --wipe.')
        if options['apply'] and stage not in {'baseline', 'all'} and options['wipe']:
            raise CommandError('--wipe is allowed only for baseline/all stages.')

        engine = WorkflowEngine()
        engine.stdout = self.stdout
        engine.stderr = self.stderr
        engine.style = self.style

        snapshot_path = Path(options['snapshot'])
        if not snapshot_path.is_absolute():
            snapshot_path = Path.cwd() / snapshot_path
        if not snapshot_path.exists():
            raise CommandError(f'Snapshot not found: {snapshot_path}')

        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        sheets = snapshot.get('sheets') or {}
        plan = engine._build_plan(sheets)

        engine._print_plan(plan, strict_gaps=options['strict_gaps'])
        self._print_stage_plan(stage)

        if plan['blockers']:
            raise CommandError('Workflow has blockers; fix them before apply.')
        if options['strict_gaps'] and plan['warnings']:
            raise CommandError('Workflow has warnings and --strict-gaps is enabled.')
        if options['dry_run']:
            return

        if stage == 'baseline':
            with transaction.atomic():
                engine._wipe_database()
                users = engine._create_users()
                for scenario in SCENARIOS:
                    self._create_baseline(engine, scenario, sheets, users)
        elif stage == 'procurements':
            with transaction.atomic():
                for scenario in SCENARIOS:
                    ctx = self._load_context(scenario, sheets)
                    if ctx['procurement_exists']:
                        raise CommandError(f'{scenario.tenant_name}: procurement already exists.')
                    engine._create_procurement(
                        scenario=scenario,
                        tenant_id=ctx['tenant_id'],
                        supplier_id=ctx['supplier'].id,
                        operator=ctx['operator'],
                        investor=ctx['investor'],
                        sheets=sheets,
                        plan=plan,
                        variants=ctx['variants'],
                    )
        elif stage == 'transfers':
            with transaction.atomic():
                for scenario in SCENARIOS:
                    ctx = self._load_context(scenario, sheets, require_procurement=True)
                    if ctx['has_transfers']:
                        raise CommandError(f'{scenario.tenant_name}: transfers already exist.')
                    engine._transfer_for_sales(
                        tenant_id=ctx['tenant_id'],
                        procurement=ctx['procurement'],
                        warehouses=ctx['warehouses'],
                        sheets=sheets,
                        plan=plan,
                        variants=ctx['variants'],
                    )
        elif stage == 'sales':
            with transaction.atomic():
                for scenario in SCENARIOS:
                    ctx = self._load_context(scenario, sheets, require_procurement=True)
                    if ctx['has_sales']:
                        raise CommandError(f'{scenario.tenant_name}: sales already exist.')
                    engine._replay_sales(
                        tenant_id=ctx['tenant_id'],
                        cashier=ctx['cashier'],
                        shop=ctx['warehouses']['DOKON'],
                        cash_accounts=ctx['cash_accounts'],
                        customers=ctx['customers'],
                        variants=ctx['variants'],
                        discount_reason_id=ctx['discount_reason'].id,
                        sheets=sheets,
                    )
            engine._refresh_financial_aggregates()
        elif stage == 'final':
            engine._refresh_financial_aggregates()
            self._print_final_summary()
        elif stage == 'all':
            with transaction.atomic():
                engine._wipe_database()
                users = engine._create_users()
                for scenario in SCENARIOS:
                    ctx = self._create_baseline(engine, scenario, sheets, users)
                    procurement = engine._create_procurement(
                        scenario=scenario,
                        tenant_id=ctx['tenant_id'],
                        supplier_id=ctx['supplier'].id,
                        operator=ctx['operator'],
                        investor=ctx['investor'],
                        sheets=sheets,
                        plan=plan,
                        variants=ctx['variants'],
                    )
                    engine._transfer_for_sales(
                        tenant_id=ctx['tenant_id'],
                        procurement=procurement,
                        warehouses=ctx['warehouses'],
                        sheets=sheets,
                        plan=plan,
                        variants=ctx['variants'],
                    )
                    engine._replay_sales(
                        tenant_id=ctx['tenant_id'],
                        cashier=ctx['cashier'],
                        shop=ctx['warehouses']['DOKON'],
                        cash_accounts=ctx['cash_accounts'],
                        customers=ctx['customers'],
                        variants=ctx['variants'],
                        discount_reason_id=ctx['discount_reason'].id,
                        sheets=sheets,
                    )
            engine._refresh_financial_aggregates()

        self.stdout.write(self.style.SUCCESS(f'Excel workflow stage applied: {stage}'))

    def _print_stage_plan(self, stage: str) -> None:
        labels = {
            'baseline': 'wipe + users + two businesses + reference data/products',
            'procurements': 'two partner procurements + payments + partial receive',
            'transfers': 'stock transfers from warehouse to shop',
            'sales': 'POS sessions + sales rows from Excel',
            'final': 'refresh aggregates and print summary',
            'all': 'baseline + procurements + transfers + sales + aggregates',
        }
        self.stdout.write(f'  stage: {stage} — {labels[stage]}')

    def _create_baseline(self, engine, scenario, sheets, users):
        from apps.catalog.models import Category, DiscountReason
        from apps.catalog.services import create_product_with_variants
        from apps.core.models import Business, BusinessInvestorRelation, Partner
        from apps.finance.chart_of_accounts import setup_chart_of_accounts
        from apps.finance.models import Account, CashAccount, ExchangeRate
        from apps.inventory.models import Warehouse
        from apps.investors.models import Investor
        from apps.suppliers.models import Supplier
        from apps.core.demo_constants import DEFAULT_DEMO_USD_UZS_RATE
        from django.utils import timezone
        from decimal import Decimal

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
                tenant=business,
                name='Основной склад',
                kind=Warehouse.WarehouseKind.STORAGE,
                is_active=True,
            ),
            'DOKON': Warehouse.objects.create(
                tenant=business,
                name='Основной магазин',
                kind=Warehouse.WarehouseKind.SHOP,
                is_active=True,
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
            tenant=business,
            name='Торг',
            is_default=True,
            is_active=True,
        )
        supplier = Supplier.objects.create(tenant=business, name='Excel поставщик', is_active=True)
        customers = engine._create_customers(tenant_id, sheets)
        variants = engine._create_products(
            tenant_id=tenant_id,
            category_id=category.id,
            sheets=sheets,
            create_product_with_variants=create_product_with_variants,
        )
        self.stdout.write(self.style.SUCCESS(f'  {scenario.tenant_name}: baseline applied'))
        return {
            'tenant_id': tenant_id,
            'business': business,
            'warehouses': warehouses,
            'cash_accounts': cash_accounts,
            'operator': operator,
            'investor': investor,
            'supplier': supplier,
            'customers': customers,
            'variants': variants,
            'discount_reason': discount_reason,
            'cashier': users['cashier'],
        }

    def _load_context(self, scenario, sheets, *, require_procurement: bool = False):
        from django.contrib.auth.models import User
        from apps.catalog.models import DiscountReason, Product
        from apps.core.models import Business, Partner
        from apps.customers.models import Customer
        from apps.finance.models import CashAccount
        from apps.inventory.models import StockMovement, Warehouse
        from apps.partnerships.models import Procurement
        from apps.sales.models import Sale
        from apps.suppliers.models import Supplier

        business = Business.objects.get(name=scenario.tenant_name)
        tenant_id = business.id
        warehouses = {
            'ASOSIY': Warehouse.objects.get(tenant=business, name='Основной склад'),
            'DOKON': Warehouse.objects.get(tenant=business, name='Основной магазин'),
        }
        cash_accounts = {
            account.name: account
            for account in CashAccount.objects.filter(tenant=business)
        }
        variants = {}
        product_names = {
            str(row['MAHSULOT']).strip()
            for row in sheets.get('SOTIB OLISH', [])
            if row.get('MAHSULOT')
        }
        product_names.add(IN_TRANSIT_PRODUCT)
        for product in Product.objects.filter(tenant=business, name__in=product_names).prefetch_related('variants'):
            variants[product.name] = product.variants.filter(is_active=True).first()
        missing = sorted(name for name in product_names if name not in variants or variants[name] is None)
        if missing:
            raise CommandError(f'{scenario.tenant_name}: missing product variants: {missing}')

        procurement = (
            Procurement.objects
            .filter(tenant=business, procurement_type=Procurement.Type.PARTNERSHIP)
            .order_by('id')
            .first()
        )
        if require_procurement and procurement is None:
            raise CommandError(f'{scenario.tenant_name}: procurement stage has not been applied.')

        return {
            'tenant_id': tenant_id,
            'business': business,
            'warehouses': warehouses,
            'cash_accounts': cash_accounts,
            'operator': Partner.objects.get(tenant=business, role=Partner.Role.OPERATOR),
            'investor': Partner.objects.get(tenant=business, display_name=scenario.investor_display),
            'supplier': Supplier.objects.get(tenant=business, name='Excel поставщик'),
            'customers': {
                customer.name: customer
                for customer in Customer.objects.filter(tenant=business)
            },
            'variants': variants,
            'discount_reason': DiscountReason.objects.get(tenant=business, name='Торг'),
            'cashier': User.objects.get(username='cashier'),
            'procurement': procurement,
            'procurement_exists': procurement is not None,
            'has_transfers': StockMovement.objects.filter(
                tenant=business,
                movement_type=StockMovement.MovementType.TRANSFER,
            ).exists(),
            'has_sales': Sale.objects.filter(tenant=business).exists(),
        }

    def _print_final_summary(self) -> None:
        from django.db.models import Count, Sum
        from apps.core.models import Business
        from apps.sales.models import Sale, SalePayment

        self.stdout.write('Final workflow summary:')
        for business in Business.objects.order_by('id'):
            sales = Sale.objects.filter(tenant=business)
            payments = (
                SalePayment.objects
                .filter(tenant=business, role=SalePayment.Role.INCOMING)
                .values('currency')
                .annotate(count=Count('id'), total=Sum('amount'))
                .order_by('currency')
            )
            self.stdout.write(
                f'  {business.id}. {business.name}: '
                f'{sales.count()} sales, revenue_uzs={sales.aggregate(total=Sum("total_amount"))["total"] or 0}'
            )
            for row in payments:
                self.stdout.write(f'     {row["currency"]}: {row["total"]} ({row["count"]} payments)')
