from django.contrib import admin
from .models import Bill, Payment, Loan, Recurrence, AuditEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (Bill, Payment, Loan, Recurrence):
    admin.site.register(model, ReadOnlyAdmin)


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyAdmin):
    list_display = ('occurred_at', 'actor_name', 'action', 'entity_type', 'label', 'source', 'transaction_id')
    list_filter = ('entity_type', 'action', 'source')
    search_fields = ('actor_name', 'label', 'transaction_id', 'entity_id')
    date_hierarchy = 'occurred_at'


admin.site.site_header = 'Family Bill Tracker · Administration'
