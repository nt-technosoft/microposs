from decimal import Decimal

from rest_framework import serializers

from .models import (
    AgreementAllocation,
    AgreementContribution,
    AgreementEvent,
    AgreementPartner,
    AgreementTermsVersion,
    AgreementWithdrawal,
    CapitalSettlementSource,
    CapitalCommitment,
    InvestmentAgreement,
    ContractPartner,
    DividendPayment,
    DisputeCase,
    FundApplication,
    FundContribution,
    FundDeployment,
    FundMember,
    FundMemberExit,
    FundMemberPositionReadModel,
    FundPositionReadModel,
    FundTermsVersion,
    InvestmentContract,
    PartnerLedgerEntry,
    InvestmentFund,
    PayoutObligation,
    PayoutDecision,
    PayoutPolicy,
    PayoutSettlement,
    ContractReview,
    Procurement,
    ProcurementExpense,
    ProcurementExpenseTarget,
    ProcurementItem,
    ProcurementPartnerLedger,
    ProcurementReceiveBatch,
    ProcurementReceiveBatchCapitalAllocation,
    ProcurementReceiveBatchExpense,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
    ProcurementTermsAmendment,
)
from .money_utils import money as _money, ratio as _ratio
from .workspace import build_workspace_payload
from apps.core.models import Partner
from apps.suppliers.models import PaymentSchedule

def _to_contract_currency(amount, currency: str, fx_rate, contract_currency: str) -> Decimal:
    amount_dec = Decimal(str(amount))
    rate_dec = Decimal(str(fx_rate or '1'))
    source = str(currency or contract_currency).upper()
    target = str(contract_currency or 'UZS').upper()
    if source == target:
        return _money(amount_dec)
    if source == 'USD' and target == 'UZS':
        return _money(amount_dec * rate_dec)
    if source == 'UZS' and target == 'USD':
        if rate_dec <= 0:
            return Decimal('0.00')
        return _money(amount_dec / rate_dec)
    return _money(amount_dec)


def _investor_pool_shares(obj) -> dict | None:
    investors = [
        row for row in obj.partners.all()
        if row.role == AgreementPartner.Role.INVESTOR
    ]
    if not investors:
        return None
    budget = Decimal(str(obj.planned_budget or '0'))
    capital = sum((Decimal(str(row.planned_capital_share or '0')) for row in investors), Decimal('0'))
    profit = sum((Decimal(str(row.profit_share or '0')) for row in investors), Decimal('0'))
    return {
        'capital_amount': str(_money(capital)),
        'profit_share': str(_ratio(profit)),
        'capital_percent': round(float(capital / budget * Decimal('100'))) if budget else 0,
        'profit_percent': round(float(profit * Decimal('100'))),
        'investors_count': len(investors),
    }


class ProcurementItemSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(source='product_variant.__str__', read_only=True)

    class Meta:
        model = ProcurementItem
        fields = [
            'id', 'product_variant', 'product_variant_name', 'quantity',
            'unit_purchase_price', 'currency', 'fx_rate', 'goods_ownership',
            'lifecycle_state',
        ]
        read_only_fields = ['id']


class ProcurementExpenseSerializer(serializers.ModelSerializer):
    target_item_ids = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementExpense
        fields = [
            'id', 'expense_type', 'amount', 'currency', 'fx_rate',
            'allocation_method', 'notes', 'lifecycle_state', 'target_item_ids',
        ]
        read_only_fields = ['id']

    def get_target_item_ids(self, obj):
        return list(obj.targets.values_list('item_id', flat=True))


class ProcurementReceiveBatchLineSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(source='item.product_variant.__str__', read_only=True)

    class Meta:
        model = ProcurementReceiveBatchLine
        fields = [
            'id', 'item', 'lot', 'product_variant_name',
            'quantity_planned', 'quantity_received', 'discrepancy_reason',
            'unit_purchase_price_uzs', 'allocated_expense_uzs', 'landed_cost_per_unit_uzs',
        ]
        read_only_fields = ['id']


class ProcurementReceiveBatchExpenseSerializer(serializers.ModelSerializer):
    expense_type = serializers.CharField(source='expense.expense_type', read_only=True)

    class Meta:
        model = ProcurementReceiveBatchExpense
        fields = ['id', 'expense', 'expense_type', 'allocated_amount_uzs']
        read_only_fields = ['id']


class ProcurementReceiveBatchCapitalAllocationSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)

    class Meta:
        model = ProcurementReceiveBatchCapitalAllocation
        fields = [
            'id', 'partner', 'partner_name', 'role',
            'amount_contract_currency', 'capital_share', 'profit_share',
        ]
        read_only_fields = ['id']


class ProcurementReceiveBatchSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    lines = ProcurementReceiveBatchLineSerializer(many=True, read_only=True)
    expenses = ProcurementReceiveBatchExpenseSerializer(many=True, read_only=True)
    capital_allocations = ProcurementReceiveBatchCapitalAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = ProcurementReceiveBatch
        fields = [
            'id', 'warehouse', 'warehouse_name', 'received_at',
            'items_count', 'total_inventory_uzs', 'lines', 'expenses',
            'capital_allocations',
        ]
        read_only_fields = ['id']


class PaymentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSchedule
        fields = [
            'id', 'sequence_number', 'due_date', 'amount',
            'currency', 'status', 'paid_at', 'paid_amount',
        ]
        read_only_fields = ['id']


class ProcurementTermsSerializer(serializers.ModelSerializer):
    schedule = PaymentScheduleSerializer(source='schedule_entries', many=True, read_only=True)
    paid_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
    )
    remaining_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
    )

    class Meta:
        model = ProcurementTerms
        fields = [
            'id', 'type', 'currency_of_obligation', 'fx_rate_at_obligation',
            'total_amount_due', 'paid_amount', 'remaining_amount', 'status',
            'deadline_date', 'consignment_agreement', 'notes', 'schedule',
        ]
        read_only_fields = ['id', 'paid_amount', 'remaining_amount']


class AgreementPartnerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = AgreementPartner
        fields = [
            'id', 'partner', 'partner_name', 'display_name', 'role',
            'planned_capital_share', 'profit_share',
        ]
        read_only_fields = ['id']

    def get_display_name(self, obj):
        return 'Бизнес' if obj.role == AgreementPartner.Role.OPERATOR else obj.partner.display_name


class PayoutPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutPolicy
        fields = [
            'review_interval_days', 'minimum_available_amount',
            'minimum_days_between_payouts', 'reserve_amount',
            'grace_period_days', 'allow_partial', 'trigger_mode',
            'last_evaluated_at',
        ]


class PayoutPolicyInputSerializer(serializers.Serializer):
    review_interval_days = serializers.IntegerField(required=False, min_value=1)
    minimum_available_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    minimum_days_between_payouts = serializers.IntegerField(required=False, min_value=0)
    reserve_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    grace_period_days = serializers.IntegerField(required=False, min_value=0)
    allow_partial = serializers.BooleanField(required=False)
    trigger_mode = serializers.ChoiceField(
        choices=PayoutPolicy.TriggerMode.choices,
        required=False,
    )


class AgreementTermsVersionSerializer(serializers.ModelSerializer):
    payout_policy = PayoutPolicySerializer(read_only=True)

    class Meta:
        model = AgreementTermsVersion
        fields = [
            'id', 'version', 'effective_at', 'review_at', 'offline_agreed_at',
            'offline_agreement_reference', 'terms_snapshot', 'notes', 'payout_policy',
        ]
        read_only_fields = fields


class FundTermsVersionSerializer(serializers.ModelSerializer):
    payout_policy = PayoutPolicySerializer(read_only=True)

    class Meta:
        model = FundTermsVersion
        fields = [
            'id', 'version', 'effective_at', 'review_at', 'manager_profit_share',
            'offline_agreed_at', 'offline_agreement_reference', 'terms_snapshot', 'notes', 'payout_policy',
        ]
        read_only_fields = fields


class FundMemberSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source='profile.display_name', read_only=True)
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = FundMember
        fields = [
            'id', 'profile', 'profile_name', 'partner', 'partner_name', 'application', 'status',
            'approved_amount', 'confirmed_amount', 'joined_at', 'exited_at',
            'offline_agreed_at', 'offline_agreement_reference',
        ]
        read_only_fields = fields

    def get_partner_name(self, obj):
        return obj.profile.display_name if obj.profile_id else (obj.partner.display_name if obj.partner_id else '')


class FundApplicationSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source='profile.display_name', read_only=True)
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = FundApplication
        fields = [
            'id', 'fund', 'profile', 'profile_name', 'partner', 'partner_name', 'requested_amount',
            'approved_amount', 'currency', 'status', 'message', 'decided_at',
            'decided_by', 'created_at',
        ]
        read_only_fields = fields

    def get_partner_name(self, obj):
        return obj.profile.display_name if obj.profile_id else (obj.partner.display_name if obj.partner_id else '')


class FundApplicationCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False)
    invite_token = serializers.CharField(required=False, default='', allow_blank=True)
    requested_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    message = serializers.CharField(required=False, default='', allow_blank=True)


class FundApplicationDecisionSerializer(serializers.Serializer):
    approved_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)


class FundApplicationApprovalPreviewRowSerializer(serializers.Serializer):
    application_id = serializers.IntegerField()
    approved_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)


class FundApplicationApprovalPreviewSerializer(serializers.Serializer):
    approvals = FundApplicationApprovalPreviewRowSerializer(many=True)


class FundContributionSerializer(serializers.ModelSerializer):
    partner = serializers.IntegerField(source='member.partner_id', read_only=True)
    profile = serializers.IntegerField(source='member.profile_id', read_only=True)
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = FundContribution
        fields = [
            'id', 'member', 'profile', 'partner', 'partner_name', 'amount', 'currency',
            'fx_rate', 'fx_rate_source', 'fx_rate_date', 'date', 'notes',
            'client_request_id',
        ]
        read_only_fields = fields

    def get_partner_name(self, obj):
        member = obj.member
        return member.profile.display_name if member.profile_id else (member.partner.display_name if member.partner_id else '')


class FundDeploymentSerializer(serializers.ModelSerializer):
    agreement_label = serializers.SerializerMethodField()

    class Meta:
        model = FundDeployment
        fields = [
            'id', 'agreement', 'agreement_label', 'agreement_contribution',
            'amount', 'currency', 'date', 'notes', 'client_request_id',
        ]
        read_only_fields = fields

    def get_agreement_label(self, obj):
        return f'Инвестдоговор #{obj.agreement_id}'


class FundMemberExitSerializer(serializers.ModelSerializer):
    partner = serializers.IntegerField(source='member.partner_id', read_only=True)
    profile = serializers.IntegerField(source='member.profile_id', read_only=True)
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = FundMemberExit
        fields = [
            'id', 'fund', 'member', 'profile', 'partner', 'partner_name', 'reason',
            'refund_amount', 'currency', 'refunded_at', 'notes',
            'client_request_id',
        ]
        read_only_fields = fields

    def get_partner_name(self, obj):
        member = obj.member
        return member.profile.display_name if member.profile_id else (member.partner.display_name if member.partner_id else '')


class FundMemberExitCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False)
    profile_id = serializers.IntegerField(required=False)
    reason = serializers.ChoiceField(choices=FundMemberExit.Reason.choices)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class FundMemberPositionSerializer(serializers.ModelSerializer):
    partner = serializers.IntegerField(source='member.partner_id', read_only=True)
    profile = serializers.IntegerField(source='member.profile_id', read_only=True)
    partner_name = serializers.SerializerMethodField()

    class Meta:
        model = FundMemberPositionReadModel
        fields = [
            'id', 'member', 'profile', 'partner', 'partner_name', 'currency', 'capital_share',
            'paid_in', 'deployed', 'available', 'provisional_profit_uzs',
            'capital_return_available_uzs', 'profit_available_uzs',
            'manager_fee_accrued_uzs', 'computed_at',
        ]
        read_only_fields = fields

    def get_partner_name(self, obj):
        member = obj.member
        return member.profile.display_name if member.profile_id else (member.partner.display_name if member.partner_id else '')


class FundPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FundPositionReadModel
        fields = [
            'currency', 'paid_in', 'deployed', 'available',
            'provisional_profit_uzs', 'capital_return_available_uzs',
            'profit_available_uzs', 'manager_fee_accrued_uzs', 'computed_at',
        ]
        read_only_fields = fields


class InvestmentFundSerializer(serializers.ModelSerializer):
    manager_profile_name = serializers.CharField(source='manager_profile.display_name', read_only=True)
    manager_partner_name = serializers.SerializerMethodField()
    holder_partner_name = serializers.SerializerMethodField()
    active_members_count = serializers.SerializerMethodField()
    pending_applications_count = serializers.SerializerMethodField()
    current_terms = FundTermsVersionSerializer(read_only=True)
    members = FundMemberSerializer(many=True, read_only=True)
    applications = FundApplicationSerializer(many=True, read_only=True)
    contributions = FundContributionSerializer(many=True, read_only=True)
    deployments = FundDeploymentSerializer(many=True, read_only=True)
    member_exits = FundMemberExitSerializer(many=True, read_only=True)
    positions = FundMemberPositionSerializer(source='member_position_rows', many=True, read_only=True)
    position = FundPositionSerializer(source='position_row', read_only=True)
    invite_path = serializers.SerializerMethodField()
    viewer_role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentFund
        fields = [
            'id', 'name', 'status', 'manager_profile', 'manager_profile_name',
            'manager_partner', 'manager_partner_name',
            'holder_partner', 'holder_partner_name', 'capital_account', 'currency',
            'visibility', 'invite_token', 'invite_path', 'target_amount',
            'min_contribution_amount', 'opened_at', 'closed_at', 'current_terms', 'members',
            'applications', 'contributions', 'deployments', 'member_exits', 'positions',
            'position', 'active_members_count', 'pending_applications_count',
            'viewer_role', 'permissions',
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        role = data.get('viewer_role')
        if role != 'MANAGER':
            viewer_profile_id = self._viewer_profile_id()
            self._redact_public_terms_snapshot(data)
            data['members'] = [
                row for row in data.get('members', [])
                if role == 'MEMBER' and row.get('profile') and row.get('profile') == viewer_profile_id
            ]
            data['applications'] = [
                row for row in data.get('applications', [])
                if row.get('profile') and row.get('profile') == viewer_profile_id
            ]
            data['contributions'] = []
            data['deployments'] = []
            data['member_exits'] = []
            data['positions'] = [
                row for row in data.get('positions', [])
                if row.get('profile') and row.get('profile') == viewer_profile_id
            ]
        return data

    def _redact_public_terms_snapshot(self, data):
        current_terms = data.get('current_terms')
        if not isinstance(current_terms, dict):
            return
        snapshot = current_terms.get('terms_snapshot')
        if not isinstance(snapshot, dict):
            return
        allowed_keys = {
            'name',
            'currency',
            'target_amount',
            'min_contribution_amount',
            'visibility',
            'manager_profit_share',
            'waterfall',
        }
        current_terms['terms_snapshot'] = {
            key: value for key, value in snapshot.items() if key in allowed_keys
        }

    def _viewer_profile_id(self):
        request = self.context.get('request')
        try:
            profile = getattr(getattr(request, 'user', None), 'investment_profile', None)
        except Exception:
            profile = None
        return getattr(profile, 'pk', None)

    def get_manager_partner_name(self, obj):
        return obj.manager_profile.display_name if obj.manager_profile_id else (obj.manager_partner.display_name if obj.manager_partner_id else '')

    def get_holder_partner_name(self, obj):
        return obj.holder_partner.display_name if obj.holder_partner_id else ''

    def get_active_members_count(self, obj):
        return obj.members.filter(status=FundMember.Status.ACTIVE).count()

    def get_pending_applications_count(self, obj):
        return obj.applications.filter(status=FundApplication.Status.PENDING).count()

    def get_invite_path(self, obj):
        if not obj.invite_token:
            return ''
        return f'/investor/funds/join/{obj.invite_token}'

    def get_viewer_role(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return 'PUBLIC'
        if request.user.is_staff:
            return 'MANAGER'
        profile_id = self._viewer_profile_id()
        if profile_id and obj.manager_profile_id == profile_id:
            return 'MANAGER'
        if profile_id and obj.members.filter(profile_id=profile_id, status=FundMember.Status.ACTIVE).exists():
            return 'MEMBER'
        if profile_id and obj.applications.filter(profile_id=profile_id).exists():
            return 'APPLICANT'
        return 'PUBLIC'

    def get_permissions(self, obj):
        role = self.get_viewer_role(obj)
        raising = obj.status == InvestmentFund.Status.RAISING
        return {
            'can_apply': role in {'PUBLIC', 'APPLICANT'} and raising,
            'can_manage_applications': role == 'MANAGER' and raising,
            'can_confirm_contribution': role == 'MANAGER' and raising,
            'can_amend_terms': role == 'MANAGER' and raising,
            'can_deploy': role == 'MANAGER' and obj.status in {InvestmentFund.Status.RAISING, InvestmentFund.Status.DEPLOYED},
            'can_record_payout': role == 'MANAGER',
        }


class InvestmentFundCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    manager_partner_id = serializers.IntegerField(required=False)
    member_partner_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    target_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)
    min_contribution_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, default='0')
    visibility = serializers.ChoiceField(choices=InvestmentFund.Visibility.choices, required=False, default=InvestmentFund.Visibility.PRIVATE_INVITE)
    manager_profit_share = serializers.DecimalField(max_digits=7, decimal_places=6, required=False, default='0')
    review_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreed_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreement_reference = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    payout_policy = PayoutPolicyInputSerializer(required=False)


class FundTermsAmendSerializer(serializers.Serializer):
    target_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)
    min_contribution_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)
    visibility = serializers.ChoiceField(
        choices=InvestmentFund.Visibility.choices,
        required=False,
        allow_null=True,
    )
    review_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreed_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreement_reference = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    payout_policy = PayoutPolicyInputSerializer(required=False)
    manager_profit_share = serializers.DecimalField(max_digits=7, decimal_places=6, required=False, allow_null=True)


class FundContributionCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False)
    profile_id = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class FundDeploymentCreateSerializer(serializers.Serializer):
    agreement_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class PayoutSettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutSettlement
        fields = [
            'id', 'amount', 'settled_at', 'evidence', 'dividend_payment',
            'capital_withdrawal',
        ]
        read_only_fields = fields


class PayoutObligationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.SerializerMethodField()
    settlements = PayoutSettlementSerializer(many=True, read_only=True)

    class Meta:
        model = PayoutObligation
        fields = [
            'id', 'agreement', 'fund', 'recipient', 'recipient_profile', 'recipient_name', 'procurement',
            'kind', 'amount', 'paid_amount', 'currency', 'due_at', 'status', 'recorded_at',
            'confirmed_at', 'dividend_payment', 'capital_withdrawal', 'notes',
            'settlements',
        ]
        read_only_fields = fields

    def get_recipient_name(self, obj):
        if obj.recipient_id:
            return obj.recipient.display_name
        if obj.recipient_profile_id:
            return obj.recipient_profile.display_name
        return ''


class PayoutDecisionAllocationInputSerializer(serializers.Serializer):
    procurement_id = serializers.IntegerField()
    partner_id = serializers.IntegerField()
    amount_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)


class PayoutDecisionPreviewSerializer(serializers.Serializer):
    decision_type = serializers.ChoiceField(choices=PayoutDecision.DecisionType.choices)
    amount_uzs = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, allow_null=True)
    from_account_id = serializers.IntegerField(required=False, allow_null=True)
    allocations = PayoutDecisionAllocationInputSerializer(many=True, required=False)


class PayoutDecisionExecuteSerializer(PayoutDecisionPreviewSerializer):
    amount_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class DisputeCaseSerializer(serializers.ModelSerializer):
    raised_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DisputeCase
        fields = [
            'id', 'agreement', 'fund', 'obligation', 'raised_by', 'raised_by_profile', 'raised_by_name',
            'status', 'statement', 'evidence', 'resolved_at', 'resolution_notes',
        ]
        read_only_fields = fields

    def get_raised_by_name(self, obj):
        if obj.raised_by_id:
            return obj.raised_by.display_name
        if obj.raised_by_profile_id:
            return obj.raised_by_profile.display_name
        return ''


class DisputeCreateSerializer(serializers.Serializer):
    raised_by_id = serializers.IntegerField(required=False, allow_null=True)
    raised_by_profile_id = serializers.IntegerField(required=False, allow_null=True)
    statement = serializers.CharField()
    evidence = serializers.CharField(required=False, default='', allow_blank=True)


class DisputeResolveSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()
    resolution_notes = serializers.CharField(required=False, default='', allow_blank=True)


class ContractReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractReview
        fields = [
            'id', 'agreement', 'fund', 'due_at', 'resolution', 'resolved_at',
            'resolved_by', 'extension_until', 'notes',
        ]
        read_only_fields = fields


class ContractReviewResolveSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=ContractReview.Resolution.choices)
    extension_until = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class TermsVersionCreateSerializer(serializers.Serializer):
    review_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreed_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreement_reference = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    payout_policy = PayoutPolicyInputSerializer(required=False)
    manager_profit_share = serializers.DecimalField(max_digits=7, decimal_places=6, required=False)


class CapitalCommitmentSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = CapitalCommitment
        fields = [
            'id', 'partner', 'partner_name', 'partner_role',
            # CapitalCommitment is a plan/intent record, not a money movement —
            # fx snapshot (source/date) lives only on actual flows (contribution/
            # withdrawal/dividend). Decision from Codex session 2026-05-26.
            'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'notes', 'client_request_id',
        ]
        read_only_fields = ['id', 'created_by_name', 'actor_partner_name']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class SettlePartnerCapitalSerializer(serializers.Serializer):
    """B (participant↔pool): settle a partner's net capital shortfall vs the pool."""
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    source = serializers.ChoiceField(choices=CapitalSettlementSource.choices)
    from_account_id = serializers.IntegerField(required=False, allow_null=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class RepayVentureDebtSerializer(serializers.Serializer):
    """E17 T-5.3: repay a partner's negative venture position with real cash."""
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    paid_to_account_id = serializers.IntegerField()
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class AgreementContributionSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementContribution
        fields = [
            'id', 'partner', 'partner_name', 'partner_role',
            'amount', 'currency', 'fx_rate', 'fx_rate_source', 'fx_rate_date', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'notes', 'client_request_id',
        ]
        read_only_fields = ['id', 'date']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementWithdrawalSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementWithdrawal
        fields = [
            'id', 'procurement', 'paid_from_account', 'partner', 'partner_name', 'partner_role',
            'return_kind', 'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'reason', 'client_request_id',
        ]
        read_only_fields = ['id', 'date']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementAllocationSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementAllocation
        fields = [
            'id', 'procurement', 'partner', 'partner_name', 'partner_role',
            'direction', 'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'notes', 'client_request_id',
        ]
        read_only_fields = ['id', 'date']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementEventSerializer(serializers.ModelSerializer):
    actor_user_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementEvent
        fields = [
            'id', 'event_type', 'occurred_at',
            'actor_user', 'actor_user_name', 'actor_partner',
            'actor_partner_name', 'source', 'related_model',
            'related_id', 'payload',
        ]
        read_only_fields = fields

    def get_actor_user_name(self, obj):
        user = getattr(obj, 'actor_user', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class InvestmentAgreementListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    partners_count = serializers.SerializerMethodField()
    procurements_count = serializers.SerializerMethodField()
    investor_names = serializers.SerializerMethodField()
    operator_names = serializers.SerializerMethodField()
    investor_shares = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentAgreement
        fields = [
            'id', 'status', 'opened_at', 'closed_at', 'supplier', 'supplier_name',
            'planned_budget', 'currency', 'mudaraba_ratio', 'reconciliation_mode', 'balances',
            'partners_count', 'investor_names', 'operator_names',
            'investor_shares', 'procurements_count', 'notes', 'current_terms',
        ]
        read_only_fields = ['id']

    def get_partners_count(self, obj):
        return obj.partners.count()

    def get_investor_names(self, obj):
        return [
            row.partner.display_name
            for row in obj.partners.all()
            if row.role == AgreementPartner.Role.INVESTOR
        ]

    def get_operator_names(self, obj):
        return [
            row.partner.display_name
            for row in obj.partners.all()
            if row.role == AgreementPartner.Role.OPERATOR
        ]

    def get_procurements_count(self, obj):
        return obj.procurements.count()

    def get_investor_shares(self, obj):
        return _investor_pool_shares(obj)


class InvestmentAgreementDetailSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    partners = AgreementPartnerSerializer(many=True, read_only=True)
    commitments = CapitalCommitmentSerializer(many=True, read_only=True)
    contributions = AgreementContributionSerializer(many=True, read_only=True)
    withdrawals = AgreementWithdrawalSerializer(many=True, read_only=True)
    allocations = AgreementAllocationSerializer(many=True, read_only=True)
    events = AgreementEventSerializer(many=True, read_only=True)
    procurements = serializers.SerializerMethodField()
    participant_totals = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    current_terms = AgreementTermsVersionSerializer(read_only=True)
    investor_shares = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentAgreement
        fields = [
            'id', 'status', 'opened_at', 'closed_at', 'supplier', 'supplier_name',
            'mudaraba_ratio', 'loss_rule', 'planned_budget', 'currency',
            'reconciliation_mode', 'current_terms',
            'balances', 'notes', 'client_request_id', 'partners',
            'commitments', 'contributions', 'withdrawals', 'allocations',
            'events', 'procurements', 'participant_totals', 'history',
            'investor_shares',
        ]
        read_only_fields = ['id']

    def get_procurements(self, obj):
        return ProcurementListSerializer(obj.procurements.all(), many=True, context=self.context).data

    def get_investor_shares(self, obj):
        return _investor_pool_shares(obj)

    def get_participant_totals(self, obj):
        from .read_models import read_positions
        positions = read_positions(obj)

        rows = {
            partner.partner_id: {
                'partner_id': partner.partner_id,
                'partner_name': partner.partner.display_name,
                'display_name': 'Бизнес' if partner.role == AgreementPartner.Role.OPERATOR else partner.partner.display_name,
                'role': partner.role,
                'planned_capital_share': str(_money(partner.planned_capital_share)),
                'planned_profit_share': str(_ratio(partner.profit_share)),
                'contributed_amount': Decimal('0.00'),
                'gross_contributed_amount': Decimal('0.00'),
                'withdrawn_amount': Decimal('0.00'),
                'pool_withdrawn_amount': Decimal('0.00'),
                'proceeds_withdrawn_amount': Decimal('0.00'),
                'allocated_amount': Decimal('0.00'),
                'returned_amount': Decimal('0.00'),
            }
            for partner in obj.partners.all()
        }
        target_currency = str(obj.currency or 'UZS').upper()
        for contribution in obj.contributions.all():
            if contribution.partner_id in rows:
                rows[contribution.partner_id]['gross_contributed_amount'] += _to_contract_currency(
                    contribution.amount, contribution.currency, contribution.fx_rate, target_currency,
                )
        for withdrawal in obj.withdrawals.all():
            if withdrawal.partner_id in rows:
                amount = _to_contract_currency(
                    withdrawal.amount, withdrawal.currency, withdrawal.fx_rate, target_currency,
                )
                rows[withdrawal.partner_id]['withdrawn_amount'] += amount
                if withdrawal.return_kind == AgreementWithdrawal.ReturnKind.FROM_POOL:
                    rows[withdrawal.partner_id]['pool_withdrawn_amount'] += amount
                else:
                    rows[withdrawal.partner_id]['proceeds_withdrawn_amount'] += amount
        for allocation in obj.allocations.all():
            if allocation.partner_id not in rows:
                continue
            amount = _to_contract_currency(allocation.amount, allocation.currency, allocation.fx_rate, target_currency)
            if allocation.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
                rows[allocation.partner_id]['allocated_amount'] += amount
            else:
                rows[allocation.partner_id]['returned_amount'] += amount
        result = []
        for row in rows.values():
            pid = row['partner_id']
            pos = positions.get(pid, {})
            # E17/E18: use pool-correct paid_in from the materialized read-model
            # instead of contributed − ALL withdrawals (which wrongly included
            # recovered-capital returns and made available_amount go negative).
            paid_in = Decimal(str(pos.get('paid_in', Decimal('0.00'))))
            withdrawable = Decimal(str(pos.get('withdrawable', Decimal('0.00'))))
            row['contributed_amount'] = paid_in
            row['available_amount'] = paid_in - row['allocated_amount'] + row['returned_amount']
            row['withdrawable_amount'] = withdrawable
            for key in [
                'contributed_amount', 'gross_contributed_amount',
                'withdrawn_amount', 'pool_withdrawn_amount', 'proceeds_withdrawn_amount',
                'allocated_amount', 'returned_amount', 'available_amount', 'withdrawable_amount',
            ]:
                row[key] = str(_money(row[key]))
            result.append(row)
        return sorted(result, key=lambda item: (item['role'], item['partner_id']))

    def get_history(self, obj):
        entries = []
        for contribution in obj.contributions.all():
            entries.append({
                'id': f'contribution-{contribution.id}',
                'kind': 'CONTRIBUTION',
                'date': contribution.date,
                'title': 'Пополнение договора',
                'partner_id': contribution.partner_id,
                'partner_name': contribution.partner.display_name,
                'partner_role': contribution.partner.role,
                'amount': str(_money(contribution.amount)),
                'currency': str(contribution.currency).upper(),
                'procurement_id': None,
                'note': contribution.notes,
            })
        for withdrawal in obj.withdrawals.all():
            title = (
                'Возврат реализованного капитала'
                if withdrawal.return_kind == AgreementWithdrawal.ReturnKind.FROM_PROCEEDS
                else 'Возврат свободного капитала из договора'
            )
            entries.append({
                'id': f'withdrawal-{withdrawal.id}',
                'kind': 'WITHDRAWAL',
                'return_kind': withdrawal.return_kind,
                'date': withdrawal.date,
                'title': title,
                'partner_id': withdrawal.partner_id,
                'partner_name': withdrawal.partner.display_name,
                'display_name': 'Бизнес' if withdrawal.partner.role == Partner.Role.OPERATOR else withdrawal.partner.display_name,
                'partner_role': withdrawal.partner.role,
                'amount': str(_money(withdrawal.amount)),
                'currency': str(withdrawal.currency).upper(),
                'procurement_id': withdrawal.procurement_id,
                'note': withdrawal.reason,
            })
        for allocation in obj.allocations.all():
            entries.append({
                'id': f'allocation-{allocation.id}',
                'kind': allocation.direction,
                'date': allocation.date,
                'title': 'В приход' if allocation.direction == AgreementAllocation.Direction.TO_PROCUREMENT else 'Возврат из прихода',
                'partner_id': allocation.partner_id,
                'partner_name': allocation.partner.display_name,
                'partner_role': allocation.partner.role,
                'amount': str(_money(allocation.amount)),
                'currency': str(allocation.currency).upper(),
                'procurement_id': allocation.procurement_id,
                'note': allocation.notes,
            })
        return sorted(entries, key=lambda item: (item['date'], item['id']), reverse=True)

class ContractPartnerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)

    class Meta:
        model = ContractPartner
        fields = [
            'id', 'partner', 'partner_name', 'role',
            'planned_capital_share', 'profit_share',
        ]
        read_only_fields = ['id']


class InvestmentContractSerializer(serializers.ModelSerializer):
    partners = ContractPartnerSerializer(source='contract_partners', many=True, read_only=True)

    class Meta:
        model = InvestmentContract
        fields = [
            'id', 'mudaraba_ratio', 'loss_rule', 'planned_budget',
            'currency', 'partners',
        ]
        read_only_fields = ['id']


class PartnerLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerLedgerEntry
        fields = [
            'id', 'date', 'amount', 'currency', 'fx_rate',
            'functional_amount_uzs', 'entry_type', 'source_ref',
        ]
        read_only_fields = ['id']


class ProcurementLedgerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    entries = PartnerLedgerEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ProcurementPartnerLedger
        fields = ['id', 'partner', 'partner_name', 'entries']
        read_only_fields = ['id']


class ProcurementListSerializer(serializers.ModelSerializer):
    funding_source = serializers.CharField(read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    agreement_label = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    is_receive_ready = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    receive_status = serializers.SerializerMethodField()
    receive_message = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'funding_source', 'status', 'opened_at', 'received_at',
            'supplier', 'supplier_name', 'agreement', 'agreement_label',
            'items_count', 'is_receive_ready',
            'total_amount', 'notes', 'receive_status', 'receive_message',
        ]
        read_only_fields = ['id']

    def get_items_count(self, obj):
        return obj.items.count()

    def get_agreement_label(self, obj):
        if not obj.agreement_id:
            return None
        return f'Инвестдоговор #{obj.agreement_id}'

    def _receive_plan(self, obj):
        cache = self.context.setdefault('_workspace_payload_cache', {})
        if obj.pk not in cache:
            cache[obj.pk] = build_workspace_payload(obj)
        return cache[obj.pk]

    def get_total_amount(self, obj):
        item_total = sum(
            (
                Decimal(str(item.quantity))
                * Decimal(str(item.unit_purchase_price))
                * Decimal(str(item.fx_rate))
                for item in obj.items.all()
            ),
            Decimal('0'),
        )
        expense_total = sum(
            (
                Decimal(str(expense.amount))
                * Decimal(str(expense.fx_rate))
                for expense in obj.expenses.all()
            ),
            Decimal('0'),
        )
        return str((item_total + expense_total).quantize(Decimal('0.01')))

    def get_is_receive_ready(self, obj):
        return bool(self._receive_plan(obj)['readiness']['receive_ready']['ok'])

    def get_receive_status(self, obj):
        return 'READY' if self.get_is_receive_ready(obj) else 'BLOCKED'

    def get_receive_message(self, obj):
        return self._receive_plan(obj)['readiness']['receive_ready']['message']


class ProcurementDetailSerializer(serializers.ModelSerializer):
    funding_source = serializers.CharField(read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    agreement_label = serializers.SerializerMethodField()
    items = ProcurementItemSerializer(many=True, read_only=True)
    expenses = ProcurementExpenseSerializer(many=True, read_only=True)
    contract = InvestmentContractSerializer(read_only=True)
    terms = ProcurementTermsSerializer(read_only=True)
    receive_batches = ProcurementReceiveBatchSerializer(many=True, read_only=True)
    receive_plan = serializers.SerializerMethodField()
    cost_preview = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'funding_source', 'status', 'opened_at', 'received_at', 'closed_at',
            'supplier', 'supplier_name', 'agreement', 'agreement_label',
            'notes', 'client_request_id',
            'items', 'expenses', 'contract', 'balance', 'terms',
            'receive_batches', 'receive_plan', 'cost_preview',
        ]
        read_only_fields = ['id']

    def get_agreement_label(self, obj):
        if not obj.agreement_id:
            return None
        return f'Инвестдоговор #{obj.agreement_id}'

    def get_receive_plan(self, obj):
        payload = build_workspace_payload(obj)
        return {
            'status': 'READY' if payload['readiness']['receive_ready']['ok'] else 'BLOCKED',
            'message': payload['readiness']['receive_ready']['message'],
            'readiness': payload['readiness'],
            'policy': payload['policy'],
        }

    def get_cost_preview(self, obj):
        payload = build_workspace_payload(obj)
        return {
            'items_total_uzs': payload['summaries']['items_total_uzs'],
            'expenses_total_uzs': payload['summaries']['expenses_total_uzs'],
            'payables_total': payload['summaries']['payables_total'],
            'receive_batches_count': payload['summaries']['receive_batches_count'],
        }


class ContractPartnerInputSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=ContractPartner.Role.choices)
    planned_capital_share = serializers.DecimalField(max_digits=14, decimal_places=2)
    profit_share = serializers.DecimalField(max_digits=7, decimal_places=6, required=False, default='0')


class InvestmentContractInputSerializer(serializers.Serializer):
    mudaraba_ratio = serializers.DecimalField(max_digits=7, decimal_places=6)
    planned_budget = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    partners = ContractPartnerInputSerializer(many=True)


class InvestmentAgreementCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    mudaraba_ratio = serializers.DecimalField(max_digits=7, decimal_places=6, required=False)
    planned_budget = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    investor_partner_id = serializers.IntegerField(required=False)
    investor_planned_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    investor_capital_percent = serializers.DecimalField(max_digits=7, decimal_places=4, required=False)
    investor_profit_percent = serializers.DecimalField(max_digits=7, decimal_places=4, required=False)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    review_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreed_at = serializers.DateTimeField(required=False, allow_null=True)
    offline_agreement_reference = serializers.CharField(max_length=255, required=False, default='', allow_blank=True)
    payout_policy = PayoutPolicyInputSerializer(required=False)
    reconciliation_mode = serializers.ChoiceField(
        choices=InvestmentAgreement.ReconciliationMode.choices, required=False)
    partners = ContractPartnerInputSerializer(many=True, required=False)

    def validate(self, attrs):
        if attrs.get('partners'):
            if 'planned_budget' not in attrs or 'mudaraba_ratio' not in attrs:
                raise serializers.ValidationError({
                    'detail': 'Explicit partners payload requires planned_budget and mudaraba_ratio.',
                })
            return attrs

        required = [
            'investor_partner_id',
            'investor_planned_amount',
            'investor_capital_percent',
            'investor_profit_percent',
        ]
        missing = [field for field in required if attrs.get(field) in (None, '')]
        if missing:
            raise serializers.ValidationError({field: 'This field is required.' for field in missing})

        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None)
        if tenant_id is None:
            raise serializers.ValidationError({'detail': 'Tenant context is required.'})

        operator = Partner.objects.filter(
            tenant_id=tenant_id,
            role=Partner.Role.OPERATOR,
            is_active=True,
        ).first()
        if operator is None:
            raise serializers.ValidationError({'detail': 'Active business operator partner is required.'})

        investor_id = int(attrs['investor_partner_id'])
        if not Partner.objects.filter(
            tenant_id=tenant_id,
            id=investor_id,
            role=Partner.Role.INVESTOR,
            is_active=True,
        ).exists():
            raise serializers.ValidationError({'investor_partner_id': 'Active investor partner is required.'})

        investor_amount = _money(attrs['investor_planned_amount'])
        capital_percent = Decimal(str(attrs['investor_capital_percent']))
        profit_percent = Decimal(str(attrs['investor_profit_percent']))
        if investor_amount <= 0:
            raise serializers.ValidationError({'investor_planned_amount': 'Must be greater than 0.'})
        if capital_percent <= 0 or capital_percent >= 100:
            raise serializers.ValidationError({'investor_capital_percent': 'Must be between 0 and 100.'})
        if profit_percent < 0 or profit_percent > 100:
            raise serializers.ValidationError({'investor_profit_percent': 'Must be between 0 and 100.'})

        investor_capital_share = (capital_percent / Decimal('100')).quantize(Decimal('0.000001'))
        investor_profit_share = (profit_percent / Decimal('100')).quantize(Decimal('0.000001'))
        mudaraba_ratio = (investor_profit_share / investor_capital_share).quantize(Decimal('0.000001'))
        if mudaraba_ratio < 0 or mudaraba_ratio > 1:
            raise serializers.ValidationError({
                'investor_profit_percent': 'Profit formula cannot exceed investor capital ratio in MVP.',
            })

        planned_budget = _money(investor_amount / investor_capital_share)
        operator_amount = _money(planned_budget - investor_amount)
        attrs['planned_budget'] = planned_budget
        attrs['mudaraba_ratio'] = mudaraba_ratio
        attrs['partners'] = [
            {
                'partner_id': investor_id,
                'role': 'INVESTOR',
                'planned_capital_share': investor_amount,
                'profit_share': investor_profit_share,
            },
            {
                'partner_id': operator.id,
                'role': 'OPERATOR',
                'planned_capital_share': operator_amount,
                'profit_share': Decimal('1') - investor_profit_share,
            },
        ]
        return attrs


class AgreementAllocationRowSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class AgreementAllocationCreateSerializer(serializers.Serializer):
    procurement_id = serializers.IntegerField()
    allocations = AgreementAllocationRowSerializer(many=True)


class ProcurementItemInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    product_variant_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_purchase_price = serializers.DecimalField(max_digits=14, decimal_places=6)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)


class ProcurementExpenseInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    expense_type = serializers.ChoiceField(choices=ProcurementExpense.ExpenseType.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    allocation_method = serializers.ChoiceField(
        choices=ProcurementExpense.AllocationMethod.choices,
        required=False,
        default=ProcurementExpense.AllocationMethod.BY_VALUE,
    )
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    target_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class ProcurementItemSplitSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)


class ProcurementExpenseTargetsSerializer(serializers.Serializer):
    expense_id = serializers.IntegerField()
    target_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class PaymentScheduleInputSerializer(serializers.Serializer):
    sequence_number = serializers.IntegerField(required=False)
    due_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)


class ProcurementTermsInputSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=ProcurementTerms.Type.choices)
    currency_of_obligation = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate_at_obligation = serializers.DecimalField(max_digits=16, decimal_places=6, required=False, default='1')
    total_amount_due = serializers.DecimalField(max_digits=16, decimal_places=2)
    deadline_date = serializers.DateField(required=False, allow_null=True)
    consignment_agreement_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ProcurementCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    funding_source = serializers.ChoiceField(choices=Procurement.FundingSource.choices, required=False)
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    agreement_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    contract = InvestmentContractInputSerializer(required=False, allow_null=True)
    items = ProcurementItemInputSerializer(many=True, required=False, default=list)
    expenses = ProcurementExpenseInputSerializer(many=True, required=False, default=list)
    terms = ProcurementTermsInputSerializer(required=False, allow_null=True)
    schedule = PaymentScheduleInputSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if not attrs.get('funding_source'):
            raise serializers.ValidationError({'funding_source': 'This field is required.'})
        return attrs


class AgreementContributionCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    cash_account_id = serializers.IntegerField(required=False, allow_null=True)


class AgreementWithdrawalCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False, allow_null=True)
    procurement_id = serializers.IntegerField(required=False, allow_null=True)
    from_account_id = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    reason = serializers.CharField(required=False, default='', allow_blank=True)
    payout_obligation_id = serializers.IntegerField(required=False, allow_null=True)
    payout_decision_id = serializers.IntegerField(required=False, allow_null=True)


class ReceiveProcurementSerializer(serializers.Serializer):
    destination_warehouse_id = serializers.IntegerField()
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )
    capital_allocations = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )
    # E01 — optional terms / schedule for the procurement
    terms_payload = serializers.DictField(required=False, allow_null=True)
    schedule_payload = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )


class TermsAmendmentSerializer(serializers.Serializer):
    """Payload for POST /procurements/{id}/terms/amend/"""
    new_fields = serializers.DictField()
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class ProcurementTermsAmendmentSerializer(serializers.ModelSerializer):
    changed_by_user_name = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementTermsAmendment
        fields = [
            'id', 'amended_at', 'changed_by_user',
            'changed_by_user_name', 'change_payload', 'reason',
        ]
        read_only_fields = fields

    def get_changed_by_user_name(self, obj):
        user = getattr(obj, 'changed_by_user', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class ConsignmentReturnLineSerializer(serializers.Serializer):
    lot_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    disposition = serializers.ChoiceField(choices=[
        'RETURN_TO_SUPPLIER',
        'DISPOSE_SUPPLIER_LOSS',
        'DISPOSE_BUSINESS_LOSS',
        'CONVERT_TO_OWN',
    ])
    agreed_price_per_unit = serializers.DecimalField(max_digits=14, decimal_places=6)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ConsignmentReturnCreateSerializer(serializers.Serializer):
    """Payload for POST /procurements/{id}/consignment-return/"""
    warehouse_id = serializers.IntegerField()
    lines = ConsignmentReturnLineSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class PayProcurementItemsSerializer(serializers.Serializer):
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    cash_account_id = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class PayProcurementExpensesSerializer(serializers.Serializer):
    expense_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    cash_account_id = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class DividendPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DividendPayment
        fields = [
            'id', 'partner', 'procurement', 'amount', 'currency',
            'fx_rate', 'fx_rate_source', 'fx_rate_date',
            'paid_from_account_id', 'date',
        ]
        read_only_fields = ['id', 'date']


class DividendPaymentCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    procurement_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)
    paid_from_account_id = serializers.IntegerField(required=False, allow_null=True)
    payout_obligation_id = serializers.IntegerField(required=False, allow_null=True)
    payout_decision_id = serializers.IntegerField(required=False, allow_null=True)
