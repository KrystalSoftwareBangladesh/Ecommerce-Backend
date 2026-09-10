# user_api/management/commands/import_users.py
import json

from django.core.management.base import BaseCommand
from django.db import transaction

from user_api.models import User
from customer_api.models import CustomerProfile


class Command(BaseCommand):
    help = "Import WordPress users from woocommerce_users.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to woocommerce_users.json",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_file = options["json_file"]

        self.stdout.write(
            self.style.NOTICE(f"Loading {json_file}")
        )

        with open(json_file, "r", encoding="utf-8") as fp:
            users = json.load(fp)

        self.stdout.write(
            self.style.NOTICE(
                f"Found {len(users)} users"
            )
        )

        created_count = 0
        updated_count = 0
        profile_created_count = 0
        profile_updated_count = 0
        skipped_count = 0
        failed_count = 0

        for index, item in enumerate(users, start=1):
            legacy_id = item.get("legacy_id")
            username = item.get("username", "").strip()
            email = self.clean_value(item.get("email"))
            first_name = self.clean_value(item.get("first_name"))
            last_name = self.clean_value(item.get("last_name"))
            billing_phone = self.clean_value(item.get("billing_phone"))
            role = item.get("role")

            try:
                if not legacy_id:
                    raise ValueError("Missing legacy_id")

                if not username:
                    raise ValueError("Missing username")

                if role not in {
                    choice[0] for choice in User.ROLE_CHOICES
                }:
                    raise ValueError(
                        f"Invalid role: {role}"
                    )

                user = User.objects.filter(
                    legacy_id=legacy_id
                ).first()

                if user:
                    user.username = username
                    user.email = email
                    user.first_name = first_name
                    user.last_name = last_name
                    user.role = role
                    user.is_active = True
                    user.save()

                    updated_count += 1

                else:
                    collision = self.find_collision(
                        username=username,
                        email=email,
                    )

                    if collision:
                        skipped_count += 1

                        self.stderr.write(
                            self.style.WARNING(
                                f"User {legacy_id} skipped: "
                                f"{collision}"
                            )
                        )
                        continue

                    user = User(
                        legacy_id=legacy_id,
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        role=role,
                        is_active=True,
                    )
                    user.set_unusable_password()
                    user.save()

                    created_count += 1

                if role == "CUSTOMER":
                    profile, profile_created = (
                        CustomerProfile.objects.get_or_create(
                            user=user,
                            defaults={
                                "phone": billing_phone,
                                "customer_type": "WEBSITE",
                                "is_active": True,
                            },
                        )
                    )

                    if profile_created:
                        profile_created_count += 1
                    else:
                        profile.phone = billing_phone
                        profile.customer_type = "WEBSITE"
                        profile.is_active = True
                        profile.save()

                        profile_updated_count += 1

                if index % 100 == 0:
                    self.stdout.write(
                        f"Processed {index}/{len(users)}"
                    )

            except Exception as exc:
                failed_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f"User {legacy_id} failed: {exc}"
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"Created users: {created_count}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated users: {updated_count}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created customer profiles: "
                f"{profile_created_count}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated customer profiles: "
                f"{profile_updated_count}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Skipped users: {skipped_count}"
            )
        )
        self.stdout.write(
            self.style.ERROR(
                f"Failed: {failed_count}"
            )
        )

    @staticmethod
    def clean_value(value):
        if value is None:
            return ""

        return str(value).strip()

    @staticmethod
    def find_collision(username, email):
        username_collision = User.objects.filter(
            username__iexact=username
        ).first()

        if username_collision:
            return (
                f"username '{username}' already belongs "
                f"to Django user {username_collision.pk}"
            )

        if email:
            email_collision = User.objects.filter(
                email__iexact=email
            ).first()

            if email_collision:
                return (
                    f"email '{email}' already belongs "
                    f"to Django user {email_collision.pk}"
                )

        return None
