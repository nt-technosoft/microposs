"""Suppliers URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SupplierViewSet, ConsignmentAgreementViewSet

router = DefaultRouter()
router.register('suppliers', SupplierViewSet, basename='supplier')
router.register('consignment-agreements', ConsignmentAgreementViewSet, basename='consignment-agreement')

urlpatterns = [
    path('', include(router.urls)),
]
