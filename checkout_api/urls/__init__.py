# checkout_api/urls/__init__.py
from django.urls import path, include

urlpatterns = [
    path(
        "v1/",
        include("checkout_api.urls.v1"),
    ),
]
