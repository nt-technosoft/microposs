"""Bootstrap deterministic demo data for local development."""

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Category, DiscountReason, Product
from apps.catalog.services import create_product_with_variants
from apps.core.models import Business
from apps.customers.models import Customer
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.models import CashFlowSummary, DailySummary
from apps.inventory.models import Location, Lot, Receipt, ReceiptLine
from apps.inventory.services import confirm_receipt
from apps.investors.models import Investor, InvestorContract, InvestorProfitRecord, InvestorSummary
from apps.sales.models import PosSession, Sale
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

    def handle(self, *args, **options):
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

            store, _ = Location.objects.get_or_create(
                tenant=business,
                name='Main Store',
                defaults={
                    'location_type': Location.LocationType.STORE,
                    'address': 'Demo storefront',
                    'is_active': True,
                },
            )
            warehouse, _ = Location.objects.get_or_create(
                tenant=business,
                name='Main Warehouse',
                defaults={
                    'location_type': Location.LocationType.WAREHOUSE,
                    'address': 'Demo warehouse',
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
                    pricing_mode='DEFAULT_EDITABLE',
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
                    pricing_mode='DEFAULT_EDITABLE',
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

            Supplier.objects.get_or_create(
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

            investor_profile, _ = Investor.objects.get_or_create(
                tenant=business,
                user=investor_user,
                defaults={
                    'name': 'Demo Investor',
                    'phone': '+998900000003',
                    'is_active': True,
                },
            )
            contract = InvestorContract.objects.filter(
                tenant=business,
                investor=investor_profile,
                status=InvestorContract.ContractStatus.ACTIVE,
            ).order_by('id').first()
            if contract is None:
                contract = InvestorContract.objects.create(
                    tenant=business,
                    investor=investor_profile,
                    contract_type=InvestorContract.ContractType.MUDARABA,
                    default_profit_ratio=Decimal('0.4000'),
                    start_date=timezone.localdate(),
                    status=InvestorContract.ContractStatus.ACTIVE,
                    notes='Seeded investor contract',
                )

            receipt = Receipt.objects.filter(
                tenant=business,
                notes='Demo seeded receipt',
            ).first()
            if receipt is None and variant is not None:
                receipt = Receipt.objects.create(
                    tenant=business,
                    receipt_type=Receipt.ReceiptType.BUSINESS_OWNED,
                    status=Receipt.ReceiptStatus.DRAFT,
                    date=timezone.now(),
                    destination=store,
                    notes='Demo seeded receipt',
                )
                ReceiptLine.objects.create(
                    tenant=business,
                    receipt=receipt,
                    product_variant=variant,
                    quantity=30,
                    cost_per_unit=Decimal('45000.00'),
                )
                receipt = confirm_receipt(receipt)

            lot = (
                Lot.objects
                .filter(tenant=business, product_variant=variant, quantity_remaining__gt=0)
                .order_by('id')
                .first()
            )

            session = PosSession.objects.filter(
                tenant=business,
                location=store,
                status=PosSession.SessionStatus.OPEN,
            ).order_by('-opened_at').first()
            if session is None:
                session = open_pos_session(
                    tenant_id=business.id,
                    location_id=store.id,
                    opened_by_id=cashier_user.id,
                    opening_cash=Decimal('500000.00'),
                )

            sale = Sale.objects.filter(
                tenant=business,
                notes='Demo seeded sale',
            ).order_by('id').first()
            if sale is None and lot is not None and variant is not None:
                sale = create_sale(
                    tenant_id=business.id,
                    pos_session_id=session.id,
                    sold_by_id=cashier_user.id,
                    payment_method='cash',
                    customer_id=customer.id,
                    lines=[{
                        'product_variant_id': variant.id,
                        'quantity': 1,
                        'unit_price': '65000.00',
                        'lot_id': lot.id,
                    }],
                    notes='Demo seeded sale',
                )

            today = timezone.localdate()
            sale_amount = sale.total_amount if sale else Decimal('0')
            sale_cogs = sale.total_cogs if sale else Decimal('0')
            gross_profit = self._money(sale_amount - sale_cogs)

            DailySummary.objects.update_or_create(
                tenant=business,
                date=today,
                defaults={
                    'total_revenue': sale_amount,
                    'total_cogs': sale_cogs,
                    'gross_profit': gross_profit,
                    'investor_share': self._money(gross_profit * Decimal('0.40')),
                    'net_business_profit': self._money(gross_profit * Decimal('0.60')),
                    'total_sales_count': 1 if sale else 0,
                    'total_returns_count': 0,
                    'total_writeoffs': Decimal('0.00'),
                },
            )
            CashFlowSummary.objects.update_or_create(
                tenant=business,
                date=today,
                defaults={
                    'cash_in_sales': sale_amount,
                    'cash_in_debt_payments': Decimal('0.00'),
                    'cash_in_investor': Decimal('0.00'),
                    'cash_out_purchases': Decimal('0.00'),
                    'cash_out_supplier_payments': Decimal('0.00'),
                    'cash_out_investor_payments': Decimal('0.00'),
                    'net_cash_flow': sale_amount,
                },
            )

            seeded_profit = InvestorProfitRecord.objects.filter(
                tenant=business,
                contract=contract,
                description='Demo seeded profit record',
            ).first()
            if seeded_profit is None:
                InvestorProfitRecord.objects.create(
                    tenant=business,
                    contract=contract,
                    investor=investor_profile,
                    record_type=InvestorProfitRecord.RecordType.PROFIT,
                    amount=self._money(gross_profit * Decimal('0.40')) if sale else Decimal('0.00'),
                    source_type='seed',
                    source_id=0,
                    lot=lot,
                    description='Demo seeded profit record',
                )

            InvestorSummary.objects.update_or_create(
                tenant=business,
                investor=investor_profile,
                contract=contract,
                defaults={
                    'total_invested': Decimal('1000000.00'),
                    'in_stock_value': Decimal('900000.00'),
                    'total_sold_revenue': sale_amount,
                    'total_profit': self._money(gross_profit * Decimal('0.40')),
                    'total_losses': Decimal('0.00'),
                    'turnover_ratio': Decimal('1.15'),
                    'business_owes': self._money(Decimal('1000000.00') + gross_profit * Decimal('0.40')),
                },
            )

        self.stdout.write(self.style.SUCCESS('Demo bootstrap completed.'))
        self.stdout.write('Users:')
        self.stdout.write(f"  admin / {options['admin_password']} (superuser)")
        self.stdout.write(f"  owner / {options['owner_password']} (owner role)")
        self.stdout.write(f"  cashier / {options['cashier_password']} (cashier role)")
        self.stdout.write(f"  warehouse / {options['warehouse_password']} (warehouse role)")
        self.stdout.write(f"  investor / {options['investor_password']} (investor role)")
        self.stdout.write(f'Tenant: {tenant_name}')
