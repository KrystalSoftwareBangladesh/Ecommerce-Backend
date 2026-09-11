# scripts/export_woocommerce_customer_addresses.py
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
    u.ID AS user_legacy_id,

    MAX(CASE WHEN um.meta_key = 'billing_first_name'
        THEN um.meta_value END) AS billing_first_name,
    MAX(CASE WHEN um.meta_key = 'billing_last_name'
        THEN um.meta_value END) AS billing_last_name,
    MAX(CASE WHEN um.meta_key = 'billing_company'
        THEN um.meta_value END) AS billing_company,
    MAX(CASE WHEN um.meta_key = 'billing_address_1'
        THEN um.meta_value END) AS billing_address_1,
    MAX(CASE WHEN um.meta_key = 'billing_address_2'
        THEN um.meta_value END) AS billing_address_2,
    MAX(CASE WHEN um.meta_key = 'billing_city'
        THEN um.meta_value END) AS billing_city,
    MAX(CASE WHEN um.meta_key = 'billing_state'
        THEN um.meta_value END) AS billing_state,
    MAX(CASE WHEN um.meta_key = 'billing_postcode'
        THEN um.meta_value END) AS billing_postcode,
    MAX(CASE WHEN um.meta_key = 'billing_country'
        THEN um.meta_value END) AS billing_country,
    MAX(CASE WHEN um.meta_key = 'billing_email'
        THEN um.meta_value END) AS billing_email,
    MAX(CASE WHEN um.meta_key = 'billing_phone'
        THEN um.meta_value END) AS billing_phone,

    MAX(CASE WHEN um.meta_key = 'shipping_first_name'
        THEN um.meta_value END) AS shipping_first_name,
    MAX(CASE WHEN um.meta_key = 'shipping_last_name'
        THEN um.meta_value END) AS shipping_last_name,
    MAX(CASE WHEN um.meta_key = 'shipping_company'
        THEN um.meta_value END) AS shipping_company,
    MAX(CASE WHEN um.meta_key = 'shipping_address_1'
        THEN um.meta_value END) AS shipping_address_1,
    MAX(CASE WHEN um.meta_key = 'shipping_address_2'
        THEN um.meta_value END) AS shipping_address_2,
    MAX(CASE WHEN um.meta_key = 'shipping_city'
        THEN um.meta_value END) AS shipping_city,
    MAX(CASE WHEN um.meta_key = 'shipping_state'
        THEN um.meta_value END) AS shipping_state,
    MAX(CASE WHEN um.meta_key = 'shipping_postcode'
        THEN um.meta_value END) AS shipping_postcode,
    MAX(CASE WHEN um.meta_key = 'shipping_country'
        THEN um.meta_value END) AS shipping_country,
    MAX(CASE WHEN um.meta_key = 'shipping_phone'
        THEN um.meta_value END) AS shipping_phone

FROM wpoy_users u
LEFT JOIN wpoy_usermeta um
    ON um.user_id = u.ID
    AND um.meta_key IN (
        'billing_first_name',
        'billing_last_name',
        'billing_company',
        'billing_address_1',
        'billing_address_2',
        'billing_city',
        'billing_state',
        'billing_postcode',
        'billing_country',
        'billing_email',
        'billing_phone',
        'shipping_first_name',
        'shipping_last_name',
        'shipping_company',
        'shipping_address_1',
        'shipping_address_2',
        'shipping_city',
        'shipping_state',
        'shipping_postcode',
        'shipping_country',
        'shipping_phone'
    )
GROUP BY u.ID
HAVING
    COALESCE(
        MAX(CASE WHEN um.meta_key = 'billing_address_1'
            THEN NULLIF(TRIM(um.meta_value), '') END),
        ''
    ) <> ''
    OR
    COALESCE(
        MAX(CASE WHEN um.meta_key = 'shipping_address_1'
            THEN NULLIF(TRIM(um.meta_value), '') END),
        ''
    ) <> ''
ORDER BY u.ID;
"""


def main():
    print("Connecting to database...")
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching customer addresses...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} users with addresses")

        output_file = Path("resources/customer_addresses.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as fp:
            json.dump(rows, fp, ensure_ascii=False, indent=2)

        print(f"Export completed: {output_file.resolve()}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
