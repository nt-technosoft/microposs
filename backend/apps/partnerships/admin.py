from django.contrib import admin

from .models import (
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


@admin.register(Procurement)
class ProcurementAdmin(admin.ModelAdmin):
    list_display = ('id', 'procurement_type', 'status', 'supplier', 'opened_at')
    list_filter = ('procurement_type', 'status')
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
