"""Investor-facing confirmation and dispute actions for E20 payout obligations."""

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.permissions import IsInvestor
from apps.partnerships.lifecycle_services import confirm_payout_obligation, open_dispute
from apps.partnerships.models import PayoutObligation
from apps.partnerships.serializers import DisputeCaseSerializer, PayoutObligationSerializer

from .views import _get_request_investor_partner


class InvestorPayoutObligationView(APIView):
    permission_classes = [IsInvestor]

    def get(self, request):
        partner = _get_request_investor_partner(request)
        rows = PayoutObligation.objects.filter(
            tenant_id=request.tenant_id,
            recipient=partner,
        ).select_related('procurement', 'agreement', 'fund', 'recipient').prefetch_related('settlements')
        return Response(PayoutObligationSerializer(rows, many=True).data)

    def post(self, request, obligation_id: int, action: str):
        partner = _get_request_investor_partner(request)
        obligation = PayoutObligation.objects.filter(
            tenant_id=request.tenant_id,
            pk=obligation_id,
            recipient=partner,
        ).first()
        if obligation is None:
            raise PermissionDenied('Payout obligation is not available for this investor.')
        try:
            if action == 'confirm':
                return Response(PayoutObligationSerializer(confirm_payout_obligation(obligation=obligation)).data)
            if action == 'dispute':
                statement = str(request.data.get('statement') or '')
                dispute = open_dispute(
                    obligation=obligation,
                    raised_by_id=partner.id,
                    statement=statement,
                    evidence=str(request.data.get('evidence') or ''),
                )
                return Response(DisputeCaseSerializer(dispute).data, status=201)
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        raise ValidationError({'action': 'Unsupported payout action.'})
