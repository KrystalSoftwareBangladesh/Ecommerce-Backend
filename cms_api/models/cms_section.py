# cms_api/models/cms_section.py
"""CmsSection snippet — global section instance (docs/cms-architecture.md
5.2, approved design AD-4).

A section is one named instance of a single registered section type.
Draft/publish/revisions come from Wagtail's native mixins; deletion is
archive-by-default with a dependency-guarded, elevated permanent
delete backed by SoftDeleteModel (rows referenced from revisions stay).
"""
from django.core.exceptions import ValidationError
from django.db import models

from wagtail.fields import StreamField
from wagtail.models import (
    DraftStateMixin,
    LockableMixin,
    PreviewableMixin,
    RevisionMixin,
)

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)
from cms_api.sections import CONTENT_BLOCKS, SECTION_TYPE_CHOICES


class CmsSection(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
    DraftStateMixin,
    RevisionMixin,
    PreviewableMixin,
    LockableMixin,
    models.Model,
):
    PREVIEW_TEMPLATE = "cms_api/cms_section_preview.html"

    name = models.CharField(max_length=255)
    section_type = models.CharField(
        max_length=50,
        choices=SECTION_TYPE_CHOICES,
    )
    content = StreamField(
        CONTENT_BLOCKS,
        min_num=1,
        max_num=1,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    panels = [
        # Minimal panels until Phase 5 owns the admin experience.
        "name",
        "section_type",
        "content",
    ]

    class Meta:
        verbose_name = "CMS section"
        verbose_name_plural = "CMS sections"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["section_type"]),
            models.Index(fields=["archived_at"]),
        ]
        permissions = [
            ("publish_cms_section", "Can publish CMS section"),
            ("unpublish_cms_section", "Can unpublish CMS section"),
            ("archive_cms_section", "Can archive CMS section"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        errors = {}
        stream = list(self.content) if self.content else []
        if stream and len(stream) != 1:
            errors["content"] = (
                "Content must contain exactly one section block."
            )
        elif stream and stream[0].block_type != self.section_type:
            errors["content"] = (
                "Content block type must match section_type (%s)."
                % self.section_type
            )
        if errors:
            raise ValidationError(errors)

    def get_preview_template(self, request, mode_name):
        return self.PREVIEW_TEMPLATE

    def get_preview_context(self, request, mode_name):
        context = super().get_preview_context(request, mode_name)
        context["section"] = self
        return context
