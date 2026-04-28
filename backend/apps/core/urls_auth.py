"""Auth URL patterns."""

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from .auth_views import CurrentUserView, PendingAwareTokenObtainPairView

urlpatterns = [
    path('token/', PendingAwareTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', CurrentUserView.as_view(), name='auth_me'),
]
