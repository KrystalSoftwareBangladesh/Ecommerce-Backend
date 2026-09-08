# blog_api/management/commands/import_blog_post_tags.py
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from blog_api.models import BlogPost, BlogTag


class Command(BaseCommand):
    help = "Import blog post/tag relationships from blog_post_tags.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to blog_post_tags.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            relationships = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(relationships)} relationships"
            )
        )

        created_count = 0
        skipped_count = 0
        failed_count = 0

        for index, item in enumerate(relationships, start=1):
            post_legacy_id = item.get("blog_post_legacy_id")
            tag_legacy_id = item.get("tag_legacy_id")

            try:
                post = BlogPost.objects.get(
                    legacy_id=post_legacy_id
                )
                tag = BlogTag.objects.get(
                    legacy_id=tag_legacy_id
                )

                relation_exists = post.tags.filter(
                    pk=tag.pk
                ).exists()

                if relation_exists:
                    skipped_count += 1
                else:
                    post.tags.add(tag)
                    created_count += 1

                if index % 500 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(relationships)}"
                    )

            except (BlogPost.DoesNotExist, BlogTag.DoesNotExist) as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Relationship failed "
                        f"(post={post_legacy_id}, "
                        f"tag={tag_legacy_id}): {exc}"
                    )
                )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Relationship failed "
                        f"(post={post_legacy_id}, "
                        f"tag={tag_legacy_id}): {exc}"
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
