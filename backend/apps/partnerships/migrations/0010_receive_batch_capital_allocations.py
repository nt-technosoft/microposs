# Generated manually for receive batch capital/profit snapshots.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_investor_invites'),
        ('partnerships', '0009_procurement_partial_receive_batches'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProcurementReceiveBatchCapitalAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('role', models.CharField(choices=[('INVESTOR', 'Инвестор'), ('OPERATOR', 'Оператор')], max_length=20)),
                ('amount_contract_currency', models.DecimalField(decimal_places=2, max_digits=20)),
                ('capital_share', models.DecimalField(decimal_places=6, max_digits=8)),
                ('profit_share', models.DecimalField(decimal_places=6, max_digits=8)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='capital_allocations', to='partnerships.procurementreceivebatch')),
                ('partner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='procurement_receive_batch_allocations', to='core.partner')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_procurement_receive_batch_capital_allocation',
                'indexes': [
                    models.Index(fields=['batch'], name='partnership_batch_i_19d320_idx'),
                    models.Index(fields=['partner'], name='partnership_partner_32d0cb_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('batch', 'partner'), name='uq_receive_batch_capital_partner'),
                ],
            },
        ),
    ]
