# checkout_api/urls/v1.py
from django.urls import path
from checkout_api.views import v1

urlpatterns = [
    path(
        "checkout/validate/",
        v1.CheckoutValidateView.as_view(),
        name="checkout-validate",
    ),
]
