# product_api/management/commands/import_brand_metadata.py
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from product_api.models import Brand


class Command(BaseCommand):
    help = (
        "Import Brand metadata from "
        "brand_metadata.json"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to brand_metadata.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        try:
            with open(
                json_file,
                "r",
                encoding="utf-8",
            ) as fp:
                metadata = json.load(fp)

        except FileNotFoundError:
            raise CommandError(
                f"File not found: {json_file}"
            )

        except json.JSONDecodeError as exc:
            raise CommandError(
                f"Invalid JSON file: {exc}"
            )

        if not isinstance(metadata, list):
            raise CommandError(
                "JSON must contain a list of brands"
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Loaded {len(metadata)} Brand records"
            )
        )

        #
        # Preload Brands by legacy ID.
        #
        brands = {
            brand.legacy_id: brand
            for brand in Brand.objects.only(
                "id",
                "legacy_id",
            )
            if brand.legacy_id is not None
        }

        updated_count = 0
        missing_brands = set()
        failed_count = 0

        for row in metadata:
            legacy_id = row.get("legacy_id")

            brand = brands.get(legacy_id)

            if not brand:
                missing_brands.add(legacy_id)
                continue

            try:
                brand.description = row.get(
                    "description",
                    "",
                )
                brand.seo_title = row.get(
                    "seo_title",
                    "",
                )
                brand.seo_description = row.get(
                    "seo_description",
                    "",
                )
                brand.seo_focus_keyword = row.get(
                    "seo_focus_keyword",
                    "",
                )

                brand.save(
                    update_fields=[
                        "description",
                        "seo_title",
                        "seo_description",
                        "seo_focus_keyword",
                    ]
                )

                updated_count += 1

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        "Failed to update Brand "
                        f"legacy_id={legacy_id} "
                        f"name={row.get('name')} "
                        f"error={exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 50)

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated: {updated_count}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Missing Brands: "
                f"{len(missing_brands)}"
            )
        )

        self.stdout.write(
            self.style.ERROR(
                f"Failed: {failed_count}"
            )
        )
