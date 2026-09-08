# blog_api/management/commands/import_blog_tags.py
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from blog_api.models import BlogTag


class Command(BaseCommand):
    help = "Import blog tags from blog_tags.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to blog_tags.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            tags = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(tags)} blog tags"
            )
        )

        created_count = 0
        updated_count = 0
        failed_count = 0

        for index, item in enumerate(tags, start=1):
            try:
                tag, created = BlogTag.objects.update_or_create(
                    legacy_id=item["legacy_id"],
                    defaults={
                        "name": item["name"],
                        "slug": item["slug"],
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(tags)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Blog tag {item.get('legacy_id')} failed: {exc}"
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
