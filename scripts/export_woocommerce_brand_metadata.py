# scripts/export_woocommerce_brand_metadata.py
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


BRAND_METADATA_QUERY = """
SELECT
    t.term_id AS legacy_id,
    t.name,

    tt.description,

    MAX(
        CASE
            WHEN tm.meta_key = 'rank_math_title'
            THEN tm.meta_value
        END
    ) AS seo_title,

    MAX(
        CASE
            WHEN tm.meta_key = 'rank_math_description'
            THEN tm.meta_value
        END
    ) AS seo_description,

    MAX(
        CASE
            WHEN tm.meta_key = 'rank_math_focus_keyword'
            THEN tm.meta_value
        END
    ) AS seo_focus_keyword

FROM wpoy_terms t

JOIN wpoy_term_taxonomy tt
    ON tt.term_id = t.term_id
    AND tt.taxonomy = 'pa_brand'

LEFT JOIN wpoy_termmeta tm
    ON tm.term_id = t.term_id
    AND tm.meta_key IN (
        'rank_math_title',
        'rank_math_description',
        'rank_math_focus_keyword'
    )

GROUP BY
    t.term_id,
    t.name,
    tt.description

ORDER BY t.term_id;
"""


def fetch_all(cursor, query):
    cursor.execute(query)
    return cursor.fetchall()


def main():
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching Brand metadata...")

            rows = fetch_all(
                cursor,
                BRAND_METADATA_QUERY,
            )

        brand_metadata = []

        for row in rows:
            brand_metadata.append(
                {
                    "legacy_id": row["legacy_id"],
                    "name": row["name"],
                    "description": row["description"] or "",
                    "seo_title": row["seo_title"] or "",
                    "seo_description": (
                        row["seo_description"] or ""
                    ),
                    "seo_focus_keyword": (
                        row["seo_focus_keyword"] or ""
                    ),
                }
            )

        output_file = Path(
            "resources/brand_metadata.json"
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
                brand_metadata,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print("")
        print("=" * 50)
        print(
            f"Brands exported: "
            f"{len(brand_metadata)}"
        )
        print(
            f"Saved to: "
            f"{output_file.resolve()}"
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
