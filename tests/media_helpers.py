import io
from PIL import Image, ImageDraw
from django.core.files.uploadedfile import SimpleUploadedFile
from tracker.media import stage


def fictional_image(name='fictional.png'):
    image=Image.new('RGB',(160,96),'white')
    ImageDraw.Draw(image).text((8,35),'FICTIONAL RECEIPT',fill='black')
    output=io.BytesIO();image.save(output,format='PNG')
    return SimpleUploadedFile(name,output.getvalue(),content_type='image/png')


def receipt(bill,user):
    return stage(fictional_image(),user,'receipt',bill)
