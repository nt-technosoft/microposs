"""Bootstrap production-friendly baseline data after deploy."""

from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, DiscountReason, Product
from apps.catalog.services import create_product_with_variants
from apps.core.models import Business, Partner
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.models import Account, CashAccount
from apps.inventory.models import Warehouse


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

    def handle(self, *args, **options):
        with transaction.atomic():
            users = self._create_users(options)
            business = self._create_business(options['tenant_name'], users['owner'])
            baseline = self._create_operational_baseline(business, users)
            created_products = self._seed_products(
                business=business,
                category=baseline['category'],
                skip_products=options['skip_products'],
            )

        self.stdout.write(self.style.SUCCESS('Deploy baseline bootstrap complete.'))
        self.stdout.write(f"Business: {business.name} (#{business.id})")
        self.stdout.write('Users:')
        self.stdout.write(f"  admin / {options['admin_password']}")
        self.stdout.write(
            f"  {options['owner_username']} / {options['owner_password']}"
        )
        self.stdout.write(f"  cashier / {options['cashier_password']}")
        self.stdout.write(f"  warehouse / {options['warehouse_password']}")
        self.stdout.write(f"  investor / {options['investor_password']}")
        if options['skip_products']:
            self.stdout.write('Products: skipped')
        else:
            self.stdout.write(f'Products synced: {created_products}')

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
        cash_account = Account.objects.get(tenant_id=business.id, code='1000')
        bank_account = Account.objects.get(tenant_id=business.id, code='1010')

        Warehouse.objects.update_or_create(
            tenant=business,
            name='ASOSIY',
            defaults={
                'kind': Warehouse.WarehouseKind.STORAGE,
                'is_active': True,
            },
        )
        Warehouse.objects.update_or_create(
            tenant=business,
            name='DOKON',
            defaults={
                'kind': Warehouse.WarehouseKind.SHOP,
                'is_active': True,
            },
        )

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

        Partner.objects.update_or_create(
            tenant=business,
            role=Partner.Role.OPERATOR,
            defaults={
                'display_name': 'Бизнес',
                'user': users['owner'],
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

        return {'category': category}

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
