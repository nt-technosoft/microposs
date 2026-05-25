from django.urls import path, re_path
from . import views

urlpatterns = [
    path('agreement-link', views.agreement_link),
    path('sale', views.sale),
    path('inventory', views.inventory),
    path('agreements', views.agreements),
    re_path(r'^(?P<slug>[a-z0-9-]{1,64})$', views.catchall),
]
