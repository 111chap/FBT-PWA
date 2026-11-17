from django.contrib import admin
from django.urls import path
from tracker import views

urlpatterns = [
    path('', views.home), path('app/', views.shell),
    path('login/', views.login_view), path('logout/', views.logout_view),
    path('setup/', views.bootstrap), path('setup-guide/', views.setup_guide),
    path('admin/', admin.site.urls), path('sw.js', views.service_worker),
    path('health/live/', views.liveness), path('api/reachable/', views.reachable),
    path('api/snapshot/', views.snapshot), path('api/bills/', views.create_bill),
    path('api/bills/<int:bill_id>/payments/', views.record_payment),
    path('api/loans/', views.create_loan), path('api/status/', views.status),
    path('api/settings/', views.update_settings), path('api/export/', views.export_bills),
    path('api/push/', views.push_subscription), path('api/push/test/', views.test_push),
    path('api/audit/', views.audit_history),
    path('api/recurrences/<int:recurrence_id>/action/', views.recurrence_action),
    path('api/bills/<int:bill_id>/remove/', views.remove_bill),
    path('api/bills/<int:bill_id>/payer/', views.reassign_payer),
]
