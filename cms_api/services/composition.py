# cms_api/services/composition.py
"""Page composition writes (docs/cms-architecture.md 5.3, 7.3).

A composition row is either a link to a global ``CmsSection`` or
local content holding exactly one registry block (XOR enforced on
the model and in the serializers).

Every write commits rows through the page's in-memory child-relation
state (modelcluster) so the next page revision serializes the new
composition, and then snapshots a page revision. Composition writes
are optimistic-locked like page writes (``base_revision_id``).
"""
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from cms_api.models import CmsPageSection
from cms_api.services.cms_section import (
    _check_base_revision,
    _full_clean,
)


def make_section_row(page, data, sort_order):
    """Build an unsaved CmsPageSection row for ``page``.

    ``data`` accepts both serializer-validated dicts and template
    seed dicts (name/global_section/content).
    """
    global_section = data.get("global_section")
    name = data.get("name") or ""
    if global_section is not None and not name:
        name = global_section.name
    row = CmsPageSection(
        page=page,
        name=name,
        global_section=global_section,
        content=data.get("content") or None,
        sort_order=sort_order,
    )
    if data.get("archived"):
        row.archived_at = timezone.now()
    return row


def get_page_section(page, section_id):
    """Return the row or raise 400 like the section service does.

    Rows come from the page's mutable in-memory child list: modelcluster
    only commits rows tracked in that list on ``page.save()``, and
    ``.all()`` returns untracked live-query objects when the list has
    not been built yet.
    """
    for row in page.sections.get_object_list():
        if str(row.pk) == str(section_id):
            return row
    raise ValidationError({"detail": "Page section not found."})


def apply_section_rows(page, sections_data):
    """Replace the whole composition (no revision snapshot)."""
    page.sections.clear()
    for index, data in enumerate(sections_data):
        row = make_section_row(page, data, sort_order=index)
        _full_clean(row)
        page.sections.add(row)
    page.save()


def add_page_section(
    *, page, validated_data, user, base_revision_id=None,
):
    _check_base_revision(page, base_revision_id)
    row = make_section_row(
        page, validated_data,
        sort_order=len(list(page.sections.all())),
    )
    _full_clean(row)
    page.sections.add(row)
    page.save()
    page.save_revision(user=user, log_action="cms_api.update")
    return row


def update_page_section(
    *, page, section, validated_data, user, base_revision_id=None,
):
    _check_base_revision(page, base_revision_id)
    if "name" in validated_data:
        section.name = validated_data["name"]
    if "content" in validated_data:
        section.content = validated_data["content"] or None
        if section.content:
            # Replacing a global reference with local content.
            section.global_section = None
    if "global_section" in validated_data:
        section.global_section = validated_data["global_section"]
        if section.global_section:
            # Attaching a global section replaces local content.
            section.content = None
            if not section.name:
                section.name = section.global_section.name
    if "archived" in validated_data:
        if validated_data["archived"]:
            section.archived_at = section.archived_at or timezone.now()
        else:
            section.archived_at = None
    _full_clean(section)
    page.save()
    page.save_revision(user=user, log_action="cms_api.update")
    return section


def remove_page_section(
    *, page, section, user, base_revision_id=None,
):
    _check_base_revision(page, base_revision_id)
    page.sections.remove(section)
    page.save()
    page.save_revision(user=user, log_action="cms_api.update")


def reorder_page_sections(
    *, page, order, user, base_revision_id=None,
):
    _check_base_revision(page, base_revision_id)
    rows = {
        row.pk: row for row in page.sections.get_object_list()
    }
    if sorted(order) != sorted(rows):
        raise ValidationError(
            {"order": (
                "order must list every page section id exactly once"
            )}
        )
    for position, row_id in enumerate(order):
        rows[row_id].sort_order = position
    page.save()
    page.save_revision(user=user, log_action="cms_api.update")


def duplicate_page_section(
    *, page, section, user, base_revision_id=None,
):
    _check_base_revision(page, base_revision_id)
    copy = make_section_row(
        page,
        {
            "name": section.name,
            "global_section": section.global_section,
            "content": section.content or None,
        },
        sort_order=len(list(page.sections.all())),
    )
    _full_clean(copy)
    page.sections.add(copy)
    page.save()
    page.save_revision(user=user, log_action="cms_api.update")
    return copy
