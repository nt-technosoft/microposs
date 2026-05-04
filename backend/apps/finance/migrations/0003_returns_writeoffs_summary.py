from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailysummary',
            name='total_return_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14),
        ),
        migrations.AddField(
            model_name='dailysummary',
            name='total_return_restock_cogs',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14),
        ),
        migrations.AddField(
            model_name='dailysummary',
            name='total_return_disposal_loss',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14),
        ),
        migrations.AddField(
            model_name='cashflowsummary',
            name='cash_out_refunds',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14),
        ),
        migrations.AlterField(
            model_name='refund',
            name='customer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='refunds',
                to='customers.customer',
            ),
        ),
        migrations.AlterField(
            model_name='refund',
            name='method',
            field=models.CharField(
                choices=[
                    ('cash', 'Наличные'),
                    ('plastik', 'Карт-терминал'),
                    ('transfer', 'Перевод'),
                    ('receivable_offset', 'Зачёт долга'),
                ],
                max_length=20,
            ),
        ),
    ]
