from django.urls import include, path

from .v1 import urlpatterns as transaction_urlpatterns


urlpatterns = [
    path('v1/', include(transaction_urlpatterns)),
]
