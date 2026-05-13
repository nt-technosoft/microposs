"""
Catalog domain — categories, products, variants, attributes.
"""

from decimal import Decimal

from django.db import models
from apps.core.models import TenantModel


class Category(TenantModel):
    """Product category with template settings."""

    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
    )
    default_pricing_mode = models.CharField(
        max_length=20,
        choices=[
            ('ALWAYS_ASK', 'Всегда спрашивать'),
            ('EDITABLE', 'По умолчанию, можно менять'),
            ('FIXED', 'Фиксированная'),
        ],
        default='EDITABLE',
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'catalog_category'
        verbose_name_plural = 'categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Attribute(TenantModel):
    """
    Structured attribute type (e.g., "Size", "Color").
    Values are predefined choices.
    """

    name = models.CharField(max_length=100)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'catalog_attribute'
        ordering = ['sort_order']

    def __str__(self):
        return self.name


class AttributeValue(TenantModel):
    """Predefined value for an attribute (e.g., "S", "M", "L")."""

    attribute = models.ForeignKey(
        Attribute,
        on_delete=models.CASCADE,
        related_name='values',
    )
    value = models.CharField(max_length=100)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'catalog_attribute_value'
        ordering = ['sort_order']
        unique_together = [('attribute', 'value')]

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"


class CategoryAttribute(TenantModel):
    """Template: which attributes a category suggests for its products."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='template_attributes',
    )
    attribute = models.ForeignKey(
        Attribute,
        on_delete=models.CASCADE,
    )
    is_variant_generating = models.BooleanField(
        default=True,
        help_text='If True, this attribute creates product variants (SKUs).',
    )

    class Meta:
        db_table = 'catalog_category_attribute'
        unique_together = [('category', 'attribute')]


class CategoryCharacteristicTemplate(TenantModel):
    """Template: default characteristics for products in category."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='template_characteristics',
    )
    name = models.CharField(max_length=100)
    default_value = models.CharField(max_length=500, blank=True, default='')
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'catalog_category_characteristic_template'
        ordering = ['sort_order', 'id']
        unique_together = [('category', 'name')]


class Product(TenantModel):
    """Product — a logical item with one or more variants."""

    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
    )
    description = models.TextField(blank=True, default='')
    photo = models.FileField(
        upload_to='products/%Y/%m/',
        null=True,
        blank=True,
    )
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Default price. Variants can override.',
    )
    pricing_mode = models.CharField(
        max_length=20,
        choices=[
            ('ALWAYS_ASK', 'Всегда спрашивать'),
            ('EDITABLE', 'По умолчанию, можно менять'),
            ('FIXED', 'Фиксированная'),
        ],
        default='EDITABLE',
    )
    has_variants = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'catalog_product'
        indexes = [
            models.Index(fields=['tenant', 'category', 'is_active']),
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self):
        return self.name


class ProductVariant(TenantModel):
    """
    SKU — specific combination of attributes.
    Even products without variants have one default ProductVariant.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants',
    )
    sku = models.CharField(max_length=100, blank=True, default='')
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Override price. Falls back to product.base_price if null.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'catalog_product_variant'
        indexes = [
            models.Index(fields=['tenant', 'product', 'is_active']),
        ]

    def __str__(self):
        attrs = self.attribute_values.select_related('attribute_value__attribute').all()
        if attrs:
            parts = [
                f"{a.attribute_value.attribute.name}:{a.attribute_value.value}"
                for a in attrs
            ]
            return f"{self.product.name} ({', '.join(parts)})"
        return self.product.name

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.base_price


class VariantAttributeValue(TenantModel):
    """Links a variant to its attribute values (e.g., Size=M, Color=Red)."""

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='attribute_values',
    )
    attribute_value = models.ForeignKey(
        AttributeValue,
        on_delete=models.CASCADE,
    )

    class Meta:
        db_table = 'catalog_variant_attribute_value'
        unique_together = [('variant', 'attribute_value')]


class ProductCharacteristic(TenantModel):
    """
    Descriptive (non-variant) property of a product.
    E.g., Material: leather + suede.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='characteristics',
    )
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=500)

    class Meta:
        db_table = 'catalog_product_characteristic'


class DiscountReason(TenantModel):
    """Configurable list of discount reasons. Default: 'Торг'."""

    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'catalog_discount_reason'

    def __str__(self):
        return self.name


class ProductSupplier(TenantModel):
    """
    Soft association between a ProductVariant and a Supplier — captures the
    fact that this variant has been (or is) sourced from this supplier.

    Auto-maintained by the procurement service: created on first receipt,
    updated on subsequent receipts. Never deleted manually.

    No explicit "primary" flag — preferred supplier is computed on the fly
    by `(-last_received_at, -total_procurements_count)`.
    """

    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='supplier_links',
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.CASCADE,
        related_name='product_links',
    )
    last_received_at = models.DateTimeField(
        help_text='Timestamp of the most recent confirmed receipt from this supplier.',
    )
    last_unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        help_text='Unit price of the most recent receipt (in last_currency).',
    )
    last_currency = models.CharField(max_length=3, default='UZS')
    total_received_quantity = models.DecimalField(
        max_digits=16,
        decimal_places=3,
        default=Decimal('0'),
    )
    total_received_value_uzs = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Cumulative value of received quantities, normalized to UZS.',
    )
    total_procurements_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of distinct confirmed procurements this link has participated in.',
    )

    class Meta:
        db_table = 'catalog_product_supplier'
        constraints = [
            models.UniqueConstraint(
                fields=['product_variant', 'supplier'],
                name='uq_product_supplier_pair',
            ),
        ]
        indexes = [
            # For sorting catalog by "preferred for this supplier" — newest first
            models.Index(fields=['supplier', '-last_received_at']),
            models.Index(fields=['tenant', 'supplier']),
            models.Index(fields=['tenant', 'product_variant']),
        ]

    def __str__(self):
        return f"{self.product_variant_id} ← {self.supplier_id} (last {self.last_received_at})"
