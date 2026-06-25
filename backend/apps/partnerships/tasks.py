"""Scheduled lifecycle evaluation for E20 contracts and closed funds."""

import logging

from celery import shared_task
from django.utils import timezone

from .lifecycle_services import (
    ensure_contract_review,
    evaluate_agreement_payout_obligations,
    evaluate_fund_payout_obligations,
)
from .models import InvestmentAgreement, InvestmentFund

logger = logging.getLogger(__name__)


@shared_task
def evaluate_due_contract_lifecycle() -> dict[str, int]:
    """Create due actions/reminders only; no scheduled task moves money.

    Policies own their own cadence and are locked by the service. Iterating per
    contract preserves tenant isolation and lets a bad record fail without
    suppressing all other lifecycle checks.
    """
    now = timezone.now()
    result = {
        'agreement_obligations': 0,
        'fund_obligations': 0,
        'agreement_reviews': 0,
        'fund_reviews': 0,
        'errors': 0,
    }
    agreements = InvestmentAgreement.objects.filter(
        status__in=[InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE],
        current_terms__isnull=False,
    ).select_related('current_terms')
    for agreement in agreements.iterator():
        try:
            result['agreement_obligations'] += len(
                evaluate_agreement_payout_obligations(agreement=agreement, now=now),
            )
            result['agreement_reviews'] += int(
                ensure_contract_review(agreement=agreement, now=now) is not None,
            )
        except Exception:
            result['errors'] += 1
            logger.exception('E20 lifecycle evaluation failed for agreement %s', agreement.pk)

    funds = InvestmentFund.objects.filter(
        status__in=[InvestmentFund.Status.RAISING, InvestmentFund.Status.DEPLOYED],
        current_terms__isnull=False,
    ).select_related('current_terms')
    for fund in funds.iterator():
        try:
            result['fund_obligations'] += len(
                evaluate_fund_payout_obligations(fund=fund, now=now),
            )
            result['fund_reviews'] += int(
                ensure_contract_review(fund=fund, now=now) is not None,
            )
        except Exception:
            result['errors'] += 1
            logger.exception('E20 lifecycle evaluation failed for fund %s', fund.pk)
    return result
