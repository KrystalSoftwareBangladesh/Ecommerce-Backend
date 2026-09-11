# customer_api/management/commands/import_customer_addresses.py
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from customer_api.models import CustomerAddress, CustomerProfile
from user_api.models import User


def clean_postcode(value):
    value = (value or "").strip()

    if len(value) > 50:
        return ""

    return value


class Command(BaseCommand):
    help = "Import customer addresses from WooCommerce export"

    def handle(self, *args, **options):
        input_file = Path("resources/customer_addresses.json")

        if not input_file.exists():
            self.stdout.write(
                self.style.ERROR(
                    f"Resource file not found: {input_file}"
                )
            )
            return

        with open(input_file, "r", encoding="utf-8") as fp:
            rows = json.load(fp)

        self.stdout.write(
            f"Found {len(rows)} users with address data"
        )

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for row in rows:
            user_legacy_id = row.get("user_legacy_id")

            if not user_legacy_id:
                self.stdout.write(
                    self.style.WARNING(
                        "Skipping row without user_legacy_id"
                    )
                )
                skipped_count += 1
                continue

            user = User.objects.filter(
                legacy_id=user_legacy_id
            ).first()

            if not user:
                self.stdout.write(
                    self.style.WARNING(
                        f"User not found for legacy_id={user_legacy_id}"
                    )
                )
                skipped_count += 1
                continue

            customer_profile = CustomerProfile.objects.filter(
                user=user
            ).first()

            if not customer_profile:
                self.stdout.write(
                    self.style.WARNING(
                        f"CustomerProfile not found for "
                        f"user legacy_id={user_legacy_id}"
                    )
                )
                skipped_count += 1
                continue

            addresses = []

            billing_address_1 = (
                row.get("billing_address_1") or ""
            ).strip()

            if billing_address_1:
                addresses.append(
                    (
                        CustomerAddress.AddressType.BILLING,
                        {
                            "first_name": row.get(
                                "billing_first_name"
                            ) or "",
                            "last_name": row.get(
                                "billing_last_name"
                            ) or "",
                            "company": row.get(
                                "billing_company"
                            ) or "",
                            "address_1": billing_address_1,
                            "address_2": row.get(
                                "billing_address_2"
                            ) or "",
                            "city": row.get(
                                "billing_city"
                            ) or "",
                            "state": row.get(
                                "billing_state"
                            ) or "",
                            "postcode": clean_postcode(
                                row.get("billing_postcode")
                            ),
                            "country": row.get(
                                "billing_country"
                            ) or "",
                            "phone": row.get(
                                "billing_phone"
                            ) or "",
                        },
                    )
                )

            shipping_address_1 = (
                row.get("shipping_address_1") or ""
            ).strip()

            if shipping_address_1:
                addresses.append(
                    (
                        CustomerAddress.AddressType.SHIPPING,
                        {
                            "first_name": row.get(
                                "shipping_first_name"
                            ) or "",
                            "last_name": row.get(
                                "shipping_last_name"
                            ) or "",
                            "company": row.get(
                                "shipping_company"
                            ) or "",
                            "address_1": shipping_address_1,
                            "address_2": row.get(
                                "shipping_address_2"
                            ) or "",
                            "city": row.get(
                                "shipping_city"
                            ) or "",
                            "state": row.get(
                                "shipping_state"
                            ) or "",
                            "postcode": row.get(
                                "shipping_postcode"
                            ) or "",
                            "country": row.get(
                                "shipping_country"
                            ) or "",
                            "phone": row.get(
                                "shipping_phone"
                            ) or "",
                        },
                    )
                )

            for address_type, address_data in addresses:
                with transaction.atomic():
                    address, created = (
                        CustomerAddress.objects.update_or_create(
                            customer=customer_profile,
                            address_type=address_type,
                            defaults=address_data,
                        )
                    )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Customer address import completed."
            )
        )
        self.stdout.write(
            f"Created: {created_count}"
        )
        self.stdout.write(
            f"Updated: {updated_count}"
        )
        self.stdout.write(
            f"Skipped: {skipped_count}"
        )
