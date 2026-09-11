# scripts/export_woocommerce_brand_images.py
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


BRAND_IMAGES_QUERY = """
SELECT
    t.term_id AS brand_legacy_id,
    t.name AS brand_name,

    a.ID AS attachment_id,
    file.meta_value AS relative_file_path

FROM wpoy_terms t

JOIN wpoy_term_taxonomy tt
    ON tt.term_id = t.term_id
    AND tt.taxonomy = 'pa_brand'

JOIN wpoy_termmeta thumbnail
    ON thumbnail.term_id = t.term_id
    AND thumbnail.meta_key = 'thumbnail_id'

JOIN wpoy_posts a
    ON a.ID = CAST(thumbnail.meta_value AS UNSIGNED)
    AND a.post_type = 'attachment'

JOIN wpoy_postmeta file
    ON file.post_id = a.ID
    AND file.meta_key = '_wp_attached_file'

WHERE thumbnail.meta_value IS NOT NULL
  AND thumbnail.meta_value != ''
  AND file.meta_value IS NOT NULL
  AND file.meta_value != ''

ORDER BY t.term_id;
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
            print("Fetching Brand logos...")

            rows = fetch_all(
                cursor,
                BRAND_IMAGES_QUERY,
            )

        brand_images = []

        for row in rows:
            relative_file_path = row[
                "relative_file_path"
            ]

            brand_images.append(
                {
                    "brand_legacy_id": row[
                        "brand_legacy_id"
                    ],
                    "brand_name": row[
                        "brand_name"
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
            "resources/brand_images.json"
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
                brand_images,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print("")
        print("=" * 50)
        print(
            f"Brands with logos: "
            f"{len(brand_images)}"
        )
        print(
            f"Saved to: "
            f"{output_file.resolve()}"
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
