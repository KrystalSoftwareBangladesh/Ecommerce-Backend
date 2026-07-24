# meta_api/urls/__init__.py
from django.urls import path, include

from .v1 import urlpatterns as meta_urlpatterns


urlpatterns = [
    path('v1/', include(meta_urlpatterns)),
]
