from django.urls import path
from . import views

urlpatterns = [
    path('', views.AttachmentListCreateView.as_view(), name='attachment-list-create'),
    path('<int:pk>/', views.AttachmentDetailView.as_view(), name='attachment-detail'),
]
