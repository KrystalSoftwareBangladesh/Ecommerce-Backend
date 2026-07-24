# review_api/urls/__init__.py
from django.urls import path, include

from .v1 import urlpatterns as review_urlpatterns


urlpatterns = [
    path('v1/', include(review_urlpatterns)),
]
