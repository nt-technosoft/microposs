"""Investors URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    InvestorViewSet,
    InvestorContractViewSet,
    InvestorProfitRecordViewSet,
    InvestorSummaryViewSet,
)

router = DefaultRouter()
router.register('investors', InvestorViewSet, basename='investor')
router.register('contracts', InvestorContractViewSet, basename='investor-contract')
router.register('profit-records', InvestorProfitRecordViewSet, basename='profit-record')
router.register('summaries', InvestorSummaryViewSet, basename='investor-summary')

urlpatterns = [
    path('', include(router.urls)),
]
