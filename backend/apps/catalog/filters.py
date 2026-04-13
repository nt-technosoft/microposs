"""
Catalog filters for list views.
"""

import django_filters
from .models import Product, Category


class ProductFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name='category_id')
    is_active = django_filters.BooleanFilter()
    has_variants = django_filters.BooleanFilter()
    pricing_mode = django_filters.CharFilter()
    search = django_filters.CharFilter(field_name='name', lookup_expr='icontains')
    min_price = django_filters.NumberFilter(field_name='base_price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='base_price', lookup_expr='lte')

    class Meta:
        model = Product
        fields = ['category', 'is_active', 'has_variants', 'pricing_mode']


class CategoryFilter(django_filters.FilterSet):
    parent = django_filters.NumberFilter(field_name='parent_id')
    root_only = django_filters.BooleanFilter(
        method='filter_root_only',
        label='Root categories only',
    )

    class Meta:
        model = Category
        fields = ['parent']

    def filter_root_only(self, queryset, name, value):
        if value:
            return queryset.filter(parent__isnull=True)
        return queryset
