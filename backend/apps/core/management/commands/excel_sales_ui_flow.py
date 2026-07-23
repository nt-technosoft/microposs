"""Replay Excel sales through the same API flow used by the POS UI."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.management.commands.excel_workflow_audit import (
    SNAPSHOT_DEFAULT,
    _dec,
    _money,
    _parse_dt,
    resolve_snapshot_path,
)


class Command(BaseCommand):
    help = 'Create Excel SOTUV sales via POS API endpoints: open session, checkout, close session.'

    def add_arguments(self, parser):
        parser.add_argument('--snapshot', default=SNAPSHOT_DEFAULT)
        parser.add_argument('--tenant-name', default='MicroPOS Real Cost Audit')
        parser.add_argument('--username', default='owner')
        parser.add_argument('--shop-name', default='Основной магазин')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument(
            '--allow-existing-sales',
            action='store_true',
            help='Allow replay when the tenant already has sales. Idempotency still prevents duplicate row ids.',
        )

    def handle(self, *args, **options):
        if bool(options['dry_run']) == bool(options['apply']):
            raise CommandError('Choose exactly one: --dry-run or --apply.')

        from apps.catalog.models import Product
        from apps.core.models import Business
        from apps.customers.models import Customer
        from apps.inventory.models import LotStock, Warehouse
        from apps.sales.models import Sale, SalePayment
        from apps.sales.views import PosSessionViewSet, SaleViewSet

        snapshot_path = resolve_snapshot_path(options['snapshot'])
        if not snapshot_path.exists():
            raise CommandError(f'Snapshot not found: {snapshot_path}')
        sheets = json.loads(snapshot_path.read_text(encoding='utf-8')).get('sheets') or {}
        rows = sorted(
            [row for row in sheets.get('SOTUV', []) if row.get('MAHSULOT')],
            key=lambda row: (_parse_dt(row.get('SOTUV SANASI')), int(row.get('_row_id') or 0)),
        )
        if not rows:
            raise CommandError('No SOTUV rows found in snapshot.')

        business = Business.objects.get(name=options['tenant_name'])
        tenant_id = business.id
        user = User.objects.get(username=options['username'])
        shop = Warehouse.objects.get(tenant=business, name=options['shop_name'])

        existing_sales = Sale.objects.filter(tenant=business).count()
        if existing_sales and options['apply'] and not options['allow_existing_sales']:
            raise CommandError(
                f'{business.name}: tenant already has {existing_sales} sales. '
                'Pass --allow-existing-sales only if you intentionally want to continue.'
            )

        product_names = sorted({str(row['MAHSULOT']).strip() for row in rows})
        products = {
            product.name: product
            for product in Product.objects.filter(tenant=business, name__in=product_names).prefetch_related('variants')
        }
        variants = {}
        missing = []
        for name in product_names:
            variant = products.get(name).variants.filter(is_active=True).first() if name in products else None
            if variant is None:
                missing.append(name)
            else:
                variants[name] = variant
        if missing:
            raise CommandError(f'Missing product variants: {missing}')

        required = defaultdict(Decimal)
        for row in rows:
            required[str(row['MAHSULOT']).strip()] += _dec(row.get('JAMI DONA'))
        available = defaultdict(Decimal)
        stocks = (
            LotStock.objects
            .filter(
                tenant=business,
                warehouse=shop,
                lot__product_variant__in=variants.values(),
                quantity_remaining__gt=0,
            )
            .select_related('lot__product_variant__product')
        )
        for stock in stocks:
            available[stock.lot.product_variant.product.name] += Decimal(str(stock.quantity_remaining))
        shortages = {
            name: required_qty - available.get(name, Decimal('0'))
            for name, required_qty in required.items()
            if available.get(name, Decimal('0')) < required_qty
        }
        if shortages:
            raise CommandError(f'Not enough shop stock for Excel sales: {shortages}')

        customers = {
            customer.name: customer
            for customer in Customer.objects.filter(tenant=business)
        }

        rows_by_day = defaultdict(list)
        for row in rows:
            rows_by_day[_parse_dt(row.get('SOTUV SANASI')).date()].append(row)

        currency_count = defaultdict(int)
        currency_total = defaultdict(Decimal)
        for row in rows:
            currency = self._sale_currency(row)
            qty = _dec(row.get('JAMI DONA'))
            amount = self._native_unit_price(row, currency) * qty
            currency_count[currency] += 1
            currency_total[currency] += _money(amount)

        self.stdout.write(f'Tenant: {business.name} #{tenant_id}')
        self.stdout.write(f'User flow actor: {user.username}')
        self.stdout.write(f'Shop: {shop.name} #{shop.id}')
        self.stdout.write(f'Sales rows: {len(rows)} across {len(rows_by_day)} POS sessions')
        if existing_sales:
            self.stdout.write(f'Existing tenant sales: {existing_sales}')
        for currency in sorted(currency_total):
            self.stdout.write(
                f'  {currency}: {currency_count[currency]} rows, '
                f'{_money(currency_total[currency])}'
            )
        if options['dry_run']:
            return

        factory = APIRequestFactory()
        PosSessionViewSet.throttle_classes = []
        SaleViewSet.throttle_classes = []
        open_view = PosSessionViewSet.as_view({'post': 'open_session'})
        close_view = PosSessionViewSet.as_view({'post': 'close_session'})
        sale_view = SaleViewSet.as_view({'post': 'create'})

        with transaction.atomic():
            for day, day_rows in sorted(rows_by_day.items()):
                session_response = self._post(
                    factory=factory,
                    view=open_view,
                    path='/api/v1/sales/sessions/open/',
                    user=user,
                    tenant_id=tenant_id,
                    data={
                        'location_id': shop.id,
                        'opening_cash': '0.00',
                        'opening_cash_by_currency': {'UZS': '0.00', 'USD': '0.00'},
                    },
                )
                session_id = int(session_response.data['id'])
                cash_totals = defaultdict(Decimal)

                for row in day_rows:
                    name = str(row['MAHSULOT']).strip()
                    qty = int(_dec(row.get('JAMI DONA')))
                    currency = self._sale_currency(row)
                    unit_raw = self._native_unit_price(row, currency)
                    fx = _dec(row.get('KURS'), '1')
                    operation_unit_price = _money(unit_raw)
                    functional_unit_price = _money(unit_raw if currency == 'UZS' else unit_raw * fx)
                    payment_amount = _money(unit_raw * qty)
                    customer_name = str(row.get('MIJOZ') or '').strip()

                    payload = {
                        'client_request_id': str(uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f'excel-sotuv:{tenant_id}:{row.get("_row_id")}',
                        )),
                        'pos_session_id': session_id,
                        'location_id': shop.id,
                        'date': _parse_dt(row.get('SOTUV SANASI')).isoformat(),
                        'customer_id': customers[customer_name].id if customer_name in customers else None,
                        'lines': [{
                            'product_variant_id': variants[name].id,
                            'quantity': qty,
                            'unit_price': str(functional_unit_price),
                            'operation_currency': currency,
                            'operation_unit_price': str(operation_unit_price),
                            'fx_rate': str(fx if currency == 'USD' else Decimal('1')),
                        }],
                        'payments': [{
                            'amount': str(payment_amount),
                            'currency': currency,
                            'fx_rate': str(fx if currency == 'USD' else Decimal('1')),
                            'method': SalePayment.Method.CASH,
                        }],
                        'notes': (
                            f"Excel SOTUV row {row.get('_row_id')}; "
                            f"original_warehouse={row.get('OMBOR') or 'DOKON'}; "
                            f"customer={customer_name}"
                        ),
                    }
                    self._post(
                        factory=factory,
                        view=sale_view,
                        path='/api/v1/sales/sales/',
                        user=user,
                        tenant_id=tenant_id,
                        data=payload,
                    )
                    cash_totals[currency] += payment_amount

                self._post(
                    factory=factory,
                    view=close_view,
                    path=f'/api/v1/sales/sessions/{session_id}/close/',
                    user=user,
                    tenant_id=tenant_id,
                    data={
                        'actual_cash': '0.00',
                        'actual_cash_by_currency': {
                            currency: str(_money(amount))
                            for currency, amount in cash_totals.items()
                        },
                    },
                    pk=session_id,
                )

        self.stdout.write(self.style.SUCCESS(f'Created Excel UI-flow sales: {len(rows)}'))

    def _post(self, *, factory, view, path, user, tenant_id: int, data: dict, **view_kwargs):
        request = factory.post(path, data, format='json', HTTP_X_TENANT_ID=str(tenant_id))
        force_authenticate(request, user=user)
        request.tenant_id = tenant_id
        response = view(request, **view_kwargs)
        if response.status_code >= 400:
            raise CommandError(f'API flow failed at {path}: {response.status_code} {response.data}')
        return response

    @staticmethod
    def _sale_currency(row: dict) -> str:
        raw = str(row.get('VALYUTA') or 'SOM').strip().upper()
        return 'UZS' if raw == 'SOM' else raw

    @staticmethod
    def _native_unit_price(row: dict, currency: str) -> Decimal:
        value = _dec(row.get('SOTUV NARXI'))
        return value if currency == 'USD' else _money(value)
