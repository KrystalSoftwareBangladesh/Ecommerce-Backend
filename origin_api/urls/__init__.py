from django.urls import path, include

from .v1 import urlpatterns as origin_urlpatterns


urlpatterns = [
    path('v1/', include(origin_urlpatterns)),
]
