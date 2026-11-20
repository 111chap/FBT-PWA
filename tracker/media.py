"""Private, bounded, canonical image storage. Files are durable before DB commit."""
import hashlib
import io
import os
import uuid
import warnings
from datetime import timedelta
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import MediaAsset, WorkerHeartbeat, PaymentQR, ReceiptRevision, Payment


class StorageUnavailable(Exception):
    pass


def normalized_image(upload, purpose="receipt"):
    if upload.size <= 0 or upload.size > settings.FBT_UPLOAD_MAX_BYTES:
        raise ValidationError('Choose an image up to 8 MB (or the configured upload limit).')
    raw = upload.read(settings.FBT_UPLOAD_MAX_BYTES + 1)
    if len(raw) > settings.FBT_UPLOAD_MAX_BYTES:
        raise ValidationError('The image is too large.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            fmt = image.format
            if fmt not in ('JPEG','PNG','WEBP') or getattr(image, 'n_frames', 1) != 1:
                raise ValidationError('Use a still JPEG, PNG or WebP image. SVG, GIF and HEIC are not supported.')
            w, h = image.size
            if w < 16 or h < 16 or max(w,h) > 12000 or w*h > settings.FBT_IMAGE_MAX_PIXELS:
                raise ValidationError('The image dimensions are outside the allowed limits (up to 20 megapixels by default).')
            if (fmt=='JPEG' and not raw.endswith(b'\xff\xd9')) or (fmt=='PNG' and not raw.endswith(b'IEND\xaeB`\x82')) or (fmt=='WEBP' and int.from_bytes(raw[4:8],'little')+8 != len(raw)):
                raise ValidationError('The image contains unexpected trailing data. Export it as a new image first.')
            image.verify()
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            image.load()
            # Preserve pixels/quiet area and strip EXIF, location and text chunks.
            if image.mode in ('RGBA','LA') or 'transparency' in image.info:
                rgba=image.convert('RGBA');clean=Image.new('RGB',rgba.size,'white');clean.paste(rgba,mask=rgba.getchannel('A'))
            else:
                clean=image.convert('RGB')
            clean.info.clear()
            if purpose=='qr':fmt='PNG'
            output=io.BytesIO()
            clean.save(output,format=fmt,**({'quality':95,'subsampling':0} if fmt=='JPEG' else {'lossless':True} if fmt=='WEBP' else {}))
            data=output.getvalue()
            if len(data)>settings.FBT_UPLOAD_MAX_BYTES*2:
                raise ValidationError('The cleaned image is too large. Export a smaller image.')
            return data, {'JPEG':'jpg','PNG':'png','WEBP':'webp'}[fmt], clean.width, clean.height
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValidationError('This file could not be decoded safely as a JPEG, PNG or WebP image.')


def root():
    path=Path(settings.MEDIA_ROOT).resolve()
    path.mkdir(parents=True,exist_ok=True)
    return path


def path_for(name):
    if Path(name).name != name or not name or '/' in name or '\\' in name:
        raise StorageUnavailable('Invalid stored media path.')
    return root()/name


def sync_directory():
    if os.name != 'nt':
        fd=os.open(root(),os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


def open_verified(asset):
    try:
        fd=os.open(path_for(asset.storage_name),os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        stream=os.fdopen(fd,'rb')
        data=stream.read(settings.FBT_UPLOAD_MAX_BYTES*2+1)
        if len(data)!=asset.size or hashlib.sha256(data).hexdigest()!=asset.sha256:
            stream.close()
            raise StorageUnavailable('Evidence verification failed.')
        stream.seek(0)
        return stream
    except OSError:
        raise StorageUnavailable('Private image storage is unavailable.')


def stage(upload, user, purpose, bill=None):
    data,ext,w,h=normalized_image(upload,purpose)
    with transaction.atomic():
        WorkerHeartbeat.objects.get_or_create(name='media-lock')
        WorkerHeartbeat.objects.select_for_update().get(name='media-lock')
        if MediaAsset.objects.filter(uploaded_by=user,created_at__gte=timezone.now()-timedelta(days=1)).count()>=settings.FBT_UPLOADS_PER_DAY or MediaAsset.objects.filter(uploaded_by=user,finalized=False).count()>=settings.FBT_PENDING_UPLOADS:
            raise ValidationError('Upload allowance reached. Retry later; unused uploads are cleaned after 48 hours.')
        try:
            used=sum(p.stat().st_size for p in root().iterdir() if p.is_file())
            if used+len(data)>settings.FBT_MEDIA_MAX_BYTES:
                raise ValidationError('Private image storage is full. Ask the administrator to check the storage limit and NAS space.')
            name=f'stage_{uuid.uuid4().hex}.{ext}'
            fd=os.open(path_for(name),os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'wb') as output:
                output.write(data);output.flush();os.fsync(output.fileno())
            sync_directory()
            return MediaAsset.objects.create(purpose=purpose,bill=bill,uploaded_by=user,storage_name=name,sha256=hashlib.sha256(data).hexdigest(),size=len(data),width=w,height=h)
        except OSError:
            raise StorageUnavailable('Could not store the image. No payment was recorded.')
        # Failed metadata/audit writes leave only a quarantined orphan; cleanup
        # never removes any file referenced by a committed MediaAsset row.


def eligible_receipt(asset_id, bill, user):
    try:
        asset=MediaAsset.objects.select_for_update().get(pk=uuid.UUID(str(asset_id)),purpose='receipt',bill=bill,uploaded_by=user,finalized=False,created_at__gte=timezone.now()-timedelta(hours=24))
    except (MediaAsset.DoesNotExist,ValueError,TypeError):
        raise ValidationError('Attach a fresh receipt image for this payment. A receipt cannot be reused for another transaction.')
    with open_verified(asset):pass
    return asset


def finalize(asset, bill_type='household', payment_id=None):
    with open_verified(asset):pass
    stamp=timezone.localtime(asset.created_at).strftime('%Y-%m-%d_%H-%M-%S_PHT')
    suffix=Path(asset.storage_name).suffix
    label=f'{bill_type}_payment-{payment_id}' if payment_id is not None else 'household-qr'
    name=f'{stamp}_{label}_{asset.pk.hex}{suffix}'
    try:
        # Hard-link creates without overwriting; rename is not allowed to replace evidence.
        os.link(path_for(asset.storage_name),path_for(name),follow_symlinks=False)
        sync_directory()
        path_for(asset.storage_name).unlink()
        sync_directory()
    except OSError:
        raise StorageUnavailable('Could not finalize receipt storage. No payment was recorded; attach the image again.')
    asset.storage_name=name;asset.finalized=True
    asset.save(update_fields=['storage_name','finalized'])


def cleanup_unused(now=None):
    now=now or timezone.now();cutoff=now-timedelta(hours=48)
    with transaction.atomic():
        WorkerHeartbeat.objects.get_or_create(name='media-lock')
        WorkerHeartbeat.objects.select_for_update().get(name='media-lock')
        candidates=MediaAsset.objects.select_for_update().filter(finalized=False,created_at__lt=cutoff)
        for asset in candidates:
            if Payment.objects.filter(receipt=asset).exists() or ReceiptRevision.objects.filter(asset=asset).exists() or PaymentQR.objects.filter(asset=asset).exists():continue
            path_for(asset.storage_name).unlink(missing_ok=True)
            asset.delete()
        referenced=set(MediaAsset.objects.values_list('storage_name',flat=True))
        for path in root().iterdir():
            if path.is_file() and not path.is_symlink() and path.name not in referenced and path.stat().st_mtime<cutoff.timestamp():
                path.unlink()
        sync_directory()
