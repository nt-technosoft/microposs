from django.urls import path
from . import views

urlpatterns = [
    path('credentials', views.credentials_list_create),
    path('credentials/<str:pk>/revoke', views.credential_revoke),
]
