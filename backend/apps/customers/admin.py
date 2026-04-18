from django.contrib import admin
from .models import Customer, CustomerPayment, Receivable, ReceivableEntry


class CustomerPaymentInline(admin.TabularInline):
    model = CustomerPayment
    extra = 0
    readonly_fields = ('amount', 'currency', 'payment_method', 'date')


class ReceivableEntryInline(admin.TabularInline):
    model = ReceivableEntry
    extra = 0
    readonly_fields = ('date', 'amount', 'currency', 'fx_rate', 'entry_type', 'source_ref')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'phone')
    inlines = [CustomerPaymentInline]


@admin.register(Receivable)
class ReceivableAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'balances')
    inlines = [ReceivableEntryInline]


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'amount', 'currency', 'payment_method', 'date')
    list_filter = ('payment_method', 'currency')
