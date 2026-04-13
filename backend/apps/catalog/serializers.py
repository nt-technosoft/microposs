"""
Catalog serializers — DRF serializers for all catalog models.
"""

from rest_framework import serializers
from .models import (
    Category, Attribute, AttributeValue, CategoryAttribute,
    Product, ProductVariant, VariantAttributeValue,
    ProductCharacteristic, DiscountReason,
)


# === Category ===

class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'parent', 'default_pricing_mode',
            'sort_order', 'products_count', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_products_count(self, obj):
        return obj.products.count()


class CategoryDetailSerializer(CategorySerializer):
    children = CategorySerializer(many=True, read_only=True)
    template_attributes = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ['children', 'template_attributes']

    def get_template_attributes(self, obj):
        cas = obj.template_attributes.select_related('attribute').all()
        return [
            {
                'id': ca.id,
                'attribute_id': ca.attribute_id,
                'attribute_name': ca.attribute.name,
                'is_variant_generating': ca.is_variant_generating,
            }
            for ca in cas
        ]


class CategoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['name', 'parent', 'default_pricing_mode', 'sort_order']


class ApplyCategorySettingsSerializer(serializers.Serializer):
    apply_to_existing = serializers.BooleanField(default=False)


# === Attributes ===

class AttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeValue
        fields = ['id', 'value', 'sort_order']
        read_only_fields = ['id']


class AttributeSerializer(serializers.ModelSerializer):
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = Attribute
        fields = ['id', 'name', 'sort_order', 'values']
        read_only_fields = ['id']


class AttributeCreateSerializer(serializers.ModelSerializer):
    values = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )

    class Meta:
        model = Attribute
        fields = ['name', 'sort_order', 'values']

    def create(self, validated_data):
        values_data = validated_data.pop('values', [])
        tenant_id = self.context['request'].tenant_id
        attribute = Attribute.objects.create(
            tenant_id=tenant_id,
            **validated_data,
        )
        for i, value in enumerate(values_data):
            AttributeValue.objects.create(
                tenant_id=tenant_id,
                attribute=attribute,
                value=value,
                sort_order=i,
            )
        return attribute


class CategoryAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryAttribute
        fields = ['id', 'category', 'attribute', 'is_variant_generating']
        read_only_fields = ['id']


# === Product Variants ===

class VariantAttributeDisplaySerializer(serializers.Serializer):
    attribute_name = serializers.CharField()
    value = serializers.CharField()


class ProductVariantSerializer(serializers.ModelSerializer):
    attribute_values = serializers.SerializerMethodField()
    effective_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
    )
    stock_quantity = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'product', 'sku', 'price', 'effective_price',
            'is_active', 'attribute_values', 'stock_quantity',
        ]
        read_only_fields = ['id', 'effective_price']

    def get_attribute_values(self, obj):
        avs = obj.attribute_values.select_related(
            'attribute_value__attribute'
        ).all()
        return [
            {
                'attribute_name': av.attribute_value.attribute.name,
                'value': av.attribute_value.value,
            }
            for av in avs
        ]

    def get_stock_quantity(self, obj):
        from apps.inventory.models import Lot
        from django.db import models as db_models
        result = Lot.objects.filter(
            product_variant=obj,
            is_active=True,
        ).aggregate(
            total=db_models.Sum('quantity_remaining')
        )
        return result['total'] or 0


class ProductVariantCreateSerializer(serializers.Serializer):
    sku = serializers.CharField(required=False, default='', allow_blank=True)
    price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
    )
    attribute_value_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )


# === Product Characteristics ===

class ProductCharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCharacteristic
        fields = ['id', 'name', 'value']
        read_only_fields = ['id']


# === Product ===

class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None,
    )
    variants_count = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'category_name',
            'base_price', 'pricing_mode', 'has_variants',
            'is_active', 'variants_count', 'total_stock',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_variants_count(self, obj):
        return obj.variants.filter(is_active=True).count()

    def get_total_stock(self, obj):
        from apps.inventory.models import Lot
        from django.db import models as db_models
        result = Lot.objects.filter(
            product_variant__product=obj,
            is_active=True,
        ).aggregate(total=db_models.Sum('quantity_remaining'))
        return result['total'] or 0


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None,
    )
    variants = ProductVariantSerializer(many=True, read_only=True)
    characteristics = ProductCharacteristicSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'category_name', 'description',
            'base_price', 'pricing_mode', 'has_variants', 'is_active',
            'variants', 'characteristics', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    base_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
    )
    pricing_mode = serializers.ChoiceField(
        choices=['ASK_EACH_SALE', 'DEFAULT_EDITABLE', 'FIXED_LOCKED'],
        default='DEFAULT_EDITABLE',
    )
    description = serializers.CharField(required=False, default='', allow_blank=True)
    variants = ProductVariantCreateSerializer(many=True, required=False)
    characteristics = ProductCharacteristicSerializer(many=True, required=False)


class ProductUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'description', 'base_price',
            'pricing_mode', 'is_active',
        ]


# === Discount Reasons ===

class DiscountReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscountReason
        fields = ['id', 'name', 'is_default', 'is_active']
        read_only_fields = ['id']
