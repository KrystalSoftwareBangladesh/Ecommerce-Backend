# product_api/management/commands/import_product_images.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import json
import time
import requests

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from product_api.models import Product, ProductImage


class Command(BaseCommand):
    help = (
        "Download and import product images from "
        "WordPress product_images.json"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to product_images.json",
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
                products_data = json.load(fp)

        except json.JSONDecodeError as exc:
            raise CommandError(
                f"Invalid JSON file: {exc}"
            )

        if not isinstance(products_data, list):
            raise CommandError(
                "JSON must contain a list of products"
            )

        workers = options["workers"]
        timeout = options["timeout"]
        retries = options["retries"]

        self.stdout.write(
            self.style.NOTICE(
                f"Loaded {len(products_data)} products"
            )
        )

        #
        # Preload products by legacy ID.
        #
        products = {
            product.legacy_id: product
            for product in Product.objects.only(
                "id",
                "legacy_id",
                "name",
            )
            if product.legacy_id is not None
        }

        #
        # Flatten image records.
        #
        image_tasks = []
        missing_products = set()

        for product_data in products_data:
            legacy_id = product_data.get(
                "product_legacy_id"
            )

            product = products.get(legacy_id)

            if not product:
                missing_products.add(legacy_id)
                continue

            for image_data in product_data.get(
                "images",
                [],
            ):
                image_tasks.append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "product_legacy_id": legacy_id,
                        "image_data": image_data,
                    }
                )

        self.stdout.write(
            self.style.NOTICE(
                f"Prepared {len(image_tasks)} image tasks"
            )
        )

        #
        # Find already imported image positions.
        #
        existing_images = set(
            ProductImage.objects.values_list(
                "product_id",
                "display_order",
            )
        )

        tasks_to_process = []
        skipped_count = 0

        for task in image_tasks:
            image_data = task["image_data"]

            key = (
                task["product_id"],
                image_data["display_order"],
            )

            if key in existing_images:
                skipped_count += 1
                continue

            tasks_to_process.append(task)

        self.stdout.write(
            self.style.NOTICE(
                f"Skipping {skipped_count} existing images"
            )
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Downloading "
                f"{len(tasks_to_process)} images "
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
                for task in tasks_to_process
            }

            for index, future in enumerate(
                as_completed(futures),
                start=1,
            ):
                task = futures[future]

                try:
                    content = future.result()

                    self._create_product_image(
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
                            f"product={task['product_legacy_id']} "
                            f"attachment="
                            f"{image_data.get('attachment_id')} "
                            f"url={image_data.get('image_url')} "
                            f"error={exc}"
                        )
                    )

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed "
                        f"{index}/{len(tasks_to_process)}"
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
                f"Missing products: "
                f"{len(missing_products)}"
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

    def _create_product_image(
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

        product_image = ProductImage(
            product_id=task["product_id"],
            alt_text=task["product_name"],
            display_order=image_data[
                "display_order"
            ],
            is_default=image_data[
                "is_default"
            ],
        )

        product_image.image.save(
            filename,
            ContentFile(content),
            save=False,
        )

        product_image.save()
