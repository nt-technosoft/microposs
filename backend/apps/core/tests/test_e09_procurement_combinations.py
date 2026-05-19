from django.test import SimpleTestCase

from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.policies import (
    LEGAL_COMBINATIONS,
    validate_procurement_combination,
)

OWN_FUNDS = Procurement.FundingSource.OWN_FUNDS
PARTNERSHIP = Procurement.FundingSource.PARTNERSHIP
OWNED = Procurement.GoodsOwnership.OWNED
CONSIGNED = Procurement.GoodsOwnership.CONSIGNED
PREPAID = ProcurementTerms.Type.PREPAID
PARTIAL = ProcurementTerms.Type.PARTIAL
DEFERRED = ProcurementTerms.Type.DEFERRED
INSTALLMENT = ProcurementTerms.Type.INSTALLMENT
ON_SALE = ProcurementTerms.Type.ON_SALE


class ProcurementCombinationTests(SimpleTestCase):
    def test_legal_combinations_accepted(self):
        for funding, timing, ownership in LEGAL_COMBINATIONS:
            with self.subTest(funding=funding, timing=timing, ownership=ownership):
                validate_procurement_combination(funding, timing, ownership)

    def test_partnership_with_non_prepaid_rejected(self):
        with self.assertRaises(ValueError):
            validate_procurement_combination(PARTNERSHIP, DEFERRED, OWNED)

    def test_partnership_with_consigned_rejected(self):
        with self.assertRaises(ValueError):
            validate_procurement_combination(PARTNERSHIP, ON_SALE, CONSIGNED)

    def test_own_funds_consigned_with_prepaid_rejected(self):
        with self.assertRaises(ValueError):
            validate_procurement_combination(OWN_FUNDS, PREPAID, CONSIGNED)

    def test_own_funds_on_sale_with_owned_rejected(self):
        with self.assertRaises(ValueError):
            validate_procurement_combination(OWN_FUNDS, ON_SALE, OWNED)
