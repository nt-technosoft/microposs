"""Finance URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet,
    CashAccountViewSet,
    CashEntryViewSet,
    CurrencyExchangeViewSet,
    DailySummaryViewSet,
    ExpenseViewSet,
    ExchangeRateViewSet,
    JournalEntryViewSet,
    CashFlowSummaryViewSet,
    OwnerContributionViewSet,
    OwnerDrawingViewSet,
    CashTransferViewSet,
    RefundViewSet,
    SaleProfitabilityView,
    ProductProfitabilityView,
    ProcurementProfitabilityView,
    ProcurementProfitabilityDetailView,
    AgreementProfitabilityDetailView,
    ReportAnalyticsView,
    ReportSummaryView,
)

router = DefaultRouter()
router.register('accounts', AccountViewSet, basename='account')
router.register('cash-accounts', CashAccountViewSet, basename='cash-account')
router.register('cash-entries', CashEntryViewSet, basename='cash-entry')
router.register('currency-exchanges', CurrencyExchangeViewSet, basename='currency-exchange')
router.register('refunds', RefundViewSet, basename='refund')
router.register('owner-contributions', OwnerContributionViewSet, basename='owner-contribution')
router.register('owner-drawings', OwnerDrawingViewSet, basename='owner-drawing')
router.register('cash-transfers', CashTransferViewSet, basename='cash-transfer')
router.register('journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register('expenses', ExpenseViewSet, basename='expense')
router.register('daily-summaries', DailySummaryViewSet, basename='daily-summary')
router.register('cash-flow', CashFlowSummaryViewSet, basename='cash-flow')
router.register('fx-rates', ExchangeRateViewSet, basename='fx-rate')

urlpatterns = [
    path('reports/summary/', ReportSummaryView.as_view()),
    path('reports/analytics/', ReportAnalyticsView.as_view()),
    path('sales-profitability/', SaleProfitabilityView.as_view()),
    path('product-profitability/', ProductProfitabilityView.as_view()),
    path('procurement-profitability/', ProcurementProfitabilityView.as_view()),
    path('procurement-profitability/<int:procurement_id>/', ProcurementProfitabilityDetailView.as_view()),
    path('agreement-profitability/<int:agreement_id>/', AgreementProfitabilityDetailView.as_view()),
    path('', include(router.urls)),
]
