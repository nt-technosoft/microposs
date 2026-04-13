"""
Catalog business logic — product/variant creation, category template application.
"""

from django.db import transaction
from .models import (
    Product, ProductVariant, VariantAttributeValue,
    Category, CategoryAttribute, AttributeValue,
)


def create_product_with_variants(
    tenant_id: int,
    name: str,
    category_id: int | None,
    base_price: str | None,
    pricing_mode: str,
    description: str = '',
    variant_data: list[dict] | None = None,
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

        product = Product.objects.create(
            tenant_id=tenant_id,
            name=name,
            category=category,
            base_price=base_price,
            pricing_mode=pricing_mode,
            description=description,
            has_variants=bool(variant_data and len(variant_data) > 1),
        )

        if variant_data:
            for vd in variant_data:
                variant = ProductVariant.objects.create(
                    tenant_id=tenant_id,
                    product=product,
                    sku=vd.get('sku', ''),
                    price=vd.get('price'),
                )
                for av_id in vd.get('attribute_value_ids', []):
                    VariantAttributeValue.objects.create(
                        tenant_id=tenant_id,
                        variant=variant,
                        attribute_value_id=av_id,
                    )
        else:
            # No variants — create a single default variant
            ProductVariant.objects.create(
                tenant_id=tenant_id,
                product=product,
                sku='',
                price=None,
            )

        return product


def apply_category_template_to_product(product: Product) -> None:
    """
    Apply category's default_pricing_mode to a product.
    Called on product creation when category is set.
    """
    if product.category:
        product.pricing_mode = product.category.default_pricing_mode
        product.save(update_fields=['pricing_mode', 'updated_at'])


def apply_category_settings_to_products(
    category: Category,
    apply_to_existing: bool = False,
) -> int:
    """
    Apply category settings to products.
    Returns number of updated products.

    If apply_to_existing=False, only affects new products (no-op here).
    If apply_to_existing=True, mass-update all products in category.
    """
    if not apply_to_existing:
        return 0

    return Product.objects.filter(
        category=category,
        tenant_id=category.tenant_id,
    ).update(
        pricing_mode=category.default_pricing_mode,
    )


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
