"""Finance URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet,
    JournalEntryViewSet,
    ExpenseViewSet,
    DailySummaryViewSet,
    CashFlowSummaryViewSet,
    ExchangeRateViewSet,
)

router = DefaultRouter()
router.register('accounts', AccountViewSet, basename='account')
router.register('journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register('expenses', ExpenseViewSet, basename='expense')
router.register('daily-summaries', DailySummaryViewSet, basename='daily-summary')
router.register('cash-flow', CashFlowSummaryViewSet, basename='cash-flow')
router.register('fx-rates', ExchangeRateViewSet, basename='fx-rate')

urlpatterns = [
    path('', include(router.urls)),
]
