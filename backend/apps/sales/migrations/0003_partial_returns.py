from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_multicurrency_sales'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sale',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Черновик'),
                    ('completed', 'Завершена'),
                    ('partially_returned', 'Частично возвращена'),
                    ('returned', 'Возвращена'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
    ]
