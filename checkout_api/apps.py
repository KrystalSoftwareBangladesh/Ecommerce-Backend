# checkout_api/apps.py
from django.apps import AppConfig


class CheckoutApiConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )
    name = "checkout_api"
    verbose_name = "Checkout"
