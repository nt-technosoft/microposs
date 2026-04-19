"""MicroPOS URL Configuration."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1
    path('api/v1/', include([
        path('auth/', include('apps.core.urls_auth')),
        path('core/', include('apps.core.urls')),
        path('catalog/', include('apps.catalog.urls')),
        path('inventory/', include('apps.inventory.urls')),
        path('sales/', include('apps.sales.urls')),
        path('finance/', include('apps.finance.urls')),
        path('partnerships/', include('apps.partnerships.urls')),
        path('investors/', include('apps.investors.urls')),
        path('suppliers/', include('apps.suppliers.urls')),
        path('customers/', include('apps.customers.urls')),
        path('risk/', include('apps.risk.urls')),
        path('analytics/', include('apps.analytics.urls')),
    ])),

    # OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += [
        path('__debug__/', include('debug_toolbar.urls')),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
