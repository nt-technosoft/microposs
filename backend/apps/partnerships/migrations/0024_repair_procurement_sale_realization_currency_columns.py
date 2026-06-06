# Generated manually after E17 cutover to repair environments that applied an
# older draft of 0022 before per-currency realization fields were finalized.

from django.db import migrations


FORWARD_SQL = """
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS sale_proceeds_currency varchar(3) NOT NULL DEFAULT 'UZS';
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS sale_proceeds_amount numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS sale_fx_rate numeric(14,6) NOT NULL DEFAULT 1;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS cost_basis_currency varchar(3) NOT NULL DEFAULT 'UZS';
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS cost_basis_amount numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS cost_fx_rate numeric(14,6) NOT NULL DEFAULT 1;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS cost_basis_at_sale_uzs numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS capital_recovered_currency varchar(3) NOT NULL DEFAULT 'UZS';
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS capital_recovered_amount numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS profit_currency varchar(3) NOT NULL DEFAULT 'UZS';
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS profit_amount numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS loss_currency varchar(3) NOT NULL DEFAULT 'UZS';
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS loss_amount numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS fx_gain_loss_uzs numeric(20,2) NOT NULL DEFAULT 0;
ALTER TABLE partnerships_procurement_sale_realization ADD COLUMN IF NOT EXISTS is_partner_liability boolean NOT NULL DEFAULT false;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('partnerships', '0023_agreementwithdrawal_paid_from_account_and_more'),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
