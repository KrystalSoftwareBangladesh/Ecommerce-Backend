# scripts/export_woocommerce_products.py
import json
import decimal
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
    p.ID AS product_id,
    p.post_title AS title,
    p.post_name AS slug,
    p.post_content AS description,
    p.post_excerpt AS short_description,

    sku.meta_value AS sku,
    price.meta_value AS price,
    regular_price.meta_value AS regular_price,

    stock.meta_value AS stock,
    stock_status.meta_value AS stock_status,
    manage_stock.meta_value AS manage_stock,

    specifications.meta_value AS specifications

FROM wpoy_posts p

LEFT JOIN wpoy_postmeta sku
    ON p.ID = sku.post_id
   AND sku.meta_key = '_sku'

LEFT JOIN wpoy_postmeta price
    ON p.ID = price.post_id
   AND price.meta_key = '_price'

LEFT JOIN wpoy_postmeta regular_price
    ON p.ID = regular_price.post_id
   AND regular_price.meta_key = '_regular_price'

LEFT JOIN wpoy_postmeta stock
    ON p.ID = stock.post_id
   AND stock.meta_key = '_stock'

LEFT JOIN wpoy_postmeta stock_status
    ON p.ID = stock_status.post_id
   AND stock_status.meta_key = '_stock_status'

LEFT JOIN wpoy_postmeta manage_stock
    ON p.ID = manage_stock.post_id
   AND manage_stock.meta_key = '_manage_stock'

LEFT JOIN wpoy_postmeta specifications
    ON p.ID = specifications.post_id
   AND specifications.meta_key = '_specifications'

WHERE p.post_type = 'product'
  AND p.post_status = 'publish'

ORDER BY p.ID;
"""


def to_int(value):
    if value in (None, ""):
        return None

    try:
        return int(float(value))
    except Exception:
        return None


def to_decimal(value):
    if value in (None, ""):
        return None

    try:
        return str(decimal.Decimal(value))
    except Exception:
        return None


def build_product(row):
    return {
        "legacy_id": row["product_id"],
        "title": row["title"],
        "slug": row["slug"],
        "description": row["description"] or "",
        "short_description": row["short_description"] or "",
        "sku": row["sku"] or f"LEGACY-{row['product_id']}",
        "price": to_decimal(row["price"]),
        "regular_price": to_decimal(row["regular_price"]),
        "stock": to_int(row["stock"]),
        "stock_status": row["stock_status"],
        "manage_stock": row["manage_stock"] == "yes",
        "specifications": row["specifications"] or "",
    }


def main():
    print("Connecting to database...")

    connection = pymysql.connect(**DB_CONFIG)

    try:
        with connection.cursor() as cursor:
            print("Fetching products...")
            cursor.execute(QUERY)
            rows = cursor.fetchall()

        print(f"Found {len(rows)} products")

        products = [build_product(row) for row in rows]

        output_file = "resources/products.json"

        with open(output_file, "w", encoding="utf-8") as fp:
            json.dump(
                products,
                fp,
                ensure_ascii=False,
                indent=2,
            )

        print(f"Export completed: {output_file}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
