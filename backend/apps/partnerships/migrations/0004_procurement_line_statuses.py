from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0003_partnerledgerentry_fx'),
    ]

    operations = [
        migrations.AddField(
            model_name='procurementexpense',
            name='status',
            field=models.CharField(
                choices=[('DRAFT', 'Черновик'), ('PAID', 'Оплачено')],
                default='DRAFT',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='procurementitem',
            name='status',
            field=models.CharField(
                choices=[('DRAFT', 'Черновик'), ('PAID', 'Оплачено')],
                default='DRAFT',
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name='procurementexpense',
            index=models.Index(fields=['procurement', 'status'], name='partnership_procure_ab1e4e_idx'),
        ),
        migrations.AddIndex(
            model_name='procurementitem',
            index=models.Index(fields=['procurement', 'status'], name='partnership_procure_cda147_idx'),
        ),
    ]
