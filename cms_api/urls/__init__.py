# cms_api/urls/__init__.py
from django.urls import path, include

urlpatterns = [
    path(
        "v1/",
        include("cms_api.urls.v1"),
    ),
]
