from django.urls import path

from .workspace_views import (
    ProcurementWorkspaceActionView,
    ProcurementWorkspaceDetailView,
    ProcurementWorkspaceListCreateView,
)

urlpatterns = [
    path('', ProcurementWorkspaceListCreateView.as_view(), name='procurement-workspace-list'),
    path('<int:pk>/', ProcurementWorkspaceDetailView.as_view(), name='procurement-workspace-detail'),
    path('<int:pk>/actions/<str:action>/', ProcurementWorkspaceActionView.as_view(), name='procurement-workspace-action'),
]

