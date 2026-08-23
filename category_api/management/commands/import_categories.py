import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from category_api.models import Category


class Command(BaseCommand):
    help = 'Import categories from a JSON file into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to the categories JSON file (e.g., resources/categories.json)'   # noqa
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing categories before import'
        )

    def handle(self, *args, **options):
        file_path = Path(options['file_path'])

        # Validate file exists
        if not file_path.exists():
            raise CommandError(f'File not found: {file_path}')

        # Load JSON data
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON file: {e}')
        except IOError as e:
            raise CommandError(f'Error reading file: {e}')

        # Validate data structure
        if not isinstance(data, list):
            raise CommandError('JSON must be an list of categories')

        # Clear existing categories if requested
        if options['clear']:
            Category.objects.all().delete()
            self.stdout.write(
                self.style.WARNING('Cleared all existing categories')
            )

        # Import categories with transaction
        try:
            with transaction.atomic():
                created_count = self._import_categories(data)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully imported {created_count} categories'
                )
            )
        except Exception as e:
            raise CommandError(f'Error importing categories: {e}')

    def _import_categories(self, categories_data):
        categories_by_legacy_id = {}

        #
        # PASS 1
        # Create all categories without parent
        #
        for index, item in enumerate(categories_data):
            category = Category.objects.create(
                name=item["name"],
                slug=item["slug"],
                description=item.get("description") or "",
                legacy_id=item["legacy_id"],
                display_order=index,
            )

            categories_by_legacy_id[item["legacy_id"]] = category

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {len(categories_by_legacy_id)} categories"
            )
        )

        #
        # PASS 2
        # Attach parents
        #
        updated = 0

        for item in categories_data:
            parent_legacy_id = item.get("parent_legacy_id")

            if not parent_legacy_id:
                continue

            category = categories_by_legacy_id[item["legacy_id"]]
            parent = categories_by_legacy_id.get(parent_legacy_id)

            if parent:
                category.parent = parent
                category.save(update_fields=["parent"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Linked {updated} parent-child relationships"
            )
        )
