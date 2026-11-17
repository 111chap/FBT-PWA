from django.contrib import admin
from .models import Bill, Payment, Loan, Recurrence


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (Bill, Payment, Loan, Recurrence):
    admin.site.register(model, ReadOnlyAdmin)
admin.site.site_header = 'Family Bill Tracker · Administration'
