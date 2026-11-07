# cms_api/wagtail_hooks.py
"""Wagtail registrations for the CMS (docs/cms-architecture.md).

Product, Category and Brand are registered as snippets because the
section registry's chooser blocks (product_collection,
product_slider, category_collection, brand_collection) use
``SnippetChooserBlock``, which requires snippet models to resolve
their choosers and validate content.

Side effect (reported in the Phase 1 report): these three models
appear in the Wagtail admin "Snippets" menu. That admin surface is
Phase 5's concern; registration here is for the content pipeline.
"""
from django.utils.translation import gettext_lazy as _

from wagtail import hooks
from wagtail.models import ReferenceIndex
from wagtail.snippets.models import register_snippet

from category_api.models import Category
from cms_api.models import CmsSection
from product_api.models import Brand, Product

register_snippet(CmsSection)
register_snippet(Product)
register_snippet(Category)
register_snippet(Brand)

# Track CmsSection as a reference source so its product/category/
# brand references are recorded in the ReferenceIndex (delete guards
# on those entities stay accurate).
ReferenceIndex.register_model(CmsSection)


@hooks.register("register_log_actions")
def register_cms_log_actions(actions):
    """Register log actions not provided by Wagtail core.

    ``wagtail.create``/``wagtail.edit``/``wagtail.delete`` exist in
    core; ``cms_api.archive`` covers the archive operation, which has
    no Wagtail-native action.
    """
    actions.register_action(
        "cms_api.archive", _("Archive"), _("Archived")
    )
