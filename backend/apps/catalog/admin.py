from django.contrib import admin
from .models import (
    Category, Attribute, AttributeValue, CategoryAttribute,
    Product, ProductVariant, VariantAttributeValue,
    ProductCharacteristic, DiscountReason,
)


class CategoryAttributeInline(admin.TabularInline):
    model = CategoryAttribute
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'default_pricing_mode', 'sort_order')
    list_filter = ('default_pricing_mode',)
    search_fields = ('name',)
    inlines = [CategoryAttributeInline]


class AttributeValueInline(admin.TabularInline):
    model = AttributeValue
    extra = 1


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'sort_order')
    inlines = [AttributeValueInline]


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    readonly_fields = ('sku',)


class ProductCharacteristicInline(admin.TabularInline):
    model = ProductCharacteristic
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'base_price', 'pricing_mode', 'has_variants', 'is_active')
    list_filter = ('pricing_mode', 'has_variants', 'is_active', 'category')
    search_fields = ('name',)
    inlines = [ProductVariantInline, ProductCharacteristicInline]


@admin.register(DiscountReason)
class DiscountReasonAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_default', 'is_active')
