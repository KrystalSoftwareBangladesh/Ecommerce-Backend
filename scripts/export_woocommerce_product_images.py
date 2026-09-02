# scripts/export_woocommerce_product_images.py
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


FEATURED_IMAGES_QUERY = """
SELECT
    p.ID AS product_legacy_id,
    p.post_title AS product_title,

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

WHERE p.post_type = 'product'
  AND p.post_status = 'publish'
  AND thumbnail.meta_value IS NOT NULL
  AND thumbnail.meta_value != ''
  AND file.meta_value IS NOT NULL
  AND file.meta_value != ''

ORDER BY p.ID;
"""


GALLERY_IMAGES_QUERY = """
SELECT
    p.ID AS product_legacy_id,
    p.post_title AS product_title,
    gallery.meta_value AS gallery_attachment_ids

FROM wpoy_posts p

JOIN wpoy_postmeta gallery
    ON gallery.post_id = p.ID
    AND gallery.meta_key = '_product_image_gallery'

WHERE p.post_type = 'product'
  AND p.post_status = 'publish'
  AND gallery.meta_value IS NOT NULL
  AND gallery.meta_value != ''

ORDER BY p.ID;
"""


ATTACHMENTS_QUERY = """
SELECT
    a.ID AS attachment_id,
    file.meta_value AS relative_file_path

FROM wpoy_posts a

JOIN wpoy_postmeta file
    ON file.post_id = a.ID
    AND file.meta_key = '_wp_attached_file'

WHERE a.post_type = 'attachment'
  AND a.ID IN ({placeholders});
"""


BASE_IMAGE_URL = (
    "https://bestcomputerhub.com/wp-content/uploads/"
)


def fetch_all(cursor, query):
    cursor.execute(query)
    return cursor.fetchall()


def fetch_attachments(cursor, attachment_ids):
    if not attachment_ids:
        return {}

    placeholders = ",".join(["%s"] * len(attachment_ids))

    query = ATTACHMENTS_QUERY.format(
        placeholders=placeholders
    )

    cursor.execute(query, attachment_ids)

    rows = cursor.fetchall()

    return {
        row["attachment_id"]: row["relative_file_path"]
        for row in rows
        if row["relative_file_path"]
    }


def build_image_url(relative_file_path):
    return BASE_IMAGE_URL + relative_file_path.lstrip("/")


def main():
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:

            print("Fetching featured images...")

            featured_rows = fetch_all(
                cursor,
                FEATURED_IMAGES_QUERY,
            )

            print(
                f"Found {len(featured_rows)} featured images"
            )

            print("Fetching gallery images...")

            gallery_rows = fetch_all(
                cursor,
                GALLERY_IMAGES_QUERY,
            )

            print(
                f"Found {len(gallery_rows)} "
                "products with galleries"
            )

            #
            # Collect gallery attachment IDs
            #
            gallery_attachment_ids = set()

            for row in gallery_rows:
                raw_ids = row["gallery_attachment_ids"]

                attachment_ids = [
                    int(value.strip())
                    for value in raw_ids.split(",")
                    if value.strip().isdigit()
                ]

                gallery_attachment_ids.update(
                    attachment_ids
                )

            print(
                "Fetching gallery attachment paths..."
            )

            attachments = fetch_attachments(
                cursor,
                list(gallery_attachment_ids),
            )

        #
        # Organize images by product
        #
        products = {}

        #
        # Featured images
        #
        for row in featured_rows:
            product_legacy_id = row[
                "product_legacy_id"
            ]

            products[product_legacy_id] = {
                "product_legacy_id": product_legacy_id,
                "product_title": row["product_title"],
                "images": [
                    {
                        "attachment_id": row[
                            "attachment_id"
                        ],
                        "relative_file_path": row[
                            "relative_file_path"
                        ],
                        "image_url": build_image_url(
                            row[
                                "relative_file_path"
                            ]
                        ),
                        "display_order": 0,
                        "is_default": True,
                    }
                ],
            }

        #
        # Gallery images
        #
        for row in gallery_rows:
            product_legacy_id = row[
                "product_legacy_id"
            ]

            #
            # Ignore galleries for products
            # without a valid featured image.
            #
            if product_legacy_id not in products:
                continue

            raw_ids = row["gallery_attachment_ids"]

            attachment_ids = [
                int(value.strip())
                for value in raw_ids.split(",")
                if value.strip().isdigit()
            ]

            featured_attachment_id = products[
                product_legacy_id
            ]["images"][0]["attachment_id"]

            display_order = 1

            for attachment_id in attachment_ids:

                #
                # Avoid duplicate featured image.
                #
                if attachment_id == featured_attachment_id:
                    continue

                relative_file_path = attachments.get(
                    attachment_id
                )

                #
                # Skip missing attachment paths.
                #
                if not relative_file_path:
                    continue

                products[product_legacy_id][
                    "images"
                ].append(
                    {
                        "attachment_id": attachment_id,
                        "relative_file_path": (
                            relative_file_path
                        ),
                        "image_url": build_image_url(
                            relative_file_path
                        ),
                        "display_order": display_order,
                        "is_default": False,
                    }
                )

                display_order += 1

        #
        # Convert dictionary to list.
        #
        product_images = list(products.values())

        output_file = Path(
            "resources/product_images.json"
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
                product_images,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        total_images = sum(
            len(product["images"])
            for product in product_images
        )

        print("")
        print("=" * 50)
        print(
            f"Products with images: "
            f"{len(product_images)}"
        )
        print(
            f"Total image records: "
            f"{total_images}"
        )
        print(
            f"Saved to: "
            f"{output_file.resolve()}"
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
