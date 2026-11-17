from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    family_name = models.CharField(max_length=80, default='Our family')
    server_url = models.URLField(blank=True)
    nas_name = models.CharField(max_length=80, default='Family NAS')


class Loan(models.Model):
    title = models.CharField(max_length=100)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    installments = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Recurrence(models.Model):
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=40, default='Household')
    next_due = models.DateField()
    anchor_day = models.PositiveSmallIntegerField()
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')


class Bill(models.Model):
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    category = models.CharField(max_length=40, default='Household')
    notes = models.CharField(max_length=500, blank=True)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assigned_bills')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_bills')
    loan = models.ForeignKey(Loan, null=True, blank=True, on_delete=models.PROTECT, related_name='bills')
    recurrence = models.ForeignKey(Recurrence, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='bill_positive_amount'), models.UniqueConstraint(fields=['recurrence', 'due_date'], name='unique_recurring_occurrence')]

    @property
    def paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal('0.00'))

    @property
    def balance(self):
        return Decimal(self.amount) - self.paid


class Payment(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_date = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    request_key = models.UUIDField(unique=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='payment_positive_amount')]


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=30, primary_key=True)
    updated_at = models.DateTimeField(default=timezone.now)
    detail = models.CharField(max_length=120, default='Starting')


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=1500, unique=True)
    keys = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class ReminderDelivery(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE)
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE)
    day = models.DateField()
    delivered_at = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['bill', 'subscription', 'day'], name='unique_daily_reminder')]


class LoginFailure(models.Model):
    key = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
