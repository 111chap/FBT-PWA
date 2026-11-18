from django.db import migrations, models
from . import _audit_v2, _audit_v3
from django.db.migrations.exceptions import IrreversibleError


def safe_uninstall(apps,schema_editor):
    alias=schema_editor.connection.alias
    if (apps.get_model('tracker','Loan').objects.using(alias).filter(removed=True).exists()
        or apps.get_model('tracker','Payment').objects.using(alias).filter(removed=True).exists()
        or apps.get_model('tracker','AuditEvent').objects.using(alias).exclude(reason='').exists()):
        raise IrreversibleError('Corrections exist. Restore the complete pre-upgrade backup instead of removing correction fields.')
    _audit_v3.uninstall(apps,schema_editor)


class Migration(migrations.Migration):
    dependencies=[('tracker','0004_family_workflows')]
    operations=[
        migrations.RunPython(_audit_v2.uninstall,_audit_v2.install),
        migrations.AddField('loan','removed',models.BooleanField(default=False)),
        migrations.AddField('payment','removed',models.BooleanField(default=False)),
        migrations.AddField('auditcontext','reason',models.CharField(max_length=500,blank=True,default='')),
        migrations.AddField('auditevent','reason',models.CharField(max_length=500,blank=True,default='')),
        migrations.RunPython(_audit_v3.install,safe_uninstall),
    ]
