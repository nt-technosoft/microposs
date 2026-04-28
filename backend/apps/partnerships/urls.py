from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DividendPaymentViewSet, InvestmentAgreementViewSet, ProcurementViewSet

router = DefaultRouter()
router.register('agreements', InvestmentAgreementViewSet, basename='investment-agreement')
router.register('procurements', ProcurementViewSet, basename='procurement')
router.register('dividends', DividendPaymentViewSet, basename='dividend-payment')

urlpatterns = [
    path('', include(router.urls)),
]
