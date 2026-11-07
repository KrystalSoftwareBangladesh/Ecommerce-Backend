# cms_api/sections/blocks.py
"""Wagtail StructBlocks for the Phase 1 section type registry.

One StructBlock per section type (docs/cms-architecture.md 5.4). The
field schemas are the Phase 1 design approved on 2026-11-07: minimal
fields per type name, rich text limited to the whitelist, e-commerce
links held as chooser-block foreign keys, and collection blocks
carrying mode + ordered entity lists + limit (AD-17).
"""
from django.core.exceptions import ValidationError

from wagtail import blocks
from wagtail.embeds.blocks import EmbedBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.snippets.blocks import SnippetChooserBlock


RICH_TEXT_FEATURES = [
    "h2",
    "h3",
    "h4",
    "bold",
    "italic",
    "ol",
    "ul",
    "link",
    "blockquote",
    "table",
    "image",
]

INLINE_TEXT_FEATURES = ["bold", "italic", "ol", "ul", "link"]

PRODUCT_MODES = [
    ("LATEST", "Latest"),
    ("BEST_SELLERS", "Best sellers"),
    ("FEATURED", "Featured"),
    ("MANUAL", "Manual"),
    ("BY_CATEGORY", "By category"),
    ("BY_BRAND", "By brand"),
]

SIMPLE_MODES = [
    ("ALL", "All"),
    ("MANUAL", "Manual"),
]


class HeroBannerBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    subheading = blocks.CharBlock(required=False, default="")
    image = ImageChooserBlock(required=False)
    cta_label = blocks.CharBlock(required=False, default="")
    cta_url = blocks.CharBlock(required=False, default="")

    class Meta:
        label = "Hero banner"


class RichTextSectionBlock(blocks.StructBlock):
    body = blocks.RichTextBlock(features=RICH_TEXT_FEATURES)

    class Meta:
        label = "Rich text"


class HeadingBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    level = blocks.ChoiceBlock(
        choices=[("h2", "H2"), ("h3", "H3"), ("h4", "H4")],
        default="h2",
    )

    class Meta:
        label = "Heading"


class ParagraphBlock(blocks.StructBlock):
    body = blocks.RichTextBlock(features=INLINE_TEXT_FEATURES)

    class Meta:
        label = "Paragraph"


class ImageWithTextBlock(blocks.StructBlock):
    image = ImageChooserBlock(required=False)
    heading = blocks.CharBlock(required=False, default="")
    body = blocks.RichTextBlock(features=INLINE_TEXT_FEATURES)
    alignment = blocks.ChoiceBlock(
        choices=[("left", "Left"), ("right", "Right")],
        default="left",
    )

    class Meta:
        label = "Image with text"


class GalleryImageBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    caption = blocks.CharBlock(required=False, default="")


class ImageGalleryBlock(blocks.StructBlock):
    images = blocks.ListBlock(
        GalleryImageBlock(),
        min_num=1,
        label="Images",
    )

    class Meta:
        label = "Image gallery"


class VideoBlock(blocks.StructBlock):
    url = blocks.URLBlock(help_text="YouTube or Vimeo URL")
    caption = blocks.CharBlock(required=False, default="")
    thumbnail = ImageChooserBlock(required=False)

    class Meta:
        label = "Video"


class ProductSelectionBlock(blocks.StructBlock):
    """Shared shape for product collection blocks (AD-17)."""

    mode = blocks.ChoiceBlock(choices=PRODUCT_MODES, default="LATEST")
    products = blocks.ListBlock(
        SnippetChooserBlock("product_api.Product"),
        default=[],
        label="Products",
        help_text="Ordered selection used by MANUAL mode",
    )
    category = SnippetChooserBlock(
        "category_api.Category",
        required=False,
        help_text="Used by BY_CATEGORY mode",
    )
    brand = SnippetChooserBlock(
        "product_api.Brand",
        required=False,
        help_text="Used by BY_BRAND mode",
    )
    limit = blocks.IntegerBlock(default=8, min_value=1, max_value=50)

    def clean(self, value):
        value = super().clean(value)
        errors = {}
        mode = value.get("mode") if value else None
        if mode == "MANUAL" and not value.get("products"):
            errors["products"] = [
                ValidationError(
                    "At least one product is required for MANUAL mode."
                )
            ]
        elif mode == "BY_CATEGORY" and not value.get("category"):
            errors["category"] = [
                ValidationError(
                    "A category is required for BY_CATEGORY mode."
                )
            ]
        elif mode == "BY_BRAND" and not value.get("brand"):
            errors["brand"] = [
                ValidationError("A brand is required for BY_BRAND mode.")
            ]
        if errors:
            raise blocks.StructBlockValidationError(block_errors=errors)
        return value


class ProductCollectionBlock(ProductSelectionBlock):
    class Meta:
        label = "Product collection"


class ProductSliderBlock(ProductSelectionBlock):
    class Meta:
        label = "Product slider"


class CategoryCollectionBlock(blocks.StructBlock):
    mode = blocks.ChoiceBlock(choices=SIMPLE_MODES, default="ALL")
    categories = blocks.ListBlock(
        SnippetChooserBlock("category_api.Category"),
        default=[],
        label="Categories",
        help_text="Ordered selection used by MANUAL mode",
    )
    limit = blocks.IntegerBlock(default=8, min_value=1, max_value=50)

    def clean(self, value):
        value = super().clean(value)
        if (
            value
            and value.get("mode") == "MANUAL"
            and not value.get("categories")
        ):
            raise blocks.StructBlockValidationError(
                block_errors={
                    "categories": [
                        ValidationError(
                            "At least one category is required for "
                            "MANUAL mode."
                        )
                    ]
                }
            )
        return value

    class Meta:
        label = "Category collection"


class BrandCollectionBlock(blocks.StructBlock):
    mode = blocks.ChoiceBlock(choices=SIMPLE_MODES, default="ALL")
    brands = blocks.ListBlock(
        SnippetChooserBlock("product_api.Brand"),
        default=[],
        label="Brands",
        help_text="Ordered selection used by MANUAL mode",
    )
    limit = blocks.IntegerBlock(default=8, min_value=1, max_value=50)

    def clean(self, value):
        value = super().clean(value)
        if (
            value
            and value.get("mode") == "MANUAL"
            and not value.get("brands")
        ):
            raise blocks.StructBlockValidationError(
                block_errors={
                    "brands": [
                        ValidationError(
                            "At least one brand is required for MANUAL "
                            "mode."
                        )
                    ]
                }
            )
        return value

    class Meta:
        label = "Brand collection"


class TestimonialItemBlock(blocks.StructBlock):
    quote = blocks.TextBlock()
    author = blocks.CharBlock()
    role = blocks.CharBlock(required=False, default="")
    image = ImageChooserBlock(required=False)
    rating = blocks.IntegerBlock(
        required=False, min_value=1, max_value=5
    )


class TestimonialsBlock(blocks.StructBlock):
    items = blocks.ListBlock(TestimonialItemBlock(), min_num=1)

    class Meta:
        label = "Testimonials"


class FAQItemBlock(blocks.StructBlock):
    question = blocks.CharBlock()
    answer = blocks.RichTextBlock(features=INLINE_TEXT_FEATURES)


class FAQBlock(blocks.StructBlock):
    items = blocks.ListBlock(FAQItemBlock(), min_num=1)

    class Meta:
        label = "FAQ"


class StatisticItemBlock(blocks.StructBlock):
    value = blocks.CharBlock()
    label = blocks.CharBlock()
    description = blocks.CharBlock(required=False, default="")


class StatisticsBlock(blocks.StructBlock):
    items = blocks.ListBlock(StatisticItemBlock(), min_num=1)

    class Meta:
        label = "Statistics"


class CallToActionBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    subheading = blocks.CharBlock(required=False, default="")
    button_label = blocks.CharBlock()
    button_url = blocks.CharBlock()

    class Meta:
        label = "Call to action"


class PromotionalBannerBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    subheading = blocks.CharBlock(required=False, default="")
    image = ImageChooserBlock(required=False)
    button_label = blocks.CharBlock(required=False, default="")
    button_url = blocks.CharBlock(required=False, default="")

    class Meta:
        label = "Promotional banner"


class FeatureItemBlock(blocks.StructBlock):
    icon = blocks.CharBlock(required=False, default="")
    title = blocks.CharBlock()
    description = blocks.CharBlock(required=False, default="")


class FeaturesBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False, default="")
    items = blocks.ListBlock(FeatureItemBlock(), min_num=1)

    class Meta:
        label = "Features"


class ContactInformationBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False, default="")
    phone = blocks.CharBlock(required=False, default="")
    email = blocks.CharBlock(required=False, default="")
    address = blocks.CharBlock(required=False, default="")
    working_hours = blocks.CharBlock(required=False, default="")

    class Meta:
        label = "Contact information"


class EmbedSectionBlock(blocks.StructBlock):
    embed = EmbedBlock()
    caption = blocks.CharBlock(required=False, default="")

    class Meta:
        label = "Embed"
