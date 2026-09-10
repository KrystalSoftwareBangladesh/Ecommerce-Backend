# blog_api/management/commands/import_blog_post_authors.py
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from blog_api.models import BlogPost
from user_api.models import User


class Command(BaseCommand):
    help = "Import blog post/author relationships from blog_post_authors.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to blog_post_authors.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            relations = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(relations)} relationships"
            )
        )

        mapped_count = 0
        missing_post_count = 0
        missing_user_count = 0
        failed_count = 0

        for index, item in enumerate(relations, start=1):
            blog_post_legacy_id = item.get(
                "blog_post_legacy_id"
            )
            author_legacy_id = item.get(
                "author_legacy_id"
            )

            try:
                if not blog_post_legacy_id:
                    raise ValueError(
                        "Missing blog_post_legacy_id"
                    )

                if not author_legacy_id:
                    raise ValueError(
                        "Missing author_legacy_id"
                    )

                blog_post = BlogPost.objects.filter(
                    legacy_id=blog_post_legacy_id
                ).first()

                if not blog_post:
                    missing_post_count += 1

                    self.stderr.write(
                        self.style.WARNING(
                            f"Blog post {blog_post_legacy_id} "
                            f"not found"
                        )
                    )
                    continue

                author = User.objects.filter(
                    legacy_id=author_legacy_id
                ).first()

                if not author:
                    missing_user_count += 1

                    self.stderr.write(
                        self.style.WARNING(
                            f"Author {author_legacy_id} "
                            f"not found for blog post "
                            f"{blog_post_legacy_id}"
                        )
                    )
                    continue

                blog_post.author = author
                blog_post.save(
                    update_fields=["author"]
                )

                mapped_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(relations)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Blog post {blog_post_legacy_id} "
                        f"author mapping failed: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"Mapped: {mapped_count}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Missing blog posts: {missing_post_count}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Missing authors: {missing_user_count}"
            )
        )
        self.stdout.write(
            self.style.ERROR(
                f"Failed: {failed_count}"
            )
        )
