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
    ProcurementBalance, BalanceContribution, BalanceWithdrawal,
    ProcurementPartnerLedger, PartnerLedgerEntry, DividendPayment,
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


class BalanceContributionInline(admin.TabularInline):
    model = BalanceContribution
    extra = 0


class BalanceWithdrawalInline(admin.TabularInline):
    model = BalanceWithdrawal
    extra = 0


@admin.register(ProcurementBalance)
class ProcurementBalanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'procurement', 'balances')
    inlines = [BalanceContributionInline, BalanceWithdrawalInline]


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
