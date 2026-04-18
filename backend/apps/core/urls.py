"""Core alignment URL patterns."""

from django.urls import path

from .views_alignment import ReconciliationLatestView

urlpatterns = [
    path(
        'excel/reconciliation/latest/',
        ReconciliationLatestView.as_view(),
        name='excel-reconciliation-latest',
    ),
]
