# wishlist_api/urls/v1.py
from django.urls import path, include

from .v1 import urlpatterns as wishlist_urlpatterns


urlpatterns = [
    path('v1/', include(wishlist_urlpatterns)),
]
