from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_investmentprofile'),
        ('finance', '0012_alter_cashaccount_kind_alter_payment_target_type_and_more'),
        ('partnerships', '0040_profile_payouts_and_fund_contribution_idempotency'),
    ]

    operations = [
        migrations.AddField(
            model_name='partnerpositionreadmodel',
            name='capital_rolled_to_pool_uzs',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=20),
        ),
        migrations.AddField(
            model_name='payoutpolicy',
            name='trigger_mode',
            field=models.CharField(choices=[('ANY', 'Interval OR threshold'), ('ALL', 'Interval AND threshold')], default='ANY', max_length=8),
        ),
        migrations.CreateModel(
            name='PayoutDecision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('decision_type', models.CharField(choices=[('PAY_OUT', 'Pay out recovered capital'), ('ROLL_OVER_CAPITAL', 'Roll recovered capital into pool'), ('CAPITALIZE_PROFIT', 'Capitalize profit')], max_length=24)),
                ('amount_uzs', models.DecimalField(decimal_places=2, max_digits=20)),
                ('currency', models.CharField(default='UZS', max_length=3)),
                ('decided_at', models.DateTimeField()),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('CONFIRMED', 'Confirmed'), ('CANCELLED', 'Cancelled')], default='CONFIRMED', max_length=20)),
                ('notes', models.TextField(blank=True, default='')),
                ('client_request_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('agreement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payout_decisions', to='partnerships.investmentagreement')),
                ('source_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payout_decisions', to='finance.cashaccount')),
                ('tenant', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_payout_decision',
                'ordering': ['-decided_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='CapitalRollover',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=20)),
                ('currency', models.CharField(default='UZS', max_length=3)),
                ('fx_rate', models.DecimalField(decimal_places=6, default=Decimal('1'), max_digits=14)),
                ('fx_rate_source', models.CharField(blank=True, default='', max_length=16)),
                ('fx_rate_date', models.DateField(blank=True, null=True)),
                ('amount_uzs', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=20)),
                ('date', models.DateTimeField()),
                ('notes', models.TextField(blank=True, default='')),
                ('client_request_id', models.UUIDField(blank=True, db_index=True, null=True)),
                ('agreement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='capital_rollovers', to='partnerships.investmentagreement')),
                ('decision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='capital_rollovers', to='partnerships.payoutdecision')),
                ('from_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='capital_rollovers', to='finance.cashaccount')),
                ('partner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='capital_rollovers', to='core.partner')),
                ('procurement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='capital_rollovers', to='partnerships.procurement')),
                ('tenant', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_capital_rollover',
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='PayoutDecisionAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('amount_uzs', models.DecimalField(decimal_places=2, max_digits=20)),
                ('available_uzs', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=20)),
                ('capital_rollover', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payout_decision_allocation', to='partnerships.capitalrollover')),
                ('capital_withdrawal', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payout_decision_allocation', to='partnerships.agreementwithdrawal')),
                ('decision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='partnerships.payoutdecision')),
                ('partner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payout_decision_allocations', to='core.partner')),
                ('procurement', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payout_decision_allocations', to='partnerships.procurement')),
                ('tenant', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name='%(app_label)s_%(class)s_set', to='core.business')),
            ],
            options={
                'db_table': 'partnerships_payout_decision_allocation',
                'ordering': ['decision_id', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='payoutdecision',
            index=models.Index(fields=['agreement', 'decision_type', 'status'], name='pdec_agreement_type_idx'),
        ),
        migrations.AddConstraint(
            model_name='payoutdecision',
            constraint=models.UniqueConstraint(condition=models.Q(('client_request_id__isnull', False)), fields=('tenant', 'client_request_id'), name='uq_payout_decision_idempotent'),
        ),
        migrations.AddIndex(
            model_name='capitalrollover',
            index=models.Index(fields=['agreement', 'partner'], name='croll_agreement_partner_idx'),
        ),
        migrations.AddIndex(
            model_name='capitalrollover',
            index=models.Index(fields=['procurement', 'partner'], name='croll_proc_partner_idx'),
        ),
        migrations.AddConstraint(
            model_name='capitalrollover',
            constraint=models.UniqueConstraint(condition=models.Q(('client_request_id__isnull', False)), fields=('tenant', 'client_request_id'), name='uq_capital_rollover_idempotent'),
        ),
        migrations.AddIndex(
            model_name='payoutdecisionallocation',
            index=models.Index(fields=['decision', 'partner'], name='pdec_alloc_partner_idx'),
        ),
    ]
