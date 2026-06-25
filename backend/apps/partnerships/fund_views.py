from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .fund_services import (
    add_fund_contribution,
    create_investment_fund,
    deploy_fund_to_agreement,
)
from .lifecycle_services import (
    ensure_contract_review,
    evaluate_fund_payout_obligations,
    open_dispute,
    resolve_contract_review,
)
from .models import DisputeCase, InvestmentFund, PayoutObligation
from .serializers import (
    ContractReviewResolveSerializer,
    ContractReviewSerializer,
    DisputeCaseSerializer,
    DisputeCreateSerializer,
    DisputeResolveSerializer,
    FundContributionCreateSerializer,
    FundContributionSerializer,
    FundDeploymentCreateSerializer,
    FundDeploymentSerializer,
    InvestmentFundCreateSerializer,
    InvestmentFundSerializer,
    PayoutObligationSerializer,
    FundTermsVersionSerializer,
    TermsVersionCreateSerializer,
)


class InvestmentFundViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'head', 'options']
    ordering = ['-opened_at']

    def get_queryset(self):
        return InvestmentFund.objects.filter(tenant_id=self.request.tenant_id).select_related(
            'manager_partner', 'holder_partner', 'capital_account', 'current_terms',
        ).prefetch_related(
            'current_terms__payout_policy',
            'members__partner', 'contributions__member__partner',
            'deployments__agreement', 'member_position_rows__member__partner', 'position_row',
        )

    def get_serializer_class(self):
        return InvestmentFundCreateSerializer if self.action == 'create' else InvestmentFundSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvestmentFundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            fund = create_investment_fund(
                tenant_id=request.tenant_id,
                name=data['name'],
                manager_partner_id=data['manager_partner_id'],
                member_partner_ids=data['member_partner_ids'],
                currency=data.get('currency', 'UZS'),
                target_amount=data.get('target_amount'),
                manager_profit_share=data.get('manager_profit_share', '0'),
                review_at=data.get('review_at'),
                offline_agreed_at=data.get('offline_agreed_at'),
                offline_agreement_reference=data.get('offline_agreement_reference', ''),
                notes=data.get('notes', ''),
                payout_policy=data.get('payout_policy'),
                created_by_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(InvestmentFundSerializer(fund, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='terms')
    def terms(self, request, pk=None):
        from .lifecycle_services import create_fund_terms_version
        serializer = TermsVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fund = self.get_object()
        try:
            terms = create_fund_terms_version(
                fund=fund,
                review_at=serializer.validated_data.get('review_at'),
                manager_profit_share=serializer.validated_data.get('manager_profit_share'),
                offline_agreed_at=serializer.validated_data.get('offline_agreed_at'),
                offline_agreement_reference=serializer.validated_data.get('offline_agreement_reference', ''),
                notes=serializer.validated_data.get('notes', ''),
                created_by_id=request.user.id if request.user.is_authenticated else None,
                payout_policy=serializer.validated_data.get('payout_policy'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundTermsVersionSerializer(terms).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='contributions')
    def contributions(self, request, pk=None):
        serializer = FundContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            contribution = add_fund_contribution(
                tenant_id=request.tenant_id,
                fund_id=int(pk),
                partner_id=data['partner_id'],
                amount=data['amount'],
                currency=data.get('currency', 'UZS'),
                fx_rate=data.get('fx_rate'),
                from_cash_account_id=data.get('from_cash_account_id'),
                notes=data.get('notes', ''),
                client_request_id=data.get('client_request_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundContributionSerializer(contribution).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='deployments')
    def deployments(self, request, pk=None):
        serializer = FundDeploymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            deployment = deploy_fund_to_agreement(
                tenant_id=request.tenant_id,
                fund_id=int(pk),
                agreement_id=data['agreement_id'],
                amount=data['amount'],
                notes=data.get('notes', ''),
                client_request_id=data.get('client_request_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundDeploymentSerializer(deployment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='evaluate-payouts')
    def evaluate_payouts(self, request, pk=None):
        rows = evaluate_fund_payout_obligations(fund=self.get_object())
        return Response(PayoutObligationSerializer(rows, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='payout-obligations')
    def payout_obligations(self, request, pk=None):
        rows = PayoutObligation.objects.filter(fund=self.get_object()).select_related(
            'recipient',
        ).prefetch_related('settlements')
        return Response(PayoutObligationSerializer(rows, many=True).data)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        fund = self.get_object()
        review = ensure_contract_review(fund=fund)
        if review is None:
            return Response({'detail': 'Contract review date has not arrived.'}, status=status.HTTP_400_BAD_REQUEST)
        if request.data.get('resolution'):
            serializer = ContractReviewResolveSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            review = resolve_contract_review(
                review=review,
                resolution=serializer.validated_data['resolution'],
                resolved_by_id=request.user.id if request.user.is_authenticated else None,
                extension_until=serializer.validated_data.get('extension_until'),
                notes=serializer.validated_data.get('notes', ''),
            )
        return Response(ContractReviewSerializer(review).data)


class PayoutObligationViewSet(viewsets.GenericViewSet):
    permission_classes = [IsOwner]
    queryset = PayoutObligation.objects.all()

    def get_queryset(self):
        return PayoutObligation.objects.filter(tenant_id=self.request.tenant_id).select_related('recipient')

    @action(detail=True, methods=['post'], url_path='record')
    def record(self, request, pk=None):
        """Record an externally settled fund payout; direct payouts use their existing cash endpoints."""
        from .lifecycle_services import record_payout_obligation
        obligation = self.get_object()
        if not obligation.fund_id:
            raise ValidationError({'detail': 'Record direct agreement payouts through dividend or capital-return endpoints.'})
        try:
            row = record_payout_obligation(
                obligation=obligation,
                amount=request.data.get('amount'),
                evidence=str(request.data.get('evidence') or ''),
                notes=str(request.data.get('notes') or ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(PayoutObligationSerializer(row).data)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        from .lifecycle_services import confirm_payout_obligation
        try:
            row = confirm_payout_obligation(obligation=self.get_object())
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(PayoutObligationSerializer(row).data)

    @action(detail=True, methods=['post'], url_path='disputes')
    def disputes(self, request, pk=None):
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            dispute = open_dispute(
                obligation=self.get_object(),
                raised_by_id=serializer.validated_data['raised_by_id'],
                statement=serializer.validated_data['statement'],
                evidence=serializer.validated_data.get('evidence', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(DisputeCaseSerializer(dispute).data, status=status.HTTP_201_CREATED)


class DisputeCaseViewSet(viewsets.GenericViewSet):
    permission_classes = [IsOwner]
    queryset = DisputeCase.objects.all()

    def get_queryset(self):
        return DisputeCase.objects.filter(tenant_id=self.request.tenant_id).select_related('obligation', 'raised_by')

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        serializer = DisputeResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .lifecycle_services import resolve_dispute
        try:
            dispute = resolve_dispute(
                dispute=self.get_object(),
                accepted=serializer.validated_data['accepted'],
                resolution_notes=serializer.validated_data['resolution_notes'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(DisputeCaseSerializer(dispute).data)
