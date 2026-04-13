from django.contrib import admin
from .models import Business, OutboxEvent


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'owner', 'currency', 'is_active', 'created_at')
    list_filter = ('is_active', 'currency')
    search_fields = ('name',)


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'tenant_id', 'processed_at', 'created_at')
    list_filter = ('event_type', 'processed_at')
    readonly_fields = ('event_type', 'payload', 'tenant_id', 'created_at')
