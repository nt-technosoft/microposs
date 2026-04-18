"""
Catalog domain — categories, products, variants, attributes.
"""

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
