"""Shared test fixtures for vacuum-model test suite (PR-9c)."""

from decimal import Decimal
from django.contrib.auth.models import User
from django.utils import timezone

from apps.catalog.models import Category
from apps.catalog.services import create_product_with_variants
from apps.core.models import Business, BusinessInvestorRelation, Partner
from apps.customers.models import Customer
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.models import CashAccount, Account
from apps.inventory.models import Warehouse
from apps.partnerships.models import Procurement
from apps.partnerships.services import (
    add_contribution,
    open_procurement,
    pay_procurement_expenses,
    pay_procurement_items,
    receive_procurement,
)
from apps.sales.services import open_pos_session
from apps.suppliers.models import Supplier


def build_tenant():
    """Create a minimal tenant with users, partners, warehouses, product, and cash chart."""
    owner = User.objects.create_user(username='t_owner', password='x')
    cashier = User.objects.create_user(username='t_cashier', password='x')
    investor_user = User.objects.create_user(username='t_investor', password='x')

    business = Business.objects.create(
        owner=owner, name='Test Tenant', currency='UZS', is_active=True,
    )
    setup_chart_of_accounts(business.id)
    cash_account = CashAccount.objects.create(
        tenant=business,
        name='Main Cash',
        currency='UZS',
        kind=CashAccount.Kind.CASH,
        linked_account=Account.objects.get(tenant=business, code='1000'),
    )
    card_account = CashAccount.objects.create(
        tenant=business,
        name='Main Card',
        currency='UZS',
        kind=CashAccount.Kind.CARD_TERMINAL,
        linked_account=Account.objects.get(tenant=business, code='1010'),
    )

    operator = Partner.objects.create(
        tenant=business, role=Partner.Role.OPERATOR,
        display_name='Op', user=owner, is_active=True,
    )
    investor = Partner.objects.create(
        tenant=business, role=Partner.Role.INVESTOR,
        display_name='Inv', user=investor_user, is_active=True,
    )
    BusinessInvestorRelation.objects.create(
        tenant=business,
        partner=investor,
        status=BusinessInvestorRelation.Status.ACTIVE,
        source=BusinessInvestorRelation.Source.MANUAL,
        created_by=owner,
    )

    store = Warehouse.objects.create(
        tenant=business, name='Store', kind=Warehouse.WarehouseKind.SHOP,
        is_active=True,
    )
    storage = Warehouse.objects.create(
        tenant=business, name='Storage', kind=Warehouse.WarehouseKind.STORAGE,
        is_active=True,
    )

    supplier = Supplier.objects.create(
        tenant=business, name='Test Supplier', is_active=True,
    )
    customer = Customer.objects.create(
        tenant=business, name='Test Customer', is_active=True,
    )

    category = Category.objects.create(tenant=business, name='Cat', sort_order=1)
    product = create_product_with_variants(
        tenant_id=business.id, name='P', category_id=category.id,
        base_price='240000.00', pricing_mode='EDITABLE', variant_data=None,
    )
    variant = product.variants.filter(is_active=True).first()

    return {
        'business': business, 'owner': owner, 'cashier': cashier,
        'operator': operator, 'investor': investor,
        'store': store, 'storage': storage,
        'supplier': supplier, 'customer': customer,
        'product': product, 'variant': variant,
        'cash_account': cash_account, 'card_account': card_account,
    }


def seed_received_procurement(ctx, *, qty=50, unit_usd=10, customs_usd=50):
    """
    70/30 investor/operator, mudaraba 4/7 → profit 40/60.
    Contributes exactly enough, drains balance, receives into storage.
    fx_rate = 12000 UZS/USD.
    Returns (procurement, landed_per_unit).
    """
    fx = Decimal('12000')
    usd = 'USD'
    total_usd = Decimal(qty) * Decimal(unit_usd) + Decimal(customs_usd)
    inv_amt = (total_usd * Decimal('0.7')).quantize(Decimal('0.01'))
    op_amt = total_usd - inv_amt

    proc = open_procurement(
        tenant_id=ctx['business'].id,
        procurement_type=Procurement.Type.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
        contract={
            'mudaraba_ratio': Decimal('0.571429'),
            'planned_budget': total_usd,
            'currency': usd,
            'partners': [
                {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                 'planned_capital_share': inv_amt, 'profit_share': Decimal('0.4')},
                {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                 'planned_capital_share': op_amt, 'profit_share': Decimal('0.6')},
            ],
        },
        items=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': Decimal(qty),
            'unit_purchase_price': Decimal(unit_usd),
            'currency': usd, 'fx_rate': fx,
        }],
        expenses=[{
            'expense_type': 'CUSTOMS',
            'amount': Decimal(customs_usd),
            'currency': usd, 'fx_rate': fx,
        }],
    )
    add_contribution(
        tenant_id=ctx['business'].id, procurement_id=proc.id,
        partner_id=ctx['investor'].id, amount=inv_amt, currency=usd, fx_rate=fx,
    )
    add_contribution(
        tenant_id=ctx['business'].id, procurement_id=proc.id,
        partner_id=ctx['operator'].id, amount=op_amt, currency=usd, fx_rate=fx,
    )
    pay_procurement_items(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
    )
    pay_procurement_expenses(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
    )
    proc = receive_procurement(
        tenant_id=ctx['business'].id, procurement_id=proc.id,
        destination_warehouse_id=ctx['storage'].id,
    )
    from apps.inventory.models import Lot
    lot = Lot.objects.get(procurement_item__procurement=proc)
    return proc, lot


def open_session(ctx):
    return open_pos_session(
        tenant_id=ctx['business'].id,
        location_id=ctx['storage'].id,
        opened_by_id=ctx['cashier'].id,
        opening_cash=Decimal('0'),
    )
