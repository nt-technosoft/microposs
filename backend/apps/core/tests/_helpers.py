"""Shared test fixtures for vacuum-model test suite (PR-9c).

Test suite canon (T-8.1 audit):
- Tag-presence checks (assertTrue/exists) verify correct domain labelling (pocket/flow/partner).
  They are semantic, not purely structural, but they do NOT verify amounts.
- Amount/GL/conservation checks (assertEqual with Decimal, venture_conservation, _assert_current)
  verify economic correctness. Both kinds are required.
- Tests that only check structure without any numeric assertion are candidates for pruning:
  either add an economic assert (e.g. negative_position_uzs > 0) or delete if fully covered.
- Property-based scenarios live in test_e18_property_conservation.py; add new operation
  types there first before writing one-off example tests.
"""

from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.utils import timezone

from apps.catalog.models import Category
from apps.catalog.services import create_product_with_variants
from apps.core.models import Business, BusinessInvestorRelation, Partner
from apps.customers.models import Customer
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.finance.models import CashAccount, Account
from apps.finance.models import ExchangeRate
from apps.finance.fx_rates import upsert_exchange_rate
from apps.inventory.models import Warehouse, LotStock
from apps.inventory.services import transfer_lot_stock
from apps.partnerships.models import Procurement
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
)
from apps.sales.services import open_pos_session
from apps.suppliers.models import Supplier


def build_tenant():
    """Create a minimal tenant with users, partners, warehouses, product, and cash chart."""
    owner = User.objects.create_user(username='t_owner', password='x')
    cashier = User.objects.create_user(username='t_cashier', password='x')
    investor_user = User.objects.create_user(username='t_investor', password='x')

    owner_group, _ = Group.objects.get_or_create(name='owner')
    cashier_group, _ = Group.objects.get_or_create(name='cashier')
    investor_group, _ = Group.objects.get_or_create(name='investor')
    owner.groups.add(owner_group)
    cashier.groups.add(cashier_group)
    investor_user.groups.add(investor_group)

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

    upsert_exchange_rate(
        tenant_id=ctx['business'].id,
        base_currency=usd,
        quote_currency='UZS',
        rate_date=timezone.localdate(),
        rate=fx,
        source=ExchangeRate.Source.MANUAL,
        is_manual=True,
        notes='test fixture',
    )

    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
    )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='CREATE_INVESTMENT_AGREEMENT',
        payload={'payload': {
            'mudaraba_ratio': Decimal('0.571429'),
            'planned_budget': total_usd,
            'currency': usd,
            'partners': [
                {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                 'planned_capital_share': inv_amt, 'profit_share': Decimal('0.4')},
                {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                 'planned_capital_share': op_amt, 'profit_share': Decimal('0.6')},
            ],
        }},
    )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {
            'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal(qty),
                'unit_purchase_price': Decimal(unit_usd),
                'currency': usd,
                'fx_rate': fx,
            }],
            'expenses': [{
                'expense_type': 'CUSTOMS',
                'amount': Decimal(customs_usd),
                'currency': usd,
                'fx_rate': fx,
            }],
        }},
    )
    for partner_id, amount in (
        (ctx['investor'].id, inv_amt),
        (ctx['operator'].id, op_amt),
    ):
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=proc,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': partner_id,
                'amount': amount,
                'currency': usd,
                'fx_rate': fx,
                'cash_account_id': ctx['card_account'].id,
            }},
        )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='ALLOCATE_CAPITAL',
        payload={'payload': {'allocations': [
            {'partner_id': ctx['investor'].id, 'amount': inv_amt, 'currency': usd, 'fx_rate': fx},
            {'partner_id': ctx['operator'].id, 'amount': op_amt, 'currency': usd, 'fx_rate': fx},
        ]}},
    )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='RECEIVE_BATCH',
        payload={'payload': {'warehouse_id': ctx['storage'].id}},
    )
    from apps.inventory.models import Lot
    lot = Lot.objects.get(procurement_item__procurement=proc)
    return proc, lot


def open_session(ctx):
    storage_stocks = list(
        LotStock.objects
        .filter(
            tenant_id=ctx['business'].id,
            warehouse=ctx['storage'],
            quantity_remaining__gt=0,
        )
        .select_related('lot')
    )
    for stock in storage_stocks:
        transfer_lot_stock(
            tenant_id=ctx['business'].id,
            lot=stock.lot,
            from_warehouse=ctx['storage'],
            to_warehouse=ctx['store'],
            quantity=stock.quantity_remaining,
        )

    return open_pos_session(
        tenant_id=ctx['business'].id,
        location_id=ctx['store'].id,
        opened_by_id=ctx['cashier'].id,
        opening_cash=Decimal('0'),
    )
