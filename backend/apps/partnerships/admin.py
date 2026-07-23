from django.contrib import admin

from .models import (
    AgreementAllocation,
    AgreementContribution,
    AgreementEvent,
    AgreementPartner,
    AgreementWithdrawal,
    CapitalCommitment,
    InvestmentAgreement,
    Procurement, ProcurementItem, ProcurementExpense,
    InvestmentContract, ContractPartner,
    ProcurementPartnerLedger, PartnerLedgerEntry, DividendPayment,
    AgreementTermsVersion, InvestmentFund, FundTermsVersion, FundMember,
    FundContribution, FundDeployment, FundMemberPositionReadModel,
    FundPositionReadModel, PayoutPolicy, PayoutObligation, ContractReview,
    DisputeCase,
)


class ProcurementItemInline(admin.TabularInline):
    model = ProcurementItem
    extra = 0


class ProcurementExpenseInline(admin.TabularInline):
    model = ProcurementExpense
    extra = 0


class AgreementPartnerInline(admin.TabularInline):
    model = AgreementPartner
    extra = 0


class FundMemberInline(admin.TabularInline):
    model = FundMember
    extra = 0
    readonly_fields = ('joined_at', 'offline_agreed_at', 'offline_agreement_reference')


class FundContributionInline(admin.TabularInline):
    model = FundContribution
    extra = 0
    readonly_fields = ('date', 'amount', 'currency', 'fx_rate', 'notes')


class FundDeploymentInline(admin.TabularInline):
    model = FundDeployment
    extra = 0
    readonly_fields = ('agreement', 'agreement_contribution', 'amount', 'currency', 'date', 'notes')


class CapitalCommitmentInline(admin.TabularInline):
    model = CapitalCommitment
    extra = 0
    readonly_fields = ('date',)


class AgreementContributionInline(admin.TabularInline):
    model = AgreementContribution
    extra = 0
    readonly_fields = ('date',)


class AgreementAllocationInline(admin.TabularInline):
    model = AgreementAllocation
    extra = 0
    readonly_fields = ('date',)


@admin.register(InvestmentAgreement)
class InvestmentAgreementAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'planned_budget', 'currency', 'opened_at')
    list_filter = ('status', 'currency')
    inlines = [
        AgreementPartnerInline,
        CapitalCommitmentInline,
        AgreementContributionInline,
        AgreementAllocationInline,
    ]


@admin.register(InvestmentFund)
class InvestmentFundAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', 'currency', 'manager_partner', 'opened_at')
    list_filter = ('status', 'currency')
    inlines = [FundMemberInline, FundContributionInline, FundDeploymentInline]


@admin.register(AgreementTermsVersion, FundTermsVersion, PayoutPolicy, PayoutObligation, ContractReview, DisputeCase)
class LifecycleAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FundMemberPositionReadModel)
class FundMemberPositionReadModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'fund', 'computed_at')
    readonly_fields = [field.name for field in FundMemberPositionReadModel._meta.fields]


@admin.register(FundPositionReadModel)
class FundPositionReadModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'fund', 'computed_at')
    readonly_fields = [field.name for field in FundPositionReadModel._meta.fields]


@admin.register(Procurement)
class ProcurementAdmin(admin.ModelAdmin):
    list_display = ('id', 'funding_source', 'status', 'supplier', 'opened_at')
    list_filter = ('funding_source', 'status')
    inlines = [ProcurementItemInline, ProcurementExpenseInline]


class ContractPartnerInline(admin.TabularInline):
    model = ContractPartner
    extra = 0


@admin.register(InvestmentContract)
class InvestmentContractAdmin(admin.ModelAdmin):
    list_display = ('id', 'procurement', 'mudaraba_ratio', 'planned_budget', 'currency')
    inlines = [ContractPartnerInline]


class PartnerLedgerEntryInline(admin.TabularInline):
    model = PartnerLedgerEntry
    extra = 0
    readonly_fields = ('date', 'amount', 'currency', 'entry_type', 'source_ref')


@admin.register(ProcurementPartnerLedger)
class ProcurementPartnerLedgerAdmin(admin.ModelAdmin):
    list_display = ('id', 'procurement', 'partner')
    inlines = [PartnerLedgerEntryInline]


@admin.register(DividendPayment)
class DividendPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'partner', 'procurement', 'amount', 'currency', 'date')
    list_filter = ('currency',)


@admin.register(AgreementWithdrawal)
class AgreementWithdrawalAdmin(admin.ModelAdmin):
    list_display = ('id', 'agreement', 'partner', 'amount', 'currency', 'date')
    list_filter = ('currency', 'confirmation_status', 'source')


@admin.register(AgreementEvent)
class AgreementEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'agreement', 'event_type', 'source', 'occurred_at')
    list_filter = ('event_type', 'source')
    readonly_fields = (
        'agreement', 'event_type', 'occurred_at',
        'actor_user', 'actor_partner', 'source',
        'related_model', 'related_id', 'payload',
    )
