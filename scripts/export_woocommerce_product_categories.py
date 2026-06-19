# scripts/export_woocommerce_product_categories.py
import json
import pymysql
from pathlib import Path


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
    tt.term_id AS category_legacy_id
FROM wpoy_term_relationships tr
JOIN wpoy_term_taxonomy tt
    ON tr.term_taxonomy_id = tt.term_taxonomy_id
JOIN wpoy_posts p
    ON p.ID = tr.object_id
WHERE tt.taxonomy = 'product_cat'
  AND p.post_type = 'product'
  AND p.post_status = 'publish'
ORDER BY tr.object_id;
"""


def main():
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        output_file = Path("resources/product_categories.json")

        with open(output_file, "w", encoding="utf-8") as fp:
            json.dump(
                rows,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print(f"Exported {len(rows)} mappings")
        print(f"Saved to {output_file.resolve()}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
