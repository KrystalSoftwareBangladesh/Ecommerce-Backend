# product_api/management/commands/import_products.py
from django.core.management.base import BaseCommand
from django.db import transaction

import json

from product_api.models import Product


class Command(BaseCommand):
    help = "Import WooCommerce products from products.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to products.json"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            products = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(products)} products"
            )
        )

        created_count = 0
        updated_count = 0
        failed_count = 0

        for index, item in enumerate(products, start=1):
            try:
                product, created = Product.objects.update_or_create(
                    legacy_id=item["legacy_id"],
                    defaults={
                        "name": item["title"][:200],
                        "slug": item["slug"],
                        "description": item.get("description", ""),
                        "short_description": item.get("short_description", ""),
                        "specifications": item.get("specifications", ""),
                        "current_selling_price": item.get("price") or 0,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(products)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Product {item.get('legacy_id')} failed: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Created: {created_count}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Updated: {updated_count}")
        )
        self.stdout.write(
            self.style.WARNING(f"Failed: {failed_count}")
        )
