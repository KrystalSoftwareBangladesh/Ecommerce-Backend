# cms_api/apps.py
from django.apps import AppConfig


class CmsApiConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )
    name = "cms_api"
    verbose_name = "CMS"

    def ready(self):
        # Import wagtail_hooks modules (registering the CMS snippets)
        # eagerly: SnippetChooserBlock content validation resolves
        # chooser widgets, which needs the snippet registrations to
        # have happened even in API-only processes where Wagtail's
        # hook discovery would never run.
        from wagtail.hooks import search_for_hooks

        search_for_hooks()
