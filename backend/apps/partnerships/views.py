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
    SettlePartnerCapitalSerializer,
    AgreementContributionCreateSerializer,
    AgreementWithdrawalCreateSerializer,
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
from decimal import Decimal

from .agreement_services import (
    get_partner_aggregate,
    pay_dividend,
)
from .advances import partner_capital_positions, settle_partner_capital
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
                reconciliation_mode=data.get('reconciliation_mode') or 'FACTUAL',
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
        serializer = AgreementContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contribution = add_agreement_contribution(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                partner_id=serializer.validated_data['partner_id'],
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data.get('fx_rate'),
                notes=serializer.validated_data.get('notes', ''),
                created_by_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(AgreementContributionSerializer(contribution).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='withdrawals')
    def withdrawals(self, request, pk=None):
        agreement = self.get_object()
        serializer = AgreementWithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdrawal = add_agreement_withdrawal(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                partner_id=serializer.validated_data['partner_id'],
                procurement_id=serializer.validated_data.get('procurement_id'),
                from_account_id=serializer.validated_data.get('from_account_id'),
                amount=serializer.validated_data['amount'],
                currency=serializer.validated_data['currency'],
                fx_rate=serializer.validated_data.get('fx_rate'),
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

    @action(detail=True, methods=['get'], url_path='profit-summary')
    def profit_summary(self, request, pk=None):
        """Per-partner, per-procurement undistributed profit (UZS) — payable rows
        for the dividend sheet. Only rows with pending > 0."""
        from .venture import procurement_venture_positions

        agreement = self.get_object()
        procurements = list(Procurement.objects.filter(
            tenant_id=request.tenant_id, agreement=agreement,
        ))
        members = {m.partner_id: m for m in agreement.partners.select_related('partner').all()}
        rows = []
        for proc in procurements:
            venture_positions = procurement_venture_positions(procurement=proc)
            has_venture_facts = any(
                Decimal(str(pos.get('capital_recovered_uzs', '0.00'))) != 0
                or Decimal(str(pos.get('provisional_profit_uzs', '0.00'))) != 0
                or Decimal(str(pos.get('loss_uzs', '0.00'))) != 0
                for pos in venture_positions.values()
            )
            for partner_id, member in members.items():
                if has_venture_facts:
                    pending = venture_positions.get(partner_id, {}).get(
                        'provisional_profit_available_uzs', Decimal('0'),
                    )
                else:
                    agg = get_partner_aggregate(partner_id, request.tenant_id, proc.id)
                    pending = agg.get('profit_pending_payout') or Decimal('0')
                if pending and Decimal(pending) > 0:
                    rows.append({
                        'procurement_id': proc.id,
                        'partner_id': partner_id,
                        'partner_name': getattr(member.partner, 'display_name', str(partner_id)),
                        'role': member.role,
                        'pending': str(pending),
                    })
        return Response(rows)

    @action(detail=True, methods=['get'], url_path='venture-summary')
    def venture_summary(self, request, pk=None):
        """E16 agreement-level partner proceeds summary across linked procurements."""
        from .venture import procurement_venture_positions, venture_blocking_reasons

        agreement = self.get_object()
        members = {
            member.partner_id: member
            for member in agreement.partners.select_related('partner').all()
        }
        totals: dict[int, dict[str, Decimal]] = {
            partner_id: {
                'deployed_uzs': Decimal('0.00'),
                'capital_recovered_uzs': Decimal('0.00'),
                'remaining_inventory_capital_uzs': Decimal('0.00'),
                'liability_capital_recovered_uzs': Decimal('0.00'),
                'provisional_profit_uzs': Decimal('0.00'),
                'loss_uzs': Decimal('0.00'),
                'partner_liability_loss_uzs': Decimal('0.00'),
                'capital_returned_uzs': Decimal('0.00'),
                'dividends_paid_uzs': Decimal('0.00'),
                'capital_return_available_uzs': Decimal('0.00'),
                'provisional_profit_available_uzs': Decimal('0.00'),
                'negative_position_uzs': Decimal('0.00'),
            }
            for partner_id in members
        }
        procurement_rows = []
        for procurement in Procurement.objects.filter(tenant_id=request.tenant_id, agreement=agreement):
            positions = procurement_venture_positions(procurement=procurement)
            procurement_total = Decimal('0.00')
            for partner_id, pos in positions.items():
                target = totals.setdefault(partner_id, {
                    'deployed_uzs': Decimal('0.00'),
                    'capital_recovered_uzs': Decimal('0.00'),
                    'remaining_inventory_capital_uzs': Decimal('0.00'),
                    'liability_capital_recovered_uzs': Decimal('0.00'),
                    'provisional_profit_uzs': Decimal('0.00'),
                    'loss_uzs': Decimal('0.00'),
                    'partner_liability_loss_uzs': Decimal('0.00'),
                    'capital_returned_uzs': Decimal('0.00'),
                    'dividends_paid_uzs': Decimal('0.00'),
                    'capital_return_available_uzs': Decimal('0.00'),
                    'provisional_profit_available_uzs': Decimal('0.00'),
                    'negative_position_uzs': Decimal('0.00'),
                })
                for key in target:
                    target[key] += Decimal(str(pos.get(key, '0.00')))
                procurement_total += Decimal(str(pos.get('capital_return_available_uzs', '0.00')))
            procurement_rows.append({
                'procurement_id': procurement.id,
                'status': procurement.status,
                'capital_return_available_uzs': str(procurement_total.quantize(Decimal('0.01'))),
                'blocking_reasons': venture_blocking_reasons(procurement=procurement),
            })
        rows = []
        for partner_id, values in totals.items():
            member = members.get(partner_id)
            rows.append({
                'partner_id': partner_id,
                'partner_name': getattr(member.partner, 'display_name', str(partner_id)) if member else str(partner_id),
                'role': member.role if member else '',
                **{key: str(value.quantize(Decimal('0.01'))) for key, value in values.items()},
            })
        rows.sort(key=lambda item: item['partner_id'])
        return Response({
            'agreement_id': agreement.id,
            'currency': 'UZS',
            'positions': rows,
            'procurements': procurement_rows,
        })

    @action(detail=True, methods=['post'], url_path='payout-preview')
    def payout_preview(self, request, pk=None):
        """E16 preview for capital/profit payouts with blocking reasons."""
        from apps.finance.models import CashAccount
        from apps.finance.fx_rates import resolve_fx_rate_snapshot_details
        from .venture import procurement_venture_positions

        agreement = self.get_object()
        partner_id = int(request.data.get('partner_id') or 0)
        procurement_id = request.data.get('procurement_id')
        payout_type = str(request.data.get('payout_type') or 'CAPITAL_RETURN').upper()
        amount = Decimal(str(request.data.get('amount') or '0')).quantize(Decimal('0.01'))
        currency = str(request.data.get('currency') or 'UZS').upper()
        from_account_id = request.data.get('from_account_id')
        fx_snapshot = resolve_fx_rate_snapshot_details(
            tenant_id=request.tenant_id,
            operation_currency=currency,
            operation_at=None,
            fx_rate_snapshot=request.data.get('fx_rate'),
        )
        functional = (amount * Decimal(str(fx_snapshot.rate))).quantize(Decimal('0.01'))
        reasons = []
        available = Decimal('0.00')

        procurement = None
        position = {}
        if procurement_id:
            procurement = Procurement.objects.filter(
                tenant_id=request.tenant_id,
                agreement=agreement,
                pk=procurement_id,
            ).first()
            if procurement is None:
                reasons.append('Приход не найден в этом договоре.')
            else:
                position = procurement_venture_positions(procurement=procurement).get(partner_id, {})
                if payout_type == 'PROFIT':
                    available = Decimal(str(position.get('provisional_profit_available_uzs', '0.00')))
                else:
                    available = Decimal(str(position.get('capital_return_available_uzs', '0.00')))
                if Decimal(str(position.get('negative_position_uzs', '0.00'))) > 0:
                    reasons.append('Есть отрицательная позиция партнёра; сначала погасите её.')
        else:
            positions = partner_capital_positions(agreement)
            if payout_type == 'PROFIT':
                reasons.append('Выплата прибыли требует выбрать конкретный приход.')
            else:
                available = Decimal(str(positions.get(partner_id, {}).get('withdrawable', '0.00')))

        if partner_id <= 0:
            reasons.append('Выберите участника договора.')
        if amount <= 0:
            reasons.append('Укажите сумму выплаты.')
        if amount > 0 and available < functional:
            reasons.append(f'Доступно только {available.quantize(Decimal("0.01"))} UZS.')
        if from_account_id:
            account = CashAccount.objects.filter(
                tenant_id=request.tenant_id,
                pk=from_account_id,
                is_active=True,
            ).first()
            if account is None:
                reasons.append('Касса не найдена.')
            elif str(account.currency).upper() != currency:
                reasons.append('Для выплаты в другой валюте сначала сделайте явную конвертацию.')
            elif Decimal(str(account.balance)) < amount:
                reasons.append(f'В кассе доступно только {account.balance} {currency}.')

        return Response({
            'allowed': not reasons,
            'payout_type': payout_type,
            'partner_id': partner_id or None,
            'procurement_id': int(procurement_id) if procurement_id else None,
            'amount': str(amount),
            'currency': currency,
            'fx_rate': str(fx_snapshot.rate),
            'fx_rate_source': fx_snapshot.source,
            'fx_rate_date': fx_snapshot.rate_date,
            'functional_amount_uzs': str(functional),
            'available_uzs': str(available.quantize(Decimal('0.01'))),
            'blocking_reasons': reasons,
        })

    @action(detail=True, methods=['get'], url_path='capital-positions')
    def capital_positions(self, request, pk=None):
        """B (participant↔pool): net capital position per partner vs the pool."""
        agreement = self.get_object()
        positions = partner_capital_positions(agreement)
        members = {m.partner_id: m for m in agreement.partners.select_related('partner').all()}
        rows = []
        for partner_id, pos in positions.items():
            member = members.get(partner_id)
            rows.append({
                'partner_id': partner_id,
                'partner_name': getattr(member.partner, 'display_name', str(partner_id)) if member else str(partner_id),
                'role': member.role if member else '',
                'deployed': str(pos['deployed']),
                'paid_in': str(pos['paid_in']),
                'net': str(pos['net']),
                'owed': str(pos['owed']),
                'withdrawable': str(pos['withdrawable']),
                'deployed_uzs': str(pos.get('deployed_uzs', '0.00')),
                'capital_recovered_uzs': str(pos.get('capital_recovered_uzs', '0.00')),
                'remaining_inventory_capital_uzs': str(pos.get('remaining_inventory_capital_uzs', '0.00')),
                'liability_capital_recovered_uzs': str(pos.get('liability_capital_recovered_uzs', '0.00')),
                'provisional_profit_uzs': str(pos.get('provisional_profit_uzs', '0.00')),
                'loss_uzs': str(pos.get('loss_uzs', '0.00')),
                'partner_liability_loss_uzs': str(pos.get('partner_liability_loss_uzs', '0.00')),
                'capital_returned_uzs': str(pos.get('capital_returned_uzs', '0.00')),
                'dividends_paid_uzs': str(pos.get('dividends_paid_uzs', '0.00')),
                'capital_return_available_uzs': str(pos.get('capital_return_available_uzs', '0.00')),
                'provisional_profit_available_uzs': str(pos.get('provisional_profit_available_uzs', '0.00')),
                'negative_position_uzs': str(pos.get('negative_position_uzs', '0.00')),
                'currency': agreement.currency,
            })
        rows.sort(key=lambda r: r['partner_id'])
        return Response(rows)

    @action(detail=True, methods=['post'], url_path='settle-partner-capital')
    def settle_partner_capital_action(self, request, pk=None):
        agreement = self.get_object()
        serializer = SettlePartnerCapitalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            settle_partner_capital(
                tenant_id=request.tenant_id,
                agreement_id=agreement.id,
                partner_id=serializer.validated_data['partner_id'],
                amount=serializer.validated_data['amount'],
                source=serializer.validated_data['source'],
                from_account_id=serializer.validated_data.get('from_account_id'),
                client_request_id=serializer.validated_data.get('client_request_id'),
            )
        except (ValueError, NotImplementedError) as error:
            raise ValidationError({'detail': str(error)}) from error
        return self.capital_positions(request, pk=pk)


class ProcurementViewSet(viewsets.ModelViewSet):
    ordering = ['-opened_at']

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'ledger', 'receive', 'receive_plan', 'venture_summary'):
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

    @action(detail=True, methods=['get'], url_path='venture-summary')
    def venture_summary(self, request, pk=None):
        """E16: current procurement-venture economic buckets in functional UZS."""
        from .venture import procurement_venture_positions, venture_blocking_reasons

        procurement = self.get_object()
        positions = procurement_venture_positions(procurement=procurement)
        members = {}
        if procurement.agreement_id:
            members = {
                member.partner_id: member
                for member in procurement.agreement.partners.select_related('partner').all()
            }
        rows = []
        totals = {
            'deployed_uzs': Decimal('0.00'),
            'capital_recovered_uzs': Decimal('0.00'),
            'remaining_inventory_capital_uzs': Decimal('0.00'),
            'liability_capital_recovered_uzs': Decimal('0.00'),
            'provisional_profit_uzs': Decimal('0.00'),
            'loss_uzs': Decimal('0.00'),
            'partner_liability_loss_uzs': Decimal('0.00'),
            'capital_returned_uzs': Decimal('0.00'),
            'dividends_paid_uzs': Decimal('0.00'),
            'capital_return_available_uzs': Decimal('0.00'),
            'provisional_profit_available_uzs': Decimal('0.00'),
            'negative_position_uzs': Decimal('0.00'),
        }
        for partner_id, pos in positions.items():
            member = members.get(partner_id)
            row = {
                'partner_id': partner_id,
                'partner_name': getattr(member.partner, 'display_name', str(partner_id)) if member else str(partner_id),
                'role': member.role if member else '',
            }
            for key in totals:
                value = Decimal(str(pos.get(key, '0.00'))).quantize(Decimal('0.01'))
                row[key] = str(value)
                totals[key] += value
            rows.append(row)
        rows.sort(key=lambda item: item['partner_id'])
        return Response({
            'procurement_id': procurement.id,
            'agreement_id': procurement.agreement_id,
            'currency': 'UZS',
            'positions': rows,
            'totals': {key: str(value.quantize(Decimal('0.01'))) for key, value in totals.items()},
            'blocking_reasons': venture_blocking_reasons(procurement=procurement),
        })

    @action(detail=True, methods=['post'], url_path='venture-settlements')
    def venture_settlements(self, request, pk=None):
        """E16: create constructive/final procurement venture settlement."""
        from .venture import create_venture_settlement

        procurement = self.get_object()
        try:
            settlement = create_venture_settlement(
                tenant_id=request.tenant_id,
                procurement_id=procurement.id,
                settlement_type=request.data.get('settlement_type', 'CONSTRUCTIVE'),
                inventory_value_uzs=request.data.get('inventory_value_uzs', '0'),
                reserve_uzs=request.data.get('reserve_uzs', '0'),
                notes=request.data.get('notes', ''),
                client_request_id=request.data.get('client_request_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response({
            'id': settlement.id,
            'procurement_id': settlement.procurement_id,
            'settlement_type': settlement.settlement_type,
            'settled_at': settlement.settled_at,
            'inventory_value_uzs': str(settlement.inventory_value_uzs),
            'reserve_uzs': str(settlement.reserve_uzs),
            'totals': settlement.totals,
            'partner_positions': settlement.partner_positions,
            'notes': settlement.notes,
        }, status=status.HTTP_201_CREATED)

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
        serializer = AgreementContributionCreateSerializer(data=request.data)
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
                fx_rate=serializer.validated_data.get('fx_rate'),
                from_account_id=serializer.validated_data.get('paid_from_account_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(DividendPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
