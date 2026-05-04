"""Reset local database to a minimal workflow-test baseline."""

from decimal import Decimal

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.catalog.models import DiscountReason
from apps.core.management.safety import require_debug_or_confirmation
from apps.core.models import Business, BusinessInvestorRelation, Partner
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.models import Account, CashAccount
from apps.inventory.models import Warehouse
from apps.investors.models import Investor


class Command(BaseCommand):
    help = (
        'Clear business data and create only baseline users, tenant, cash '
        'accounts, warehouses, and the owner/operator partner.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tenant-name', default='MicroPOS Workflow')
        parser.add_argument('--admin-password', default='Admin123!')
        parser.add_argument('--owner-password', default='Owner123!')
        parser.add_argument('--cashier-password', default='Cashier123!')
        parser.add_argument('--warehouse-password', default='Warehouse123!')
        parser.add_argument('--investor-password', default='Investor123!')
        parser.add_argument(
            '--confirm-production-reset',
            action='store_true',
            help='Allow workflow demo reset when DEBUG=False.',
        )

    def handle(self, *args, **options):
        require_debug_or_confirmation(
            command_name='reset_workflow_demo',
            confirmed=options['confirm_production_reset'],
            flag_name='--confirm-production-reset',
            action='this command truncates business data and resets users',
        )

        with transaction.atomic():
            self._wipe_business_data()
            users = self._create_users(options)
            business = self._create_business(options['tenant_name'], users['owner'])
            self._create_operational_baseline(business, users)

        self.stdout.write(self.style.SUCCESS('Workflow baseline reset complete.'))
        self.stdout.write(f"Tenant: {business.name} (#{business.id})")
        self.stdout.write('Users:')
        if settings.DEBUG:
            self.stdout.write(f"  admin / {options['admin_password']} (superuser)")
            self.stdout.write(f"  owner / {options['owner_password']} (owner)")
            self.stdout.write(f"  cashier / {options['cashier_password']} (cashier)")
            self.stdout.write(f"  warehouse / {options['warehouse_password']} (warehouse)")
            self.stdout.write(
                f"  investor / {options['investor_password']} "
                "(linked investor)"
            )
        else:
            self.stdout.write('  admin, owner, cashier, warehouse, investor')
            self.stdout.write('  Passwords are not printed while DEBUG=False.')

    def _wipe_business_data(self) -> None:
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
                username='owner',
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
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        user.is_active = True
        user.is_staff = is_superuser
        user.is_superuser = is_superuser
        user.save(update_fields=['is_active', 'is_staff', 'is_superuser'])
        user.groups.set(groups)
        return user

    def _create_business(self, tenant_name: str, owner: User) -> Business:
        return Business.objects.create(
            owner=owner,
            name=tenant_name,
            currency='UZS',
            is_active=True,
        )

    def _create_operational_baseline(
        self,
        business: Business,
        users: dict[str, User],
    ) -> None:
        setup_chart_of_accounts(business.id)
        cash_account = Account.objects.get(tenant_id=business.id, code='1000')
        bank_account = Account.objects.get(tenant_id=business.id, code='1010')

        Warehouse.objects.create(
            tenant=business,
            name='Основной склад',
            kind=Warehouse.WarehouseKind.STORAGE,
            is_active=True,
        )
        Warehouse.objects.create(
            tenant=business,
            name='Основной магазин',
            kind=Warehouse.WarehouseKind.SHOP,
            is_active=True,
        )

        for name, currency, kind, linked_account in [
            ('KASSA SOM', 'UZS', CashAccount.Kind.CASH, cash_account),
            ('KASSA DOLLAR', 'USD', CashAccount.Kind.CASH, bank_account),
            ('PLASTIK SOM', 'UZS', CashAccount.Kind.CARD_TERMINAL, bank_account),
        ]:
            CashAccount.objects.create(
                tenant=business,
                name=name,
                currency=currency,
                kind=kind,
                balance=Decimal('0'),
                is_active=True,
                linked_account=linked_account,
            )

        Partner.objects.create(
            tenant=business,
            role=Partner.Role.OPERATOR,
            display_name='Owner operator',
            user=users['owner'],
            is_active=True,
        )
        investor_partner = Partner.objects.create(
            tenant=business,
            role=Partner.Role.INVESTOR,
            display_name='Устоз',
            user=users['investor'],
            is_active=True,
        )
        BusinessInvestorRelation.objects.create(
            tenant=business,
            partner=investor_partner,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
            created_by=users['owner'],
            notes='Workflow audit baseline investor access',
        )
        Investor.objects.create(
            tenant=business,
            user=users['investor'],
            name='Устоз',
            email=users['investor'].email,
            is_active=True,
        )

        DiscountReason.objects.create(
            tenant=business,
            name='Торг',
            is_default=True,
            is_active=True,
        )
