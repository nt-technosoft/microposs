"""Analytics URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProductPerformanceViewSet, AgingReportViewSet

router = DefaultRouter()
router.register('product-performance', ProductPerformanceViewSet, basename='product-performance')
router.register('aging-reports', AgingReportViewSet, basename='aging-report')

urlpatterns = [
    path('', include(router.urls)),
]
