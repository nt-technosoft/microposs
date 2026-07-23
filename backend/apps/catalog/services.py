"""
Catalog business logic — product/variant creation, category template application,
product-supplier link maintenance.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    Product, ProductVariant, VariantAttributeValue,
    Category, CategoryAttribute, CategoryCharacteristicTemplate, AttributeValue,
    ProductCharacteristic, ProductSupplier,
)

_ZERO = Decimal('0')


def _ensure_variant_sku(variant: ProductVariant) -> None:
    """Assign deterministic SKU when it was omitted at creation time."""
    if (variant.sku or '').strip():
        return
    variant.sku = f"P{variant.product_id}-V{variant.id}"
    variant.save(update_fields=['sku', 'updated_at'])


def create_product_with_variants(
    tenant_id: int,
    name: str,
    category_id: int | None,
    base_price: str | None,
    pricing_mode: str | None,
    description: str = '',
    variant_data: list[dict] | None = None,
    photo=None,
) -> Product:
    """
    Create a product and optionally generate variants from attribute combinations.

    variant_data format:
    [
        {
            "attribute_value_ids": [1, 5],  # e.g., Size=M, Color=Red
            "price": "45000.00" or None,    # override price
            "sku": "SKU-001" or ""
        },
        ...
    ]
    """
    with transaction.atomic():
        category = None
        if category_id:
            category = Category.objects.get(pk=category_id, tenant_id=tenant_id)

        resolved_pricing_mode = pricing_mode or (
            category.default_pricing_mode if category else 'EDITABLE'
        )

        product = Product.objects.create(
            tenant_id=tenant_id,
            name=name,
            category=category,
            base_price=base_price,
            pricing_mode=resolved_pricing_mode,
            description=description,
            photo=photo,
            has_variants=bool(variant_data and len(variant_data) > 1),
        )

        # Apply category templates on create (only once, not dynamic inheritance).
        apply_category_template_to_product(
            product,
            apply_pricing_mode=pricing_mode is None,
            apply_characteristics=True,
        )

        if variant_data:
            for vd in variant_data:
                variant = ProductVariant.objects.create(
                    tenant_id=tenant_id,
                    product=product,
                    sku=vd.get('sku', ''),
                    price=vd.get('price'),
                )
                _ensure_variant_sku(variant)
                for av_id in vd.get('attribute_value_ids', []):
                    VariantAttributeValue.objects.create(
                        tenant_id=tenant_id,
                        variant=variant,
                        attribute_value_id=av_id,
                    )
        else:
            # No variants — create a single default variant
            variant = ProductVariant.objects.create(
                tenant_id=tenant_id,
                product=product,
                sku='',
                price=None,
            )
            _ensure_variant_sku(variant)

        return product


def apply_category_template_to_product(
    product: Product,
    apply_pricing_mode: bool = True,
    apply_characteristics: bool = True,
) -> None:
    """
    Apply category's default_pricing_mode to a product.
    Called on product creation when category is set.
    """
    if not product.category:
        return

    update_fields: list[str] = []
    if apply_pricing_mode:
        product.pricing_mode = product.category.default_pricing_mode
        update_fields.append('pricing_mode')

    if update_fields:
        product.save(update_fields=[*update_fields, 'updated_at'])

    if apply_characteristics:
        characteristic_templates = list(
            CategoryCharacteristicTemplate.objects.filter(
                tenant_id=product.tenant_id,
                category=product.category,
            ).order_by('sort_order', 'id')
        )
        if not characteristic_templates:
            return

        names = [tpl.name for tpl in characteristic_templates]
        ProductCharacteristic.objects.filter(
            tenant_id=product.tenant_id,
            product=product,
            name__in=names,
        ).delete()
        ProductCharacteristic.objects.bulk_create([
            ProductCharacteristic(
                tenant_id=product.tenant_id,
                product=product,
                name=tpl.name,
                value=tpl.default_value,
            )
            for tpl in characteristic_templates
        ])


def apply_category_settings_to_products(
    category: Category,
    apply_to_existing: bool = False,
    apply_pricing_mode: bool = True,
    apply_characteristics: bool = True,
) -> int:
    """
    Apply category settings to products.
    Returns number of updated products.

    If apply_to_existing=False, only affects new products (no-op here).
    If apply_to_existing=True, mass-update all products in category.
    """
    if not apply_to_existing:
        return 0

    products = Product.objects.filter(
        category=category,
        tenant_id=category.tenant_id,
    )
    updated_count = products.count()

    if updated_count == 0:
        return 0

    if apply_pricing_mode:
        products.update(pricing_mode=category.default_pricing_mode)

    if apply_characteristics:
        characteristic_templates = list(
            CategoryCharacteristicTemplate.objects.filter(
                tenant_id=category.tenant_id,
                category=category,
            ).order_by('sort_order', 'id')
        )
        template_names = [tpl.name for tpl in characteristic_templates]
        if template_names:
            for product in products.only('id', 'tenant_id'):
                ProductCharacteristic.objects.filter(
                    tenant_id=category.tenant_id,
                    product=product,
                    name__in=template_names,
                ).delete()
                ProductCharacteristic.objects.bulk_create([
                    ProductCharacteristic(
                        tenant_id=category.tenant_id,
                        product=product,
                        name=tpl.name,
                        value=tpl.default_value,
                    )
                    for tpl in characteristic_templates
                ])

    return updated_count


def generate_variant_combinations(
    tenant_id: int,
    product: Product,
    attribute_ids: list[int],
) -> list[ProductVariant]:
    """
    Auto-generate all combinations of attribute values.
    E.g., Size [S,M,L] x Color [Red,Blue] = 6 variants.
    """
    from itertools import product as itertools_product

    value_groups = []
    for attr_id in attribute_ids:
        values = list(
            AttributeValue.objects.filter(
                attribute_id=attr_id,
                tenant_id=tenant_id,
            ).order_by('sort_order')
        )
        if values:
            value_groups.append(values)

    if not value_groups:
        return []

    variants = []
    with transaction.atomic():
        for combo in itertools_product(*value_groups):
            variant = ProductVariant.objects.create(
                tenant_id=tenant_id,
                product=product,
                sku='',
                price=None,
            )
            _ensure_variant_sku(variant)
            for attr_value in combo:
                VariantAttributeValue.objects.create(
                    tenant_id=tenant_id,
                    variant=variant,
                    attribute_value=attr_value,
                )
            variants.append(variant)

        if len(variants) > 1:
            product.has_variants = True
            product.save(update_fields=['has_variants', 'updated_at'])

    return variants


def generate_variant_combinations_from_value_groups(
    tenant_id: int,
    product: Product,
    value_groups: list[list[AttributeValue]],
) -> list[ProductVariant]:
    """
    Generate variants from explicit value groups selected in UI.
    Example: [[Size:S, Size:M], [Color:Black, Color:White]]
    """
    from itertools import product as itertools_product

    normalized_groups = [group for group in value_groups if group]
    if not normalized_groups:
        return []

    variants = []
    with transaction.atomic():
        for combo in itertools_product(*normalized_groups):
            variant = ProductVariant.objects.create(
                tenant_id=tenant_id,
                product=product,
                sku='',
                price=None,
            )
            _ensure_variant_sku(variant)
            for attr_value in combo:
                VariantAttributeValue.objects.create(
                    tenant_id=tenant_id,
                    variant=variant,
                    attribute_value=attr_value,
                )
            variants.append(variant)

        if variants:
            product.has_variants = True
            product.save(update_fields=['has_variants', 'updated_at'])

    return variants


# =========================================================================
# E02 — Product–Supplier links
# =========================================================================


def upsert_product_supplier_link(
    *,
    tenant_id: int,
    product_variant_id: int,
    supplier_id: int,
    unit_price: Decimal,
    currency: str,
    quantity: Decimal,
    received_at=None,
    fx_rate: Decimal | None = None,
) -> ProductSupplier:
    """
    Create or update the ProductSupplier link between a variant and a supplier
    after a confirmed receipt of `quantity` units at `unit_price` (in `currency`).

    Aggregates:
      - last_received_at = received_at (always overwritten)
      - last_unit_price = unit_price (always overwritten)
      - last_currency  = currency
      - total_received_quantity += quantity
      - total_received_value_uzs += quantity × unit_price × fx_rate
      - total_procurements_count += 1
    """
    if quantity is None or Decimal(str(quantity)) <= _ZERO:
        raise ValueError('quantity must be > 0 for upsert.')

    received_at = received_at or timezone.now()
    fx_rate = Decimal(str(fx_rate or 1))
    unit_price = Decimal(str(unit_price or 0))
    quantity = Decimal(str(quantity))
    value_uzs = (unit_price * quantity * fx_rate).quantize(Decimal('0.01'))

    with transaction.atomic():
        link, created = ProductSupplier.objects.select_for_update().get_or_create(
            product_variant_id=product_variant_id,
            supplier_id=supplier_id,
            defaults={
                'tenant_id': tenant_id,
                'last_received_at': received_at,
                'last_unit_price': unit_price,
                'last_currency': str(currency or 'UZS').upper(),
                'total_received_quantity': quantity,
                'total_received_value_uzs': value_uzs,
                'total_procurements_count': 1,
            },
        )
        if not created:
            link.last_received_at = received_at
            link.last_unit_price = unit_price
            link.last_currency = str(currency or 'UZS').upper()
            link.total_received_quantity = Decimal(
                str(link.total_received_quantity)
            ) + quantity
            link.total_received_value_uzs = Decimal(
                str(link.total_received_value_uzs)
            ) + value_uzs
            link.total_procurements_count = (link.total_procurements_count or 0) + 1
            link.save(update_fields=[
                'last_received_at', 'last_unit_price', 'last_currency',
                'total_received_quantity', 'total_received_value_uzs',
                'total_procurements_count', 'updated_at',
            ])
        return link


def quick_create_product(
    *,
    tenant_id: int,
    name: str,
    category_id: int | None = None,
    baseline_price=None,
    supplier_id: int | None = None,
    received_at=None,
) -> ProductVariant:
    """
    Minimal product creator for inline use in the intake form.

    Creates a Product + single default ProductVariant (same as
    create_product_with_variants without variant_data) and — if `supplier_id`
    is given — establishes a ProductSupplier link as if a 0-quantity link
    placeholder, so subsequent receipts naturally upsert it.

    Note: returns the ProductVariant (not the Product). Caller usually needs
    the variant to put it into a ProcurementItem.
    """
    name = (name or '').strip()
    if not name:
        raise ValueError('Product name is required.')

    received_at = received_at or timezone.now()

    with transaction.atomic():
        category = None
        if category_id:
            category = Category.objects.get(pk=category_id, tenant_id=tenant_id)

        product = Product.objects.create(
            tenant_id=tenant_id,
            name=name,
            category=category,
            base_price=baseline_price,
            pricing_mode=(
                category.default_pricing_mode if category else 'EDITABLE'
            ),
            description='',
            has_variants=False,
        )

        # Apply category template (consistent with create_product_with_variants)
        apply_category_template_to_product(
            product,
            apply_pricing_mode=False,  # pricing mode already set from category default
            apply_characteristics=True,
        )

        variant = ProductVariant.objects.create(
            tenant_id=tenant_id,
            product=product,
            sku='',
            price=None,
        )
        _ensure_variant_sku(variant)

        # Optional supplier link: create with 0 totals — first receipt will
        # populate `last_*` fields and increment counters via upsert.
        if supplier_id is not None:
            ProductSupplier.objects.get_or_create(
                product_variant=variant,
                supplier_id=supplier_id,
                defaults={
                    'tenant_id': tenant_id,
                    'last_received_at': received_at,
                    'last_unit_price': baseline_price or _ZERO,
                    'last_currency': 'UZS',
                    'total_received_quantity': _ZERO,
                    'total_received_value_uzs': _ZERO,
                    'total_procurements_count': 0,
                },
            )

        return variant
