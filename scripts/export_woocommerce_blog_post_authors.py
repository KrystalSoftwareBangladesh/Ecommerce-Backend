# scripts/export_woocommerce_blog_post_authors.py
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
    p.ID AS blog_post_legacy_id,
    p.post_author AS author_legacy_id
FROM wpoy_posts p
WHERE p.post_type = 'post'
  AND p.post_status IN ('publish', 'draft')
  AND p.post_author > 0
ORDER BY p.ID;
"""


def main():
    print("Connecting to database...")

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching blog post/author relationships...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} relationships")

        output_file = Path("resources/blog_post_authors.json")
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
