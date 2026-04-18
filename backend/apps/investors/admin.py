from django.contrib import admin
from .models import Investor, InvestorContract


class InvestorContractInline(admin.TabularInline):
    model = InvestorContract
    extra = 0
    readonly_fields = ('contract_type', 'status', 'start_date', 'closed_at')


@admin.register(Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'email', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'phone')
    inlines = [InvestorContractInline]


@admin.register(InvestorContract)
class InvestorContractAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'investor', 'contract_type',
        'default_profit_ratio', 'status',
        'start_date', 'closed_at',
    )
    list_filter = ('contract_type', 'status')
    readonly_fields = ('closed_at', 'final_settlement')
