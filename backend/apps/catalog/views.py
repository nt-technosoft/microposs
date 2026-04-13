"""
Catalog API views — CRUD for categories, products, attributes, discount reasons.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsCashier

from .models import (
    Category, Attribute, AttributeValue, CategoryAttribute,
    Product, ProductVariant, ProductCharacteristic, DiscountReason,
)
from .serializers import (
    CategorySerializer, CategoryDetailSerializer, CategoryCreateSerializer,
    ApplyCategorySettingsSerializer,
    AttributeSerializer, AttributeCreateSerializer, AttributeValueSerializer,
    CategoryAttributeSerializer,
    ProductListSerializer, ProductDetailSerializer,
    ProductCreateSerializer, ProductUpdateSerializer,
    ProductVariantSerializer, ProductCharacteristicSerializer,
    DiscountReasonSerializer,
)
from .filters import ProductFilter, CategoryFilter
from .services import (
    create_product_with_variants,
    apply_category_settings_to_products,
    generate_variant_combinations,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD for product categories."""

    filterset_class = CategoryFilter
    search_fields = ['name']
    ordering = ['sort_order', 'name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashier()]
        return [IsOwner()]

    def get_queryset(self):
        return Category.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('parent')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CategoryDetailSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return CategoryCreateSerializer
        return CategorySerializer

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    @action(detail=True, methods=['post'], url_path='apply-settings')
    def apply_settings(self, request, pk=None):
        """Apply category settings to existing products."""
        category = self.get_object()
        ser = ApplyCategorySettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        count = apply_category_settings_to_products(
            category,
            apply_to_existing=ser.validated_data['apply_to_existing'],
        )
        return Response({'updated_count': count})

    @action(detail=True, methods=['get', 'post'], url_path='attributes')
    def template_attributes(self, request, pk=None):
        """Manage category template attributes."""
        category = self.get_object()
        if request.method == 'GET':
            cas = CategoryAttribute.objects.filter(
                category=category,
            ).select_related('attribute')
            serializer = CategoryAttributeSerializer(cas, many=True)
            return Response(serializer.data)

        serializer = CategoryAttributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            tenant_id=self.request.tenant_id,
            category=category,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AttributeViewSet(viewsets.ModelViewSet):
    """CRUD for attributes (Size, Color, etc.)."""

    permission_classes = [IsOwner]
    search_fields = ['name']
    ordering = ['sort_order']

    def get_queryset(self):
        return Attribute.objects.filter(
            tenant_id=self.request.tenant_id,
        ).prefetch_related('values')

    def get_serializer_class(self):
        if self.action in ('create',):
            return AttributeCreateSerializer
        return AttributeSerializer

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post'], url_path='values')
    def add_value(self, request, pk=None):
        """Add a new value to an attribute."""
        attribute = self.get_object()
        serializer = AttributeValueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            tenant_id=self.request.tenant_id,
            attribute=attribute,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductViewSet(viewsets.ModelViewSet):
    """CRUD for products with variants."""

    filterset_class = ProductFilter
    search_fields = ['name']
    ordering_fields = ['name', 'base_price', 'created_at']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashier()]
        return [IsOwner()]

    def get_queryset(self):
        qs = Product.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('category')

        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                'variants__attribute_values__attribute_value__attribute',
                'characteristics',
            )
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        if self.action == 'create':
            return ProductCreateSerializer
        if self.action in ('update', 'partial_update'):
            return ProductUpdateSerializer
        return ProductListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        product = create_product_with_variants(
            tenant_id=request.tenant_id,
            name=data['name'],
            category_id=data.get('category_id'),
            base_price=data.get('base_price'),
            pricing_mode=data.get('pricing_mode', 'DEFAULT_EDITABLE'),
            description=data.get('description', ''),
            variant_data=data.get('variants'),
        )

        # Save characteristics
        for char in data.get('characteristics', []):
            ProductCharacteristic.objects.create(
                tenant_id=request.tenant_id,
                product=product,
                name=char['name'],
                value=char['value'],
            )

        output = ProductDetailSerializer(product)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=['post'], url_path='generate-variants')
    def generate_variants(self, request, pk=None):
        """Auto-generate variants from attribute combinations."""
        product = self.get_object()
        attribute_ids = request.data.get('attribute_ids', [])
        if not attribute_ids:
            return Response(
                {'detail': 'attribute_ids required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        variants = generate_variant_combinations(
            tenant_id=request.tenant_id,
            product=product,
            attribute_ids=attribute_ids,
        )
        serializer = ProductVariantSerializer(variants, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='variants')
    def list_variants(self, request, pk=None):
        """List all active variants for a product."""
        product = self.get_object()
        variants = product.variants.filter(
            is_active=True,
        ).prefetch_related(
            'attribute_values__attribute_value__attribute',
        )
        serializer = ProductVariantSerializer(variants, many=True)
        return Response(serializer.data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    """Direct CRUD for variants (update price, SKU, deactivate)."""

    serializer_class = ProductVariantSerializer
    permission_classes = [IsOwner]
    ordering = ['-created_at']

    def get_queryset(self):
        return ProductVariant.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('product').prefetch_related(
            'attribute_values__attribute_value__attribute',
        )

    def perform_destroy(self, instance):
        instance.soft_delete()


class DiscountReasonViewSet(viewsets.ModelViewSet):
    """CRUD for discount reasons."""

    serializer_class = DiscountReasonSerializer
    permission_classes = [IsOwner]
    ordering = ['name']

    def get_queryset(self):
        return DiscountReason.objects.filter(
            tenant_id=self.request.tenant_id,
        )

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.soft_delete()
