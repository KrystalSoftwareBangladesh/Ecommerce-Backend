# scripts/export_woocommerce_blog_tags.py
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
    t.slug
FROM wpoy_terms t
JOIN wpoy_term_taxonomy tt
    ON t.term_id = tt.term_id
WHERE tt.taxonomy = 'post_tag'
ORDER BY t.term_id;
"""


def main():
    print("Connecting to database...")

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching blog tags...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} blog tags")

        output_file = Path("resources/blog_tags.json")
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
