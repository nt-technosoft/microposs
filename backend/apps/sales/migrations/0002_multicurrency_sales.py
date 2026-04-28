from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='possession',
            name='opening_cash_by_currency',
            field=models.JSONField(blank=True, default=dict, help_text='Native opening cash by currency, e.g. {"UZS": "100000.00", "USD": "20.00"}.'),
        ),
        migrations.AddField(
            model_name='possession',
            name='expected_cash_by_currency',
            field=models.JSONField(blank=True, default=dict, help_text='Native expected cash by currency calculated on close.'),
        ),
        migrations.AddField(
            model_name='possession',
            name='actual_cash_by_currency',
            field=models.JSONField(blank=True, default=dict, help_text='Native actual cash by currency entered on close.'),
        ),
        migrations.AddField(
            model_name='possession',
            name='cash_difference_by_currency',
            field=models.JSONField(blank=True, default=dict, help_text='Native cash difference by currency.'),
        ),
        migrations.AddField(
            model_name='saleline',
            name='operation_currency',
            field=models.CharField(default='UZS', max_length=3),
        ),
        migrations.AddField(
            model_name='saleline',
            name='operation_unit_price',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Native sale price per unit as entered by cashier.', max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='saleline',
            name='fx_rate_snapshot',
            field=models.DecimalField(decimal_places=6, default=Decimal('1'), help_text='Immutable FX snapshot used to convert operation price to UZS.', max_digits=14),
        ),
        migrations.AlterField(
            model_name='saleline',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, help_text='Functional UZS sale price per unit.', max_digits=12),
        ),
    ]
