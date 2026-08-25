# content_security_api/management/commands/scan_content.py
from django.core.management.base import BaseCommand, CommandError

from rest_framework.exceptions import ValidationError

from content_security_api.constants import SCAN_BATCH_SIZE, SCANNER_VERSION
from content_security_api.models import ScanContentType
from content_security_api.services import (
    load_rule_set,
    scan_all,
    scan_content_type,
    scan_object,
)
from content_security_api.services.content_sources import (
    get_content_source,
)


class Command(BaseCommand):
    help = (
        'Scan stored content for suspicious, injected or spam patterns. '
        'Detects and reports only; content is never modified.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=[choice for choice, _ in ScanContentType.choices],
            help='Scan a single content type instead of all of them'
        )
        parser.add_argument(
            '--object-id',
            type=int,
            help='Scan one object. Requires --type.'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Scan every supported content type. This is the default.'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=SCAN_BATCH_SIZE,
            help=f'Rows fetched per query (default {SCAN_BATCH_SIZE})'
        )

    def handle(self, *args, **options):
        content_type = options.get('type')
        object_id = options.get('object_id')
        batch_size = options['batch_size']

        if object_id and not content_type:
            raise CommandError('--object-id requires --type.')

        if batch_size < 1:
            raise CommandError('--batch-size must be at least 1.')

        # Rules are read and compiled once for the whole run.
        rule_set = load_rule_set()

        try:
            result = self._run(
                content_type,
                object_id,
                rule_set,
                batch_size,
            )
        except ValidationError as error:
            raise CommandError(str(error.detail))

        self._report(result)

    def _run(self, content_type, object_id, rule_set, batch_size):
        if object_id:
            source = get_content_source(content_type)

            return scan_object(
                content_type=content_type,
                obj=source.get_object(object_id),
                rule_set=rule_set,
            )

        if content_type:
            self.stdout.write(f'Scanning {content_type} content...')

            return scan_content_type(
                content_type=content_type,
                rule_set=rule_set,
                batch_size=batch_size,
                progress=self._progress,
            )

        self.stdout.write('Scanning all supported content types...')

        return scan_all(
            rule_set=rule_set,
            batch_size=batch_size,
            progress=self._progress,
        )

    def _progress(self, obj):
        """
        Placeholder hook kept quiet so the command stays usable in cron.
        """
        return None

    def _report(self, result):
        self.stdout.write(
            f'Scanner version: {SCANNER_VERSION}'
        )
        self.stdout.write(
            f'Objects scanned: {result.scanned_objects}'
        )
        self.stdout.write(
            f'Fields scanned: {result.scanned_fields}'
        )
        self.stdout.write(
            f'Fields with findings: {result.flagged_fields}'
        )
        self.stdout.write(
            f'Findings recorded: {result.total_findings}'
        )

        for status, count in sorted(result.status_counts().items()):
            self.stdout.write(f'  {status}: {count}')

        self.stdout.write(
            self.style.SUCCESS('Content scan complete.')
        )
