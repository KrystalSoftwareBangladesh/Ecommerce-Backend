# content_security_api/services/content_sources.py
"""
Registry of the content the scanner knows how to read.

This is the only content-type-aware layer in the scanner. It maps a
`ScanContentType` onto a model, the fields to scan and a queryset, and it
contains no detection logic whatsoever. Supporting a new content type -
blog, SEO metadata, static page, brand, collection - means adding one entry
here; the detectors, scoring and persistence stay untouched.
"""
from rest_framework.exceptions import ValidationError

from category_api.models import Category
from product_api.models import Product

from content_security_api.models import ScanContentType


class ContentSource:
    """
    Where one content type's scannable text lives.
    """

    def __init__(self, content_type, model, fields, label_field):
        self.content_type = content_type
        self.model = model
        self.fields = fields
        self.label_field = label_field

    def get_queryset(self):
        """
        Objects eligible for scanning, loading only the columns needed.

        Soft-deleted rows are excluded, matching how `Product` and
        `Category` are read everywhere else in the project.
        """
        return self.model.objects.filter(
            deleted_at__isnull=True
        ).only('id', self.label_field, *self.fields)

    def get_object(self, object_id):
        """
        One scannable object, or a validation error when it does not exist.
        """
        try:
            return self.get_queryset().get(pk=object_id)
        except self.model.DoesNotExist:
            raise ValidationError(
                f'{self.content_type} {object_id} does not exist.'
            )

    def get_label(self, obj):
        return getattr(obj, self.label_field, '') or ''

    def get_content(self, obj, field_name):
        return getattr(obj, field_name, '') or ''


CONTENT_SOURCES = {
    ScanContentType.PRODUCT: ContentSource(
        content_type=ScanContentType.PRODUCT,
        model=Product,
        fields=['description', 'short_description', 'specifications'],
        label_field='name',
    ),
    ScanContentType.CATEGORY: ContentSource(
        content_type=ScanContentType.CATEGORY,
        model=Category,
        fields=['description'],
        label_field='name',
    ),
}


def get_content_source(content_type):
    """
    Look up a registered content source.
    """
    source = CONTENT_SOURCES.get(content_type)

    if source is None:
        raise ValidationError(
            f'Content type {content_type} is not supported by the scanner.'
        )

    return source


def get_object_label(content_type, object_id):
    """
    Human-readable label of a scanned object, or an empty string when it no
    longer exists. Never raises, so a scan result stays readable after its
    object is removed.
    """
    source = CONTENT_SOURCES.get(content_type)

    if source is None:
        return ''

    obj = source.get_queryset().filter(pk=object_id).first()

    if obj is None:
        return ''

    return source.get_label(obj)


def resolve_fields(source, field_names=None):
    """
    Validate a requested subset of fields, defaulting to all of them.
    """
    if not field_names:
        return list(source.fields)

    unknown = [
        field_name
        for field_name in field_names
        if field_name not in source.fields
    ]

    if unknown:
        raise ValidationError(
            f'Unsupported field(s) for {source.content_type}: '
            f'{", ".join(unknown)}.'
        )

    return list(field_names)
