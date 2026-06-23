# category_api/management/commands/clean_category_html_entities.py
from html import unescape

from django.core.management.base import BaseCommand
from django.db import transaction

from category_api.models import Category


class Command(BaseCommand):
    help = "Clean HTML entities from category names and descriptions"

    def handle(self, *args, **options):
        categories = Category.objects.all()

        updated_categories = []

        processed = 0
        updated = 0

        for category in categories:
            processed += 1

            original_name = category.name
            original_description = category.description or ""

            cleaned_name = unescape(original_name)
            cleaned_description = unescape(original_description)

            changed = False

            if cleaned_name != original_name:
                category.name = cleaned_name
                changed = True

            if cleaned_description != original_description:
                category.description = cleaned_description
                changed = True

            if changed:
                updated += 1
                updated_categories.append(category)

        with transaction.atomic():
            Category.objects.bulk_update(
                updated_categories,
                ["name", "description"],
                batch_size=1000,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed: {processed}, Updated: {updated}"
            )
        )
