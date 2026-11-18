from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from tracker.models import AuditEvent, PushSubscription
from tests.test_audit import unavailable_audit_storage


class ProviderFailure(Exception):
    def __init__(self, status):
        self.response = SimpleNamespace(status_code=status)
        super().__init__('private provider details must not reach the response')


@override_settings(SECURE_SSL_REDIRECT=False, VAPID_PUBLIC_KEY='fictional-public',
                   VAPID_PRIVATE_KEY='fictional-private', VAPID_SUBJECT='mailto:test@example.com')
class PushTestTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('push-member', password='fictional-test-password')
        self.client.force_login(self.user)

    def device(self, name, user=None):
        return PushSubscription.objects.create(user=user or self.user,
            endpoint=f'https://fcm.googleapis.com/fcm/send/fictional-{name}', keys={})

    def send(self):
        return self.client.post('/api/push/test/', '{}', content_type='application/json')

    @patch('tracker.views.send_push')
    def test_expired_device_does_not_block_working_device_and_cleanup_is_audited(self, send):
        expired, working = self.device('expired'), self.device('working')
        send.side_effect = [ProviderFailure(410), None]
        result = self.send()
        self.assertEqual(result.status_code, 200)
        self.assertEqual((result.json()['accepted'], result.json()['expired'], result.json()['failed']), (1, 1, 0))
        self.assertEqual([call.args[0].endpoint for call in send.call_args_list], [expired.endpoint, working.endpoint])
        self.assertFalse(PushSubscription.objects.filter(pk=expired.pk).exists())
        self.assertTrue(PushSubscription.objects.filter(pk=working.pk).exists())
        event = AuditEvent.objects.get(entity_type='device', action='delete', entity_id=str(expired.pk))
        self.assertEqual(event.actor_name, self.user.username)
        self.assertEqual(event.source, 'app')

    @patch('tracker.views.send_push')
    def test_all_expired_registrations_are_committed_with_an_honest_result(self, send):
        self.device('gone'); self.device('expired')
        send.side_effect = [ProviderFailure(404), ProviderFailure(410)]
        result = self.send()
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()['ok'])
        self.assertEqual(result.json()['expired'], 2)
        self.assertIn('No test notifications were accepted', result.json()['note'])
        self.assertIn('Enable notifications again', result.json()['note'])
        self.assertFalse(PushSubscription.objects.filter(user=self.user).exists())

    @patch('tracker.views.send_push')
    def test_transient_failures_are_retained_and_other_devices_are_attempted(self, send):
        devices = [self.device(name) for name in ('forbidden', 'timeout', 'working')]
        send.side_effect = [ProviderFailure(403), TimeoutError(), None]
        result = self.send().json()
        self.assertEqual((result['accepted'], result['expired'], result['failed']), (1, 0, 2))
        self.assertEqual(send.call_count, 3)
        self.assertEqual(PushSubscription.objects.filter(pk__in=[d.pk for d in devices]).count(), 3)
        self.assertNotIn('private provider details', result['note'])

    @patch('tracker.views.send_push', side_effect=TimeoutError)
    def test_all_failed_is_not_reported_as_accepted(self, send):
        self.device('timeout')
        result = self.send().json()
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed'], 1)
        self.assertIn('No test notifications were accepted', result['note'])

    @patch('tracker.views.send_push')
    def test_other_users_devices_are_neither_sent_to_nor_removed(self, send):
        other = get_user_model().objects.create_user('other-member')
        untouched = self.device('other', other)
        self.device('own')
        self.assertTrue(self.send().json()['ok'])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0].user_id, self.user.pk)
        self.assertTrue(PushSubscription.objects.filter(pk=untouched.pk).exists())

    @patch('tracker.views.send_push', side_effect=ProviderFailure(410))
    def test_cleanup_rolls_back_when_its_audit_cannot_be_written(self, send):
        device = self.device('audit-failure')
        before = AuditEvent.objects.count()
        with unavailable_audit_storage():
            self.assertEqual(self.send().status_code, 409)
        self.assertTrue(PushSubscription.objects.filter(pk=device.pk).exists())
        self.assertEqual(AuditEvent.objects.count(), before)

    @patch('tracker.views.send_push')
    def test_authentication_and_csrf_are_required(self, send):
        self.device('protected')
        self.assertEqual(Client().post('/api/push/test/', '{}', content_type='application/json').status_code, 401)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/api/push/test/', '{}', content_type='application/json').status_code, 403)
        send.assert_not_called()

    @patch('tracker.views.send_push')
    def test_no_registrations_requests_enrollment(self, send):
        self.assertEqual(self.send().status_code, 409)
        send.assert_not_called()
