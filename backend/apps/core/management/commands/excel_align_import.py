"""Excel-to-MicroPOS alignment import command."""

from django.core.management.base import BaseCommand, CommandError

from apps.core.excel_alignment import ExcelAlignmentImporter, load_snapshot
from apps.core.models import ExcelImportBatch


class Command(BaseCommand):
    help = (
        'Run Excel alignment pipeline for a tenant. '
        'Source is a local JSON snapshot (canonical or connector format).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            required=True,
            help='Target tenant (Business) ID.',
        )
        parser.add_argument(
            '--mode',
            choices=[
                ExcelImportBatch.Mode.DRY_RUN,
                ExcelImportBatch.Mode.LOAD_MASTER,
                ExcelImportBatch.Mode.LOAD_TRANSACTIONS,
                ExcelImportBatch.Mode.RECONCILE,
            ],
            required=True,
        )
        parser.add_argument(
            '--source-file',
            type=str,
            required=True,
            help='Path to JSON snapshot file.',
        )
        parser.add_argument(
            '--seller-user-id',
            type=int,
            required=False,
            help='Optional user ID used for imported sales.',
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Stop on first row failure.',
        )
        parser.add_argument(
            '--notes',
            type=str,
            default='',
            help='Optional batch notes.',
        )

    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        mode = options['mode']
        source_file = options['source_file']
        seller_user_id = options.get('seller_user_id')
        strict = bool(options.get('strict'))
        notes = options.get('notes') or ''

        try:
            snapshot = load_snapshot(source_file)
        except FileNotFoundError as exc:
            raise CommandError(f'Source file not found: {source_file}') from exc
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f'Unable to read source file: {exc}') from exc

        importer = ExcelAlignmentImporter(
            tenant_id=tenant_id,
            mode=mode,
            source_ref=source_file,
            strict=strict,
            seller_user_id=seller_user_id,
            notes=notes,
        )

        summary = importer.run(snapshot)
        batch = importer.ctx.batch
        self.stdout.write(self.style.SUCCESS(
            f'Excel alignment batch #{batch.id} finished with status={batch.status}'
        ))
        self.stdout.write(f"Mode: {mode}")
        self.stdout.write(f"Source: {source_file}")
        self.stdout.write(f"Totals: {summary}")
