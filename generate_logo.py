"""Generate the ABC fallback PNG logo. Run once; output goes to assets/logo.png."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "assets" / "logo.png"
OUT.parent.mkdir(exist_ok=True)

SIZE = 600
BG = (10, 10, 10, 255)
YELLOW = (252, 211, 77, 255)
RED = (220, 38, 38, 255)
RED_DEEP = (153, 27, 27, 255)
WHITE = (255, 255, 255, 255)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

cx = cy = SIZE // 2
r = SIZE // 2 - 10

# Filled black circle background
d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BG)

# Outer split border — yellow on left half, red on right half
border_width = 14
# Yellow arc: 90° → 270° (left half going counter-clockwise = top→left→bottom)
d.arc((cx - r, cy - r, cx + r, cy + r), start=90, end=270, fill=YELLOW, width=border_width)
# Red arc: 270° → 90° (right half)
d.arc((cx - r, cy - r, cx + r, cy + r), start=270, end=450, fill=RED, width=border_width)

# Stylized red bicep silhouette (flexed arm on the left side)
bicep_pts = [
    (cx - 175, cy - 30),
    (cx - 175, cy - 90),
    (cx - 100, cy - 115),
    (cx - 55, cy - 60),
    (cx - 50, cy - 10),
    (cx - 75, cy + 25),
    (cx - 55, cy + 65),
    (cx - 80, cy + 110),
    (cx - 140, cy + 115),
    (cx - 180, cy + 80),
    (cx - 195, cy + 20),
    (cx - 185, cy - 10),
]
d.polygon(bicep_pts, fill=RED)
# Fist detail (small red ellipse at top of bicep)
d.ellipse((cx - 130, cy - 130, cx - 80, cy - 90), fill=RED_DEEP)

# Try to load Impact font, fall back gracefully
def load_font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()

font_brand = load_font(["impact.ttf", "Impact.ttf", "arialbd.ttf", "Arial Bold.ttf"], 145)
font_tagline = load_font(["arialbd.ttf", "Arial Bold.ttf", "arial.ttf"], 30)
font_since = load_font(["ariali.ttf", "arial.ttf"], 24)

# ABC text — yellow with red drop-shadow, positioned right of bicep
text = "ABC"
tx = cx + 25
ty = cy - 75
# Red drop shadow
d.text((tx + 4, ty + 4), text, font=font_brand, fill=RED_DEEP, anchor="mm")
# Yellow main
d.text((tx, ty), text, font=font_brand, fill=YELLOW, anchor="mm")

# FITNESS · CLUB tagline (white) — centered under the ABC text
d.text((cx, cy + 50), "FITNESS · CLUB", font=font_tagline, fill=WHITE, anchor="mm")

# Since 2020 (yellow italic) — at bottom
d.text((cx, cy + 110), "SINCE 2020", font=font_since, fill=YELLOW, anchor="mm")

img.save(OUT, "PNG")
print(f"OK: {OUT}")
