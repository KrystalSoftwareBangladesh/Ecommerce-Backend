# scripts/export_woocommerce_product_brands.py
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
    tr.object_id AS product_legacy_id,
    tt.term_id AS brand_legacy_id
FROM wpoy_term_relationships tr
JOIN wpoy_term_taxonomy tt
    ON tr.term_taxonomy_id = tt.term_taxonomy_id
JOIN wpoy_posts p
    ON p.ID = tr.object_id
WHERE tt.taxonomy = 'pa_brand'
  AND p.post_type = 'product'
  AND p.post_status IN ('publish', 'draft')
ORDER BY tr.object_id, tt.term_id;
"""


def main():
    print("Connecting to database...")

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching product/brand relationships...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} relationships")

        output_file = Path("resources/product_brands.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as fp:
            json.dump(
                rows,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print(f"Export completed: {output_file.resolve()}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
