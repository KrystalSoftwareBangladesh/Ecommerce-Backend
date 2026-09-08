# blog_api/management/commands/import_blog_posts.py
import json
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from blog_api.models import BlogPost


class Command(BaseCommand):
    help = "Import blog posts from blog_posts.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to blog_posts.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            posts = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(posts)} blog posts"
            )
        )

        created_count = 0
        updated_count = 0
        failed_count = 0

        for index, item in enumerate(posts, start=1):
            try:
                published_at = self.parse_datetime(
                    item.get("published_at")
                )

                post, created = BlogPost.objects.update_or_create(
                    legacy_id=item["legacy_id"],
                    defaults={
                        "title": item.get("title", ""),
                        "slug": item.get("slug", ""),
                        "content": item.get("content", ""),
                        "status": item["status"],
                        "published_at": published_at,
                        "seo_title": item.get("seo_title", ""),
                        "seo_description": item.get(
                            "seo_description",
                            "",
                        ),
                        "seo_focus_keyword": item.get(
                            "seo_focus_keyword",
                            "",
                        ),
                        "seo_noindex": item.get(
                            "seo_noindex",
                            False,
                        ),
                        "seo_nofollow": item.get(
                            "seo_nofollow",
                            False,
                        ),
                        "author": None,
                        "featured_image": None,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(posts)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"Blog post {item.get('legacy_id')} "
                        f"failed: {exc}"
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

    @staticmethod
    def parse_datetime(value):
        if not value:
            return None

        dt = datetime.fromisoformat(value)

        if timezone.is_naive(dt):
            dt = timezone.make_aware(
                dt,
                timezone.get_current_timezone(),
            )

        return dt
