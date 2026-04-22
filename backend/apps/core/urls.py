"""Core URL patterns."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views_alignment import ReconciliationLatestView
from .views import (
    BusinessInvestorRelationViewSet,
    InvestorInviteAcceptView,
    InvestorInvitePreviewView,
    InvestorInviteRegisterView,
    InvestorInviteViewSet,
    PartnerViewSet,
)

router = DefaultRouter()
router.register('partners', PartnerViewSet, basename='partner')
router.register('investor-relations', BusinessInvestorRelationViewSet, basename='investor-relation')
router.register('investor-invites', InvestorInviteViewSet, basename='investor-invite')

urlpatterns = [
    path('', include(router.urls)),
    path('investor-invites/<str:token>/preview/', InvestorInvitePreviewView.as_view()),
    path('investor-invites/<str:token>/accept/', InvestorInviteAcceptView.as_view()),
    path('investor-invites/<str:token>/register/', InvestorInviteRegisterView.as_view()),
    path(
        'excel/reconciliation/latest/',
        ReconciliationLatestView.as_view(),
        name='excel-reconciliation-latest',
    ),
]
