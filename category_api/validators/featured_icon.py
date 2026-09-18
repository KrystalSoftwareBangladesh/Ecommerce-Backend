#  category_api/validators/featured_icon.py
import re
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image
from rest_framework import serializers


MAX_FEATURED_ICON_SIZE = 100 * 1024  # 100 KB
FEATURED_ICON_SIZE = 64

ALLOWED_FEATURED_ICON_EXTENSIONS = {
    ".png",
    ".webp",
}

SVG_EXTENSION = ".svg"


def validate_featured_icon(uploaded_file):
    """
    Validate a featured category icon.

    Supported formats:
    - PNG
    - WebP
    - SVG

    Raster images must be exactly 64x64.
    SVG files must have a square viewBox or square dimensions.
    """

    if not uploaded_file:
        raise serializers.ValidationError(
            "Featured icon is required."
        )

    if uploaded_file.size > MAX_FEATURED_ICON_SIZE:
        raise serializers.ValidationError(
            "Featured icon must not exceed 100 KB."
        )

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in ALLOWED_FEATURED_ICON_EXTENSIONS and extension != SVG_EXTENSION:    # noqa
        raise serializers.ValidationError(
            "Only PNG, WebP, and SVG files are allowed."
        )

    if extension == SVG_EXTENSION:
        _validate_svg_icon(uploaded_file)
    else:
        _validate_raster_icon(uploaded_file)

    return uploaded_file


def _validate_raster_icon(uploaded_file):
    """
    Validate PNG/WebP dimensions and format.
    """

    try:
        uploaded_file.seek(0)

        with Image.open(uploaded_file) as image:
            if image.format not in {"PNG", "WEBP"}:
                raise serializers.ValidationError(
                    "The uploaded file is not a valid PNG or WebP image."
                )

            width, height = image.size

            if width != FEATURED_ICON_SIZE or height != FEATURED_ICON_SIZE:
                raise serializers.ValidationError(
                    "Featured icon must be exactly 64x64 pixels."
                )

    except serializers.ValidationError:
        raise

    except Exception as exc:
        raise serializers.ValidationError(
            "The uploaded raster image could not be processed."
        ) from exc

    finally:
        uploaded_file.seek(0)


def _validate_svg_icon(uploaded_file):
    """
    Validate SVG structure, dimensions, and obvious unsafe content.
    """

    try:
        uploaded_file.seek(0)
        content = uploaded_file.read()

        if not content:
            raise serializers.ValidationError(
                "The SVG file is empty."
            )

        if b"<script" in content.lower():
            raise serializers.ValidationError(
                "SVG files containing scripts are not allowed."
            )

        if re.search(
            rb"\bon[a-z]+\s*=",
            content,
            flags=re.IGNORECASE,
        ):
            raise serializers.ValidationError(
                "SVG event handlers are not allowed."
            )

        if re.search(
            rb"(javascript:|data:text/html)",
            content,
            flags=re.IGNORECASE,
        ):
            raise serializers.ValidationError(
                "Unsafe SVG content is not allowed."
            )

        root = ElementTree.fromstring(content)

        tag_name = root.tag.split("}")[-1]

        if tag_name.lower() != "svg":
            raise serializers.ValidationError(
                "The uploaded file is not a valid SVG."
            )

        view_box = root.attrib.get("viewBox")

        if view_box:
            values = view_box.replace(",", " ").split()

            if len(values) != 4:
                raise serializers.ValidationError(
                    "SVG viewBox must contain four values."
                )

            _, _, width, height = map(float, values)

            if width <= 0 or height <= 0 or width != height:
                raise serializers.ValidationError(
                    "SVG featured icon must have a square viewBox."
                )

        else:
            width = _parse_svg_dimension(root.attrib.get("width"))
            height = _parse_svg_dimension(root.attrib.get("height"))

            if width is None or height is None:
                raise serializers.ValidationError(
                    "SVG must define a square viewBox or square dimensions."
                )

            if width != height:
                raise serializers.ValidationError(
                    "SVG featured icon must be square."
                )

    except serializers.ValidationError:
        raise

    except ElementTree.ParseError as exc:
        raise serializers.ValidationError(
            "The uploaded SVG is not valid XML."
        ) from exc

    except Exception as exc:
        raise serializers.ValidationError(
            "The uploaded SVG could not be processed."
        ) from exc

    finally:
        uploaded_file.seek(0)


def _parse_svg_dimension(value):
    """
    Parse a simple SVG dimension such as:
    - 64
    - 64px
    """

    if not value:
        return None

    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)(?:px)?\s*",
        value,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return float(match.group(1))
