import io
import json
import os
import uuid
from datetime import timedelta, datetime, date
from zoneinfo import ZoneInfo
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from tracker.models import Bill, Loan, Recurrence, Payment, MediaAsset, ReceiptRevision, PaymentQR, AuditEvent, PrivacyAccess, PushSubscription, ReminderDelivery
from tracker.media import path_for, open_verified, cleanup_unused, finalize
from tracker.services import materialize_recurring, deliver_reminders
from tracker.audit import audit_transaction
from tracker.versions import loan_version, recurrence_version, payment_version
from tests.media_helpers import fictional_image, receipt
from tests.test_audit import unavailable_audit_storage

PASSWORD='Fictional-test-passphrase-42!'


@override_settings(SECURE_SSL_REDIRECT=False)
class RemainingFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.admin=User.objects.create_superuser('remaining-admin',password=PASSWORD)
        cls.owner=User.objects.create_user('remaining-owner',password=PASSWORD)
        cls.other=User.objects.create_user('remaining-other',password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.owner)
        self.bill=Bill.objects.create(title='Fictional private repair',amount='100',due_date=timezone.localdate(),owner=self.owner,visibility='private',responsible=self.owner,created_by=self.owner)

    def post(self,path,data):return self.client.post(path,json.dumps(data),content_type='application/json')

    def pay(self,asset=None,key=None,**extra):
        return self.post(f'/api/bills/{self.bill.pk}/payments/',{'amount':'25','paid_date':timezone.localdate().isoformat(),'request_key':key or str(uuid.uuid4()),'receipt_id':str(asset.pk) if asset else '',**extra})

    def upload(self,purpose='receipt',file=None,bill=None):
        return self.client.post('/api/media/upload/',{'purpose':purpose,'bill_id':(bill or self.bill).pk,'image':file or fictional_image()})

    def test_shared_loan_notes_update_paid_existing_installments_without_financial_changes(self):
        loan=Loan.objects.create(title='Historical fictional loan',total='200',installments=2,owner=self.owner,visibility='private',created_by=self.owner)
        children=[Bill.objects.create(title=f'Old installment {i}',amount='100',due_date=date(2026,i,1),notes=f'Individual note {i}',loan=loan,owner=self.owner,visibility='private',created_by=self.owner,responsible=self.owner) for i in (1,2)]
        for b in children:Payment.objects.create(receipt_required=False,bill=b,amount='100',paid_date=b.due_date,recorded_by=self.owner,request_key=uuid.uuid4())
        loan.refresh_from_db()
        before=list(Bill.objects.filter(loan=loan).values('id','amount','due_date','notes','responsible_id','owner_id'))
        for note in ('Shared\n<script>text only</script>','Updated shared note',''):
            response=self.post(f'/api/descriptions/loan/{loan.pk}/',{'description':note,'reason':'Fictional text correction','confirmed':True,'expected_version':loan_version(loan,loan.bills.filter(removed=False))})
            self.assertEqual(response.status_code,200,response.content);loan.refresh_from_db()
            values=[b for b in self.client.get('/api/snapshot/').json()['bills'] if b['loan_id']==loan.pk]
            self.assertEqual([b['shared_description'] for b in values],[note,note])
            self.assertEqual([b['notes'] for b in values],['Individual note 1','Individual note 2'])
            self.assertTrue(all(b['balance']=='0.00' for b in values))
        self.assertEqual(list(Bill.objects.filter(loan=loan).values('id','amount','due_date','notes','responsible_id','owner_id')),before)
        self.assertEqual(Payment.objects.count(),2)
        self.assertEqual(AuditEvent.objects.filter(reason='Fictional text correction').count(),3)

    def test_new_loan_and_recurring_notes_are_parent_values_and_remain_current(self):
        result=self.post('/api/loans/',{'title':'Fictional notes loan','total':'100','installments':2,'first_due':'2027-01-31','notes':'Shared loan note'})
        self.assertEqual(result.status_code,201,result.content)
        loan=Loan.objects.get(pk=result.json()['id']);self.assertEqual(loan.description,'Shared loan note')
        self.assertTrue(all(b.notes=='' for b in loan.bills.all()))
        result=self.post('/api/bills/',{'title':'Fictional service','amount':'50','due_date':timezone.localdate().isoformat(),'repeat_monthly':True,'notes':'Shared recurring note'})
        schedule=Recurrence.objects.get();self.assertEqual(schedule.description,'Shared recurring note')
        materialize_recurring(timezone.localdate()+timedelta(days=35))
        schedule.refresh_from_db()
        before=list(Bill.objects.filter(recurrence=schedule).values_list('pk','amount','due_date','notes'))
        result=self.post(f'/api/descriptions/recurrence/{schedule.pk}/',{'description':'Current revised note','reason':'Fictional note update','confirmed':True,'expected_version':recurrence_version(schedule)})
        self.assertEqual(result.status_code,200,result.content)
        snapshot=self.client.get('/api/snapshot/').json()
        self.assertTrue(all(b['shared_description']=='Current revised note' for b in snapshot['bills'] if b['recurrence_id']==schedule.pk))
        self.assertEqual(list(Bill.objects.filter(recurrence=schedule).values_list('pk','amount','due_date','notes')),before)

    def test_description_permission_stale_review_and_audit_failure(self):
        loan=Loan.objects.create(title='Fictional protected loan',total='10',installments=1,owner=self.owner,visibility='private',created_by=self.owner)
        payload={'description':'Must not save','reason':'Fixture','confirmed':True,'expected_version':loan_version(loan,[])}
        self.client.force_login(self.admin)
        self.assertEqual(self.post(f'/api/descriptions/loan/{loan.pk}/',payload).status_code,404)
        self.client.force_login(self.owner)
        self.assertEqual(self.post(f'/api/descriptions/loan/{loan.pk}/',{**payload,'confirmed':False}).status_code,400)
        self.assertEqual(self.post(f'/api/descriptions/loan/{loan.pk}/',{**payload,'expected_version':'stale'}).status_code,409)
        with unavailable_audit_storage():
            self.assertEqual(self.post(f'/api/descriptions/loan/{loan.pk}/',payload).status_code,409)
        loan.refresh_from_db();self.assertEqual(loan.description,'')

    def test_missing_evidence_and_false_legacy_flag_do_not_create_payment(self):
        for extra in ({},{'receipt_required':False},{'receipt_id':str(uuid.uuid4())}):
            self.assertEqual(self.pay(**extra).status_code,400)
        self.assertFalse(Payment.objects.exists())
        with self.assertRaises(IntegrityError),transaction.atomic():
            Payment.objects.create(bill=self.bill,amount='1',paid_date=timezone.localdate(),recorded_by=self.owner,request_key=uuid.uuid4())
        with self.assertRaises(IntegrityError),audit_transaction(self.owner):
            Payment.objects.create(receipt_required=False,bill=self.bill,amount='1',paid_date=timezone.localdate(),recorded_by=self.owner,request_key=uuid.uuid4())

    def test_valid_receipt_payment_is_durable_named_idempotent_and_manifest_matches(self):
        result=self.upload();self.assertEqual(result.status_code,201,result.content)
        asset=MediaAsset.objects.get(pk=result.json()['id']);key=str(uuid.uuid4())
        self.assertEqual(self.pay(asset,key).status_code,201)
        asset.refresh_from_db();payment=Payment.objects.get()
        self.assertTrue(asset.finalized);self.assertIn(f'_utilities_payment-{payment.pk}_',asset.storage_name)
        self.assertNotIn(self.owner.username,asset.storage_name);self.assertNotIn(self.bill.title,asset.storage_name)
        with open_verified(asset) as stream:self.assertTrue(stream.read().startswith(b'\x89PNG'))
        self.assertEqual(self.pay(asset,key).status_code,200)
        self.assertEqual(Payment.objects.count(),1);self.assertEqual(ReceiptRevision.objects.count(),1)
        self.assertEqual(self.pay(asset).status_code,400)
        other=receipt(self.bill,self.owner)
        self.assertEqual(self.pay(other,key).status_code,409)
        event=AuditEvent.objects.get(entity_type='payment',action='insert')
        self.assertTrue(AuditEvent.objects.filter(entity_type='evidence',transaction_id=event.transaction_id).exists())
        self.assertNotIn('storage_name',self.client.get('/api/snapshot/').json()['bills'][0]['payments'][0])

    def test_attachment_cannot_cross_bill_or_uploader(self):
        other_bill=Bill.objects.create(title='Fictional other bill',amount='10',due_date=timezone.localdate(),created_by=self.owner,responsible=self.owner)
        self.assertEqual(self.pay(receipt(other_bill,self.owner)).status_code,400)
        self.assertEqual(self.pay(receipt(self.bill,self.other)).status_code,400)

    def test_invalid_disguised_trailing_animated_oversized_and_pixel_bomb_images_are_rejected(self):
        raw=fictional_image().read()
        for content in (b'<svg><script>alert(1)</script></svg>',raw+b'<script>trailing</script>',b'MZ'+b'\x00'*100):
            self.assertEqual(self.upload(file=SimpleUploadedFile('fake.png',content,content_type='image/png')).status_code,400)
        with override_settings(FBT_UPLOAD_MAX_BYTES=20):self.assertEqual(self.upload().status_code,400)
        with override_settings(FBT_IMAGE_MAX_PIXELS=100):self.assertEqual(self.upload().status_code,400)
        output=io.BytesIO();Image.new('RGB',(32,32),'white').save(output,format='PNG',save_all=True,append_images=[Image.new('RGB',(32,32),'black')],duration=100,loop=0)
        self.assertEqual(self.upload(file=SimpleUploadedFile('animated.png',output.getvalue())).status_code,400)
        self.assertFalse(MediaAsset.objects.exists())

    def test_exif_is_removed_and_orientation_corrected(self):
        image=Image.new('RGB',(32,64),'white');exif=Image.Exif();exif[274]=6;exif[270]='Fictional private location metadata'
        output=io.BytesIO();image.save(output,format='JPEG',exif=exif)
        result=self.upload(file=SimpleUploadedFile('rotated.jpg',output.getvalue(),content_type='image/jpeg'))
        self.assertEqual(result.status_code,201,result.content)
        asset=MediaAsset.objects.get(pk=result.json()['id']);self.assertEqual((asset.width,asset.height),(64,32))
        with open_verified(asset) as stream:
            cleaned=Image.open(stream);self.assertEqual(len(cleaned.getexif()),0)

    def test_storage_and_audit_failure_never_commit_a_payment(self):
        asset=receipt(self.bill,self.owner);before=AuditEvent.objects.count()
        with patch('tracker.media.os.link',side_effect=OSError('Fixture disk failure')):
            self.assertEqual(self.pay(asset).status_code,503)
        self.assertFalse(Payment.objects.exists());self.assertFalse(ReceiptRevision.objects.exists());self.assertEqual(AuditEvent.objects.count(),before)
        asset.refresh_from_db();self.assertFalse(asset.finalized)
        with unavailable_audit_storage():self.assertEqual(self.pay(asset).status_code,409)
        self.assertFalse(Payment.objects.exists())
        path_for(asset.storage_name).unlink()
        self.assertEqual(self.pay(asset).status_code,503)

    def test_private_image_and_audit_access_requires_owner_or_logged_emergency(self):
        asset=receipt(self.bill,self.owner);self.assertEqual(self.pay(asset).status_code,201);asset.refresh_from_db()
        url=f'/api/media/{asset.pk}/';payment=Payment.objects.get()
        for user in (self.other,self.admin):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code,404)
            self.assertEqual(self.client.get(f'/api/payments/{payment.pk}/evidence/').status_code,404)
            if user.is_superuser:
                self.assertNotIn(str(asset.pk),self.client.get('/api/audit/').content.decode())
        self.client.force_login(self.admin)
        self.assertTrue(self.post('/api/privacy/emergency/',{'confirmed':True,'password':PASSWORD,'reason':'Fictional receipt review'}).json()['ok'])
        response=self.client.get(url+'?download=1');self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control']);b''.join(response.streaming_content)
        self.assertTrue(PrivacyAccess.objects.filter(owner=self.owner,action='receipt-viewed').exists())
        self.assertEqual(self.post(f'/api/payments/{payment.pk}/evidence/replace/',{}).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(url).status_code,401)

    def test_replacement_and_logical_deletion_retain_all_evidence(self):
        first=receipt(self.bill,self.owner);self.pay(first);payment=Payment.objects.get();first.refresh_from_db()
        second=receipt(self.bill,self.owner)
        result=self.post(f'/api/payments/{payment.pk}/evidence/replace/',{'asset_id':str(second.pk),'reason':'Clearer fictional proof','confirmed':True,'expected_version':payment_version(payment)})
        self.assertEqual(result.status_code,200,result.content);second.refresh_from_db();payment.refresh_from_db()
        self.assertEqual(ReceiptRevision.objects.filter(payment=payment).count(),2)
        self.assertTrue(path_for(first.storage_name).exists());self.assertTrue(path_for(second.storage_name).exists())
        self.assertEqual(str(payment.amount),'25.00')
        payment.removed=True;payment.save(update_fields=['removed'])
        cleanup_unused(timezone.now()+timedelta(days=3))
        self.assertEqual(ReceiptRevision.objects.count(),2)
        self.assertTrue(path_for(first.storage_name).exists());self.assertTrue(path_for(second.storage_name).exists())

    def test_unused_upload_cleanup_retains_referenced_images_and_removes_orphans(self):
        abandoned=receipt(self.bill,self.owner);old=timezone.now()-timedelta(hours=49)
        MediaAsset.objects.filter(pk=abandoned.pk).update(created_at=old)
        os.utime(path_for(abandoned.storage_name),(old.timestamp(),old.timestamp()))
        stray=path_for('stage_fictional-orphan.png');stray.write_bytes(b'fictional orphan');os.utime(stray,(old.timestamp(),old.timestamp()))
        kept=receipt(self.bill,self.owner);self.pay(kept);kept.refresh_from_db()
        cleanup_unused()
        self.assertFalse(MediaAsset.objects.filter(pk=abandoned.pk).exists());self.assertFalse(stray.exists())
        self.assertTrue(path_for(kept.storage_name).exists())

    def test_upload_csrf_quota_and_path_names_are_safe(self):
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.owner)
        self.assertEqual(csrf.post('/api/media/upload/',{'purpose':'receipt','bill_id':self.bill.pk,'image':fictional_image()}).status_code,403)
        with override_settings(FBT_MEDIA_MAX_BYTES=1):self.assertEqual(self.upload().status_code,400)
        result=self.upload(file=fictional_image('../../outside.png'));self.assertEqual(result.status_code,201)
        asset=MediaAsset.objects.get(pk=result.json()['id']);self.assertEqual(Path(asset.storage_name).name,asset.storage_name)

    def test_qr_configuration_permissions_replacement_retention_and_unchanged_balances(self):
        self.assertFalse(self.client.get('/api/payment-qr/').json()['configured'])
        self.assertEqual(self.upload('qr').status_code,403)
        self.client.force_login(self.admin)
        originals=list(Bill.objects.values('pk','amount'));version=self.client.get('/api/payment-qr/').json()['version']
        previous=None
        for recipient in ('Fictional recipient A','Fictional recipient B'):
            uploaded=self.upload('qr');self.assertEqual(uploaded.status_code,201,uploaded.content)
            asset=MediaAsset.objects.get(pk=uploaded.json()['id'])
            result=self.post('/api/payment-qr/configure/',{'action':'replace','recipient':recipient,'asset_id':str(asset.pk),'reason':'Fictional verified QR','confirmed':True,'expected_version':version})
            self.assertEqual(result.status_code,200,result.content)
            current=self.client.get('/api/payment-qr/').json();version=current['version']
            response=self.client.get(current['url']);self.assertEqual(response.status_code,200);b''.join(response.streaming_content)
            if previous:self.assertEqual(self.client.get(previous).status_code,404)
            previous=current['url']
        self.client.force_login(self.other)
        self.assertEqual(self.post('/api/payment-qr/configure/',{'confirmed':True}).status_code,403)
        response=self.client.get(previous+'?download=1');self.assertEqual(response.status_code,200);b''.join(response.streaming_content)
        self.client.force_login(self.admin)
        self.assertEqual(self.post('/api/payment-qr/configure/',{'action':'remove','reason':'Fictional removal','confirmed':True,'expected_version':version}).status_code,200)
        self.assertFalse(self.client.get('/api/payment-qr/').json()['configured'])
        self.assertEqual(self.client.get(previous).status_code,404)
        self.assertEqual(MediaAsset.objects.filter(finalized=True).count(),2)
        self.assertEqual(list(Bill.objects.values('pk','amount')),originals);self.assertFalse(Payment.objects.exists())

    @override_settings(VAPID_PUBLIC_KEY='fixture',VAPID_PRIVATE_KEY='fixture',VAPID_SUBJECT='mailto:fixture@example.test')
    @patch('tracker.services.send_push')
    def test_milestones_and_overdue_daily_schedule_use_manila_dates(self,send):
        now=datetime(2028,2,22,9,tzinfo=ZoneInfo('Asia/Manila'))
        PushSubscription.objects.create(user=self.owner,endpoint='https://fcm.googleapis.com/fcm/send/fictional',keys={})
        for days in (7,6,5,4,3,2,1,0,-1):
            self.bill.due_date=now.date()+timedelta(days=days);self.bill.save(update_fields=['due_date'])
            ReminderDelivery.objects.all().delete();send.reset_mock()
            deliver_reminders(now);deliver_reminders(now)
            self.assertEqual(send.call_count,1 if days in (7,3,1,0,-1) else 0,days)
            if send.called:self.assertNotIn(self.bill.title,str(send.call_args))
        send.reset_mock();deliver_reminders(now.replace(hour=20));send.assert_not_called()

    @override_settings(VAPID_PUBLIC_KEY='fixture',VAPID_PRIVATE_KEY='fixture',VAPID_SUBJECT='mailto:fixture@example.test')
    @patch('tracker.services.send_push')
    def test_cancelled_recurring_obligations_do_not_send(self,send):
        schedule=Recurrence.objects.create(title='Fictional cancelled',amount='100',next_due=timezone.localdate(),anchor_day=1,created_by=self.owner,responsible=self.owner,active=False)
        self.bill.recurrence=schedule;self.bill.save(update_fields=['recurrence'])
        PushSubscription.objects.create(user=self.owner,endpoint='https://fcm.googleapis.com/fcm/send/fictional',keys={})
        deliver_reminders(timezone.localtime().replace(hour=10));send.assert_not_called()

    @override_settings(VAPID_PUBLIC_KEY='fixture',VAPID_PRIVATE_KEY='fixture',VAPID_SUBJECT='mailto:fixture@example.test')
    @patch('tracker.media.cleanup_unused',side_effect=OSError('Fictional storage fault'))
    @patch('tracker.services.send_push')
    def test_cleanup_fault_does_not_roll_back_successful_reminder_delivery(self,send,cleanup):
        from django.core.management import call_command
        PushSubscription.objects.create(user=self.owner,endpoint='https://fcm.googleapis.com/fcm/send/fixture',keys={})
        now=timezone.localtime().replace(hour=10)
        with patch('tracker.services.timezone.now',return_value=now):call_command('reminder_worker',once=True,stderr=io.StringIO())
        self.assertEqual(send.call_count,1)
        self.assertIsNotNone(ReminderDelivery.objects.get().delivered_at)
