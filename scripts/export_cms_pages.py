# scripts/export_cms_pages.py

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from datetime import date, datetime, time
from decimal import Decimal
import pymysql


# ---------------------------------------------------------
# Database configuration
# ---------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("WP_DB_HOST", "localhost"),
    "user": os.getenv("WP_DB_USER", "bch_dev"),
    "password": os.getenv("WP_DB_PASSWORD", "Admin123#"),
    "database": os.getenv("WP_DB_NAME", "bch_db"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


# ---------------------------------------------------------
# Queries
# ---------------------------------------------------------

PAGES_QUERY = """
SELECT
    ID AS legacy_id,
    post_author,
    post_date,
    post_date_gmt,
    post_content,
    post_title,
    post_excerpt,
    post_status,
    comment_status,
    ping_status,
    post_password,
    post_name,
    post_modified,
    post_modified_gmt,
    post_parent,
    guid,
    menu_order,
    post_type,
    post_mime_type,
    comment_count
FROM wpoy_posts
WHERE post_type = 'page'
ORDER BY ID;
"""


# Exclude metadata that is generated automatically,
# editor-specific, analytical, or cache-related.
EXCLUDED_META_KEYS = {
    "_edit_lock",
    "_edit_last",
    "_elementor_element_cache",
    "_elementor_page_assets",
    "_elementor_css",
    "_elementor_controls_usage",
    "rank_math_analytic_object_id",
    "rank_math_internal_links_processed",
    "rank_math_seo_score",
}


# Preserve all other metadata, including:
# - Elementor configuration
# - WPBakery configuration
# - Rank Math SEO settings
# - Featured image references
# - Page templates
# - Table of contents settings
# - Other potentially relevant page-specific metadata.


# ---------------------------------------------------------
# Export
# ---------------------------------------------------------

def json_serializer(value):
    """Convert database-specific Python values into JSON-compatible values."""

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable"
    )


def main():
    print("Connecting to WordPress database...")

    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "Missing WP_DB_PASSWORD environment variable."
        )

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:

            # Fetch all WordPress pages.
            print("Fetching WordPress pages...")
            cursor.execute(PAGES_QUERY)
            pages = cursor.fetchall()

            print(f"Found {len(pages)} pages")

            if not pages:
                raise RuntimeError("No WordPress pages found.")

            # Validate source IDs.
            page_ids = [
                page["legacy_id"]
                for page in pages
            ]

            if len(page_ids) != len(set(page_ids)):
                raise RuntimeError(
                    "Duplicate WordPress page IDs detected."
                )

            # Fetch metadata for all pages.
            print("Fetching page metadata...")

            placeholders = ", ".join(
                ["%s"] * len(page_ids)
            )

            metadata_query = f"""
                SELECT
                    post_id,
                    meta_key,
                    meta_value
                FROM wpoy_postmeta
                WHERE post_id IN ({placeholders})
                ORDER BY meta_id;
            """

            cursor.execute(
                metadata_query,
                page_ids,
            )

            metadata_rows = cursor.fetchall()

        # -------------------------------------------------
        # Organize metadata by page ID.
        # -------------------------------------------------

        metadata_by_page = defaultdict(
            lambda: defaultdict(list)
        )

        for row in metadata_rows:
            meta_key = row["meta_key"]

            if not meta_key:
                continue

            if meta_key in EXCLUDED_META_KEYS:
                continue

            metadata_by_page[row["post_id"]][meta_key].append(
                row["meta_value"]
            )

        # -------------------------------------------------
        # Attach metadata to page records.
        # -------------------------------------------------

        for page in pages:
            page_metadata = metadata_by_page.get(
                page["legacy_id"],
                {},
            )

            page["metadata"] = {}

            for meta_key, values in page_metadata.items():

                # Preserve a single value as a scalar.
                # Preserve repeated metadata keys as a list.
                if len(values) == 1:
                    page["metadata"][meta_key] = values[0]
                else:
                    page["metadata"][meta_key] = values

        # -------------------------------------------------
        # Validate exported records.
        # -------------------------------------------------

        exported_ids = [
            page["legacy_id"]
            for page in pages
        ]

        if len(exported_ids) != len(set(exported_ids)):
            raise RuntimeError(
                "Duplicate IDs found in exported data."
            )

        if set(page_ids) != set(exported_ids):
            raise RuntimeError(
                "Source and exported page IDs do not match."
            )

        # -------------------------------------------------
        # Generate statistics.
        # -------------------------------------------------

        status_counts = Counter(
            page["post_status"]
            for page in pages
        )

        elementor_count = sum(
            bool(page["metadata"].get("_elementor_data"))
            for page in pages
        )

        wpbakery_count = sum(
            any(
                key in page["metadata"]
                for key in (
                    "_wpb_vc_js_status",
                    "_wpb_post_custom_layout",
                )
            )
            for page in pages
        )

        featured_image_count = sum(
            "_thumbnail_id" in page["metadata"]
            for page in pages
        )

        seo_keys = {
            "rank_math_title",
            "rank_math_description",
            "rank_math_focus_keyword",
            "rank_math_robots",
            "rank_math_canonical_url",
            "rank_math_facebook_title",
            "rank_math_facebook_description",
            "rank_math_facebook_image",
            "rank_math_twitter_title",
            "rank_math_twitter_description",
            "rank_math_twitter_image",
        }

        seo_count = sum(
            bool(
                seo_keys.intersection(
                    page["metadata"].keys()
                )
            )
            for page in pages
        )

        empty_content_count = sum(
            not (page["post_content"] or "").strip()
            for page in pages
        )

        # -------------------------------------------------
        # Write JSON resource.
        # -------------------------------------------------

        output_file = (
            Path(__file__).resolve().parents[1]
            / "resources"
            / "cms_pages.json"
        )

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_file = output_file.with_suffix(
            ".json.tmp"
        )

        with open(
            temporary_file,
            "w",
            encoding="utf-8",
        ) as fp:
            json.dump(
                pages,
                fp,
                ensure_ascii=False,
                indent=2,
                default=json_serializer,
            )

        temporary_file.replace(output_file)

        # -------------------------------------------------
        # Report.
        # -------------------------------------------------

        print("\n" + "=" * 55)
        print("WORDPRESS CMS PAGE EXPORT REPORT")
        print("=" * 55)

        print(f"Total pages exported: {len(pages)}")

        print("\nPages by status:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")

        print("\nContent and metadata:")
        print(f"  Elementor pages: {elementor_count}")
        print(f"  WPBakery pages: {wpbakery_count}")
        print(
            f"  Pages with featured images: "
            f"{featured_image_count}"
        )
        print(f"  Pages with SEO metadata: {seo_count}")
        print(
            f"  Pages with empty content: "
            f"{empty_content_count}"
        )

        print("\nValidation:")
        print("  Duplicate page IDs: 0")
        print("  Source/export ID mismatch: 0")
        print("  Export validation: PASSED")

        print(f"\nOutput file: {output_file}")
        print("=" * 55)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
