# cms_api/apps.py
from django.apps import AppConfig


class CmsApiConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )
    name = "cms_api"
    verbose_name = "CMS"
