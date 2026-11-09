# cms_api/models/cms_media.py
"""CmsMediaConfig singleton (docs/cms-architecture.md 5.6).

Max upload sizes, allowed document extensions, and allowed image
types for the media management API. Anchors the custom permission
``manage_cms_media`` (``wagtailimages.Image``/``wagtaildocs.Document``
cannot declare ``Meta.permissions``, so the codename lives here and a
small dedicated permission class checks
``user.has_perm("cms_api.manage_cms_media")``).

Exactly one row can ever exist: ``save()`` always writes to
``SINGLETON_PK``, and the ``CheckConstraint`` below is the
database-level backstop (a raw insert bypassing ``save()`` cannot
create a second row either). ``get_solo()`` is the one way callers
should read it — it creates the row with its defaults on first access
so there is never a "no config yet" state to handle.
"""
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel, UserStampedModel

SINGLETON_PK = 1

DEFAULT_ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
DEFAULT_ALLOWED_DOCUMENT_EXTENSIONS = ["pdf"]


def default_allowed_image_extensions():
    return list(DEFAULT_ALLOWED_IMAGE_EXTENSIONS)


def default_allowed_document_extensions():
    return list(DEFAULT_ALLOWED_DOCUMENT_EXTENSIONS)


class CmsMediaConfig(TimeStampedModel, UserStampedModel):
    SINGLETON_PK = SINGLETON_PK

    max_image_upload_size = models.PositiveBigIntegerField(
        default=10 * 1024 * 1024,
        help_text="Maximum image upload size, in bytes.",
    )
    max_image_pixels = models.PositiveBigIntegerField(
        default=128_000_000,
        help_text="Maximum image pixel count (width x height).",
    )
    allowed_image_extensions = models.JSONField(
        default=default_allowed_image_extensions,
        help_text="Lower-case file extensions, without the dot.",
    )
    max_document_upload_size = models.PositiveBigIntegerField(
        default=20 * 1024 * 1024,
        help_text="Maximum document upload size, in bytes.",
    )
    allowed_document_extensions = models.JSONField(
        default=default_allowed_document_extensions,
        help_text="Lower-case file extensions, without the dot.",
    )

    class Meta:
        verbose_name = "CMS media configuration"
        verbose_name_plural = "CMS media configuration"
        constraints = [
            models.CheckConstraint(
                check=models.Q(pk=SINGLETON_PK),
                name="cms_mediaconfig_singleton",
            ),
        ]
        permissions = [
            ("manage_cms_media", "Can manage CMS media"),
        ]

    def __str__(self):
        return "CMS media configuration"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
