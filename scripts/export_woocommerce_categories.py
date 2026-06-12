# scripts/export_woocommerce_categories.py

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
    t.term_id AS legacy_id,
    t.name,
    t.slug,
    tt.description,
    tt.parent AS parent_legacy_id
FROM wpoy_terms t
JOIN wpoy_term_taxonomy tt
    ON t.term_id = tt.term_id
WHERE tt.taxonomy = 'product_cat'
ORDER BY t.term_id;
"""


def main():
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            cursor.execute(QUERY)
            categories = cursor.fetchall()

        output_file = Path("resources/categories.json")

        with open(output_file, "w", encoding="utf-8") as fp:
            json.dump(
                categories,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print(f"Exported {len(categories)} categories")
        print(f"Saved to {output_file.resolve()}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
