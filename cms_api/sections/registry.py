# cms_api/sections/registry.py
"""Phase 1 section-type registry (docs/cms-architecture.md 5.4).

`SECTION_TYPES` maps the stable API section type key to its StructBlock
in the documented order. `CONTENT_BLOCKS` builds the StreamField block
list for `CmsSection.content`, and `section_type_schemas()` renders the
deterministic JSON schema served by the section-types API.
"""
from collections import OrderedDict

from wagtail import blocks
from wagtail.embeds.blocks import EmbedBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.snippets.blocks import SnippetChooserBlock

from .blocks import (
    BrandCollectionBlock,
    CallToActionBlock,
    CategoryCollectionBlock,
    ContactInformationBlock,
    EmbedSectionBlock,
    FAQBlock,
    FeaturesBlock,
    HeadingBlock,
    HeroBannerBlock,
    ImageGalleryBlock,
    ImageWithTextBlock,
    ParagraphBlock,
    ProductCollectionBlock,
    ProductSliderBlock,
    PromotionalBannerBlock,
    RichTextSectionBlock,
    StatisticsBlock,
    TestimonialsBlock,
    VideoBlock,
)


SECTION_TYPES = OrderedDict([
    ("hero_banner", HeroBannerBlock()),
    ("rich_text", RichTextSectionBlock()),
    ("heading", HeadingBlock()),
    ("paragraph", ParagraphBlock()),
    ("image_with_text", ImageWithTextBlock()),
    ("image_gallery", ImageGalleryBlock()),
    ("video", VideoBlock()),
    ("product_collection", ProductCollectionBlock()),
    ("product_slider", ProductSliderBlock()),
    ("category_collection", CategoryCollectionBlock()),
    ("brand_collection", BrandCollectionBlock()),
    ("testimonials", TestimonialsBlock()),
    ("faq", FAQBlock()),
    ("statistics", StatisticsBlock()),
    ("call_to_action", CallToActionBlock()),
    ("promotional_banner", PromotionalBannerBlock()),
    ("features", FeaturesBlock()),
    ("contact_information", ContactInformationBlock()),
    ("embed", EmbedSectionBlock()),
])

CONTENT_BLOCKS = list(SECTION_TYPES.items())

SECTION_TYPE_CHOICES = [
    (key, block.meta.label) for key, block in SECTION_TYPES.items()
]

_TYPE_NAMES = {
    blocks.CharBlock: "string",
    blocks.TextBlock: "text",
    blocks.IntegerBlock: "integer",
    blocks.FloatBlock: "float",
    blocks.DecimalBlock: "decimal",
    blocks.BooleanBlock: "boolean",
    blocks.DateBlock: "date",
    blocks.DateTimeBlock: "datetime",
    blocks.TimeBlock: "time",
    blocks.EmailBlock: "email",
    blocks.URLBlock: "url",
    blocks.RichTextBlock: "richtext",
    ImageChooserBlock: "image",
    EmbedBlock: "embed",
}


def _snippet_model_name(block):
    return block.target_model._meta.label_lower


def _label(block):
    return getattr(block, "label", None) or block.name or ""


def _required(block):
    # block.required on a FieldBlock resolves the form field (and its
    # widget), which needs snippet registration for chooser blocks.
    # Block.__new__ captures the constructor kwargs for every block
    # class, so read the declared value from there.
    _args, kwargs = block._constructor_args
    return kwargs.get("required", True)


def describe_block(block):
    """Return a deterministic JSON schema for one block."""
    if isinstance(block, blocks.ListBlock):
        return {
            "type": "list",
            "label": _label(block),
            "required": _required(block),
            "min_items": block.meta.min_num,
            "max_items": block.meta.max_num,
            "item": describe_block(block.child_block),
        }
    if isinstance(block, blocks.StructBlock):
        fields = []
        for name, child in block.child_blocks.items():
            schema = describe_block(child)
            schema["name"] = name
            fields.append(schema)
        return {
            "type": "object",
            "label": _label(block),
            "required": _required(block),
            "fields": fields,
        }
    if isinstance(block, blocks.ChoiceBlock):
        # BaseChoiceBlock keeps the normalised choices list in
        # _constructor_kwargs; the public .choices attribute is the
        # class-level placeholder.
        raw_choices = block._constructor_kwargs.get("choices") or []
        schema = {
            "type": "choice",
            "label": _label(block),
            "required": _required(block),
            "choices": [
                {"value": value, "label": str(label)}
                for value, label in raw_choices
            ],
        }
        if block.meta.default is not None:
            schema["default"] = block.meta.default
        return schema
    if isinstance(block, SnippetChooserBlock):
        return {
            "type": "entity",
            "label": _label(block),
            "required": _required(block),
            "model": _snippet_model_name(block),
        }
    if isinstance(block, blocks.FieldBlock):
        schema = {
            "type": _TYPE_NAMES.get(type(block), "string"),
            "label": _label(block),
            "required": _required(block),
        }
        if isinstance(block, blocks.RichTextBlock):
            schema["features"] = list(block.features)
        if isinstance(block, blocks.IntegerBlock):
            schema["min_value"] = block.field.min_value
            schema["max_value"] = block.field.max_value
        if block.meta.default is not None:
            schema["default"] = block.meta.default
        return schema
    return {
        "type": "unknown",
        "label": _label(block),
        "required": block.required,
    }


def section_type_schemas():
    """Full schema list for the section-types API endpoint."""
    return [
        {
            "type": key,
            "label": block.meta.label,
            "content": describe_block(block),
        }
        for key, block in SECTION_TYPES.items()
    ]
