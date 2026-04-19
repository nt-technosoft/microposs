"""Investors URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import InvestorViewSet, InvestorContractViewSet, InvestorDashboardView, InvestorProcurementView

router = DefaultRouter()
router.register('investors', InvestorViewSet, basename='investor')
router.register('contracts', InvestorContractViewSet, basename='investor-contract')

urlpatterns = [
    path('dashboard/', InvestorDashboardView.as_view()),
    path('procurements/', InvestorProcurementView.as_view()),
    path('procurements/<int:procurement_id>/', InvestorProcurementView.as_view()),
    path('', include(router.urls)),
]
