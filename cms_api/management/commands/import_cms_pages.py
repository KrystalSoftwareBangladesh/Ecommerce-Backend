# cms_api/management/commands/import_cms_pages.py

import html
import json
# import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from wagtail.models import Page, Site

from cms_api.models import CmsPage, CmsPageSection


HOME_LEGACY_ID = 5289
DEFAULT_SITE_HOSTNAME = "localhost"


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip()


def parse_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(
            parsed,
            timezone.get_current_timezone(),
        )

    return parsed


def unique_slug(parent, original_slug, legacy_id, current_page=None):
    base_slug = original_slug or f"page-{legacy_id}"
    base_slug = base_slug[:255]

    candidate = base_slug
    suffix = 2

    while True:
        siblings = parent.get_children().filter(
            slug=candidate
        )

        if current_page:
            siblings = siblings.exclude(pk=current_page.pk)

        if not siblings.exists():
            return candidate

        suffix_text = f"-{suffix}"
        candidate = f"{base_slug[:255 - len(suffix_text)]}{suffix_text}"
        suffix += 1


def extract_elementor_text(elementor_data):
    """
    Extract only straightforward text-based Elementor widgets.

    The original Elementor JSON remains preserved in legacy_data.
    This is not a full Elementor layout conversion.
    """

    if not elementor_data:
        return "", 0

    try:
        elements = (
            json.loads(elementor_data)
            if isinstance(elementor_data, str)
            else elementor_data
        )
    except (TypeError, json.JSONDecodeError):
        return "", 1

    output = []
    unsupported_count = 0

    def walk(nodes):
        nonlocal unsupported_count

        if not isinstance(nodes, list):
            return

        for node in nodes:
            if not isinstance(node, dict):
                continue

            widget_type = node.get("widgetType")
            settings = node.get("settings") or {}

            if node.get("elType") == "widget":
                if widget_type == "heading":
                    title = clean_text(settings.get("title"))

                    if title:
                        level = clean_text(
                            settings.get("header_size")
                        ).lower()

                        if level not in {
                            "h1", "h2", "h3", "h4", "h5", "h6"
                        }:
                            level = "h2"

                        output.append(
                            f"<{level}>{html.escape(title)}</{level}>"
                        )

                elif widget_type == "text-editor":
                    editor = settings.get("editor") or ""
                    if editor:
                        output.append(str(editor))

                elif widget_type == "html":
                    content = settings.get("html") or ""
                    if content:
                        output.append(str(content))

                elif widget_type == "button":
                    label = clean_text(settings.get("text"))
                    link = settings.get("link") or {}
                    url = clean_text(link.get("url"))

                    if label:
                        escaped_label = html.escape(label)

                        if url:
                            output.append(
                                f'<p><a href="{html.escape(url, quote=True)}">'
                                f"{escaped_label}</a></p>"
                            )
                        else:
                            output.append(f"<p>{escaped_label}</p>")

                elif widget_type:
                    unsupported_count += 1

            walk(node.get("elements") or [])

    walk(elements)

    return "\n".join(output), unsupported_count


def get_import_content(item):
    """
    Prefer WordPress post_content to avoid duplicating content
    that also exists in Elementor text widgets.

    If post_content is empty, extract basic text from Elementor.
    """

    post_content = item.get("post_content") or ""

    if post_content.strip():
        return post_content, "wordpress_content", 0

    metadata = item.get("metadata") or {}
    elementor_data = metadata.get("_elementor_data")

    if elementor_data:
        extracted, unsupported = extract_elementor_text(
            elementor_data
        )

        if extracted.strip():
            return extracted, "elementor_text_extraction", unsupported

        return "", "elementor_preserved_only", unsupported

    return "", "empty", 0


def get_seo_values(metadata):
    metadata = metadata or {}

    description = clean_text(
        metadata.get("rank_math_description")
    )

    focus_keyword = clean_text(
        metadata.get("rank_math_focus_keyword")
    )

    facebook_title = clean_text(
        metadata.get("rank_math_facebook_title")
    )

    facebook_description = clean_text(
        metadata.get("rank_math_facebook_description")
    )

    canonical_url = clean_text(
        metadata.get("rank_math_canonical_url")
    )

    robots = clean_text(
        metadata.get("rank_math_robots")
    ).lower()

    return {
        "seo_description": description[:500],
        "meta_keywords": focus_keyword[:255],
        "og_title": facebook_title[:255],
        "og_description": facebook_description[:500],
        "canonical_url": canonical_url,
        "seo_noindex": "noindex" in robots,
        "seo_nofollow": "nofollow" in robots,
    }


def set_page_fields(page, item, slug):
    metadata = item.get("metadata") or {}
    seo = get_seo_values(metadata)

    page.title = (
        clean_text(item.get("post_title"))
        or f"Untitled page {item['legacy_id']}"
    )

    page.slug = slug
    page.template_key = "blank"

    for field, value in seo.items():
        setattr(page, field, value)

    # Keep the entire original source record, including:
    # post_content, builder JSON, SEO metadata, and WordPress IDs.
    page.legacy_data = item

    # WordPress publication dates remain available in legacy_data.
    # Wagtail publication timestamps are managed by Wagtail revisions.


def replace_local_content(page, item):
    """
    Replace imported page sections with one RichText section
    when usable source content is available.
    """

    page.sections.all().delete()

    content, source_type, unsupported_widgets = get_import_content(
        item
    )

    if content.strip():
        CmsPageSection.objects.create(
            page=page,
            name="Imported WordPress content",
            content=[
                (
                    "rich_text",
                    {
                        "body": content,
                    },
                )
            ],
        )

    return {
        "source_type": source_type,
        "unsupported_widgets": unsupported_widgets,
        "has_content": bool(content.strip()),
    }


class Command(BaseCommand):
    help = "Import WordPress pages into the Wagtail CMS."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to cms_pages.json",
        )

        parser.add_argument(
            "--site-hostname",
            default=DEFAULT_SITE_HOSTNAME,
            help="Wagtail Site hostname whose root page will be replaced.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = Path(options["json_file"])
        hostname = options["site_hostname"]

        if not json_file.exists():
            raise CommandError(
                f"JSON file does not exist: {json_file}"
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Loading WordPress pages from {json_file}"
            )
        )

        try:
            with json_file.open("r", encoding="utf-8") as fp:
                pages = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(
                f"Unable to read JSON file: {exc}"
            )

        if not isinstance(pages, list):
            raise CommandError(
                "Expected the JSON root to be an array."
            )

        if not pages:
            raise CommandError("No pages found in JSON.")

        # -------------------------------------------------
        # Validate input.
        # -------------------------------------------------

        ids = [item.get("legacy_id") for item in pages]

        if any(not legacy_id for legacy_id in ids):
            raise CommandError(
                "One or more pages have a missing legacy_id."
            )

        if len(ids) != len(set(ids)):
            raise CommandError(
                "Duplicate legacy_id values found in JSON."
            )

        home_items = [
            item for item in pages
            if item.get("legacy_id") == HOME_LEGACY_ID
        ]

        if len(home_items) != 1:
            raise CommandError(
                f"Expected exactly one Home page with legacy_id "
                f"{HOME_LEGACY_ID}; found {len(home_items)}."
            )

        home_item = home_items[0]

        if home_item.get("post_status") != "publish":
            raise CommandError(
                "The WordPress Home page must be published "
                "before it can become the Wagtail site root."
            )

        try:
            site = Site.objects.get(hostname=hostname)
        except Site.DoesNotExist:
            raise CommandError(
                f"No Wagtail Site found for hostname '{hostname}'."
            )

        root_page = Page.get_first_root_node()

        if not root_page:
            raise CommandError(
                "Wagtail structural root page could not be found."
            )

        # Confirm the model supports source preservation.
        try:
            CmsPage._meta.get_field("legacy_data")
            CmsPage._meta.get_field("legacy_id")
        except Exception as exc:
            raise CommandError(
                "CmsPage must have legacy_id and legacy_data fields. "
                "Run migrations first. "
                f"Details: {exc}"
            )

        created_count = 0
        updated_count = 0
        published_count = 0
        draft_count = 0

        content_sources = {}
        unsupported_widget_count = 0
        empty_content_count = 0
        slug_adjustments = []

        # -------------------------------------------------
        # Import Home first.
        # -------------------------------------------------

        self.stdout.write(
            self.style.NOTICE(
                f"Importing Home (legacy_id={HOME_LEGACY_ID})..."
            )
        )

        home_page = CmsPage.objects.filter(
            legacy_id=HOME_LEGACY_ID
        ).first()

        home_slug = unique_slug(
            root_page,
            clean_text(home_item.get("post_name")),
            HOME_LEGACY_ID,
            current_page=home_page,
        )

        if home_page:
            if home_page.get_parent().pk != root_page.pk:
                home_page.move(root_page, pos="last-child")

            updated_count += 1
        else:
            # home_page = CmsPage(
            #     legacy_id=HOME_LEGACY_ID,
            #     live=False,
            # )
            # root_page.add_child(instance=home_page)
            # created_count += 1
            home_page = CmsPage(
                legacy_id=HOME_LEGACY_ID,
                title=clean_text(home_item.get("post_title")) or "Home",
                slug=home_slug,
                template_key="blank",
                live=False,
            )
            root_page.add_child(instance=home_page)
            created_count += 1

        set_page_fields(home_page, home_item, home_slug)

        home_result = replace_local_content(
            home_page,
            home_item,
        )

        content_sources[HOME_LEGACY_ID] = (
            home_result["source_type"]
        )
        unsupported_widget_count += (
            home_result["unsupported_widgets"]
        )

        if not home_result["has_content"]:
            empty_content_count += 1

        home_page.live = False
        home_page.save()

        home_revision = home_page.save_revision()

        home_revision.publish()
        published_count += 1

        # -------------------------------------------------
        # Import remaining pages under Home.
        # -------------------------------------------------

        remaining_pages = [
            item for item in pages
            if item["legacy_id"] != HOME_LEGACY_ID
        ]

        remaining_pages.sort(
            key=lambda item: (
                item.get("menu_order") or 0,
                item["legacy_id"],
            )
        )

        for index, item in enumerate(remaining_pages, start=1):
            legacy_id = item["legacy_id"]

            title = (   # noqa
                clean_text(item.get("post_title"))
                or f"Untitled page {legacy_id}"
            )

            original_slug = clean_text(
                item.get("post_name")
            )

            page = CmsPage.objects.filter(
                legacy_id=legacy_id
            ).first()

            slug = unique_slug(
                home_page,
                original_slug,
                legacy_id,
                current_page=page,
            )

            if slug != original_slug:
                slug_adjustments.append(
                    (legacy_id, original_slug, slug)
                )

            if page:
                if page.get_parent().pk != home_page.pk:
                    page.move(home_page, pos="last-child")

                updated_count += 1
            else:
                # page = CmsPage(
                #     legacy_id=legacy_id,
                #     live=False,
                # )
                # home_page.add_child(instance=page)
                # created_count += 1
                page = CmsPage(
                    legacy_id=legacy_id,
                    title=title,
                    slug=slug,
                    template_key="blank",
                    live=False,
                )
                home_page.add_child(instance=page)
                created_count += 1

            set_page_fields(page, item, slug)

            result = replace_local_content(page, item)

            content_sources[legacy_id] = result["source_type"]
            unsupported_widget_count += (
                result["unsupported_widgets"]
            )

            if not result["has_content"]:
                empty_content_count += 1

            page.live = False
            page.save()

            revision = page.save_revision()

            if item.get("post_status") == "publish":
                revision.publish()
                published_count += 1
            else:
                # Keep non-published WordPress pages as Wagtail drafts.
                draft_count += 1

            if index % 10 == 0:
                self.stdout.write(
                    f"Processed {index}/{len(remaining_pages)} pages"
                )

        # -------------------------------------------------
        # Set the migrated Home page as the Wagtail site root.
        # -------------------------------------------------

        site.root_page = home_page
        site.save(update_fields=["root_page"])

        # -------------------------------------------------
        # Report.
        # -------------------------------------------------

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("WORDPRESS CMS PAGE IMPORT REPORT")
        self.stdout.write("=" * 60)

        self.stdout.write(
            self.style.SUCCESS(
                f"Total source pages: {len(pages)}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {created_count}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated: {updated_count}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Published: {published_count}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Drafts: {draft_count}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Pages with no imported section content: "
                f"{empty_content_count}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Unsupported Elementor widgets encountered: "
                f"{unsupported_widget_count}"
            )
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Slug adjustments: {len(slug_adjustments)}"
            )
        )

        for legacy_id, original, adjusted in slug_adjustments:
            self.stdout.write(
                self.style.WARNING(
                    f"  Page {legacy_id}: "
                    f"'{original}' -> '{adjusted}'"
                )
            )

        self.stdout.write("")
        self.stdout.write(
            f"Wagtail site hostname: {site.hostname}"
        )
        self.stdout.write(
            f"New site root: {home_page.title} "
            f"(page ID {home_page.pk})"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "\nCMS page import completed successfully."
            )
        )

        self.stdout.write("=" * 60)
