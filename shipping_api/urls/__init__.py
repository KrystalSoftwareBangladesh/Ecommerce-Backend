# shipping_api/urls/__init__.py
from django.urls import path, include

urlpatterns = [
    path(
        "v1/",
        include("shipping_api.urls.v1"),
    ),
]
