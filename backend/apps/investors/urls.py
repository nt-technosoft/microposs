"""Investors URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .payout_views import InvestorPayoutObligationView
from .views import InvestorViewSet, InvestorContractViewSet, InvestorAgreementView, InvestorDashboardView, InvestorProcurementView

router = DefaultRouter()
router.register('investors', InvestorViewSet, basename='investor')
router.register('contracts', InvestorContractViewSet, basename='investor-contract')

urlpatterns = [
    path('dashboard/', InvestorDashboardView.as_view()),
    path('agreements/', InvestorAgreementView.as_view()),
    path('agreements/<int:agreement_id>/', InvestorAgreementView.as_view()),
    path('procurements/', InvestorProcurementView.as_view()),
    path('procurements/<int:procurement_id>/', InvestorProcurementView.as_view()),
    path('payout-obligations/', InvestorPayoutObligationView.as_view()),
    path('payout-obligations/<int:obligation_id>/<str:action>/', InvestorPayoutObligationView.as_view()),
    path('', include(router.urls)),
]
