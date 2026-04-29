"""
Catalog API views — CRUD for categories, products, attributes, discount reasons.
"""

from django.db.models import Count, Max, Prefetch
from django.conf import settings
from django.core.validators import FileExtensionValidator
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsCashierOrWarehouse

from .models import (
    Category, Attribute, AttributeValue, CategoryAttribute, CategoryCharacteristicTemplate,
    Product, ProductVariant, ProductCharacteristic, DiscountReason,
)
from .serializers import (
    CategorySerializer, CategoryDetailSerializer, CategoryCreateSerializer,
    ApplyCategorySettingsSerializer,
    AttributeSerializer, AttributeCreateSerializer, AttributeValueSerializer,
    CategoryAttributeSerializer, CategoryCharacteristicTemplateSerializer,
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
    generate_variant_combinations_from_value_groups,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD for product categories."""

    filterset_class = CategoryFilter
    search_fields = ['name']
    ordering = ['sort_order', 'name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashierOrWarehouse()]
        return [IsOwner()]

    def get_queryset(self):
        qs = Category.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('parent').annotate(
            products_count=Count('products', distinct=True),
        )
        if self.action == 'retrieve':
            qs = qs.prefetch_related(
                Prefetch(
                    'children',
                    queryset=Category.objects.annotate(
                        products_count=Count('products', distinct=True),
                    ),
                )
            )
        return qs

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
            apply_pricing_mode=ser.validated_data['apply_pricing_mode'],
            apply_characteristics=ser.validated_data['apply_characteristics'],
        )
        return Response({'updated_count': count})

    @action(detail=True, methods=['get', 'post', 'put'], url_path='attributes')
    def template_attributes(self, request, pk=None):
        """Manage category template attributes."""
        category = self.get_object()
        if request.method == 'GET':
            cas = CategoryAttribute.objects.filter(
                category=category,
            ).select_related('attribute')
            serializer = CategoryAttributeSerializer(cas, many=True)
            return Response(serializer.data)

        if request.method == 'PUT':
            payload = request.data if isinstance(request.data, list) else []
            CategoryAttribute.all_objects.filter(
                tenant_id=category.tenant_id,
                category=category,
            ).delete()
            for raw in payload:
                attribute_id = raw.get('attribute') or raw.get('attribute_id')
                if not attribute_id:
                    continue
                if not Attribute.objects.filter(
                    tenant_id=category.tenant_id,
                    pk=attribute_id,
                ).exists():
                    continue
                CategoryAttribute.objects.create(
                    tenant_id=category.tenant_id,
                    category=category,
                    attribute_id=attribute_id,
                    is_variant_generating=bool(raw.get('is_variant_generating', True)),
                )
            cas = CategoryAttribute.objects.filter(
                category=category,
            ).select_related('attribute')
            return Response(CategoryAttributeSerializer(cas, many=True).data)

        serializer = CategoryAttributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            tenant_id=self.request.tenant_id,
            category=category,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post', 'put'], url_path='characteristics')
    def template_characteristics(self, request, pk=None):
        """Manage category default product characteristics."""
        category = self.get_object()
        if request.method == 'GET':
            templates = CategoryCharacteristicTemplate.objects.filter(
                tenant_id=category.tenant_id,
                category=category,
            ).order_by('sort_order', 'id')
            return Response(
                CategoryCharacteristicTemplateSerializer(templates, many=True).data
            )

        if request.method == 'PUT':
            payload = request.data if isinstance(request.data, list) else []
            CategoryCharacteristicTemplate.all_objects.filter(
                tenant_id=category.tenant_id,
                category=category,
            ).delete()
            for index, raw in enumerate(payload):
                name = str(raw.get('name', '')).strip()
                if not name:
                    continue
                CategoryCharacteristicTemplate.objects.create(
                    tenant_id=category.tenant_id,
                    category=category,
                    name=name,
                    default_value=str(raw.get('default_value', '')).strip(),
                    sort_order=int(raw.get('sort_order', index)),
                )
            templates = CategoryCharacteristicTemplate.objects.filter(
                tenant_id=category.tenant_id,
                category=category,
            ).order_by('sort_order', 'id')
            return Response(
                CategoryCharacteristicTemplateSerializer(templates, many=True).data
            )

        serializer = CategoryCharacteristicTemplateSerializer(data=request.data)
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

    parser_classes = [JSONParser, FormParser, MultiPartParser]
    filterset_class = ProductFilter
    search_fields = ['name']
    ordering_fields = ['name', 'base_price', 'created_at']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'list_variants'):
            return [IsCashierOrWarehouse()]
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        raw_location = (
            self.request.query_params.get('location_id')
            or self.request.query_params.get('location')
        )
        if raw_location and str(raw_location).isdigit():
            context['location_id'] = int(raw_location)
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        selected_pricing_mode = data.get('pricing_mode')
        if 'pricing_mode' not in request.data:
            selected_pricing_mode = None
        product = create_product_with_variants(
            tenant_id=request.tenant_id,
            name=data['name'],
            category_id=data.get('category_id'),
            base_price=data.get('base_price'),
            pricing_mode=selected_pricing_mode,
            description=data.get('description', ''),
            variant_data=data.get('variants'),
            photo=data.get('photo'),
        )

        # Save characteristics
        for char in data.get('characteristics', []):
            ProductCharacteristic.objects.create(
                tenant_id=request.tenant_id,
                product=product,
                name=char['name'],
                value=char['value'],
            )

        output = ProductDetailSerializer(product, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if isinstance(request.data.get('characteristics'), list):
            incoming = request.data.get('characteristics', [])
            ProductCharacteristic.objects.filter(
                tenant_id=request.tenant_id,
                product=instance,
            ).delete()
            for idx, char in enumerate(incoming):
                name = str(char.get('name', '')).strip()
                value = str(char.get('value', '')).strip()
                if not name:
                    continue
                ProductCharacteristic.objects.create(
                    tenant_id=request.tenant_id,
                    product=instance,
                    name=name,
                    value=value,
                )

        output = ProductDetailSerializer(instance, context=self.get_serializer_context())
        return Response(output.data)

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=['post'], url_path='generate-variants')
    def generate_variants(self, request, pk=None):
        """
        Auto-generate variants.

        Supported payloads:
        1) {"attribute_ids": [1,2]}
        2) {"attributes": [{"attribute_id": 1, "values": ["S", "M"]}, ...]}
        """
        product = self.get_object()
        attributes_payload = request.data.get('attributes')
        attribute_ids = request.data.get('attribute_ids', [])

        if attributes_payload:
            value_groups = []
            for attribute_payload in attributes_payload:
                attr_id = attribute_payload.get('attribute_id')
                raw_values = attribute_payload.get('values', [])
                if not attr_id or not isinstance(raw_values, list):
                    continue

                cleaned_values = []
                for value in raw_values:
                    text = str(value).strip()
                    if text and text not in cleaned_values:
                        cleaned_values.append(text)
                if not cleaned_values:
                    continue

                max_sort = AttributeValue.objects.filter(
                    tenant_id=request.tenant_id,
                    attribute_id=attr_id,
                ).aggregate(max_sort=Max('sort_order'))['max_sort'] or 0

                group = []
                for idx, value_text in enumerate(cleaned_values, start=1):
                    attr_value, _ = AttributeValue.objects.get_or_create(
                        tenant_id=request.tenant_id,
                        attribute_id=attr_id,
                        value=value_text,
                        defaults={'sort_order': max_sort + idx},
                    )
                    group.append(attr_value)

                if group:
                    value_groups.append(group)

            if not value_groups:
                return Response(
                    {'detail': 'attributes with values required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            variants = generate_variant_combinations_from_value_groups(
                tenant_id=request.tenant_id,
                product=product,
                value_groups=value_groups,
            )
        else:
            if not attribute_ids:
                return Response(
                    {'detail': 'attribute_ids or attributes required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            variants = generate_variant_combinations(
                tenant_id=request.tenant_id,
                product=product,
                attribute_ids=attribute_ids,
            )

        serializer = ProductVariantSerializer(variants, many=True)
        return Response(
            {
                'variants_created': len(variants),
                'variants': serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='variants')
    def list_variants(self, request, pk=None):
        """List all active variants for a product."""
        product = self.get_object()
        variants = product.variants.filter(
            is_active=True,
        ).prefetch_related(
            'attribute_values__attribute_value__attribute',
        )
        serializer = ProductVariantSerializer(
            variants,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=True, methods=['post', 'delete'], url_path='photo')
    def photo(self, request, pk=None):
        """Upload/replace or remove product photo."""
        product = self.get_object()

        if request.method == 'DELETE':
            if product.photo:
                product.photo.delete(save=False)
            product.photo = None
            product.save(update_fields=['photo', 'updated_at'])
            return Response({'photo_url': None}, status=status.HTTP_200_OK)

        upload = request.FILES.get('photo')
        if upload is None:
            return Response(
                {'detail': 'photo file is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if upload.size > 5 * 1024 * 1024:
            return Response(
                {'detail': 'photo must be <= 5MB.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = getattr(upload, 'content_type', '')
        if not str(content_type).startswith('image/'):
            return Response(
                {'detail': 'photo must be an image file.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validator = FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])
        try:
            validator(upload)
        except Exception:
            return Response(
                {'detail': 'allowed photo formats: jpg, jpeg, png, webp.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if product.photo:
            product.photo.delete(save=False)
        product.photo = upload
        product.save(update_fields=['photo', 'updated_at'])

        output = ProductDetailSerializer(product, context=self.get_serializer_context())
        return Response({'photo_url': output.data.get('photo_url')}, status=status.HTTP_200_OK)


class ProductVariantViewSet(viewsets.ModelViewSet):
    """Direct CRUD for variants (update price, SKU, deactivate)."""

    serializer_class = ProductVariantSerializer
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashierOrWarehouse()]
        return [IsOwner()]

    def get_queryset(self):
        return ProductVariant.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('product').prefetch_related(
            'attribute_values__attribute_value__attribute',
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        raw_location = (
            self.request.query_params.get('location_id')
            or self.request.query_params.get('location')
        )
        if raw_location and str(raw_location).isdigit():
            context['location_id'] = int(raw_location)
        return context

    def perform_destroy(self, instance):
        instance.soft_delete()


class DiscountReasonViewSet(viewsets.ModelViewSet):
    """CRUD for discount reasons."""

    serializer_class = DiscountReasonSerializer
    ordering = ['name']

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsCashierOrWarehouse()]
        return [IsOwner()]

    def get_queryset(self):
        return DiscountReason.objects.filter(
            tenant_id=self.request.tenant_id,
        )

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        instance.soft_delete()
