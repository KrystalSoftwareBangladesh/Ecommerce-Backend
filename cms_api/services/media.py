# cms_api/services/media.py
"""CMS media management (docs/cms-architecture.md 5.6, 6, 11).

Upload validation reads its limits from ``CmsMediaConfig.get_solo()``
rather than Wagtail's own ``WAGTAILIMAGES_*``/``WAGTAILDOCS_*``
settings: those are read only by Wagtail's admin *form fields*
(``wagtail.images.fields.WagtailImageField`` et al.), never by a plain
model ``full_clean()`` or a DRF serializer, so they have no effect on
this API unless reimplemented here. The image check adapts the
existing Pillow-based pattern in
``product_api/serializers/product_image.py`` (open + ``verify()``,
checking the real decoded format, not the filename extension — never
trusting the browser-supplied ``content_type``) instead of adding a
new dependency.

Reference-aware deletion mirrors ``cms_api/services/cms_section.py:
delete_section`` exactly: a referenced image/document is never
deletable (no ``acknowledge`` override), returning the same structured
dependency shape every other CMS delete guard uses.
"""
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from django.db import transaction

from rest_framework.exceptions import ValidationError

from wagtail.documents.models import Document
from wagtail.images.models import Image
from wagtail.log_actions import log
from wagtail.models import ReferenceIndex

from cms_api.models import CmsMediaConfig

# Pillow format names, lower-cased, keyed by the file extension they
# must match. "jpg" is the common extension for the "jpeg" format.
_PILLOW_FORMAT_BY_EXTENSION = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "webp": "webp",
    "gif": "gif",
}


def _extension_of(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_image_file(file, config=None):
    """Validate an uploaded image against ``CmsMediaConfig`` (size,
    extension, real decoded format, pixel count). Never trusts
    ``file.content_type``: the format check re-opens and decodes the
    file with Pillow."""
    config = config or CmsMediaConfig.get_solo()

    size = getattr(file, "size", None)
    if size is not None and size > config.max_image_upload_size:
        raise ValidationError({
            "file": (
                "Image is too large. Maximum size is %d bytes."
                % config.max_image_upload_size
            ),
        })

    extension = _extension_of(file.name or "")
    if extension not in config.allowed_image_extensions:
        raise ValidationError({
            "file": (
                "Unsupported image format. Allowed formats: %s."
                % ", ".join(config.allowed_image_extensions)
            ),
        })

    try:
        with PILImage.open(file) as image_file:
            image_format = image_file.format
            width, height = image_file.size
            image_file.verify()
    except (UnidentifiedImageError, OSError):
        raise ValidationError({"file": "Uploaded file is not a valid image."})
    finally:
        file.seek(0)

    normalised_format = (image_format or "").lower()
    expected_format = _PILLOW_FORMAT_BY_EXTENSION.get(extension)
    if not normalised_format or normalised_format != expected_format:
        raise ValidationError({
            "file": (
                "The file extension does not match the actual "
                "image format."
            ),
        })

    if width * height > config.max_image_pixels:
        raise ValidationError({
            "file": (
                "Image has too many pixels. Maximum is %d."
                % config.max_image_pixels
            ),
        })


def validate_document_file(file, config=None):
    """Validate an uploaded document against ``CmsMediaConfig``
    (size, extension). Documents are not necessarily a format Pillow
    can decode, so this is extension + size only — the same ceiling
    Wagtail's own ``Document.clean()`` uses."""
    config = config or CmsMediaConfig.get_solo()

    size = getattr(file, "size", None)
    if size is not None and size > config.max_document_upload_size:
        raise ValidationError({
            "file": (
                "Document is too large. Maximum size is %d bytes."
                % config.max_document_upload_size
            ),
        })

    extension = _extension_of(file.name or "")
    if extension not in config.allowed_document_extensions:
        raise ValidationError({
            "file": (
                "Unsupported document format. Allowed formats: %s."
                % ", ".join(config.allowed_document_extensions)
            ),
        })


def _reference_dependencies(obj):
    dependencies = []
    grouped = ReferenceIndex.get_grouped_references_to(obj)
    for source, refs in grouped:
        dependencies.append({
            "model": source._meta.label if source else None,
            "object_id": refs[0].object_id,
            "object": str(source) if source else None,
            "fields": sorted({
                ref.describe_source_field() for ref in refs
            }),
        })
    return dependencies


def _guard_delete(obj):
    dependencies = _reference_dependencies(obj)
    if dependencies:
        raise ValidationError({
            "detail": (
                "Cannot delete: this item is referenced by other "
                "content."
            ),
            "dependencies": dependencies,
        })


@transaction.atomic
def create_image(*, validated_data, user):
    file = validated_data["file"]
    validate_image_file(file)
    image = Image(
        title=validated_data.get("title") or file.name,
        file=file,
        description=validated_data.get("description", ""),
        uploaded_by_user=user,
    )
    image.full_clean()
    image.save()
    log(image, "wagtail.create", user=user)
    return image


@transaction.atomic
def update_image(*, image, validated_data, user):
    if "file" in validated_data:
        validate_image_file(validated_data["file"])
        image.file = validated_data["file"]
    if "title" in validated_data:
        image.title = validated_data["title"]
    if "description" in validated_data:
        image.description = validated_data["description"]
    image.full_clean()
    image.save()
    log(image, "wagtail.edit", user=user)
    return image


@transaction.atomic
def delete_image(*, image, user):
    _guard_delete(image)
    # Logged before delete(): Django clears the in-memory pk once the
    # row is actually removed, and log_action() requires a pk.
    log(image, "wagtail.delete", user=user)
    image.delete()


@transaction.atomic
def create_document(*, validated_data, user):
    file = validated_data["file"]
    validate_document_file(file)
    document = Document(
        title=validated_data.get("title") or file.name,
        file=file,
        uploaded_by_user=user,
    )
    document.full_clean()
    document.save()
    log(document, "wagtail.create", user=user)
    return document


@transaction.atomic
def update_document(*, document, validated_data, user):
    if "file" in validated_data:
        validate_document_file(validated_data["file"])
        document.file = validated_data["file"]
    if "title" in validated_data:
        document.title = validated_data["title"]
    document.full_clean()
    document.save()
    log(document, "wagtail.edit", user=user)
    return document


@transaction.atomic
def delete_document(*, document, user):
    _guard_delete(document)
    # Logged before delete(): Django clears the in-memory pk once the
    # row is actually removed, and log_action() requires a pk.
    log(document, "wagtail.delete", user=user)
    document.delete()


@transaction.atomic
def update_media_config(*, config, validated_data, user):
    for field, value in validated_data.items():
        setattr(config, field, value)
    config.updated_by = user
    config.full_clean()
    config.save()
    log(config, "wagtail.edit", user=user)
    return config
