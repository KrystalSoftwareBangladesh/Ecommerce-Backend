# shipping_api/apps.py
from django.apps import AppConfig


class ShippingApiConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )
    name = "shipping_api"
    verbose_name = "Shipping"
