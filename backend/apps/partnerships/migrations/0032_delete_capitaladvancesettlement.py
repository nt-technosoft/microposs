from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0031_partnerjournallinetag_flow'),
    ]

    operations = [
        migrations.DeleteModel(
            name='CapitalAdvanceSettlement',
        ),
    ]
