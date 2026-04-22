from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='investmentcontract',
            name='mudaraba_ratio',
            field=models.DecimalField(
                decimal_places=6,
                help_text='m in [0..1]; investor profit = capital * m',
                max_digits=8,
            ),
        ),
    ]
