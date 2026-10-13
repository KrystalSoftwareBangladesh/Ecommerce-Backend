# checkout_api/urls/v1.py
from django.urls import path

from checkout_api.views import v1

urlpatterns = [
    path(
        "checkout/validate/",
        v1.CheckoutValidateView.as_view(),
        name="checkout-validate",
    ),
    path(
        "checkout/confirm/",
        v1.CheckoutConfirmView.as_view(),
        name="checkout-confirm",
    ),
    path(
        "orders/",
        v1.CustomerOrderListView.as_view(),
        name="customer-order-list",
    ),
    path(
        "orders/<int:pk>/",
        v1.CustomerOrderDetailView.as_view(),
        name="customer-order-detail",
    ),
    path(
        "orders/<int:pk>/cancel/",
        v1.CustomerOrderCancelView.as_view(),
        name="customer-order-cancel",
    ),
]
