from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.core import signing
from django.http import HttpResponse
from .versions import version
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


class ReviewAdminMixin:
    change_form_template = 'admin/family_change_form.html'
    delete_confirmation_template = 'admin/family_delete_confirmation.html'
    change_user_password_template = 'admin/family_password.html'
    actions = None  # Avoid bulk account removal without an individual review.

    class Media:
        js = ('review.js', 'admin-review.js')
        css = {'all': ('review.css',)}

    def record_version(self, request, object_id):
        obj = self.get_object(request, str(object_id)) if object_id else None
        if not obj:
            return None
        values = list(type(obj).objects.filter(pk=obj.pk).values())
        for relation in obj._meta.many_to_many:
            values.append(list(getattr(obj, relation.name).order_by('pk').values_list('pk', flat=True)))
        return [request.user.pk, request.path, version(values)]

    def check_version(self, request, object_id):
        if request.method != 'POST' or not object_id:
            return True
        self.model.objects.select_for_update().filter(pk=object_id).first()
        try:
            return signing.loads(request.POST.get('_record_version', ''), salt='admin-review', max_age=900) == self.record_version(request, object_id)
        except signing.BadSignature:
            return False

    def version_context(self, request, object_id, extra_context):
        return {**(extra_context or {}), 'record_version': signing.dumps(self.record_version(request, object_id), salt='admin-review')}

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if not self.check_version(request, object_id):
            return HttpResponse('This account or permission record changed, or the review expired. Reload and review again.', status=409)
        return super().changeform_view(request, object_id, form_url, self.version_context(request, object_id, extra_context))

    def user_change_password(self, request, id, form_url=''):
        if not self.check_version(request, id):
            return HttpResponse('This account changed, or the review expired. Reload and review again.', status=409)
        response = super().user_change_password(request, id, form_url)
        if hasattr(response, 'context_data'):
            response.context_data.update(self.version_context(request, id, None))
        return response

    def delete_view(self, request, object_id, extra_context=None):
        if not self.check_version(request, object_id):
            return HttpResponse('This record changed, or the deletion review expired. Reload and review again.', status=409)
        return super().delete_view(request, object_id, self.version_context(request, object_id, extra_context))


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class FamilyUserAdmin(ReviewAdminMixin, UserAdmin):
    pass


admin.site.unregister(Group)


@admin.register(Group)
class FamilyGroupAdmin(ReviewAdminMixin, GroupAdmin):
    pass
