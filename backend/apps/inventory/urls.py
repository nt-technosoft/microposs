"""Inventory URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    LocationViewSet,
    ReceiptViewSet,
    LotViewSet,
    StockMovementViewSet,
    StockView,
)

router = DefaultRouter()
router.register('locations', LocationViewSet, basename='location')
router.register('receipts', ReceiptViewSet, basename='receipt')
router.register('lots', LotViewSet, basename='lot')
router.register('movements', StockMovementViewSet, basename='movement')
router.register('stock', StockView, basename='stock')

urlpatterns = [
    path('', include(router.urls)),
]
