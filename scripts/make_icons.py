"""python -m scripts.make_icons  -> static/icon-192.png and icon-512.png (uses static/logo.png if present)"""
import os

from PIL import Image, ImageDraw, ImageFont

for size in (192, 512):
    if os.path.exists("static/logo.png"):
        logo = Image.open("static/logo.png").convert("RGBA")
        logo.thumbnail((int(size * 0.8), int(size * 0.8)))
        im = Image.new("RGBA", (size, size), "#FFFFFF")
        im.paste(logo, ((size - logo.width) // 2, (size - logo.height) // 2), logo)
    else:
        im = Image.new("RGB", (size, size), "#B5452A")
        d = ImageDraw.Draw(im)
        d.text((size / 2, size / 2), "H", fill="white", anchor="mm",
               font=ImageFont.load_default(size=int(size * 0.6)))
    im.convert("RGB").save(f"static/icon-{size}.png")
    print("wrote", f"static/icon-{size}.png")
