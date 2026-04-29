"""
Catalog serializers — DRF serializers for all catalog models.
"""

from rest_framework import serializers
from django.db import models as db_models

from .models import (
    Category, Attribute, AttributeValue, CategoryAttribute, CategoryCharacteristicTemplate,
    Product, ProductVariant, VariantAttributeValue,
    ProductCharacteristic, DiscountReason,
)


def _requested_location_id(context) -> int | None:
    warehouse_id = context.get('warehouse_id') or context.get('location_id')
    return warehouse_id if isinstance(warehouse_id, int) else None


def _stock_base_queryset():
    from apps.inventory.models import LotStock

    return LotStock.objects.filter(
        lot__is_active=True,
        quantity_remaining__gt=0,
    )


def _stock_total(queryset) -> int:
    result = queryset.aggregate(total=db_models.Sum('quantity_remaining'))
    return int(result['total'] or 0)


def _stock_by_location(queryset) -> list[dict]:
    return [
        {
            'warehouse_id': row['warehouse_id'],
            'warehouse_name': row['warehouse__name'],
            'warehouse_kind': row['warehouse__kind'],
            'quantity': int(row['quantity'] or 0),
        }
        for row in queryset.values(
            'warehouse_id',
            'warehouse__name',
            'warehouse__kind',
        ).annotate(
            quantity=db_models.Sum('quantity_remaining'),
        ).order_by('warehouse__kind', 'warehouse__name')
    ]


def _availability_state(*, total_stock: int, stock_at_location: int) -> str:
    if stock_at_location > 0:
        return 'in_shop'
    if total_stock > 0:
        return 'warehouse_only'
    return 'out_of_stock'


# === Category ===

class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'parent', 'default_pricing_mode',
            'sort_order', 'products_count', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CategoryDetailSerializer(CategorySerializer):
    children = CategorySerializer(many=True, read_only=True)
    template_attributes = serializers.SerializerMethodField()
    template_characteristics = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + [
            'children',
            'template_attributes',
            'template_characteristics',
        ]

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

    def get_template_characteristics(self, obj):
        templates = obj.template_characteristics.all()
        return [
            {
                'id': tpl.id,
                'name': tpl.name,
                'default_value': tpl.default_value,
                'sort_order': tpl.sort_order,
            }
            for tpl in templates
        ]


class CategoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'parent', 'default_pricing_mode', 'sort_order']
        read_only_fields = ['id']


class ApplyCategorySettingsSerializer(serializers.Serializer):
    apply_to_existing = serializers.BooleanField(default=False)
    apply_pricing_mode = serializers.BooleanField(default=True)
    apply_characteristics = serializers.BooleanField(default=True)


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
        extra_kwargs = {
            'category': {'required': False},
        }


class CategoryCharacteristicTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryCharacteristicTemplate
        fields = ['id', 'category', 'name', 'default_value', 'sort_order']
        read_only_fields = ['id']
        extra_kwargs = {
            'category': {'required': False},
        }


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
    total_stock_all_locations = serializers.SerializerMethodField()
    stock_at_location = serializers.SerializerMethodField()
    stock_by_location = serializers.SerializerMethodField()
    availability_state = serializers.SerializerMethodField()
    product_name = serializers.CharField(source='product.name', read_only=True)
    category_id = serializers.IntegerField(source='product.category_id', read_only=True)
    category_name = serializers.CharField(source='product.category.name', read_only=True, default=None)
    display_sku = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'product', 'product_name', 'category_id', 'category_name',
            'sku', 'display_sku', 'price', 'effective_price',
            'is_active', 'attribute_values', 'stock_quantity',
            'total_stock_all_locations', 'stock_at_location',
            'stock_by_location', 'availability_state',
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
        queryset = _stock_base_queryset().filter(
            lot__product_variant=obj,
        )
        warehouse_id = _requested_location_id(self.context)
        if warehouse_id is not None:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return _stock_total(queryset)

    def get_total_stock_all_locations(self, obj):
        return _stock_total(_stock_base_queryset().filter(lot__product_variant=obj))

    def get_stock_at_location(self, obj):
        warehouse_id = _requested_location_id(self.context)
        if warehouse_id is None:
            return None
        return _stock_total(
            _stock_base_queryset().filter(
                lot__product_variant=obj,
                warehouse_id=warehouse_id,
            )
        )

    def get_stock_by_location(self, obj):
        return _stock_by_location(
            _stock_base_queryset().filter(lot__product_variant=obj)
        )

    def get_availability_state(self, obj):
        total_stock = self.get_total_stock_all_locations(obj)
        stock_at_location = self.get_stock_at_location(obj)
        return _availability_state(
            total_stock=total_stock,
            stock_at_location=stock_at_location or 0,
        )

    def get_display_sku(self, obj):
        sku = (obj.sku or '').strip()
        return sku or f'VAR-{obj.id}'


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
    total_stock_all_locations = serializers.SerializerMethodField()
    stock_at_location = serializers.SerializerMethodField()
    stock_by_location = serializers.SerializerMethodField()
    availability_state = serializers.SerializerMethodField()
    display_sku = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'category_name',
            'base_price', 'pricing_mode', 'has_variants',
            'is_active', 'photo_url', 'display_sku', 'variants_count', 'total_stock',
            'total_stock_all_locations', 'stock_at_location',
            'stock_by_location', 'availability_state',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_variants_count(self, obj):
        return obj.variants.filter(is_active=True).count()

    def get_total_stock(self, obj):
        queryset = _stock_base_queryset().filter(
            lot__product_variant__product=obj,
        )
        warehouse_id = _requested_location_id(self.context)
        if warehouse_id is not None:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return _stock_total(queryset)

    def get_total_stock_all_locations(self, obj):
        return _stock_total(
            _stock_base_queryset().filter(lot__product_variant__product=obj)
        )

    def get_stock_at_location(self, obj):
        warehouse_id = _requested_location_id(self.context)
        if warehouse_id is None:
            return None
        return _stock_total(
            _stock_base_queryset().filter(
                lot__product_variant__product=obj,
                warehouse_id=warehouse_id,
            )
        )

    def get_stock_by_location(self, obj):
        return _stock_by_location(
            _stock_base_queryset().filter(lot__product_variant__product=obj)
        )

    def get_availability_state(self, obj):
        total_stock = self.get_total_stock_all_locations(obj)
        stock_at_location = self.get_stock_at_location(obj)
        return _availability_state(
            total_stock=total_stock,
            stock_at_location=stock_at_location or 0,
        )

    def get_display_sku(self, obj):
        variant = obj.variants.filter(is_active=True).order_by('id').first()
        if not variant:
            return ''
        sku = (variant.sku or '').strip()
        return sku or f'VAR-{variant.id}'

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if not obj.photo:
            return None
        url = obj.photo.url
        return request.build_absolute_uri(url) if request is not None else url


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None,
    )
    variants = ProductVariantSerializer(many=True, read_only=True)
    characteristics = ProductCharacteristicSerializer(many=True, read_only=True)
    photo_url = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()
    total_stock_all_locations = serializers.SerializerMethodField()
    stock_at_location = serializers.SerializerMethodField()
    stock_by_location = serializers.SerializerMethodField()
    availability_state = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'category_name', 'description',
            'base_price', 'pricing_mode', 'has_variants', 'is_active',
            'photo_url', 'variants', 'characteristics',
            'total_stock', 'total_stock_all_locations', 'stock_at_location',
            'stock_by_location', 'availability_state',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_stock(self, obj):
        return ProductListSerializer(context=self.context).get_total_stock(obj)

    def get_total_stock_all_locations(self, obj):
        return ProductListSerializer(context=self.context).get_total_stock_all_locations(obj)

    def get_stock_at_location(self, obj):
        return ProductListSerializer(context=self.context).get_stock_at_location(obj)

    def get_stock_by_location(self, obj):
        return ProductListSerializer(context=self.context).get_stock_by_location(obj)

    def get_availability_state(self, obj):
        return ProductListSerializer(context=self.context).get_availability_state(obj)

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if not obj.photo:
            return None
        url = obj.photo.url
        return request.build_absolute_uri(url) if request is not None else url


class ProductCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    base_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
    )
    pricing_mode = serializers.ChoiceField(
        choices=['ALWAYS_ASK', 'EDITABLE', 'FIXED'],
        required=False,
    )
    description = serializers.CharField(required=False, default='', allow_blank=True)
    photo = serializers.ImageField(required=False, allow_null=True)
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
