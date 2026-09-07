# blog_api/urls/__init__.py
from django.urls import path, include

from .v1 import urlpatterns as blog_urlpatterns


urlpatterns = [
    path('v1/', include(blog_urlpatterns)),
]
