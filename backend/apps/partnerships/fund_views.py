from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q

from apps.core.models import InvestmentProfile, Partner
from apps.core.permissions import ROLE_INVESTOR, ROLE_OWNER, ensure_request_tenant, resolve_user_role
from apps.core.services import get_or_create_investment_profile

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
    """Authenticated fund actor. Fundraising itself does not require business context."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        ensure_request_tenant(request)
        if getattr(view, 'action', None) in {
            'action_queue', 'by_invite', 'applications', 'list', 'retrieve',
            'create', 'approve_application', 'reject_application',
            'application_approval_preview', 'member_exits', 'terms',
            'contributions', 'deployments', 'evaluate_payouts',
            'payout_obligations', 'review', 'record', 'confirm',
            'disputes', 'resolve',
        }:
            return True
        return request.tenant_id is not None


class InvestmentFundViewSet(viewsets.ModelViewSet):
    permission_classes = [IsFundActor]
    http_method_names = ['get', 'post', 'head', 'options']
    ordering = ['-opened_at']

    def _base_queryset(self):
        return InvestmentFund.objects.select_related(
            'manager_profile', 'manager_partner', 'holder_partner', 'capital_account', 'current_terms',
        ).prefetch_related(
            'current_terms__payout_policy',
            'members__profile', 'members__partner',
            'applications__profile', 'applications__partner',
            'contributions__member__profile', 'contributions__member__partner',
            'deployments__agreement',
            'member_position_rows__member__profile', 'member_position_rows__member__partner',
            'position_row',
            'member_exits__member__profile', 'member_exits__member__partner',
        )

    def get_queryset(self):
        queryset = self._base_queryset()
        if not self.request.user.is_staff:
            profile = self._user_profile(create=False)
            profile_id = profile.pk if profile else None
            user_partner_ids = self._user_partner_ids(self.request.tenant_id)
            visible = Q(
                visibility=InvestmentFund.Visibility.PUBLIC_LISTING,
                status=InvestmentFund.Status.RAISING,
            )
            if profile_id:
                visible |= (
                    Q(manager_profile_id=profile_id)
                    | Q(members__profile_id=profile_id)
                    | Q(applications__profile_id=profile_id)
                )
            if user_partner_ids:
                visible |= (
                    Q(manager_partner_id__in=user_partner_ids)
                    | Q(members__partner_id__in=user_partner_ids)
                    | Q(applications__partner_id__in=user_partner_ids)
                )
            queryset = queryset.filter(visible).distinct()
        return queryset

    def _user_profile(self, *, create: bool = True) -> InvestmentProfile | None:
        try:
            if create:
                return get_or_create_investment_profile(self.request.user)
            return self.request.user.investment_profile
        except Exception:
            return None

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
        profile = self._user_profile(create=False)
        if profile and fund.manager_profile_id == profile.pk:
            return
        if fund.manager_partner_id and fund.manager_partner_id in self._user_partner_ids(fund.tenant_id):
            return
        raise PermissionDenied('Only the fund manager can perform this action.')

    def _require_member_actor(self, fund: InvestmentFund, *, profile_id: int | None = None, partner_id: int | None = None) -> None:
        if self.request.user.is_staff:
            return
        profile = self._user_profile(create=False)
        if profile_id and profile and profile_id == profile.pk:
            return
        if partner_id and partner_id in self._user_partner_ids(fund.tenant_id):
            return
        raise PermissionDenied('Only the fund member can perform this action.')

    def _user_has_fund_access(self, fund: InvestmentFund) -> bool:
        if self.request.user.is_staff:
            return True
        profile = self._user_profile(create=False)
        if profile and fund.manager_profile_id == profile.pk:
            return True
        if profile and fund.members.filter(profile_id=profile.pk).exists():
            return True
        if profile and fund.applications.filter(profile_id=profile.pk).exists():
            return True
        partner_ids = self._user_partner_ids(fund.tenant_id)
        if not partner_ids:
            return False
        return (
            (fund.manager_partner_id in partner_ids)
            or fund.members.filter(partner_id__in=partner_ids).exists()
            or fund.applications.filter(partner_id__in=partner_ids).exists()
        )

    def _has_investor_cabinet_entitlement(self) -> bool:
        if self.request.user.is_staff:
            return True
        role = resolve_user_role(self.request.user, self.request.tenant_id)
        if role == ROLE_INVESTOR:
            return True
        if role is not None:
            return False
        profile = self._user_profile(create=False)
        if profile and profile.is_active:
            return True
        return Partner.objects.filter(
            user_id=self.request.user.id,
            is_active=True,
            role=Partner.Role.INVESTOR,
        ).exists()

    def _get_fund_for_action(self, pk) -> InvestmentFund:
        return get_object_or_404(InvestmentFund.objects.select_related(
            'manager_profile', 'manager_partner', 'holder_partner', 'capital_account', 'current_terms',
        ), pk=int(pk))

    def get_serializer_class(self):
        return InvestmentFundCreateSerializer if self.action == 'create' else InvestmentFundSerializer

    def get_permissions(self):
        if self.action == 'by_invite':
            return [AllowAny()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        if not self._has_investor_cabinet_entitlement():
            raise PermissionDenied('Fund creation is available only from the investor cabinet.')
        serializer = InvestmentFundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            if data.get('review_at') is not None:
                raise ValueError('Fund review date requires deployment into a business first.')
            display_name = ''
            if data.get('manager_partner_id'):
                partner = Partner.objects.filter(
                    pk=data['manager_partner_id'],
                    user_id=request.user.id,
                    is_active=True,
                ).first()
                display_name = partner.display_name if partner else ''
            profile = get_or_create_investment_profile(request.user, display_name)
            if profile is None:
                raise PermissionDenied('Investor-cabinet fund creation requires an investment profile.')
            fund = create_investment_fund(
                tenant_id=None,
                name=data['name'],
                manager_profile_id=profile.pk,
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
        ).select_related('manager_profile', 'manager_partner', 'holder_partner', 'capital_account', 'current_terms').first()
        if fund is None:
            raise ValidationError({'detail': 'Fund invite was not found.'})
        return Response(InvestmentFundSerializer(fund, context=self.get_serializer_context()).data)

    @action(detail=False, methods=['get'], url_path='action-queue')
    def action_queue(self, request):
        profile = self._user_profile(create=False)
        partner_ids = self._user_partner_ids(request.tenant_id)
        role = resolve_user_role(request.user, request.tenant_id)
        allow_tenant_queue = request.tenant_id is not None and role == ROLE_OWNER
        managed_filter = Q(pk__in=[])
        actor_filter = Q(pk__in=[])
        if profile:
            managed_filter |= Q(manager_profile=profile)
            actor_filter |= Q(fund__manager_profile=profile) | Q(recipient_profile=profile)
        if partner_ids:
            managed_filter |= Q(manager_partner_id__in=partner_ids)
            actor_filter |= Q(fund__manager_partner_id__in=partner_ids) | Q(recipient_id__in=partner_ids)
        managed_funds = InvestmentFund.objects.filter(managed_filter)
        application_rows = []
        for application in FundApplication.objects.filter(
            fund__in=managed_funds,
            status=FundApplication.Status.PENDING,
        ).select_related('fund', 'profile', 'partner').order_by('created_at')[:50]:
            applicant = application.profile.display_name if application.profile_id else application.partner.display_name
            application_rows.append({
                'id': f'fund-application-{application.id}',
                'kind': 'FUND_APPLICATION',
                'fund_id': application.fund_id,
                'title': f'Заявка в фонд: {application.fund.name}',
                'subtitle': f'{applicant} · {application.requested_amount} {application.currency}',
                'created_at': application.created_at,
            })
        payout_rows = []
        payout_filter = Q(status__in=[
            PayoutObligation.Status.PENDING,
            PayoutObligation.Status.RECORDED,
            PayoutObligation.Status.DISPUTED,
        ])
        if allow_tenant_queue:
            payout_filter &= Q(tenant_id=request.tenant_id)
        elif profile or partner_ids:
            payout_filter &= actor_filter
        else:
            payout_filter &= Q(pk__in=[])
        for obligation in PayoutObligation.objects.filter(
            payout_filter,
        ).select_related('fund', 'agreement', 'recipient', 'recipient_profile').order_by('due_at')[:50]:
            owner = obligation.fund.name if obligation.fund_id else f'Договор #{obligation.agreement_id}'
            recipient_name = (
                obligation.recipient.display_name
                if obligation.recipient_id
                else obligation.recipient_profile.display_name
            )
            payout_rows.append({
                'id': f'payout-{obligation.id}',
                'kind': 'PAYOUT_OBLIGATION',
                'fund_id': obligation.fund_id,
                'agreement_id': obligation.agreement_id,
                'title': f'Выплата: {owner}',
                'subtitle': f'{recipient_name} · {obligation.amount} {obligation.currency} · {obligation.status}',
                'created_at': obligation.due_at,
            })
        review_rows = []
        review_filter = Q(
            resolved_at__isnull=True,
            due_at__lte=timezone.now(),
        )
        if allow_tenant_queue:
            review_filter &= Q(tenant_id=request.tenant_id)
        elif profile or partner_ids:
            review_actor_filter = Q(pk__in=[])
            if profile:
                review_actor_filter |= Q(fund__manager_profile=profile)
            if partner_ids:
                review_actor_filter |= Q(fund__manager_partner_id__in=partner_ids)
            review_filter &= review_actor_filter
        else:
            review_filter &= Q(pk__in=[])
        for review in ContractReview.objects.filter(
            review_filter,
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
        dispute_filter = Q(
            status=DisputeCase.Status.OPEN,
        )
        if allow_tenant_queue:
            dispute_filter &= Q(tenant_id=request.tenant_id)
        elif profile or partner_ids:
            dispute_actor_filter = Q(pk__in=[])
            if profile:
                dispute_actor_filter |= Q(fund__manager_profile=profile) | Q(raised_by_profile=profile)
            if partner_ids:
                dispute_actor_filter |= Q(fund__manager_partner_id__in=partner_ids) | Q(raised_by_id__in=partner_ids)
            dispute_filter &= dispute_actor_filter
        else:
            dispute_filter &= Q(pk__in=[])
        for dispute in DisputeCase.objects.filter(
            dispute_filter,
        ).select_related('fund', 'agreement', 'raised_by', 'raised_by_profile').order_by('created_at')[:50]:
            owner = dispute.fund.name if dispute.fund_id else f'Договор #{dispute.agreement_id}'
            raised_by_name = dispute.raised_by.display_name if dispute.raised_by_id else dispute.raised_by_profile.display_name
            dispute_rows.append({
                'id': f'dispute-{dispute.id}',
                'kind': 'DISPUTE',
                'fund_id': dispute.fund_id,
                'agreement_id': dispute.agreement_id,
                'title': f'Спор: {owner}',
                'subtitle': f'{raised_by_name} · {dispute.statement[:80]}',
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
            if data.get('partner_id') and data['partner_id'] not in self._user_partner_ids(fund.tenant_id):
                raise PermissionDenied('You can submit a fund application only as your own investor profile.')
            invite_token = str(data.get('invite_token') or '')
            has_invite_access = bool(invite_token and invite_token == fund.invite_token)
            if (
                fund.visibility != InvestmentFund.Visibility.PUBLIC_LISTING
                and not has_invite_access
                and not self._user_has_fund_access(fund)
            ):
                raise PermissionDenied('Fund invite access is required to submit an application.')
            profile = self._user_profile(create=True)
            if profile is None:
                raise PermissionDenied('Investment profile is required to apply to a fund.')
            application = submit_fund_application(
                tenant_id=None,
                fund_id=fund.pk,
                profile_id=profile.pk,
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
                profile = self._user_profile(create=False)
                self._require_member_actor(
                    fund,
                    profile_id=data.get('profile_id') or (profile.pk if profile else None),
                    partner_id=data.get('partner_id'),
                )
            exit_row = exit_fund_member(
                tenant_id=fund.tenant_id,
                fund_id=fund.pk,
                profile_id=data.get('profile_id'),
                partner_id=data.get('partner_id'),
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
            if serializer.validated_data.get('review_at') is not None and fund.tenant_id is None:
                raise ValueError('Fund review date requires deployment into a business first.')
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
                tenant_id=fund.tenant_id,
                fund_id=fund.pk,
                profile_id=data.get('profile_id'),
                partner_id=data.get('partner_id'),
                amount=data['amount'],
                currency=data.get('currency', 'UZS'),
                fx_rate=data.get('fx_rate'),
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
                created_by_id=request.user.id if request.user.is_authenticated else None,
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
            'recipient', 'recipient_profile',
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

    def _user_profile(self) -> InvestmentProfile | None:
        try:
            return self.request.user.investment_profile
        except Exception:
            return None

    def get_queryset(self):
        queryset = PayoutObligation.objects.select_related(
            'recipient', 'recipient_profile', 'fund', 'agreement',
        )
        if self.request.user.is_staff:
            return queryset
        profile = self._user_profile()
        partner_ids = self._user_partner_ids(self.request.tenant_id)
        visible = Q(pk__isnull=True)
        if profile:
            visible |= Q(recipient_profile=profile) | Q(fund__manager_profile=profile)
        if partner_ids:
            visible |= (
                Q(recipient_id__in=partner_ids)
                | Q(fund__manager_partner_id__in=partner_ids)
                | Q(
                    agreement__partners__partner_id__in=partner_ids,
                    agreement__partners__role=AgreementPartner.Role.OPERATOR,
                )
            )
        return queryset.filter(visible).distinct()

    def _require_fund_manager(self, obligation: PayoutObligation) -> None:
        if self.request.user.is_staff:
            return
        profile = self._user_profile()
        if obligation.fund_id and profile and obligation.fund.manager_profile_id == profile.pk:
            return
        if obligation.fund_id and obligation.fund.manager_partner_id in self._user_partner_ids(obligation.tenant_id):
            return
        raise PermissionDenied('Only the fund manager can perform this action.')

    def _require_recipient(
        self,
        obligation: PayoutObligation,
        partner_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        if self.request.user.is_staff:
            return
        profile = self._user_profile()
        expected_profile_id = profile_id or obligation.recipient_profile_id
        if expected_profile_id and profile and expected_profile_id == profile.pk:
            return
        expected_partner_id = partner_id or obligation.recipient_id
        if expected_partner_id and expected_partner_id in self._user_partner_ids(obligation.tenant_id):
            return
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
        profile_id = serializer.validated_data.get('raised_by_profile_id')
        if profile_id is None and obligation.recipient_profile_id:
            profile_id = obligation.recipient_profile_id
        self._require_recipient(
            obligation,
            serializer.validated_data.get('raised_by_id'),
            profile_id,
        )
        try:
            dispute = open_dispute(
                obligation=obligation,
                raised_by_id=serializer.validated_data.get('raised_by_id'),
                raised_by_profile_id=profile_id,
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

    def _user_profile(self) -> InvestmentProfile | None:
        try:
            return self.request.user.investment_profile
        except Exception:
            return None

    def get_queryset(self):
        queryset = DisputeCase.objects.select_related(
            'obligation', 'raised_by', 'raised_by_profile', 'fund', 'agreement',
        )
        if self.request.user.is_staff:
            return queryset
        profile = self._user_profile()
        partner_ids = self._user_partner_ids(self.request.tenant_id)
        visible = Q(pk__isnull=True)
        if profile:
            visible |= Q(raised_by_profile=profile) | Q(fund__manager_profile=profile)
        if partner_ids:
            visible |= (
                Q(raised_by_id__in=partner_ids)
                | Q(fund__manager_partner_id__in=partner_ids)
                | Q(
                    agreement__partners__partner_id__in=partner_ids,
                    agreement__partners__role=AgreementPartner.Role.OPERATOR,
                )
            )
        return queryset.filter(visible).distinct()

    def _require_resolver(self, dispute: DisputeCase) -> None:
        if self.request.user.is_staff:
            return
        profile = self._user_profile()
        if dispute.fund_id and profile and dispute.fund.manager_profile_id == profile.pk:
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
