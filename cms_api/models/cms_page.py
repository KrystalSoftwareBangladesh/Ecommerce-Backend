# cms_api/models/cms_page.py
"""CmsPage (docs/cms-architecture.md 5.1).

The CMS page is a Wagtail ``Page`` subclass so URL hierarchy,
revisions, publish state and tree integrity are reused from Wagtail.
``seo_title`` is inherited from ``wagtailcore.Page``; everything else
is declared here.

Custom permissions follow the Phase 1 ``CmsSection`` pattern so the
lifecycle endpoints are gated by the spec permissions (``publish_cms_page``,
``unpublish_cms_page``, ``archive_cms_page`` covering archive/restore).
"""
from django.db import models

from wagtail.models import Page

from cms_api.pages.templates import PAGE_TEMPLATE_CHOICES


class CmsPage(Page):
    template_key = models.CharField(
        max_length=20,
        choices=PAGE_TEMPLATE_CHOICES,
        default="blank",
    )
    seo_description = models.CharField(max_length=500, blank=True, default="")
    meta_keywords = models.CharField(max_length=255, blank=True, default="")
    og_title = models.CharField(max_length=255, blank=True, default="")
    og_description = models.CharField(
        max_length=500, blank=True, default=""
    )
    og_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    canonical_url = models.URLField(blank=True, default="")
    seo_noindex = models.BooleanField(default=False)
    seo_nofollow = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    panels = [
        # Minimal panels until Phase 5 owns the admin experience.
        "template_key",
        "seo_description",
        "meta_keywords",
        "og_title",
        "og_description",
        "og_image",
        "canonical_url",
        "seo_noindex",
        "seo_nofollow",
    ]

    class Meta:
        verbose_name = "CMS page"
        verbose_name_plural = "CMS pages"
        permissions = [
            ("publish_cms_page", "Can publish CMS pages"),
            ("unpublish_cms_page", "Can unpublish CMS pages"),
            ("archive_cms_page", "Can archive or restore CMS pages"),
        ]

    def __str__(self):
        return self.title
