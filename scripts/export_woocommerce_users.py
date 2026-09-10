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


USERS_QUERY = """
SELECT
    u.ID AS legacy_id,
    u.user_login AS username,
    u.user_email AS email,
    u.display_name,

    first_name.meta_value AS first_name,
    last_name.meta_value AS last_name,
    billing_phone.meta_value AS billing_phone,

    capabilities.meta_value AS capabilities

FROM wpoy_users u

LEFT JOIN wpoy_usermeta first_name
    ON first_name.user_id = u.ID
    AND first_name.meta_key = 'first_name'

LEFT JOIN wpoy_usermeta last_name
    ON last_name.user_id = u.ID
    AND last_name.meta_key = 'last_name'

LEFT JOIN wpoy_usermeta billing_phone
    ON billing_phone.user_id = u.ID
    AND billing_phone.meta_key = 'billing_phone'

LEFT JOIN (
    SELECT
        user_id,
        MAX(meta_value) AS meta_value
    FROM wpoy_usermeta
    WHERE meta_key = 'wpoy_capabilities'
    GROUP BY user_id
) capabilities
    ON capabilities.user_id = u.ID

ORDER BY u.ID;
"""


def fetch_all(cursor, query):
    cursor.execute(query)
    return cursor.fetchall()


def normalize_role(capabilities):
    if capabilities == 'a:1:{s:8:"customer";b:1;}':
        return "CUSTOMER"

    if capabilities == 'a:1:{s:13:"administrator";b:1;}':
        return "STAFF"

    if capabilities == "a:0:{}":
        return "STAFF"

    if capabilities is None:
        return "CUSTOMER"

    raise ValueError(
        f"Unknown WordPress capabilities: {capabilities!r}"
    )


def clean_value(value):
    if value is None:
        return ""

    return value.strip()


def main():
    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching WordPress users...")

            rows = fetch_all(
                cursor,
                USERS_QUERY,
            )

        users = []

        for row in rows:
            role = normalize_role(
                row["capabilities"]
            )

            users.append(
                {
                    "legacy_id": row["legacy_id"],
                    "username": clean_value(
                        row["username"]
                    ),
                    "email": clean_value(
                        row["email"]
                    ).lower(),
                    "first_name": clean_value(
                        row["first_name"]
                    ),
                    "last_name": clean_value(
                        row["last_name"]
                    ),
                    "display_name": clean_value(
                        row["display_name"]
                    ),
                    "role": role,
                    "billing_phone": clean_value(
                        row["billing_phone"]
                    ),
                }
            )

        output_file = Path(
            "resources/users.json"
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
                users,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        customer_count = sum(
            1
            for user in users
            if user["role"] == "CUSTOMER"
        )

        staff_count = sum(
            1
            for user in users
            if user["role"] == "STAFF"
        )

        users_with_phone = sum(
            1
            for user in users
            if user["billing_phone"]
        )

        users_with_first_name = sum(
            1
            for user in users
            if user["first_name"]
        )

        users_with_last_name = sum(
            1
            for user in users
            if user["last_name"]
        )

        print("")
        print("=" * 50)
        print(
            f"Total users: {len(users)}"
        )
        print(
            f"Customers: {customer_count}"
        )
        print(
            f"Staff: {staff_count}"
        )
        print(
            f"Users with phone: {users_with_phone}"
        )
        print(
            f"Users with first name: "
            f"{users_with_first_name}"
        )
        print(
            f"Users with last name: "
            f"{users_with_last_name}"
        )
        print(
            f"Saved to: {output_file.resolve()}"
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
