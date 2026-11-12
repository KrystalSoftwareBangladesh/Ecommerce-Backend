# cms_api/services/navigation.py
"""Navigation menu and item management (docs/cms-architecture.md
5.5, 6, 8).

Menus and items are plain Django models (no Wagtail revisions): CRUD
is straightforward queryset work, unlike the modelcluster-backed page
composition rows. ``manage_cms_navigation`` is the single permission
for every operation here (enforced at the API layer); services only
validate business rules.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from wagtail.log_actions import log

from cms_api.models import CmsNavigationItem, CmsNavigationMenu
from cms_api.services.cache import queue_navigation_invalidation
from cms_api.services.paths import published_url_path


def _full_clean(obj):
    try:
        obj.full_clean()
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise ValidationError(exc.message_dict)
        raise ValidationError(exc.messages)


def _validate_parent(*, menu, item, parent):
    """``parent`` must belong to the same menu and must not be ``item``
    itself or one of its own descendants (which would create a cycle).
    """
    if parent is None:
        return
    if parent.menu_id != menu.pk:
        raise ValidationError({
            "parent": "parent must belong to the same menu.",
        })
    if item is None:
        return
    node = parent
    seen = set()
    while node is not None:
        if node.pk == item.pk:
            raise ValidationError({
                "parent": (
                    "A descendant cannot become an ancestor of "
                    "itself."
                ),
            })
        if node.pk in seen:
            break
        seen.add(node.pk)
        node = node.parent


@transaction.atomic
def create_menu(*, validated_data, user):
    menu = CmsNavigationMenu(
        created_by=user, updated_by=user, **validated_data,
    )
    _full_clean(menu)
    menu.save()
    log(menu, "wagtail.create", user=user)
    return menu


@transaction.atomic
def update_menu(*, menu, validated_data, user):
    # The public tree is cached by key (services/cache.py); capture
    # it before a rename so the old key's stale cache entry is
    # dropped too, not just whatever key the menu ends up with.
    old_key = menu.key
    for field, value in validated_data.items():
        setattr(menu, field, value)
    menu.updated_by = user
    _full_clean(menu)
    menu.save()
    log(menu, "wagtail.edit", user=user)
    queue_navigation_invalidation(old_key)
    if menu.key != old_key:
        queue_navigation_invalidation(menu.key)
    return menu


@transaction.atomic
def delete_menu(*, menu, user):
    """Soft-delete the menu (preferred pattern for new code);
    ``is_active=False`` also hides it from the public read."""
    menu.updated_by = user
    menu.save(update_fields=["updated_by"])
    menu.soft_delete()
    log(menu, "wagtail.delete", user=user)
    queue_navigation_invalidation(menu.key)
    return menu


def get_navigation_item(menu, item_id):
    try:
        return menu.items.get(pk=item_id)
    except CmsNavigationItem.DoesNotExist:
        raise ValidationError({"detail": "Navigation item not found."})


def _next_sort_order(menu, parent):
    return menu.items.filter(parent=parent).count()


@transaction.atomic
def add_navigation_item(*, menu, validated_data, user):
    parent = validated_data.pop("parent", None)
    _validate_parent(menu=menu, item=None, parent=parent)
    item = CmsNavigationItem(
        menu=menu,
        parent=parent,
        sort_order=_next_sort_order(menu, parent),
        **validated_data,
    )
    _full_clean(item)
    item.save()
    log(item, "wagtail.create", user=user)
    queue_navigation_invalidation(menu.key)
    return item


@transaction.atomic
def update_navigation_item(*, menu, item, validated_data, user):
    if "parent" in validated_data:
        parent = validated_data.pop("parent")
        _validate_parent(menu=menu, item=item, parent=parent)
        item.parent = parent
    for field, value in validated_data.items():
        setattr(item, field, value)
    _full_clean(item)
    item.save()
    log(item, "wagtail.edit", user=user)
    queue_navigation_invalidation(menu.key)
    return item


@transaction.atomic
def remove_navigation_item(*, menu, item, user):
    # Logged before delete(): Django clears the in-memory pk once the
    # row is actually removed, and log_action() requires a pk.
    log(item, "wagtail.delete", user=user)
    item.delete()
    queue_navigation_invalidation(menu.key)


@transaction.atomic
def reorder_navigation_items(*, menu, parent_id, order, user):
    siblings = {
        row.pk: row for row in menu.items.filter(parent_id=parent_id)
    }
    if sorted(order) != sorted(siblings):
        raise ValidationError({
            "order": (
                "order must list every sibling item id exactly once"
            ),
        })
    for position, item_id in enumerate(order):
        CmsNavigationItem.objects.filter(pk=item_id).update(
            sort_order=position,
        )
    log(
        menu, "cms_api.navigation.reorder", user=user,
        data={"parent_id": parent_id, "order": order},
    )
    queue_navigation_invalidation(menu.key)


def _page_is_publicly_visible(page):
    return page is not None and page.live and page.archived_at is None


def resolve_navigation_tree(menu):
    """Public menu tree (draft isolation, spec 6).

    Rows are filtered to ``is_visible`` and, for PAGE items, a
    currently live/non-archived target; an invisible or unresolvable
    item's whole subtree is pruned (a hidden parent in a rendered menu
    would otherwise leave orphaned children).
    """
    items = list(
        menu.items.select_related("page").order_by("sort_order")
    )
    children_by_parent = {}
    for item in items:
        children_by_parent.setdefault(item.parent_id, []).append(item)

    def build(parent_id):
        nodes = []
        for item in children_by_parent.get(parent_id, []):
            if not item.is_visible:
                continue
            if item.page_id:
                if not _page_is_publicly_visible(item.page):
                    continue
                url = published_url_path(item.page)
            else:
                url = item.external_url
            nodes.append({
                "id": item.pk,
                "label": item.label,
                "url": url,
                "open_in_new_tab": item.open_in_new_tab,
                "children": build(item.pk),
            })
        return nodes

    return build(None)
