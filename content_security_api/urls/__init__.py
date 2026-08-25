from django.urls import path, include

from .v1 import urlpatterns as content_security_urlpatterns


urlpatterns = [
    path('v1/', include(content_security_urlpatterns)),
]
