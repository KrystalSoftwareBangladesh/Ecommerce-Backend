# product_api/utils/image_processing.py
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


def optimize_image_file(image_file, max_dimension=500):
    """
    Resize an image so its largest dimension does not exceed
    max_dimension while preserving its aspect ratio and format.

    Returns:
        tuple: (optimized_file, metadata)
    """
    try:
        image_file.seek(0)

        with Image.open(image_file) as source:
            image_format = source.format

            if image_format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValidationError(
                    'Unsupported image format.'
                )

            image = ImageOps.exif_transpose(source)
            image.load()

        original_width, original_height = image.size

        if max(original_width, original_height) <= max_dimension:
            raise ValidationError(
                'Image dimensions are already within the limit.'
            )

        ratio = max_dimension / max(original_width, original_height)

        new_width = round(original_width * ratio)
        new_height = round(original_height * ratio)

        image = image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS,
        )

        output = BytesIO()

        save_options = {'optimize': True}

        if image_format == 'JPEG':
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')

            save_options.update({
                'quality': 85,
                'progressive': True,
            })

        elif image_format == 'WEBP':
            save_options.update({
                'quality': 85,
                'method': 6,
            })

        elif image_format == 'PNG':
            pass

        image.save(
            output,
            format=image_format,
            **save_options,
        )

        output.seek(0)

        original_name = Path(image_file.name).name

        optimized_file = ContentFile(
            output.getvalue(),
            name=original_name,
        )

        metadata = {
            'original_dimensions': {
                'width': original_width,
                'height': original_height,
            },
            'optimized_dimensions': {
                'width': new_width,
                'height': new_height,
            },
            'original_size': image_file.size,
            'optimized_size': optimized_file.size,
        }

        return optimized_file, metadata

    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(
            'Unable to process the uploaded image.'
        ) from exc

    finally:
        image_file.seek(0)
