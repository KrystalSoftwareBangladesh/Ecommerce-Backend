# cms_api/models/cms_navigation.py
"""CmsNavigationMenu / CmsNavigationItem (docs/cms-architecture.md
5.5).

Navigation is independent of the page tree: a menu is an ordered,
nestable list of items, each pointing at either a `CmsPage` or an
external URL, never both. `manage_cms_navigation` is the single
permission covering every navigation operation (menu and item CRUD
alike) per the permission matrix (§8) — there is no separate
add/change/delete split for this resource.
"""
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)


class NavigationLinkType(models.TextChoices):
    PAGE = 'PAGE', 'Page'
    EXTERNAL = 'EXTERNAL', 'External URL'


class CmsNavigationMenu(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    """A named menu (HEADER, FOOTER, or a custom key).

    ``is_active`` (from ``SoftDeleteModel``) doubles as both "enabled"
    and "not deleted" — there is no separate toggle, matching how
    other CMS models reuse the same flag (e.g. ``CmsSection``'s
    ``is_active`` queryset filter).
    """

    name = models.CharField(max_length=255)
    key = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "CMS navigation menu"
        verbose_name_plural = "CMS navigation menus"
        ordering = ["name"]
        permissions = [
            ("manage_cms_navigation", "Can manage CMS navigation"),
        ]

    def __str__(self):
        return self.name


class CmsNavigationItem(TimeStampedModel):
    """One node in a menu's tree.

    Exactly one of ``page``/``external_url`` is set, matching
    ``link_type`` (``CheckConstraint`` below; also enforced in
    ``clean()`` and the write serializers). ``parent`` nests items
    within the same menu; cycle prevention is a service-layer concern
    (a ``CheckConstraint`` cannot see other rows).
    """

    menu = models.ForeignKey(
        CmsNavigationMenu,
        on_delete=models.CASCADE,
        related_name="items",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    label = models.CharField(max_length=255)
    link_type = models.CharField(
        max_length=20,
        choices=NavigationLinkType.choices,
    )
    page = models.ForeignKey(
        "cms_api.CmsPage",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    external_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        validators=[URLValidator(schemes=["http", "https"])],
    )
    is_visible = models.BooleanField(default=True)
    open_in_new_tab = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "CMS navigation item"
        verbose_name_plural = "CMS navigation items"
        ordering = ["sort_order"]
        indexes = [
            models.Index(fields=["menu", "parent", "sort_order"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        link_type=NavigationLinkType.PAGE,
                        page__isnull=False,
                        external_url="",
                    )
                    | (
                        models.Q(
                            link_type=NavigationLinkType.EXTERNAL,
                            page__isnull=True,
                        )
                        & ~models.Q(external_url="")
                    )
                ),
                name="cms_navigationitem_exactly_one_link_target",
            ),
        ]

    def __str__(self):
        return self.label

    def clean(self):
        super().clean()
        errors = {}
        has_page = self.page_id is not None
        has_external_url = bool(self.external_url)
        if self.link_type == NavigationLinkType.PAGE:
            if not has_page:
                errors["page"] = (
                    "page is required when link_type is PAGE."
                )
            if has_external_url:
                errors["external_url"] = (
                    "external_url must be blank when link_type is "
                    "PAGE."
                )
        elif self.link_type == NavigationLinkType.EXTERNAL:
            if not has_external_url:
                errors["external_url"] = (
                    "external_url is required when link_type is "
                    "EXTERNAL."
                )
            if has_page:
                errors["page"] = (
                    "page must not be set when link_type is "
                    "EXTERNAL."
                )
        if self.parent_id is not None and self.parent_id == self.pk:
            errors["parent"] = "An item cannot be its own parent."
        if errors:
            raise ValidationError(errors)
