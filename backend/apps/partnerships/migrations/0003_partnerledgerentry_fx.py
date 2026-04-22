from decimal import Decimal

from django.db import migrations, models


def backfill_ledger_fx(apps, schema_editor):
    PartnerLedgerEntry = apps.get_model('partnerships', 'PartnerLedgerEntry')
    BalanceContribution = apps.get_model('partnerships', 'BalanceContribution')
    BalanceWithdrawal = apps.get_model('partnerships', 'BalanceWithdrawal')
    DividendPayment = apps.get_model('partnerships', 'DividendPayment')

    source_models = {
        'contribution': BalanceContribution,
        'withdrawal': BalanceWithdrawal,
        'dividend_payment': DividendPayment,
    }

    for entry in PartnerLedgerEntry.objects.all().iterator():
        fx_rate = Decimal('1')
        source_type, _, source_id = (entry.source_ref or '').partition(':')
        model = source_models.get(source_type)
        if model is not None and source_id.isdigit():
            source = model.objects.filter(pk=int(source_id)).first()
            if source is not None:
                fx_rate = Decimal(str(getattr(source, 'fx_rate', Decimal('1'))))

        if str(entry.currency).upper() == 'UZS':
            functional_amount = Decimal(str(entry.amount))
            fx_rate = Decimal('1')
        else:
            functional_amount = Decimal(str(entry.amount)) * fx_rate

        entry.fx_rate = fx_rate
        entry.functional_amount_uzs = functional_amount.quantize(Decimal('0.01'))
        entry.save(update_fields=['fx_rate', 'functional_amount_uzs'])


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0002_alter_investmentcontract_mudaraba_ratio'),
    ]

    operations = [
        migrations.AddField(
            model_name='partnerledgerentry',
            name='fx_rate',
            field=models.DecimalField(
                decimal_places=6,
                default=Decimal('1'),
                help_text='Snapshot rate to UZS for this ledger entry.',
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name='partnerledgerentry',
            name='functional_amount_uzs',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Entry amount converted to tenant functional currency (UZS).',
                max_digits=20,
            ),
        ),
        migrations.RunPython(backfill_ledger_fx, migrations.RunPython.noop),
    ]
