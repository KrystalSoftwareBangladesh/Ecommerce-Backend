# import_product_brands
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from product_api.models import Brand, Product


class Command(BaseCommand):
    help = "Import product/brand relationships from product_brands.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to product_brands.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write("Loading product/brand relationships...")

        with open(json_file, "r", encoding="utf-8") as fp:
            rows = json.load(fp)

        self.stdout.write(
            f"Found {len(rows)} product/brand relationships"
        )

        mapped = 0
        missing_products = 0
        missing_brands = 0
        failed = 0

        for row in rows:
            product_legacy_id = row["product_legacy_id"]
            brand_legacy_id = row["brand_legacy_id"]

            product = Product.objects.filter(
                legacy_id=product_legacy_id
            ).first()

            if not product:
                missing_products += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Product not found: legacy_id={product_legacy_id}"
                    )
                )
                continue

            brand = Brand.objects.filter(
                legacy_id=brand_legacy_id
            ).first()

            if not brand:
                missing_brands += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Brand not found: legacy_id={brand_legacy_id}"
                    )
                )
                continue

            try:
                product.brand = brand
                product.save(update_fields=["brand"])
                mapped += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to map product "
                        f"{product_legacy_id} to brand "
                        f"{brand_legacy_id}: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import completed."))
        self.stdout.write(f"Mapped: {mapped}")
        self.stdout.write(f"Missing products: {missing_products}")
        self.stdout.write(f"Missing brands: {missing_brands}")
        self.stdout.write(f"Failed: {failed}")
