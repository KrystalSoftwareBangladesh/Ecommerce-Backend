# checkout_api/management/commands/expire_pending_orders.py
from django.core.management.base import BaseCommand

from checkout_api.services import expire_pending_orders


class Command(BaseCommand):
    help = (
        'Cancel PENDING storefront orders whose stock reservation '
        'expired, and release all expired reservations.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of orders to process per batch.',
        )

    def handle(self, *args, **options):
        cancelled, released = expire_pending_orders(
            batch_size=options['batch_size']
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Cancelled {cancelled} expired orders; released '
                f'{released} other expired reservations.'
            )
        )
