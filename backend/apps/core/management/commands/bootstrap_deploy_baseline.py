"""Bootstrap production-friendly baseline data after deploy."""

from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, DiscountReason, Product
from apps.catalog.services import create_product_with_variants
from apps.core.demo_constants import DEFAULT_DEMO_USD_UZS_RATE
from apps.core.management.safety import require_debug_or_confirmation
from apps.core.models import Business, BusinessInvestorRelation, Partner
from apps.customers.models import Customer
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.models import Account, CashAccount, ExchangeRate
from apps.inventory.models import Lot, Warehouse
from apps.inventory.services import transfer_lot_stock
from apps.investors.models import Investor
from apps.partnerships.models import Procurement
from apps.sales.models import PosSession, SalePayment
from apps.sales.services import create_sale, open_pos_session
from apps.suppliers.models import Supplier


DEFAULT_PRODUCTS = {
    '120x180': Decimal('130000'),
    '2 talik 50x80': Decimal('90000'),
    '2 talik 60x90': Decimal('110000'),
    '32 PCS': Decimal('590000'),
    '80x160': Decimal('85000'),
    'Atirgul 60x60': Decimal('25000'),
    'Gul 50x80': Decimal('30000'),
    'Welcome 60x90': Decimal('35000'),
}

BASELINE_PROCUREMENT_REQUEST_ID = UUID('00000000-0000-0000-0000-000000000101')
BASELINE_SALE_REQUEST_ID = UUID('00000000-0000-0000-0000-000000000102')
BASELINE_PROCUREMENT_NOTES = 'Baseline partnership procurement'
BASELINE_SALE_NOTES = 'Baseline demo sale'


class Command(BaseCommand):
    help = (
        'Create/update baseline users, business, operational entities, and '
        'starter catalog for a deployed environment.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tenant-name', default='MicroPOS Workflow')
        parser.add_argument('--admin-password', default='Admin123!')
        parser.add_argument('--owner-password', default='Owner123!')
        parser.add_argument('--cashier-password', default='Cashier123!')
        parser.add_argument('--warehouse-password', default='Warehouse123!')
        parser.add_argument('--investor-password', default='Investor123!')
        parser.add_argument('--owner-username', default='owner')
        parser.add_argument('--skip-products', action='store_true')
        parser.add_argument('--skip-sample-flow', action='store_true')
        parser.add_argument(
            '--confirm-production-bootstrap',
            action='store_true',
            help='Allow baseline user/password bootstrap when DEBUG=False.',
        )

    def handle(self, *args, **options):
        require_debug_or_confirmation(
            command_name='bootstrap_deploy_baseline',
            confirmed=options['confirm_production_bootstrap'],
            flag_name='--confirm-production-bootstrap',
            action='this command creates users and sets account passwords',
        )

        with transaction.atomic():
            users = self._create_users(options)
            business = self._create_business(options['tenant_name'], users['owner'])
            baseline = self._create_operational_baseline(business, users)
            created_products = self._seed_products(
                business=business,
                category=baseline['category'],
                skip_products=options['skip_products'],
            )
            sample_flow_seeded = self._seed_sample_flow(
                business=business,
                baseline=baseline,
                users=users,
                skip_products=options['skip_products'],
                skip_sample_flow=options['skip_sample_flow'],
            )

        self.stdout.write(self.style.SUCCESS('Deploy baseline bootstrap complete.'))
        self.stdout.write(f"Business: {business.name} (#{business.id})")
        self.stdout.write('Users:')
        if settings.DEBUG:
            self.stdout.write(f"  admin / {options['admin_password']}")
            self.stdout.write(
                f"  {options['owner_username']} / {options['owner_password']}"
            )
            self.stdout.write(f"  cashier / {options['cashier_password']}")
            self.stdout.write(f"  warehouse / {options['warehouse_password']}")
            self.stdout.write(f"  investor / {options['investor_password']}")
        else:
            self.stdout.write('  admin, owner, cashier, warehouse, investor')
            self.stdout.write('  Passwords are not printed while DEBUG=False.')
        if options['skip_products']:
            self.stdout.write('Products: skipped')
        else:
            self.stdout.write(f'Products synced: {created_products}')
        if options['skip_sample_flow']:
            self.stdout.write('Sample flow: skipped')
        else:
            self.stdout.write(
                f"Sample flow: {'seeded' if sample_flow_seeded else 'unchanged'}"
            )

    def _create_users(self, options) -> dict[str, User]:
        groups = {
            name: Group.objects.get_or_create(name=name)[0]
            for name in ('owner', 'cashier', 'warehouse', 'investor')
        }
        return {
            'admin': self._upsert_user(
                username='admin',
                email='admin@local.dev',
                password=options['admin_password'],
                groups=[groups['owner']],
                is_superuser=True,
            ),
            'owner': self._upsert_user(
                username=options['owner_username'],
                email='owner@local.dev',
                password=options['owner_password'],
                groups=[groups['owner']],
            ),
            'cashier': self._upsert_user(
                username='cashier',
                email='cashier@local.dev',
                password=options['cashier_password'],
                groups=[groups['cashier']],
            ),
            'warehouse': self._upsert_user(
                username='warehouse',
                email='warehouse@local.dev',
                password=options['warehouse_password'],
                groups=[groups['warehouse']],
            ),
            'investor': self._upsert_user(
                username='investor',
                email='investor@local.dev',
                password=options['investor_password'],
                groups=[groups['investor']],
            ),
        }

    def _upsert_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        groups: list[Group],
        is_superuser: bool = False,
    ) -> User:
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'email': email},
        )
        user.email = email
        user.is_active = True
        user.is_staff = is_superuser
        user.is_superuser = is_superuser
        user.set_password(password)
        user.save()
        user.groups.set(groups)
        return user

    def _create_business(self, tenant_name: str, owner: User) -> Business:
        business, created = Business.objects.get_or_create(
            owner=owner,
            defaults={
                'name': tenant_name,
                'currency': 'UZS',
                'is_active': True,
            },
        )
        update_fields: list[str] = []
        if not created and business.name != tenant_name:
            business.name = tenant_name
            update_fields.append('name')
        if not business.is_active:
            business.is_active = True
            update_fields.append('is_active')
        if business.currency != 'UZS':
            business.currency = 'UZS'
            update_fields.append('currency')
        if update_fields:
            business.save(update_fields=[*update_fields, 'updated_at'])
        return business

    def _create_operational_baseline(
        self,
        business: Business,
        users: dict[str, User],
    ) -> dict[str, object]:
        setup_chart_of_accounts(business.id)
        ExchangeRate.objects.get_or_create(
            tenant=business,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            defaults={
                'rate': DEFAULT_DEMO_USD_UZS_RATE,
                'source': ExchangeRate.Source.MANUAL,
                'is_manual': True,
                'notes': 'Deploy baseline seed rate',
                'raw_payload': {},
                'fetched_at': timezone.now(),
            },
        )
        cash_account = Account.objects.get(tenant_id=business.id, code='1000')
        bank_account = Account.objects.get(tenant_id=business.id, code='1010')

        storage, _ = Warehouse.objects.update_or_create(
            tenant=business,
            name='Основной склад',
            defaults={
                'kind': Warehouse.WarehouseKind.STORAGE,
                'is_active': True,
            },
        )
        store, _ = Warehouse.objects.update_or_create(
            tenant=business,
            name='Основной магазин',
            defaults={
                'kind': Warehouse.WarehouseKind.SHOP,
                'is_active': True,
            },
        )

        accounts: dict[str, CashAccount] = {}
        for name, currency, kind, linked_account in [
            ('KASSA SOM', 'UZS', CashAccount.Kind.CASH, cash_account),
            ('KASSA DOLLAR', 'USD', CashAccount.Kind.CASH, bank_account),
            ('PLASTIK SOM', 'UZS', CashAccount.Kind.CARD_TERMINAL, bank_account),
        ]:
            account, _ = CashAccount.objects.update_or_create(
                tenant=business,
                name=name,
                defaults={
                    'currency': currency,
                    'kind': kind,
                    'is_active': True,
                    'linked_account': linked_account,
                },
            )
            if account.balance is None:
                account.balance = Decimal('0')
                account.save(update_fields=['balance', 'updated_at'])
            accounts[name] = account

        operator, _ = Partner.objects.update_or_create(
            tenant=business,
            role=Partner.Role.OPERATOR,
            defaults={
                'display_name': 'Бизнес',
                'user': users['owner'],
                'is_active': True,
            },
        )
        investor_partner, _ = Partner.objects.update_or_create(
            tenant=business,
            role=Partner.Role.INVESTOR,
            user=users['investor'],
            defaults={
                'display_name': 'Устоз (инвестор)',
                'is_active': True,
            },
        )
        if investor_partner.display_name != 'Устоз (инвестор)' or not investor_partner.is_active:
            investor_partner.display_name = 'Устоз (инвестор)'
            investor_partner.is_active = True
            investor_partner.save(update_fields=['display_name', 'is_active', 'updated_at'])

        BusinessInvestorRelation.objects.update_or_create(
            tenant=business,
            partner=investor_partner,
            defaults={
                'status': BusinessInvestorRelation.Status.ACTIVE,
                'source': BusinessInvestorRelation.Source.MANUAL,
                'created_by': users['owner'],
                'notes': 'Baseline bootstrap investor access',
            },
        )
        investor_profile, _ = Investor.objects.update_or_create(
            tenant=business,
            user=users['investor'],
            defaults={
                'name': 'Устоз',
                'email': users['investor'].email,
                'is_active': True,
            },
        )

        supplier, _ = Supplier.objects.update_or_create(
            tenant=business,
            name='Baseline Supplier',
            defaults={
                'contact_person': 'Supplier Contact',
                'phone': '+998900000001',
                'is_active': True,
            },
        )
        customer, _ = Customer.objects.update_or_create(
            tenant=business,
            name='Baseline Customer',
            defaults={
                'phone': '+998900000002',
                'is_active': True,
            },
        )

        category, _ = Category.objects.update_or_create(
            tenant=business,
            name='Ковры',
            defaults={'sort_order': 1},
        )
        DiscountReason.objects.update_or_create(
            tenant=business,
            name='Торг',
            defaults={'is_default': True, 'is_active': True},
        )

        return {
            'category': category,
            'storage': storage,
            'store': store,
            'cash_accounts': accounts,
            'operator': operator,
            'investor_partner': investor_partner,
            'investor_profile': investor_profile,
            'supplier': supplier,
            'customer': customer,
        }

    def _seed_products(
        self,
        *,
        business: Business,
        category: Category,
        skip_products: bool,
    ) -> int:
        if skip_products:
            return 0

        synced = 0
        for name, base_price in DEFAULT_PRODUCTS.items():
            product = Product.objects.filter(
                tenant=business,
                name=name,
            ).first()
            if product:
                update_fields: list[str] = []
                if product.category_id != category.id:
                    product.category = category
                    update_fields.append('category')
                if product.base_price != base_price:
                    product.base_price = base_price
                    update_fields.append('base_price')
                if product.pricing_mode != 'EDITABLE':
                    product.pricing_mode = 'EDITABLE'
                    update_fields.append('pricing_mode')
                if not product.is_active:
                    product.is_active = True
                    update_fields.append('is_active')
                if update_fields:
                    product.save(update_fields=[*update_fields, 'updated_at'])
            else:
                create_product_with_variants(
                    tenant_id=business.id,
                    name=name,
                    category_id=category.id,
                    base_price=str(base_price),
                    pricing_mode='EDITABLE',
                    variant_data=None,
                )
            synced += 1
        return synced

    def _seed_sample_flow(
        self,
        *,
        business: Business,
        baseline: dict[str, object],
        users: dict[str, User],
        skip_products: bool,
        skip_sample_flow: bool,
    ) -> bool:
        if skip_products or skip_sample_flow:
            return False

        variant = (
            Product.objects.filter(tenant=business, is_active=True)
            .order_by('id')
            .values_list('variants__id', flat=True)
            .first()
        )
        if variant is None:
            return False

        procurement = Procurement.objects.filter(
            tenant=business,
            client_request_id=BASELINE_PROCUREMENT_REQUEST_ID,
        ).first()

        if procurement is None:
            # TODO E07 Phase D: rewrite using InvestmentAgreement + ProcurementWorkspace API.
            # Legacy open_procurement/add_contribution/receive_procurement removed in E08 T-1.4.
            return False

        lot = Lot.objects.filter(
            tenant=business,
            procurement_item__procurement=procurement,
        ).order_by('id').first()
        if lot is None:
            return False

        source_stock = lot.stocks.filter(
            warehouse=baseline['storage'],
            quantity_remaining__gt=0,
        ).first()
        if source_stock is not None:
            transfer_lot_stock(
                tenant_id=business.id,
                lot=lot,
                from_warehouse=baseline['storage'],
                to_warehouse=baseline['store'],
                quantity=source_stock.quantity_remaining,
            )

        session = (
            PosSession.objects.filter(
                tenant=business,
                location=baseline['store'],
                status=PosSession.SessionStatus.OPEN,
            )
            .order_by('id')
            .first()
        )
        if session is None:
            session = open_pos_session(
                tenant_id=business.id,
                location_id=baseline['store'].id,
                opened_by_id=users['cashier'].id,
                opening_cash=Decimal('0'),
            )

        create_sale(
            tenant_id=business.id,
            pos_session_id=session.id,
            location_id=baseline['store'].id,
            sold_by_id=users['cashier'].id,
            customer_id=baseline['customer'].id,
            lines=[{
                'product_variant_id': variant,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': baseline['cash_accounts']['KASSA SOM'].id,
            }],
            client_request_id=BASELINE_SALE_REQUEST_ID,
            notes=BASELINE_SALE_NOTES,
        )
        return True
