# inventory_api/management/commands/expire_reservations.py
from django.core.management.base import BaseCommand

from inventory_api.services.reservation import (
    expire_reservations,
)


class Command(BaseCommand):
    help = (
        'Release expired active inventory '
        'reservations.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of reservations to process per batch.',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        total = expire_reservations(
            batch_size=batch_size
        )
        if total:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Released {total} expired '
                    f'reservations.'
                )
            )
        else:
            self.stdout.write(
                'No expired reservations found.'
            )
