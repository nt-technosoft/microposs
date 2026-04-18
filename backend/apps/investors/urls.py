"""Investors URL patterns."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import InvestorViewSet, InvestorContractViewSet

router = DefaultRouter()
router.register('investors', InvestorViewSet, basename='investor')
router.register('contracts', InvestorContractViewSet, basename='investor-contract')

urlpatterns = [
    path('', include(router.urls)),
]
