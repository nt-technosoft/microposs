from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q

from apps.core.models import Partner
from apps.core.permissions import ensure_request_tenant

from .fund_services import (
    add_fund_contribution,
    amend_fundraising_terms,
    approve_fund_application,
    create_investment_fund,
    deploy_fund_to_agreement,
    exit_fund_member,
    preview_fund_application_approvals,
    reject_fund_application,
    submit_fund_application,
)
from .lifecycle_services import (
    ensure_contract_review,
    evaluate_fund_payout_obligations,
    open_dispute,
    resolve_contract_review,
)
from .models import AgreementPartner, ContractReview, DisputeCase, FundApplication, InvestmentFund, PayoutObligation
from .serializers import (
    ContractReviewResolveSerializer,
    ContractReviewSerializer,
    DisputeCaseSerializer,
    DisputeCreateSerializer,
    DisputeResolveSerializer,
    FundApplicationCreateSerializer,
    FundApplicationDecisionSerializer,
    FundApplicationApprovalPreviewSerializer,
    FundApplicationSerializer,
    FundContributionCreateSerializer,
    FundContributionSerializer,
    FundDeploymentCreateSerializer,
    FundDeploymentSerializer,
    FundMemberExitCreateSerializer,
    FundMemberExitSerializer,
    FundTermsAmendSerializer,
    InvestmentFundCreateSerializer,
    InvestmentFundSerializer,
    PayoutObligationSerializer,
    FundTermsVersionSerializer,
)


class IsFundActor(IsAuthenticated):
    """Authenticated user with a business/investor profile in the tenant."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        ensure_request_tenant(request)
        if getattr(view, 'action', None) in {'by_invite', 'applications', 'list', 'retrieve', 'create'}:
            return True
        return request.tenant_id is not None


class InvestmentFundViewSet(viewsets.ModelViewSet):
    permission_classes = [IsFundActor]
    http_method_names = ['get', 'post', 'head', 'options']
    ordering = ['-opened_at']

    def _base_queryset(self):
        return InvestmentFund.objects.select_related(
            'manager_partner', 'holder_partner', 'capital_account', 'current_terms',
        ).prefetch_related(
            'current_terms__payout_policy',
            'members__partner', 'applications__partner', 'contributions__member__partner',
            'deployments__agreement', 'member_position_rows__member__partner', 'position_row',
            'member_exits__member__partner',
        )

    def get_queryset(self):
        queryset = self._base_queryset()
        if self.request.tenant_id is not None:
            queryset = queryset.filter(tenant_id=self.request.tenant_id)
        if not self.request.user.is_staff:
            user_partner_ids = self._user_partner_ids(self.request.tenant_id)
            queryset = queryset.filter(
                manager_partner_id__in=user_partner_ids,
            ) | queryset.filter(
                members__partner_id__in=user_partner_ids,
            ) | queryset.filter(
                applications__partner_id__in=user_partner_ids,
            ) | queryset.filter(
                visibility=InvestmentFund.Visibility.PUBLIC_LISTING,
                status=InvestmentFund.Status.RAISING,
            )
            queryset = queryset.distinct()
        return queryset

    def _user_partner_ids(self, tenant_id: int | None) -> list[int]:
        query = Partner.objects.filter(
            user_id=self.request.user.id,
            is_active=True,
        )
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        return list(query.values_list('id', flat=True))

    def _require_fund_manager(self, fund: InvestmentFund) -> None:
        if self.request.user.is_staff:
            return
        if fund.manager_partner_id not in self._user_partner_ids(fund.tenant_id):
            raise PermissionDenied('Only the fund manager can perform this action.')

    def _require_application_actor(self, fund: InvestmentFund, partner_id: int) -> None:
        if self.request.user.is_staff:
            return
        if not Partner.objects.filter(
            tenant_id=fund.tenant_id,
            pk=partner_id,
            user_id=self.request.user.id,
            is_active=True,
        ).exists():
            raise PermissionDenied('You can submit a fund application only as your own investor profile.')

    def _get_fund_for_action(self, pk) -> InvestmentFund:
        return get_object_or_404(InvestmentFund.objects.select_related(
            'manager_partner', 'holder_partner', 'capital_account', 'current_terms',
        ), pk=int(pk), tenant_id=self.request.tenant_id)

    def get_serializer_class(self):
        return InvestmentFundCreateSerializer if self.action == 'create' else InvestmentFundSerializer

    def create(self, request, *args, **kwargs):
        serializer = InvestmentFundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            manager_query = Partner.objects.filter(pk=data['manager_partner_id'], is_active=True)
            if request.tenant_id is not None:
                manager_query = manager_query.filter(tenant_id=request.tenant_id)
            manager = manager_query.first()
            if manager is None:
                raise ValueError('Fund manager was not found.')
            if manager.role != Partner.Role.INVESTOR:
                raise PermissionDenied('Fund creation is investor-led: manager must be an investor profile.')
            if manager.user_id and manager.user_id != request.user.id and not request.user.is_staff:
                raise PermissionDenied('Only the selected fund manager can create this fund.')
            if not request.user.is_staff and not manager.user_id:
                raise PermissionDenied('Investor-cabinet fund creation requires a user-linked manager profile.')
            tenant_id = request.tenant_id or manager.tenant_id
            fund = create_investment_fund(
                tenant_id=tenant_id,
                name=data['name'],
                manager_partner_id=data['manager_partner_id'],
                member_partner_ids=data['member_partner_ids'],
                currency=data.get('currency', 'UZS'),
                target_amount=data.get('target_amount'),
                min_contribution_amount=data.get('min_contribution_amount', '0'),
                visibility=data.get('visibility'),
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

    @action(detail=False, methods=['get'], url_path='by-invite/(?P<token>[^/.]+)')
    def by_invite(self, request, token=None):
        fund = InvestmentFund.objects.filter(
            invite_token=token,
        ).select_related('manager_partner', 'holder_partner', 'capital_account', 'current_terms').first()
        if fund is None:
            raise ValidationError({'detail': 'Fund invite was not found.'})
        return Response(InvestmentFundSerializer(fund, context=self.get_serializer_context()).data)

    @action(detail=False, methods=['get'], url_path='action-queue')
    def action_queue(self, request):
        funds = InvestmentFund.objects.filter(tenant_id=request.tenant_id)
        application_rows = []
        for application in FundApplication.objects.filter(
            tenant_id=request.tenant_id,
            fund__in=funds,
            status=FundApplication.Status.PENDING,
        ).select_related('fund', 'partner').order_by('created_at')[:50]:
            application_rows.append({
                'id': f'fund-application-{application.id}',
                'kind': 'FUND_APPLICATION',
                'fund_id': application.fund_id,
                'title': f'Заявка в фонд: {application.fund.name}',
                'subtitle': f'{application.partner.display_name} · {application.requested_amount} {application.currency}',
                'created_at': application.created_at,
            })
        payout_rows = []
        for obligation in PayoutObligation.objects.filter(
            tenant_id=request.tenant_id,
            status__in=[
                PayoutObligation.Status.PENDING,
                PayoutObligation.Status.RECORDED,
                PayoutObligation.Status.DISPUTED,
            ],
        ).select_related('fund', 'agreement', 'recipient').order_by('due_at')[:50]:
            owner = obligation.fund.name if obligation.fund_id else f'Договор #{obligation.agreement_id}'
            payout_rows.append({
                'id': f'payout-{obligation.id}',
                'kind': 'PAYOUT_OBLIGATION',
                'fund_id': obligation.fund_id,
                'agreement_id': obligation.agreement_id,
                'title': f'Выплата: {owner}',
                'subtitle': f'{obligation.recipient.display_name} · {obligation.amount} {obligation.currency} · {obligation.status}',
                'created_at': obligation.due_at,
            })
        review_rows = []
        for review in ContractReview.objects.filter(
            tenant_id=request.tenant_id,
            resolved_at__isnull=True,
            due_at__lte=timezone.now(),
        ).select_related('fund', 'agreement').order_by('due_at')[:50]:
            owner = review.fund.name if review.fund_id else f'Договор #{review.agreement_id}'
            review_rows.append({
                'id': f'review-{review.id}',
                'kind': 'CONTRACT_REVIEW',
                'fund_id': review.fund_id,
                'agreement_id': review.agreement_id,
                'title': f'Пересмотр: {owner}',
                'subtitle': 'Срок договора/фонда требует решения сторон',
                'created_at': review.due_at,
            })
        dispute_rows = []
        for dispute in DisputeCase.objects.filter(
            tenant_id=request.tenant_id,
            status=DisputeCase.Status.OPEN,
        ).select_related('fund', 'agreement', 'raised_by').order_by('created_at')[:50]:
            owner = dispute.fund.name if dispute.fund_id else f'Договор #{dispute.agreement_id}'
            dispute_rows.append({
                'id': f'dispute-{dispute.id}',
                'kind': 'DISPUTE',
                'fund_id': dispute.fund_id,
                'agreement_id': dispute.agreement_id,
                'title': f'Спор: {owner}',
                'subtitle': f'{dispute.raised_by.display_name} · {dispute.statement[:80]}',
                'created_at': dispute.created_at,
            })
        return Response(sorted(application_rows + payout_rows + review_rows + dispute_rows, key=lambda row: row['created_at']))

    @action(detail=True, methods=['post'], url_path='applications')
    def applications(self, request, pk=None):
        serializer = FundApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            fund = get_object_or_404(InvestmentFund.objects.all(), pk=int(pk))
            self._require_application_actor(fund, data['partner_id'])
            application = submit_fund_application(
                tenant_id=fund.tenant_id,
                fund_id=fund.pk,
                partner_id=data['partner_id'],
                requested_amount=data['requested_amount'],
                message=data.get('message', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundApplicationSerializer(application).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/approve')
    def approve_application(self, request, pk=None, application_id=None):
        serializer = FundApplicationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fund = self._get_fund_for_action(pk)
            self._require_fund_manager(fund)
            application = approve_fund_application(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
                application_id=int(application_id),
                approved_amount=serializer.validated_data.get('approved_amount'),
                decided_by_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundApplicationSerializer(application).data)

    @action(detail=True, methods=['post'], url_path='applications/approval-preview')
    def application_approval_preview(self, request, pk=None):
        serializer = FundApplicationApprovalPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fund = self._get_fund_for_action(pk)
            self._require_fund_manager(fund)
            preview = preview_fund_application_approvals(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
                approvals=serializer.validated_data['approvals'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(preview)

    @action(detail=True, methods=['post'], url_path='applications/(?P<application_id>[^/.]+)/reject')
    def reject_application(self, request, pk=None, application_id=None):
        try:
            fund = self._get_fund_for_action(pk)
            self._require_fund_manager(fund)
            application = reject_fund_application(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
                application_id=int(application_id),
                decided_by_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundApplicationSerializer(application).data)

    @action(detail=True, methods=['post'], url_path='member-exits')
    def member_exits(self, request, pk=None):
        serializer = FundMemberExitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            fund = self._get_fund_for_action(pk)
            if data['reason'] == 'MANAGER_REMOVE':
                self._require_fund_manager(fund)
            else:
                self._require_application_actor(fund, data['partner_id'])
            exit_row = exit_fund_member(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
                partner_id=data['partner_id'],
                reason=data['reason'],
                notes=data.get('notes', ''),
                client_request_id=data.get('client_request_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(FundMemberExitSerializer(exit_row).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='terms')
    def terms(self, request, pk=None):
        serializer = FundTermsAmendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fund = self._get_fund_for_action(pk)
            self._require_fund_manager(fund)
            terms = amend_fundraising_terms(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
                target_amount=serializer.validated_data.get('target_amount'),
                min_contribution_amount=serializer.validated_data.get('min_contribution_amount'),
                visibility=serializer.validated_data.get('visibility'),
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
            fund = self._get_fund_for_action(pk)
            self._require_fund_manager(fund)
            contribution = add_fund_contribution(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
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
            fund = self._get_fund_for_action(pk)
            self._require_fund_manager(fund)
            deployment = deploy_fund_to_agreement(
                tenant_id=request.tenant_id,
                fund_id=fund.pk,
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
        fund = self.get_object()
        self._require_fund_manager(fund)
        rows = evaluate_fund_payout_obligations(fund=fund)
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
        self._require_fund_manager(fund)
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
    permission_classes = [IsFundActor]
    queryset = PayoutObligation.objects.all()

    def _user_partner_ids(self, tenant_id: int | None) -> list[int]:
        if tenant_id is None:
            return []
        return list(Partner.objects.filter(
            tenant_id=tenant_id,
            user_id=self.request.user.id,
            is_active=True,
        ).values_list('id', flat=True))

    def get_queryset(self):
        queryset = PayoutObligation.objects.filter(tenant_id=self.request.tenant_id).select_related(
            'recipient', 'fund', 'agreement',
        )
        if self.request.user.is_staff:
            return queryset
        partner_ids = self._user_partner_ids(self.request.tenant_id)
        return queryset.filter(
            Q(recipient_id__in=partner_ids)
            | Q(fund__manager_partner_id__in=partner_ids)
            | Q(
                agreement__partners__partner_id__in=partner_ids,
                agreement__partners__role=AgreementPartner.Role.OPERATOR,
            )
        ).distinct()

    def _require_fund_manager(self, obligation: PayoutObligation) -> None:
        if self.request.user.is_staff:
            return
        if not obligation.fund_id or obligation.fund.manager_partner_id not in self._user_partner_ids(obligation.tenant_id):
            raise PermissionDenied('Only the fund manager can perform this action.')

    def _require_recipient(self, obligation: PayoutObligation, partner_id: int | None = None) -> None:
        if self.request.user.is_staff:
            return
        expected_partner_id = partner_id or obligation.recipient_id
        if expected_partner_id not in self._user_partner_ids(obligation.tenant_id):
            raise PermissionDenied('Only the payout recipient can perform this action.')

    @action(detail=True, methods=['post'], url_path='record')
    def record(self, request, pk=None):
        """Record an externally settled fund payout; direct payouts use their existing cash endpoints."""
        from .lifecycle_services import record_payout_obligation
        obligation = self.get_object()
        if not obligation.fund_id:
            raise ValidationError({'detail': 'Record direct agreement payouts through dividend or capital-return endpoints.'})
        self._require_fund_manager(obligation)
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
        obligation = self.get_object()
        self._require_recipient(obligation)
        try:
            row = confirm_payout_obligation(obligation=obligation)
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(PayoutObligationSerializer(row).data)

    @action(detail=True, methods=['post'], url_path='disputes')
    def disputes(self, request, pk=None):
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obligation = self.get_object()
        self._require_recipient(obligation, serializer.validated_data['raised_by_id'])
        try:
            dispute = open_dispute(
                obligation=obligation,
                raised_by_id=serializer.validated_data['raised_by_id'],
                statement=serializer.validated_data['statement'],
                evidence=serializer.validated_data.get('evidence', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(DisputeCaseSerializer(dispute).data, status=status.HTTP_201_CREATED)


class DisputeCaseViewSet(viewsets.GenericViewSet):
    permission_classes = [IsFundActor]
    queryset = DisputeCase.objects.all()

    def _user_partner_ids(self, tenant_id: int | None) -> list[int]:
        if tenant_id is None:
            return []
        return list(Partner.objects.filter(
            tenant_id=tenant_id,
            user_id=self.request.user.id,
            is_active=True,
        ).values_list('id', flat=True))

    def get_queryset(self):
        queryset = DisputeCase.objects.filter(tenant_id=self.request.tenant_id).select_related(
            'obligation', 'raised_by', 'fund', 'agreement',
        )
        if self.request.user.is_staff:
            return queryset
        partner_ids = self._user_partner_ids(self.request.tenant_id)
        return queryset.filter(
            Q(raised_by_id__in=partner_ids)
            | Q(fund__manager_partner_id__in=partner_ids)
            | Q(
                agreement__partners__partner_id__in=partner_ids,
                agreement__partners__role=AgreementPartner.Role.OPERATOR,
            )
        ).distinct()

    def _require_resolver(self, dispute: DisputeCase) -> None:
        if self.request.user.is_staff:
            return
        partner_ids = self._user_partner_ids(dispute.tenant_id)
        if dispute.fund_id and dispute.fund.manager_partner_id in partner_ids:
            return
        if dispute.agreement_id and AgreementPartner.objects.filter(
            agreement_id=dispute.agreement_id,
            partner_id__in=partner_ids,
            role=AgreementPartner.Role.OPERATOR,
        ).exists():
            return
        raise PermissionDenied('Only the fund manager or agreement operator can resolve this dispute.')

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        serializer = DisputeResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .lifecycle_services import resolve_dispute
        dispute = self.get_object()
        self._require_resolver(dispute)
        try:
            dispute = resolve_dispute(
                dispute=dispute,
                accepted=serializer.validated_data['accepted'],
                resolution_notes=serializer.validated_data['resolution_notes'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(DisputeCaseSerializer(dispute).data)
