from django.db import migrations
from ._audit_v1 import install, uninstall


class Migration(migrations.Migration):
    dependencies = [('tracker', '0002_auditcontext_auditevent')]
    operations = [migrations.RunPython(install, uninstall)]
