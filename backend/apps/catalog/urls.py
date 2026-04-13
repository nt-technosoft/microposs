"""Catalog URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    AttributeViewSet,
    ProductViewSet,
    ProductVariantViewSet,
    DiscountReasonViewSet,
)

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('attributes', AttributeViewSet, basename='attribute')
router.register('products', ProductViewSet, basename='product')
router.register('variants', ProductVariantViewSet, basename='variant')
router.register('discount-reasons', DiscountReasonViewSet, basename='discount-reason')

urlpatterns = [
    path('', include(router.urls)),
]
