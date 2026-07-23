from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .fund_views import DisputeCaseViewSet, InvestmentFundViewSet, PayoutObligationViewSet
from .views import DividendPaymentViewSet, InvestmentAgreementViewSet, ProcurementViewSet

router = DefaultRouter()
router.register('agreements', InvestmentAgreementViewSet, basename='investment-agreement')
router.register('procurements', ProcurementViewSet, basename='procurement')
router.register('dividends', DividendPaymentViewSet, basename='dividend-payment')
router.register('funds', InvestmentFundViewSet, basename='investment-fund')
router.register('payout-obligations', PayoutObligationViewSet, basename='payout-obligation')
router.register('disputes', DisputeCaseViewSet, basename='dispute-case')

urlpatterns = [
    path('', include(router.urls)),
]
