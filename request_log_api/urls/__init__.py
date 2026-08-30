from django.urls import path, include

from .v1 import urlpatterns as request_log_urlpatterns


urlpatterns = [
    path('v1/', include(request_log_urlpatterns)),
]
