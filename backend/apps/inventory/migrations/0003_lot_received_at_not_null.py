from django.db import migrations, models
from django.utils import timezone


def backfill_received_at(apps, schema_editor):
    Lot = apps.get_model('inventory', 'Lot')
    # Backfill from created_at as best available approximation of receive date.
    # Legacy lots created via old Receipt path may have had NULL received_at.
    Lot.objects.filter(received_at__isnull=True).update(
        received_at=models.F('created_at'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(backfill_received_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='lot',
            name='received_at',
            field=models.DateTimeField(),
        ),
    ]
