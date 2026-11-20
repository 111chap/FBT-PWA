"""Authorization, disclosure, credential and transaction regression checks."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from tracker.models import Bill, Loan, Recurrence, Payment, AuditEvent, PrivacyAccess, EmergencyGrant, PinCredential, PinDevice, PushSubscription
from tracker.services import deliver_reminders, materialize_recurring
from tracker.versions import bill_version, loan_version
from tracker.audit import audit_transaction, trigger_status


PASSWORD = 'Fictional-strong-test-password-42!'
PIN = '839274'


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'localhost'])
class PrivacyPinTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('fixture-owner', password=PASSWORD)
        self.member = User.objects.create_user('fixture-member', password=PASSWORD)
        self.admin = User.objects.create_superuser('fixture-admin', password=PASSWORD)
        self.client.force_login(self.owner)
        self.private = Bill.objects.create(title='Private fictional fee', amount='100', due_date=timezone.localdate(), owner=self.owner, visibility='private', created_by=self.owner, responsible=self.owner)
        self.shared = Bill.objects.create(title='Shared fictional fee', amount='100', due_date=timezone.localdate(), owner=self.owner, visibility='family', created_by=self.owner, responsible=self.member)

    def post(self, path, data, **kwargs):
        return self.client.post(path, json.dumps(data), content_type='application/json', **kwargs)

    def pay(self, bill):
        return self.post(f'/api/bills/{bill.pk}/payments/', {'amount':'10', 'paid_date':timezone.localdate().isoformat(), 'request_key':str(uuid.uuid4())})

    def enable_pin(self):
        return self.post('/api/security/pin/', {'action':'enable', 'pin':PIN, 'pin_confirmation':PIN, 'password':PASSWORD, 'confirmed':True}, secure=True)

    def test_normal_member_and_admin_cannot_read_private_snapshots_exports_audits_or_ids(self):
        for user in (self.member, self.admin):
            self.client.force_login(user)
            snapshot = self.client.get('/api/snapshot/').json()
            self.assertEqual([b['id'] for b in snapshot['bills']], [self.shared.pk])
            self.assertNotIn('Private fictional', self.client.get('/api/export/').content.decode())
            self.assertEqual(self.pay(self.private).status_code, 404)
            self.assertEqual(self.post(f'/api/manage/bill/{self.private.pk}/', {'action':'delete','confirmed':True,'reason':'Fixture correction','expected_version':bill_version(self.private),'request_key':str(uuid.uuid4())}).status_code,404)
            if user.is_superuser:
                self.assertNotIn('Private fictional', self.client.get('/api/audit/').content.decode())
                self.assertNotIn('Private fictional', self.client.get('/admin/tracker/bill/').content.decode())
                self.assertNotEqual(self.client.get(f'/admin/tracker/bill/{self.private.pk}/change/').status_code,200)

    def test_owner_manages_private_bill_but_member_cannot_correct_family_bill(self):
        response=self.post(f'/api/manage/bill/{self.private.pk}/', {'action':'edit','confirmed':True,'reason':'Fixture amount correction','expected_version':bill_version(self.private),'request_key':str(uuid.uuid4()),'title':self.private.title,'amount':'110','due_date':self.private.due_date.isoformat(),'category':self.private.category,'notes':'Owner correction','responsible':self.owner.pk})
        self.assertEqual(response.status_code,200,response.content)
        self.client.force_login(self.member)
        response=self.post(f'/api/manage/bill/{self.shared.pk}/', {'action':'delete','confirmed':True,'reason':'Not allowed','expected_version':bill_version(self.shared),'request_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,403)

    def test_linked_private_parent_cannot_be_exposed_by_shared_child(self):
        loan=Loan.objects.create(title='Hidden agreement',total='50',installments=1,created_by=self.owner,owner=self.owner,visibility='private')
        child=Bill.objects.create(title='Inconsistent import',amount='50',due_date=timezone.localdate(),created_by=self.owner,responsible=self.owner,owner=self.owner,visibility='family',loan=loan)
        self.client.force_login(self.admin)
        value=self.client.get('/api/snapshot/').json()
        self.assertNotIn(child.pk,[b['id'] for b in value['bills']])
        self.assertEqual(value['loans'],[])
        self.assertEqual(self.pay(child).status_code,404)

    def test_emergency_requires_password_reason_confirmation_and_is_read_only(self):
        self.assertEqual(self.post('/api/privacy/emergency/',{'reason':'Fixture emergency','password':PASSWORD,'confirmed':True}).status_code,403)
        self.client.force_login(self.admin)
        self.assertFalse(self.post('/api/privacy/emergency/',{'reason':'Fixture emergency','password':'incorrect','confirmed':True}).json()['ok'])
        self.assertEqual(self.post('/api/privacy/emergency/',{'reason':'Fixture emergency','password':PASSWORD}).status_code,400)
        response=self.post('/api/privacy/emergency/',{'reason':'Fixture emergency','password':PASSWORD,'confirmed':True})
        self.assertTrue(response.json()['ok'],response.content)
        value=self.client.get('/api/privacy/emergency/records/').json()
        self.assertFalse(value['offline_safe'])
        self.assertTrue(value['emergency'])
        self.assertIn(self.private.pk,[b['id'] for b in value['bills']])
        self.assertTrue(all(not b['can_manage'] for b in value['bills']))
        self.assertEqual(self.pay(self.private).status_code,403)
        self.assertEqual(self.pay(self.shared).status_code,403)
        self.assertNotIn(self.private.pk,[b['id'] for b in self.client.get('/api/snapshot/').json()['bills']])
        self.post('/api/privacy/emergency/',{'action':'exit'})
        self.assertEqual(self.client.get('/api/privacy/emergency/records/').status_code,403)
        self.client.force_login(self.owner)
        events=self.client.get('/api/privacy/access/').json()['events']
        self.assertTrue({'activated','viewed','deactivated'}.issubset({e['action'] for e in events}))
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/api/privacy/access/').json()['events'],[])

    def test_emergency_expiry_is_logged_and_not_enabled_in_another_session(self):
        self.client.force_login(self.admin)
        self.post('/api/privacy/emergency/',{'reason':'Fixture emergency','password':PASSWORD,'confirmed':True})
        another=Client();another.force_login(self.admin)
        self.assertEqual(another.get('/api/privacy/emergency/records/').status_code,403)
        EmergencyGrant.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.get('/api/privacy/emergency/records/').status_code,403)
        self.assertTrue(PrivacyAccess.objects.filter(owner=self.owner,action='expired').exists())

    def test_sharing_requires_owner_explicit_confirmation_and_updates_parent_children(self):
        payload={'kind':'bill','id':self.private.pk,'visibility':'family','reason':'Owner sharing','expected_version':bill_version(self.private)}
        self.assertEqual(self.post('/api/privacy/visibility/',payload).status_code,400)
        payload['confirmed']=True
        self.assertEqual(self.post('/api/privacy/visibility/',payload).status_code,200)
        self.private.refresh_from_db();self.assertEqual(self.private.visibility,'family')
        self.client.force_login(self.admin)
        self.assertEqual(self.post('/api/privacy/visibility/',{**payload,'visibility':'private','expected_version':bill_version(self.private)}).status_code,403)
        # Earlier private audit contents do not become exposed after sharing.
        self.assertFalse(any(e.get('after',{}).get('visibility')=='private' for e in self.client.get('/api/audit/').json()['events'] if e.get('after')))

    def test_new_defaults_private_legacy_family_and_one_time_partial_payments(self):
        payload={'title':'One-time fictional repair','amount':'80','due_date':timezone.localdate().isoformat(),'bill_type':'one-time','notes':'Fixture note'}
        response=self.post('/api/bills/',payload);self.assertEqual(response.status_code,201,response.content)
        bill=Bill.objects.get(pk=response.json()['id'])
        self.assertEqual((bill.visibility,bill.owner_id,bill.bill_type,bill.recurrence_id),('private',self.owner.pk,'one-time',None))
        self.assertEqual(self.pay(bill).status_code,201)
        self.assertEqual(str(bill.balance),'70.00')
        self.assertEqual(self.shared.visibility,'family')
        self.assertIn('One-time bill',self.client.get('/api/export/').content.decode())
        self.assertEqual(self.post('/api/bills/',{**payload,'repeat_monthly':True}).status_code,400)
        self.assertEqual(self.post('/api/bills/',{**payload,'bill_type':'loan'}).status_code,400)
        self.assertEqual(self.post('/api/bills/',{**payload,'responsible':self.member.pk}).status_code,400)

    def test_loan_creation_and_recurrence_inherit_owner_and_visibility(self):
        response=self.post('/api/loans/',{'title':'Private installment fixture','total':'90','installments':3,'first_due':timezone.localdate().isoformat()})
        self.assertEqual(response.status_code,201,response.content)
        loan=Loan.objects.get(pk=response.json()['id'])
        self.assertTrue(all(b.owner_id==self.owner.pk and b.visibility=='private' and b.bill_type=='loan' for b in loan.bills.all()))
        recurrence=Recurrence.objects.create(title='Private schedule',amount='30',next_due=timezone.localdate(),anchor_day=timezone.localdate().day,responsible=self.owner,created_by=self.owner,owner=self.owner,visibility='private')
        materialize_recurring()
        self.assertTrue(all(b.owner_id==self.owner.pk and b.visibility=='private' for b in Bill.objects.filter(recurrence=recurrence)))

    @patch('tracker.services.push_ready',return_value=True)
    @patch('tracker.services.send_push')
    def test_reminders_only_send_private_records_to_owner(self,send,ready):
        for user in (self.owner,self.member,self.admin):
            PushSubscription.objects.create(user=user,endpoint=f'https://fcm.googleapis.com/fcm/send/fixture-{user.pk}',keys={'auth':'fixture','p256dh':'fixture'})
        deliver_reminders(timezone.localtime().replace(hour=10,minute=0))
        # One private reminder to owner and one family reminder to each member.
        self.assertEqual(send.call_count,4)
        self.assertEqual(sum(call.args[0].user_id==self.owner.pk for call in send.call_args_list),2)
        self.assertTrue(all('Private fictional' not in str(call) for call in send.call_args_list))

    def test_pin_is_opt_in_hashed_secure_cookie_and_password_unchanged(self):
        self.assertFalse(PinCredential.objects.exists())
        password_hash=self.owner.password
        response=self.enable_pin();self.assertEqual(response.status_code,200,response.content);self.assertTrue(response.json()['ok'])
        credential=PinCredential.objects.get(user=self.owner)
        self.assertNotEqual(credential.pin_hash,PIN);self.assertTrue(check_password(PIN,credential.pin_hash))
        self.owner.refresh_from_db();self.assertEqual(password_hash,self.owner.password)
        cookie=response.cookies['fbt_pin_device']
        self.assertTrue(cookie['secure']);self.assertTrue(cookie['httponly']);self.assertEqual(cookie['samesite'],'Strict')
        self.assertNotEqual(PinDevice.objects.get().verifier,cookie.value)
        self.assertNotIn(PIN,json.dumps(list(AuditEvent.objects.values('before','after','label'))))
        self.assertNotIn(credential.pin_hash,str(list(AuditEvent.objects.values())))

    def test_pin_login_requires_device_and_rotates_session(self):
        response=self.client.post('/login/pin/',{'pin':PIN},secure=True)
        self.assertEqual(response.status_code,200)
        self.enable_pin()
        self.post('/logout/',{})
        session_before=self.client.session.session_key
        response=self.client.post('/login/pin/',{'pin':PIN},secure=True)
        self.assertEqual(response.status_code,302,response.content)
        self.assertNotEqual(self.client.session.session_key,session_before)
        self.assertEqual(int(self.client.session['_auth_user_id']),self.owner.pk)
        stranger=Client();self.assertEqual(stranger.post('/login/pin/',{'pin':PIN},secure=True).status_code,200)
        self.assertNotIn('_auth_user_id',stranger.session)

    def test_pin_failed_attempts_commit_and_cannot_bypass_by_changing_ip(self):
        self.enable_pin();self.post('/logout/',{})
        for index in range(5):
            self.client.post('/login/pin/',{'pin':'482975'},secure=True,REMOTE_ADDR=f'192.0.2.{index}')
        credential=PinCredential.objects.get(user=self.owner)
        self.assertGreater(credential.blocked_until,timezone.now())
        self.client.post('/login/pin/',{'pin':PIN},secure=True,REMOTE_ADDR='192.0.2.100')
        self.assertNotIn('_auth_user_id',self.client.session)
        # Password fallback remains usable during PIN cooldown.
        self.assertEqual(self.client.post('/login/',{'username':self.owner.username,'password':PASSWORD},secure=True).status_code,302)

    def test_pin_reset_disable_revocation_password_change_and_disabled_account(self):
        for action in ('revoke','disable'):
            self.enable_pin()
            response=self.post('/api/security/pin/',{'action':action,'password':PASSWORD,'confirmed':True},secure=True)
            self.assertTrue(response.json()['ok'])
            self.assertFalse(PinDevice.objects.filter(revoked=False).exists())
        self.enable_pin()
        self.owner.set_password('Another-fictional-passphrase-42!');self.owner.save()
        self.client.post('/logout/')
        self.client.post('/login/pin/',{'pin':PIN},secure=True)
        self.assertNotIn('_auth_user_id',self.client.session)
        self.owner.is_active=False;self.owner.save()
        self.client.post('/login/pin/',{'pin':PIN},secure=True)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_pin_enrollment_requires_password_confirmation_csrf_and_strong_pin(self):
        for data in ({'pin':'123456','pin_confirmation':'123456'}, {'pin':'839274','pin_confirmation':'839275'}, {'pin':'839274','pin_confirmation':'839274','confirmed':False}):
            response=self.post('/api/security/pin/',{'action':'enable','password':PASSWORD,'confirmed':True,**data},secure=True)
            self.assertEqual(response.status_code,400)
        self.assertFalse(self.post('/api/security/pin/',{'action':'disable','password':'incorrect','confirmed':True},secure=True).json()['ok'])
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.owner)
        self.assertEqual(csrf.post('/api/security/pin/',{},secure=True).status_code,403)
        self.assertFalse(PinDevice.objects.exists())

    def test_security_writes_and_audits_roll_back_together(self):
        count=AuditEvent.objects.count()
        with self.assertRaises(RuntimeError):
            with audit_transaction(self.owner):
                PinDevice.objects.create(user=self.owner,verifier='a'*64,password_stamp='b'*64,expires_at=timezone.now()+timedelta(days=1))
                raise RuntimeError('Fixture rollback')
        self.assertFalse(PinDevice.objects.exists())
        self.assertEqual(AuditEvent.objects.count(),count)
        self.assertEqual(trigger_status()['state'],'healthy')

    def test_account_switch_updates_offline_scope_before_snapshot(self):
        response=self.client.post('/login/',{'username':self.member.username,'password':PASSWORD},secure=True)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.cookies['fbt_account_scope'].value,str(self.member.pk))
        self.assertEqual(self.client.get('/api/snapshot/').cookies['fbt_account_scope'].value,str(self.member.pk))

    def test_shared_parent_does_not_leak_private_child_total(self):
        loan=Loan.objects.create(title='Malformed shared parent',total='50',installments=1,created_by=self.owner,owner=self.owner,visibility='family')
        self.private.loan=loan;self.private.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/api/snapshot/').json()['loans'],[])
