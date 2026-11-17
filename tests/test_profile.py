from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from tracker.models import AuditEvent


@override_settings(SECURE_SSL_REDIRECT=False)
class ProfileIsolationTests(TestCase):
    def test_snapshot_only_exposes_current_account_identity(self):
        User=get_user_model()
        admin=User.objects.create_superuser('private-admin',email='private@example.test',password='Fictional-passphrase-123!')
        member=User.objects.create_user('family-member',password='Fictional-passphrase-456!')
        self.client.force_login(member)
        before=AuditEvent.objects.count()
        response=self.client.get(f'/api/snapshot/?user_id={admin.pk}')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['user'],{'id':member.pk,'name':member.username,'admin':False})
        self.assertNotContains(response,admin.email)
        self.assertNotContains(response,'password')
        self.assertEqual(AuditEvent.objects.count(),before)

    def test_profile_snapshot_requires_live_account(self):
        user=get_user_model().objects.create_user('former-member',password='Fictional-passphrase-456!')
        self.client.force_login(user)
        user.is_active=False;user.save()
        self.assertEqual(self.client.get('/api/snapshot/').status_code,401)
