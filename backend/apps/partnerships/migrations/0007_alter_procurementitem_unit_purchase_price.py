from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0006_procurementexpensetarget_investmentagreement_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='procurementitem',
            name='unit_purchase_price',
            field=models.DecimalField(decimal_places=6, max_digits=14),
        ),
    ]

