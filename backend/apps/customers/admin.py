from django.contrib import admin
from .models import Customer, CustomerPayment


class CustomerPaymentInline(admin.TabularInline):
    model = CustomerPayment
    extra = 0
    readonly_fields = ('amount', 'payment_method', 'date')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'outstanding_balance', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'phone')
    inlines = [CustomerPaymentInline]


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'amount', 'payment_method', 'date')
    list_filter = ('payment_method',)
