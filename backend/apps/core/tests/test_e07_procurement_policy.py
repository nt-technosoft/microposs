from django.test import SimpleTestCase

from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.policies import (
    ProcurementPolicyContext,
    evaluate_procurement_policy,
    validate_procurement_policy,
)


class ProcurementPolicyTests(SimpleTestCase):
    def test_own_funds_allows_all_supplier_settlement_modes(self):
        result = evaluate_procurement_policy(
            ProcurementPolicyContext(
                funding_source=Procurement.FundingSource.OWN_FUNDS,
                settlement_type=ProcurementTerms.Type.DEFERRED,
                has_supplier=True,
            ),
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(result.normalized_funding_source, Procurement.FundingSource.OWN_FUNDS)
        self.assertEqual(
            result.allowed_settlements,
            (
                ProcurementTerms.Type.PREPAID,
                ProcurementTerms.Type.PARTIAL,
                ProcurementTerms.Type.DEFERRED,
                ProcurementTerms.Type.INSTALLMENT,
                ProcurementTerms.Type.CONSIGNMENT,
            ),
        )
        self.assertNotIn('capital', result.visible_sections)

    def test_own_funds_rejects_procurement_balance(self):
        result = evaluate_procurement_policy(
            ProcurementPolicyContext(
                funding_source=Procurement.FundingSource.OWN_FUNDS,
                settlement_type=ProcurementTerms.Type.PREPAID,
                has_procurement_balance=True,
            ),
        )

        self.assertFalse(result.is_valid)
        self.assertIn('OWN_FUNDS must not use ProcurementBalance.', result.blocked_reasons)

    def test_supplier_credit_requires_supplier(self):
        with self.assertRaisesMessage(ValueError, 'DEFERRED settlement requires supplier.'):
            validate_procurement_policy(
                ProcurementPolicyContext(
                    funding_source=Procurement.FundingSource.OWN_FUNDS,
                    settlement_type=ProcurementTerms.Type.DEFERRED,
                    has_supplier=False,
                ),
            )

    def test_partnership_allows_only_prepaid_in_mvp(self):
        result = evaluate_procurement_policy(
            ProcurementPolicyContext(
                funding_source=Procurement.FundingSource.PARTNERSHIP,
                settlement_type=ProcurementTerms.Type.PREPAID,
                has_investment_agreement=True,
                has_procurement_balance=True,
            ),
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(result.allowed_settlements, (ProcurementTerms.Type.PREPAID,))
        self.assertIn('capital', result.visible_sections)
        self.assertIn('pay_from_capital_pool', result.allowed_actions)

    def test_partnership_rejects_supplier_credit_hybrid(self):
        with self.assertRaisesMessage(
            ValueError,
            'PARTNERSHIP does not allow DEFERRED settlement in MVP.',
        ):
            validate_procurement_policy(
                ProcurementPolicyContext(
                    funding_source=Procurement.FundingSource.PARTNERSHIP,
                    settlement_type=ProcurementTerms.Type.DEFERRED,
                    has_supplier=True,
                    has_investment_agreement=True,
                    has_procurement_balance=True,
                ),
            )

    def test_partnership_requires_investment_agreement(self):
        result = evaluate_procurement_policy(
            ProcurementPolicyContext(
                funding_source=Procurement.FundingSource.PARTNERSHIP,
                settlement_type=ProcurementTerms.Type.PREPAID,
                has_investment_agreement=False,
                has_procurement_balance=True,
            ),
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            'PARTNERSHIP requires an InvestmentAgreement.',
            result.blocked_reasons,
        )
        self.assertFalse(result.readiness['source_ready'])

    def test_partnership_requires_capital_pool(self):
        result = evaluate_procurement_policy(
            ProcurementPolicyContext(
                funding_source=Procurement.FundingSource.PARTNERSHIP,
                settlement_type=ProcurementTerms.Type.PREPAID,
                has_investment_agreement=True,
                has_procurement_balance=False,
            ),
        )

        self.assertFalse(result.is_valid)
        self.assertIn(
            'PARTNERSHIP requires ProcurementBalance capital pool.',
            result.blocked_reasons,
        )
        self.assertFalse(result.readiness['capital_ready'])

    def test_musharaka_is_legacy_alias_but_not_valid_new_flow(self):
        result = evaluate_procurement_policy(
            ProcurementPolicyContext(
                funding_source='MUSHARAKA',
                settlement_type=ProcurementTerms.Type.PREPAID,
                has_investment_agreement=True,
                has_procurement_balance=True,
            ),
        )

        self.assertEqual(result.normalized_funding_source, Procurement.FundingSource.PARTNERSHIP)
        self.assertFalse(result.is_valid)
        self.assertIn(
            'MUSHARAKA is legacy-only; use PARTNERSHIP in new flows.',
            result.blocked_reasons,
        )
