# scripts/export_woocommerce_blog_categories.py
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
    tt.parent,
    tt.count
FROM wpoy_terms t
JOIN wpoy_term_taxonomy tt
    ON t.term_id = tt.term_id
WHERE tt.taxonomy = 'category'
ORDER BY t.term_id;
"""


def main():
    print("Connecting to database...")

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching blog categories...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} blog categories")

        output_file = Path("resources/blog_categories.json")
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
