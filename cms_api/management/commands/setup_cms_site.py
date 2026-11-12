# cms_api/management/commands/setup_cms_site.py
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from wagtail.models import Site


class Command(BaseCommand):
    help = (
        "Point the default Wagtail site at the public storefront "
        "hostname. Idempotent; run once after migrate (issue#463)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hostname",
            default="",
            help=(
                "Public hostname (optionally host:port). Defaults "
                "to the host in FRONTEND_BASE_URL."
            ),
        )

    def handle(self, *args, **options):
        target = options["hostname"] or settings.FRONTEND_BASE_URL
        if "://" not in target:
            target = "https://" + target
        parsed = urlparse(target)
        hostname = parsed.hostname or "localhost"
        port = parsed.port or (
            443 if parsed.scheme == "https" else 80
        )
        with transaction.atomic():
            site = Site.objects.get(is_default_site=True)
            site.hostname = hostname
            site.port = port
            site.save()
        self.stdout.write(
            "Default Wagtail site set to %s:%s" % (hostname, port)
        )
