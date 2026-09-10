# blog_api/management/commands/import_blog_post_images.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import json
import time

import requests

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from blog_api.models import BlogPost


class Command(BaseCommand):
    help = (
        "Download and import BlogPost featured images "
        "from WordPress blog_post_images.json"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to blog_post_images.json",
        )

        parser.add_argument(
            "--workers",
            type=int,
            default=10,
            help="Number of concurrent image downloads",
        )

        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Download timeout in seconds",
        )

        parser.add_argument(
            "--retries",
            type=int,
            default=3,
            help="Number of download retries",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])

        if not file_path.exists():
            raise CommandError(
                f"File not found: {file_path}"
            )

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as fp:
                images_data = json.load(fp)

        except json.JSONDecodeError as exc:
            raise CommandError(
                f"Invalid JSON file: {exc}"
            )

        if not isinstance(images_data, list):
            raise CommandError(
                "JSON must contain a list of images"
            )

        workers = options["workers"]
        timeout = options["timeout"]
        retries = options["retries"]

        self.stdout.write(
            self.style.NOTICE(
                f"Loaded {len(images_data)} featured images"
            )
        )

        #
        # Preload BlogPosts by legacy ID.
        #
        blog_posts = {
            blog_post.legacy_id: blog_post
            for blog_post in BlogPost.objects.only(
                "id",
                "legacy_id",
                "title",
                "featured_image",
            )
            if blog_post.legacy_id is not None
        }

        image_tasks = []
        missing_blog_posts = set()
        skipped_count = 0

        for image_data in images_data:
            legacy_id = image_data.get(
                "blog_post_legacy_id"
            )

            blog_post = blog_posts.get(legacy_id)

            if not blog_post:
                missing_blog_posts.add(legacy_id)
                continue

            #
            # Skip BlogPosts that already have
            # a featured image.
            #
            if blog_post.featured_image:
                skipped_count += 1
                continue

            image_tasks.append(
                {
                    "blog_post_id": blog_post.id,
                    "blog_post_title": blog_post.title,
                    "blog_post_legacy_id": legacy_id,
                    "image_data": image_data,
                }
            )

        self.stdout.write(
            self.style.NOTICE(
                f"Prepared {len(image_tasks)} image tasks"
            )
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Skipping {skipped_count} existing "
                "featured images"
            )
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Downloading {len(image_tasks)} images "
                f"with {workers} workers"
            )
        )

        success_count = 0
        failed_count = 0

        #
        # Download concurrently.
        #
        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:

            futures = {
                executor.submit(
                    self._download_image,
                    task["image_data"]["image_url"],
                    timeout,
                    retries,
                ): task
                for task in image_tasks
            }

            for index, future in enumerate(
                as_completed(futures),
                start=1,
            ):
                task = futures[future]

                try:
                    content = future.result()

                    self._save_featured_image(
                        task=task,
                        content=content,
                    )

                    success_count += 1

                except Exception as exc:
                    failed_count += 1

                    image_data = task["image_data"]

                    self.stderr.write(
                        self.style.ERROR(
                            "Failed image "
                            f"blog_post="
                            f"{task['blog_post_legacy_id']} "
                            f"attachment="
                            f"{image_data.get('attachment_id')} "
                            f"url="
                            f"{image_data.get('image_url')} "
                            f"error={exc}"
                        )
                    )

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed "
                        f"{index}/{len(image_tasks)}"
                    )

        self.stdout.write("")
        self.stdout.write("=" * 50)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported: {success_count}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Skipped existing: {skipped_count}"
            )
        )

        self.stdout.write(
            self.style.WARNING(
                f"Missing BlogPosts: "
                f"{len(missing_blog_posts)}"
            )
        )

        self.stdout.write(
            self.style.ERROR(
                f"Failed: {failed_count}"
            )
        )

    def _download_image(
        self,
        image_url,
        timeout,
        retries,
    ):
        last_error = None

        for attempt in range(
            1,
            retries + 1,
        ):
            try:
                response = requests.get(
                    image_url,
                    timeout=timeout,
                )

                response.raise_for_status()

                return response.content

            except requests.RequestException as exc:
                last_error = exc

                if attempt < retries:
                    time.sleep(attempt)

        raise last_error

    def _save_featured_image(
        self,
        task,
        content,
    ):
        image_data = task["image_data"]

        relative_file_path = (
            image_data["relative_file_path"]
        )

        filename = Path(
            relative_file_path
        ).name

        blog_post = BlogPost.objects.get(
            id=task["blog_post_id"]
        )

        blog_post.featured_image.save(
            filename,
            ContentFile(content),
            save=True,
        )
