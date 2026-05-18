"""Bootstrap deterministic demo data for local development."""

from decimal import Decimal, ROUND_HALF_UP

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
from apps.finance.models import CashAccount, ExchangeRate
from apps.inventory.models import Warehouse
from apps.partnerships.models import Procurement
from apps.sales.services import create_sale, open_pos_session
from apps.suppliers.models import Supplier


class Command(BaseCommand):
    help = (
        'Create or update local demo users, tenant, and sample records for '
        'frontend smoke testing.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tenant-name', default='MicroPOS Demo')
        parser.add_argument('--admin-password', default='Admin123!')
        parser.add_argument('--owner-password', default='Owner123!')
        parser.add_argument('--cashier-password', default='Cashier123!')
        parser.add_argument('--warehouse-password', default='Warehouse123!')
        parser.add_argument('--investor-password', default='Investor123!')
        parser.add_argument(
            '--confirm-production-demo',
            action='store_true',
            help='Allow demo bootstrap mutations when DEBUG=False.',
        )

    def _upsert_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        groups: list[Group],
        is_staff: bool = False,
        is_superuser: bool = False,
    ) -> User:
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'email': email},
        )
        user.email = email
        user.is_staff = is_staff or is_superuser
        user.is_superuser = is_superuser
        user.is_active = True
        user.set_password(password)
        user.save()

        user.groups.clear()
        for group in groups:
            user.groups.add(group)

        return user

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def _seed_partnership_flow(
        self,
        *,
        business,
        operator,
        investor,
        supplier,
        customer,
        variant,
        store,
        warehouse,
        cashier_user,
    ):
        """
        TODO E07 Phase D: rewrite using InvestmentAgreement + ProcurementWorkspace API.
        The legacy open_procurement/add_contribution/receive_procurement functions were
        removed in E08 Phase 1 (T-1.4).
        """
        raise NotImplementedError('Partnership demo flow requires E07 Phase D rewrite.')

    def handle(self, *args, **options):
        require_debug_or_confirmation(
            command_name='bootstrap_demo',
            confirmed=options['confirm_production_demo'],
            flag_name='--confirm-production-demo',
            action='this command creates demo users and sets account passwords',
        )

        tenant_name = options['tenant_name']

        with transaction.atomic():
            role_groups = {}
            for role_name in ('owner', 'cashier', 'warehouse', 'investor'):
                group, _ = Group.objects.get_or_create(name=role_name)
                role_groups[role_name] = group

            admin_user = self._upsert_user(
                username='admin',
                email='admin@local.dev',
                password=options['admin_password'],
                groups=[role_groups['owner']],
                is_superuser=True,
            )
            owner_user = self._upsert_user(
                username='owner',
                email='owner@local.dev',
                password=options['owner_password'],
                groups=[role_groups['owner']],
            )
            cashier_user = self._upsert_user(
                username='cashier',
                email='cashier@local.dev',
                password=options['cashier_password'],
                groups=[role_groups['cashier']],
            )
            warehouse_user = self._upsert_user(
                username='warehouse',
                email='warehouse@local.dev',
                password=options['warehouse_password'],
                groups=[role_groups['warehouse']],
            )
            investor_user = self._upsert_user(
                username='investor',
                email='investor@local.dev',
                password=options['investor_password'],
                groups=[role_groups['investor']],
            )

            business, _ = Business.objects.get_or_create(
                owner=owner_user,
                name=tenant_name,
                defaults={
                    'currency': 'UZS',
                    'is_active': True,
                },
            )
            if not business.is_active:
                business.is_active = True
                business.save(update_fields=['is_active', 'updated_at'])

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
                    'notes': 'Local demo seed rate',
                    'raw_payload': {},
                    'fetched_at': timezone.now(),
                },
            )

            store, _ = Warehouse.objects.get_or_create(
                tenant=business,
                name='Основной магазин',
                defaults={
                    'kind': Warehouse.WarehouseKind.SHOP,
                    'address': 'Торговая точка',
                    'is_active': True,
                },
            )
            warehouse, _ = Warehouse.objects.get_or_create(
                tenant=business,
                name='Основной склад',
                defaults={
                    'kind': Warehouse.WarehouseKind.STORAGE,
                    'address': 'Склад',
                    'is_active': True,
                },
            )

            category, _ = Category.objects.get_or_create(
                tenant=business,
                name='Demo Category',
                defaults={
                    'sort_order': 1,
                },
            )

            product = Product.objects.filter(
                tenant=business,
                name='Demo Product',
            ).first()
            if product is None:
                product = create_product_with_variants(
                    tenant_id=business.id,
                    name='Demo Product',
                    category_id=category.id,
                    base_price='65000.00',
                    pricing_mode='EDITABLE',
                    description='Seeded product for smoke tests',
                    variant_data=None,
                )
            variant = product.variants.filter(is_active=True).order_by('id').first()
            if variant is None:
                variant = create_product_with_variants(
                    tenant_id=business.id,
                    name='Demo Product (Auto Variant)',
                    category_id=category.id,
                    base_price='65000.00',
                    pricing_mode='EDITABLE',
                    description='Auto-created fallback product',
                    variant_data=None,
                ).variants.filter(is_active=True).first()

            discount_reason = (
                DiscountReason.objects
                .filter(tenant=business, name='Торг')
                .order_by('id')
                .first()
            )
            if discount_reason is None:
                DiscountReason.objects.create(
                    tenant=business,
                    name='Торг',
                    is_default=True,
                    is_active=True,
                )
            else:
                needs_update = False
                if not discount_reason.is_default:
                    discount_reason.is_default = True
                    needs_update = True
                if not discount_reason.is_active:
                    discount_reason.is_active = True
                    needs_update = True
                if needs_update:
                    discount_reason.save(update_fields=['is_default', 'is_active', 'updated_at'])

            supplier, _ = Supplier.objects.get_or_create(
                tenant=business,
                name='Demo Supplier',
                defaults={
                    'contact_person': 'Supplier Contact',
                    'phone': '+998900000001',
                    'is_active': True,
                },
            )
            customer, _ = Customer.objects.get_or_create(
                tenant=business,
                name='Demo Customer',
                defaults={
                    'phone': '+998900000002',
                    'is_active': True,
                },
            )

            # ─── Partners ─────────────────────────────────────────────────────
            operator, _ = Partner.objects.get_or_create(
                tenant=business,
                role=Partner.Role.OPERATOR,
                display_name='Бекзод (оператор)',
                defaults={'user': owner_user, 'is_active': True},
            )
            investor, _ = Partner.objects.get_or_create(
                tenant=business,
                role=Partner.Role.INVESTOR,
                display_name='Устоз (инвестор)',
                defaults={'user': investor_user, 'is_active': True},
            )
            BusinessInvestorRelation.objects.get_or_create(
                tenant=business,
                partner=investor,
                defaults={
                    'status': BusinessInvestorRelation.Status.ACTIVE,
                    'source': BusinessInvestorRelation.Source.MANUAL,
                    'created_by': owner_user,
                },
            )

            # ─── Cash accounts ────────────────────────────────────────────────
            kassa_som, _ = CashAccount.objects.get_or_create(
                tenant=business,
                name='KASSA_SOM',
                defaults={
                    'currency': 'UZS',
                    'kind': CashAccount.Kind.CASH,
                    'balance': Decimal('0'),
                    'is_active': True,
                },
            )
            CashAccount.objects.get_or_create(
                tenant=business,
                name='KASSA_DOLLAR',
                defaults={
                    'currency': 'USD',
                    'kind': CashAccount.Kind.CASH,
                    'balance': Decimal('0'),
                    'is_active': True,
                },
            )
            CashAccount.objects.get_or_create(
                tenant=business,
                name='PLASTIK_SOM',
                defaults={
                    'currency': 'UZS',
                    'kind': CashAccount.Kind.CARD_TERMINAL,
                    'balance': Decimal('0'),
                    'is_active': True,
                },
            )

            # ─── Procurement → Sale demo (idempotent: skip if already seeded) ─
            existing_demo = Procurement.objects.filter(
                tenant=business,
                procurement_type=Procurement.Type.PARTNERSHIP,
            ).first()
            if existing_demo is None:
                self._seed_partnership_flow(
                    business=business,
                    operator=operator,
                    investor=investor,
                    supplier=supplier,
                    customer=customer,
                    variant=variant,
                    store=store,
                    warehouse=warehouse,
                    cashier_user=cashier_user,
                )

        self.stdout.write(self.style.SUCCESS('Demo bootstrap completed.'))
        self.stdout.write('Users:')
        if settings.DEBUG:
            self.stdout.write(f"  admin / {options['admin_password']} (superuser)")
            self.stdout.write(f"  owner / {options['owner_password']} (owner role)")
            self.stdout.write(f"  cashier / {options['cashier_password']} (cashier role)")
            self.stdout.write(f"  warehouse / {options['warehouse_password']} (warehouse role)")
            self.stdout.write(f"  investor / {options['investor_password']} (investor role)")
        else:
            self.stdout.write('  admin, owner, cashier, warehouse, investor')
            self.stdout.write('  Passwords are not printed while DEBUG=False.')
        self.stdout.write(f'Tenant: {tenant_name}')
