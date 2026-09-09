# blog_api/management/commands/import_blog_categories.py
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from category_api.models import Category


class Command(BaseCommand):
    help = """
    Import and reconcile WordPress blog categories into the
    shared Category model
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to blog_categories.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            blog_categories = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(blog_categories)} blog categories"
            )
        )

        categories_by_key = {
            (category.name, category.slug): category
            for category in Category.objects.all()
        }

        blog_categories_by_id = {
            item["legacy_id"]: item
            for item in blog_categories
        }
        print(blog_categories_by_id)

        category_mapping = {}

        created_count = 0
        reused_count = 0

        # Resolve categories in parent-first order.
        pending = list(blog_categories)

        while pending:
            progress = False
            remaining = []

            for item in pending:
                legacy_id = item["legacy_id"]
                name = item["name"]
                slug = item["slug"]
                parent_legacy_id = item.get("parent") or 0

                # Reuse an existing category with the same name and slug.
                existing = categories_by_key.get((name, slug))

                if existing:
                    category_mapping[legacy_id] = existing.pk
                    reused_count += 1
                    progress = True
                    continue

                # Root category.
                if not parent_legacy_id:
                    category = Category.objects.create(
                        name=name,
                        slug=slug,
                    )

                    categories_by_key[(name, slug)] = category
                    category_mapping[legacy_id] = category.pk

                    created_count += 1
                    progress = True
                    continue

                # Parent must already have been resolved.
                parent_pk = category_mapping.get(parent_legacy_id)

                if not parent_pk:
                    remaining.append(item)
                    continue

                category = Category.objects.create(
                    name=name,
                    slug=slug,
                    parent_id=parent_pk,
                )

                categories_by_key[(name, slug)] = category
                category_mapping[legacy_id] = category.pk

                created_count += 1
                progress = True

            if not progress:
                unresolved = [
                    {
                        "legacy_id": item["legacy_id"],
                        "name": item["name"],
                        "parent": item.get("parent"),
                    }
                    for item in remaining
                ]

                raise ValueError(
                    "Could not resolve category hierarchy. "
                    f"Unresolved categories: {unresolved}"
                )

            pending = remaining

        # Save the Blog category → Django Category mapping.
        mapping_file = Path("resources/blog_category_mapping.json")

        with open(mapping_file, "w", encoding="utf-8") as fp:
            json.dump(
                [
                    {
                        "blog_category_legacy_id": legacy_id,
                        "category_id": category_id,
                    }
                    for legacy_id, category_id in sorted(
                        category_mapping.items()
                    )
                ],
                fp,
                ensure_ascii=False,
                indent=2,
            )

        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Created: {created_count}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Reused: {reused_count}")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Mapped: {len(category_mapping)}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Mapping saved: {mapping_file}"
            )
        )
