# scripts/export_woocommerce_blog_posts.py
import json
from pathlib import Path

import pymysql


DB_CONFIG = {
    "host": "localhost",
    "user": "bch_dev",
    "password": "Admin123#",
    "database": "bch_db",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


QUERY = """
SELECT
    p.ID AS legacy_id,
    p.post_title AS title,
    p.post_name AS slug,
    p.post_content AS content,
    p.post_author AS author_legacy_id,
    p.post_status AS status,
    p.post_date AS published_at,

    thumbnail.meta_value AS featured_image_legacy_id,

    seo_title.meta_value AS seo_title,
    seo_description.meta_value AS seo_description,
    seo_focus_keyword.meta_value AS seo_focus_keyword,
    seo_robots.meta_value AS seo_robots

FROM wpoy_posts p

LEFT JOIN wpoy_postmeta thumbnail
    ON p.ID = thumbnail.post_id
   AND thumbnail.meta_key = '_thumbnail_id'

LEFT JOIN wpoy_postmeta seo_title
    ON p.ID = seo_title.post_id
   AND seo_title.meta_key = 'rank_math_title'

LEFT JOIN wpoy_postmeta seo_description
    ON p.ID = seo_description.post_id
   AND seo_description.meta_key = 'rank_math_description'

LEFT JOIN wpoy_postmeta seo_focus_keyword
    ON p.ID = seo_focus_keyword.post_id
   AND seo_focus_keyword.meta_key = 'rank_math_focus_keyword'

LEFT JOIN wpoy_postmeta seo_robots
    ON p.ID = seo_robots.post_id
   AND seo_robots.meta_key = 'rank_math_robots'

WHERE p.post_type = 'post'
  AND p.post_status IN ('publish', 'draft')

ORDER BY p.ID;
"""


def to_int(value):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_seo_robots(value):
    """
    Convert Rank Math robots metadata into the fields supported by BlogPost.

    WordPress stores this value as serialized data. The importer will receive
    normalized boolean values instead of WordPress-specific metadata.
    """
    if not value:
        return {
            "seo_noindex": False,
            "seo_nofollow": False,
        }

    value = str(value).lower()

    return {
        "seo_noindex": "noindex" in value,
        "seo_nofollow": "nofollow" in value,
    }


def build_blog_post(row):
    seo_robots = parse_seo_robots(row["seo_robots"])

    return {
        "legacy_id": row["legacy_id"],
        "title": row["title"] or "",
        "slug": row["slug"] or "",
        "content": row["content"] or "",
        "author_legacy_id": to_int(row["author_legacy_id"]),
        "status": row["status"],
        "published_at": (
            row["published_at"].isoformat()
            if row["published_at"]
            else None
        ),
        "featured_image_legacy_id": to_int(
            row["featured_image_legacy_id"]
        ),
        "seo_title": row["seo_title"] or "",
        "seo_description": row["seo_description"] or "",
        "seo_focus_keyword": row["seo_focus_keyword"] or "",
        **seo_robots,
    }


def main():
    print("Connecting to database...")

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching blog posts...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} blog posts")

        posts = [build_blog_post(row) for row in rows]

        output_file = Path("resources/blog_posts.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as fp:
            json.dump(
                posts,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print(f"Export completed: {output_file.resolve()}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
