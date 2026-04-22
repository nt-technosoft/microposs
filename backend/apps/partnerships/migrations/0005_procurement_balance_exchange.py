from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0004_procurement_line_statuses'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcurementBalanceExchange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('from_currency', models.CharField(default='UZS', max_length=3)),
                ('from_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('to_currency', models.CharField(default='USD', max_length=3)),
                ('to_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('rate', models.DecimalField(decimal_places=6, default=Decimal('1'), max_digits=14)),
                ('date', models.DateTimeField()),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('balance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exchanges', to='partnerships.procurementbalance')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_balance_exchange',
                'ordering': ['-date', '-id'],
                'abstract': False,
            },
        ),
        migrations.AddIndex(
            model_name='procurementbalanceexchange',
            index=models.Index(fields=['balance'], name='partnership_balance_8b2668_idx'),
        ),
    ]
