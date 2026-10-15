"""Generate the add-on's colored panel icons (icons/png/*.png).

Original artwork drawn from simple geometric primitives; the generated PNGs are
dedicated to the public domain (CC0 1.0), as Blender's extension platform
requires for bundled assets. Development tool only (needs Pillow); the PNGs are
committed and this script is excluded from the extension package.

    python scripts/generate_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 32
SCALE = 8  # supersampling factor for smooth edges
S = SIZE * SCALE
W = round(2.4 * SCALE)  # stroke width

# Categories are monochrome, close to Blender's own icon tone on the default
# dark theme, so they read as part of the UI; only Favorites is gold.
MONO = "#D4D4D4"
GOLD = "#F2C14E"
# Result statuses; shapes differ so color is never the only cue.
OK = "#70CB89"
WARNING = "#E5BE62"
ERROR = "#EF8585"
INFO = "#83AFF0"
IDLE = "#B0B0B0"

OUT = Path(__file__).resolve().parents[1] / "icons" / "png"


def p(*xy):
    """Scale 32-px design coordinates to the supersampled canvas."""
    return [v * SCALE for v in xy]


def canvas():
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def save(image, name):
    OUT.mkdir(parents=True, exist_ok=True)
    image.resize((SIZE, SIZE), Image.LANCZOS).save(OUT / f"{name}.png")


def line(d, color, *points):
    d.line(p(*points), fill=color, width=W, joint="curve")
    for x, y in zip(points[::2], points[1::2]):
        r = W / 2
        d.ellipse((x * SCALE - r, y * SCALE - r, x * SCALE + r, y * SCALE + r), fill=color)


def ring(d, color, cx, cy, r, width=W):
    d.ellipse(p(cx - r, cy - r, cx + r, cy + r), outline=color, width=width)


def dot(d, color, cx, cy, r):
    d.ellipse(p(cx - r, cy - r, cx + r, cy + r), fill=color)


def rect(d, color, x0, y0, x1, y1, fill=False):
    if fill:
        d.rounded_rectangle(p(x0, y0, x1, y1), radius=1.5 * SCALE, fill=color)
    else:
        d.rounded_rectangle(p(x0, y0, x1, y1), radius=1.5 * SCALE, outline=color, width=W)


# --- categories ------------------------------------------------------------

def shape_keys(c):
    image, d = canvas()
    d.ellipse(p(4, 9, 20, 25), outline=c, width=W)
    d.ellipse(p(12, 5, 28, 21), outline=c, width=W)
    return image


def favorites(c):
    import math
    image, d = canvas()
    points = []
    for i in range(10):
        r = 13 if i % 2 == 0 else 5.6
        a = math.radians(-90 + i * 36)
        points.append((16 + r * math.cos(a)) * SCALE)
        points.append((17 + r * math.sin(a)) * SCALE)
    d.polygon(points, fill=c)
    return image


def mesh(c):
    image, d = canvas()
    line(d, c, 16, 5, 27, 26, 5, 26, 16, 5)
    for x, y in ((16, 5), (27, 26), (5, 26)):
        dot(d, c, x, y, 3.2)
    return image


def quad(c):
    image, d = canvas()
    rect(d, c, 5, 5, 27, 27)
    line(d, c, 16, 5, 16, 27)
    line(d, c, 5, 16, 27, 16)
    return image


def cad(c):
    image, d = canvas()
    line(d, c, 4, 27, 4, 19, 11, 19, 11, 12, 19, 12, 19, 5, 28, 5, 28, 27, 4, 27)
    return image


def gn(c):
    image, d = canvas()
    line(d, c, 8, 9, 23, 16)
    line(d, c, 8, 23, 23, 16)
    for x, y in ((8, 9), (8, 23), (23, 16)):
        dot(d, c, x, y, 4.6)
    return image


def materials(c):
    image, d = canvas()
    ring(d, c, 16, 16, 11)
    d.pieslice(p(5, 5, 27, 27), 45, 225, fill=c)
    return image


def colors(c):
    image, d = canvas()
    for i, angle in enumerate((-25, 0, 25)):
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rect(ld, c, 12, 4, 20, 25, fill=i == 2)
        if i != 2:
            rect(ld, c, 12, 4, 20, 25)
        image.alpha_composite(layer.rotate(angle, center=(16 * SCALE, 27 * SCALE), resample=Image.BICUBIC))
    return image


def uv(c):
    image, d = canvas()
    # Unfolded cube net: a cross of five squares.
    line(d, c, 12, 4, 20, 4, 20, 12, 28, 12, 28, 20, 20, 20, 20, 28, 12, 28, 12, 20, 4, 20, 4, 12, 12, 12, 12, 4)
    line(d, c, 12, 12, 20, 12, 20, 20, 12, 20, 12, 12)
    return image


def bakers(c):
    image, d = canvas()
    for y in (5, 10, 15):
        line(d, c, 4, y + 3, 16, y, 28, y + 3, 16, y + 6, 4, y + 3)
    line(d, c, 16, 22, 16, 29)
    line(d, c, 12, 25, 16, 29, 20, 25)
    return image


def presets(c):
    image, d = canvas()
    for y, x in ((8, 20), (16, 10), (24, 23)):
        line(d, c, 4, y, 28, y)
        dot(d, c, x, y, 3.6)
    return image


def kalibra(c):
    image, d = canvas()
    line(d, c, 5, 10, 21, 10, 21, 27, 5, 27, 5, 10)
    line(d, c, 5, 10, 11, 5, 27, 5, 27, 21, 21, 27)
    line(d, c, 21, 10, 27, 5)
    return image


def babylon(c):
    image, d = canvas()
    line(d, c, 4, 13, 18, 13, 18, 28, 4, 28, 4, 13)
    line(d, c, 4, 13, 9, 8, 13, 8)
    line(d, c, 18, 21, 22, 17)
    line(d, c, 17, 4, 28, 4, 28, 15)
    line(d, c, 28, 4, 19, 13)
    return image


# --- statuses --------------------------------------------------------------

def ok(c):
    image, d = canvas()
    line(d, c, 6, 17, 13, 24, 26, 8)
    return image


def warning(c):
    image, d = canvas()
    d.polygon(p(16, 3, 30, 28, 2, 28), fill=c)
    dark = (40, 40, 40, 255)
    d.rounded_rectangle(p(14.6, 11, 17.4, 21), radius=SCALE, fill=dark)
    dot(d, dark, 16, 24.5, 1.7)
    return image


def error(c):
    image, d = canvas()
    dot(d, c, 16, 16, 13)
    dark = (40, 40, 40, 255)
    d.line(p(11, 11, 21, 21), fill=dark, width=round(2.8 * SCALE))
    d.line(p(21, 11, 11, 21), fill=dark, width=round(2.8 * SCALE))
    return image


def info(c):
    image, d = canvas()
    ring(d, c, 16, 16, 12)
    d.rounded_rectangle(p(14.6, 14, 17.4, 23), radius=SCALE, fill=c)
    dot(d, c, 16, 10, 1.8)
    return image


def idle(c):
    image, d = canvas()
    ring(d, c, 16, 16, 10)
    return image


def running(c):
    image, d = canvas()
    line(d, c, 7, 4, 25, 4)
    line(d, c, 7, 28, 25, 28)
    line(d, c, 9, 4, 9, 8, 16, 16, 9, 24, 9, 28)
    line(d, c, 23, 4, 23, 8, 16, 16, 23, 24, 23, 28)
    d.polygon(p(11.5, 26, 20.5, 26, 16, 20), fill=c)
    return image


def cancelled(c):
    image, d = canvas()
    rect(d, c, 8, 8, 24, 24, fill=True)
    return image


ICONS = {
    "category_favorites": (favorites, GOLD),
    "category_shape_keys": (shape_keys, MONO),
    "category_mesh": (mesh, MONO),
    "category_quad": (quad, MONO),
    "category_cad": (cad, MONO),
    "category_gn": (gn, MONO),
    "category_materials": (materials, MONO),
    "category_colors": (colors, MONO),
    "category_uv": (uv, MONO),
    "category_bakers": (bakers, MONO),
    "category_presets": (presets, MONO),
    "category_kalibra": (kalibra, MONO),
    "category_babylon": (babylon, MONO),
    "status_ok": (ok, OK),
    "status_warning": (warning, WARNING),
    "status_error": (error, ERROR),
    "status_info": (info, INFO),
    "status_idle": (idle, IDLE),
    "status_running": (running, INFO),
    "status_cancelled": (cancelled, IDLE),
}


def main():
    for name, (draw, color) in ICONS.items():
        save(draw(color), name)
    print(f"Wrote {len(ICONS)} icons to {OUT}")


if __name__ == "__main__":
    main()
