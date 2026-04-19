from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DividendPaymentViewSet, ProcurementViewSet

router = DefaultRouter()
router.register('procurements', ProcurementViewSet, basename='procurement')
router.register('dividends', DividendPaymentViewSet, basename='dividend-payment')

urlpatterns = [
    path('', include(router.urls)),
]
