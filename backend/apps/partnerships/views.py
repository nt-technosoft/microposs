from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsWarehouse

from .models import DividendPayment, InvestmentAgreement, Procurement
from .serializers import (
    AgreementAllocationCreateSerializer,
    AgreementAllocationSerializer,
    AgreementContributionSerializer,
    AgreementWithdrawalSerializer,
    BalanceContributionCreateSerializer,
    BalanceWithdrawalCreateSerializer,
    DividendPaymentCreateSerializer,
    DividendPaymentSerializer,
    InvestmentAgreementCreateSerializer,
    InvestmentAgreementDetailSerializer,
    InvestmentAgreementListSerializer,
    ProcurementCreateSerializer,
    ProcurementExpenseTargetsSerializer,
    PayProcurementExpensesSerializer,
    PayProcurementItemsSerializer,
    ReceiveProcurementSerializer,
    TermsAmendmentSerializer,
    ProcurementTermsAmendmentSerializer,
)
from .services import (
    pay_dividend,
)
from .workspace_support import (
    add_agreement_contribution,
    add_agreement_withdrawal,
    create_investment_agreement,
)
from .workspace import (
    allocate_workspace_capital,
    build_workspace_payload,
    build_workspace_capital_allocation_preview,
    create_workspace,
    dispatch_workspace_action,
    workspace_queryset,
)


class InvestmentAgreementViewSet(viewsets.ModelViewSet):
    permission_classes = [IsOwner]
    ordering = ['-opened_at']

    def get_queryset(self):
        return (
            InvestmentAgreement.objects
            .filter(tenant_id=self.request.tenant_id)
            .select_related('supplier')
            .prefetch_related(
                'partners__partner',
                'commitments__partner',
                'commitments__created_by',
                'commitments__actor_partner',
                'contributions__partner',
                'contributions__created_by',
                'contributions__actor_partner',
                'withdrawals__partner',
                'withdrawals__created_by',
                'withdrawals__actor_partner',
                'allocations__partner',
                'allocations__created_by',
                'allocations__actor_partner',
                'allocations__procurement',
                'events__actor_user',
                'events__actor_partner',
                'procurements__supplier',
                'procurements__items',
                'procurements__expenses',
            )
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return InvestmentAgreementCreateSerializer
        if self.action == 'retrieve':
            return InvestmentAgreementDetailSerializer
        return InvestmentAgreementListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            agreement = create_investment_agreement(
                tenant_id=request.tenant_id,
                supplier_id=data.get('supplier_id'),
                mudaraba_ratio=data['mudaraba_ratio'],
                planned_budget=data['planned_budget'],
                currency=data.get('currency', 'UZS'),
                notes=data.get('notes', ''),
                client_request_id=str(data['client_request_id']) if data.get('client_request_id') else None,
                created_by_id=request.user.id if request.user.is_authenticated else None,
                partners=[dict(partner) for partner in data.get('partners', [])],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(InvestmentAgreementDetailSerializer(agreement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='contributions')
    def contributions(self, request, pk=None):
        agreement = self.get_object()
        serializer = BalanceContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contribution = add_agreement_contribution(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                partner_id=serializer.validated_data['partner_id'],
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data['fx_rate'],
                notes=serializer.validated_data.get('notes', ''),
                created_by_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(AgreementContributionSerializer(contribution).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='withdrawals')
    def withdrawals(self, request, pk=None):
        agreement = self.get_object()
        serializer = BalanceWithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdrawal = add_agreement_withdrawal(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                partner_id=serializer.validated_data['partner_id'],
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data['fx_rate'],
                reason=serializer.validated_data.get('reason', ''),
                created_by_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(AgreementWithdrawalSerializer(withdrawal).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='allocation-preview')
    def allocation_preview(self, request, pk=None):
        agreement = self.get_object()
        procurement_id = request.query_params.get('procurement_id')
        if not procurement_id:
            raise ValidationError({'procurement_id': 'This query parameter is required.'})
        try:
            payload = build_workspace_capital_allocation_preview(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                procurement_id=int(procurement_id),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(payload)

    @action(detail=True, methods=['post'], url_path='allocations')
    def allocations(self, request, pk=None):
        agreement = self.get_object()
        serializer = AgreementAllocationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = Procurement.objects.filter(
                tenant_id=request.tenant_id,
                pk=serializer.validated_data['procurement_id'],
                agreement=agreement,
            ).first()
            if procurement is None:
                raise ValueError('Procurement is not linked to this agreement.')
            allocations = allocate_workspace_capital(
                tenant_id=request.tenant_id,
                procurement=procurement,
                payload={'allocations': [dict(row) for row in serializer.validated_data['allocations']]},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(AgreementAllocationSerializer(allocations, many=True).data, status=status.HTTP_201_CREATED)


class ProcurementViewSet(viewsets.ModelViewSet):
    ordering = ['-opened_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'ledger', 'receive', 'receive_plan'):
            return [IsWarehouse()]
        return [IsOwner()]

    def get_queryset(self):
        queryset = workspace_queryset(self.request.tenant_id)
        status_value = self.request.query_params.get('status')
        if status_value:
            queryset = queryset.filter(status=status_value)
        funding_source = self.request.query_params.get('funding_source')
        if funding_source:
            queryset = queryset.filter(funding_source=funding_source)

        return queryset

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ProcurementCreateSerializer
        return ProcurementCreateSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        rows = [build_workspace_payload(procurement) for procurement in queryset[:50]]
        return Response(rows)

    def retrieve(self, request, *args, **kwargs):
        return Response(build_workspace_payload(self.get_object()))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            procurement = create_workspace(
                tenant_id=request.tenant_id,
                funding_source=data['funding_source'],
                supplier_id=data.get('supplier_id'),
                notes=data.get('notes', ''),
                client_request_id=str(data['client_request_id']) if data.get('client_request_id') else None,
                agreement_id=data.get('agreement_id'),
            )
            procurement = self._apply_workspace_payload(procurement, data)
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        procurement = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            procurement = self._apply_workspace_payload(procurement, data, update_source=True)
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement))

    def _apply_workspace_payload(self, procurement, data, *, update_source=False):
        if data.get('contract'):
            procurement = dispatch_workspace_action(
                tenant_id=self.request.tenant_id,
                procurement=procurement,
                action='CREATE_INVESTMENT_AGREEMENT',
                payload={'payload': dict(data['contract'])},
                user_id=self.request.user.id if self.request.user.is_authenticated else None,
            )
        elif data.get('agreement_id') and procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
            procurement = dispatch_workspace_action(
                tenant_id=self.request.tenant_id,
                procurement=procurement,
                action='LINK_INVESTMENT_AGREEMENT',
                payload={'payload': {'agreement_id': data['agreement_id']}},
                user_id=self.request.user.id if self.request.user.is_authenticated else None,
            )

        if update_source:
            procurement = dispatch_workspace_action(
                tenant_id=self.request.tenant_id,
                procurement=procurement,
                action='UPDATE_SOURCE',
                payload={'payload': {
                    'funding_source': data['funding_source'],
                    'supplier_id': data.get('supplier_id'),
                    'agreement_id': data.get('agreement_id') or procurement.agreement_id,
                    'notes': data.get('notes', ''),
                }},
                user_id=self.request.user.id if self.request.user.is_authenticated else None,
            )

        if data.get('items') or data.get('expenses'):
            procurement = dispatch_workspace_action(
                tenant_id=self.request.tenant_id,
                procurement=procurement,
                action='UPDATE_ITEMS',
                payload={'payload': {
                    'items': [dict(item) for item in data.get('items', [])],
                    'expenses': [dict(expense) for expense in data.get('expenses', [])],
                }},
                user_id=self.request.user.id if self.request.user.is_authenticated else None,
            )

        if data.get('terms'):
            terms_payload = dict(data['terms'])
            terms_payload['schedule'] = [dict(row) for row in data.get('schedule', [])]
            procurement = dispatch_workspace_action(
                tenant_id=self.request.tenant_id,
                procurement=procurement,
                action='UPDATE_SETTLEMENT',
                payload={'payload': terms_payload},
                user_id=self.request.user.id if self.request.user.is_authenticated else None,
            )

        return procurement

    @action(detail=True, methods=['post'], url_path='contributions')
    def contributions(self, request, pk=None):
        procurement = self.get_object()
        serializer = BalanceContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
                procurement=procurement,
                action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': dict(serializer.validated_data)},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='withdrawals')
    def withdrawals(self, request, pk=None):
        raise ValidationError({
            'detail': 'Balance withdrawals are not part of the E07 procurement workspace contract yet.'
        })

    @action(detail=True, methods=['post'], url_path='balance-exchanges')
    def balance_exchanges(self, request, pk=None):
        raise ValidationError({
            'detail': 'Balance exchange is not part of the E07 procurement workspace contract yet.'
        })

    @action(detail=True, methods=['post'], url_path='pay-items')
    def pay_items(self, request, pk=None):
        procurement = self.get_object()
        serializer = PayProcurementItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
                procurement=procurement,
                action='PAY_COSTS',
                payload={'payload': {
                    'item_ids': serializer.validated_data.get('item_ids'),
                    'cash_account_id': serializer.validated_data.get('cash_account_id'),
                    'notes': serializer.validated_data.get('reason', ''),
                }},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='pay-expenses')
    def pay_expenses(self, request, pk=None):
        procurement = self.get_object()
        serializer = PayProcurementExpensesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
                procurement=procurement,
                action='PAY_COSTS',
                payload={'payload': {
                    'expense_ids': serializer.validated_data.get('expense_ids'),
                    'cash_account_id': serializer.validated_data.get('cash_account_id'),
                    'notes': serializer.validated_data.get('reason', ''),
                }},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='expense-targets')
    def expense_targets(self, request, pk=None):
        procurement = self.get_object()
        serializer = ProcurementExpenseTargetsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
                procurement=procurement,
                action='UPDATE_EXPENSES',
                payload={'payload': {
                    'expenses': [{
                        'expense_id': serializer.validated_data['expense_id'],
                        'target_item_ids': serializer.validated_data.get('target_item_ids', []),
                    }],
                }},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='split-item')
    def split_item(self, request, pk=None):
        raise ValidationError({
            'detail': 'Item split must be implemented as an E07 workspace correction document, not via legacy split service.'
        })

    @action(detail=True, methods=['post'], url_path='receive')
    def receive(self, request, pk=None):
        procurement = self.get_object()
        serializer = ReceiveProcurementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
                procurement=procurement,
                action='RECEIVE_BATCH',
                payload={'payload': {
                    'destination_warehouse_id': serializer.validated_data['destination_warehouse_id'],
                    'item_ids': serializer.validated_data.get('item_ids'),
                    'capital_allocations': serializer.validated_data.get('capital_allocations'),
                }},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement))

    @action(detail=True, methods=['post'], url_path='terms/amend')
    def terms_amend(self, request, pk=None):
        procurement = self.get_object()
        if not hasattr(procurement, 'terms'):
            raise ValidationError({'detail': 'Procurement has no terms to amend.'})
        serializer = TermsAmendmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
                procurement=procurement,
                action='AMEND_SETTLEMENT',
                payload={'payload': {
                    **serializer.validated_data['new_fields'],
                    'reason': serializer.validated_data.get('reason', ''),
                }},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='terms/amendments')
    def terms_amendments(self, request, pk=None):
        procurement = self.get_object()
        if not hasattr(procurement, 'terms'):
            return Response([])
        amendments = (
            procurement.terms.amendments
            .filter(tenant_id=request.tenant_id)
            .select_related('changed_by_user')
            .order_by('-amended_at', '-id')
        )
        return Response(ProcurementTermsAmendmentSerializer(amendments, many=True).data)

    @action(detail=True, methods=['post'], url_path='consignment-return')
    def consignment_return(self, request, pk=None):
        raise ValidationError({
            'detail': 'Consignment return must be implemented through RETURN_CONSIGNMENT workspace action.'
        })

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        procurement = self.get_object()
        payload = build_workspace_payload(procurement)
        return Response({
            'procurement_id': procurement.id,
            'investment': payload['documents']['investment'],
            'history': payload['history'],
        })

    @action(detail=True, methods=['get'], url_path='receive-plan')
    def receive_plan(self, request, pk=None):
        procurement = self.get_object()
        payload = build_workspace_payload(procurement)
        return Response({
            'procurement_id': procurement.id,
            'receive_ready': payload['readiness']['receive_ready'],
            'policy': payload['policy'],
        })


class DividendPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = DividendPaymentSerializer
    permission_classes = [IsOwner]
    ordering = ['-date']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = DividendPayment.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('partner', 'procurement')

        partner_id = self.request.query_params.get('partner')
        if partner_id:
            queryset = queryset.filter(partner_id=partner_id)

        procurement_id = self.request.query_params.get('procurement')
        if procurement_id:
            queryset = queryset.filter(procurement_id=procurement_id)

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return DividendPaymentCreateSerializer
        return DividendPaymentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = pay_dividend(
                tenant_id=request.tenant_id,
                partner_id=serializer.validated_data['partner_id'],
                procurement_id=serializer.validated_data['procurement_id'],
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data['fx_rate'],
                from_account_id=serializer.validated_data.get('paid_from_account_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(DividendPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
