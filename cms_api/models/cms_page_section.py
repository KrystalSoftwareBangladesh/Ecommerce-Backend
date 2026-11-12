# cms_api/models/cms_page_section.py
"""CmsPageSection (docs/cms-architecture.md 5.3).

An editable section instance on a page composition row: either a
link to a global ``CmsSection`` (``global_section``) or local content
(``content``, exactly one registry block). ``content`` is nullable
only when ``global_section`` is set.

``ParentalKey`` lets Wagtail revisions serialize the page's
composition rows into the page revision content, so page rollback
restores composition too (7.3).
"""
from django.core.exceptions import ValidationError
from django.db import models

from modelcluster.fields import ParentalKey

from wagtail.fields import StreamField
from wagtail.models import Orderable

from cms_api.sections.registry import CONTENT_BLOCKS


class CmsPageSection(Orderable):
    page = ParentalKey(
        "cms_api.CmsPage",
        on_delete=models.CASCADE,
        related_name="sections",
    )
    name = models.CharField(max_length=255, blank=True, default="")
    global_section = models.ForeignKey(
        "cms_api.CmsSection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    content = StreamField(
        CONTENT_BLOCKS,
        min_num=1,
        max_num=1,
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "CMS page section"
        verbose_name_plural = "CMS page sections"

    def __str__(self):
        return self.name or "Page section"

    def clean(self):
        errors = {}
        has_content = bool(self.content) and len(self.content) > 0
        if self.global_section_id and has_content:
            errors["content"] = (
                "Set either global_section or local content, not both."
            )
        elif not self.global_section_id and not has_content:
            errors["content"] = (
                "Local content is required when no global_section "
                "is set."
            )
        if errors:
            raise ValidationError(errors)
