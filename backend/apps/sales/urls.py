"""Sales URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import PosSessionViewSet, SaleViewSet

router = DefaultRouter()
router.register('sessions', PosSessionViewSet, basename='pos-session')
router.register('sales', SaleViewSet, basename='sale')

urlpatterns = [
    path('', include(router.urls)),
]
