"""Inventory URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WarehouseViewSet,
    ReceiptViewSet,
    LotViewSet,
    StockMovementViewSet,
    StockView,
)

router = DefaultRouter()
router.register('warehouses', WarehouseViewSet, basename='warehouse')
router.register('receipts', ReceiptViewSet, basename='receipt')
router.register('lots', LotViewSet, basename='lot')
router.register('movements', StockMovementViewSet, basename='movement')
router.register('stock', StockView, basename='stock')

urlpatterns = [
    path('', include(router.urls)),
]
