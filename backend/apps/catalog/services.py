"""
Catalog business logic — product/variant creation, category template application.
"""

from django.db import transaction
from .models import (
    Product, ProductVariant, VariantAttributeValue,
    Category, CategoryAttribute, CategoryCharacteristicTemplate, AttributeValue,
    ProductCharacteristic,
)


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
            category.default_pricing_mode if category else 'DEFAULT_EDITABLE'
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
