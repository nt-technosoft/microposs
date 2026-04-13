from django.contrib import admin
from .models import Supplier, SupplierPayment, ConsignmentAgreement


class SupplierPaymentInline(admin.TabularInline):
    model = SupplierPayment
    extra = 0
    readonly_fields = ('amount', 'payment_method', 'date')


class ConsignmentAgreementInline(admin.TabularInline):
    model = ConsignmentAgreement
    extra = 0


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'contact_person', 'phone', 'outstanding_balance', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact_person', 'phone')
    inlines = [SupplierPaymentInline, ConsignmentAgreementInline]


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'amount', 'payment_method', 'date')
    list_filter = ('payment_method',)


@admin.register(ConsignmentAgreement)
class ConsignmentAgreementAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'rule_type', 'rule_value', 'is_active')
    list_filter = ('rule_type', 'is_active')
