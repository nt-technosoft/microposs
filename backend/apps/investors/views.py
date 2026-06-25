"""
Investors API views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Partner
from apps.core.permissions import IsOwner, IsInvestor
from apps.partnerships.models import PayoutObligation, ProcurementPartnerLedger
from apps.partnerships.serializers import PayoutObligationSerializer, DisputeCaseSerializer
from apps.partnerships.lifecycle_services import confirm_payout_obligation, open_dispute
from apps.partnerships.agreement_services import get_partner_aggregate

from .models import Investor, InvestorContract
from .serializers import (
    InvestorSerializer, InvestorCreateSerializer,
    InvestorContractSerializer, InvestorContractCreateSerializer,
    InvestorDashboardAggregateSerializer, InvestorLedgerSerializer,
    InvestorProcurementListSerializer, InvestorProcurementDetailSerializer,
)
from .services import close_investor_contract, update_investor_summary
from .services import get_partner_capital_state


def _get_request_investor_partner(request):
    if request.tenant_id is None:
        raise PermissionDenied('Investor account is not linked to a business yet.')

    try:
        return Partner.objects.get(
            tenant_id=request.tenant_id,
            user_id=request.user.id,
            role=Partner.Role.INVESTOR,
        )
    except Partner.DoesNotExist as exc:
        raise PermissionDenied('Investor account is not linked to this business.') from exc


def _serialize_investor_ledger(ledger):
    return {
        'partner_id': ledger.partner_id,
        'partner_name': ledger.partner.display_name,
        'entries': [
            {
                'id': entry.id,
                'date': entry.date,
                'amount': entry.amount,
                'currency': entry.currency,
                'fx_rate': entry.fx_rate,
                'functional_amount_uzs': entry.functional_amount_uzs,
                'entry_type': entry.entry_type,
                'source_ref': entry.source_ref,
            }
            for entry in ledger.entries.order_by('date', 'id')
        ],
    }


class InvestorDashboardView(APIView):
    permission_classes = [IsInvestor]

    def get(self, request):
        partner = _get_request_investor_partner(request)
        data = {
            'partner_id': partner.id,
            **get_partner_aggregate(partner.id, request.tenant_id),
            'capital_state': get_partner_capital_state(
                tenant_id=request.tenant_id,
                partner_id=partner.id,
            ),
        }
        serializer = InvestorDashboardAggregateSerializer(data)
        return Response(serializer.data)


class InvestorProcurementView(APIView):
    permission_classes = [IsInvestor]

    def get(self, request, procurement_id=None):
        partner = _get_request_investor_partner(request)
        ledgers = ProcurementPartnerLedger.objects.filter(
            tenant_id=request.tenant_id,
            partner=partner,
        ).select_related('procurement__supplier', 'partner')

        if procurement_id is None:
            payload = [
                {
                    'id': ledger.procurement_id,
                    'procurement_type': ledger.procurement.funding_source,
                    'status': ledger.procurement.status,
                    'opened_at': ledger.procurement.opened_at,
                    'received_at': ledger.procurement.received_at,
                    'supplier_name': getattr(ledger.procurement.supplier, 'name', None),
                }
                for ledger in ledgers.order_by('-procurement__opened_at')
            ]
            return Response(InvestorProcurementListSerializer(payload, many=True).data)

        ledger = ledgers.prefetch_related('entries').get(procurement_id=procurement_id)
        payload = {
            'id': ledger.procurement_id,
            'procurement_type': ledger.procurement.funding_source,
            'status': ledger.procurement.status,
            'opened_at': ledger.procurement.opened_at,
            'received_at': ledger.procurement.received_at,
            'supplier_name': getattr(ledger.procurement.supplier, 'name', None),
            'notes': ledger.procurement.notes,
            'investor_aggregate': {
                'partner_id': partner.id,
                **get_partner_aggregate(
                    partner.id,
                    request.tenant_id,
                    procurement_id=procurement_id,
                ),
                'capital_state': get_partner_capital_state(
                    tenant_id=request.tenant_id,
                    partner_id=partner.id,
                    procurement_id=procurement_id,
                ),
            },
            'capital_state': get_partner_capital_state(
                tenant_id=request.tenant_id,
                partner_id=partner.id,
                procurement_id=procurement_id,
            ),
            'investor_ledger': _serialize_investor_ledger(ledger),
        }
        return Response(InvestorProcurementDetailSerializer(payload).data)


class InvestorAgreementView(APIView):
    permission_classes = [IsInvestor]

    def get(self, request, agreement_id=None):
        from rest_framework.exceptions import ValidationError
        from apps.finance.report_currency import ReportCurrencyError
        from apps.finance.services import get_agreement_profitability_detail
        from apps.partnerships.models import InvestmentAgreement

        partner = _get_request_investor_partner(request)
        agreements = (
            InvestmentAgreement.objects
            .filter(tenant_id=request.tenant_id, partners__partner=partner)
            .select_related('supplier')
            .prefetch_related('procurements', 'partners__partner')
            .distinct()
        )

        if agreement_id is None:
            payload = [
                {
                    'id': agreement.id,
                    'status': agreement.status,
                    'opened_at': agreement.opened_at,
                    'closed_at': agreement.closed_at,
                    'supplier_name': getattr(agreement.supplier, 'name', None),
                    'planned_budget': agreement.planned_budget,
                    'currency': agreement.currency,
                    'balances': agreement.balances or {},
                    'procurements_count': agreement.procurements.count(),
                }
                for agreement in agreements.order_by('-opened_at')
            ]
            return Response(payload)

        agreement = agreements.filter(pk=agreement_id).first()
        if agreement is None:
            raise PermissionDenied('Agreement is not available for this investor.')
        try:
            payload = get_agreement_profitability_detail(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                report_currency=request.query_params.get('report_currency'),
            )
        except ReportCurrencyError as exc:
            raise ValidationError({'report_currency': str(exc)})
        payload['current_partner_id'] = partner.id
        return Response(payload)


class InvestorViewSet(viewsets.ModelViewSet):
    serializer_class = InvestorSerializer
    permission_classes = [IsOwner]
    search_fields = ['name', 'phone']
    ordering = ['name']

    def get_queryset(self):
        return Investor.objects.filter(
            tenant_id=self.request.tenant_id,
        ).prefetch_related('contracts')

    def get_serializer_class(self):
        if self.action == 'create':
            return InvestorCreateSerializer
        return InvestorSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvestorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        investor = Investor.objects.create(
            tenant_id=request.tenant_id,
            user_id=data['user_id'],
            name=data['name'],
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            notes=data.get('notes', ''),
        )
        return Response(InvestorSerializer(investor).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.soft_delete()


class InvestorContractViewSet(viewsets.ModelViewSet):
    serializer_class = InvestorContractSerializer
    permission_classes = [IsOwner]
    ordering = ['-start_date']

    def get_queryset(self):
        qs = InvestorContract.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('investor')

        investor_id = self.request.query_params.get('investor')
        if investor_id:
            qs = qs.filter(investor_id=investor_id)

        contract_status = self.request.query_params.get('status')
        if contract_status:
            qs = qs.filter(status=contract_status)

        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return InvestorContractCreateSerializer
        return InvestorContractSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvestorContractCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        contract = InvestorContract.objects.create(
            tenant_id=request.tenant_id,
            investor_id=data['investor_id'],
            contract_type=data['contract_type'],
            default_profit_ratio=data['default_profit_ratio'],
            start_date=data['start_date'],
            notes=data.get('notes', ''),
            status='active',
        )
        return Response(InvestorContractSerializer(contract).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        contract = self.get_object()
        contract = close_investor_contract(
            tenant_id=request.tenant_id,
            contract_id=contract.pk,
        )
        return Response(InvestorContractSerializer(contract).data)

    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        """
        Computed investor summary for this contract.
        Backed by PartnerLedgerEntry — replaces deprecated InvestorSummary model.
        """
        contract = self.get_object()
        data = update_investor_summary(
            tenant_id=request.tenant_id,
            contract_id=contract.pk,
        )
        return Response(data)
