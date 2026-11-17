"""Render the project's simple f. mark into installable app icon sizes (Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
font_paths = [root / 'static/fonts/dm-sans.ttf', Path('C:/Windows/Fonts/segoeuib.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]
font_path = next((path for path in font_paths if path.exists()), None)
for size in (180, 192, 512):
    scale = 4
    image = Image.new('RGB', (size * scale, size * scale), '#9E6235')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), int(size * scale * .73)) if font_path else ImageFont.load_default(size=int(size * scale * .73))
    draw.text((size * scale * .32, size * scale * .03), 'f', font=font, fill='#F5EBE1')
    x,y,r = size*scale*.72,size*scale*.72,size*scale*.045
    draw.ellipse((x-r,y-r,x+r,y+r),fill='#F5EBE1')
    image.resize((size,size),Image.Resampling.LANCZOS).save(root/'static'/f'icon-{size}.png')
