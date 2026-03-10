from django.urls import include, path

from .v1 import urlpatterns as account_urlpatterns


urlpatterns = [
    path('v1/', include(account_urlpatterns)),
]
