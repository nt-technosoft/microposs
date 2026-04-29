from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import IsOwner, IsWarehouse

from .models import DividendPayment, InvestmentAgreement, Procurement, ProcurementPartnerLedger
from .serializers import (
    AgreementAllocationCreateSerializer,
    AgreementAllocationSerializer,
    AgreementContributionSerializer,
    AgreementWithdrawalSerializer,
    BalanceContributionCreateSerializer,
    BalanceContributionSerializer,
    BalanceExchangeCreateSerializer,
    ProcurementBalanceExchangeSerializer,
    BalanceWithdrawalCreateSerializer,
    BalanceWithdrawalSerializer,
    DividendPaymentCreateSerializer,
    DividendPaymentSerializer,
    InvestmentAgreementCreateSerializer,
    InvestmentAgreementDetailSerializer,
    InvestmentAgreementListSerializer,
    ProcurementCreateSerializer,
    ProcurementDetailSerializer,
    ProcurementExpenseSerializer,
    ProcurementExpenseTargetsSerializer,
    ProcurementItemSplitSerializer,
    ProcurementLedgerSerializer,
    ProcurementListSerializer,
    PayProcurementExpensesSerializer,
    PayProcurementItemsSerializer,
    ReceiveProcurementSerializer,
)
from .services import (
    add_agreement_contribution,
    add_contribution,
    add_agreement_withdrawal,
    allocate_agreement_to_procurement,
    create_investment_agreement,
    exchange_procurement_balance,
    add_withdrawal,
    get_agreement_allocation_preview,
    get_procurement_receive_plan,
    open_procurement,
    pay_procurement_expenses,
    pay_procurement_items,
    pay_dividend,
    receive_procurement,
    split_procurement_item,
    update_procurement_expense_targets,
    update_open_procurement,
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
                'contributions__partner',
                'withdrawals__partner',
                'allocations__partner',
                'allocations__procurement',
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
            payload = get_agreement_allocation_preview(
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
            allocations = allocate_agreement_to_procurement(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                procurement_id=serializer.validated_data['procurement_id'],
                allocations=[dict(row) for row in serializer.validated_data['allocations']],
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
        queryset = Procurement.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('supplier', 'balance', 'contract').prefetch_related(
            'items__product_variant',
            'expenses__targets',
            'balance__contributions__partner',
            'balance__withdrawals',
            'balance__withdrawals__partner',
            'balance__exchanges',
            'contract__contract_partners__partner',
            'receive_batches__warehouse',
            'receive_batches__lines__item__product_variant',
            'receive_batches__lines__lot',
            'receive_batches__expenses__expense',
            'receive_batches__capital_allocations__partner',
        )

        status_value = self.request.query_params.get('status')
        if status_value:
            queryset = queryset.filter(status=status_value)

        procurement_type = self.request.query_params.get('procurement_type')
        if procurement_type:
            queryset = queryset.filter(procurement_type=procurement_type)

        return queryset

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ProcurementCreateSerializer
        if self.action == 'retrieve':
            return ProcurementDetailSerializer
        return ProcurementListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            procurement = open_procurement(
                tenant_id=request.tenant_id,
                procurement_type=data['procurement_type'],
                supplier_id=data.get('supplier_id'),
                notes=data.get('notes', ''),
                client_request_id=str(data['client_request_id']) if data.get('client_request_id') else None,
                agreement_id=data.get('agreement_id'),
                contract=dict(data['contract']) if data.get('contract') else None,
                items=[dict(item) for item in data.get('items', [])],
                expenses=[dict(expense) for expense in data.get('expenses', [])],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(ProcurementDetailSerializer(procurement).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        procurement = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            procurement = update_open_procurement(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                procurement_type=data['procurement_type'],
                supplier_id=data.get('supplier_id'),
                notes=data.get('notes', ''),
                agreement_id=data.get('agreement_id'),
                contract=dict(data['contract']) if data.get('contract') else None,
                items=[dict(item) for item in data.get('items', [])],
                expenses=[dict(expense) for expense in data.get('expenses', [])],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(ProcurementDetailSerializer(procurement).data)

    @action(detail=True, methods=['post'], url_path='contributions')
    def contributions(self, request, pk=None):
        procurement = self.get_object()
        serializer = BalanceContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contribution = add_contribution(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                partner_id=serializer.validated_data['partner_id'],
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data['fx_rate'],
                notes=serializer.validated_data.get('notes', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(BalanceContributionSerializer(contribution).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='withdrawals')
    def withdrawals(self, request, pk=None):
        procurement = self.get_object()
        serializer = BalanceWithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdrawal = add_withdrawal(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                partner_id=serializer.validated_data.get('partner_id'),
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data['fx_rate'],
                reason=serializer.validated_data.get('reason', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(BalanceWithdrawalSerializer(withdrawal).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='balance-exchanges')
    def balance_exchanges(self, request, pk=None):
        procurement = self.get_object()
        serializer = BalanceExchangeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            exchange = exchange_procurement_balance(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                from_currency=serializer.validated_data['from_currency'],
                from_amount=serializer.validated_data['from_amount'],
                to_currency=serializer.validated_data['to_currency'],
                rate=serializer.validated_data['rate'],
                notes=serializer.validated_data.get('notes', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(ProcurementBalanceExchangeSerializer(exchange).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='pay-items')
    def pay_items(self, request, pk=None):
        procurement = self.get_object()
        serializer = PayProcurementItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            items = pay_procurement_items(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                item_ids=serializer.validated_data.get('item_ids'),
                reason=serializer.validated_data.get('reason', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response({
            'count': len(items),
            'status': 'paid',
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='pay-expenses')
    def pay_expenses(self, request, pk=None):
        procurement = self.get_object()
        serializer = PayProcurementExpensesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expenses = pay_procurement_expenses(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                expense_ids=serializer.validated_data.get('expense_ids'),
                reason=serializer.validated_data.get('reason', ''),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response({
            'count': len(expenses),
            'status': 'paid',
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='expense-targets')
    def expense_targets(self, request, pk=None):
        procurement = self.get_object()
        serializer = ProcurementExpenseTargetsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expense = update_procurement_expense_targets(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                expense_id=serializer.validated_data['expense_id'],
                target_item_ids=serializer.validated_data.get('target_item_ids', []),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(ProcurementExpenseSerializer(expense).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='split-item')
    def split_item(self, request, pk=None):
        procurement = self.get_object()
        serializer = ProcurementItemSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            split_procurement_item(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                item_id=serializer.validated_data['item_id'],
                quantity=serializer.validated_data['quantity'],
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        procurement.refresh_from_db()
        return Response(ProcurementDetailSerializer(procurement).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='receive')
    def receive(self, request, pk=None):
        procurement = self.get_object()
        serializer = ReceiveProcurementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            procurement = receive_procurement(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                destination_warehouse_id=serializer.validated_data['destination_warehouse_id'],
                item_ids=serializer.validated_data.get('item_ids'),
                capital_allocations=serializer.validated_data.get('capital_allocations'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        detail = ProcurementDetailSerializer(procurement).data
        detail['items_count'] = procurement.items.count()
        return Response(detail)

    @action(detail=True, methods=['get'], url_path='ledger')
    def ledger(self, request, pk=None):
        procurement = self.get_object()
        ledgers = ProcurementPartnerLedger.objects.filter(
            tenant_id=request.tenant_id,
            procurement=procurement,
        ).select_related('partner').prefetch_related('entries').order_by('partner_id')
        return Response({
            'procurement_id': procurement.id,
            'partners': ProcurementLedgerSerializer(ledgers, many=True).data,
        })

    @action(detail=True, methods=['get'], url_path='receive-plan')
    def receive_plan(self, request, pk=None):
        procurement = self.get_object()
        raw_item_ids = request.query_params.get('item_ids', '')
        item_ids = [
            int(value)
            for value in raw_item_ids.split(',')
            if value.strip()
        ] or None
        return Response(get_procurement_receive_plan(
            tenant_id=request.tenant_id,
            procurement_id=procurement.id,
            item_ids=item_ids,
        ))


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
