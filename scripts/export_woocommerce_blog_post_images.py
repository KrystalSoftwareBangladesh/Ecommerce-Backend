# scripts/export_woocommerce_blog_post_images.py

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


BLOG_POST_IMAGES_QUERY = """
SELECT
    p.ID AS blog_post_legacy_id,
    p.post_title AS blog_post_title,

    a.ID AS attachment_id,
    file.meta_value AS relative_file_path

FROM wpoy_posts p

JOIN wpoy_postmeta thumbnail
    ON thumbnail.post_id = p.ID
    AND thumbnail.meta_key = '_thumbnail_id'

JOIN wpoy_posts a
    ON a.ID = CAST(thumbnail.meta_value AS UNSIGNED)
    AND a.post_type = 'attachment'

JOIN wpoy_postmeta file
    ON file.post_id = a.ID
    AND file.meta_key = '_wp_attached_file'

WHERE p.post_type = 'post'
  AND p.post_status IN ('publish', 'draft')
  AND thumbnail.meta_value IS NOT NULL
  AND thumbnail.meta_value != ''
  AND file.meta_value IS NOT NULL
  AND file.meta_value != ''

ORDER BY p.ID;
"""


BASE_IMAGE_URL = (
    "https://bestcomputerhub.com/wp-content/uploads/"
)


def fetch_all(cursor, query):
    cursor.execute(query)
    return cursor.fetchall()


def build_image_url(relative_file_path):
    return BASE_IMAGE_URL + relative_file_path.lstrip("/")


def main():
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching BlogPost featured images...")

            rows = fetch_all(
                cursor,
                BLOG_POST_IMAGES_QUERY,
            )

        blog_post_images = []

        for row in rows:
            relative_file_path = row[
                "relative_file_path"
            ]

            blog_post_images.append(
                {
                    "blog_post_legacy_id": row[
                        "blog_post_legacy_id"
                    ],
                    "blog_post_title": row[
                        "blog_post_title"
                    ],
                    "attachment_id": row[
                        "attachment_id"
                    ],
                    "relative_file_path": relative_file_path,
                    "image_url": build_image_url(
                        relative_file_path
                    ),
                }
            )

        output_file = Path(
            "resources/blog_post_images.json"
        )

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            output_file,
            "w",
            encoding="utf-8",
        ) as fp:
            json.dump(
                blog_post_images,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print("")
        print("=" * 50)
        print(
            f"BlogPosts with featured images: "
            f"{len(blog_post_images)}"
        )
        print(
            f"Saved to: "
            f"{output_file.resolve()}"
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
