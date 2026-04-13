"""Risk URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import RiskEventViewSet, InventoryCheckViewSet

router = DefaultRouter()
router.register('events', RiskEventViewSet, basename='risk-event')
router.register('checks', InventoryCheckViewSet, basename='inventory-check')

urlpatterns = [
    path('', include(router.urls)),
]
