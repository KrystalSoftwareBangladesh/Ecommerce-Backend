# blog_api/management/commands/import_blog_post_categories.py
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from blog_api.models import BlogPost
from category_api.models import Category


class Command(BaseCommand):
    help = """
        Import blog post/category relationships using the blog category mapping
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to blog_post_categories.json",
        )
        parser.add_argument(
            "--mapping-file",
            type=str,
            default="resources/blog_category_mapping.json",
            help="Path to blog category mapping JSON",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]
        mapping_file = options["mapping_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )
        with open(json_file, "r", encoding="utf-8") as fp:
            relationships = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(f"Loading {mapping_file}")
        )
        with open(mapping_file, "r", encoding="utf-8") as fp:
            mappings = json.load(fp)

        category_mapping = {
            item["blog_category_legacy_id"]: item["category_id"]
            for item in mappings
        }

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(relationships)} blog post/category relationships"
            )
        )
        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(category_mapping)} category mappings"
            )
        )

        created_count = 0
        skipped_count = 0
        failed_count = 0

        for index, item in enumerate(relationships, start=1):
            post_legacy_id = item.get("blog_post_legacy_id")
            category_legacy_id = item.get("category_legacy_id")

            try:
                category_id = category_mapping.get(category_legacy_id)

                if category_id is None:
                    raise ValueError(
                        f"No Django Category mapping found for "
                        f"blog category legacy ID {category_legacy_id}"
                    )

                post = BlogPost.objects.get(
                    legacy_id=post_legacy_id
                )
                category = Category.objects.get(
                    pk=category_id
                )

                relation_exists = post.categories.filter(
                    pk=category.pk
                ).exists()

                if relation_exists:
                    skipped_count += 1
                else:
                    post.categories.add(category)
                    created_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(relationships)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Relationship failed "
                        f"(post={post_legacy_id}, "
                        f"category={category_legacy_id}): {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Created: {created_count}")
        )
        self.stdout.write(
            self.style.NOTICE(f"Skipped: {skipped_count}")
        )
        self.stdout.write(
            self.style.WARNING(f"Failed: {failed_count}")
        )
