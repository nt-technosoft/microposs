# Generated manually for partial procurement receive batches.

from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_initial'),
        ('partnerships', '0008_alter_procurementexpense_status_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='procurement',
            name='status',
            field=models.CharField(
                choices=[
                    ('OPEN', 'Открыт'),
                    ('PARTIALLY_RECEIVED', 'Частично оприходовано'),
                    ('RECEIVED', 'Получен'),
                    ('CLOSED', 'Закрыт'),
                    ('CANCELLED', 'Отменён'),
                ],
                default='OPEN',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='ProcurementReceiveBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('received_at', models.DateTimeField()),
                ('items_count', models.PositiveIntegerField(default=0)),
                ('total_inventory_uzs', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=20)),
                ('procurement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receive_batches', to='partnerships.procurement')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
                ('warehouse', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='procurement_receive_batches', to='inventory.warehouse')),
            ],
            options={
                'db_table': 'partnerships_procurement_receive_batch',
                'ordering': ['-received_at', '-id'],
                'indexes': [
                    models.Index(fields=['procurement', 'received_at'], name='partnership_procure_f0a2ed_idx'),
                    models.Index(fields=['warehouse'], name='partnership_warehou_3f31c8_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ProcurementReceiveBatchLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('unit_purchase_price_uzs', models.DecimalField(decimal_places=2, max_digits=20)),
                ('allocated_expense_uzs', models.DecimalField(decimal_places=2, max_digits=20)),
                ('landed_cost_per_unit_uzs', models.DecimalField(decimal_places=2, max_digits=20)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='partnerships.procurementreceivebatch')),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receive_batch_lines', to='partnerships.procurementitem')),
                ('lot', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='receive_batch_line', to='inventory.lot')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_procurement_receive_batch_line',
                'indexes': [
                    models.Index(fields=['batch'], name='partnership_batch_i_5e6e1d_idx'),
                    models.Index(fields=['item'], name='partnership_item_id_bf9414_idx'),
                    models.Index(fields=['lot'], name='partnership_lot_id_776a8e_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ProcurementReceiveBatchExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('allocated_amount_uzs', models.DecimalField(decimal_places=2, max_digits=20)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='partnerships.procurementreceivebatch')),
                ('expense', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receive_batch_expenses', to='partnerships.procurementexpense')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_procurement_receive_batch_expense',
                'indexes': [
                    models.Index(fields=['batch'], name='partnership_batch_i_2b88d7_idx'),
                    models.Index(fields=['expense'], name='partnership_expense_cebc8a_idx'),
                ],
            },
        ),
    ]
