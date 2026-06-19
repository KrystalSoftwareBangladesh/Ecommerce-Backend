# product_api/management/commands/import_product_categories.py
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import json

from category_api.models import Category
from product_api.models import Product


class Command(BaseCommand):
    help = "Import Product ↔ Category relationships"

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to product_categories.json"
        )

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            mappings = json.load(f)

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(mappings)} mappings"
            )
        )

        products = {
            product.legacy_id: product.id
            for product in Product.objects.only(
                "id",
                "legacy_id",
            )
        }

        categories = {
            category.legacy_id: category.id
            for category in Category.objects.only(
                "id",
                "legacy_id",
            )
        }

        through_model = Product.categories.through

        relations = []
        missing_products = 0
        missing_categories = 0

        for item in mappings:
            product_id = products.get(
                item["product_legacy_id"]
            )

            category_id = categories.get(
                item["category_legacy_id"]
            )

            if not product_id:
                missing_products += 1
                continue

            if not category_id:
                missing_categories += 1
                continue

            relations.append(
                through_model(
                    product_id=product_id,
                    category_id=category_id,
                )
            )

        self.stdout.write(
            self.style.WARNING(
                f"Prepared {len(relations)} relations"
            )
        )

        with transaction.atomic():
            through_model.objects.bulk_create(
                relations,
                batch_size=5000,
                ignore_conflicts=True,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(relations)} relations"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Missing Products: {missing_products}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Missing Categories: {missing_categories}"
            )
        )
