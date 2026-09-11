# product_api/management/commands/import_brands.py
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from product_api.models import Brand


class Command(BaseCommand):
    help = "Import brands from brands.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to brands.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            brands = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(brands)} brands"
            )
        )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        for index, item in enumerate(brands, start=1):
            legacy_id = item.get("legacy_id")
            name = (item.get("name") or "").strip()
            slug = (item.get("slug") or "").strip()

            try:
                if not legacy_id:
                    raise ValueError("Missing legacy_id")

                if not name:
                    raise ValueError("Missing brand name")

                if not slug:
                    raise ValueError("Missing brand slug")

                brand = Brand.objects.filter(
                    legacy_id=legacy_id
                ).first()

                if brand:
                    brand.name = name
                    brand.slug = slug
                    brand.save(
                        update_fields=[
                            "name",
                            "slug",
                        ]
                    )

                    updated_count += 1

                else:
                    name_collision = Brand.objects.filter(
                        name__iexact=name
                    ).first()

                    if name_collision:
                        skipped_count += 1

                        self.stderr.write(
                            self.style.WARNING(
                                f"Brand {legacy_id} skipped: "
                                f"name '{name}' already belongs "
                                f"to Brand {name_collision.pk}"
                            )
                        )
                        continue

                    slug_collision = Brand.objects.filter(
                        slug__iexact=slug
                    ).first()

                    if slug_collision:
                        skipped_count += 1

                        self.stderr.write(
                            self.style.WARNING(
                                f"Brand {legacy_id} skipped: "
                                f"slug '{slug}' already belongs "
                                f"to Brand {slug_collision.pk}"
                            )
                        )
                        continue

                    Brand.objects.create(
                        legacy_id=legacy_id,
                        name=name,
                        slug=slug,
                    )

                    created_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(brands)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Brand {legacy_id} failed: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {created_count}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated: {updated_count}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Skipped: {skipped_count}"
            )
        )
        self.stdout.write(
            self.style.ERROR(
                f"Failed: {failed_count}"
            )
        )
