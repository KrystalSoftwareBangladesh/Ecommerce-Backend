from django.urls import path, include

from .v1 import urlpatterns as category_urlpatterns


urlpatterns = [
    path('v1/', include(category_urlpatterns)),
]
